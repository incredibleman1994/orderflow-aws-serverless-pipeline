"""
file-processor  (SQS -> Lambda)

Flow
  1. A CSV lands in  s3://<bucket>/incoming/  and S3 sends an event to an SQS queue.
  2. Lambda reads the queue, downloads each CSV, validates every row and writes
     valid orders to DynamoDB with a conditional put (idempotent: re-processing
     the same file never creates duplicates).
  3. The file is moved to  processed/YYYY/MM/DD/  (or  failed/YYYY/MM/DD/  if the
     file itself is unusable) and a summary is published to SNS.

Error handling
  * Bad *content* (missing columns, not UTF-8, too large)  -> permanent failure:
    file goes to failed/, no retry.
  * Bad *rows*                                              -> rejected and reported,
    the good rows are still ingested.
  * Transient problems (throttling, network, ...)           -> the SQS message is
    returned in batchItemFailures, retried, and finally lands in the dead-letter queue.

Environment variables
  TABLE_NAME (required), TOPIC_ARN, MAX_ROWS (2000), MAX_FILE_BYTES (5242880), LOG_LEVEL
"""
import csv
import io
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import unquote_plus

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

TABLE_NAME = os.environ["TABLE_NAME"]
TOPIC_ARN = os.environ.get("TOPIC_ARN", "")
MAX_ROWS = int(os.environ.get("MAX_ROWS", "2000"))
MAX_FILE_BYTES = int(os.environ.get("MAX_FILE_BYTES", str(5 * 1024 * 1024)))

INCOMING_PREFIX = "incoming/"
REQUIRED_COLUMNS = ("order_id", "customer", "product", "quantity", "unit_price")
ORDER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

s3 = boto3.client("s3")
sns = boto3.client("sns")
table = boto3.resource("dynamodb").Table(TABLE_NAME)


class PermanentFailure(Exception):
    """The file can never be processed - do not retry."""


class ValidationError(ValueError):
    """A single CSV row is invalid."""


# ----------------------------------------------------------------- validation
def validate_row(row: dict) -> dict:
    order_id = (row.get("order_id") or "").strip()
    if not ORDER_ID_RE.match(order_id):
        raise ValidationError("order_id must be 1-64 characters: letters, digits, '-' or '_'")

    customer = (row.get("customer") or "").strip()
    if not customer or len(customer) > 100:
        raise ValidationError("customer is required (max 100 characters)")

    product = (row.get("product") or "").strip()
    if not product or len(product) > 100:
        raise ValidationError("product is required (max 100 characters)")

    try:
        quantity = int((row.get("quantity") or "").strip())
    except ValueError:
        raise ValidationError("quantity must be a whole number")
    if not 1 <= quantity <= 100000:
        raise ValidationError("quantity must be between 1 and 100000")

    try:
        unit_price = Decimal((row.get("unit_price") or "").strip())
    except InvalidOperation:
        raise ValidationError("unit_price must be a number")
    if not unit_price.is_finite() or not Decimal("0") < unit_price <= Decimal("10000000"):
        raise ValidationError("unit_price must be greater than 0 and at most 10,000,000")
    unit_price = unit_price.quantize(Decimal("0.01"))
    if unit_price <= 0:
        raise ValidationError("unit_price must be at least 0.01")

    return {
        "order_id": order_id,
        "customer": customer,
        "product": product,
        "quantity": quantity,
        "unit_price": unit_price,
        "total": unit_price * quantity,
    }


# ------------------------------------------------------------------ ingestion
def ingest(bucket: str, key: str) -> dict:
    """Read, validate and store one CSV file. Raises PermanentFailure for unusable files."""
    obj = s3.get_object(Bucket=bucket, Key=key)
    if obj["ContentLength"] > MAX_FILE_BYTES:
        raise PermanentFailure(f"file is larger than {MAX_FILE_BYTES} bytes")

    try:
        text = obj["Body"].read().decode("utf-8-sig")  # tolerate Excel's BOM
    except UnicodeDecodeError:
        raise PermanentFailure("file is not valid UTF-8 text")

    reader = csv.DictReader(io.StringIO(text))
    try:
        reader.fieldnames = [h.strip() for h in (reader.fieldnames or [])]
        missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise PermanentFailure("missing required column(s): " + ", ".join(missing))
        rows = list(reader)
    except csv.Error as exc:
        raise PermanentFailure(f"unreadable CSV: {exc}")

    if len(rows) > MAX_ROWS:
        raise PermanentFailure(f"file has more than {MAX_ROWS} rows")

    ingested_at = datetime.now(timezone.utc).isoformat()
    valid_items, rejected = [], []
    for line_no, row in enumerate(rows, start=2):  # line 1 is the header
        try:
            item = validate_row(row)
            item["source_file"] = key
            item["ingested_at"] = ingested_at
            valid_items.append(item)
        except ValidationError as exc:
            rejected.append({"line": line_no, "reason": str(exc)})

    ingested = duplicates = 0
    for item in valid_items:
        try:
            table.put_item(Item=item, ConditionExpression="attribute_not_exists(order_id)")
            ingested += 1
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
                duplicates += 1  # already stored by an earlier file / earlier attempt
            else:
                raise  # transient -> let SQS retry

    return {"ingested": ingested, "duplicates": duplicates, "rejected": rejected}


def move(bucket: str, key: str, status: str) -> str:
    now = datetime.now(timezone.utc)
    dest = f"{status}/{now:%Y/%m/%d}/{key[len(INCOMING_PREFIX):]}"
    s3.copy_object(Bucket=bucket, Key=dest, CopySource={"Bucket": bucket, "Key": key})
    s3.delete_object(Bucket=bucket, Key=key)
    return dest


def notify(key: str, summary: dict, destination: str) -> None:
    if not TOPIC_ARN:
        return
    name = os.path.basename(key)
    subject = f"[Orders pipeline] {summary['status']}: {name}"
    subject = subject.encode("ascii", "replace").decode()[:100]
    lines = [
        f"File:        {name}",
        f"Status:      {summary['status']}",
        f"Moved to:    {destination}",
        f"Ingested:    {summary['ingested']}",
        f"Duplicates:  {summary['duplicates']}",
        f"Rejected:    {len(summary['rejected'])}",
    ]
    if summary.get("reason"):
        lines.append(f"Reason:      {summary['reason']}")
    for r in summary["rejected"][:10]:
        lines.append(f"  - line {r['line']}: {r['reason']}")
    if len(summary["rejected"]) > 10:
        lines.append(f"  ... and {len(summary['rejected']) - 10} more")
    try:
        sns.publish(TopicArn=TOPIC_ARN, Subject=subject, Message="\n".join(lines))
    except ClientError:
        # The data is already stored; never fail (and retry) just because the email failed.
        logger.exception("Could not publish SNS notification")


def handle_file(bucket: str, key: str, totals: dict) -> None:
    try:
        try:
            summary = ingest(bucket, key)
            summary["status"] = "PROCESSED"
            destination = move(bucket, key, "processed")
            totals["FilesProcessed"] += 1
        except PermanentFailure as exc:
            logger.warning("Permanent failure for %s: %s", key, exc)
            summary = {"status": "FAILED", "reason": str(exc), "ingested": 0, "duplicates": 0, "rejected": []}
            destination = move(bucket, key, "failed")
            totals["FilesFailed"] += 1
    except s3.exceptions.NoSuchKey:
        # At-least-once delivery: an earlier attempt already moved this file.
        logger.warning("s3://%s/%s no longer exists - already processed", bucket, key)
        return

    totals["RowsIngested"] += summary["ingested"]
    totals["RowsRejected"] += len(summary["rejected"])
    totals["DuplicateRows"] += summary["duplicates"]
    logger.info(
        "file=%s status=%s ingested=%d duplicates=%d rejected=%d",
        key, summary["status"], summary["ingested"], summary["duplicates"], len(summary["rejected"]),
    )
    notify(key, summary, destination)


# ------------------------------------------------------------------- metrics
def emit_metrics(totals: dict) -> None:
    """CloudWatch Embedded Metric Format: a JSON log line that becomes custom metrics, no API call."""
    print(json.dumps({
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [{
                "Namespace": "OrdersPipeline",
                "Dimensions": [["Function"]],
                "Metrics": [{"Name": name, "Unit": "Count"} for name in totals],
            }],
        },
        "Function": "file-processor",
        **totals,
    }))


# ------------------------------------------------------------------- handler
def lambda_handler(event, context):
    totals = {
        "FilesProcessed": 0, "FilesFailed": 0, "RowsIngested": 0,
        "RowsRejected": 0, "DuplicateRows": 0, "MessageFailures": 0,
    }
    batch_item_failures = []

    for record in event.get("Records", []):
        try:
            body = json.loads(record["body"])
            # S3 sends an "s3:TestEvent" (no Records list) when the notification is first created.
            for s3_record in body.get("Records", []):
                bucket = s3_record["s3"]["bucket"]["name"]
                key = unquote_plus(s3_record["s3"]["object"]["key"])  # keys arrive URL-encoded
                if not key.startswith(INCOMING_PREFIX) or not key.lower().endswith(".csv"):
                    logger.info("Ignoring %s", key)
                    continue
                handle_file(bucket, key, totals)
        except Exception:
            logger.exception("Failed to process SQS message %s", record.get("messageId"))
            batch_item_failures.append({"itemIdentifier": record["messageId"]})
            totals["MessageFailures"] += 1

    emit_metrics(totals)
    return {"batchItemFailures": batch_item_failures}

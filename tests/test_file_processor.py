import json
import pathlib

import boto3
import pytest
from botocore.exceptions import ClientError

from conftest import BUCKET, ROOT, load, sqs_event

SAMPLES = ROOT / "sample-data"


@pytest.fixture
def proc(aws):
    return load("file_processor", "src/file_processor/lambda_function.py")


def upload(aws, name: str, body: bytes | None = None, key: str | None = None):
    data = body if body is not None else (SAMPLES / name).read_bytes()
    key = key or f"incoming/{name}"
    aws["s3"].put_object(Bucket=BUCKET, Key=key, Body=data)
    return key


def keys(aws, prefix):
    resp = aws["s3"].list_objects_v2(Bucket=BUCKET, Prefix=prefix)
    return [o["Key"] for o in resp.get("Contents", [])]


def order_count():
    return boto3.client("dynamodb", region_name="ap-south-1").scan(TableName="orders")["Count"]


def test_valid_file_is_ingested_and_moved(aws, proc):
    key = upload(aws, "orders_valid.csv")
    result = proc.lambda_handler(sqs_event(key), None)
    assert result == {"batchItemFailures": []}
    assert order_count() == 8
    assert keys(aws, "incoming/") == []
    assert len(keys(aws, "processed/")) == 1


def test_reprocessing_same_orders_creates_no_duplicates(aws, proc):
    proc.lambda_handler(sqs_event(upload(aws, "orders_valid.csv")), None)
    key2 = upload(aws, "orders_valid.csv", key="incoming/orders_valid_again.csv")
    proc.lambda_handler(sqs_event(key2, "m-2"), None)
    assert order_count() == 8  # still 8, duplicates skipped


def test_invalid_rows_are_rejected_but_valid_rows_are_kept(aws, proc):
    upload(aws, "orders_valid.csv")
    proc.lambda_handler(sqs_event("incoming/orders_valid.csv"), None)
    key = upload(aws, "orders_with_errors.csv")
    result = proc.lambda_handler(sqs_event(key, "m-2"), None)
    assert result["batchItemFailures"] == []
    # 8 earlier + ORD-2001 + ORD-2005 ; ORD-1001 is a duplicate; 4 rows invalid
    assert order_count() == 10
    assert len(keys(aws, "processed/")) == 2


def test_bad_header_goes_to_failed_without_retry(aws, proc):
    key = upload(aws, "orders_bad_header.csv")
    result = proc.lambda_handler(sqs_event(key), None)
    assert result == {"batchItemFailures": []}
    assert order_count() == 0
    assert len(keys(aws, "failed/")) == 1
    assert keys(aws, "incoming/") == []


def test_non_utf8_file_goes_to_failed(aws, proc):
    key = upload(aws, "x", body=b"\xff\xfe\x00bad", key="incoming/binary.csv")
    proc.lambda_handler(sqs_event(key), None)
    assert len(keys(aws, "failed/")) == 1


def test_s3_test_event_is_ignored(aws, proc):
    event = {"Records": [{"messageId": "t-1", "body": json.dumps({"Event": "s3:TestEvent"})}]}
    assert proc.lambda_handler(event, None) == {"batchItemFailures": []}


def test_file_already_processed_is_skipped_not_retried(aws, proc):
    # key is in the event but no longer exists (a previous attempt moved it)
    result = proc.lambda_handler(sqs_event("incoming/ghost.csv"), None)
    assert result == {"batchItemFailures": []}


def test_url_encoded_keys_are_decoded(aws, proc):
    upload(aws, "x", body=(SAMPLES / "orders_valid.csv").read_bytes(), key="incoming/my file.csv")
    result = proc.lambda_handler(sqs_event("incoming/my+file.csv"), None)
    assert result == {"batchItemFailures": []}
    assert order_count() == 8


def test_transient_dynamodb_error_returns_batch_item_failure(aws, proc, monkeypatch):
    key = upload(aws, "orders_valid.csv")

    def boom(**kwargs):
        raise ClientError({"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "slow down"}}, "PutItem")

    monkeypatch.setattr(proc.table, "put_item", boom)
    result = proc.lambda_handler(sqs_event(key, "m-9"), None)
    assert result == {"batchItemFailures": [{"itemIdentifier": "m-9"}]}
    assert keys(aws, "incoming/") == [key]  # file untouched so the retry can succeed


def test_malformed_message_body_is_reported_as_failure(aws, proc):
    event = {"Records": [{"messageId": "bad-1", "body": "not json"}]}
    assert proc.lambda_handler(event, None) == {"batchItemFailures": [{"itemIdentifier": "bad-1"}]}


def test_non_incoming_or_non_csv_keys_are_ignored(aws, proc):
    for key in ("processed/a.csv", "incoming/readme.txt"):
        assert proc.lambda_handler(sqs_event(key), None) == {"batchItemFailures": []}

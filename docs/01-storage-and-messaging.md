# Step 1 - S3, SQS and SNS (the event backbone)

**Region:** `ap-south-1` (any region works - keep everything in the same one).

Build order matters: the queue policy must exist **before** S3 can be pointed at the queue.

## 1.1 S3 bucket
S3 -> Create bucket: `orders-pipeline-<account-id>-ap-south-1`

| Setting | Value |
|---|---|
| Block all public access | **ON** |
| Default encryption | SSE-S3 |
| Versioning | Off (processed files are kept in `processed/` instead) |

Then:
1. Create three "folders": `incoming/`, `processed/`, `failed/`.
2. **Permissions -> Bucket policy:** paste `iam/s3-bucket-policy.json` (replace `REPLACE_BUCKET`). It denies any non-HTTPS access.
3. **Management -> Lifecycle rules:**
   - `expire-processed`: prefix `processed/` -> expire current objects after **30 days**
   - `expire-failed`: prefix `failed/` -> expire after **90 days**
   - `abort-incomplete-uploads`: whole bucket -> delete incomplete multipart uploads after **7 days**

## 1.2 Dead-letter queue (DLQ)
SQS -> Create queue -> **Standard**: `file-events-dlq`
- Message retention: **14 days**
- Encryption: SSE-SQS (default)

## 1.3 Main queue
SQS -> Create queue -> **Standard**: `file-events-queue`

| Setting | Value | Why |
|---|---|---|
| Visibility timeout | **360 seconds** | AWS recommends at least 6x the Lambda timeout (60 s) |
| Message retention | 4 days | |
| Receive message wait time | 20 s | Long polling |
| Encryption | **SSE-SQS** (Amazon SQS-managed) | S3 cannot publish to a queue encrypted with the AWS-managed KMS key |
| Dead-letter queue | Enabled -> `file-events-dlq`, **Maximum receives = 3** | Poison messages stop retrying after 3 attempts |
| Access policy | Paste `iam/sqs-queue-policy.json` (replace the `REPLACE_*` values) | Only *your* bucket can send messages |

## 1.4 Connect S3 to SQS
Bucket -> **Properties -> Event notifications -> Create event notification**

| Setting | Value |
|---|---|
| Name | `new-csv-uploaded` |
| Prefix | `incoming/` |
| Suffix | `.csv` |
| Event types | All object create events |
| Destination | SQS queue -> `file-events-queue` |

> The prefix filter is essential: the Lambda writes to `processed/` and `failed/`. Without it the function would
> trigger itself in an infinite loop.

S3 sends a one-off `s3:TestEvent` message to the queue when you save - the Lambda is written to ignore it.

## 1.5 SNS topics
SNS -> Create topic (Standard):
- `pipeline-notifications` - business summaries ("file X processed: 8 ingested, 2 rejected")
- `pipeline-alerts` - operational alarms (used in step 6)

Subscribe your email to **both** (Protocol: Email) and confirm both subscription emails.

Screenshot: `screenshots/01-s3-event-notification.png`, `screenshots/01-sqs-dlq-config.png`

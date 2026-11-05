# Step 4 - Lambda: file-processor

## 4.1 Create the function
Lambda -> Create function -> *Author from scratch*

| Setting | Value |
|---|---|
| Name | `file-processor` |
| Runtime | Python 3.12 |
| Architecture | arm64 (Graviton - cheaper, pure Python so no changes needed) |
| Execution role | existing -> `orders-processor-role` |

Paste the contents of `src/file_processor/lambda_function.py` into the code editor and **Deploy**.
No extra libraries are needed - `boto3` is included in the Lambda runtime.

## 4.2 Configuration

| Setting | Value |
|---|---|
| Memory | 256 MB |
| Timeout | **60 seconds** (must be lower than the queue's 360 s visibility timeout) |
| Environment variables | `TABLE_NAME=orders`, `TOPIC_ARN=<pipeline-notifications ARN>`, `MAX_ROWS=2000` |

## 4.3 Connect the queue
Function -> **Add trigger** -> SQS -> `file-events-queue`

| Setting | Value |
|---|---|
| Batch size | 5 |
| Batch window | 0-5 seconds |
| **Report batch item failures** | **Checked** - only the failed messages return to the queue, not the whole batch |
| **Maximum concurrency** | **5** - protects DynamoDB and caps cost if someone uploads 1,000 files |

## 4.4 How it behaves

| Situation | What happens |
|---|---|
| Valid file | Rows stored -> file moved to `processed/YYYY/MM/DD/` -> summary email |
| Some bad rows | Good rows stored, bad rows listed in the email, file moved to `processed/` |
| Missing columns / not UTF-8 / too big | **Permanent failure**: file moved to `failed/`, email sent, **no retry** |
| Same order seen again | Conditional write skips it (counted as a duplicate) |
| Transient error (throttling, network) | Message returned to the queue -> retried -> after 3 receives lands in the DLQ |
| Message arrives for a file already moved | Logged and skipped (at-least-once delivery) |

## 4.5 Custom metrics for free (Embedded Metric Format)
Each invocation prints one JSON line in CloudWatch's Embedded Metric Format. CloudWatch turns it into metrics
in the `OrdersPipeline` namespace with no extra API calls or permissions:
`FilesProcessed`, `FilesFailed`, `RowsIngested`, `RowsRejected`, `DuplicateRows`, `MessageFailures`.

> With partial-batch responses Lambda counts the invocation as a *success*, so the built-in `Errors` metric will not
> show failed messages. That is why `MessageFailures` and the DLQ depth are the alarms that matter (step 6).

Screenshot: `screenshots/04-lambda-trigger-config.png`

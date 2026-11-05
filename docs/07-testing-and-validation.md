# Step 7 - Testing and validation

Upload files with the S3 console (bucket -> `incoming/` -> Upload) or CloudShell:
`aws s3 cp orders_valid.csv s3://<bucket>/incoming/`. Sample files are in `sample-data/`.

| # | Test | Steps | Expected result |
|---|---|---|---|
| 1 | **Happy path** | Upload `orders_valid.csv` | Within seconds: 8 items in DynamoDB; file moved to `processed/YYYY/MM/DD/`; summary email "PROCESSED, ingested 8" |
| 2 | **Idempotency** | Rename the file to `orders_valid_again.csv` and upload it | Email shows ingested 0, duplicates 8; table still has 8 items |
| 3 | **Bad rows** | Upload `orders_with_errors.csv` | 2 new orders (`ORD-2001`, `ORD-2005`); 1 duplicate (`ORD-1001`); 4 rejected rows listed with line numbers and reasons |
| 4 | **Bad file** | Upload `orders_bad_header.csv` | File lands in `failed/`; email says "missing required column(s): unit_price"; **no retries** (queue stays empty) |
| 5 | **Poison message -> DLQ** | SQS console -> `file-events-queue` -> *Send message*: `not json` | Message fails 3 times (~12 min with a 6-min visibility timeout; for a quick test temporarily set Maximum receives = 1), then appears in the DLQ -> `dlq-not-empty` alarm email |
| 6 | **Break and recover** | Temporarily remove `dynamodb:PutItem` from `orders-processor-policy`, upload a CSV, watch the retries and the DLQ fill, **restore the permission**, then use **DLQ redrive** ("Start DLQ redrive") | After the redrive the file is processed successfully - nothing was lost |
| 7 | **Burst / concurrency cap** | Upload 20 small CSVs at once | Lambda concurrency never exceeds 5 (check `ConcurrentExecutions`); all files processed |
| 8 | **API without a token** | `curl $API/orders/ORD-1001` | `401 Unauthorized` |
| 9 | **API with a token** | Use the CloudShell commands in step 5 | `200` with the order JSON |
| 10 | **API behaviour** | Unknown id; `GET /orders` without `customer`; paging with `limit=1` and `next_token` | `404`; `400`; each page returns the next order, no overlaps |
| 11 | **Public access blocked** | Open an object's *Object URL* in a browser | `AccessDenied` |
| 12 | **Least privilege** | Review role permissions; try `aws s3 ls` from a Lambda test event (optional) | Only the specific actions on specific resources are allowed |

## Optional: run the unit tests locally
The Lambda logic is also covered by 19 unit tests that run against mocked AWS services (no AWS account needed):
```bash
pip install -r requirements-dev.txt
pytest tests -v
```

## Results log (fill in with your real results)

| # | Date | Result (pass / notes) | Screenshot |
|---|---|---|---|
| 1 | | | |
| 2 | | | |
| 3 | | | |
| 4 | | | |
| 5 | | | |
| 6 | | | |
| 7 | | | |
| 8 | | | |
| 9 | | | |
| 10 | | | |
| 11 | | | |
| 12 | | | |

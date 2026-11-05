# Screenshots to capture

Name the files exactly like this and **blur your AWS account ID and email address**.

| File | What to show |
|---|---|
| `01-s3-event-notification.png` | S3 event notification: prefix `incoming/`, suffix `.csv`, destination SQS |
| `01-sqs-dlq-config.png` | Main queue with its dead-letter queue and max receives = 3 |
| `02-dynamodb-table-and-gsi.png` | The `orders` table and `customer-index` |
| `03-processor-role-permissions.png` | Permissions of `orders-processor-role` |
| `04-lambda-trigger-config.png` | SQS trigger: batch item failures + max concurrency |
| `05-api-routes-authorizer.png` | HTTP API routes with the JWT authorizer attached |
| `05-api-401-vs-200.png` | CloudShell: 401 without token, 200 with token |
| `06-dashboard.png` | Dashboard with live data after your tests |
| `06-alarms.png` | Alarm list |
| `07-processed-email.png` | The summary email (blur personal info) |
| `07-dlq-redrive.png` | DLQ with a message, and the redrive in progress |
| `07-dynamodb-items.png` | Items in the table after the happy-path test |

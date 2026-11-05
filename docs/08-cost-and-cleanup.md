# Step 8 - Cost awareness and cleanup

## Cost
Everything here is pay-per-use with **no always-on servers** (no NAT gateway, no load balancer, no EC2/RDS), so a full
build-and-test cycle normally costs well under a few US dollars and often falls within the AWS Free Tier or your
account's free credits. Check your account's current free-tier terms and the AWS Pricing Calculator for exact numbers.

| Service | Billing model |
|---|---|
| Lambda | Requests + GB-seconds (arm64 is cheaper than x86) |
| SQS, SNS | Per request / per notification |
| DynamoDB (on-demand) | Per read/write request + storage (+ PITR storage) |
| API Gateway (HTTP API) | Per million requests |
| Cognito | Per monthly active user, with a free allowance |
| S3 | Storage + requests (lifecycle rules keep it tiny) |
| CloudWatch | Logs ingested/stored, alarms and dashboards beyond the free allowance |

## Cleanup order
1. API Gateway -> delete `orders-api`
2. Lambda -> delete `file-processor` and `orders-api`
3. Remove the S3 event notification, then empty and delete the bucket
4. SQS -> delete `file-events-queue` and `file-events-dlq`
5. SNS -> delete both topics (and subscriptions)
6. DynamoDB -> delete `orders` (also removes PITR backups after you confirm)
7. Cognito -> delete the user pool
8. IAM -> delete both roles and the three custom policies
9. CloudWatch -> delete alarms, the dashboard and the two Lambda log groups
10. Billing -> check Cost Explorer the next day

Keeping the project but not paying for it is easy: with no traffic, almost everything here costs nothing.

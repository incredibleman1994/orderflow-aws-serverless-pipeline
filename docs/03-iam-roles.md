# Step 3 - IAM roles (one per function, least privilege)

Each Lambda gets its **own** role, so a bug or compromise in one cannot touch the other's resources.

Replace the placeholders in each JSON file first: `REPLACE_BUCKET`, `REPLACE_REGION`, `REPLACE_ACCOUNT_ID`.

## 3.1 Role for the file processor
1. IAM -> Policies -> Create policy -> JSON -> paste `iam/processor-policy.json` -> name `orders-processor-policy`
2. IAM -> Roles -> Create role -> *AWS service* -> *Lambda* (trust policy = `iam/lambda-trust-policy.json`)
3. Attach:

| Policy | Why |
|---|---|
| `AWSLambdaSQSQueueExecutionRole` (AWS managed) | Read/delete from SQS + write CloudWatch Logs |
| `orders-processor-policy` (yours) | Read/delete `incoming/*`, write `processed/*` and `failed/*`, `PutItem` on `orders`, publish to one SNS topic |

Role name: `orders-processor-role`

## 3.2 Role for the API function
1. Create policy from `iam/api-policy.json` -> `orders-api-policy` (read-only: `GetItem` and `Query` on the table and its GSI)
2. Create Lambda role, attach `AWSLambdaBasicExecutionRole` (AWS managed) + `orders-api-policy`

Role name: `orders-api-role`

## Things worth noticing
- The processor can **write** to the table but cannot read or delete from it; the API can **read** but never write.
- Neither role has `*` actions or `*` resources (apart from the log permissions inside the AWS-managed policies).
- The S3 permissions are scoped by prefix, so the processor cannot overwrite files it already moved.

Screenshot: `screenshots/03-processor-role-permissions.png`

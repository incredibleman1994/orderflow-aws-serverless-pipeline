# Step 6 - Monitoring and alerts

All alarms notify the **`pipeline-alerts`** SNS topic.

## 6.1 Alarms

| Alarm | Namespace / metric | Dimensions | Statistic | Condition |
|---|---|---|---|---|
| `dlq-not-empty` | SQS / `ApproximateNumberOfMessagesVisible` | QueueName=`file-events-dlq` | Maximum, 1 min | >= 1 |
| `queue-backlog-age` | SQS / `ApproximateAgeOfOldestMessage` | QueueName=`file-events-queue` | Maximum, 1 min | > 300 s |
| `processor-message-failures` | OrdersPipeline / `MessageFailures` | Function=`file-processor` | Sum, 1 min | >= 1 |
| `processor-throttles` | Lambda / `Throttles` | FunctionName=`file-processor` | Sum, 1 min | >= 1 |
| `processor-duration-p95` | Lambda / `Duration` | FunctionName=`file-processor` | p95, 5 min | > 48000 ms (80 % of the timeout) |
| `api-lambda-errors` | Lambda / `Errors` | FunctionName=`orders-api` | Sum, 1 min | >= 1 |
| `api-5xx` | ApiGateway / `5xx` | ApiId=`<api id>` | Sum, 5 min | >= 1 |
| `ddb-throttled-requests` | DynamoDB / `ThrottledRequests` | TableName=`orders` | Sum, 1 min | >= 1 |

Set **Treat missing data = Not breaching** on all of them (these metrics are empty when nothing happens).

## 6.2 Dashboard
CloudWatch -> Dashboards -> `orders-pipeline`. Suggested widgets:
1. SQS: visible messages (main queue vs DLQ) and age of oldest message
2. Lambda `file-processor`: Invocations, Errors, Duration (avg + p95), ConcurrentExecutions
3. `OrdersPipeline`: RowsIngested, RowsRejected, DuplicateRows, FilesFailed (Sum)
4. API Gateway: Count, 4xx, 5xx, Latency, IntegrationLatency
5. DynamoDB: ConsumedReadCapacityUnits / ConsumedWriteCapacityUnits

## 6.3 Logs Insights queries
Log groups `/aws/lambda/file-processor` and `/aws/lambda/orders-api`. Set retention to **14 days**.

Failures and warnings:
```
fields @timestamp, @message
| filter @message like /ERROR|WARNING/
| sort @timestamp desc
| limit 20
```
Slowest invocations:
```
filter @type = "REPORT"
| stats max(@duration) as max_ms, avg(@duration) as avg_ms, count(*) as runs by bin(5m)
```

## 6.4 Cost guardrail
Billing -> Budgets -> monthly cost budget (US$5 is plenty) with an email alert at 80 % actual.

Screenshots: `screenshots/06-dashboard.png`, `screenshots/06-alarms.png`

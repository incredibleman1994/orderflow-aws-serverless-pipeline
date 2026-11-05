# Step 2 - DynamoDB

DynamoDB -> Create table

| Setting | Value |
|---|---|
| Table name | `orders` |
| Partition key | `order_id` (String) |
| Table settings | *Customize settings* |
| Capacity mode | **On-demand** |
| Encryption | Owned by Amazon DynamoDB (default) |
| Deletion protection | Off for the lab |

## Global secondary index (query by customer)
Table -> **Indexes -> Create index**

| Setting | Value |
|---|---|
| Partition key | `customer` (String) |
| Sort key | `ingested_at` (String) |
| Index name | `customer-index` |
| Projected attributes | All |

## Point-in-time recovery
Table -> **Backups** -> Edit PITR -> **Turn on**.

## Data model

| Attribute | Type | Notes |
|---|---|---|
| `order_id` | String (PK) | Unique; used for idempotent writes |
| `customer` | String | GSI partition key |
| `product` | String | |
| `quantity` | Number | |
| `unit_price`, `total` | Number | Stored as exact decimals, returned by the API as 2-dp strings |
| `source_file` | String | Which upload the order came from |
| `ingested_at` | String (ISO-8601 UTC) | GSI sort key - newest-first listing |

## Access patterns (why this design)
| Question | Operation |
|---|---|
| Get one order | `GetItem` on the base table |
| List a customer's orders, newest first | `Query` on `customer-index` |

Both use keys - no `Scan` anywhere, so cost and latency stay flat as the table grows.

The pipeline writes with `attribute_not_exists(order_id)`, so processing the same order twice is harmless
(SQS guarantees *at-least-once* delivery, not exactly-once).

Screenshot: `screenshots/02-dynamodb-table-and-gsi.png`

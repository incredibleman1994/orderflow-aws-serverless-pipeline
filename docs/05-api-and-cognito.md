# Step 5 - Secure REST API (API Gateway + Cognito + Lambda)

## 5.1 Lambda: orders-api
Lambda -> Create function: `orders-api`, Python 3.12, arm64, role `orders-api-role`.
Paste `src/orders_api/lambda_function.py`, Deploy.
Environment variables: `TABLE_NAME=orders`, `INDEX_NAME=customer-index`. Timeout 10 s, memory 128 MB.

## 5.2 Cognito user pool
Cognito -> Create user pool

| Setting | Value |
|---|---|
| Application type | Single-page application (no client secret) |
| Name | `orders-users` |
| Sign-in identifiers | Email |
| Self-registration | Disabled (admin-created users only) |
| MFA | Optional/off for the lab (use it in production) |

After creating, open the **App client** -> Edit -> Authentication flows -> enable
**`ALLOW_USER_PASSWORD_AUTH`** (so we can fetch tokens from the command line).
Note the **User pool ID** and **Client ID**.

## 5.3 HTTP API
API Gateway -> **HTTP API** -> Build

1. Integration: Lambda -> `orders-api`, API name `orders-api`
2. Routes:
   - `GET /orders`
   - `GET /orders/{order_id}`
3. Stage: `$default` with auto-deploy

### JWT authorizer
API -> Authorization -> Create authorizer: type **JWT**, name `cognito-jwt`

| Setting | Value |
|---|---|
| Identity source | `$request.header.Authorization` |
| Issuer URL | `https://cognito-idp.ap-south-1.amazonaws.com/<USER_POOL_ID>` |
| Audience | `<APP_CLIENT_ID>` |

Attach the authorizer to **both** routes. (Use the Cognito **ID token** - its `aud` claim equals the client ID.)

### Throttling
API -> Stages -> `$default` -> Edit -> default route throttling: **rate 10 req/s, burst 20**.

Note the **Invoke URL**, e.g. `https://abc123.execute-api.ap-south-1.amazonaws.com`.

## 5.4 Create a test user and call the API (AWS CloudShell)
```bash
POOL=<USER_POOL_ID>; CLIENT=<APP_CLIENT_ID>; API=<INVOKE_URL>

aws cognito-idp admin-create-user --user-pool-id $POOL --username tester@example.com --message-action SUPPRESS
aws cognito-idp admin-set-user-password --user-pool-id $POOL --username tester@example.com \
  --password 'Use-A-Strong-P@ssw0rd-1' --permanent

TOKEN=$(aws cognito-idp initiate-auth --auth-flow USER_PASSWORD_AUTH --client-id $CLIENT \
  --auth-parameters USERNAME=tester@example.com,PASSWORD='Use-A-Strong-P@ssw0rd-1' \
  --query 'AuthenticationResult.IdToken' --output text)

curl -s -H "Authorization: Bearer $TOKEN" "$API/orders/ORD-1001"
curl -s -H "Authorization: Bearer $TOKEN" "$API/orders?customer=Asha%20Traders&limit=1"
curl -s -o /dev/null -w "%{http_code}\n" "$API/orders/ORD-1001"     # no token -> 401
```

## Response shape
```json
{ "order_id": "ORD-1001", "customer": "Asha Traders", "product": "USB-C Cable",
  "quantity": 10, "unit_price": "4.99", "total": "49.90",
  "source_file": "incoming/orders_valid.csv", "ingested_at": "2026-11-05T10:12:44.120+00:00" }
```
Listing returns `{ "count": n, "items": [...], "next_token": "..." }` - pass `next_token` back to get the next page.

Screenshots: `screenshots/05-api-routes-authorizer.png`, `screenshots/05-api-401-vs-200.png`

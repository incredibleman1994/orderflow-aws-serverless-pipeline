"""
orders-api  (API Gateway HTTP API -> Lambda -> DynamoDB)

Routes (payload format 2.0, protected by a Cognito JWT authorizer):
  GET /orders/{order_id}
  GET /orders?customer=<name>[&limit=1..100][&next_token=...]

Environment variables: TABLE_NAME (required), INDEX_NAME (default customer-index)
"""
import base64
import json
import logging
import os
import re
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

TABLE_NAME = os.environ["TABLE_NAME"]
INDEX_NAME = os.environ.get("INDEX_NAME", "customer-index")
table = boto3.resource("dynamodb").Table(TABLE_NAME)

ORDER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MONEY_FIELDS = {"unit_price", "total"}
TOKEN_KEYS = {"order_id", "customer", "ingested_at"}


def respond(status: int, body: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def serialize(item: dict) -> dict:
    out = {}
    for key, value in item.items():
        if isinstance(value, Decimal):
            out[key] = format(value, ".2f") if key in MONEY_FIELDS else int(value)
        else:
            out[key] = value
    return out


def get_order(order_id: str) -> dict:
    if not ORDER_ID_RE.match(order_id or ""):
        return respond(400, {"error": "invalid order_id"})
    item = table.get_item(Key={"order_id": order_id}).get("Item")
    if not item:
        return respond(404, {"error": "order not found"})
    return respond(200, serialize(item))


def list_orders(params: dict) -> dict:
    customer = (params.get("customer") or "").strip()
    if not customer:
        return respond(400, {"error": "query parameter 'customer' is required"})

    try:
        limit = int(params.get("limit", 25))
    except ValueError:
        return respond(400, {"error": "limit must be a number"})
    limit = max(1, min(limit, 100))

    query = {
        "IndexName": INDEX_NAME,
        "KeyConditionExpression": Key("customer").eq(customer),
        "ScanIndexForward": False,  # newest first
        "Limit": limit,
    }
    token = params.get("next_token")
    if token:
        try:
            start_key = json.loads(base64.urlsafe_b64decode(token.encode()))
            if not isinstance(start_key, dict) or set(start_key) != TOKEN_KEYS:
                raise ValueError
        except Exception:
            return respond(400, {"error": "invalid next_token"})
        query["ExclusiveStartKey"] = start_key

    result = table.query(**query)
    body = {"count": len(result["Items"]), "items": [serialize(i) for i in result["Items"]]}
    if "LastEvaluatedKey" in result:
        body["next_token"] = base64.urlsafe_b64encode(
            json.dumps(result["LastEvaluatedKey"]).encode()
        ).decode()
    return respond(200, body)


def lambda_handler(event, context):
    route = event.get("routeKey", "")
    try:
        if route == "GET /orders/{order_id}":
            return get_order((event.get("pathParameters") or {}).get("order_id", ""))
        if route == "GET /orders":
            return list_orders(event.get("queryStringParameters") or {})
        return respond(404, {"error": "route not found"})
    except ClientError:
        logger.exception("DynamoDB call failed")
        return respond(500, {"error": "internal error"})

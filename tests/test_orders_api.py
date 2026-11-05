import base64
import json
from decimal import Decimal

import boto3
import pytest

from conftest import load


@pytest.fixture
def api(aws):
    module = load("orders_api", "src/orders_api/lambda_function.py")
    table = boto3.resource("dynamodb", region_name="ap-south-1").Table("orders")
    for i in range(1, 6):
        table.put_item(Item={
            "order_id": f"ORD-{i}", "customer": "Asha Traders", "product": "Cable",
            "quantity": i, "unit_price": Decimal("4.50"), "total": Decimal("4.50") * i,
            "source_file": "incoming/x.csv", "ingested_at": f"2026-11-05T10:00:0{i}+00:00",
        })
    table.put_item(Item={
        "order_id": "ORD-99", "customer": "Other Co", "product": "Mouse", "quantity": 1,
        "unit_price": Decimal("10.00"), "total": Decimal("10.00"),
        "source_file": "incoming/y.csv", "ingested_at": "2026-11-05T11:00:00+00:00",
    })
    return module


def call(api, route, path=None, qs=None):
    event = {"routeKey": route, "pathParameters": path, "queryStringParameters": qs}
    resp = api.lambda_handler(event, None)
    return resp["statusCode"], json.loads(resp["body"])


def test_get_order_returns_formatted_money(api):
    status, body = call(api, "GET /orders/{order_id}", {"order_id": "ORD-2"})
    assert status == 200
    assert body["unit_price"] == "4.50" and body["total"] == "9.00" and body["quantity"] == 2


def test_get_unknown_order_is_404(api):
    assert call(api, "GET /orders/{order_id}", {"order_id": "NOPE"})[0] == 404


def test_get_order_with_bad_id_is_400(api):
    assert call(api, "GET /orders/{order_id}", {"order_id": "bad id!"})[0] == 400


def test_list_requires_customer(api):
    assert call(api, "GET /orders")[0] == 400


def test_list_by_customer_newest_first(api):
    status, body = call(api, "GET /orders", qs={"customer": "Asha Traders"})
    assert status == 200 and body["count"] == 5
    assert [i["order_id"] for i in body["items"]][0] == "ORD-5"
    assert all(i["customer"] == "Asha Traders" for i in body["items"])


def test_pagination_round_trip(api):
    status, page1 = call(api, "GET /orders", qs={"customer": "Asha Traders", "limit": "2"})
    assert page1["count"] == 2 and "next_token" in page1
    _, page2 = call(api, "GET /orders", qs={"customer": "Asha Traders", "limit": "2", "next_token": page1["next_token"]})
    ids = [i["order_id"] for i in page1["items"] + page2["items"]]
    assert len(set(ids)) == 4  # no overlap between pages


def test_tampered_token_is_rejected(api):
    evil = base64.urlsafe_b64encode(json.dumps({"order_id": "x", "extra": "y"}).encode()).decode()
    assert call(api, "GET /orders", qs={"customer": "Asha Traders", "next_token": evil})[0] == 400
    assert call(api, "GET /orders", qs={"customer": "Asha Traders", "next_token": "%%%"})[0] == 400


def test_unknown_route_is_404(api):
    assert call(api, "DELETE /orders")[0] == 404

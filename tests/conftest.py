import importlib.util
import json
import os
import pathlib

import boto3
import pytest
from moto import mock_aws

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUCKET = "test-orders-bucket"


def load(module_name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(module_name, ROOT / rel_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def aws(monkeypatch):
    for k, v in {
        "AWS_ACCESS_KEY_ID": "test", "AWS_SECRET_ACCESS_KEY": "test",
        "AWS_DEFAULT_REGION": "ap-south-1", "TABLE_NAME": "orders",
        "INDEX_NAME": "customer-index",
    }.items():
        monkeypatch.setenv(k, v)

    with mock_aws():
        region = "ap-south-1"
        s3 = boto3.client("s3", region_name=region)
        s3.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": region})

        ddb = boto3.client("dynamodb", region_name=region)
        ddb.create_table(
            TableName="orders",
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "order_id", "AttributeType": "S"},
                {"AttributeName": "customer", "AttributeType": "S"},
                {"AttributeName": "ingested_at", "AttributeType": "S"},
            ],
            KeySchema=[{"AttributeName": "order_id", "KeyType": "HASH"}],
            GlobalSecondaryIndexes=[{
                "IndexName": "customer-index",
                "KeySchema": [
                    {"AttributeName": "customer", "KeyType": "HASH"},
                    {"AttributeName": "ingested_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }],
        )
        topic_arn = boto3.client("sns", region_name=region).create_topic(Name="pipeline-notifications")["TopicArn"]
        monkeypatch.setenv("TOPIC_ARN", topic_arn)
        yield {"s3": s3, "bucket": BUCKET}


def sqs_event(key: str, message_id: str = "m-1", bucket: str = BUCKET) -> dict:
    s3_event = {"Records": [{"s3": {"bucket": {"name": bucket}, "object": {"key": key}}}]}
    return {"Records": [{"messageId": message_id, "body": json.dumps(s3_event)}]}

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import boto3
import pytest
from moto import mock_aws

from core.models import URLMapping
from core.repository import DynamoDBRepository

URLS_TABLE = "test-urls"
COUNTER_TABLE = "test-counter"


@pytest.fixture
def dynamo_repo():
    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        client.create_table(
            TableName=URLS_TABLE,
            AttributeDefinitions=[{"AttributeName": "short_key", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "short_key", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )
        client.create_table(
            TableName=COUNTER_TABLE,
            AttributeDefinitions=[{"AttributeName": "counter_name", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "counter_name", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield DynamoDBRepository(URLS_TABLE, COUNTER_TABLE, region="us-east-1")


def test_save_and_get(dynamo_repo):
    mapping = URLMapping(short_key="abc1234", long_url="https://example.com", created_at=1.0)
    assert dynamo_repo.save_if_absent(mapping) is True
    fetched = dynamo_repo.get("abc1234")
    assert fetched.long_url == "https://example.com"
    assert fetched.click_count == 0


def test_save_if_absent_returns_false_on_collision(dynamo_repo):
    mapping = URLMapping(short_key="dupe123", long_url="https://a.com", created_at=1.0)
    assert dynamo_repo.save_if_absent(mapping) is True
    collided = URLMapping(short_key="dupe123", long_url="https://b.com", created_at=2.0)
    assert dynamo_repo.save_if_absent(collided) is False
    # Original mapping must be untouched.
    assert dynamo_repo.get("dupe123").long_url == "https://a.com"


def test_increment_click_count(dynamo_repo):
    mapping = URLMapping(short_key="clk0001", long_url="https://example.com", created_at=1.0)
    dynamo_repo.save_if_absent(mapping)
    dynamo_repo.increment_click_count("clk0001")
    dynamo_repo.increment_click_count("clk0001")
    assert dynamo_repo.get("clk0001").click_count == 2


def test_counter_increments_atomically(dynamo_repo):
    assert dynamo_repo.next_counter_value() == 1
    assert dynamo_repo.next_counter_value() == 2
    assert dynamo_repo.next_counter_value() == 3


def test_get_missing_key_returns_none(dynamo_repo):
    assert dynamo_repo.get("nope") is None

"""
Storage layer. StorageRepository is an abstract interface (dependency
inversion) so the service layer never talks to boto3 directly, and so tests
can substitute an in-memory fake instead of hitting real DynamoDB.
"""
from abc import ABC, abstractmethod
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from .models import URLMapping


class StorageRepository(ABC):
    @abstractmethod
    def save_if_absent(self, mapping: URLMapping) -> bool:
        """Atomically insert `mapping` only if its key doesn't already
        exist. Returns True on success, False if the key was taken
        (a collision) so the caller can retry with a new key."""
        raise NotImplementedError

    @abstractmethod
    def get(self, short_key: str) -> Optional[URLMapping]:
        raise NotImplementedError

    @abstractmethod
    def increment_click_count(self, short_key: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def next_counter_value(self) -> int:
        raise NotImplementedError


class DynamoDBRepository(StorageRepository):
    def __init__(self, table_name: str, counter_table_name: str = "", region: Optional[str] = None):
        resource = boto3.resource("dynamodb", region_name=region)
        self.table = resource.Table(table_name)
        self.counter_table = resource.Table(counter_table_name) if counter_table_name else None

    def save_if_absent(self, mapping: URLMapping) -> bool:
        try:
            self.table.put_item(
                Item={
                    "short_key": mapping.short_key,
                    "long_url": mapping.long_url,
                    "created_at": str(mapping.created_at),
                    "click_count": 0,
                },
                # This ConditionExpression is what makes the "detect and
                # retry on collision" strategy safe under concurrent writes
                # from multiple Lambda invocations -- DynamoDB rejects the
                # write atomically instead of us doing a racy read-then-write.
                ConditionExpression="attribute_not_exists(short_key)",
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False
            raise

    def get(self, short_key: str) -> Optional[URLMapping]:
        response = self.table.get_item(Key={"short_key": short_key})
        item = response.get("Item")
        if not item:
            return None
        return URLMapping(
            short_key=item["short_key"],
            long_url=item["long_url"],
            created_at=float(item["created_at"]),
            click_count=int(item.get("click_count", 0)),
        )

    def increment_click_count(self, short_key: str) -> None:
        self.table.update_item(
            Key={"short_key": short_key},
            UpdateExpression="ADD click_count :inc",
            ExpressionAttributeValues={":inc": 1},
        )

    def next_counter_value(self) -> int:
        if self.counter_table is None:
            raise RuntimeError("No counter table configured")
        response = self.counter_table.update_item(
            Key={"counter_name": "short_url_id"},
            UpdateExpression="ADD current_value :inc",
            ExpressionAttributeValues={":inc": 1},
            ReturnValues="UPDATED_NEW",
        )
        return int(response["Attributes"]["current_value"])

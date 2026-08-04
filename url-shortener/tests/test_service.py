import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from core.exceptions import InvalidURLError, KeyGenerationExhaustedError, URLNotFoundError
from core.hashing import KeyGenerationStrategy
from core.models import URLMapping
from core.repository import StorageRepository
from core.service import URLShortenerService


class FakeRepository(StorageRepository):
    """In-memory double -- lets us test collision handling deterministically
    without touching DynamoDB or mocking boto3."""

    def __init__(self):
        self.store = {}
        self.counter = 0

    def save_if_absent(self, mapping: URLMapping) -> bool:
        if mapping.short_key in self.store:
            return False
        self.store[mapping.short_key] = mapping
        return True

    def get(self, short_key: str):
        return self.store.get(short_key)

    def increment_click_count(self, short_key: str) -> None:
        if short_key in self.store:
            self.store[short_key].click_count += 1

    def next_counter_value(self) -> int:
        self.counter += 1
        return self.counter


class AlwaysCollideStrategy(KeyGenerationStrategy):
    """Deliberately returns the same key every time, to prove the service
    gives up after MAX_COLLISION_RETRIES instead of looping forever."""

    def generate(self, long_url: str, attempt: int = 0) -> str:
        return "samekey"


class SequentialStrategy(KeyGenerationStrategy):
    def generate(self, long_url: str, attempt: int = 0) -> str:
        return f"key{attempt}"


@pytest.fixture
def repo():
    return FakeRepository()


def test_shorten_and_resolve_roundtrip(repo):
    service = URLShortenerService(repo, SequentialStrategy(), base_domain="https://short.ly")
    short_url = service.shorten("https://example.com/some/long/path")
    key = short_url.split("/")[-1]
    assert service.resolve(key) == "https://example.com/some/long/path"


def test_rejects_invalid_url(repo):
    service = URLShortenerService(repo, SequentialStrategy(), base_domain="https://short.ly")
    with pytest.raises(InvalidURLError):
        service.shorten("not-a-url")


def test_resolve_missing_key_raises(repo):
    service = URLShortenerService(repo, SequentialStrategy(), base_domain="https://short.ly")
    with pytest.raises(URLNotFoundError):
        service.resolve("doesnotexist")


def test_click_count_increments_on_resolve(repo):
    service = URLShortenerService(repo, SequentialStrategy(), base_domain="https://short.ly")
    short_url = service.shorten("https://example.com/x")
    key = short_url.split("/")[-1]
    service.resolve(key)
    service.resolve(key)
    assert service.stats(key).click_count == 2


def test_collision_exhaustion_raises(repo):
    # Pre-seed the one key the strategy will ever produce, so every
    # save_if_absent() call fails -- forcing the retry loop to exhaust.
    repo.store["samekey"] = URLMapping(short_key="samekey", long_url="https://taken.com", created_at=0)
    service = URLShortenerService(repo, AlwaysCollideStrategy(), base_domain="https://short.ly")
    with pytest.raises(KeyGenerationExhaustedError):
        service.shorten("https://example.com/new")


def test_collision_retry_succeeds_on_second_attempt(repo):
    # First key ("key0") is taken; SequentialStrategy salts by attempt,
    # so the service should fall through to "key1" and succeed.
    repo.store["key0"] = URLMapping(short_key="key0", long_url="https://other.com", created_at=0)
    service = URLShortenerService(repo, SequentialStrategy(), base_domain="https://short.ly")
    short_url = service.shorten("https://example.com/new")
    assert short_url.endswith("key1")

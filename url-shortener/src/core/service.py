from urllib.parse import urlparse

from .exceptions import InvalidURLError, KeyGenerationExhaustedError, URLNotFoundError
from .hashing import KeyGenerationStrategy
from .models import URLMapping
from .repository import StorageRepository

MAX_COLLISION_RETRIES = 5


class URLShortenerService:
    """Business logic, decoupled from AWS. Depends only on the two
    abstractions (StorageRepository, KeyGenerationStrategy) via
    constructor injection -- swap either one out (e.g. for tests, or to
    switch hash-based -> counter-based key generation) without touching
    this class."""

    def __init__(self, repository: StorageRepository, strategy: KeyGenerationStrategy, base_domain: str):
        self.repository = repository
        self.strategy = strategy
        self.base_domain = base_domain.rstrip("/")

    @staticmethod
    def _validate(long_url: str) -> None:
        parsed = urlparse(long_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise InvalidURLError(f"'{long_url}' is not a valid absolute URL")

    def shorten(self, long_url: str) -> str:
        self._validate(long_url)
        for attempt in range(MAX_COLLISION_RETRIES):
            short_key = self.strategy.generate(long_url, attempt)
            mapping = URLMapping(short_key=short_key, long_url=long_url, created_at=URLMapping.now())
            if self.repository.save_if_absent(mapping):
                return f"{self.base_domain}/{short_key}"
            # Collision: another URL already owns this key. Loop again;
            # the strategy will salt with the next `attempt` value.
        raise KeyGenerationExhaustedError(
            f"Could not generate a unique key after {MAX_COLLISION_RETRIES} attempts"
        )

    def resolve(self, short_key: str) -> str:
        mapping = self.repository.get(short_key)
        if mapping is None:
            raise URLNotFoundError(f"No URL found for key '{short_key}'")
        self.repository.increment_click_count(short_key)
        return mapping.long_url

    def stats(self, short_key: str) -> URLMapping:
        mapping = self.repository.get(short_key)
        if mapping is None:
            raise URLNotFoundError(f"No URL found for key '{short_key}'")
        return mapping

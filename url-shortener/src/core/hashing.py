"""
Key generation for short URLs.

Two interchangeable strategies (Strategy pattern), so the interviewer-facing
design decision -- "hash-based vs counter-based, and why" -- is explicit in
code rather than hidden in a single hard-coded function.

1. HashBasedStrategy
   - Deterministic-ish: MD5(long_url + attempt) -> take N bits -> base62 encode.
   - O(1) to generate, no shared counter/coordination needed (good for a
     distributed, multi-region write path).
   - Not guaranteed unique -> caller must detect collisions (via a
     conditional DynamoDB write) and retry with a bumped `attempt` salt.
   - This is the "real" system-design tradeoff: we trade a small, bounded
     retry probability for full decentralization.

2. CounterBasedStrategy
   - A monotonically increasing integer (from a DynamoDB atomic counter)
     base62-encoded. Guarantees uniqueness by construction, so no collision
     retries are ever needed.
   - Trade-off: the counter is a single logical point of coordination
     (though DynamoDB atomic increments scale fine in practice up to very
     high throughput, it's still a centralized sequence).

Both are provided so the design can be discussed and swapped at the
composition root (see handlers/*.py) without touching business logic.
"""
import hashlib
import string
from abc import ABC, abstractmethod
from typing import Callable

BASE62_ALPHABET = string.digits + string.ascii_lowercase + string.ascii_uppercase
BASE = 62


def base62_encode(num: int) -> str:
    """Encode a non-negative integer as a base62 string. O(log62 n)."""
    if num < 0:
        raise ValueError("base62_encode requires a non-negative integer")
    if num == 0:
        return BASE62_ALPHABET[0]
    digits = []
    while num:
        num, remainder = divmod(num, BASE)
        digits.append(BASE62_ALPHABET[remainder])
    return "".join(reversed(digits))


def base62_decode(encoded: str) -> int:
    """Inverse of base62_encode. O(len(encoded))."""
    num = 0
    for char in encoded:
        num = num * BASE + BASE62_ALPHABET.index(char)
    return num


class KeyGenerationStrategy(ABC):
    @abstractmethod
    def generate(self, long_url: str, attempt: int = 0) -> str:
        """Return a candidate short key. `attempt` is a salt used for
        retrying after a collision."""
        raise NotImplementedError


class HashBasedStrategy(KeyGenerationStrategy):
    def __init__(self, key_length: int = 7):
        if key_length < 4:
            raise ValueError("key_length too small; collision risk too high")
        self.key_length = key_length

    def generate(self, long_url: str, attempt: int = 0) -> str:
        salted = f"{long_url}:{attempt}".encode("utf-8")
        digest = hashlib.md5(salted).hexdigest()
        # Take 48 bits (12 hex chars) of the digest as our integer space.
        num = int(digest[:12], 16)
        encoded = base62_encode(num)
        # Pad/truncate to a fixed, predictable key length.
        if len(encoded) < self.key_length:
            encoded = encoded.rjust(self.key_length, BASE62_ALPHABET[0])
        return encoded[: self.key_length]


class CounterBasedStrategy(KeyGenerationStrategy):
    def __init__(self, counter_provider: Callable[[], int]):
        # counter_provider is injected so this class has no AWS dependency
        # and is trivially unit-testable with a fake counter.
        self.counter_provider = counter_provider

    def generate(self, long_url: str, attempt: int = 0) -> str:
        next_id = self.counter_provider()
        return base62_encode(next_id)

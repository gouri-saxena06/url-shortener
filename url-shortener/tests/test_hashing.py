import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.hashing import base62_encode, base62_decode, HashBasedStrategy, CounterBasedStrategy


def test_base62_roundtrip():
    for n in [0, 1, 61, 62, 3843, 999999, 2**40]:
        assert base62_decode(base62_encode(n)) == n


def test_base62_is_alphanumeric():
    encoded = base62_encode(123456789)
    assert encoded.isalnum()


def test_hash_strategy_deterministic_for_same_attempt():
    strategy = HashBasedStrategy(key_length=7)
    key1 = strategy.generate("https://example.com/page", attempt=0)
    key2 = strategy.generate("https://example.com/page", attempt=0)
    assert key1 == key2
    assert len(key1) == 7


def test_hash_strategy_changes_with_attempt_salt():
    strategy = HashBasedStrategy(key_length=7)
    keys = {strategy.generate("https://example.com/page", attempt=i) for i in range(5)}
    # Salting with attempt should (overwhelmingly likely) produce distinct
    # keys, which is exactly what the collision-retry loop relies on.
    assert len(keys) == 5


def test_hash_strategy_different_urls_different_keys():
    strategy = HashBasedStrategy(key_length=7)
    a = strategy.generate("https://example.com/a", attempt=0)
    b = strategy.generate("https://example.com/b", attempt=0)
    assert a != b


def test_counter_strategy_uses_injected_provider():
    calls = iter([1, 2, 3])
    strategy = CounterBasedStrategy(counter_provider=lambda: next(calls))
    assert strategy.generate("any-url") == base62_encode(1)
    assert strategy.generate("any-url") == base62_encode(2)
    assert strategy.generate("any-url") == base62_encode(3)

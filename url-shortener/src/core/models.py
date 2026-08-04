"""Domain model for the URL shortener."""
import time
from dataclasses import dataclass


@dataclass
class URLMapping:
    short_key: str
    long_url: str
    created_at: float
    click_count: int = 0

    @staticmethod
    def now() -> float:
        return time.time()

class URLShortenerError(Exception):
    """Base class for all domain errors."""


class InvalidURLError(URLShortenerError):
    """Raised when the input is not a valid absolute URL."""


class URLNotFoundError(URLShortenerError):
    """Raised when a short key has no mapping."""


class KeyGenerationExhaustedError(URLShortenerError):
    """Raised when we can't find a free key after max retries."""

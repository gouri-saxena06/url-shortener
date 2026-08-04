import json
import os

from core.exceptions import InvalidURLError, KeyGenerationExhaustedError
from core.hashing import HashBasedStrategy
from core.repository import DynamoDBRepository
from core.service import URLShortenerService
from utils.response import build_response

# Built once per warm Lambda container (not per invocation) -- this is the
# composition root. To switch to counter-based keys, swap the strategy line
# for `CounterBasedStrategy(repository.next_counter_value)`.
_repository = DynamoDBRepository(
    table_name=os.environ["URLS_TABLE"],
    counter_table_name=os.environ.get("COUNTER_TABLE", ""),
)
_strategy = HashBasedStrategy(key_length=int(os.environ.get("KEY_LENGTH", "7")))
_service = URLShortenerService(_repository, _strategy, base_domain=os.environ["BASE_DOMAIN"])


def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return build_response(400, {"error": "Request body must be valid JSON"})

    long_url = body.get("url")
    if not long_url:
        return build_response(400, {"error": "Missing 'url' field in request body"})

    try:
        short_url = _service.shorten(long_url)
        return build_response(201, {"short_url": short_url, "original_url": long_url})
    except InvalidURLError as e:
        return build_response(400, {"error": str(e)})
    except KeyGenerationExhaustedError as e:
        return build_response(503, {"error": str(e)})
    except Exception:
        return build_response(500, {"error": "Internal server error"})

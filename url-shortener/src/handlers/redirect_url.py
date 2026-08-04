import os

from core.exceptions import URLNotFoundError
from core.hashing import HashBasedStrategy
from core.repository import DynamoDBRepository
from core.service import URLShortenerService
from utils.response import build_response

_repository = DynamoDBRepository(
    table_name=os.environ["URLS_TABLE"],
    counter_table_name=os.environ.get("COUNTER_TABLE", ""),
)
_strategy = HashBasedStrategy(key_length=int(os.environ.get("KEY_LENGTH", "7")))
_service = URLShortenerService(_repository, _strategy, base_domain=os.environ["BASE_DOMAIN"])


def handler(event, context):
    short_key = (event.get("pathParameters") or {}).get("shortKey")
    if not short_key:
        return build_response(400, {"error": "Missing short key in path"})

    try:
        long_url = _service.resolve(short_key)
        return {
            "statusCode": 301,
            "headers": {"Location": long_url, "Cache-Control": "no-cache"},
            "body": "",
        }
    except URLNotFoundError:
        return build_response(404, {"error": "Short URL not found"})
    except Exception:
        return build_response(500, {"error": "Internal server error"})

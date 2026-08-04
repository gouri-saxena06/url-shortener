# Distributed URL Shortener (AWS Lambda + DynamoDB + API Gateway)

A serverless URL shortener built to be **discussed in an interview**, not
just to work. The architecture, algorithm choices, and code structure are
deliberately explicit so every decision has a one-line justification you can
defend on a whiteboard.

## Architecture

```
Client
  │
  ▼
API Gateway (REST API)
  │
  ├── POST /shorten          → CreateUrlFunction (Lambda)
  ├── GET  /{shortKey}        → RedirectFunction (Lambda)   → 301 redirect
  └── GET  /{shortKey}/stats  → StatsFunction (Lambda)
                                       │
                                       ▼
                              DynamoDB (url-shortener-urls)
                              DynamoDB (url-shortener-counter)
```

- **API Gateway** — front door, request validation, throttling, auth hook if
  you want to add API keys/Cognito later.
- **Lambda (3 functions)** — stateless compute, one per operation, scales
  independently and to zero.
- **DynamoDB** — single-digit-ms key-value lookups at any scale;
  `PAY_PER_REQUEST` billing so it scales with traffic, not provisioning.
- **Two tables**: `urls` (short_key → long_url + click_count) and `counter`
  (a single atomic-increment row, only used by the counter-based key
  strategy — see below).

## The actual algorithm (not just CRUD)

`src/core/hashing.py` implements **two interchangeable key-generation
strategies** behind a `KeyGenerationStrategy` interface (Strategy pattern),
because "how do you generate the short key" is the real system-design
question here, and there's a genuine tradeoff:

| Strategy | How | Uniqueness | Coordination |
|---|---|---|---|
| `HashBasedStrategy` (default) | MD5(url + attempt-salt) → 48 bits → base62, fixed length | Not guaranteed — collisions are possible | None — fully decentralized, any Lambda can generate a key with zero shared state |
| `CounterBasedStrategy` | DynamoDB atomic counter → base62 | Guaranteed by construction | One shared sequence (single logical bottleneck, though DynamoDB atomic increments scale very high in practice) |

**Collision handling** (the part that makes this "real" and not a toy hash
function): a `save_if_absent()` write uses a DynamoDB
`ConditionExpression: attribute_not_exists(short_key)`. This is an atomic
compare-and-swap at the database layer — not a racy "read, check, then
write" in application code, which would be broken under concurrent Lambda
invocations. If the conditional write fails, `URLShortenerService.shorten()`
retries with a bumped salt (`attempt`) up to `MAX_COLLISION_RETRIES` times,
then raises `KeyGenerationExhaustedError`.

`base62_encode`/`base62_decode` are hand-rolled (`O(log₆₂ n)` encode, `O(n)`
decode) rather than pulled from a library, since implementing them correctly
(alphabet choice, zero-handling, no left-padding ambiguity) is itself a
common interview ask.

## OOP design

- **`URLMapping`** (`core/models.py`) — plain data class, no behavior.
- **`KeyGenerationStrategy`** (`core/hashing.py`) — abstract strategy;
  `HashBasedStrategy` / `CounterBasedStrategy` are concrete implementations.
- **`StorageRepository`** (`core/repository.py`) — abstract repository;
  `DynamoDBRepository` is the concrete AWS implementation. Business logic
  never imports boto3.
- **`URLShortenerService`** (`core/service.py`) — orchestrates validation +
  key generation + storage, depends only on the two abstractions above
  (constructor injection). This is what makes `tests/test_service.py` able
  to test collision-retry logic with an in-memory fake and zero AWS calls.
- **Lambda handlers** (`handlers/*.py`) — thin adapters: parse the API
  Gateway event, call the service, format the HTTP response. This is the
  composition root where concrete implementations get wired together — the
  only place you'd touch to swap `HashBasedStrategy` for
  `CounterBasedStrategy`.

## API

**Create a short URL**
```
POST /shorten
Content-Type: application/json

{ "url": "https://example.com/some/very/long/path" }
```
```
201 Created
{ "short_url": "https://short.ly/aZ3kQ9x", "original_url": "https://example.com/..." }
```

**Follow a short URL**
```
GET /{shortKey}   →  301 Location: <original long URL>
```

**Get click stats**
```
GET /{shortKey}/stats
→ { "short_key": "...", "long_url": "...", "created_at": ..., "click_count": 3 }
```

## Deploying

Requires the [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html) and AWS credentials configured.

```bash
sam build
sam deploy --guided
```

After the first deploy, copy the `ApiInvokeUrl` output and set it as the
`BASE_DOMAIN` environment variable on the three functions (or edit
`template.yaml`'s `Globals.Function.Environment.Variables.BASE_DOMAIN` and
redeploy) so generated short URLs point at your real API Gateway domain.

```bash
curl -X POST https://<api-id>.execute-api.<region>.amazonaws.com/prod/shorten \
  -H 'Content-Type: application/json' \
  -d '{"url": "https://aws.amazon.com/lambda/"}'
```

## Running tests locally (no AWS needed)

```bash
pip install -r requirements.txt
pytest tests/ -v
```

17 tests cover: base62 round-tripping, both key-generation strategies,
collision-retry and exhaustion behavior in the service layer (via an
in-memory fake repository), and the DynamoDB repository's conditional-write
semantics (via `moto`, a mocked DynamoDB — no real AWS account required to
run these).

## Talking points for an interview

- Why DynamoDB conditional writes instead of a distributed lock — cheaper,
  simpler, and DynamoDB already gives you the atomicity for free.
- Why hash+retry over a single global counter by default — no
  single-writer bottleneck, good for a multi-region write path — and why
  you might pick the counter anyway (shorter keys sooner, zero collision
  probability, simpler reasoning about capacity).
- How you'd extend this: custom aliases, expiring links (DynamoDB TTL),
  analytics via DynamoDB Streams → Kinesis, a CloudFront cache in front of
  the redirect endpoint to cut Lambda invocations for hot links.

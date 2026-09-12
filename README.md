# Shopping assistant

The first implementation slice ([ticket #1](https://github.com/egor000/shop-w/issues/1)) lets an anonymous shopper ask about one fictional product and return to its saved answer. Python/FastAPI serves the browser and public API; a separate Python worker processes PostgreSQL work records. The deterministic provider requires no GPU or model downloads.

## Run locally

```sh
docker compose up --build -d --wait
```

Open http://localhost:8091. PostgreSQL stays on the private Compose network and keeps data in the `postgres-data` volume. Port 8091 is bound to loopback. The supplied database credentials are for this local demo. For HTTPS deployments set `COOKIE_SECURE=true`; all API replicas must use the same database.

```sh
docker compose logs -f api worker
docker compose down
```

Ordinary `down` preserves stored conversations. `down -v` deletes them. The migration command (`python -m shop.migrate`) is versioned, transactional, and safe to repeat before starting either application process. Python dependencies, including transitive dependencies, are pinned in the requirements files.

## Public interface

- `POST /api/session`: create/reuse a persistent, HttpOnly anonymous cookie.
- `POST /api/conversations`: create a conversation belonging to that session.
- `POST /api/conversations/{id}/questions`: accept `{ "submission_id": "UUID", "text": "question" }` and return `202` only after both the question and work record commit. The browser generates and saves the UUID before sending.
- `GET /api/conversations/{id}`: recover all accepted questions, original acceptance/deadline timestamps, statuses and complete answers. Returns `404` for another session's conversation.
- `GET /products/trail-cup`: product facts and local product page.
- `GET /health`: database reachability; `/docs`: generated API documentation.

Identical retries return the original question, including its current state. Changed content with the same ID, or a second pending question, returns `409`. Invalid envelopes, blank questions, and questions exceeding 4,000 characters return `422`. The deadline is recorded as acceptance plus two minutes. The UI polls persisted state; it needs no sticky sessions and renders shopper/provider text as text, never HTML. The anonymous cookie lasts 30 days; its random secret is stored only as a hash in PostgreSQL.

Each acceptance transaction locks its conversation. Worker claims use PostgreSQL `FOR UPDATE SKIP LOCKED` and distinct attempt identifiers; inference runs outside the transaction. Completion commits the authoritative answer and removes work together. Logs contain request/attempt identifiers and statuses, without shopper questions or answers.

## Verify

Python 3.13 and Docker are required. Use a dedicated test database, never a production database. Tests create a uniquely named schema for each run and remove only that schema afterward.

```sh
python -m venv .venv
# Windows: .venv/Scripts/python.exe; Linux: .venv/bin/python
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
docker compose -f compose.test.yaml up -d --wait
.venv/Scripts/python.exe -m mypy
.venv/Scripts/python.exe -m pytest -q
```

`TEST_DATABASE_URL` overrides the default test database at `127.0.0.1:55439`. Tests launch real API and worker subprocesses, exercise HTTP only, and observe answers after API restarts. PostgreSQL is real; inference is deterministic and its delay is controlled with `DETERMINISTIC_DELAY_SECONDS`. Test setup uses SQL only to isolate the schema, not to assert behavior.

The browser checklist and recorded results are in [docs/browser-check.md](docs/browser-check.md).

## Remaining tickets

This slice records the two-minute deadline but does not yet enforce expiry. A worker crash after a claim leaves its question processing; renewable leases, recovery and fencing belong to [#2](https://github.com/egor000/shop-w/issues/2), and cancellation, expiry and retries to [#3](https://github.com/egor000/shop-w/issues/3). A provider exception is saved as a failed question; there is no automatic retry yet.

Qdrant ingestion, real local vLLM, semantic caching, overload protection, observability dashboards and Kubernetes are later [implementation tickets](https://github.com/egor000/shop-w/issues). The accepted design is in [.scratch/shop-assistant/spec.md](.scratch/shop-assistant/spec.md). Live catalog updates, database failover, shopper accounts and administrator permissions are outside v1.

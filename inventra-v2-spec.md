# Inventra v2 — Implementation Spec

**Target repo:** `tharunsridhar/Inventra` (Django branch)
**Goal:** Add caching, background jobs, throttling, structured logging, and load-test evidence to an existing, working Django 5 + DRF inventory API.
**Estimated scope:** 7 phases, ~2 weeks part-time.

---

## Instructions for the executing agent

Read this section before writing any code.

### Ground rules

1. **This is a brownfield repo. Inspect before you assume.** Every file path in this spec is derived from the project README, not from reading the code. Verify each path exists before editing. If the structure differs, adapt and note the difference in your commit message.
2. **The existing test suite must stay green.** There are ~15 tests including 2 real concurrency tests using `django_db(transaction=True)` + `live_server`. Run `uv run pytest -v` before you start and after every task. If a change breaks a test, fix the change, not the test.
3. **Do not weaken existing guarantees.** Specifically: the append-only ledger (no create/update/delete route, admin permissions hard-disabled), `select_for_update()` on every stock mutation with fixed id-sorted lock ordering, and the idempotent 409-on-replay contract for `/receive` and `/complete`. These are the most valuable things in the repo. If a task appears to require relaxing one, stop and flag it instead.
4. **One commit per task.** Message format: `phase-N: <task title>`. Do not batch unrelated changes.
5. **No public API contract changes** without flagging first. Existing endpoint paths, request bodies, and response shapes stay as they are. New endpoints and new response headers are fine.
6. **Dependency management is `uv`.** Use `uv add <pkg>`, not bare `pip install`. Keep the lockfile committed.
7. **Ask before guessing on anything ambiguous.** A question costs a minute; a wrong assumption costs a rewrite.

### Explicitly out of scope

- Upgrading Django or DRF versions
- Adding a frontend
- Refactoring existing views, models, or tests that this spec does not name
- Multi-warehouse, partial PO receiving, PO approval workflow, supplier returns, PDF generation beyond what Phase 4 specifies
- Renaming apps, models, or endpoints

### Known project facts

```
Stack        Django 5, DRF, PostgreSQL 16 (psycopg v3), simplejwt (+ token_blacklist),
             django-filter, whitenoise, pytest + pytest-django, Docker, GitHub Actions
Deps         uv (uv sync / uv run)
Apps         apps/accounts, apps/catalog, apps/inventory, apps/reports, apps/notifications
Config       config/settings/{base,development,production}.py, config/urls.py
Tests        tests/, tests/conftest.py, tests/test_concurrency.py
Infra        Dockerfile, docker-compose.yml, docker-entrypoint.sh, railway.json,
             .github/workflows/ci.yml
Endpoints    /health, /auth/*, /users, /categories, /suppliers, /products,
             /purchase-orders/{id}/receive, /sales-orders/{id}/complete,
             /returns/{id}/approve, /damage, /inventory-transactions,
             /dashboard, /reports/{products,purchases,sales,inventory}, /notifications
Roles        Admin / Manager / Employee
Not present  Redis, Celery, caching, throttling, structured logging, load tests
```

---

## Phase 0 — Recon and baseline

No feature work. Establish ground truth.

- [ ] **0.1 — Map the repo.** Read `config/settings/base.py`, `config/urls.py`, `apps/inventory/views.py`, `apps/reports/views.py`, `tests/conftest.py`, `tests/test_concurrency.py`, `docker-compose.yml`, `.github/workflows/ci.yml`. Write `docs/v2/CURRENT_STATE.md` recording: actual app/file layout, how settings are split and selected, how the two concurrency tests are wired, and what `docker compose up` currently starts.
- [ ] **0.2 — Verify the suite is green.** Run `uv run pytest -v`. Record the count and duration in `CURRENT_STATE.md`. If anything is already failing, stop and report before continuing.
- [ ] **0.3 — Record a query-count baseline.** For `/dashboard`, `/reports/inventory`, `/reports/sales`, and `/products` (list), record the number of SQL queries and response time with a realistically seeded dataset. Use `django-silk` in dev or `CaptureQueriesContext`. Put the table in `CURRENT_STATE.md`. **These are the numbers Phase 2 must improve, so they must exist before Phase 2 starts.**
- [ ] **0.4 — Add a seed command.** `python manage.py seed_demo --products 500 --orders 2000` creating deterministic data (fixed random seed) for benchmarking and load tests. Put it in `apps/catalog/management/commands/` or a new `apps/core/`. Must be idempotent or offer `--flush`.

**Acceptance:** `docs/v2/CURRENT_STATE.md` exists with layout notes, a green test count, and a baseline query/latency table. `seed_demo` runs clean twice in a row.

---

## Phase 1 — Redis infrastructure

Add Redis as a service and wire it as Django's cache backend. No behaviour change yet.

- [ ] **1.1 — Add Redis to `docker-compose.yml`.** `redis:7-alpine`, named volume, healthcheck (`redis-cli ping`). The `api` service gains `depends_on: redis: condition: service_healthy`.
- [ ] **1.2 — Add deps.** `uv add django-redis celery redis`.
- [ ] **1.3 — Configure the cache in `config/settings/base.py`.** `django.core.cache.backends.redis.RedisCache` or `django_redis.cache.RedisCache`, URL from `REDIS_URL` env var. Default `redis://localhost:6379/0`. Use **db 0 for cache, db 1 for Celery broker, db 2 for Celery results** — keep them separate so a `FLUSHDB` on the cache can't destroy the queue.
- [ ] **1.4 — Test settings must not share the dev cache.** In the test settings (or a pytest fixture), point the cache at a distinct Redis db or `LocMemCache`. Tests must never see cached data from a dev run.
- [ ] **1.5 — Extend `/health`.** It currently reports app + DB. Add a `redis` key. Response shape:
  ```json
  {"status": "ok", "checks": {"database": "ok", "redis": "ok", "celery": "ok"}}
  ```
  Return `503` if any check fails. Keep the existing top-level `status` key so Railway's healthcheck doesn't break. Celery check comes in Phase 4 — stub it as `"not_configured"` for now.
- [ ] **1.6 — Document env vars.** Add `REDIS_URL` (and later Celery vars) to `.env.example` with comments.

**Acceptance:** `docker compose up --build` starts postgres + redis + api. `GET /health` returns database and redis both `ok`. Full test suite still green.

---

## Phase 2 — Caching read-heavy endpoints

The reports and dashboard endpoints run aggregations on every request. Cache them and invalidate correctly on stock mutations.

- [ ] **2.1 — Design the cache key scheme.** Do **not** enumerate and delete individual keys on invalidation — it doesn't scale and it's easy to miss one. Use a **version counter**:
  ```
  key = f"reports:v{get_version('inventory')}:{endpoint}:{hash(query_params)}"
  ```
  `get_version()` reads an integer from Redis; invalidation is `cache.incr("version:inventory")`, which orphans all old keys at once and lets them expire naturally by TTL. Document this choice in `docs/v2/adr/0001-cache-invalidation.md`.
- [ ] **2.2 — Build the cache helper.** New module `apps/core/cache.py` (create `apps/core` if it doesn't exist) exposing `cached_response(namespace, ttl)` as a decorator or mixin usable on DRF views, plus `bump_version(namespace)`. Include the requesting user's role and id in the key where the response is role- or user-scoped. **A cache that leaks one user's data to another is worse than no cache — write the test for this first.**
- [ ] **2.3 — Apply caching.** To `/dashboard` and `/reports/{products,purchases,sales,inventory}`. TTL 300s. Do **not** cache `/inventory-transactions` (audit trail, must always be live) or any write endpoint.
- [ ] **2.4 — Wire invalidation.** Every stock-mutating path — `/receive`, `/complete`, `/returns/{id}/approve`, `/damage` — calls `bump_version("inventory")`. Critical: dispatch it inside `transaction.on_commit(...)`, never inline. If the transaction rolls back, the cache must not have been invalidated on the basis of a change that never happened.
- [ ] **2.5 — Add a cache-status response header.** `X-Cache: HIT` or `MISS` on cached endpoints. Makes the behaviour visible in the browsable API and in the load test output.
- [ ] **2.6 — Tests.** In `tests/test_caching.py`:
  - Second identical request hits cache (assert via `assertNumQueries` dropping to near zero, and `X-Cache: HIT`).
  - A `/complete` call invalidates: the next report request is a MISS and reflects the new stock.
  - **Isolation:** user A's cached report is never served to user B, and an Employee never receives an Admin-scoped cached response.
  - A rolled-back transaction does **not** invalidate the cache.
- [ ] **2.7 — Record the improvement.** Re-run the Phase 0.3 measurements. Add a before/after column to `CURRENT_STATE.md`.

**Acceptance:** Report endpoints measurably faster with query counts near zero on hit. All isolation tests pass. Stock mutations invalidate correctly, including under rollback.

---

## Phase 3 — Rate limiting

- [ ] **3.1 — Configure DRF throttling** in `config/settings/base.py`. `ScopedRateThrottle` plus `AnonRateThrottle`. Scopes and suggested rates (put them in settings, not hardcoded):
  | Scope | Rate | Applies to |
  |---|---|---|
  | `auth` | 10/min | `/auth/login`, `/auth/register` |
  | `read` | 200/min | list/retrieve endpoints |
  | `write` | 60/min | create/update endpoints |
  | `stock_mutation` | 20/min | `/receive`, `/complete`, `/returns/*/approve`, `/damage` |
  | `reports` | 30/min | dashboard + reports |
- [ ] **3.2 — Apply `throttle_scope`** to the relevant viewsets and `@action` methods.
- [ ] **3.3 — Return a proper 429.** Include a `Retry-After` header and the project's existing error body shape. Match whatever error format the repo already uses — check before inventing one.
- [ ] **3.4 — Exempt the health endpoint** and, if present, the Django Admin.
- [ ] **3.5 — Tests.** `tests/test_throttling.py`: exceeding a scope returns 429 with `Retry-After`; the counter is per-user, not global; `/health` is never throttled. Override rates to something small in the test settings so tests stay fast.

**Acceptance:** Throttles enforced per scope and per user. 429 responses carry `Retry-After`. Suite green.

---

## Phase 4 — Celery background jobs

- [ ] **4.1 — Add `config/celery.py`.** Standard Django Celery app with `app.config_from_object("django.conf:settings", namespace="CELERY")` and `autodiscover_tasks()`. Import it in `config/__init__.py`. Broker = Redis db 1, result backend = Redis db 2.
- [ ] **4.2 — Add worker and beat services** to `docker-compose.yml`. Both reuse the api image with different commands. Both `depends_on` redis and postgres.
- [ ] **4.3 — Task: async invoice generation.** `/sales-orders/{id}/invoice` currently returns synchronously — verify this, then change it to enqueue a task, return `202 Accepted` with a task id, and add `GET /tasks/{id}/` returning status and a result URL when ready. Generate a PDF (`reportlab` or `weasyprint`) into media storage. **Keep the old synchronous behaviour available behind a query param or a second endpoint if any test depends on it.**
- [ ] **4.4 — Task: low-stock sweep (Celery Beat).** Every 15 minutes, find products below their reorder threshold and create `Notification` rows for Managers and Admins. Must be idempotent — do not create a duplicate notification for a product already flagged and unread.
- [ ] **4.5 — Task: nightly ledger reconciliation.** Assert that each product's `current_stock` equals the sum of its `InventoryTransaction` rows. On mismatch, log at ERROR with the product ids and create an Admin notification. **Read-only — it must never "fix" the discrepancy silently.**
- [ ] **4.6 — Dispatch rules.** Every `.delay()` / `.apply_async()` triggered from inside a request goes through `transaction.on_commit(...)`. Configure `task_acks_late=True` and `autoretry_for` with `retry_backoff=True`, `max_retries=3` on any task doing I/O.
- [ ] **4.7 — Finish the `/health` celery check** from 1.5 — ping the worker with a short timeout, report `ok` / `degraded`.
- [ ] **4.8 — Tests.** `tests/test_tasks.py`: use `CELERY_TASK_ALWAYS_EAGER=True` for logic tests; separately assert that a task dispatched inside a rolled-back transaction never runs. Test low-stock idempotency and reconciliation detection with a deliberately corrupted row.

**Acceptance:** `docker compose up` starts api + worker + beat. Invoice generation is async with a status endpoint. Beat schedule visible in logs. Reconciliation detects a seeded mismatch. Suite green.

---

## Phase 5 — Structured logging

- [ ] **5.1 — Add `structlog`.** Configure JSON output in production settings, human-readable console renderer in development.
- [ ] **5.2 — Request ID middleware.** Read `X-Request-ID` from the incoming request or generate a UUID4. Bind it to the structlog context for the request's lifetime. Echo it back as a response header.
- [ ] **5.3 — Propagate the request ID into Celery.** Attach it to the task headers on dispatch; bind it in a task prerun signal handler. One id must trace a request through web → queue → worker.
- [ ] **5.4 — Log the events that matter.** Structured, with fields not string interpolation:
  - Every stock mutation: `order_id`, `product_ids`, `quantity_delta`, `actor_id`, `role`, `lock_wait_ms`
  - Every 409 idempotent replay
  - Every 429 throttle rejection
  - Cache hit/miss ratio per endpoint
  - Task start/success/failure with duration
  Do **not** log JWTs, passwords, or full request bodies.
- [ ] **5.5 — Add a log sample** to `docs/v2/` showing one request traced end to end across web and worker.

**Acceptance:** JSON logs in prod config. A single request id appears in web and worker logs for one async operation. No secrets in output.

---

## Phase 6 — Load testing (the headline deliverable)

**This is the most important phase in the spec. If time runs short, cut Phase 4 tasks before cutting this.**

- [ ] **6.1 — Add a locking kill-switch.** New setting `INVENTORY_LOCKING_ENABLED`, default `True`. When `False`, the stock mutation path skips `select_for_update()` and does a plain read-check-write. **Guard it:** raise `ImproperlyConfigured` at startup if it is `False` while `DEBUG` is `False`. This exists solely to produce the comparison in 6.4 — it must be impossible to deploy the unsafe path.
- [ ] **6.2 — Write `loadtest/locustfile.py`.** Scenarios:
  - `StockMutator` — concurrent `POST /sales-orders/{id}/complete` against a single product with limited stock
  - `ReportReader` — hammering `/dashboard` and `/reports/inventory` (measures cache effectiveness)
  - `MixedLoad` — 80% reads, 20% writes
  Handle JWT acquisition once per user at start, not per request.
- [ ] **6.3 — Write `loadtest/README.md`** — how to seed, how to run each scenario, what to record.
- [ ] **6.4 — Run the experiment and record results.** Fill this table in `docs/v2/LOAD_TEST_RESULTS.md`:

  | Config | Users | Stock | Sold | Oversold | p50 | p95 | p99 | RPS | Errors |
  |---|---|---|---|---|---|---|---|---|---|
  | Locking OFF | 500 | 100 | ? | ? | | | | | |
  | Locking ON | 500 | 100 | ? | **0** | | | | | |
  | Reports, cache OFF | 500 | — | — | — | | | | | |
  | Reports, cache ON | 500 | — | — | — | | | | | |

  Record hardware, dataset size, and Locust config alongside the numbers. **Do not publish a number you cannot reproduce on demand.**
- [ ] **6.5 — Write the analysis.** In `LOAD_TEST_RESULTS.md`, explain *why* locking costs latency (serialised access to the contended row), *why* the unlocked version oversells (read-check-write across concurrent transactions under READ COMMITTED), and what you'd do if the locking cost became unacceptable — sharded counters, queue-based serialisation, optimistic retry.
- [ ] **6.6 — Record a GIF** of the load test running with the oversell counter at zero.

**Acceptance:** Reproducible results table with a non-zero oversell figure in the unlocked row and exactly zero in the locked row. Written analysis. GIF captured.

---

## Phase 7 — Deploy, docs, CI

- [ ] **7.1 — Update `railway.json` / deployment config** for the worker and beat processes. Add the Redis addon. Document every new env var in `.env.example`.
- [ ] **7.2 — Update CI** (`.github/workflows/ci.yml`): add a Redis service container, run the new test files, keep ruff. Do not run the load test in CI.
- [ ] **7.3 — Write the ADRs** in `docs/v2/adr/`, ~200 words each — context, decision, consequences:
  - `0001-cache-invalidation.md` — version counters over key enumeration
  - `0002-async-invoices.md` — why 202 + polling over synchronous generation
  - `0003-locking-tradeoff.md` — pessimistic locking, with the measured cost from Phase 6
  - `0004-request-tracing.md` — request id propagation across process boundaries
- [ ] **7.4 — Rewrite the README's opening.** Currently it leads with "same domain as the FastAPI version." It should lead with the strongest fact, which after Phase 6 is the load-test result. Add a **Performance** section containing the results table and a link to the full analysis. Move the FastAPI-vs-Django comparison below it — it's excellent, but it's the second thing a reader should hit, not the first.
- [ ] **7.5 — Put the GIF at the top of the README.** Most readers will never run the code.
- [ ] **7.6 — Final check.** Clean clone → `cp .env.example .env` → `docker compose up --build` → everything starts, `/health` all-green, full suite passes.

**Acceptance:** Deployed with worker + beat running. CI green. README leads with measured performance. Clean-clone quickstart verified.

---

## Definition of done

- [ ] All 7 phases complete, every existing test still passing
- [ ] New tests: caching (incl. isolation), throttling, tasks, transaction-rollback safety
- [ ] `docs/v2/LOAD_TEST_RESULTS.md` with reproducible numbers and written analysis
- [ ] 4 ADRs written
- [ ] README leads with performance evidence; GIF at top
- [ ] Deployed; `/health` reports database, redis, and celery all `ok`
- [ ] Ledger immutability, `select_for_update` lock ordering, and 409-on-replay all still intact and still tested

---

## Notes for the human (not the agent)

- Phase 6 is what you'll actually talk about in interviews. Everything before it is setup for it. If you have to stop early, stop after Phase 6 and do Phase 7 anyway — undocumented work doesn't count.
- Review the agent's Phase 2 and Phase 4 output carefully. Cache invalidation and `transaction.on_commit` are the two places where a plausible-looking implementation can be subtly wrong, and both are things you'll be asked about.
- Run the load test yourself rather than trusting reported output. You need to have watched the numbers appear to defend them.

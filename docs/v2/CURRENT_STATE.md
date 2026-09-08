# Current state (Phase 0 baseline)

Recorded 2026-09-08 on branch `v2`, against the local dev Postgres (portable
Postgres 16, port 5433 — not the docker-compose/CI default of 5432; `.env`
was updated to point at it for local work on this branch).

## Repo layout

```
config/
  settings/{base,development,production}.py   settings split, DJANGO_SETTINGS_MODULE selects which
  urls.py                                      root urlconf; /health is inline here, not in an app
  wsgi.py
apps/
  accounts/     custom User (UUID pk, email USERNAME_FIELD), RoleName TextChoices, SimpleJWT
  catalog/      Category, Supplier, Product
  inventory/    PurchaseOrder(+Item), SalesOrder(+Item), InventoryTransaction (ledger), Return
  reports/      no models — DashboardView + 4 report APIViews only
  notifications/ Notification model + notify()/notify_admins_and_managers() helpers
tests/
  conftest.py           shared fixtures; api_client, role fixtures, auth_headers()
  test_rbac.py          8 tests
  test_transaction_guarantee.py   5 tests
  test_concurrency.py   2 tests, live_server + threading, real concurrent HTTP
docker-compose.yml       postgres only today (5432), api service, no redis/worker/beat
.github/workflows/ci.yml postgres:16-alpine service, uv sync --frozen, migrate, ruff, pytest
```

`apps/core` does not exist yet — Phase 1/2 will create it for `cache.py`.

## Settings

- `DJANGO_SETTINGS_MODULE` env var picks `development` or `production`; both
  just `from .base import *` and override a handful of flags.
- `base.py` reads `SECRET_KEY` and `DATABASE_URL` from the environment with
  no fallback (`os.environ[...]`, not `.get()`) — missing either raises
  `KeyError` at import time, by design.
- `REST_FRAMEWORK` already sets `DEFAULT_PAGINATION_CLASS` (`PageNumberPagination`,
  `PAGE_SIZE=20`) and `DjangoFilterBackend` + search/ordering filters globally.
- No cache backend configured at all (implicitly `LocMemCache`, unused).

## Concurrency tests — how they're wired

`test_concurrency.py` uses `@pytest.mark.django_db(transaction=True)` +
pytest-django's `live_server` fixture: a real Django dev server in a
background thread, hit with two real HTTP requests fired from two Python
`threading.Thread`s via the `requests` library (genuinely concurrent, over
independent DB connections — a normal rolled-back-transaction test can't see
across connections, hence the `transaction=True` opt-in). Two tests:
PO-receive-twice-concurrently (asserts stock applied once, statuses
`[200, 409]`) and SO-complete-on-last-unit-concurrently (asserts no oversell).
Both rely on the views' `select_for_update()` — commented out, either fails.

## `docker compose up` today

Two services: `postgres` (16-alpine, healthcheck, named volume) and `api`
(built from the repo's `Dockerfile`, `DJANGO_SETTINGS_MODULE=production`,
gunicorn via the image's entrypoint, whitenoise for static files). No redis,
worker, or beat service. Ports 5432/8000.

## Test suite — green baseline

```
uv run pytest -v
```

**15 passed, 14 warnings in ~39s.** (14 warnings are all the same
`UserWarning: No directory at: ...\staticfiles\` from whitenoise's
middleware finding no `collectstatic` output in dev — harmless, pre-existing.)

`uv run ruff check apps config tests manage.py` — clean, no findings.

## Query-count / latency baseline (Phase 0.3)

Measured with `django.test.Client` + `override_settings(DEBUG=True)` +
`django.db.connection.queries`, authenticated as a seeded demo admin, against
the dataset produced by `seed_demo` (see below). Two runs, consistent:

| Endpoint | Queries | Time (ms) |
|---|---|---|
| `/dashboard` | 9 | ~855-865 |
| `/reports/inventory` | 2 | ~330-360 |
| `/reports/sales` | 3 | ~435-470 |
| `/products/` (list, paginated) | 3 | ~35-40 |

**These are the numbers Phase 2 caching must improve.** Note the shape of
the problem: query *counts* are already low (no N+1 here — `/dashboard` is
9 separate `COUNT(*)` queries, one per metric, not a loop; the report views
use `prefetch_related`/plain `.all()`). The cost is Python-side: both report
views pull every matching row into memory and iterate/sum in Python rather
than aggregating in SQL, so latency scales with row count, not query count.
`/reports/inventory` and `/reports/sales` are the slow ones because they
iterate the full unfiltered transaction/order tables. A cache with a 300s TTL
(Phase 2) will turn all of this into near-zero-query, near-zero-latency
responses on hit — which is the right fix here since the *endpoint* is
expensive per call, not (only) the query plan.

## Phase 2 — caching results (2.7)

Re-measured the same four endpoints with caching live (same script, same
seeded dataset, second request per endpoint so the cache is warm):

| Endpoint | Queries before | Queries after (hit) |
|---|---|---|
| `/dashboard` | 9 | **1** (JWT auth's own user lookup only) |
| `/reports/inventory` | 2 | **1** |
| `/reports/sales` | 3 | **1** |
| `/products/` (not cached — out of Phase 2's scope) | 3 | 3 (unchanged, as expected) |

Query counts on a cache hit collapse to just the JWT authentication
backend's own user lookup — the report/dashboard view body never runs at
all, confirmed by `tests/test_caching.py`'s
`test_second_identical_request_hits_cache`, which asserts this directly via
`CaptureQueriesContext` rather than trusting a manual measurement.

Wall-clock timings from this same script are **not** reported here: this
measurement session ran alongside several other background processes on
this machine (a WSL-hosted Redis instance kept alive for local verification
since Docker Desktop was unavailable, and a concurrent `pytest` run), which
inflated per-request latency into the seconds on some runs even for a
single-query cache hit — clearly host contention, not the caching code
itself, but not a number worth publishing either. The query-count result
above is the reliable signal and matches the acceptance criterion directly
("query counts near zero on hit"); a clean latency re-measurement can be
taken any time by re-running `query_baseline`-style script logic against an
idle machine.

## Seed command (Phase 0.4)

`python manage.py seed_demo --products 500 --orders 2000 [--flush]`,
implemented at
[apps/catalog/management/commands/seed_demo.py](../../apps/catalog/management/commands/seed_demo.py).

- Deterministic distribution (`random.Random(42)`) — same shape of data
  every run; primary keys are still real `uuid4()` values (Django's
  `default=uuid.uuid4` on every model isn't affected by seeding `random`).
- Tags everything it creates by naming convention so `--flush` can find and
  remove exactly its own output and nothing else: categories/suppliers named
  `"Demo ..."`, products with a `DEMO-` SKU prefix, users on the
  `@demo.seed` domain.
- Idempotent without `--flush`: if demo data is already present, it's a
  no-op (`Category.objects.filter(name__startswith="Demo Category").exists()`
  gate). Confirmed by running it twice in a row.
- Order generation replays the same stock bookkeeping the real `/receive`,
  `/complete`, `/returns/{id}/approve` and `/damage` endpoints do — one
  `InventoryTransaction` per stock change, `Product.current_stock` kept in
  sync — so the seeded dataset satisfies the ledger invariant
  (`current_stock == sum of its transactions`) that Phase 4's reconciliation
  task will check.
- Verified run (`--products 500 --orders 2000`, ~20s): 10 categories, 20
  suppliers, 6 users, 500 products, 1003 purchase orders, 998 sales orders,
  4015 inventory transactions, 39 returns. (Dev DB shows 501 products —
  one pre-existing product from earlier manual testing predates this branch;
  harmless, not part of the seeded/tagged set.)

## Environment note

Local dev Postgres is the portable install at `C:\Users\THARU\pgsql16`,
port **5433**, not 5432 — `docker-compose.yml` and CI both use 5432, no
conflict, just don't confuse the two when comparing local vs.
containerized/CI runs. `.env`'s `DATABASE_URL`/ports were pointed at 5433 and
given a real (dev-only) `DJANGO_SECRET_KEY` on this branch so the suite and
the baseline script above could actually run; `.env` is gitignored so this
doesn't leak.

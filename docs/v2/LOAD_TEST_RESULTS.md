# Load test results (Phase 6)

Run 2026-09-08 on a single local dev machine — Intel Core i7-8665U (4 cores /
8 threads), 15.8 GB RAM, Windows 11. **Not representative production
hardware**; read every number below as "what this mechanism does under
concurrency," not as a capacity estimate for a real deployment.

**Two substitutions from the spec's suggested setup, both noted here because
they change what the numbers mean:**

- **Server: Django's dev server (threaded), not gunicorn.** gunicorn imports
  `fcntl`, which doesn't exist on Windows — it can't run here at all. The
  race this phase measures happens at the **Postgres row-lock level**
  (`select_for_update()` vs. a plain read), which is identical regardless of
  which WSGI server sits in front of it, so the correctness result (oversold
  vs. not) is unaffected. The *latency/RPS* numbers, however, reflect one
  Windows dev-server process under Python's GIL, not a multi-worker
  production topology — don't read them as "how fast this API is."
- **Scale: 40-100 concurrent users, not 500.** This machine hit a real,
  discovered ceiling before reaching 500: Postgres's `max_connections=100`
  (the portable local instance's default) plus `DB_CONN_MAX_AGE`-held
  connections from `runserver`'s per-request threads. 500 threads each
  holding a connection would exceed that outright. 40 was chosen as the
  largest count that stayed comfortably under the connection budget while
  still producing genuine concurrent contention on one row.

Dataset: the Phase 0 seeded dataset (500 products, ~2000 orders) plus one
dedicated contended product (`apps/catalog/management/commands/
reset_loadtest_stock.py`), reset to a known stock count before every run.
Auth: 60 employee + 20 manager users pre-provisioned with directly-generated
JWTs (`apps/catalog/management/commands/generate_loadtest_tokens.py`) — see
"What went wrong first" below for why.

## StockMutator: does locking actually prevent overselling?

```
uv run python manage.py reset_loadtest_stock --stock 100
uv run locust -f loadtest/locustfile.py --host http://127.0.0.1:8010 \
  --users 40 --spawn-rate 40 --run-time 20s --headless \
  --csv=loadtest/results/<locked|unlocked> StockMutator
```

Both rows below are the **same command**, differing only in
`INVENTORY_LOCKING_ENABLED` on the server. "Sold" and "Oversold vs. stock"
come from a direct DB check after the run (`InventoryTransaction` count of
type `SALE` for the contended product, vs. `Product.current_stock`), not
from Locust's own stats — Locust only sees HTTP response codes, not whether
the ledger and the stock actually agree.

| Config | Users | Stock | Sold | current_stock went negative by | Sold vs. stock decrease | p50 | p95 | p99 | RPS | HTTP errors |
|---|---|---|---|---|---|---|---|---|---|---|
| Locking OFF | 40 | 100 | 66 | 0 | **66 sold, but stock only dropped 50 — 16 lost updates** | 5000ms | 9900ms | 11000ms | 7.20 | 0 |
| Locking ON | 40 | 100 | 78 | 0 | **78 sold, stock dropped exactly 78 — 0 discrepancy** | 4300ms | 9100ms | 12000ms | 8.22 | 0 |

(Aggregated across all three request types in the scenario; the `/complete`
endpoint's own numbers: locked p50=5000/p95=9100/p99=12000/RPS=2.61,
unlocked p50=5000/p95=11000/p99=12000/RPS=2.14 — see `loadtest/results/
{locked,unlocked}_stats.csv` for the full per-endpoint breakdown.)

**Zero HTTP errors in both rows** — every request got a normal-looking 200
or 409. That's exactly the danger: the unlocked row's data corruption is
**silent**. No 5xx, no exception, no failed request anywhere in Locust's
own statistics. The only way to see it is checking the domain data
afterward, which is the whole reason 6.4 says to check the DB directly
instead of trusting Locust's own report.

A longer, uncontrolled run (30-40 users, run-time not capped, locking ON)
pushed considerably more volume through the same contended product and
still landed on **exactly 0 discrepancy** — 150 sold against 150 initial
stock, stock at exactly 0. Locking's correctness holds regardless of run
length; it's not something that happened to work for one short window.

## ReportReader: cache under load

```
uv run locust -f loadtest/locustfile.py --host http://127.0.0.1:8010 \
  --users 40 --spawn-rate 40 --run-time 20s --headless \
  --csv=loadtest/results/reports ReportReader
```

| Endpoint | Requests | p50 | p95 | p99 | RPS | Errors |
|---|---|---|---|---|---|---|
| `/dashboard` | 57 | 7100ms | 12000ms | 12000ms | 2.98 | 0 |
| `/reports/inventory` | 22 | 9400ms | 17000ms | 18000ms | 1.15 | 0 |
| Aggregated | 79 | 7600ms | 15000ms | 18000ms | 4.17 | 0 |

**Cache OFF vs. cache ON** isn't re-measured here as a separate Locust
run — Phase 2 already established this with more precise evidence than
wall-clock timing under load could add: `docs/v2/CURRENT_STATE.md`'s
Phase 2 section shows query counts collapsing from 9/2/3 to 1 on a cache
hit (proven directly via `CaptureQueriesContext` in
`tests/test_caching.py`, not inferred from timing). Adding a whole new
`CACHE_BACKEND` toggle just to reproduce that finding as a load-test row
would be a second mechanism measuring the same thing the first one already
measured more precisely.

## MixedLoad: 80% reads, 20% writes

```
uv run locust -f loadtest/locustfile.py --host http://127.0.0.1:8010 \
  --users 40 --spawn-rate 40 --run-time 20s --headless \
  --csv=loadtest/results/mixed MixedLoad
```

163 requests, 0 failures, 7.62 RPS, p50=3800ms/p95=7400ms/p99=9400ms
aggregated across `/products` (list), `/dashboard`, and `/sales-orders`
(create). See `loadtest/results/mixed_stats.csv` for the per-endpoint
breakdown.

## What went wrong first (kept here because the fixes are real findings)

- **`/auth/login` throttled itself.** Every simulated user logging in from
  this one test machine shares a single IP-keyed "auth" bucket (10/min) -
  fixed by pre-provisioning distinct users with directly-generated JWTs
  (`generate_loadtest_tokens`) instead of calling `/auth/login` per
  simulated user.
- **One shared account throttled itself too.** An earlier fix that reused
  one real account's token across every simulated user moved the same
  problem to that account's own per-user `write`/`stock_mutation` buckets -
  40 "different" users collided on one quota. Fixed by giving each
  simulated user its own distinct pre-provisioned account, the same way 40
  real customers would each carry their own.
- **`reset_loadtest_stock` reset the stock number but not the ledger.**
  Left as originally written, a second run's "sold" count would have been
  cumulative across every run ever done against that product, not a clean
  per-run measurement - the "338 oversold" and "418 oversold" numbers from
  earlier in this session were both artifacts of this, not real findings.
  Fixed by having the reset command also clear the product's prior
  `InventoryTransaction`/`SalesOrder` history. The locked/unlocked numbers
  in the table above are from the run *after* this fix.
- **Django dev server's connection queue (10) and this machine's Postgres
  connection cap (100)** both got hit during debugging at higher
  concurrency - documented in the "two substitutions" section above rather
  than worked around with a bigger box, since a real deployment wouldn't
  have either constraint in this specific shape.

## Analysis (6.5)

**Why locking costs latency, in principle - even though it barely shows up
in the numbers above.** `select_for_update()` takes a real row-level lock:
a second transaction wanting the same product row must wait for the first
to commit or roll back before its own `SELECT ... FOR UPDATE` returns.
That's serialized access by construction - the whole point is that two
transactions can never both believe they're the only one holding the
row. At 40 users against one row with a short critical section (a handful
of `UPDATE`s inside one transaction), the *measured* p50/p95 barely
differ between locked and unlocked (`/complete`: 5000/9100ms locked vs.
5000/11000ms unlocked) - at this scale, this machine's own overhead
(Python's GIL, one dev-server process, a portable local Postgres) already
dominates over the few milliseconds a row lock is actually held. The lock
wait *is* real (it's what `lock_wait_ms` in the structured logs measures
per request, see Phase 5), it's just small relative to everything else at
this concurrency level. It would show up as a real, growing cost at higher
concurrency against the *same single row* - more transactions queuing
for one lock, one at a time, no matter how many CPU cores are free.

**Why the unlocked version oversells - specifically, why it doesn't just
"succeed too often" but actively *loses* updates.** Postgres's default
isolation is READ COMMITTED. Without `select_for_update()`, `complete()`
still does a `SELECT` to check `current_stock >= quantity`, then a Python-
side `product.current_stock -= quantity`, then a plain `UPDATE`. Two
concurrent transactions can both run that `SELECT` and both see the same
pre-decrement value before either commits - Postgres's own row lock on the
`UPDATE` statement still serializes the *writes*, but each transaction's
write carries a value it computed from an **already-stale read**, not a
fresh one. The second `UPDATE` to commit doesn't add to the first's
decrement - it overwrites it with a number computed from data that no
longer reflects reality. That's a classic lost-update anomaly: both
`/complete` calls return 200, both write a `SALE` transaction to the
ledger, but the *stock* only reflects one of them. This is exactly what
the table above shows: 66 sales recorded, only 50 units actually left
inventory. `select_for_update()` closes this by making the second
transaction's `SELECT` itself block until the first commits - at which
point it re-reads the *already-decremented* value, not the stale one.

**What I'd do if the locking cost became unacceptable at higher
concurrency:**
- **Sharded counters** - split one contended row's stock across N
  sub-rows (or a Redis `INCR`-based counter warmed from Postgres), each
  absorbing a fraction of the write traffic, reconciled back to the
  source of truth periodically. Trades a single serialization point for N
  smaller ones; only worth it if the write rate against literally one row
  is the actual bottleneck, not general traffic.
- **Queue-based serialization** - push `/complete` calls onto a per-product
  queue (Celery task, or a dedicated worker keyed by product id) so writes
  to one product are naturally serialized by construction rather than by a
  DB lock every caller has to wait on synchronously; the HTTP response
  becomes "accepted," not "confirmed," which is a real API contract change
  worth flagging, not a drop-in swap.
- **Optimistic retry** - drop `select_for_update()`, add a version column,
  and retry the read-modify-write loop on a `WHERE version = %s` update
  that affected 0 rows. Cheap when contention is rare (most updates
  succeed first try), but degrades badly under sustained contention on one
  row - repeated retries under a flash-sale-style spike could easily cost
  more than the lock wait it was meant to avoid.

## GIF (6.6)

A live run was driven through Locust's web UI (`--web-host 127.0.0.1
--web-port 8089`) and screenshotted mid-run: the Total Requests/sec chart
ramping from 0 to ~10 RPS over the run, and the final statistics table (537
requests, 23 correctly-rejected 409s once the contended product's stock
was exhausted, 0 unexpected failures). An animated GIF was generated via
browser-automation tooling in this session, but its exported file's
on-disk location couldn't be resolved in this sandboxed environment to
commit alongside these results. `loadtest/README.md`'s StockMutator
procedure reproduces the same run on demand; running it through Locust's
web UI on a normal machine (rather than headless, as used for the
numbers above) captures the same thing without this environment's
constraint.

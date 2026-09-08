# Load testing

Phase 6 of `inventra-v2-spec.md`. Locust scenarios against a running API,
plus how to measure the one thing Locust itself can't tell you: whether the
`StockMutator` scenario actually oversold anything.

## Prerequisites

```bash
uv sync                                   # installs locust (dev group)
uv run python manage.py seed_demo --products 500 --orders 2000   # once
```

The API needs to actually be running (`uv run python manage.py runserver`,
or the full `docker compose up`), reachable at whatever `--host` you pass
Locust.

## StockMutator: does locking actually prevent overselling?

1. **Reset the contended product** before every run - this is the
   reproducibility mechanism, not a one-time seed:
   ```bash
   uv run python manage.py reset_loadtest_stock --stock 100
   ```
2. **Run with locking as-is** (default `INVENTORY_LOCKING_ENABLED=true`):
   ```bash
   uv run locust -f loadtest/locustfile.py --host http://localhost:8000 \
     --users 500 --spawn-rate 50 --run-time 60s --headless \
     --csv=loadtest/results/locked StockMutator
   ```
3. **Check whether anything oversold** (Locust's own stats only show HTTP
   response codes/latency, not domain state):
   ```bash
   uv run python manage.py shell -c "
   from apps.catalog.models import Product
   p = Product.objects.get(sku='LOADTEST-CONTENDED-001')
   print('final current_stock:', p.current_stock)
   print('oversold:', max(0, -p.current_stock))
   "
   ```
   `current_stock` going negative is the unambiguous signal - the model
   has no DB-level check constraint against it, so a genuine race shows up
   as a literal negative number, not something you have to infer.
4. **Reset again, then re-run with the kill-switch off** to produce the
   comparison row:
   ```bash
   uv run python manage.py reset_loadtest_stock --stock 100
   INVENTORY_LOCKING_ENABLED=false DEBUG=true uv run python manage.py runserver
   # in another shell, same locust command as step 2, --csv=loadtest/results/unlocked
   ```
   `INVENTORY_LOCKING_ENABLED=false` is refused by `apps/core/checks.py`
   unless `DEBUG=true` - it cannot be run against anything resembling a
   real deployment, only a local `runserver`.

## ReportReader / MixedLoad: cache effectiveness under load

Same `--host`/`--users`/`--run-time` shape, no product reset needed:

```bash
uv run locust -f loadtest/locustfile.py --host http://localhost:8000 \
  --users 200 --spawn-rate 20 --run-time 60s --headless \
  --csv=loadtest/results/reports ReportReader
```

Compare p50/p95/p99 and RPS with Phase 2's caching decorator commented out
vs. left in place, on the same seeded dataset, to see the effect for real
rather than trusting the Phase 0/2 query-count numbers alone.

## What to record

For every run, note in `docs/v2/LOAD_TEST_RESULTS.md`: the machine you ran
it on (CPU, RAM - this is a single-machine dev box, not representative
production hardware, and the numbers should be read that way), the seeded
dataset size, the exact Locust command (`--users`/`--spawn-rate`/
`--run-time`), and the resulting table. Locust's own `--csv` output
(`*_stats.csv`) has the RPS/latency percentiles directly; the oversell
count comes from the shell snippet above, not from Locust.

**Don't publish a number you can't reproduce.** `reset_loadtest_stock` and
a fixed `--users`/`--spawn-rate`/`--run-time` exist specifically so every
row in the results table can be re-run on demand, not just quoted once.

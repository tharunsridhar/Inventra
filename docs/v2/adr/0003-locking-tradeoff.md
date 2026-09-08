# ADR 0003: Pessimistic locking on stock mutations, with the measured cost

## Context

`/receive`, `/complete`, `/returns/{id}/approve`, and `/damage` all
read-then-write `Product.current_stock`. Under concurrent requests against
the same product, a read-check-write without a lock lets two transactions
both act on the same pre-mutation value - see Phase 6's `LOAD_TEST_RESULTS.md`
for what that produces in practice, not just in theory.

## Decision

Every stock mutation takes `select_for_update()` on the product (and
parent order) row before reading `current_stock`, serializing concurrent
access to that row. Product rows touched within one transaction are locked
in a fixed order (by id) so two transactions that both touch the same two
products always acquire them in the same order and queue instead of
deadlocking.

## Consequences

- **Correctness, measured, not assumed.** Locked: 78 sales recorded against
  a 100-unit stock, stock dropped by exactly 78 - zero discrepancy.
  Unlocked, same test: 66 sales recorded, but stock only dropped by 50 - 16
  silently lost updates, with **zero HTTP errors** in either run. See
  `docs/v2/LOAD_TEST_RESULTS.md`.
- **The latency cost is real but was small at the scale tested** (40
  concurrent users against one row): locked vs. unlocked `/complete`
  p50/p95 were within noise of each other on this single dev machine. The
  serialization cost scales with contention on one specific row, not with
  total traffic - it would show up more clearly at higher concurrency
  against the same row than this test reached.
- A kill-switch (`INVENTORY_LOCKING_ENABLED`, Phase 6) exists to reproduce
  the unlocked comparison on demand, guarded so it can never be set outside
  local `DEBUG` (`apps/core/checks.py`) - the comparison stays reproducible
  without the unsafe path ever being deployable.
- If this lock's cost became unacceptable at real scale: sharded counters,
  queue-based serialization, or optimistic retry with a version column -
  see `LOAD_TEST_RESULTS.md`'s analysis for the tradeoffs of each.

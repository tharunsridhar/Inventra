# ADR 0001: Cache invalidation via version counters, not key enumeration

## Context

Phase 2 caches `/dashboard` and the four `/reports/*` endpoints. Every
stock-mutating action (`/receive`, `/complete`, `/returns/{id}/approve`,
`/damage`) must invalidate anything cached from before the mutation. Each
of those report endpoints can be requested with an open-ended set of
`start_date`/`end_date` query parameter combinations, and the cache is
scoped per requesting user on top of that.

## Decision

Cache keys are not addressed directly for deletion. Each cache "namespace"
(here, one namespace: `"inventory"`) has a single integer version counter
in Redis. Every cache key embeds the current version:
`{namespace}:v{version}:{endpoint}:{hash(user+params)}`. Invalidating the
namespace is one `cache.incr("cache:version:inventory")` - every key
written under the old version number is now unreachable by construction
(no code path can ever compute an old-version key again) and is left to
expire from Redis naturally via its TTL.

## Consequences

- No enumeration or pattern-delete of keys is ever needed, and there is no
  way to "miss" invalidating one - a missed key is only possible if a
  cached response were written under a version number newer than the
  current counter, which the read path can't produce.
- Invalidation is O(1) regardless of how many distinct query-param/user
  combinations have been cached.
- Orphaned entries are not evicted immediately; they sit in Redis until
  their TTL (300s) expires. This trades a small amount of stale-but-dead
  memory for never needing a key-deletion scan. At this data volume and
  TTL, that's a non-issue; if the namespace ever needed hard eviction, the
  fix is a shorter TTL, not enumeration.
- A single version counter per namespace means invalidation is
  all-or-nothing within that namespace - bumping it discards every cached
  report and dashboard response, not just the one affected by a given
  mutation. Acceptable here because all of Phase 2's cached endpoints read
  from the same underlying ledger; a finer-grained namespace split (e.g.
  per-report) would only be worth it if invalidation frequency or cache
  size became a measured problem.

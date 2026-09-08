# ADR 0002: Async invoice generation - 202 + polling, not synchronous

## Context

`GET /sales-orders/{id}/invoice` used to build and return invoice data
synchronously inside the request. Phase 4 adds a real PDF (reportlab),
written to disk - real I/O, with real (if small) latency and a real chance
of a transient failure. Doing that inline ties the request's response time
to file I/O and, further out, to whatever a PDF library happens to cost on
a given order's line-item count.

## Decision

The endpoint now enqueues `generate_invoice_pdf` and returns `202 Accepted`
with a `task_id` immediately. `GET /tasks/{id}/` polls status and exposes a
`result_url` once the PDF exists. Dispatch goes through
`transaction.on_commit(...)`, consistent with every other task dispatch in
this app - the endpoint doesn't mutate anything itself, but the discipline
is applied uniformly rather than as a special case.

## Consequences

- The client now needs two round trips (kick off, then poll) instead of
  one - a real contract change, which is why this endpoint specifically was
  named in the spec as needing it, rather than applied silently everywhere.
- PDF generation failures no longer fail the HTTP request that triggered
  them - they show up as a failed task, visible via `GET /tasks/{id}/` and
  in structured logs (`task_failed`, Phase 5), not as a 500.
- Retries (`autoretry_for`, `retry_backoff=True`, `max_retries=3`) can
  absorb a transient failure - e.g. a momentary disk issue - without the
  client seeing anything beyond a slightly longer `PENDING` window.
- The HTTP method stayed `GET`, matching the spec's instruction to change
  only this endpoint's response contract, not its route. A stricter REST
  reading would prefer `POST` for an endpoint that now has a side effect
  (enqueuing work) - flagged here rather than changed unilaterally.

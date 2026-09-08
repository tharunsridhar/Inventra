# ADR 0004: Request id propagation across process boundaries

## Context

A single user action (e.g. completing a sale) can span two processes: the
web request itself, and an async task it dispatches (invoice generation).
Debugging a production issue means correlating log lines across both -
grep'ing `apps.inventory.views`'s logs and a worker's logs separately and
matching them up by timestamp doesn't scale and isn't reliable under any
real concurrent load.

## Decision

`apps/core/middleware.py`'s `RequestIDMiddleware` reads `X-Request-ID` from
the incoming request (or generates a uuid4), binds it into structlog's
`contextvars` for the request's lifetime, and echoes it back as a response
header. When a view dispatches a Celery task, it passes the same id through
`apply_async(..., headers={"request_id": ...})`. `apps/core/
celery_signals.py`'s `task_prerun` handler reads it back out of
`task.request.headers` in the **worker process** and rebinds it into that
process's own structlog context before the task body runs.

## Consequences

- One id, present on every structured log line for a request and every
  task it dispatched, in both processes - `grep`-able across a web log and
  a worker log with the same string. See `docs/v2/LOG_SAMPLE.md` for a real
  captured trace showing this end to end.
- Contextvars are cleared and rebound at the start of both the middleware
  and the Celery signal handler, so a worker process reusing threads/
  greenlets across tasks can't leak one task's request_id into the next
  task's logs.
- This only covers task dispatch that already goes through
  `apply_async(...)`/`.delay()` with an explicit `headers=` kwarg - a task
  dispatched without passing headers (there currently isn't one, but a
  future one could be added carelessly) would fall back to using its own
  `task_id` as a stand-in trace id rather than silently having no id at
  all, which is why `task_prerun`'s fallback is `headers.get("request_id")
  or task_id`, not `None`.
- Client-supplied `X-Request-ID` is trusted as-is (no format validation) -
  acceptable for a correlation id used only in logs, not for anything
  security- or authorization-relevant.

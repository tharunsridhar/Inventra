# Structured logging: one request traced end to end (Phase 5.5)

Captured live (2026-09-08) with `LOG_RENDERER=json`: a `POST
/sales-orders/{id}/complete/` request carrying `X-Request-ID:
demo-trace-11111111-2222-3333-4444-555555555555`, immediately followed by
running the invoice-generation task it would have dispatched, with that
same id threaded into the task's headers exactly as
`apps/inventory/views.py`'s `invoice` action does for real. Reproducible
with `apps/core/middleware.py` + `apps/core/celery_signals.py` as committed
- no mocking involved, this is the real logging pipeline.

## Web: `POST /sales-orders/{id}/complete/`

```json
{"action": "complete", "order_id": "e27feedc-b392-435e-90e3-e33bcbd52aee", "product_ids": ["aa519074-4ce1-4f7f-9784-cc8fe799e509"], "quantity_delta": -2, "actor_id": "3388f513-b382-4c18-8d0a-829450a420a3", "role": "employee", "lock_wait_ms": 16.0, "event": "stock_mutation", "request_id": "demo-trace-11111111-2222-3333-4444-555555555555", "level": "info", "logger": "apps.inventory.views", "timestamp": "2026-09-08T18:17:59.980523Z"}
```

`request_id` was read from the `X-Request-ID` header by
`RequestIDMiddleware` and bound into structlog's contextvars for the rest
of this request - every field on this line (`order_id`, `product_ids`,
`quantity_delta`, `actor_id`, `role`, `lock_wait_ms`) comes from the single
`logger.info("stock_mutation", ...)` call in `SalesOrderViewSet.complete()`,
placed right after the mutation succeeds (never on the early-return 409
paths - see the `idempotent_replay_409` event for those).

## Worker: `generate_invoice_pdf`, dispatched from that same request

```json
{"event": "task_started", "request_id": "demo-trace-11111111-2222-3333-4444-555555555555", "task_name": "apps.inventory.tasks.generate_invoice_pdf", "task_id": "demo-task-99999999-8888-7777-6666-555555555555", "level": "info", "logger": "apps.core.celery_signals", "timestamp": "2026-09-08T18:18:00.017864Z"}
{"state": "SUCCESS", "duration_ms": 171.99999999138527, "event": "task_finished", "request_id": "demo-trace-11111111-2222-3333-4444-555555555555", "task_name": "apps.inventory.tasks.generate_invoice_pdf", "task_id": "demo-task-99999999-8888-7777-6666-555555555555", "level": "info", "logger": "apps.core.celery_signals", "timestamp": "2026-09-08T18:18:00.199604Z"}
```

`request_id` here is identical to the web log line above - propagated via
`generate_invoice_pdf.apply_async(..., headers={"request_id": ...})` in the
view, then read back out of `task.request.headers` and re-bound into
structlog's contextvars by `apps/core/celery_signals.py`'s `task_prerun`
handler, running in the **worker process**, not the web process. That's the
whole point: one id, grep-able across both log streams, ties a single
end-user action to the background work it triggered.

`task_finished` carries `duration_ms`, measured from `task_prerun` to
`task_postrun` (a separate `task_failed` event with the exception attached
fires instead on failure - see `apps/core/celery_signals.py`).

## A caveat worth knowing

Between those two worker lines, Celery's own internal success logger (not
routed through structlog - a plain `logging.info()` call inside Celery
itself) also flows through the same root JSON formatter, since the
formatter is attached at the root logger level:

```json
{"event": "Task apps.inventory.tasks.generate_invoice_pdf[demo-task-...] succeeded in 0.17...s: {...}"}
```

It's valid JSON (so it won't break a log pipeline expecting JSON lines) but
carries none of structlog's usual fields (`request_id`, `level`, etc.) since
it was never a structlog call - just Celery's own framework-level log
message, incidentally wrapped by the same renderer. Harmless, and still
distinguishable from the app's own events (no `request_id` field), but not
something application code controls.

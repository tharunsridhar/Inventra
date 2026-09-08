"""Binds the dispatching request's request_id into a worker's structlog
context for the duration of one task, and logs task start/success/failure
with duration - see docs/v2/ for a sample trace showing one request_id
across both a web log line and a worker log line.

Imported once from config/celery.py so these signal handlers are
registered as soon as the Celery app is."""

import time

import structlog
from celery.signals import task_failure, task_postrun, task_prerun

logger = structlog.get_logger(__name__)

_task_start_times: dict[str, float] = {}


@task_prerun.connect
def _bind_request_id_and_log_start(sender=None, task_id=None, task=None, **kwargs):
    headers = getattr(task.request, "headers", None) or {}
    request_id = headers.get("request_id") or task_id

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id, task_id=task_id, task_name=task.name)

    _task_start_times[task_id] = time.monotonic()
    logger.info("task_started")


@task_postrun.connect
def _log_task_finished(sender=None, task_id=None, task=None, state=None, **kwargs):
    # task_failure (below) already logs the FAILURE case with the actual
    # exception attached - don't double-log the same task's completion.
    if state == "FAILURE":
        return
    started_at = _task_start_times.pop(task_id, None)
    duration_ms = (time.monotonic() - started_at) * 1000 if started_at is not None else None
    logger.info("task_finished", state=state, duration_ms=duration_ms)


@task_failure.connect
def _log_task_failed(sender=None, task_id=None, exception=None, **kwargs):
    started_at = _task_start_times.pop(task_id, None)
    duration_ms = (time.monotonic() - started_at) * 1000 if started_at is not None else None
    logger.error("task_failed", duration_ms=duration_ms, error=str(exception))

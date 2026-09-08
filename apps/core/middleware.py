"""Request ID: read X-Request-ID from the incoming request, or generate a
uuid4 if absent. Bound into structlog's contextvars for the lifetime of the
request, so every log line emitted while handling it - in this process,
and later in a worker if the request dispatches a task, see
apps.core.celery_signals - carries the same id without every log call
needing to pass it explicitly. Echoed back as a response header so a
client (or another service) can correlate its own logs against ours."""

import uuid

import structlog


class RequestIDMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.request_id = request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = self.get_response(request)
        response["X-Request-ID"] = request_id
        return response

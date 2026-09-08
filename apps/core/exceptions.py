"""Wraps DRF's default exception handler purely to log throttle
rejections - the 429 response itself (Retry-After header, {"detail": ...}
body) is entirely DRF's own default behavior, untouched."""

import structlog
from rest_framework.exceptions import Throttled
from rest_framework.views import exception_handler as default_exception_handler

logger = structlog.get_logger(__name__)


def logging_exception_handler(exc, context):
    response = default_exception_handler(exc, context)

    if isinstance(exc, Throttled):
        request = context["request"]
        view = context["view"]
        logger.warning(
            "throttled",
            scope=getattr(view, "throttle_scope", None),
            path=request.path,
            method=request.method,
            actor_id=str(request.user.pk) if request.user and request.user.is_authenticated else None,
            wait_seconds=exc.wait,
        )

    return response

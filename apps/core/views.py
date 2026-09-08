from celery.result import AsyncResult
from django.conf import settings
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class TaskStatusView(APIView):
    """GET /tasks/{id}/ - generic status endpoint for any Celery task
    dispatched from a request (currently just invoice generation). Reads
    straight from the Celery result backend rather than a DB model - there's
    nothing to keep in sync, the result backend already durably has the
    answer for as long as CELERY_RESULT_BACKEND retains it."""

    permission_classes = [IsAuthenticated]
    throttle_scope = "read"

    def get(self, request, task_id):
        result = AsyncResult(str(task_id))
        data = {"task_id": str(task_id), "status": result.status}

        if result.successful():
            payload = result.result
            path = payload.get("path") if isinstance(payload, dict) else None
            if path:
                data["result_url"] = request.build_absolute_uri(f"{settings.MEDIA_URL}{path}")
        elif result.failed():
            data["error"] = str(result.result)

        return Response(data)

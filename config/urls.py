from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path
from django.views.generic import TemplateView

from apps.core.views import TaskStatusView
from config.celery import app as celery_app


def health_check(request):
    checks = {"database": "ok", "redis": "ok", "celery": "ok"}

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        checks["database"] = "error"

    try:
        cache.set("health_check_ping", "1", timeout=5)
        if cache.get("health_check_ping") != "1":
            raise ValueError("cache read-after-write mismatch")
    except Exception:
        checks["redis"] = "error"

    try:
        # Short timeout - /health must stay fast even if a worker is wedged,
        # not just absent. No reply within it reads the same as "no worker".
        pong = celery_app.control.inspect(timeout=1.0).ping()
        checks["celery"] = "ok" if pong else "degraded"
    except Exception:
        checks["celery"] = "degraded"

    healthy = all(v == "ok" for v in checks.values())
    return JsonResponse(
        {"status": "ok" if healthy else "error", "checks": checks},
        status=200 if healthy else 503,
    )


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", health_check, name="health"),
    path("app", TemplateView.as_view(template_name="app.html"), name="app"),
    path("tasks/<uuid:task_id>/", TaskStatusView.as_view(), name="task-status"),
    path("", include("apps.accounts.urls")),
    path("", include("apps.catalog.urls")),
    path("", include("apps.inventory.urls")),
    path("", include("apps.reports.urls")),
    path("", include("apps.notifications.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

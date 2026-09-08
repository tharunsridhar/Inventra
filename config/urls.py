from django.contrib import admin
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.urls import include, path


def health_check(request):
    # "celery" is stubbed until Phase 4 wires a real worker ping - it never
    # fails this check on its own, so it's excluded from the ok/error roll-up
    # below rather than hardcoded into it.
    checks = {"database": "ok", "redis": "ok", "celery": "not_configured"}

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

    healthy = all(v != "error" for v in checks.values())
    return JsonResponse(
        {"status": "ok" if healthy else "error", "checks": checks},
        status=200 if healthy else 503,
    )


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", health_check, name="health"),
    path("", include("apps.accounts.urls")),
    path("", include("apps.catalog.urls")),
    path("", include("apps.inventory.urls")),
    path("", include("apps.reports.urls")),
    path("", include("apps.notifications.urls")),
]

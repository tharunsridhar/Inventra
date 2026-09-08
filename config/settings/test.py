"""Settings for the pytest run (see pyproject.toml's DJANGO_SETTINGS_MODULE).

Tests must never see cached data from a dev run against real Redis, and
must not require Redis to be up at all to run the plain (non-caching) test
files - LocMemCache is process-local and reset per test process."""

from .development import *  # noqa: F403

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

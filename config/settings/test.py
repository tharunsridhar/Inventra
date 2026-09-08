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

# Small numeric limits (same "/min" window as production) so a throttling
# test can trip a 429 with a handful of requests instead of hundreds -
# window duration doesn't matter for test speed, only the count does.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {
        "auth": "3/min",
        "read": "5/min",
        "write": "5/min",
        "stock_mutation": "3/min",
        "reports": "3/min",
        "anon": "3/min",
    },
}

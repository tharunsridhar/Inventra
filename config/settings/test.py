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

# Tasks run inline, synchronously, with no broker/worker/Redis needed for
# tests at all. This is safe even for the "a rolled-back transaction must
# not dispatch its task" guarantee: dispatch is always wrapped in
# transaction.on_commit(...) in view code, and on_commit callbacks are
# governed by whether the transaction actually commits regardless of
# whether the task itself then runs eagerly or via a real broker.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
# Without this, an eager task's result exists only on the object .delay()
# returns - a *separate* request (like GET /tasks/{id}/, looking the id up
# fresh via AsyncResult) would find nothing, since eager mode skips the
# result backend by default.
CELERY_TASK_STORE_EAGER_RESULT = True
# In-process, not real Redis - tests never need a broker at all (eager mode
# never contacts it) and this keeps the result-backend side self-contained
# too, instead of depending on Redis being reachable to run the suite.
CELERY_RESULT_BACKEND = "cache+memory://"

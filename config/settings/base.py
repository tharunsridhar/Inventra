"""Settings shared by every environment. development.py / production.py each
import * from here and override what needs to differ.

Everything security- or connectivity-sensitive comes from the environment
with no fallback - see Inventra's FastAPI port for the same principle
(pydantic-settings with required fields there; os.environ[...] here, which
raises KeyError just as loudly if it's missing)."""

import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
import structlog
from celery.schedules import crontab
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    # domain apps
    "apps.accounts",
    "apps.catalog",
    "apps.inventory",
    "apps.reports",
    "apps.notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    # As early as possible - everything downstream (including the
    # exception handler that logs 429s) should see request_id already
    # bound in structlog's context.
    "apps.core.middleware.RequestIDMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Postgres only - the whole point of this port is production parity, same as
# the FastAPI side. DATABASE_URL is required, no sqlite fallback.
DATABASES = {
    "default": dj_database_url.parse(
        os.environ["DATABASE_URL"],
        conn_max_age=int(os.environ.get("DB_CONN_MAX_AGE", "600")),
        conn_health_checks=True,
    )
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Generated invoice PDFs (Phase 4). Local disk only - fine for this spec's
# scope, but a real multi-instance deployment would need this on shared/
# object storage (S3 etc.) since gunicorn workers/replicas don't share a
# filesystem. Not wired through whitenoise (that's STATIC_ROOT only, and is
# a build-time compressed/hashed bundle, not a place to write at runtime).
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
# whitenoise serves collectstatic's output directly from gunicorn - no nginx
# container needed, same "single deployable process" shape as the FastAPI
# and PhotoShare ports. Compressed + hashed filenames, so a browser can
# cache them indefinitely without risking stale CSS/JS after a deploy.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# db 0 = cache, db 1 = Celery broker, db 2 = Celery result backend - kept on
# separate logical DBs so a FLUSHDB on the cache (Phase 2 invalidates via a
# version counter, never a real flush, but still) can't also wipe out the
# task queue.
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
    }
}

_REDIS_BASE = REDIS_URL.rsplit("/", 1)[0]
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", f"{_REDIS_BASE}/1")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", f"{_REDIS_BASE}/2")
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
# Redeliver a task if the worker dies mid-execution instead of losing it -
# the cost is a task can run twice on a worker crash, which is why every
# task below is itself idempotent (skips work it can prove already happened)
# rather than relying on at-most-once delivery.
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BEAT_SCHEDULE = {
    "sweep-low-stock": {
        "task": "apps.inventory.tasks.sweep_low_stock",
        "schedule": 15 * 60,
    },
    "reconcile-ledger-nightly": {
        "task": "apps.inventory.tasks.reconcile_ledger",
        "schedule": crontab(hour=2, minute=0),
    },
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "apps.core.exceptions.logging_exception_handler",
    # ScopedRateThrottle only engages on a view that sets throttle_scope (see
    # apps.core.throttling.ScopedByActionThrottleMixin) - everything else
    # falls through untouched. AnonRateThrottle is the general backstop for
    # unauthenticated traffic on views that don't declare a scope of their
    # own. Neither ever applies to /health - it's a plain Django view, not a
    # DRF one, so it never enters this pipeline at all.
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "auth": "10/min",
        "read": "200/min",
        "write": "60/min",
        "stock_mutation": "20/min",
        "reports": "30/min",
        "anon": "20/min",
    },
}

# ROTATE_REFRESH_TOKENS + BLACKLIST_AFTER_ROTATION + the token_blacklist app
# above is SimpleJWT's version of Inventra's DB-stored revocable refresh
# tokens: a used/rotated-out token is recorded and rejected on reuse, same
# guarantee, different mechanism (a blacklist table instead of a single
# `revoked` boolean column).
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.environ.get("REFRESH_TOKEN_EXPIRE_DAYS", "7"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
}

# Structured logging (Phase 5). This processor chain is shared by every
# environment - it's what turns a logger.info(event, key=value, ...) call
# into fields, not a formatted sentence. Which *renderer* turns that into
# actual output text (JSON for production's log aggregator, colored
# console output for development) is each environment's own choice - see
# LOGGING in development.py / production.py, both built with
# core_logging_config() below.
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)


def core_logging_config(renderer):
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "structured": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processors": [structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
            },
        },
        "handlers": {
            "console": {"class": "logging.StreamHandler", "formatter": "structured"},
        },
        "root": {"handlers": ["console"], "level": "INFO"},
        "loggers": {
            "django.server": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        },
    }

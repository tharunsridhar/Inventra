import os

import structlog

from .base import *  # noqa: F403
from .base import core_logging_config

DEBUG = False

LOGGING = core_logging_config(structlog.processors.JSONRenderer())

# Required in production - no "*" fallback like development.py has.
ALLOWED_HOSTS = [h.strip() for h in os.environ["ALLOWED_HOSTS"].split(",") if h.strip()]
CORS_ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()]

SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "true").lower() == "true"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# Secure cookies require HTTPS - a browser silently drops a Secure cookie
# over plain HTTP, which breaks CSRF and session auth entirely rather than
# just weakening them. Tied to the same flag as SECURE_SSL_REDIRECT since
# both describe the same fact: is there a TLS-terminating proxy in front of
# this deployment or not.
SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT
CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT

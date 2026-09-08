import structlog

from .base import *  # noqa: F403
from .base import core_logging_config

DEBUG = True
ALLOWED_HOSTS = ["*"]
CORS_ALLOW_ALL_ORIGINS = True

LOGGING = core_logging_config(structlog.dev.ConsoleRenderer())

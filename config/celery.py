"""Celery app for the project. config/__init__.py imports `app` from here so
`@shared_task`-decorated tasks anywhere under apps/ always bind to this
instance, the same way config/wsgi.py is the one place that wires up
Django's WSGI application."""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("inventra")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

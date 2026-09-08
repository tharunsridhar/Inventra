"""Runs the dev server with a much larger TCP accept queue than
manage.py runserver's default (10) - too small for Phase 6's load tests,
which need to accept many near-simultaneous connections in a burst. Local
load-testing tool only; never used to actually serve the app.

    uv run python loadtest/run_server_for_loadtest.py 127.0.0.1:8010 --noreload
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django  # noqa: E402

django.setup()

from django.core.management import execute_from_command_line  # noqa: E402
from django.core.servers.basehttp import WSGIServer  # noqa: E402

WSGIServer.request_queue_size = 256

if __name__ == "__main__":
    execute_from_command_line([sys.argv[0], "runserver", *sys.argv[1:]])

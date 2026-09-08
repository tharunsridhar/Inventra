"""Pre-provisions distinct users + JWTs for loadtest/locustfile.py, written
to loadtest/tokens.json for the locustfile to read directly - no HTTP login
calls at test time at all.

Two throttle-related problems this sidesteps, both discovered by actually
running the load test rather than assumed up front:
  1. Logging in over HTTP, even once per simulated user, hits /auth/login's
     "auth" scope (10/min) - which for unauthenticated requests is keyed by
     client IP, not by which account is logging in, so every simulated user
     originating from this one test machine shares a single bucket.
  2. Having many simulated users share ONE real account collides on that
     account's own "write"/"stock_mutation" throttle buckets (those scopes
     are keyed by user id once authenticated) - the aggregate demand of 40
     "different" load-test users gets throttled as if it were one real
     user's traffic, which isn't what a real flash sale looks like (many
     distinct customers, each with their own quota).

Distinct pre-provisioned users with directly-generated tokens (the same
RefreshToken.for_user() pattern tests/conftest.py's auth_headers() uses)
fix both: no HTTP calls to /auth/login, and each simulated user gets an
independent throttle bucket, same as real distinct customers would."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import RoleName, User

OUTPUT_PATH = Path(__file__).resolve().parents[4] / "loadtest" / "tokens.json"


class Command(BaseCommand):
    help = "Pre-provision distinct users + JWTs for loadtest/locustfile.py (writes loadtest/tokens.json)."

    def add_arguments(self, parser):
        parser.add_argument("--employees", type=int, default=60)
        parser.add_argument("--managers", type=int, default=20)

    def handle(self, *args, **options):
        employees = self._provision(RoleName.EMPLOYEE, "loadtest-employee", options["employees"])
        managers = self._provision(RoleName.MANAGER, "loadtest-manager", options["managers"])

        OUTPUT_PATH.write_text(json.dumps({"employee": employees, "manager": managers}, indent=2))
        self.stdout.write(self.style.SUCCESS(
            f"Wrote {len(employees)} employee + {len(managers)} manager tokens to {OUTPUT_PATH}"
        ))

    def _provision(self, role, prefix, count):
        tokens = []
        for i in range(count):
            email = f"{prefix}-{i:04d}@loadtest.local"
            user = User.objects.filter(email=email).first()
            if user is None:
                user = User.objects.create_user(email=email, password="loadtestpass123", full_name=email, role=role)
            tokens.append(str(RefreshToken.for_user(user).access_token))
        return tokens

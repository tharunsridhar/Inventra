"""Phase 3 rate limiting. config.settings.test overrides every throttle
rate down to a handful of requests per minute (see config/settings/test.py)
so these tests trip a 429 in a few calls instead of hundreds - the window
duration doesn't matter for test speed, only the numeric limit does."""

import pytest

from tests.conftest import _make_user, auth_headers

pytestmark = pytest.mark.django_db


def _hit_until_throttled(api_client, path, headers, limit):
    responses = [api_client.get(path, **headers) for _ in range(limit + 1)]
    return responses


def test_exceeding_a_scope_returns_429_with_retry_after(api_client, manager_user):
    # "reports" is set to 3/min in the test settings.
    responses = _hit_until_throttled(api_client, "/dashboard", auth_headers(manager_user), limit=3)
    assert [r.status_code for r in responses[:3]] == [200, 200, 200]
    throttled = responses[3]
    assert throttled.status_code == 429
    assert "Retry-After" in throttled
    assert throttled.json()["detail"]  # same {"detail": ...} shape as every other error in this API


def test_throttle_counter_is_per_user_not_global(api_client):
    from apps.accounts.models import RoleName

    manager_a = _make_user(RoleName.MANAGER)
    manager_b = _make_user(RoleName.MANAGER)

    # Exhaust manager_a's "reports" allowance (3/min in tests).
    for _ in range(3):
        res = api_client.get("/dashboard", **auth_headers(manager_a))
        assert res.status_code == 200
    assert api_client.get("/dashboard", **auth_headers(manager_a)).status_code == 429

    # manager_b has an independent counter and is unaffected.
    assert api_client.get("/dashboard", **auth_headers(manager_b)).status_code == 200


def test_health_is_never_throttled(api_client):
    # /health is a plain Django view, not a DRF one - it never enters the
    # throttling pipeline at all, regardless of how many times it's hit.
    responses = [api_client.get("/health") for _ in range(10)]
    assert all(r.status_code in (200, 503) for r in responses)
    assert all(r.status_code != 429 for r in responses)


def test_different_scopes_have_independent_counters(api_client, manager_user):
    # Exhaust "reports" (3/min) - "read" (5/min in tests) must be unaffected.
    for _ in range(3):
        assert api_client.get("/dashboard", **auth_headers(manager_user)).status_code == 200
    assert api_client.get("/dashboard", **auth_headers(manager_user)).status_code == 429

    assert api_client.get("/products/", **auth_headers(manager_user)).status_code == 200

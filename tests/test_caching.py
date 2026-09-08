"""Phase 2 caching: version-counter invalidation, per-user isolation, and
the transaction.on_commit guarantee (a rolled-back mutation must never
invalidate the cache on the basis of a change that never happened)."""

import pytest
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext

from apps.core.cache import bump_version, get_version
from tests.conftest import _make_user, auth_headers

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


def test_second_identical_request_hits_cache(api_client, manager_user):
    with CaptureQueriesContext(connection) as first_queries:
        first = api_client.get("/reports/inventory", **auth_headers(manager_user))
    assert first.status_code == 200
    assert first["X-Cache"] == "MISS"

    with CaptureQueriesContext(connection) as second_queries:
        second = api_client.get("/reports/inventory", **auth_headers(manager_user))
    assert second.status_code == 200
    assert second["X-Cache"] == "HIT"
    assert second.json() == first.json()

    # On a hit, only JWT auth's own DB lookups run - the report's own
    # query (or queries) must be skipped entirely.
    assert len(second_queries) < len(first_queries)


@pytest.mark.django_db(transaction=True)
def test_complete_invalidates_cache_and_next_read_reflects_new_stock(api_client, manager_user, employee_user, product):
    # transaction=True (real commits) is required here, not the default
    # rolled-back-transaction test isolation: transaction.on_commit()
    # callbacks - which is how /complete's cache invalidation is wired -
    # never fire at all inside a transaction that's rolled back, not just
    # deferred.
    before = api_client.get("/reports/inventory", **auth_headers(manager_user))
    assert before["X-Cache"] == "MISS"
    total_sold_before = before.json()["summary"]["total_sold"]

    # second read within the same (unchanged) state should still be a HIT
    assert api_client.get("/reports/inventory", **auth_headers(manager_user))["X-Cache"] == "HIT"

    so = api_client.post(
        "/sales-orders/", {"items": [{"product_id": str(product.id), "quantity": 2}]},
        format="json", **auth_headers(employee_user),
    ).json()
    complete = api_client.post(f"/sales-orders/{so['id']}/complete/", **auth_headers(employee_user))
    assert complete.status_code == 200

    after = api_client.get("/reports/inventory", **auth_headers(manager_user))
    assert after["X-Cache"] == "MISS"  # invalidated, not served stale
    assert after.json()["summary"]["total_sold"] == total_sold_before + 2


def test_isolation_between_users_never_cross_serves(api_client, product):
    from apps.accounts.models import RoleName

    manager_a = _make_user(RoleName.MANAGER)
    manager_b = _make_user(RoleName.MANAGER)

    res_a1 = api_client.get("/reports/inventory", **auth_headers(manager_a))
    assert res_a1["X-Cache"] == "MISS"
    res_b1 = api_client.get("/reports/inventory", **auth_headers(manager_b))
    # user B's first request must never be served user A's cached entry
    assert res_b1["X-Cache"] == "MISS"

    res_a2 = api_client.get("/reports/inventory", **auth_headers(manager_a))
    assert res_a2["X-Cache"] == "HIT"
    res_b2 = api_client.get("/reports/inventory", **auth_headers(manager_b))
    assert res_b2["X-Cache"] == "HIT"


def test_employee_never_reaches_a_manager_scoped_cached_response(api_client, manager_user, employee_user):
    # Warm the cache as a manager first.
    assert api_client.get("/dashboard", **auth_headers(manager_user))["X-Cache"] == "MISS"
    # An Employee is blocked by permissions before the cache is ever
    # consulted - the endpoint must not leak the manager's cached response.
    res = api_client.get("/dashboard", **auth_headers(employee_user))
    assert res.status_code == 403


@pytest.mark.django_db(transaction=True)
def test_rolled_back_mutation_does_not_bump_the_version():
    version_before = get_version("inventory")

    try:
        with transaction.atomic():
            transaction.on_commit(lambda: bump_version("inventory"))
            raise RuntimeError("force a rollback after registering the on_commit hook")
    except RuntimeError:
        pass

    assert get_version("inventory") == version_before, "a rolled-back transaction must not invalidate the cache"

    with transaction.atomic():
        transaction.on_commit(lambda: bump_version("inventory"))

    assert get_version("inventory") == version_before + 1, "a committed transaction must invalidate the cache"

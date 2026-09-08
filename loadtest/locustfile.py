"""Load test scenarios for Phase 6 of inventra-v2-spec.md.

    uv run python manage.py generate_loadtest_tokens   # once, or whenever the pool needs resizing
    uv run locust -f loadtest/locustfile.py --host http://localhost:8000 StockMutator
    uv run locust -f loadtest/locustfile.py --host http://localhost:8000 ReportReader
    uv run locust -f loadtest/locustfile.py --host http://localhost:8000 MixedLoad

Run exactly one scenario at a time (Locust runs every User class in the
file by default unless you name specific ones, as above) - see
loadtest/README.md for the full run/seed/record procedure.

Every simulated user picks a token from a pool pre-provisioned by
generate_loadtest_tokens (loadtest/tokens.json) rather than logging in
itself. Discovered by actually running this, not assumed up front:
  - Hitting /auth/login from every simulated user, even once each, throttles
    itself - unauthenticated requests are throttled by client IP, not by
    which account, so every user on this one test machine shares one
    10/min bucket regardless of how many distinct accounts they represent.
  - Sharing ONE real account across many simulated users doesn't dodge that
    - it just moves the collision to that account's own per-user "write"/
    "stock_mutation" throttle buckets, throttling 40 "different" load-test
    users as if they were one real user's traffic, which understates what
    a real flash sale (many distinct customers, each with their own quota)
    actually looks like.
Distinct pre-provisioned users, each with their own independently-generated
token, avoid both - no HTTP login calls at all, and each simulated user
gets its own throttle bucket like a real distinct customer would.
"""

import json
import os
import random
from pathlib import Path

from locust import HttpUser, between, task

CONTENDED_SKU = os.environ.get("LOADTEST_CONTENDED_SKU", "LOADTEST-CONTENDED-001")
TOKENS_PATH = Path(__file__).resolve().parent / "tokens.json"

try:
    _token_pool = json.loads(TOKENS_PATH.read_text())
except FileNotFoundError:
    raise RuntimeError(
        f"{TOKENS_PATH} not found - run: uv run python manage.py generate_loadtest_tokens first"
    ) from None


class StockMutator(HttpUser):
    """Concurrent POST /sales-orders/{id}/complete against a single product
    with limited stock (see apps/catalog/management/commands/
    reset_loadtest_stock.py). Each user creates its own 1-unit order for
    the contended product, then immediately completes it - many independent
    orders racing the same product, not many requests against the same
    order (which would just test idempotency, not overselling).

    Locust itself can't assert "did we oversell" - that's a property of
    final DB state, not of any single response. Check it after the run
    with a direct product/ledger query - see loadtest/README.md."""

    wait_time = between(0, 0.05)

    def on_start(self):
        token = random.choice(_token_pool["employee"])
        self.client.headers.update({"Authorization": f"Bearer {token}"})
        # There's no exact-sku filter on this endpoint (see apps/catalog/
        # filters.py) - `search` does a fuzzy match across name/sku/etc.,
        # so filter to the exact sku client-side rather than trust ordering.
        res = self.client.get(f"/products/?search={CONTENDED_SKU}", name="/products (lookup contended)")
        results = [p for p in res.json().get("results", []) if p["sku"] == CONTENDED_SKU]
        if not results:
            raise RuntimeError(f"{CONTENDED_SKU} not found - run: manage.py reset_loadtest_stock first")
        self.product_id = results[0]["id"]

    @task
    def buy_one_unit(self):
        create_res = self.client.post(
            "/sales-orders/", json={"items": [{"product_id": self.product_id, "quantity": 1}]},
            name="/sales-orders (create)",
        )
        if create_res.status_code != 201:
            return
        so_id = create_res.json()["id"]
        self.client.post(f"/sales-orders/{so_id}/complete/", name="/sales-orders/{id}/complete")


class ReportReader(HttpUser):
    """Hammers /dashboard and /reports/inventory - measures Phase 2 cache
    effectiveness under load (compare with the caching decorator
    disabled/enabled, or watch the X-Cache ratio via response headers)."""

    wait_time = between(0.1, 0.5)

    def on_start(self):
        token = random.choice(_token_pool["manager"])
        self.client.headers.update({"Authorization": f"Bearer {token}"})

    @task(2)
    def dashboard(self):
        self.client.get("/dashboard", name="/dashboard")

    @task(1)
    def inventory_report(self):
        self.client.get("/reports/inventory", name="/reports/inventory")


class MixedLoad(HttpUser):
    """80% reads, 20% writes - a blended, more realistic traffic shape
    than either pure scenario above."""

    wait_time = between(0.1, 0.5)

    def on_start(self):
        token = random.choice(_token_pool["manager"])
        self.client.headers.update({"Authorization": f"Bearer {token}"})
        res = self.client.get("/products/", name="/products (list, seed pick)")
        self.product_ids = [p["id"] for p in res.json().get("results", [])]

    @task(4)
    def read_products(self):
        self.client.get("/products/", name="/products (list)")

    @task(3)
    def read_dashboard(self):
        self.client.get("/dashboard", name="/dashboard")

    @task(1)
    def create_sales_order(self):
        if not self.product_ids:
            return
        product_id = random.choice(self.product_ids)
        self.client.post(
            "/sales-orders/", json={"items": [{"product_id": product_id, "quantity": 1}]},
            name="/sales-orders (create)",
        )

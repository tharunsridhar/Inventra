"""Load test scenarios for Phase 6 of inventra-v2-spec.md.

    uv run locust -f loadtest/locustfile.py --host http://localhost:8000 StockMutator
    uv run locust -f loadtest/locustfile.py --host http://localhost:8000 ReportReader
    uv run locust -f loadtest/locustfile.py --host http://localhost:8000 MixedLoad

Run exactly one scenario at a time (Locust runs every User class in the
file by default unless you name specific ones, as above) - see
loadtest/README.md for the full run/seed/record procedure.

Every user acquires its JWT once in on_start(), not per request - hammering
/auth/login per request would throttle itself (the "auth" scope is 10/min)
and measure login cost instead of the scenario being tested.
"""

import os
import random

from locust import HttpUser, between, task

CONTENDED_SKU = os.environ.get("LOADTEST_CONTENDED_SKU", "LOADTEST-CONTENDED-001")
EMPLOYEE_EMAIL = os.environ.get("LOADTEST_EMPLOYEE_EMAIL", "demo-employee-1@demo.seed")
MANAGER_EMAIL = os.environ.get("LOADTEST_MANAGER_EMAIL", "demo-manager-1@demo.seed")
PASSWORD = os.environ.get("LOADTEST_PASSWORD", "demopass123")


def _login(client, email, password):
    res = client.post("/auth/login", json={"email": email, "password": password}, name="/auth/login")
    res.raise_for_status()
    return res.json()["access"]


class StockMutator(HttpUser):
    """Concurrent POST /sales-orders/{id}/complete against a single product
    with limited stock (see apps/catalog/management/commands/
    reset_loadtest_stock.py). Each user creates its own 1-unit order for
    the contended product, then immediately completes it - many independent
    orders racing the same product, not many requests against the same
    order (which would just test idempotency, not overselling).

    Locust itself can't assert "did we oversell" - that's a property of
    final DB state, not of any single response. Check it after the run
    with apps.inventory.tasks-style stock/ledger inspection - see
    loadtest/README.md."""

    wait_time = between(0, 0.05)

    def on_start(self):
        token = _login(self.client, EMPLOYEE_EMAIL, PASSWORD)
        self.client.headers.update({"Authorization": f"Bearer {token}"})
        res = self.client.get(f"/products/?sku={CONTENDED_SKU}", name="/products (lookup contended)")
        results = res.json().get("results", [])
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
    effectiveness under load (compare with the cache-response middleware
    disabled/enabled, or just watch the X-Cache ratio in the Locust UI's
    custom response headers if you enable that column)."""

    wait_time = between(0.1, 0.5)

    def on_start(self):
        token = _login(self.client, MANAGER_EMAIL, PASSWORD)
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
        token = _login(self.client, MANAGER_EMAIL, PASSWORD)
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

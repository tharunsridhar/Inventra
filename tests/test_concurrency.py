"""Proves the concurrency guarantee: receiving a purchase order and
completing a sales order are each atomic and idempotent under concurrent
requests.

Uses pytest-django's `live_server` fixture (a real Django dev server in a
background thread) and two real HTTP requests fired from separate Python
threads via `requests` - genuinely concurrent, over independent DB
connections, the same shape as the FastAPI port's live_client-based
concurrency tests. django_db(transaction=True) is required for live_server:
a normal rolled-back-transaction test wouldn't be visible to the server
thread's own connection.

Comment out .select_for_update() in either view and either test below will
fail - that's the proof the race existed and is now closed.
"""

import threading

import pytest
import requests

from apps.accounts.models import RoleName
from apps.catalog.models import Category, Product, Supplier
from apps.inventory.models import PurchaseOrder, PurchaseOrderItem, PurchaseOrderStatus, SalesOrder, SalesOrderItem, SalesOrderStatus
from tests.conftest import _make_user


def _bearer_header(user) -> dict:
    from rest_framework_simplejwt.tokens import RefreshToken

    token = RefreshToken.for_user(user).access_token
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.django_db(transaction=True)
def test_concurrent_purchase_order_receive_applies_stock_exactly_once(live_server):
    manager = _make_user(RoleName.MANAGER)
    headers = _bearer_header(manager)

    category = Category.objects.create(name="Concurrency Category PO")
    supplier = Supplier.objects.create(name="Concurrency Supplier PO", email="conc-po@example.com")
    product = Product.objects.create(
        sku="CONC-PO-001", name="Concurrency Widget", cost_price="10.00", selling_price="20.00",
        current_stock=0, category=category, supplier=supplier,
    )
    po = PurchaseOrder.objects.create(supplier=supplier, status=PurchaseOrderStatus.ORDERED)
    PurchaseOrderItem.objects.create(purchase_order=po, product=product, quantity=5, unit_cost="10.00")

    url = f"{live_server.url}/purchase-orders/{po.id}/receive/"
    results = []

    def fire():
        results.append(requests.post(url, headers=headers, timeout=10))

    threads = [threading.Thread(target=fire) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    statuses = sorted(r.status_code for r in results)
    assert statuses == [200, 409]

    product.refresh_from_db()
    # 5, not 10 - the locked second request saw status=received and never
    # touched stock, instead of both requests applying +5
    assert product.current_stock == 5


@pytest.mark.django_db(transaction=True)
def test_concurrent_sales_order_complete_never_oversells_last_unit(live_server):
    manager = _make_user(RoleName.MANAGER)
    headers = _bearer_header(manager)

    category = Category.objects.create(name="Concurrency Category SO")
    supplier = Supplier.objects.create(name="Concurrency Supplier SO", email="conc-so@example.com")
    product = Product.objects.create(
        sku="CONC-SO-001", name="Concurrency Gadget", cost_price="10.00", selling_price="20.00",
        current_stock=1, category=category, supplier=supplier,  # exactly one unit left
    )
    so = SalesOrder.objects.create(status=SalesOrderStatus.CREATED)
    SalesOrderItem.objects.create(sales_order=so, product=product, quantity=1, unit_price="20.00")

    url = f"{live_server.url}/sales-orders/{so.id}/complete/"
    results = []

    def fire():
        results.append(requests.post(url, headers=headers, timeout=10))

    threads = [threading.Thread(target=fire) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    statuses = sorted(r.status_code for r in results)
    assert statuses == [200, 409]

    product.refresh_from_db()
    # 0, not -1 - the locked second request saw status=completed and never
    # touched stock, instead of both requests deducting the same last unit
    assert product.current_stock == 0

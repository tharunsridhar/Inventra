"""The core guarantee: every stock-affecting action writes exactly one
immutable InventoryTransaction row, and receiving a purchase order /
completing a sales order are each atomic and idempotent."""

import pytest

from apps.inventory.models import InventoryTransaction, TransactionType
from tests.conftest import auth_headers

pytestmark = pytest.mark.django_db


def test_receiving_a_purchase_order_writes_one_transaction_and_updates_stock(api_client, manager_user, supplier, product):
    po = api_client.post(
        "/purchase-orders/", {"supplier_id": str(supplier.id), "items": [{"product_id": str(product.id), "quantity": 5, "unit_cost": "10.00"}]},
        format="json", **auth_headers(manager_user),
    ).json()

    res = api_client.post(f"/purchase-orders/{po['id']}/receive/", **auth_headers(manager_user))
    assert res.status_code == 200
    assert res.json()["status"] == "received"

    product.refresh_from_db()
    assert product.current_stock == 15

    txns = InventoryTransaction.objects.filter(reference_id=po["id"])
    assert txns.count() == 1
    assert txns.first().transaction_type == TransactionType.PURCHASE
    assert txns.first().quantity == 5


def test_receiving_a_purchase_order_twice_is_a_no_op_the_second_time(api_client, manager_user, supplier, product):
    po = api_client.post(
        "/purchase-orders/", {"supplier_id": str(supplier.id), "items": [{"product_id": str(product.id), "quantity": 5, "unit_cost": "10.00"}]},
        format="json", **auth_headers(manager_user),
    ).json()

    first = api_client.post(f"/purchase-orders/{po['id']}/receive/", **auth_headers(manager_user))
    assert first.status_code == 200
    second = api_client.post(f"/purchase-orders/{po['id']}/receive/", **auth_headers(manager_user))
    assert second.status_code == 409

    product.refresh_from_db()
    assert product.current_stock == 15  # not 20 - the second call changed nothing
    assert InventoryTransaction.objects.filter(reference_id=po["id"]).count() == 1


def test_completing_a_sales_order_deducts_stock_and_writes_one_transaction(api_client, employee_user, product):
    so = api_client.post("/sales-orders/", {"items": [{"product_id": str(product.id), "quantity": 3}]}, format="json", **auth_headers(employee_user)).json()

    res = api_client.post(f"/sales-orders/{so['id']}/complete/", **auth_headers(employee_user))
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "completed"
    assert body["invoice_number"]

    product.refresh_from_db()
    assert product.current_stock == 7

    txns = InventoryTransaction.objects.filter(reference_id=so["id"])
    assert txns.count() == 1
    assert txns.first().transaction_type == TransactionType.SALE


def test_completing_a_sales_order_with_insufficient_stock_changes_nothing(api_client, employee_user, product):
    so = api_client.post("/sales-orders/", {"items": [{"product_id": str(product.id), "quantity": 999}]}, format="json", **auth_headers(employee_user)).json()

    res = api_client.post(f"/sales-orders/{so['id']}/complete/", **auth_headers(employee_user))
    assert res.status_code == 409

    product.refresh_from_db()
    assert product.current_stock == 10  # unchanged
    assert InventoryTransaction.objects.filter(reference_id=so["id"]).count() == 0


def test_inventory_transactions_have_no_write_route(api_client, manager_user):
    """No PATCH/DELETE route exists on this ViewSet at all (it's a
    ReadOnlyModelViewSet) - the audit trail can't be edited or erased once
    written, by construction."""
    import uuid

    res = api_client.patch(f"/inventory-transactions/{uuid.uuid4()}/", {"quantity": 1}, format="json", **auth_headers(manager_user))
    assert res.status_code == 405

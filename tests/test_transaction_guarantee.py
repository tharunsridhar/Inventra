"""The core guarantee this app makes: every stock-affecting action writes
exactly one immutable InventoryTransaction row, and receiving a purchase
order / completing a sales order are each atomic (all-or-nothing) and
idempotent (a second call is a no-op, not a second application)."""

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.models import Category, InventoryTransaction, Product, Supplier, TransactionType
from tests.conftest import login

pytestmark = pytest.mark.asyncio


@pytest.fixture()
def category_and_supplier(db_session: Session):
    category = Category(name="Txn Category")
    supplier = Supplier(name="Txn Supplier", email="txn-supplier@example.com")
    db_session.add_all([category, supplier])
    db_session.commit()
    return category, supplier


@pytest.fixture()
def product(db_session: Session, category_and_supplier):
    category, supplier = category_and_supplier
    p = Product(
        sku="TXN-001",
        name="Txn Product",
        cost_price=Decimal("10.00"),
        selling_price=Decimal("20.00"),
        current_stock=10,
        category_id=category.id,
        supplier_id=supplier.id,
    )
    db_session.add(p)
    db_session.commit()
    return p


async def test_receiving_a_purchase_order_writes_one_transaction_and_updates_stock(
    client: AsyncClient, db_session: Session, manager_user, product
):
    user, password = manager_user
    headers = await login(client, user.email, password)

    create_res = await client.post(
        "/purchase-orders",
        headers=headers,
        json={
            "supplier_id": str(product.supplier_id),
            "items": [{"product_id": str(product.id), "quantity": 5, "unit_cost": "10.00"}],
        },
    )
    assert create_res.status_code == 201
    po_id = create_res.json()["id"]

    receive_res = await client.post(f"/purchase-orders/{po_id}/receive", headers=headers)
    assert receive_res.status_code == 200
    assert receive_res.json()["status"] == "received"

    db_session.refresh(product)
    assert product.current_stock == 15

    txns = db_session.query(InventoryTransaction).filter(InventoryTransaction.reference_id == uuid.UUID(po_id)).all()
    assert len(txns) == 1
    assert txns[0].transaction_type == TransactionType.PURCHASE
    assert txns[0].quantity == 5


async def test_receiving_a_purchase_order_twice_is_a_no_op_the_second_time(
    client: AsyncClient, db_session: Session, manager_user, product
):
    user, password = manager_user
    headers = await login(client, user.email, password)

    create_res = await client.post(
        "/purchase-orders",
        headers=headers,
        json={
            "supplier_id": str(product.supplier_id),
            "items": [{"product_id": str(product.id), "quantity": 5, "unit_cost": "10.00"}],
        },
    )
    po_id = create_res.json()["id"]

    first = await client.post(f"/purchase-orders/{po_id}/receive", headers=headers)
    assert first.status_code == 200
    second = await client.post(f"/purchase-orders/{po_id}/receive", headers=headers)
    assert second.status_code == 409

    db_session.refresh(product)
    assert product.current_stock == 15  # not 20 - the second call changed nothing

    txns = db_session.query(InventoryTransaction).filter(InventoryTransaction.reference_id == uuid.UUID(po_id)).all()
    assert len(txns) == 1  # still exactly one row, not two


async def test_completing_a_sales_order_deducts_stock_and_writes_one_transaction(
    client: AsyncClient, db_session: Session, employee_user, product
):
    user, password = employee_user
    headers = await login(client, user.email, password)

    create_res = await client.post("/sales-orders", headers=headers, json={"items": [{"product_id": str(product.id), "quantity": 3}]})
    assert create_res.status_code == 201
    so_id = create_res.json()["id"]

    complete_res = await client.post(f"/sales-orders/{so_id}/complete", headers=headers)
    assert complete_res.status_code == 200
    body = complete_res.json()
    assert body["status"] == "completed"
    assert body["invoice_number"]

    db_session.refresh(product)
    assert product.current_stock == 7

    txns = db_session.query(InventoryTransaction).filter(InventoryTransaction.reference_id == uuid.UUID(so_id)).all()
    assert len(txns) == 1
    assert txns[0].transaction_type == TransactionType.SALE


async def test_completing_a_sales_order_with_insufficient_stock_changes_nothing(
    client: AsyncClient, db_session: Session, employee_user, product
):
    user, password = employee_user
    headers = await login(client, user.email, password)

    create_res = await client.post(
        "/sales-orders", headers=headers, json={"items": [{"product_id": str(product.id), "quantity": 999}]}
    )
    so_id = create_res.json()["id"]

    complete_res = await client.post(f"/sales-orders/{so_id}/complete", headers=headers)
    assert complete_res.status_code == 409

    db_session.refresh(product)
    assert product.current_stock == 10  # unchanged

    txns = db_session.query(InventoryTransaction).filter(InventoryTransaction.reference_id == uuid.UUID(so_id)).all()
    assert len(txns) == 0  # the failed attempt left no partial trace


async def test_inventory_transactions_have_no_write_route(client: AsyncClient, manager_user):
    """No PATCH/DELETE route exists on this resource at all - the audit
    trail can't be edited or erased once written, by construction. The
    frontend's StaticFiles mount at "/" catches any unmatched API path (it
    has to go last, see app/main.py), so a PATCH here surfaces as 405
    (method not allowed on the static route) rather than a plain 404."""
    user, password = manager_user
    headers = await login(client, user.email, password)
    res = await client.patch(f"/inventory-transactions/{uuid.uuid4()}", headers=headers, json={"quantity": 1})
    assert res.status_code in (404, 405)

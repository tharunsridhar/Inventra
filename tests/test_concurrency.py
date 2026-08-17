"""Proves the concurrency guarantee described in the README: receiving a
purchase order and completing a sales order are each atomic and idempotent
under concurrent requests.

Both tests fire two requests at the exact same row at the same time, over
TWO INDEPENDENT DB connections (the `live_client` fixture - see conftest.py),
so they exercise real Postgres row locking rather than just Python-level
concurrency. Before the SELECT ... FOR UPDATE locking added in the
concurrency-hardening pass (app/routers/purchases.py, sales.py), both
requests would read the pre-mutation row, both pass their status/stock
check, and both commit - doubling the stock increase / overselling the last
unit. Comment out `.with_for_update()` in either router and either test
below will fail, which is the proof the race existed and is now closed.
"""

import asyncio
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.models import (
    Category,
    InventoryTransaction,
    Notification,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseOrderStatus,
    RefreshToken,
    SalesOrder,
    SalesOrderItem,
    SalesOrderStatus,
    Supplier,
)
from tests.conftest import login, make_user

pytestmark = pytest.mark.asyncio


@pytest.fixture()
def manager(live_db_session: Session):
    user, password = make_user(live_db_session, "manager")
    live_db_session.commit()
    yield user.email, password
    # logging in left a RefreshToken row, and receiving/completing an order
    # notifies its creator - both reference this user by FK and have to go
    # before the user itself can be deleted
    live_db_session.query(RefreshToken).filter(RefreshToken.user_id == user.id).delete()
    live_db_session.query(Notification).filter(Notification.user_id == user.id).delete()
    live_db_session.delete(live_db_session.get(type(user), user.id))
    live_db_session.commit()


@pytest.fixture()
def category_and_supplier(live_db_session: Session):
    category = Category(name=f"Concurrency Category {id(object())}")
    supplier = Supplier(name="Concurrency Supplier", email=f"conc-supplier-{id(object())}@example.com")
    live_db_session.add_all([category, supplier])
    live_db_session.commit()
    yield category, supplier
    live_db_session.delete(category)
    live_db_session.delete(supplier)
    live_db_session.commit()


async def test_concurrent_purchase_order_receive_applies_stock_exactly_once(
    live_client: AsyncClient, live_db_session: Session, manager, category_and_supplier
):
    email, password = manager
    category, supplier = category_and_supplier
    headers = await login(live_client, email, password)

    product = Product(
        sku=f"CONC-PO-{id(object())}",
        name="Concurrency Widget",
        cost_price=Decimal("10.00"),
        selling_price=Decimal("20.00"),
        current_stock=0,
        category_id=category.id,
        supplier_id=supplier.id,
    )
    live_db_session.add(product)
    live_db_session.flush()
    po = PurchaseOrder(supplier_id=supplier.id, status=PurchaseOrderStatus.ORDERED)
    po.items = [PurchaseOrderItem(product_id=product.id, quantity=5, unit_cost=Decimal("10.00"))]
    live_db_session.add(po)
    live_db_session.commit()

    try:
        r1, r2 = await asyncio.gather(
            live_client.post(f"/purchase-orders/{po.id}/receive", headers=headers),
            live_client.post(f"/purchase-orders/{po.id}/receive", headers=headers),
        )

        # exactly one call wins the race, the other correctly sees "already received"
        assert sorted([r1.status_code, r2.status_code]) == [200, 409]

        live_db_session.expire_all()
        refreshed = live_db_session.get(Product, product.id)
        # 5, not 10 - the locked second request saw status=received and never
        # touched stock, instead of both requests applying +5
        assert refreshed.current_stock == 5
    finally:
        # the /receive call left an InventoryTransaction row referencing this
        # product - it has to go before the product can be deleted (FK)
        live_db_session.query(InventoryTransaction).filter(InventoryTransaction.product_id == product.id).delete()
        live_db_session.query(PurchaseOrderItem).filter(PurchaseOrderItem.purchase_order_id == po.id).delete()
        live_db_session.delete(po)
        live_db_session.delete(product)
        live_db_session.commit()


async def test_concurrent_sales_order_complete_never_oversells_last_unit(
    live_client: AsyncClient, live_db_session: Session, manager, category_and_supplier
):
    email, password = manager
    category, supplier = category_and_supplier
    headers = await login(live_client, email, password)

    product = Product(
        sku=f"CONC-SO-{id(object())}",
        name="Concurrency Gadget",
        cost_price=Decimal("10.00"),
        selling_price=Decimal("20.00"),
        current_stock=1,  # exactly one unit left - both requests are racing for it
        category_id=category.id,
        supplier_id=supplier.id,
    )
    live_db_session.add(product)
    live_db_session.flush()
    so = SalesOrder(status=SalesOrderStatus.CREATED)
    so.items = [SalesOrderItem(product_id=product.id, quantity=1, unit_price=Decimal("20.00"))]
    live_db_session.add(so)
    live_db_session.commit()

    try:
        r1, r2 = await asyncio.gather(
            live_client.post(f"/sales-orders/{so.id}/complete", headers=headers),
            live_client.post(f"/sales-orders/{so.id}/complete", headers=headers),
        )

        # exactly one call wins the race, the other correctly sees "already completed"
        assert sorted([r1.status_code, r2.status_code]) == [200, 409]

        live_db_session.expire_all()
        refreshed = live_db_session.get(Product, product.id)
        # 0, not -1 - the locked second request saw status=completed and never
        # touched stock, instead of both requests deducting the same last unit
        assert refreshed.current_stock == 0
    finally:
        # the /complete call left an InventoryTransaction row referencing this
        # product - it has to go before the product can be deleted (FK)
        live_db_session.query(InventoryTransaction).filter(InventoryTransaction.product_id == product.id).delete()
        live_db_session.query(SalesOrderItem).filter(SalesOrderItem.sales_order_id == so.id).delete()
        live_db_session.delete(so)
        live_db_session.delete(product)
        live_db_session.commit()

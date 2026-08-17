"""Role-based access control. Admin > Manager > Employee, enforced by
require_role() dependencies - every endpoint above the Employee floor should
403 a token that doesn't have the right role, and the role check happens
before the endpoint body runs (so it wins over a 404 for a resource that
doesn't even exist)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.models import Category, Supplier
from tests.conftest import login

pytestmark = pytest.mark.asyncio


@pytest.fixture()
def category_and_supplier(db_session: Session):
    category = Category(name="RBAC Category")
    supplier = Supplier(name="RBAC Supplier", email="rbac-supplier@example.com")
    db_session.add_all([category, supplier])
    db_session.commit()
    return category, supplier


async def test_employee_cannot_create_a_product(client: AsyncClient, employee_user, category_and_supplier):
    category, supplier = category_and_supplier
    user, password = employee_user
    headers = await login(client, user.email, password)
    res = await client.post(
        "/products",
        headers=headers,
        json={
            "sku": "RBAC-001",
            "name": "Forbidden Product",
            "cost_price": "10.00",
            "selling_price": "20.00",
            "category_id": str(category.id),
            "supplier_id": str(supplier.id),
        },
    )
    assert res.status_code == 403


async def test_manager_can_create_a_product(client: AsyncClient, manager_user, category_and_supplier):
    category, supplier = category_and_supplier
    user, password = manager_user
    headers = await login(client, user.email, password)
    res = await client.post(
        "/products",
        headers=headers,
        json={
            "sku": "RBAC-002",
            "name": "Allowed Product",
            "cost_price": "10.00",
            "selling_price": "20.00",
            "category_id": str(category.id),
            "supplier_id": str(supplier.id),
        },
    )
    assert res.status_code == 201


async def test_every_role_can_read_products(client: AsyncClient, admin_user, manager_user, employee_user):
    for user, password in (admin_user, manager_user, employee_user):
        headers = await login(client, user.email, password)
        res = await client.get("/products", headers=headers)
        assert res.status_code == 200


async def test_only_admin_can_list_users(client: AsyncClient, admin_user, manager_user, employee_user):
    admin_headers = await login(client, admin_user[0].email, admin_user[1])
    manager_headers = await login(client, manager_user[0].email, manager_user[1])
    employee_headers = await login(client, employee_user[0].email, employee_user[1])

    assert (await client.get("/users", headers=admin_headers)).status_code == 200
    assert (await client.get("/users", headers=manager_headers)).status_code == 403
    assert (await client.get("/users", headers=employee_headers)).status_code == 403


async def test_role_check_wins_over_not_found_for_a_nonexistent_resource(client: AsyncClient, employee_user):
    """An employee hitting a manager-only action on a return that doesn't
    even exist should get 403, not 404 - the endpoint shouldn't leak
    whether the resource exists to a caller who couldn't touch it anyway."""
    user, password = employee_user
    headers = await login(client, user.email, password)
    res = await client.patch(f"/returns/{uuid.uuid4()}/approve", headers=headers)
    assert res.status_code == 403


async def test_employee_can_create_sales_orders(client: AsyncClient, employee_user, category_and_supplier, db_session: Session):
    from decimal import Decimal

    from app.models import Product

    category, supplier = category_and_supplier
    product = Product(
        sku="RBAC-003",
        name="Sellable Product",
        cost_price=Decimal("10.00"),
        selling_price=Decimal("20.00"),
        current_stock=5,
        category_id=category.id,
        supplier_id=supplier.id,
    )
    db_session.add(product)
    db_session.commit()

    user, password = employee_user
    headers = await login(client, user.email, password)
    res = await client.post("/sales-orders", headers=headers, json={"items": [{"product_id": str(product.id), "quantity": 1}]})
    assert res.status_code == 201


async def test_no_token_is_rejected(client: AsyncClient):
    res = await client.get("/products")
    assert res.status_code in (401, 403)


async def test_garbage_token_is_rejected(client: AsyncClient):
    res = await client.get("/products", headers={"Authorization": "Bearer not-a-real-token"})
    assert res.status_code == 401

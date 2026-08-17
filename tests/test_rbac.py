"""Role-based access control. Admin > Manager > Employee, enforced by
permission_classes - every endpoint above the Employee floor should 403 a
token that doesn't have the right role."""

import pytest

from tests.conftest import auth_headers

pytestmark = pytest.mark.django_db


def test_employee_cannot_create_a_product(api_client, employee_user, category, supplier):
    res = api_client.post(
        "/products/",
        {"sku": "RBAC-001", "name": "Forbidden", "cost_price": "10.00", "selling_price": "20.00", "category": category.id, "supplier": supplier.id},
        **auth_headers(employee_user),
    )
    assert res.status_code == 403


def test_manager_can_create_a_product(api_client, manager_user, category, supplier):
    res = api_client.post(
        "/products/",
        {"sku": "RBAC-002", "name": "Allowed", "cost_price": "10.00", "selling_price": "20.00", "category": category.id, "supplier": supplier.id},
        **auth_headers(manager_user),
    )
    assert res.status_code == 201


def test_every_role_can_read_products(api_client, admin_user, manager_user, employee_user):
    for user in (admin_user, manager_user, employee_user):
        res = api_client.get("/products/", **auth_headers(user))
        assert res.status_code == 200


def test_only_admin_can_list_users(api_client, admin_user, manager_user, employee_user):
    assert api_client.get("/users/", **auth_headers(admin_user)).status_code == 200
    assert api_client.get("/users/", **auth_headers(manager_user)).status_code == 403
    assert api_client.get("/users/", **auth_headers(employee_user)).status_code == 403


def test_employee_can_create_sales_orders(api_client, employee_user, product):
    res = api_client.post("/sales-orders/", {"items": [{"product_id": str(product.id), "quantity": 1}]}, format="json", **auth_headers(employee_user))
    assert res.status_code == 201


def test_employee_cannot_receive_purchase_orders(api_client, employee_user, manager_user, supplier, product):
    po = api_client.post(
        "/purchase-orders/", {"supplier_id": str(supplier.id), "items": [{"product_id": str(product.id), "quantity": 5, "unit_cost": "10.00"}]},
        format="json", **auth_headers(manager_user),
    ).json()
    res = api_client.post(f"/purchase-orders/{po['id']}/receive/", **auth_headers(employee_user))
    assert res.status_code == 403


def test_no_token_is_rejected(api_client):
    res = api_client.get("/products/")
    assert res.status_code == 401


def test_garbage_token_is_rejected(api_client):
    res = api_client.get("/products/", HTTP_AUTHORIZATION="Bearer not-a-real-token")
    assert res.status_code == 401

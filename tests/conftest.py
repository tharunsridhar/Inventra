"""Shared fixtures. pytest-django's `db` fixture already gives every test a
transaction that's rolled back afterward (Django's own TestCase mechanism,
same isolation goal as the FastAPI port's SAVEPOINT-based db_session
fixture, just via the test framework Django ships with instead of hand-
rolled SQLAlchemy transaction nesting).

The concurrency tests need real cross-connection visibility, which a
rolled-back transaction can't give them - they opt into
`django_db(transaction=True)` + the `live_server` fixture instead (see
tests/test_concurrency.py), the same tradeoff the FastAPI port's
live_db_session/live_client fixtures make.
"""

import uuid

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import RoleName, User
from apps.catalog.models import Category, Product, Supplier


@pytest.fixture()
def api_client():
    return APIClient()


def _make_user(role):
    return User.objects.create_user(
        email=f"{role}-{uuid.uuid4().hex[:10]}@example.com",
        password="testpass123",
        full_name=role.title(),
        role=role,
    )


@pytest.fixture()
def admin_user(db):
    return _make_user(RoleName.ADMIN)


@pytest.fixture()
def manager_user(db):
    return _make_user(RoleName.MANAGER)


@pytest.fixture()
def employee_user(db):
    return _make_user(RoleName.EMPLOYEE)


def auth_headers(user) -> dict:
    token = RefreshToken.for_user(user).access_token
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@pytest.fixture()
def category(db):
    return Category.objects.create(name=f"Category {uuid.uuid4().hex[:8]}")


@pytest.fixture()
def supplier(db):
    return Supplier.objects.create(name="Test Supplier", email=f"supplier-{uuid.uuid4().hex[:8]}@example.com")


@pytest.fixture()
def product(db, category, supplier):
    return Product.objects.create(
        sku=f"SKU-{uuid.uuid4().hex[:8]}", name="Test Product", cost_price="10.00", selling_price="20.00",
        current_stock=10, category=category, supplier=supplier,
    )

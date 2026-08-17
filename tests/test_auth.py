"""Auth lifecycle: register, login, refresh, and refresh-token revocation on
logout. A revoked or unknown refresh token must never mint a new access
token - that's the entire point of storing refresh tokens in the DB instead
of trusting a long-lived JWT."""

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.models import RefreshToken
from tests.conftest import login, make_user

pytestmark = pytest.mark.asyncio


async def test_register_creates_an_employee_by_default(client: AsyncClient):
    res = await client.post(
        "/auth/register", json={"email": "newuser@example.com", "password": "password123", "full_name": "New User"}
    )
    assert res.status_code == 201
    body = res.json()
    assert body["role"] == "employee"
    assert body["email"] == "newuser@example.com"


async def test_register_rejects_a_duplicate_email(client: AsyncClient):
    payload = {"email": "dupe@example.com", "password": "password123", "full_name": "Dupe"}
    first = await client.post("/auth/register", json=payload)
    assert first.status_code == 201
    second = await client.post("/auth/register", json=payload)
    assert second.status_code == 409


async def test_login_rejects_wrong_password(client: AsyncClient, db_session: Session):
    user, _password = make_user(db_session, "employee")
    db_session.commit()
    res = await client.post("/auth/login", json={"email": user.email, "password": "wrong-password"})
    assert res.status_code == 401


async def test_login_issues_access_and_refresh_tokens(client: AsyncClient, employee_user):
    user, password = employee_user
    res = await client.post("/auth/login", json={"email": user.email, "password": password})
    assert res.status_code == 200
    body = res.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


async def test_me_requires_a_valid_access_token(client: AsyncClient, employee_user):
    user, password = employee_user
    headers = await login(client, user.email, password)
    res = await client.get("/auth/me", headers=headers)
    assert res.status_code == 200
    assert res.json()["email"] == user.email

    res_no_auth = await client.get("/auth/me")
    assert res_no_auth.status_code in (401, 403)  # HTTPBearer 403s when the header is missing entirely


async def test_invalid_access_token_is_rejected(client: AsyncClient):
    res = await client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert res.status_code == 401


async def test_refresh_issues_a_new_access_token(client: AsyncClient, employee_user):
    user, password = employee_user
    login_res = await client.post("/auth/login", json={"email": user.email, "password": password})
    refresh_token = login_res.json()["refresh_token"]

    res = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert res.status_code == 200
    assert res.json()["access_token"]


async def test_refresh_rejects_an_unknown_token(client: AsyncClient):
    res = await client.post("/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert res.status_code == 401


async def test_logout_revokes_the_refresh_token(client: AsyncClient, employee_user, db_session: Session):
    user, password = employee_user
    login_res = await client.post("/auth/login", json={"email": user.email, "password": password})
    refresh_token = login_res.json()["refresh_token"]

    logout_res = await client.post("/auth/logout", json={"refresh_token": refresh_token})
    assert logout_res.status_code == 204

    stored = db_session.query(RefreshToken).filter(RefreshToken.token == refresh_token).first()
    assert stored.revoked is True

    # a revoked refresh token can never be exchanged for a new access token again
    reuse_res = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert reuse_res.status_code == 401


async def test_disabled_user_cannot_authenticate(client: AsyncClient, db_session: Session):
    user, password = make_user(db_session, "employee")
    user.is_active = False
    db_session.commit()

    res = await client.post("/auth/login", json={"email": user.email, "password": password})
    assert res.status_code == 401

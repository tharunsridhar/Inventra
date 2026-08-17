"""Shared fixtures: a real PostgreSQL test database (created and dropped once
per test session), transactional rollback isolation between tests, an async
test client, and factory fixtures for one user per role.

Deliberately NOT SQLite - the whole point of the Postgres migration was
parity between dev/test and prod, so testing against SQLite here would just
reintroduce the gap this project spent Prompt 1.2 closing.
"""

import uuid
from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from alembic.config import Config as AlembicConfig
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.auth import hash_password
from app.config import settings
from app.database import get_db, seed_roles
from app.main import app
from app.models import Role, User


def _test_database_url() -> str:
    # str(url) / repr(url) mask the password as "***" by default (SQLAlchemy's
    # render_as_string(hide_password=True)) - fine for logging, but this string
    # is actually used to open connections, so the real password must survive.
    url = make_url(settings.database_url)
    test_db_name = (url.database or "inventra") + "_test"
    return url.set(database=test_db_name).render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def test_db_url() -> str:
    return _test_database_url()


@pytest.fixture(scope="session")
def _test_database(test_db_url: str) -> Generator[None, None, None]:
    """Create the test database fresh, run every Alembic migration against
    it (this is also, incidentally, the migration chain's own test - if a
    revision is broken, the suite fails before a single test runs), then
    drop it once the whole session is done."""
    target = make_url(test_db_url)
    admin_url = target.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{target.database}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    admin_engine.dispose()

    alembic_cfg = AlembicConfig("alembic.ini")
    # alembic/env.py prefers this over settings.database_url when present -
    # set_main_option() alone isn't enough, env.py overwrites it otherwise.
    alembic_cfg.attributes["sqlalchemy_url"] = test_db_url
    command.upgrade(alembic_cfg, "head")

    yield

    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{target.database}" WITH (FORCE)'))
    admin_engine.dispose()


@pytest.fixture(scope="session")
def engine(test_db_url: str, _test_database: None) -> Generator[Engine, None, None]:
    eng = create_engine(test_db_url, pool_pre_ping=True)
    yield eng
    eng.dispose()


@pytest.fixture()
def db_session(engine: Engine) -> Generator[Session, None, None]:
    """One test = one outer transaction that's always rolled back at the end,
    even though the route handlers under test call session.commit(). SQLAlchemy's
    join_transaction_mode="create_savepoint" wraps each of those commits in a
    SAVEPOINT instead of really ending the outer transaction, so nothing this
    fixture touches is ever actually persisted - that's what gives every test
    a clean, isolated database without paying for a real create/drop per test."""
    connection = engine.connect()
    outer_transaction = connection.begin()
    TestSession = sessionmaker(bind=connection, join_transaction_mode="create_savepoint")
    session = TestSession()

    yield session

    session.close()
    outer_transaction.rollback()
    connection.close()


@pytest.fixture()
def _seeded_roles(db_session: Session) -> None:
    """In production, app.main's lifespan seeds the 3 fixed roles on startup.
    httpx's ASGITransport never runs that lifespan, and db_session's rollback
    means nothing persists between tests anyway - so every db_session-based
    test needs this redone itself, same as a fresh real deployment would on
    its first boot.

    Deliberately NOT autouse: db_session's role-seeding INSERT stays open
    (uncommitted at the real Postgres level - that's the whole point of the
    savepoint-rollback pattern) for the entire test. A concurrency test's
    live_db_session-based fixtures seed roles on a SEPARATE, real connection;
    if this ran for every test regardless, that second INSERT would block on
    the unique constraint waiting for the first transaction to resolve - which
    it only does at teardown, after the (stuck) test would already need to
    have finished. That's a real deadlock, not a hypothetical one: it's what
    happened before this fixture was scoped down to `client` only. Tests that
    seed their own roles via live_db_session (see test_concurrency.py) don't
    request this fixture and never hit it."""
    seed_roles(db_session)


@pytest.fixture()
def live_db_session(engine: Engine) -> Generator[Session, None, None]:
    """A real, committing session - not wrapped in a rolled-back transaction.
    Only for tests that need their data to actually be visible to OTHER
    connections (the concurrency tests, which drive two requests over two
    separate DB connections at once). Clean up whatever you create."""
    LiveSession = sessionmaker(bind=engine)
    db = LiveSession()
    yield db
    db.close()


@pytest_asyncio.fixture()
async def client(db_session: Session, _seeded_roles: None) -> AsyncGenerator[AsyncClient, None]:
    """Async client whose requests all run inside db_session's rolled-back
    transaction. Use this for anything that shouldn't leave data behind."""

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture()
async def live_client(engine: Engine) -> AsyncGenerator[AsyncClient, None]:
    """Async client where each request gets its own real, committing session
    against the test database - same lifecycle as production's get_db(). The
    rolled-back `client` fixture can't exercise real row locking or cross-
    connection visibility, because it's all one connection; this can."""
    LiveSession = sessionmaker(bind=engine)

    def _override_get_db():
        db = LiveSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


def _get_or_create_role(db: Session, name: str) -> Role:
    role = db.query(Role).filter(Role.name == name).first()
    if role is None:
        role = Role(name=name, description=name)
        db.add(role)
        db.flush()
    return role


def make_user(db: Session, role_name: str, *, password: str = "testpass123") -> tuple[User, str]:
    """Create a user with a fresh unique email for the given role. Returns
    (user, plaintext_password) - the plaintext is only ever needed to log in."""
    role = _get_or_create_role(db, role_name)
    email = f"{role_name}-{uuid.uuid4().hex[:10]}@example.com"
    user = User(email=email, hashed_password=hash_password(password), full_name=role_name.title(), role_id=role.id)
    db.add(user)
    db.flush()
    return user, password


@pytest.fixture()
def admin_user(db_session: Session) -> tuple[User, str]:
    user, password = make_user(db_session, "admin")
    db_session.commit()
    return user, password


@pytest.fixture()
def manager_user(db_session: Session) -> tuple[User, str]:
    user, password = make_user(db_session, "manager")
    db_session.commit()
    return user, password


@pytest.fixture()
def employee_user(db_session: Session) -> tuple[User, str]:
    user, password = make_user(db_session, "employee")
    db_session.commit()
    return user, password


async def login(client: AsyncClient, email: str, password: str) -> dict[str, str]:
    """Log in and return an Authorization header ready to pass to client.get/post/etc."""
    res = await client.post("/auth/login", json={"email": email, "password": password})
    res.raise_for_status()
    return {"Authorization": f"Bearer {res.json()['access_token']}"}

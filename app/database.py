from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# pool_size + max_overflow: up to 15 concurrent connections from one app
# instance before requests start queuing - fine for a single-instance
# deployment, revisit if you run multiple replicas against the same DB.
# pool_timeout: fail fast (30s) instead of hanging forever when the pool
# is exhausted.
# pool_recycle: recycle connections every 30 min so we never hand out one
# that a managed Postgres provider (Railway, RDS, etc.) has silently closed
# for being idle too long.
# pool_pre_ping: issue a cheap SELECT 1 before handing out a pooled
# connection, so a dead connection surfaces as a quick reconnect instead of
# a mid-request "server closed the connection unexpectedly".
engine = create_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=settings.db_pool_recycle,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def seed_roles(db: Session) -> None:
    """Make sure the 3 fixed roles exist. Runs on every startup, just skips
    if they're already there."""
    from app.models import Role

    existing_names = [r.name for r in db.query(Role).all()]

    roles_to_add = [
        ("admin", "Full access, including user management"),
        ("manager", "Manages products, suppliers, purchases, sales, categories, returns, damage"),
        ("employee", "Can view products and create sales only"),
    ]
    for name, description in roles_to_add:
        if name not in existing_names:
            db.add(Role(name=name, description=description))
    db.commit()

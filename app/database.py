from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import DATABASE_URL

# SQLite needs this for a multi-request app (only one thread touches a
# connection at a time normally, FastAPI's dependency system works around that)
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


# SQLite has foreign keys OFF by default, have to turn it on ourselves
if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(Engine, "connect")
    def _turn_on_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


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

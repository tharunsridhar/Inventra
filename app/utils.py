from datetime import datetime, timezone


def now() -> datetime:
    """Just datetime.utcnow() basically, but without the deprecation warning.
    We keep everything naive/UTC because SQLite doesn't really store timezone
    info anyway."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def notify(db, user_id, ntype, message, reference_id=None):
    """Add a notification row for one user. Doesn't commit - whoever called
    this is usually in the middle of a bigger save and will commit at the end."""
    from app.models import Notification

    db.add(Notification(user_id=user_id, type=ntype, message=message, reference_id=reference_id))


def notify_admins_and_managers(db, ntype, message, reference_id=None):
    from app.models import Role, User

    users = (
        db.query(User)
        .join(Role, User.role_id == Role.id)
        .filter(User.is_active.is_(True), Role.name.in_(["admin", "manager"]))
        .all()
    )
    for user in users:
        notify(db, user.id, ntype, message, reference_id)


def check_and_notify_stock(db, product):
    """Call this right after changing product.current_stock."""
    from app.models import NotificationType

    if product.current_stock <= 0:
        notify_admins_and_managers(
            db, NotificationType.OUT_OF_STOCK, f"{product.name} ({product.sku}) is out of stock", product.id
        )
    elif product.current_stock <= product.low_stock_threshold:
        notify_admins_and_managers(
            db,
            NotificationType.LOW_STOCK,
            f"{product.name} ({product.sku}) is low on stock ({product.current_stock} left)",
            product.id,
        )

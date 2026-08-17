"""Small helpers used by apps.inventory's stock-mutation views - ported
directly from Inventra's app/utils.py notify()/notify_admins_and_managers()."""

from apps.notifications.models import Notification


def notify(user_id, ntype, message, reference_id=None):
    Notification.objects.create(user_id=user_id, type=ntype, message=message, reference_id=reference_id)


def notify_admins_and_managers(ntype, message, reference_id=None):
    from apps.accounts.models import RoleName, User

    user_ids = User.objects.filter(is_active=True, role__in=[RoleName.ADMIN, RoleName.MANAGER]).values_list("id", flat=True)
    Notification.objects.bulk_create([
        Notification(user_id=uid, type=ntype, message=message, reference_id=reference_id) for uid in user_ids
    ])

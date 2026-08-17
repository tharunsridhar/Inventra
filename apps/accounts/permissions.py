"""DRF permission classes: the equivalent of Inventra's `require_role(*roles)`
FastAPI dependency factory. FastAPI expressed this as a Depends() callable
checking role membership per-route; DRF expresses the same idea as a class
with a has_permission() method, referenced in a ViewSet's
`permission_classes`. Same guarantee, different shape - a class attribute
instead of a per-route dependency list."""

from rest_framework.permissions import BasePermission

from apps.accounts.models import RoleName


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == RoleName.ADMIN)


class IsManagerOrAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in (RoleName.ADMIN, RoleName.MANAGER)
        )


class IsAnyRole(BasePermission):
    """Admin, Manager, or Employee - i.e. just "authenticated". Named to
    mirror Inventra's can_sell = require_role("admin", "manager", "employee")
    rather than relying on the DRF default IsAuthenticated implicitly."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

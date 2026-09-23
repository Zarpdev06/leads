"""Role based permissions.

Roles (accounts.User.Role): ADMIN > MANAGER > AGENT > VIEWER.
Writes require AGENT+, destructive/admin configuration requires ADMIN.
"""
from rest_framework.permissions import BasePermission

ROLE_RANK = {"VIEWER": 1, "AGENT": 2, "MANAGER": 3, "ADMIN": 4}


def _rank(user) -> int:
    if not user or not user.is_authenticated:
        return 0
    role = getattr(user, "role", None) or "VIEWER"
    return ROLE_RANK.get(role, 1)


class IsAdminRole(BasePermission):
    message = "Administrator role required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and (request.user.is_superuser or _rank(request.user) >= 4))


class IsManagerOrAdmin(BasePermission):
    message = "Manager or administrator role required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and (request.user.is_superuser or _rank(request.user) >= 3))


class CanModify(BasePermission):
    """Write operations require AGENT or higher; reads are allowed for VIEWER."""

    message = "Your role does not allow this operation."

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return bool(request.user and request.user.is_authenticated
                    and (request.user.is_superuser or _rank(request.user) >= 2))

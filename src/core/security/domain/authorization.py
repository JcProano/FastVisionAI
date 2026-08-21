"""Pure role-based access-control policy."""

from __future__ import annotations

from .models import (
    AuthorizationPermission as Permission,
    AuthorizationReason,
    AuthorizationResult,
    UserRole,
)

_OPERATOR = {
    Permission.VIEW_DASHBOARD,
    Permission.VIEW_PEOPLE,
    Permission.EDIT_PERSON,
    Permission.CHANGE_PERSON_STATUS,
    Permission.ENROLL_PERSON,
    Permission.VIEW_REPORTS,
    Permission.VIEW_ATTENDANCE,
    Permission.MANUAL_ATTENDANCE,
    Permission.VIEW_DETECTION_HISTORY,
    Permission.APPLICATION_EXIT,
    Permission.VIEW_SYSTEM_HEALTH,
}
_AUDITOR = {
    Permission.VIEW_DASHBOARD,
    Permission.VIEW_PEOPLE,
    Permission.VIEW_REPORTS,
    Permission.EXPORT_REPORTS,
    Permission.VIEW_ATTENDANCE,
    Permission.VIEW_DETECTION_HISTORY,
    Permission.VIEW_AUDIT,
    Permission.EXPORT_AUDIT,
    Permission.APPLICATION_EXIT,
    Permission.VIEW_SYSTEM_HEALTH,
}
_VIEWER = {
    Permission.VIEW_DASHBOARD,
    Permission.VIEW_PEOPLE,
    Permission.VIEW_REPORTS,
    Permission.VIEW_ATTENDANCE,
    Permission.VIEW_DETECTION_HISTORY,
    Permission.APPLICATION_EXIT,
    Permission.VIEW_SYSTEM_HEALTH,
}

ROLE_PERMISSIONS = {
    UserRole.ADMIN: frozenset(Permission),
    UserRole.OPERATOR: frozenset(_OPERATOR),
    UserRole.AUDITOR: frozenset(_AUDITOR),
    UserRole.VIEWER: frozenset(_VIEWER),
}


def evaluate_permission(
    role: object, permission: object, *, enabled: bool = True
) -> AuthorizationResult:
    role_text = (
        role.value
        if isinstance(role, UserRole)
        else str(role)
        if role is not None
        else None
    )
    permission_text = (
        permission.value
        if isinstance(permission, Permission)
        else str(permission)
        if permission is not None
        else None
    )
    if not enabled:
        return AuthorizationResult(
            False,
            True,
            role_text,
            permission_text,
            AuthorizationReason.AUTHORIZATION_DISABLED,
        )
    try:
        valid_role = role if isinstance(role, UserRole) else UserRole(role)
    except Exception:
        return AuthorizationResult(
            True,
            False,
            role_text,
            permission_text,
            AuthorizationReason.UNKNOWN_ROLE,
        )
    try:
        valid_permission = (
            permission
            if isinstance(permission, Permission)
            else Permission(permission)
        )
    except Exception:
        return AuthorizationResult(
            True,
            False,
            valid_role.value,
            permission_text,
            AuthorizationReason.UNKNOWN_PERMISSION,
        )
    allowed = valid_permission in ROLE_PERMISSIONS[valid_role]
    return AuthorizationResult(
        True,
        allowed,
        valid_role.value,
        valid_permission.value,
        AuthorizationReason.AUTHORIZED
        if allowed
        else AuthorizationReason.PERMISSION_DENIED,
    )

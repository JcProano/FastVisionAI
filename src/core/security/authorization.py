"""Stateless deterministic RBAC engine."""
from __future__ import annotations
from .contracts import AuthorizationPermission as P, AuthorizationReason, AuthorizationResult, UserRole

_OPERATOR = {P.VIEW_DASHBOARD,P.VIEW_PEOPLE,P.EDIT_PERSON,P.CHANGE_PERSON_STATUS,P.ENROLL_PERSON,P.VIEW_REPORTS,P.VIEW_ATTENDANCE,P.MANUAL_ATTENDANCE,P.VIEW_DETECTION_HISTORY,P.APPLICATION_EXIT,P.VIEW_SYSTEM_HEALTH}
_AUDITOR = {P.VIEW_DASHBOARD,P.VIEW_PEOPLE,P.VIEW_REPORTS,P.EXPORT_REPORTS,P.VIEW_ATTENDANCE,P.VIEW_DETECTION_HISTORY,P.VIEW_AUDIT,P.EXPORT_AUDIT,P.APPLICATION_EXIT,P.VIEW_SYSTEM_HEALTH}
_VIEWER = {P.VIEW_DASHBOARD,P.VIEW_PEOPLE,P.VIEW_REPORTS,P.VIEW_ATTENDANCE,P.VIEW_DETECTION_HISTORY,P.APPLICATION_EXIT,P.VIEW_SYSTEM_HEALTH}
ROLE_PERMISSIONS = {UserRole.ADMIN: frozenset(P), UserRole.OPERATOR:frozenset(_OPERATOR), UserRole.AUDITOR:frozenset(_AUDITOR), UserRole.VIEWER:frozenset(_VIEWER)}

class AuthorizationEngine:
    def __init__(self, *, enabled: bool = True) -> None: self.enabled=enabled
    def evaluate(self, role, permission) -> AuthorizationResult:
        role_text = role.value if isinstance(role,UserRole) else str(role) if role is not None else None
        permission_text = permission.value if isinstance(permission,P) else str(permission) if permission is not None else None
        if not self.enabled:
            return AuthorizationResult(False,True,role_text,permission_text,AuthorizationReason.AUTHORIZATION_DISABLED)
        try: valid_role=role if isinstance(role,UserRole) else UserRole(role)
        except Exception: return AuthorizationResult(True,False,role_text,permission_text,AuthorizationReason.UNKNOWN_ROLE)
        try: valid_permission=permission if isinstance(permission,P) else P(permission)
        except Exception: return AuthorizationResult(True,False,valid_role.value,permission_text,AuthorizationReason.UNKNOWN_PERMISSION)
        allowed=valid_permission in ROLE_PERMISSIONS[valid_role]
        return AuthorizationResult(True,allowed,valid_role.value,valid_permission.value,AuthorizationReason.AUTHORIZED if allowed else AuthorizationReason.PERMISSION_DENIED)

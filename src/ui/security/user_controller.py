"""Authorized administrative user management boundary."""
from __future__ import annotations
import uuid
from src.core.security import AuthorizationPermission as P, PasswordHasher, UserCreateRequest,UserRepository,UserRole,UserStatus,UserUpdateRequest
from .contracts import UserSummaryDTO
from .controller import AuthorizationController

class UserManagementController:
 def __init__(self,repository:UserRepository,hasher:PasswordHasher,authorization:AuthorizationController,audit_callback=None):self.repository=repository;self.hasher=hasher;self.authorization=authorization;self.audit_callback=audit_callback
 def _require(self):
  if not self.authorization.can(P.MANAGE_USERS):raise PermissionError("operation is not authorized")
 def list_users(self):self._require();return tuple(UserSummaryDTO(u.user_id,u.username,u.display_name,u.role.value,u.status.value,u.last_login_at.isoformat() if u.last_login_at else None) for u in self.repository.list_users())
 def create(self,username,display_name,password,role):
  self._require();result=self.repository.create_user(UserCreateRequest(str(uuid.uuid4()),username,display_name,UserRole(role)),self.hasher.hash_password(password));self._audit("USER_CREATED",{"user_id":result.user_id});return result
 def update(self,user_id,display_name=None,role=None):
  self._require();before=self.repository.get_by_user_id(user_id);result=self.repository.update_user(UserUpdateRequest(user_id,display_name,UserRole(role) if role else None));self._audit("USER_ROLE_CHANGED" if role and before and before.role!=result.role else "USER_UPDATED",{"user_id":user_id});return result
 def set_status(self,user_id,status):
  self._require();current=self.authorization.sessions.current()
  target=UserStatus(status)
  if current and current.user_id==user_id and target is UserStatus.DISABLED:raise PermissionError("self-disable is not allowed")
  result=self.repository.set_status(user_id,target);self._audit("USER_DISABLED" if target is UserStatus.DISABLED else "USER_ENABLED",{"user_id":user_id});return result
 def reset_password(self,user_id,new_password):self._require();self.repository.change_password_hash(user_id,self.hasher.hash_password(new_password));self._audit("PASSWORD_RESET",{"user_id":user_id})
 def _audit(self,event,payload):
  if self.audit_callback:
   try:self.audit_callback(event,payload)
   except Exception:pass

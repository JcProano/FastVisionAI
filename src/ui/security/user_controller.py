"""Authorized administrative user management boundary."""
from __future__ import annotations
import uuid
from src.core.security import AuthorizationPermission as P, PasswordHasher, UserCreateRequest,UserRepository,UserRole,UserStatus,UserUpdateRequest
from .contracts import UserSummaryDTO
from .controller import AuthorizationController

class UserManagementController:
 def __init__(self,repository:UserRepository,hasher:PasswordHasher,authorization:AuthorizationController):self.repository=repository;self.hasher=hasher;self.authorization=authorization
 def _require(self):
  if not self.authorization.can(P.MANAGE_USERS):raise PermissionError("operation is not authorized")
 def list_users(self):self._require();return tuple(UserSummaryDTO(u.user_id,u.username,u.display_name,u.role.value,u.status.value,u.last_login_at.isoformat() if u.last_login_at else None) for u in self.repository.list_users())
 def create(self,username,display_name,password,role):self._require();return self.repository.create_user(UserCreateRequest(str(uuid.uuid4()),username,display_name,UserRole(role)),self.hasher.hash_password(password))
 def update(self,user_id,display_name=None,role=None):self._require();return self.repository.update_user(UserUpdateRequest(user_id,display_name,UserRole(role) if role else None))
 def set_status(self,user_id,status):
  self._require();current=self.authorization.sessions.current()
  target=UserStatus(status)
  if current and current.user_id==user_id and target is UserStatus.DISABLED:raise PermissionError("self-disable is not allowed")
  return self.repository.set_status(user_id,target)
 def reset_password(self,user_id,new_password):self._require();self.repository.change_password_hash(user_id,self.hasher.hash_password(new_password))

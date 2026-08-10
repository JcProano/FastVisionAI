"""UI boundary for authentication, session timeout and authorization."""
from __future__ import annotations
from collections.abc import Callable
import uuid
from src.core.security import (
 AuthenticationRequest, AuthenticationService, AuthenticatedSessionManager,
 AuthorizationEngine, AuthorizationPermission, AuthorizationReason,
 AuthorizationResult, UserCreateRequest, UserRole,
)
from .contracts import LoginResultDTO,SecurityStatusDTO,SecurityUIState

class AuthorizationController:
 def __init__(self,engine:AuthorizationEngine,sessions:AuthenticatedSessionManager,*,enabled:bool=True): self.engine=engine;self.sessions=sessions;self.enabled=enabled
 def require(self,permission:AuthorizationPermission)->AuthorizationResult:
  if not self.enabled:return self.engine.evaluate(UserRole.ADMIN,permission)
  context=self.sessions.context()
  if not context.authenticated:return AuthorizationResult(True,False,None,permission.value,AuthorizationReason.NOT_AUTHENTICATED)
  return self.engine.evaluate(context.role,permission)
 def can(self,permission:AuthorizationPermission)->bool:return self.require(permission).allowed

class SecurityController:
 def __init__(self,authentication:AuthenticationService,sessions:AuthenticatedSessionManager,authorization:AuthorizationController,*,enabled:bool=True,bootstrap_enabled:bool=True,audit_callback:Callable[[str,dict[str,str]],None]|None=None):
  self.authentication=authentication;self.sessions=sessions;self.authorization=authorization;self.enabled=enabled;self.bootstrap_enabled=bootstrap_enabled;self.audit_callback=audit_callback;self.timeout_pending=False
 def needs_bootstrap(self)->bool:return self.enabled and self.authentication.repository.count_users()==0
 def bootstrap(self,username:str,display_name:str,password:str,confirmation:str)->LoginResultDTO:
  if not self.bootstrap_enabled or not self.needs_bootstrap():return LoginResultDTO(False,"El bootstrap no está disponible.",SecurityUIState.ERROR)
  if password!=confirmation:return LoginResultDTO(False,"Las contraseñas no coinciden.",SecurityUIState.BOOTSTRAP)
  result=self.authentication.bootstrap_admin(UserCreateRequest(str(uuid.uuid4()),username,display_name,UserRole.ADMIN),password)
  return self._accept(result)
 def login(self,username:str,password:str)->LoginResultDTO:return self._accept(self.authentication.authenticate(AuthenticationRequest(username,password)))
 def change_own_password(self,current_password:str,new_password:str)->bool:
  current=self.sessions.current()
  if current is None:return False
  verified=self.authentication.authenticate(AuthenticationRequest(current.username,current_password))
  if not verified.success or verified.user is None or verified.user.user_id!=current.user_id:return False
  self.authentication.change_password(current.user_id,new_password);self.sessions.touch();self._audit("PASSWORD_CHANGED",{"user_id":current.user_id});return True
 def _accept(self,result)->LoginResultDTO:
  if not result.success or result.user is None:
   self._audit("LOGIN_FAILURE",{});return LoginResultDTO(False,result.message,SecurityUIState.LOGIN)
  self.sessions.start(result.user);self.timeout_pending=False;self._audit("LOGIN_SUCCESS",{"user_id":result.user.user_id})
  return LoginResultDTO(True,result.message,SecurityUIState.AUTHENTICATED,result.user.display_name,result.user.role.value)
 def note_activity(self):
  if self.enabled:self.sessions.touch()
 def check_timeout(self,*,enrollment_active:bool=False)->SecurityStatusDTO:
  if not self.enabled:return self.status()
  if self.sessions.is_idle_expired():
   if enrollment_active:self.timeout_pending=True
   else:self.logout()
  elif self.timeout_pending and not enrollment_active:self.logout()
  return self.status()
 def logout(self):self.sessions.logout();self.timeout_pending=False;self._audit("LOGOUT",{})
 def status(self):
  current=self.sessions.current(); state=SecurityUIState.TIMEOUT_PENDING if self.timeout_pending else SecurityUIState.AUTHENTICATED if current else SecurityUIState.LOGGED_OUT
  return SecurityStatusDTO(self.enabled,current is not None,state,current.display_name if current else None,current.role.value if current else None,self.timeout_pending)
 def _audit(self,event,payload):
  if self.audit_callback:
   try:self.audit_callback(event,payload)
   except Exception:pass

"""In-memory authenticated operator session manager."""
from __future__ import annotations
import threading, uuid
from datetime import datetime, timedelta, timezone
from .contracts import AuthenticatedSessionDTO, AuthorizationContext, UserDTO

class AuthenticatedSessionManager:
    def __init__(self, idle_timeout_seconds: float=1800, *, now=None) -> None:
        if idle_timeout_seconds <= 0: raise ValueError("idle timeout must be positive")
        self.idle_timeout_seconds=idle_timeout_seconds; self._now=now or (lambda:datetime.now(timezone.utc)); self._session=None; self._lock=threading.RLock()
    def start(self,user:UserDTO)->AuthenticatedSessionDTO:
        now=self._now(); session=AuthenticatedSessionDTO(str(uuid.uuid4()),user.user_id,user.username,user.display_name,user.role,now,now)
        with self._lock: self._session=session
        return session
    def current(self)->AuthenticatedSessionDTO|None:
        with self._lock: return self._session
    def touch(self)->AuthenticatedSessionDTO|None:
        with self._lock:
            if self._session is None:return None
            s=self._session; self._session=AuthenticatedSessionDTO(s.session_id,s.user_id,s.username,s.display_name,s.role,s.authenticated_at,self._now()); return self._session
    def logout(self)->None:
        with self._lock:self._session=None
    def is_idle_expired(self)->bool:
        with self._lock:
            return self._session is not None and self._now()-self._session.last_activity_at >= timedelta(seconds=self.idle_timeout_seconds)
    def context(self)->AuthorizationContext:
        with self._lock:
            s=self._session
            return AuthorizationContext(None,None,False,None) if s is None else AuthorizationContext(s.user_id,s.role,True,s.session_id)

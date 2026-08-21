"""Bounded, expiring CSRF sessions for the embedded web adapter."""

from __future__ import annotations

import secrets
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, replace
from typing import Callable


@dataclass(frozen=True, slots=True)
class WebSession:
    session_id: str
    csrf_token: str
    created_at: float
    last_activity_at: float


class InMemoryWebSessionStore:
    """Keep only short-lived browser sessions; never stores credentials."""

    def __init__(
        self,
        *,
        ttl_seconds: float = 3600,
        maximum_sessions: int = 128,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("web session TTL must be positive")
        if maximum_sessions <= 0:
            raise ValueError("web session limit must be positive")
        self.ttl_seconds = float(ttl_seconds)
        self.maximum_sessions = int(maximum_sessions)
        self._monotonic = monotonic
        self._sessions: OrderedDict[str, WebSession] = OrderedDict()
        self._lock = threading.RLock()

    def issue(self) -> WebSession:
        now = self._monotonic()
        with self._lock:
            self._prune(now)
            while len(self._sessions) >= self.maximum_sessions:
                self._sessions.popitem(last=False)
            session = WebSession(
                secrets.token_urlsafe(24),
                secrets.token_urlsafe(32),
                now,
                now,
            )
            self._sessions[session.session_id] = session
            return session

    def validate(self, session_id: str | None, csrf_token: str | None) -> bool:
        if not session_id or not csrf_token:
            return False
        now = self._monotonic()
        with self._lock:
            self._prune(now)
            session = self._sessions.get(session_id)
            if session is None or not secrets.compare_digest(
                csrf_token, session.csrf_token
            ):
                return False
            refreshed = replace(session, last_activity_at=now)
            self._sessions[session_id] = refreshed
            self._sessions.move_to_end(session_id)
            return True

    def revoke(self, session_id: str | None) -> None:
        if not session_id:
            return
        with self._lock:
            self._sessions.pop(session_id, None)

    def close(self) -> None:
        with self._lock:
            self._sessions.clear()

    def _prune(self, now: float) -> None:
        expired = tuple(
            session_id
            for session_id, session in self._sessions.items()
            if now - session.last_activity_at >= self.ttl_seconds
        )
        for session_id in expired:
            self._sessions.pop(session_id, None)

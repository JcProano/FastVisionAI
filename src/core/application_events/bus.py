"""Thread-safe synchronous application event bus with isolated subscribers."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

from .contracts import ApplicationEvent

LOGGER = logging.getLogger(__name__)
EventHandler = Callable[[ApplicationEvent], None]


@dataclass(frozen=True, slots=True)
class SubscriptionToken:
    value: str


@dataclass(frozen=True, slots=True)
class _Subscription:
    token: SubscriptionToken
    event_type: type[ApplicationEvent]
    handler: EventHandler
    order: int


class ApplicationEventBus:
    def __init__(self, *, enabled: bool = True, max_publish_depth: int = 32) -> None:
        if max_publish_depth <= 0:
            raise ValueError("max_publish_depth must be positive")
        self.enabled = enabled
        self.max_publish_depth = max_publish_depth
        self._subscriptions: dict[SubscriptionToken, _Subscription] = {}
        self._next_order = 0
        self._lock = threading.RLock()
        self._local = threading.local()

    def subscribe(
        self, event_type: type[ApplicationEvent], handler: EventHandler,
    ) -> SubscriptionToken:
        if not isinstance(event_type, type) or not issubclass(event_type, ApplicationEvent):
            raise TypeError("event_type must derive from ApplicationEvent")
        if not callable(handler):
            raise TypeError("handler must be callable")
        token = SubscriptionToken(str(uuid4()))
        with self._lock:
            item = _Subscription(token, event_type, handler, self._next_order)
            self._next_order += 1
            self._subscriptions[token] = item
        return token

    def unsubscribe(self, token: SubscriptionToken) -> bool:
        with self._lock:
            return self._subscriptions.pop(token, None) is not None

    def publish(self, event: ApplicationEvent) -> int:
        if not isinstance(event, ApplicationEvent):
            raise TypeError("event must derive from ApplicationEvent")
        if not self.enabled:
            return 0
        depth = int(getattr(self._local, "depth", 0))
        if depth >= self.max_publish_depth:
            LOGGER.warning("Application event publish depth exceeded; event_type=%s",
                           event.event_type)
            return 0
        with self._lock:
            subscribers = tuple(sorted(
                (item for item in self._subscriptions.values()
                 if isinstance(event, item.event_type)),
                key=lambda item: item.order,
            ))
        self._local.depth = depth + 1
        try:
            for item in subscribers:
                try:
                    item.handler(event)
                except Exception as exc:
                    LOGGER.error(
                        "Application event subscriber failed safely; event_type=%s "
                        "handler_type=%s exception_type=%s",
                        event.event_type, type(item.handler).__name__, type(exc).__name__,
                    )
        finally:
            self._local.depth = depth
        return len(subscribers)

    def clear(self) -> None:
        with self._lock:
            self._subscriptions.clear()

    def subscriber_count(
        self, event_type: type[ApplicationEvent] | None = None,
    ) -> int:
        with self._lock:
            if event_type is None:
                return len(self._subscriptions)
            return sum(item.event_type is event_type
                       for item in self._subscriptions.values())


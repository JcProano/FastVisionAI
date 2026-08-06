from __future__ import annotations

import logging
from collections import defaultdict
from typing import Callable, Protocol, TypeVar, runtime_checkable

from src.engine.events.contracts import Event

LOGGER = logging.getLogger(__name__)
EventT = TypeVar("EventT", bound=Event)


@runtime_checkable
class InternalEventBus(Protocol):
    def publish(self, event: Event) -> int: ...
    def subscribe(self, event_type: type[EventT], handler: Callable[[EventT], None]) -> bool: ...
    def unsubscribe(self, event_type: type[EventT], handler: Callable[[EventT], None]) -> bool: ...


@runtime_checkable
class ExternalEventBus(Protocol):
    def publish(self, event: Event) -> int: ...
    def subscribe(self, event_type: type[EventT], handler: Callable[[EventT], None]) -> bool: ...
    def unsubscribe(self, event_type: type[EventT], handler: Callable[[EventT], None]) -> bool: ...


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[type[Event], list[Callable[[Event], None]]] = defaultdict(list)

    def subscribe(self, event_type, handler) -> bool:
        if handler in self._handlers[event_type]:
            return False
        self._handlers[event_type].append(handler)
        return True

    def unsubscribe(self, event_type, handler) -> bool:
        try:
            self._handlers[event_type].remove(handler)
            return True
        except (KeyError, ValueError):
            return False

    def publish(self, event: Event) -> int:
        handlers = [handler for event_type, items in self._handlers.items() if isinstance(event, event_type) for handler in tuple(items)]
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                LOGGER.exception("Event handler failed for %s", type(event).__name__)
        return len(handlers)

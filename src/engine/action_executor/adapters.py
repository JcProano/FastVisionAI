"""Small side-effect boundaries used only by :mod:`action_executor.executor`."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from .contracts import ActionExecutionContext


class PopupActionAdapter(Protocol):
    def show_registered(self, context: ActionExecutionContext) -> None: ...
    def show_unregistered(self, context: ActionExecutionContext) -> None: ...


class DetectionEventActionAdapter(Protocol):
    def log_proposed_event(self, context: ActionExecutionContext) -> None: ...


@dataclass(frozen=True, slots=True)
class CallbackPopupActionAdapter:
    """Prepared callback adapter; deliberately not wired by the composition root."""

    registered_callback: Callable[[ActionExecutionContext], None]
    unregistered_callback: Callable[[ActionExecutionContext], None]

    def show_registered(self, context: ActionExecutionContext) -> None:
        self.registered_callback(context)

    def show_unregistered(self, context: ActionExecutionContext) -> None:
        self.unregistered_callback(context)


@dataclass(frozen=True, slots=True)
class CallbackDetectionEventActionAdapter:
    """Prepared callback adapter; deliberately not wired by the composition root."""

    callback: Callable[[ActionExecutionContext], None]

    def log_proposed_event(self, context: ActionExecutionContext) -> None:
        self.callback(context)


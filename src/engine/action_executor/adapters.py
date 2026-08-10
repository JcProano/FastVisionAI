"""Small side-effect boundaries used only by :mod:`action_executor.executor`."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from .contracts import ActionExecutionContext, DetectionEventActionData, PopupActionData


class PopupActionAdapter(Protocol):
    def show_registered(
        self, context: ActionExecutionContext, popup: PopupActionData,
    ) -> None: ...
    def show_unregistered(
        self, context: ActionExecutionContext, popup: PopupActionData,
    ) -> None: ...


class DetectionEventActionAdapter(Protocol):
    def log_proposed_event(
        self, context: ActionExecutionContext, event: DetectionEventActionData,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class CallbackPopupActionAdapter:
    """Prepared callback adapter; deliberately not wired by the composition root."""

    registered_callback: Callable[[ActionExecutionContext, PopupActionData], None]
    unregistered_callback: Callable[[ActionExecutionContext, PopupActionData], None]

    def show_registered(
        self, context: ActionExecutionContext, popup: PopupActionData,
    ) -> None:
        self.registered_callback(context, popup)

    def show_unregistered(
        self, context: ActionExecutionContext, popup: PopupActionData,
    ) -> None:
        self.unregistered_callback(context, popup)


@dataclass(frozen=True, slots=True)
class CallbackDetectionEventActionAdapter:
    """Prepared callback adapter; deliberately not wired by the composition root."""

    callback: Callable[[ActionExecutionContext, DetectionEventActionData], None]

    def log_proposed_event(
        self, context: ActionExecutionContext, event: DetectionEventActionData,
    ) -> None:
        self.callback(context, event)

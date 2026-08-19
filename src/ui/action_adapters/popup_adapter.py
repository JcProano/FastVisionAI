"""Thread-safe presentation bridge for ActionExecutor popup requests."""

from __future__ import annotations

import queue
import logging

from src.engine.action_executor import ActionExecutionContext, PopupActionData
from src.core.application_events import ApplicationEventBus, PopupRequestedEvent
from src.ui.identification import (
    IdentificationPopupDTO, IdentificationPopupType,
    IdentificationPresentationController,
)

LOGGER = logging.getLogger(__name__)


class IdentificationPopupActionAdapter:
    """Resolve via the UI provider/controller and queue only safe presentation DTOs."""

    __slots__ = ("_controller", "_queue", "_closed", "_application_events")

    def __init__(
        self, controller: IdentificationPresentationController, *, queue_size: int = 8,
        application_event_bus: ApplicationEventBus | None = None,
    ) -> None:
        if queue_size <= 0:
            raise ValueError("popup queue size must be positive")
        self._controller = controller
        self._queue: queue.Queue[IdentificationPopupDTO] = queue.Queue(maxsize=queue_size)
        self._closed = False
        self._application_events = application_event_bus

    def show_registered(
        self, context: ActionExecutionContext, popup: PopupActionData,
    ) -> None:
        self._deliver(context, popup)

    def show_unregistered(
        self, context: ActionExecutionContext, popup: PopupActionData,
    ) -> None:
        self._deliver(context, popup)

    def _deliver(
        self, context: ActionExecutionContext, popup: PopupActionData,
    ) -> None:
        if self._closed:
            raise RuntimeError("popup adapter is closed")
        dto = self._controller.observe_action(
            context.action.value, context.person_id, popup.recognition_state,
            popup.similarity, popup.message, popup.evaluated,
        )
        if self._application_events is not None:
            try:
                self._application_events.publish(PopupRequestedEvent(
                    source="popup_action_adapter", session_id=context.session_id,
                    run_id=context.run_id, popup_action=context.action.value,
                    person_id=context.person_id, presentation_state=dto.popup_type.value,
                    reason=(dto.message if dto.popup_type is
                            IdentificationPopupType.SUPPRESSED else None),
                    timestamp=context.timestamp,
                ))
            except Exception as exc:
                LOGGER.error("Popup application event failed safely; exception_type=%s",
                             type(exc).__name__)
        # A cooldown/stability suppression is a successfully processed request, but
        # must not displace an actionable popup already waiting for Tk's main thread.
        if dto.popup_type is not IdentificationPopupType.SUPPRESSED:
            _put_recent(self._queue, dto)

    def drain(self) -> tuple[IdentificationPopupDTO, ...]:
        values: list[IdentificationPopupDTO] = []
        while True:
            try:
                values.append(self._queue.get_nowait())
            except queue.Empty:
                return tuple(values)

    def clear(self) -> None:
        self.drain()

    def close(self) -> None:
        self._closed = True
        self.clear()


def _put_recent(
    target: queue.Queue[IdentificationPopupDTO], item: IdentificationPopupDTO,
) -> None:
    try:
        target.put_nowait(item)
        return
    except queue.Full:
        pass
    try:
        target.get_nowait()
    except queue.Empty:
        pass
    try:
        target.put_nowait(item)
    except queue.Full:
        pass

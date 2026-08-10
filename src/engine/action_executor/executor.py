"""Deterministic execution of explicitly permitted orchestrator proposals."""

from __future__ import annotations

import logging

from .adapters import DetectionEventActionAdapter, PopupActionAdapter
from .contracts import (
    ActionExecutionContext, ActionExecutionInput, ActionExecutionResult,
    ActionExecutionState, ExecutableAction,
)
from .policy import ActionExecutorPolicy

LOGGER = logging.getLogger(__name__)

_ORDER = tuple(action.value for action in (
    ExecutableAction.SHOW_REGISTERED_POPUP,
    ExecutableAction.SHOW_UNREGISTERED_POPUP,
    ExecutableAction.LOG_DETECTION_EVENT,
))
_NON_EXECUTABLE = frozenset({
    "PROPOSE_ATTENDANCE", "CHECK_IN", "CHECK_OUT", "OPEN_DOOR",
    "ACCESS_GRANTED", "ACCESS_DENIED",
})


class ActionExecutor:
    """Stateless executor. Side effects can occur only through injected adapters."""

    __slots__ = ("policy", "_popup", "_detection")

    def __init__(
        self, policy: ActionExecutorPolicy | None = None, *,
        popup_adapter: PopupActionAdapter | None = None,
        detection_event_adapter: DetectionEventActionAdapter | None = None,
    ) -> None:
        self.policy = policy or ActionExecutorPolicy()
        self._popup = popup_adapter
        self._detection = detection_event_adapter

    def execute(self, value: ActionExecutionInput) -> ActionExecutionResult:
        policy = self.policy
        requested = _requested(value.proposed_actions)
        if not policy.enabled:
            return self._result(value, ActionExecutionState.NOT_EVALUATED, False, requested,
                                (), (), (), ("executor_disabled",))
        if value.orchestrator_state.upper() == "NOT_EVALUATED":
            return self._result(value, ActionExecutionState.NOT_EVALUATED, False, requested,
                                (), (), (), ("orchestrator_not_evaluated",))
        if not requested:
            return self._result(value, ActionExecutionState.NO_ACTIONS, True, (), (), (), (),
                                ("no_actions",))
        if not policy.automatic_execution_enabled:
            return self._result(value, ActionExecutionState.EXECUTION_DISABLED, True,
                                requested, (), requested, (),
                                ("automatic_execution_disabled",))
        if (policy.require_orchestrator_actions_enabled and
                not value.orchestrator_automatic_actions_enabled):
            return self._result(value, ActionExecutionState.EXECUTION_DISABLED, True,
                                requested, (), requested, (),
                                ("orchestrator_actions_disabled",))

        blocked = set(value.blocked_actions)
        executed: list[str] = []
        skipped: list[str] = []
        failed: list[str] = []
        reasons: list[str] = []
        for action_name in requested:
            if action_name in blocked:
                skipped.append(action_name); reasons.append(f"{action_name.lower()}_blocked")
                continue
            if action_name in _NON_EXECUTABLE:
                skipped.append(action_name)
                reasons.append("attendance_execution_disabled" if action_name ==
                               "PROPOSE_ATTENDANCE" else "action_not_executable")
                continue
            try:
                action = ExecutableAction(action_name)
            except ValueError:
                skipped.append(action_name); reasons.append("unknown_action")
                continue
            reason = self._precondition(action, value.person_id)
            if reason is not None:
                skipped.append(action_name); reasons.append(reason)
                continue
            context = ActionExecutionContext(
                action, value.person_id, value.run_id, value.session_id,
                value.orchestrator_state, value.timestamp,
            )
            try:
                self._invoke(action, context)
                executed.append(action_name)
            except Exception as exc:  # adapter boundary must not stop LiveFaceSession
                LOGGER.error("Action adapter failed safely; action=%s exception_type=%s",
                             action_name, type(exc).__name__)
                failed.append(action_name); reasons.append(f"{action_name.lower()}_failed")

        if executed and (skipped or failed):
            state = ActionExecutionState.PARTIALLY_EXECUTED
        elif executed:
            state = ActionExecutionState.EXECUTED
        elif failed:
            state = ActionExecutionState.FAILED
        else:
            state = ActionExecutionState.BLOCKED
        return self._result(value, state, True, requested, tuple(executed), tuple(skipped),
                            tuple(failed), tuple(dict.fromkeys(reasons)))

    def _precondition(self, action: ExecutableAction, person_id: str | None) -> str | None:
        policy = self.policy
        if action is ExecutableAction.SHOW_REGISTERED_POPUP:
            if not policy.allow_registered_popup:
                return "registered_popup_disabled"
            if person_id is None:
                return "person_id_required"
            if self._popup is None:
                return "popup_adapter_missing"
        elif action is ExecutableAction.SHOW_UNREGISTERED_POPUP:
            if not policy.allow_unregistered_popup:
                return "unregistered_popup_disabled"
            if person_id is not None:
                return "unregistered_popup_requires_no_person_id"
            if self._popup is None:
                return "popup_adapter_missing"
        elif action is ExecutableAction.LOG_DETECTION_EVENT:
            if not policy.allow_detection_event_logging:
                return "detection_event_logging_disabled"
            if self._detection is None:
                return "detection_event_adapter_missing"
        return None

    def _invoke(self, action: ExecutableAction, context: ActionExecutionContext) -> None:
        if action is ExecutableAction.SHOW_REGISTERED_POPUP:
            assert self._popup is not None
            self._popup.show_registered(context)
        elif action is ExecutableAction.SHOW_UNREGISTERED_POPUP:
            assert self._popup is not None
            self._popup.show_unregistered(context)
        else:
            assert self._detection is not None
            self._detection.log_proposed_event(context)

    def _result(
        self, value: ActionExecutionInput, state: ActionExecutionState, evaluated: bool,
        requested: tuple[str, ...], executed: tuple[str, ...], skipped: tuple[str, ...],
        failed: tuple[str, ...], reasons: tuple[str, ...],
    ) -> ActionExecutionResult:
        return ActionExecutionResult(
            state, evaluated, requested, executed, skipped, failed, reasons,
            self.policy.automatic_execution_enabled, self.policy.policy_name,
            self.policy.policy_version, value.timestamp,
        )


def _requested(values: tuple[str, ...]) -> tuple[str, ...]:
    unique = {str(getattr(item, "value", item)) for item in values}
    unique.discard("NONE")
    ordered = [name for name in _ORDER if name in unique]
    ordered.extend(sorted(unique.difference(_ORDER)))
    return tuple(ordered)


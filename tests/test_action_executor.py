import unittest
from datetime import datetime, timezone

from src.engine.action_executor import (
    ActionExecutionInput, ActionExecutionState, ActionExecutor, ActionExecutorPolicy,
    DetectionEventActionData,
    PopupActionData,
)


class PopupSpy:
    def __init__(self, calls, fail_registered=False, fail_unregistered=False):
        self.calls = calls; self.fail_registered = fail_registered
        self.fail_unregistered = fail_unregistered

    def show_registered(self, context, popup):
        self.calls.append(context.action.value)
        if self.fail_registered: raise RuntimeError("safe test failure")

    def show_unregistered(self, context, popup):
        self.calls.append(context.action.value)
        if self.fail_unregistered: raise RuntimeError("safe test failure")


class DetectionSpy:
    def __init__(self, calls, fail=False): self.calls = calls; self.fail = fail
    def log_proposed_event(self, context, event):
        self.calls.append(context.action.value)
        if self.fail: raise RuntimeError("safe test failure")


def action_input(actions=("SHOW_REGISTERED_POPUP",), **changes):
    values = dict(
        proposed_actions=tuple(actions), blocked_actions=(),
        orchestrator_state="POLICY_ELIGIBLE",
        orchestrator_automatic_actions_enabled=True, person_id="person",
        run_id="run", session_id="session", timestamp=datetime.now(timezone.utc),
        detection_event=DetectionEventActionData("NOT_EVALUATED"),
        popup=PopupActionData("NOT_EVALUATED"),
    )
    values.update(changes)
    return ActionExecutionInput(**values)


class ActionExecutorTests(unittest.TestCase):
    def executor(self, calls, **policy):
        return ActionExecutor(
            ActionExecutorPolicy(automatic_execution_enabled=True, **policy),
            popup_adapter=PopupSpy(calls), detection_event_adapter=DetectionSpy(calls),
        )

    def test_policy_disabled_is_not_evaluated(self):
        calls = []
        result = ActionExecutor(ActionExecutorPolicy(enabled=False),
                                popup_adapter=PopupSpy(calls)).execute(action_input())
        self.assertEqual(result.state, ActionExecutionState.NOT_EVALUATED)
        self.assertFalse(result.evaluated); self.assertEqual(calls, [])

    def test_automatic_execution_disabled_has_zero_adapter_calls(self):
        calls = []
        result = ActionExecutor(popup_adapter=PopupSpy(calls),
                                detection_event_adapter=DetectionSpy(calls)).execute(
            action_input(("SHOW_REGISTERED_POPUP", "LOG_DETECTION_EVENT"))
        )
        self.assertEqual(result.state, ActionExecutionState.EXECUTION_DISABLED)
        self.assertEqual(result.executed_actions, ()); self.assertEqual(calls, [])

    def test_orchestrator_actions_disabled_is_second_barrier(self):
        calls = []
        result = self.executor(calls).execute(action_input(
            orchestrator_automatic_actions_enabled=False))
        self.assertEqual(result.state, ActionExecutionState.EXECUTION_DISABLED)
        self.assertEqual(calls, []); self.assertIn("orchestrator_actions_disabled", result.reasons)

    def test_none_and_no_actions(self):
        for actions in ((), ("NONE",), ("NONE", "LOG_DETECTION_EVENT")):
            calls = []
            result = self.executor(calls).execute(action_input(actions))
            if "LOG_DETECTION_EVENT" in actions:
                self.assertEqual(result.requested_actions, ("LOG_DETECTION_EVENT",))
            else:
                self.assertEqual(result.state, ActionExecutionState.NO_ACTIONS)

    def test_registered_unregistered_and_detection_actions(self):
        cases = (
            (("SHOW_REGISTERED_POPUP",), "person"),
            (("SHOW_UNREGISTERED_POPUP",), None),
            (("LOG_DETECTION_EVENT",), None),
        )
        for actions, person_id in cases:
            calls = []
            result = self.executor(calls).execute(action_input(actions, person_id=person_id))
            self.assertEqual(result.state, ActionExecutionState.EXECUTED)
            self.assertEqual(calls, list(actions))

    def test_blocked_action_never_calls_adapter(self):
        calls = []
        result = self.executor(calls).execute(action_input(
            blocked_actions=("SHOW_REGISTERED_POPUP",)))
        self.assertEqual(result.state, ActionExecutionState.BLOCKED)
        self.assertEqual(calls, [])

    def test_duplicate_actions_are_deduplicated_and_ordered(self):
        calls = []
        result = self.executor(calls).execute(action_input((
            "LOG_DETECTION_EVENT", "SHOW_REGISTERED_POPUP", "LOG_DETECTION_EVENT",
        )))
        expected = ("SHOW_REGISTERED_POPUP", "LOG_DETECTION_EVENT")
        self.assertEqual(result.requested_actions, expected)
        self.assertEqual(tuple(calls), expected)

    def test_missing_person_unknown_attendance_and_missing_adapter_are_safe(self):
        cases = (
            (action_input(person_id=None), "person_id_required"),
            (action_input(("FUTURE_ACTION",)), "unknown_action"),
            (action_input(("PROPOSE_ATTENDANCE",)), "attendance_execution_disabled"),
        )
        for value, reason in cases:
            result = self.executor([]).execute(value)
            self.assertEqual(result.state, ActionExecutionState.BLOCKED)
            self.assertIn(reason, result.reasons)
        result = ActionExecutor(ActionExecutorPolicy(automatic_execution_enabled=True)).execute(
            action_input())
        self.assertIn("popup_adapter_missing", result.reasons)

    def test_partial_failure_continues_in_deterministic_order(self):
        calls = []
        executor = ActionExecutor(
            ActionExecutorPolicy(automatic_execution_enabled=True),
            popup_adapter=PopupSpy(calls, fail_registered=True),
            detection_event_adapter=DetectionSpy(calls),
        )
        result = executor.execute(action_input((
            "LOG_DETECTION_EVENT", "SHOW_REGISTERED_POPUP",
        )))
        self.assertEqual(result.state, ActionExecutionState.PARTIALLY_EXECUTED)
        self.assertEqual(calls, ["SHOW_REGISTERED_POPUP", "LOG_DETECTION_EVENT"])
        self.assertEqual(result.failed_actions, ("SHOW_REGISTERED_POPUP",))
        self.assertEqual(result.executed_actions, ("LOG_DETECTION_EVENT",))

    def test_all_adapter_actions_fail(self):
        calls = []
        executor = ActionExecutor(
            ActionExecutorPolicy(automatic_execution_enabled=True),
            popup_adapter=PopupSpy(calls, fail_registered=True),
            detection_event_adapter=DetectionSpy(calls, fail=True),
        )
        result = executor.execute(action_input((
            "SHOW_REGISTERED_POPUP", "LOG_DETECTION_EVENT",
        )))
        self.assertEqual(result.state, ActionExecutionState.FAILED)
        self.assertEqual(len(result.failed_actions), 2)

    def test_repeated_evaluation_is_deterministic(self):
        executor = ActionExecutor(ActionExecutorPolicy())
        value = action_input(("LOG_DETECTION_EVENT", "SHOW_REGISTERED_POPUP"))
        first = executor.execute(value); second = executor.execute(value)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()

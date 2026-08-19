import unittest
from datetime import datetime, timezone

from src.engine.decision_orchestrator import (
    DecisionOrchestrator, DecisionOrchestratorInput, DecisionOrchestratorPolicy,
    DecisionState, ProposedAction,
)


def decision_input(**changes):
    values = dict(
        face_count=1, person_id="person", recognition_state="NOT_EVALUATED",
        similarity=.8, stability_state="STABLE",
        identification_policy_state="ELIGIBLE", policy_eligible=True,
        administrative_status="ACTIVE", quality_score=80, run_id="run",
        session_id="session", timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    values.update(changes)
    return DecisionOrchestratorInput(**values)


class DecisionOrchestratorTests(unittest.TestCase):
    def evaluate(self, policy=None, **changes):
        return DecisionOrchestrator(policy).evaluate(decision_input(**changes))

    def test_disabled_and_no_face(self):
        disabled = self.evaluate(DecisionOrchestratorPolicy(enabled=False))
        self.assertEqual(disabled.state, DecisionState.NOT_EVALUATED)
        self.assertFalse(disabled.evaluated)
        self.assertEqual(disabled.proposed_actions, (ProposedAction.NONE,))
        no_face = self.evaluate(face_count=0, person_id=None)
        self.assertEqual(no_face.state, DecisionState.NO_CANDIDATE)
        self.assertEqual(no_face.proposed_actions, (ProposedAction.NONE,))

    def test_multiple_and_incompatible_keep_structural_precedence(self):
        multiple = self.evaluate(face_count=2, person_id=None)
        self.assertEqual(multiple.state, DecisionState.AMBIGUOUS)
        incompatible = self.evaluate(person_id=None, recognition_state="INCOMPATIBLE")
        self.assertEqual(incompatible.state, DecisionState.INCOMPATIBLE)
        for result in (multiple, incompatible):
            self.assertIn(ProposedAction.LOG_DETECTION_EVENT, result.proposed_actions)
            self.assertNotEqual(result.state, DecisionState.ACTIONS_DISABLED)

    def test_unregistered_popup_requires_stable_unknown_continuity(self):
        isolated = self.evaluate(
            person_id=None, recognition_state="UNKNOWN", administrative_status=None,
            identification_policy_state="NO_CANDIDATE", policy_eligible=False,
            stability_state="STABILIZING",
        )
        self.assertNotIn(ProposedAction.SHOW_UNREGISTERED_POPUP,
                         isolated.proposed_actions)
        self.assertIn(ProposedAction.SHOW_UNREGISTERED_POPUP,
                      isolated.blocked_actions)
        result = self.evaluate(person_id=None, recognition_state="UNKNOWN",
                               administrative_status=None,
                               identification_policy_state="NO_CANDIDATE",
                               policy_eligible=False, stability_state="STABLE")
        self.assertEqual(result.state, DecisionState.ACTIONS_DISABLED)
        self.assertEqual(result.proposed_actions, (
            ProposedAction.SHOW_UNREGISTERED_POPUP,
            ProposedAction.LOG_DETECTION_EVENT,
        ))
        self.assertEqual(result.reasons[0], "automatic_actions_disabled")

    def test_no_gallery_incompatible_and_not_evaluated_never_propose_unregistered_popup(self):
        for recognition in ("NO_GALLERY", "INCOMPATIBLE", "NOT_EVALUATED"):
            with self.subTest(recognition=recognition):
                result = self.evaluate(
                    person_id=None, recognition_state=recognition,
                    administrative_status=None, identification_policy_state="NO_CANDIDATE",
                    policy_eligible=False, stability_state="STABLE",
                )
                self.assertNotIn(ProposedAction.SHOW_UNREGISTERED_POPUP,
                                 result.proposed_actions)

    def test_registered_popup_requires_active_and_policy_eligible(self):
        policy = DecisionOrchestratorPolicy(automatic_actions_enabled=True)
        disabled = self.evaluate(policy, administrative_status="DISABLED")
        ineligible = self.evaluate(
            policy, identification_policy_state="INSUFFICIENT_STABILITY",
            policy_eligible=False,
        )
        for result in (disabled, ineligible):
            self.assertNotIn(ProposedAction.SHOW_REGISTERED_POPUP,
                             result.proposed_actions)
            self.assertIn(ProposedAction.SHOW_REGISTERED_POPUP,
                          result.blocked_actions)

    def test_registered_popup_requires_stability(self):
        policy = DecisionOrchestratorPolicy(automatic_actions_enabled=True)
        unstable = self.evaluate(policy, stability_state="STABILIZING")
        self.assertEqual(unstable.state, DecisionState.OBSERVATION_ONLY)
        self.assertIn(ProposedAction.SHOW_REGISTERED_POPUP, unstable.blocked_actions)
        stable = self.evaluate(policy)
        self.assertEqual(stable.state, DecisionState.POLICY_ELIGIBLE)
        self.assertIn(ProposedAction.SHOW_REGISTERED_POPUP, stable.proposed_actions)

    def test_admin_and_identification_policy_blocking(self):
        admin = self.evaluate(administrative_status="DISABLED")
        self.assertEqual(admin.state, DecisionState.BLOCKED_BY_ADMIN_STATUS)
        policy = self.evaluate(
            identification_policy_state="INSUFFICIENT_STABILITY", policy_eligible=False,
        )
        self.assertEqual(policy.state, DecisionState.BLOCKED_BY_POLICY)

    def test_attendance_disabled_is_real_block_only_when_applicable(self):
        policy = DecisionOrchestratorPolicy(automatic_actions_enabled=True)
        result = self.evaluate(policy)
        self.assertNotIn(ProposedAction.PROPOSE_ATTENDANCE, result.proposed_actions)
        self.assertIn(ProposedAction.PROPOSE_ATTENDANCE, result.blocked_actions)
        self.assertIn("attendance_proposal_disabled", result.reasons)
        inapplicable = self.evaluate(policy, stability_state="STABILIZING")
        self.assertNotIn(ProposedAction.PROPOSE_ATTENDANCE, inapplicable.blocked_actions)

    def test_attendance_enabled_is_still_only_a_proposal(self):
        policy = DecisionOrchestratorPolicy(
            automatic_actions_enabled=True, allow_attendance_proposal=True,
        )
        result = self.evaluate(policy)
        self.assertIn(ProposedAction.PROPOSE_ATTENDANCE, result.proposed_actions)
        self.assertFalse(hasattr(result, "executed_actions"))

    def test_actions_disabled_does_not_replace_higher_block(self):
        eligible = self.evaluate()
        self.assertEqual(eligible.state, DecisionState.ACTIONS_DISABLED)
        self.assertTrue(set(eligible.proposed_actions) <= set(eligible.blocked_actions))
        blocked = self.evaluate(administrative_status="PENDING_BIOMETRIC")
        self.assertEqual(blocked.state, DecisionState.BLOCKED_BY_ADMIN_STATUS)

    def test_unknown_states_degrade_without_exception(self):
        result = self.evaluate(
            recognition_state="FUTURE", stability_state="FUTURE",
            identification_policy_state="FUTURE", policy_eligible=False,
        )
        self.assertEqual(result.state, DecisionState.BLOCKED_BY_POLICY)

    def test_deterministic_stateless_side_effect_free(self):
        orchestrator = DecisionOrchestrator()
        value = decision_input()
        self.assertEqual(orchestrator.evaluate(value), orchestrator.evaluate(value))
        self.assertEqual(orchestrator.__slots__, ("policy",))


if __name__ == "__main__":
    unittest.main()

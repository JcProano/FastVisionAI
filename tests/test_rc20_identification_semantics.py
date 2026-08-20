import unittest

from src.ui.identification_semantics import (
    IdentificationVisualState, identification_visual_state, is_confirmed_match,
)


class RC20IdentificationSemanticsTests(unittest.TestCase):
    def test_top1_is_only_a_candidate_regardless_of_similarity(self):
        for _similarity in (0.178, 0.999):
            self.assertIs(
                identification_visual_state("NOT_EVALUATED", False, "jean"),
                IdentificationVisualState.BIOMETRIC_CANDIDATE,
            )

    def test_only_strict_match_is_identified(self):
        self.assertTrue(is_confirmed_match("MATCH", True, "jean"))
        for state, evaluated, person_id in (
            ("MATCH", False, "jean"), ("MATCH", True, None),
            ("NOT_EVALUATED", False, "jean"), ("UNKNOWN", True, None),
        ):
            self.assertFalse(is_confirmed_match(state, evaluated, person_id))

    def test_unknown_requires_evaluation_and_no_candidate(self):
        self.assertIs(
            identification_visual_state("UNKNOWN", True, None),
            IdentificationVisualState.UNREGISTERED,
        )
        self.assertIs(
            identification_visual_state("UNKNOWN", True, "jean"),
            IdentificationVisualState.NOT_PRESENTABLE,
        )


if __name__ == "__main__":
    unittest.main()

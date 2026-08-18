from __future__ import annotations

import dataclasses
import unittest

import numpy as np

from src.ui.contracts import (
    EnrollmentProgressDTO, EnrollmentResultDTO, ErrorDTO, MonitoringDTO, UIErrorCode, UIState,
)
from src.ui.tk_app import monitoring_text


class UIContractTests(unittest.TestCase):
    def test_public_dtos_have_no_biometric_payload_fields(self):
        forbidden = {
            "embedding", "embeddings", "template", "templates", "aligned_face",
            "aligned_faces", "frame", "model",
        }
        for dto in (MonitoringDTO, EnrollmentProgressDTO, EnrollmentResultDTO, ErrorDTO):
            names = {field.name for field in dataclasses.fields(dto)}
            self.assertTrue(names.isdisjoint(forbidden), (dto.__name__, names & forbidden))

    def test_no_ui_state_uses_recognition_language(self):
        forbidden = ("recognized", "recognised", "confirmed", "reconoc")
        for state in UIState:
            self.assertFalse(any(word in state.name.lower() or word in state.value.lower()
                                 for word in forbidden))

    def test_presenter_uses_experimental_candidate_and_no_decision(self):
        dto = MonitoringDTO(
            UIState.MONITORING, "Candidato experimental", "Temporary", .9123,
            "NOT_EVALUATED", True,
        )
        view = monitoring_text(dto)
        self.assertEqual(view.headline, "Candidato experimental")
        self.assertEqual(view.similarity, "0.9123")
        self.assertEqual(view.decision, "Threshold: N/D | Estado: NOT_EVALUATED")
        self.assertEqual(dto.recognition_state, "NOT_EVALUATED")

    def test_presenter_uses_safe_structural_messages(self):
        for message, state in (
            ("Sin candidatos registrados", "NO_GALLERY"),
            ("Sin candidatos compatibles", "INCOMPATIBLE"),
        ):
            dto = MonitoringDTO(
                UIState.MONITORING, message, None, None,
                "deshabilitada / NOT_EVALUATED", True,
                recognition_state=state,
            )
            view = monitoring_text(dto)
            self.assertEqual(view.headline, message)
            self.assertEqual(view.candidate, message)
            self.assertEqual(
                view.decision, f"Threshold: N/D | Estado: {state}"
            )

    def test_dto_instances_do_not_contain_numpy_arrays(self):
        values = (
            MonitoringDTO(UIState.MONITORING, "Sin candidatos registrados", None, None,
                          "deshabilitada / NOT_EVALUATED", True),
            EnrollmentProgressDTO(UIState.ENROLLING, "Mire al frente", 1, 3, (), 80, "good", True),
            ErrorDTO(UIState.ERROR, UIErrorCode.MATCHER_ERROR, "falló", True),
        )
        for value in values:
            self.assertFalse(any(isinstance(item, np.ndarray)
                                 for item in dataclasses.astuple(value)))


if __name__ == "__main__":
    unittest.main()

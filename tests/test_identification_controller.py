import dataclasses
import unittest
import threading
from datetime import datetime, timezone

import numpy as np

from src.ui.contracts import MonitoringDTO, UIState
from src.ui.identification import (
    IdentificationPopupPolicy, IdentificationPopupType, IdentityPersonDTO,
    IdentificationPresentationController,
)
from src.ui.people.contracts import PersonSummaryDTO
from src.ui.thumbnails import ThumbnailDTO


class Provider:
    def __init__(self, thumbnail=True):
        self.thumbnail = thumbnail
        self.people = {
            "person_a": IdentityPersonDTO(
                "person_a", "Temporary", "A", "Temporary A", "EXT-A",
                phone="0990000000", email="temporary@example.test", status="ACTIVE",
                department="Engineering", position="Developer", company="FastVisionAI",
            ),
            "person_b": PersonSummaryDTO(
                "person_b", "Temporary", "B", "Temporary B", None,
                3, 0, 3, None, None, None, None,
            ),
        }

    def get_person(self, person_id): return self.people.get(person_id)
    def get_thumbnail(self, person_id):
        return ThumbnailDTO(person_id, self.thumbnail, 224 if self.thumbnail else 0,
                            224 if self.thumbnail else 0, "jpeg", b"x" if self.thumbnail else None)


def monitoring(person_id=None, state="NOT_EVALUATED", ui_state=UIState.MONITORING,
               evaluated=None):
    if evaluated is None:
        evaluated = state == "UNKNOWN"
    return MonitoringDTO(
        ui_state, "Candidato experimental" if person_id else "Sin candidatos registrados",
        None if person_id is None else f"Temporary {person_id[-1].upper()}",
        None if person_id is None else .91, "NOT_EVALUATED", True,
        recognition_state=state, candidate_person_id=person_id, evaluated=evaluated,
    )


class IdentificationControllerTests(unittest.TestCase):
    def setUp(self):
        self.clock = [0.0]
        self.provider = Provider()
        self.controller = IdentificationPresentationController(
            IdentificationPopupPolicy(True, 10, 10, 3), self.provider,
            monotonic=lambda: self.clock[0],
            utcnow=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

    def stable(self, event):
        results = [self.controller.observe(event) for _ in range(3)]
        return next(
            (item for item in results if item.popup_type is not IdentificationPopupType.SUPPRESSED),
            results[-1],
        )

    def test_stable_candidate_opens_once_and_instable_does_not(self):
        event = monitoring("person_a")
        self.assertEqual(self.controller.observe(event).popup_type,
                         IdentificationPopupType.SUPPRESSED)
        self.controller.observe(monitoring("person_b"))
        self.assertEqual(self.controller.observe(event).popup_type,
                         IdentificationPopupType.SUPPRESSED)
        shown = self.stable(event)
        self.assertEqual(shown.popup_type, IdentificationPopupType.REGISTERED_CANDIDATE)
        self.assertIsNone(shown.external_identifier)
        self.assertIsNone(shown.phone)
        self.assertIn("CANDIDATO BIOMÉTRICO", shown.message)
        self.assertTrue(shown.thumbnail_available)
        self.assertIsNone(shown.position)
        self.assertIsNone(shown.department)
        self.assertIsNone(shown.company)
        self.assertIsNone(shown.email)
        self.assertEqual(shown.recognition_state, "NOT_EVALUATED")
        self.assertIn("PENDIENTE DE CALIBRACIÓN", shown.message)
        self.assertEqual(self.controller.observe(event).popup_type,
                         IdentificationPopupType.SUPPRESSED)

    def test_cooldown_and_candidate_change(self):
        self.assertEqual(self.stable(monitoring("person_a")).popup_type,
                         IdentificationPopupType.REGISTERED_CANDIDATE)
        self.assertEqual(self.stable(monitoring("person_b")).popup_type,
                         IdentificationPopupType.SUPPRESSED)
        self.clock[0] += 60
        self.assertEqual(self.stable(monitoring("person_b")).popup_type,
                         IdentificationPopupType.REGISTERED_CANDIDATE)

    def test_registered_popup_pause_survives_early_close_semantics(self):
        shown = self.stable(monitoring("person_a"))
        self.assertEqual(shown.popup_type,
                         IdentificationPopupType.REGISTERED_CANDIDATE)
        self.assertEqual(self.controller.registered_pause_remaining_seconds(), 60)
        self.clock[0] += 59
        self.assertEqual(self.stable(monitoring("person_a")).popup_type,
                         IdentificationPopupType.SUPPRESSED)
        self.clock[0] += 1
        self.assertEqual(self.controller.registered_pause_remaining_seconds(), 0)
        self.assertEqual(self.stable(monitoring("person_a")).popup_type,
                         IdentificationPopupType.REGISTERED_CANDIDATE)

    def test_only_evaluated_unknown_without_candidate_opens_unregistered_popup(self):
        controller = IdentificationPresentationController(
            IdentificationPopupPolicy(True, 0, 0, 1), self.provider,
        )
        self.assertEqual(controller.observe(monitoring(state="UNKNOWN", evaluated=True)).popup_type,
                         IdentificationPopupType.UNREGISTERED)
        self.assertEqual(controller.observe(monitoring(state="UNKNOWN", evaluated=False)).popup_type,
                         IdentificationPopupType.SUPPRESSED)

    def test_match_requires_evaluation_and_is_the_only_identified_popup(self):
        controller = IdentificationPresentationController(
            IdentificationPopupPolicy(True, 0, 0, 1), self.provider,
        )
        identified = controller.observe(monitoring("person_a", "MATCH", evaluated=True))
        self.assertEqual(identified.popup_type, IdentificationPopupType.REGISTERED_CANDIDATE)
        self.assertEqual(identified.recognition_state, "MATCH")
        self.assertEqual(identified.message, "Persona identificada")
        self.assertEqual(controller.observe(monitoring("person_b", "MATCH", evaluated=False)).popup_type,
                         IdentificationPopupType.SUPPRESSED)

    def test_non_evaluated_or_structural_states_never_open_unregistered_popup(self):
        for state in ("NO_GALLERY", "INCOMPATIBLE", "NOT_EVALUATED"):
            with self.subTest(state=state):
                controller = IdentificationPresentationController(
                    IdentificationPopupPolicy(True, 0, 0, 1), self.provider,
                )
                result = controller.observe(monitoring(state=state))
                self.assertEqual(result.popup_type, IdentificationPopupType.SUPPRESSED)

    def test_unknown_cooldown_starts_on_close_and_is_independent_from_timeout(self):
        controller = IdentificationPresentationController(
            IdentificationPopupPolicy(True, 0, 10, 1, 60), self.provider,
            monotonic=lambda: self.clock[0],
        )
        event = monitoring(state="UNKNOWN", evaluated=True)
        self.assertEqual(controller.observe(event).popup_type, IdentificationPopupType.UNREGISTERED)
        self.clock[0] = 60
        controller.unknown_dismissed()
        self.assertEqual(controller.observe(event).popup_type, IdentificationPopupType.SUPPRESSED)
        self.clock[0] = 70
        self.assertEqual(controller.observe(event).popup_type, IdentificationPopupType.UNREGISTERED)

    def test_multiple_faces_and_enrollment_are_suppressed(self):
        multiple = monitoring(ui_state=UIState.MULTIPLE_FACES)
        self.assertEqual(self.stable(multiple).popup_type, IdentificationPopupType.SUPPRESSED)
        self.controller.suspend()
        self.assertEqual(self.stable(monitoring("person_a")).popup_type,
                         IdentificationPopupType.SUPPRESSED)
        self.controller.resume()
        self.assertEqual(self.stable(monitoring("person_a")).popup_type,
                         IdentificationPopupType.REGISTERED_CANDIDATE)

    def test_dto_has_no_biometric_payloads(self):
        result = self.stable(monitoring("person_a"))
        forbidden = {"embedding", "template", "array", "path", "model", "image"}
        names = {field.name.casefold() for field in dataclasses.fields(result)}
        self.assertTrue(names.isdisjoint(forbidden))
        self.assertNotIn(np.ndarray, {type(value) for value in dataclasses.astuple(result)})

    def test_action_requests_share_thread_safe_stability_and_provider_path(self):
        errors = []
        def worker():
            try:
                for _ in range(20):
                    self.controller.observe_action(
                        "SHOW_REGISTERED_POPUP", "person_a", "NOT_EVALUATED", .8,
                    )
            except Exception as exc:  # pragma: no cover - asserted empty
                errors.append(type(exc).__name__)
        thread = threading.Thread(target=worker)
        thread.start()
        for _ in range(20):
            self.controller.suspend(); self.controller.resume()
        thread.join()
        self.assertEqual(errors, [])


if __name__ == "__main__": unittest.main()

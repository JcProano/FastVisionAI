import unittest
from types import SimpleNamespace

from src.ui.contracts import MonitoringDTO, UIState
from src.ui.contracts import EnrollmentProgressDTO, EnrollmentResultDTO
from src.ui.web_dashboard.controller import WebDashboardController


def monitoring(state, evaluated, person_id, similarity):
    return MonitoringDTO(UIState.MONITORING, "monitoring", "Jean Carlos Proaño",
                         similarity, "deshabilitada", False,
                         recognition_state=state, candidate_person_id=person_id,
                         evaluated=evaluated)


class RC20WebRecognitionSemanticsTests(unittest.TestCase):
    def controller(self, dto, identity=None, clock=lambda: 10.0):
        return WebDashboardController(lambda: None, presentation_provider=lambda: dto,
                                      identity_provider=identity, monotonic=clock)

    def test_top1_low_or_high_similarity_remains_candidate_without_pii(self):
        for similarity in (.14, .99):
            identity = SimpleNamespace(get_person=lambda _person_id: (_ for _ in ()).throw(
                AssertionError("NOT_EVALUATED must not resolve civil data")))
            value = self.controller(monitoring("NOT_EVALUATED", False, "jean", similarity), identity).api("/api/presentation")
            self.assertEqual(value["title"], "CANDIDATO BIOMÉTRICO")
            self.assertEqual(value["status"], "NO EVALUADO — SISTEMA PENDIENTE DE CALIBRACIÓN")
            self.assertEqual(value["details"], [])
            self.assertNotIn("IDENTIFICADO", value["status"])
            self.assertNotIn("REGISTRAR", str(value))

    def test_only_evaluated_match_resolves_civil_data(self):
        person = SimpleNamespace(display_name="Jean", external_identifier="0926334319",
            position="Dev", department="TI", company="ACME", phone="1", email="a@b.c")
        identity = SimpleNamespace(get_person=lambda _person_id: person)
        value = self.controller(monitoring("MATCH", True, "jean", .784), identity).api("/api/presentation")
        self.assertEqual(value["title"], "PERSONA IDENTIFICADA")
        self.assertEqual(value["status"], "IDENTIFICADO")
        self.assertEqual(len(value["details"]), 6)

    def test_only_evaluated_unknown_without_candidate_offers_registration(self):
        value = self.controller(monitoring("UNKNOWN", True, None, None)).api("/api/presentation")
        self.assertEqual(value["title"], "PERSONA NO REGISTRADA")
        self.assertEqual(value["kind"], "UNKNOWN")
        for dto in (monitoring("UNKNOWN", True, "jean", .2),
                    monitoring("UNKNOWN", False, None, .2),
                    monitoring("MATCH", False, "jean", .9)):
            self.assertFalse(self.controller(dto).api("/api/presentation")["active"])

    def test_single_modal_owns_header_photo_content_and_actions(self):
        page = self.controller(monitoring("UNKNOWN", True, None, None)).render("/").decode()
        self.assertEqual(page.count('id="modal-overlay"'), 1)
        self.assertEqual(page.count('id="modal"'), 1)
        self.assertNotIn('id="enrollment-flow"', page)
        card = page[page.index('id="modal"'):page.index('</section>', page.index('id="modal"'))]
        for class_name in ("modal-header", "modal-photo", "modal-content", "modal-actions"):
            self.assertIn(class_name, card)
        self.assertIn("position:fixed", page)
        self.assertIn("z-index:1000", page)
        self.assertIn("display:flex", page)

    def test_informative_states_never_become_identity_or_unknown(self):
        for state,title in (("NO_GALLERY","GALERÍA VACÍA"),
                            ("INCOMPATIBLE","MODELO BIOMÉTRICO INCOMPATIBLE")):
            value=self.controller(monitoring(state,False,None,None)).api("/api/presentation")
            self.assertEqual(value["title"],title)
            self.assertEqual(value["kind"],state)

    def test_six_stage_web_enrollment_uses_backend_commands_and_safe_status(self):
        current=[None];calls=[]
        unknown=monitoring("UNKNOWN",True,None,None)
        controller=WebDashboardController(lambda:None,presentation_provider=lambda:unknown,
            actions={"enrollment_person":lambda payload:calls.append(("person",payload)) or True,
                     "enrollment_capture_start":lambda payload:calls.append(("capture",payload)) or True,
                     "enrollment_cancel":lambda payload:calls.append(("cancel",payload)) or True,
                     "enrollment_status":lambda:current[0]})
        controller.action("/api/enrollment/start",{})
        self.assertEqual(controller.api("/api/enrollment/status")["stage"],"PERSON")
        controller.action("/api/enrollment/person",{"first_name":"Ada","last_name":"Lovelace","cedula":"1710034065"})
        self.assertEqual(controller.api("/api/enrollment/status")["stage"],"PREPARATION")
        controller.action("/api/enrollment/capture/start",{})
        current[0]=EnrollmentProgressDTO(UIState.ENROLLING,"MIRE AL FRENTE",3,5,(),82.4,"GOOD",True)
        status=controller.api("/api/enrollment/status")
        self.assertEqual((status["stage"],status["accepted_samples"]),("CAPTURE",3))
        self.assertFalse(any(word in str(status).lower() for word in ("embedding","template","hash","landmark")))
        current[0]=EnrollmentResultDTO(UIState.ENROLLMENT_COMPLETE,"p","Ada","Lovelace","Ada Lovelace",5,0,85,80,90,"enrolled",True,True,"ok")
        self.assertEqual(controller.api("/api/enrollment/status")["stage"],"PHOTO")
        controller.action("/api/enrollment/photo",{"action":"SKIP"})
        self.assertEqual(controller.api("/api/enrollment/status")["stage"],"CONFIRMATION")
        controller.action("/api/enrollment/confirm",{})
        self.assertTrue(controller.api("/api/enrollment/status")["success"])

    def test_enrollment_cancel_resets_web_state_and_calls_rollback_boundary(self):
        cancelled=[]
        controller=WebDashboardController(lambda:None,
            presentation_provider=lambda:monitoring("UNKNOWN",True,None,None),
            actions={"enrollment_cancel":lambda payload:cancelled.append(True)})
        controller.action("/api/enrollment/start",{})
        controller.action("/api/enrollment/cancel",{})
        self.assertFalse(controller.api("/api/enrollment/status")["active"])
        self.assertEqual(cancelled,[True])


if __name__ == "__main__":
    unittest.main()

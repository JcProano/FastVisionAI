from __future__ import annotations

import inspect
import tempfile
import unittest
import uuid
from pathlib import Path

from src.core.person_database import PersonCreateRequest, PersonRepository, PersonStatus
from src.engine.enrollment import EnrollmentPolicy, EnrollmentService
from src.engine.gallery import FaceGallery, FaceMatcher, MatchPolicy
from src.engine.recognition import RecognitionPolicy, RecognitionService
from src.ui.form_validation import validate_registration_form
from src.ui.identification_semantics import IdentificationVisualState, identification_visual_state
from src.ui.people.controller import PeopleManagerController
from src.ui.people.database_controller import DatabasePeopleManagerController
from src.ui.person_enrollment import (
    ExistingDisabledPersonError, PersonEnrollmentCoordinator, PersonEnrollmentState,
)
from src.ui.enrollment_workflow import LocalEnrollmentWorkflow
from src.ui.tk_app import LocalFaceTkApp
from src.engine.gallery.persistence import GalleryPersistence
from tests.test_face_gallery import GalleryTestCase


class RC229ExistingCivilBiometricsTests(GalleryTestCase):
    def setUp(self):
        super().setUp()
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.repository=PersonRepository(self.root/"people.db");self.repository.initialize()
        self.person_id=str(uuid.uuid4())
        self.repository.create(PersonCreateRequest(
            self.person_id,"1710034065","Civil","Existing",
        ))
        self.gallery=FaceGallery()
        self.workflow=LocalEnrollmentWorkflow(
            self.gallery,EnrollmentService(self.gallery,EnrollmentPolicy(5,5)),5,
        )

    def registration(self):
        return validate_registration_form(
            "Civil","Existing",None,consent_confirmed=True,persist_locally=True,
            cedula="1710034065",id_factory=lambda:str(uuid.uuid4()),
        )

    def samples(self):
        return tuple(self.embedding([1.0,index/100.0]) for index in range(5))

    def test_disabled_civil_person_is_explicit_and_never_duplicated(self):
        self.repository.set_status(self.person_id,PersonStatus.DISABLED)
        coordinator=PersonEnrollmentCoordinator(
            self.repository,self.gallery,self.workflow,
        )
        with self.assertRaises(ExistingDisabledPersonError) as raised:
            coordinator.begin(self.registration())
        self.assertEqual(raised.exception.person_id,self.person_id)
        self.assertEqual(self.repository.count(),1)
        self.assertIs(coordinator.state,PersonEnrollmentState.IDLE)

    def test_explicit_reactivation_enables_first_identity_for_same_uuid(self):
        self.repository.set_status(self.person_id,PersonStatus.DISABLED)
        biometrics=PeopleManagerController(
            self.gallery,EnrollmentService(self.gallery,EnrollmentPolicy(1,5)),
            GalleryPersistence(enabled=True),self.root/"gallery.json",self.root/"gallery.npz",
        )
        people=DatabasePeopleManagerController(self.repository,biometrics)
        blocked=people.begin_replacement(self.person_id)
        self.assertFalse(blocked.success);self.assertEqual(self.repository.count(),1)
        reactivated=people.set_administrative_status(
            self.person_id,PersonStatus.ACTIVE,confirmed=True,
        )
        started=people.begin_replacement(self.person_id)
        completed=people.complete_additional(
            self.person_id,tuple((item,None) for item in self.samples()),
        )
        self.assertTrue(reactivated.success);self.assertTrue(started.success)
        self.assertTrue(completed.success);self.assertEqual(self.repository.count(),1)
        self.assertEqual(self.gallery.list_identities()[0].person_id,self.person_id)
        self.assertEqual(len(self.gallery.templates(self.person_id)),5)

    def test_matcher_sees_new_templates_without_inventing_match(self):
        self.repository.set_status(self.person_id,PersonStatus.ACTIVE)
        biometrics=PeopleManagerController(
            self.gallery,EnrollmentService(self.gallery,EnrollmentPolicy(1,5)),
            GalleryPersistence(enabled=True),self.root/"gallery.json",self.root/"gallery.npz",
        )
        people=DatabasePeopleManagerController(self.repository,biometrics)
        people.begin_replacement(self.person_id)
        samples=self.samples()
        self.assertTrue(people.complete_additional(
            self.person_id,tuple((item,None) for item in samples)).success)
        recognition=RecognitionService(
            self.gallery,FaceMatcher(policy=MatchPolicy(False,None)),RecognitionPolicy(top_k=1),
        )
        result=recognition.recognize(samples[0])
        self.assertEqual(result.state.name,"NOT_EVALUATED")
        self.assertEqual(result.primary_candidate.person_id,self.person_id)
        self.assertFalse(result.evaluated)

    def test_popup_semantics_remain_evaluation_gated(self):
        self.assertIs(identification_visual_state("NOT_EVALUATED",False,self.person_id),
                      IdentificationVisualState.BIOMETRIC_CANDIDATE)
        self.assertIs(identification_visual_state("MATCH",True,self.person_id),
                      IdentificationVisualState.IDENTIFIED)
        self.assertIs(identification_visual_state("UNKNOWN",True,None),
                      IdentificationVisualState.UNREGISTERED)

    def test_conflict_ui_routes_zero_template_person_to_replacement(self):
        source=inspect.getsource(LocalFaceTkApp.show_enrollment_conflict)
        self.assertIn("PERSONA SIN ROSTRO REGISTRADO",source)
        self.assertIn("REGISTRAR / ACTUALIZAR ROSTRO",source)
        self.assertIn("_start_conflict_replacement",source)
        self.assertIn("PERSONA DESHABILITADA",source)
        self.assertIn("REACTIVAR PERSONA",source)


if __name__ == "__main__":unittest.main()

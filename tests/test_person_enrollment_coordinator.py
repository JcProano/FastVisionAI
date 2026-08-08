import tempfile
import unittest
import uuid
from pathlib import Path

from src.core.person_database import PersonRepository, PersonStatus
from src.engine.gallery import FaceGallery, FaceIdentity
from src.ui.contracts import EnrollmentProgressDTO, EnrollmentResultDTO, RegistrationFormData, UIState
from src.ui.person_enrollment import (
    PersonEnrollmentCoordinationError, PersonEnrollmentCoordinator, PersonEnrollmentState,
)


def form():
    return RegistrationFormData(
        "Temporary", "Person", "Temporary Person", str(uuid.uuid4()), None,
        True, False, "1710034065",
    )


def result(person_id, enrolled=True):
    return EnrollmentResultDTO(
        UIState.ENROLLMENT_COMPLETE if enrolled else UIState.ENROLLMENT_REJECTED,
        person_id, "Temporary", "Person", "Temporary Person", 1 if enrolled else 0,
        0, 90, 90, 90, "enrolled" if enrolled else "rejected", False, None, "done",
    )


class Workflow:
    def __init__(self, gallery, *, start_error=False, enrolled=True):
        self.gallery = gallery; self.start_error = start_error; self.enrolled = enrolled
        self.active = False; self.current = None
    def start(self, registration):
        if self.start_error: raise RuntimeError("controlled start")
        self.active = True; self.current = registration
        return EnrollmentProgressDTO(UIState.ENROLLING, "front", 0, 1, (), None, None, True)
    def cancel(self): self.active = False
    def commit_biometric(self, *, minimal_identity_metadata=False):
        self.active = False
        if self.enrolled:
            self.gallery.register_identity(FaceIdentity(
                self.current.person_id, self.current.display_name, {}
            ))
        return result(self.current.person_id, self.enrolled)


class StatusFailureRepository(PersonRepository):
    commit_first = False
    def set_status(self, person_id, status):
        if self.commit_first: super().set_status(person_id, status)
        raise RuntimeError("controlled activation failure")


class DeleteFailureRepository(PersonRepository):
    def delete_pending(self, person_id): raise RuntimeError("controlled delete failure")


class StatusAndDeleteFailureRepository(StatusFailureRepository):
    def delete_pending(self, person_id): raise RuntimeError("controlled delete failure")


class GalleryRemovalFailure(FaceGallery):
    def remove_identity(self, person_id): return False


class CoordinatorTests(unittest.TestCase):
    def make(self, repository_type=PersonRepository, gallery=None, **workflow):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        repository = repository_type(Path(temporary.name) / "people.db"); repository.initialize()
        gallery = gallery if gallery is not None else FaceGallery()
        flow = Workflow(gallery, **workflow)
        return repository, gallery, flow, PersonEnrollmentCoordinator(repository, gallery, flow)

    def test_reserve_cancel_and_rejected_remove_pending(self):
        repository, _, _, coordinator = self.make()
        registration = form(); coordinator.begin(registration)
        self.assertEqual(repository.get_by_person_id(registration.person_id).status,
                         PersonStatus.PENDING_BIOMETRIC)
        coordinator.cancel(); self.assertIsNone(repository.get_by_person_id(registration.person_id))
        repository, _, _, coordinator = self.make(enrolled=False)
        registration = form(); coordinator.begin(registration); outcome = coordinator.commit()
        self.assertEqual(outcome.enrollment_status, "rejected")
        self.assertIsNone(repository.get_by_person_id(registration.person_id))

    def test_start_failure_cleans_reservation(self):
        repository, _, _, coordinator = self.make(start_error=True)
        registration = form()
        with self.assertRaises(RuntimeError): coordinator.begin(registration)
        self.assertIsNone(repository.get_by_person_id(registration.person_id))

    def test_enrolled_activates_and_exception_after_commit_is_verified(self):
        for repository_type, commit_first in ((PersonRepository, False),
                                               (StatusFailureRepository, True)):
            repository, gallery, _, coordinator = self.make(repository_type)
            if isinstance(repository, StatusFailureRepository): repository.commit_first = commit_first
            registration = form(); coordinator.begin(registration); outcome = coordinator.commit()
            self.assertEqual(outcome.coordination_state, "ACTIVE")
            self.assertEqual(repository.get_by_person_id(registration.person_id).status,
                             PersonStatus.ACTIVE)
            self.assertTrue(gallery.list_identities())
            self.assertEqual(coordinator.state, PersonEnrollmentState.IDLE)

    def test_pending_activation_failure_rolls_back_both(self):
        repository, gallery, _, coordinator = self.make(StatusFailureRepository)
        registration = form(); coordinator.begin(registration)
        with self.assertRaises(PersonEnrollmentCoordinationError): coordinator.commit()
        self.assertFalse(gallery.list_identities())
        self.assertIsNone(repository.get_by_person_id(registration.person_id))

    def test_failed_gallery_or_pending_cleanup_is_inconsistent(self):
        for repository_type, gallery in (
            (StatusFailureRepository, GalleryRemovalFailure()),
            (StatusAndDeleteFailureRepository, FaceGallery()),
        ):
            repository, gallery, _, coordinator = self.make(repository_type, gallery)
            registration = form(); coordinator.begin(registration); outcome = coordinator.commit()
            self.assertEqual(outcome.coordination_state, PersonEnrollmentState.INCONSISTENT.value)
            self.assertEqual(coordinator.state, PersonEnrollmentState.INCONSISTENT)


if __name__ == "__main__": unittest.main()

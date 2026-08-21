import unittest
import uuid

from src.core.people.application import (
    CommitPersonEnrollmentUseCase,
    PersonEnrollmentSession,
)
from src.core.people.domain import (
    PersonCreateRequest,
    PersonEnrollmentCoordinationError,
    PersonEnrollmentState,
    PersonStatus,
)
from tests.core.people.fakes import (
    FakeEnrollmentResultEditor,
    FakeEnrollmentWorkflow,
    FakeGallery,
    FakeRegistration,
    InMemoryPeopleRepository,
)


class CommitPersonEnrollmentUseCaseTests(unittest.TestCase):
    def make(self):
        person_id = str(uuid.uuid4())
        repository = InMemoryPeopleRepository()
        repository.create(
            PersonCreateRequest(person_id, "1710034065", "Temporary", "Person")
        )
        gallery = FakeGallery()
        workflow = FakeEnrollmentWorkflow(gallery)
        workflow.registration = FakeRegistration(person_id)
        workflow.active = True
        session = PersonEnrollmentSession()
        session.state = PersonEnrollmentState.ENROLLING
        session.reserved_person_id = person_id
        audits = []
        use_case = CommitPersonEnrollmentUseCase(
            repository,
            gallery,
            workflow,
            FakeEnrollmentResultEditor(),
            session,
            lambda event, payload: audits.append((event, payload)),
        )
        return person_id, repository, gallery, workflow, session, audits, use_case

    def test_activates_civil_data_only_after_biometric_commit(self) -> None:
        person_id, repository, gallery, _, session, audits, use_case = self.make()

        result = use_case.execute()

        self.assertEqual(result.coordination_state, "ACTIVE")
        self.assertIs(
            repository.get_by_person_id(person_id).status, PersonStatus.ACTIVE
        )
        self.assertIn(person_id, gallery.identities)
        self.assertIs(session.state, PersonEnrollmentState.IDLE)
        self.assertEqual(audits[0][0], "PERSON_CREATED")

    def test_rejected_biometrics_remove_the_pending_person(self) -> None:
        person_id, repository, _, workflow, session, _, use_case = self.make()
        workflow.enrolled = False

        result = use_case.execute()

        self.assertEqual(result.enrollment_status, "rejected")
        self.assertIsNone(repository.get_by_person_id(person_id))
        self.assertIs(session.state, PersonEnrollmentState.IDLE)

    def test_activation_failure_compensates_both_sides(self) -> None:
        person_id, repository, gallery, _, session, _, use_case = self.make()
        repository.fail_status_change = True

        with self.assertRaises(PersonEnrollmentCoordinationError):
            use_case.execute()

        self.assertNotIn(person_id, gallery.identities)
        self.assertIsNone(repository.get_by_person_id(person_id))
        self.assertIs(session.state, PersonEnrollmentState.IDLE)

    def test_failed_gallery_compensation_is_explicitly_inconsistent(self) -> None:
        _, repository, gallery, _, session, _, use_case = self.make()
        repository.fail_status_change = True
        gallery.removal_succeeds = False

        result = use_case.execute()

        self.assertEqual(result.enrollment_status, "inconsistent")
        self.assertIs(session.state, PersonEnrollmentState.INCONSISTENT)


if __name__ == "__main__":
    unittest.main()

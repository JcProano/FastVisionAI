import unittest
import uuid

from src.core.people.application import (
    BeginPersonEnrollmentUseCase,
    PersonEnrollmentSession,
)
from src.core.people.domain import ExistingActivePersonError, PersonEnrollmentState
from tests.core.people.fakes import (
    FakeEnrollmentWorkflow,
    FakeGallery,
    FakeRegistration,
    InMemoryPeopleRepository,
    person_record,
)


class BeginPersonEnrollmentUseCaseTests(unittest.TestCase):
    def make(self, repository=None):
        repository = repository or InMemoryPeopleRepository()
        gallery = FakeGallery()
        workflow = FakeEnrollmentWorkflow(gallery)
        session = PersonEnrollmentSession()
        use_case = BeginPersonEnrollmentUseCase(
            repository, gallery, workflow, session
        )
        return repository, gallery, workflow, session, use_case

    def test_reserves_the_person_before_starting_biometrics(self) -> None:
        repository, _, workflow, session, use_case = self.make()
        form = FakeRegistration(str(uuid.uuid4()))

        progress = use_case.execute(form)

        self.assertEqual(progress, "capture-started")
        self.assertIsNotNone(repository.get_by_person_id(form.person_id))
        self.assertIs(workflow.registration, form)
        self.assertIs(session.state, PersonEnrollmentState.ENROLLING)

    def test_existing_active_cedula_is_reported_without_a_second_insert(self) -> None:
        existing = person_record()
        repository, _, _, session, use_case = self.make(
            InMemoryPeopleRepository((existing,))
        )

        with self.assertRaises(ExistingActivePersonError):
            use_case.execute(FakeRegistration(str(uuid.uuid4()), existing.cedula))

        self.assertEqual(len(repository.records), 1)
        self.assertIs(session.state, PersonEnrollmentState.IDLE)

    def test_start_failure_removes_the_pending_reservation(self) -> None:
        repository, _, workflow, session, use_case = self.make()
        workflow.start_error = True
        form = FakeRegistration(str(uuid.uuid4()))

        with self.assertRaises(RuntimeError):
            use_case.execute(form)

        self.assertIsNone(repository.get_by_person_id(form.person_id))
        self.assertIsNone(session.reserved_person_id)


if __name__ == "__main__":
    unittest.main()

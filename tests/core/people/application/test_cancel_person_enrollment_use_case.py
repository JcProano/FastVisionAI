import unittest
import uuid

from src.core.people.application import (
    CancelPersonEnrollmentUseCase,
    PersonEnrollmentSession,
)
from src.core.people.domain import PersonCreateRequest, PersonEnrollmentState
from tests.core.people.fakes import (
    FakeEnrollmentWorkflow,
    FakeGallery,
    InMemoryPeopleRepository,
)


class CancelPersonEnrollmentUseCaseTests(unittest.TestCase):
    def test_cancels_biometrics_and_removes_the_pending_person(self) -> None:
        repository = InMemoryPeopleRepository()
        person_id = str(uuid.uuid4())
        repository.create(
            PersonCreateRequest(person_id, "1710034065", "Temporary", "Person")
        )
        workflow = FakeEnrollmentWorkflow(FakeGallery())
        workflow.active = True
        session = PersonEnrollmentSession()
        session.state = PersonEnrollmentState.ENROLLING
        session.reserved_person_id = person_id

        CancelPersonEnrollmentUseCase(repository, workflow, session).execute()

        self.assertFalse(workflow.active)
        self.assertIsNone(repository.get_by_person_id(person_id))
        self.assertIs(session.state, PersonEnrollmentState.IDLE)


if __name__ == "__main__":
    unittest.main()

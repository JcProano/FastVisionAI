import unittest
import uuid

from src.core.people.application import CreatePersonUseCase
from src.core.people.domain import PersonCreateRequest, PersonStatus
from tests.core.people.fakes import InMemoryPeopleRepository


class CreatePersonUseCaseTests(unittest.TestCase):
    def test_creates_a_pending_person_through_the_repository_port(self) -> None:
        repository = InMemoryPeopleRepository()
        request = PersonCreateRequest(
            str(uuid.uuid4()), "1710034065", " Ana ", " Pérez "
        )

        result = CreatePersonUseCase(repository).execute(request)

        self.assertIs(result.status, PersonStatus.PENDING_BIOMETRIC)
        self.assertEqual(result.first_name, "Ana")
        self.assertEqual(repository.created_requests, [request])


if __name__ == "__main__":
    unittest.main()

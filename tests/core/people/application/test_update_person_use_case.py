import unittest

from src.core.people.application import UpdatePersonUseCase
from src.core.people.domain import PersonUpdateRequest
from tests.core.people.fakes import InMemoryPeopleRepository, person_record


class UpdatePersonUseCaseTests(unittest.TestCase):
    def test_updates_only_validated_civil_fields(self) -> None:
        person = person_record()
        repository = InMemoryPeopleRepository((person,))
        request = PersonUpdateRequest(person.person_id, first_name="Updated")

        result = UpdatePersonUseCase(repository).execute(request)

        self.assertEqual(result.first_name, "Updated")
        self.assertEqual(repository.updated_requests, [request])


if __name__ == "__main__":
    unittest.main()

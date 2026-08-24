import unittest

from src.core.people.application import GetPersonUseCase
from tests.core.people.fakes import InMemoryPeopleRepository, person_record


class GetPersonUseCaseTests(unittest.TestCase):
    def test_returns_the_person_without_exposing_a_database_dependency(self) -> None:
        person = person_record()
        use_case = GetPersonUseCase(InMemoryPeopleRepository((person,)))

        self.assertIs(use_case.execute(person.person_id), person)
        self.assertIsNone(use_case.execute("missing"))


if __name__ == "__main__":
    unittest.main()

import unittest

from src.core.people.application import SearchPeopleUseCase
from src.core.people.domain import PersonSearchQuery, PersonStatus
from tests.core.people.fakes import InMemoryPeopleRepository, person_record


class SearchPeopleUseCaseTests(unittest.TestCase):
    def test_passes_an_explicit_query_to_the_read_port(self) -> None:
        active = person_record(status=PersonStatus.ACTIVE)
        pending = person_record(
            cedula="0926687856", status=PersonStatus.PENDING_BIOMETRIC
        )
        repository = InMemoryPeopleRepository((active, pending))
        query = PersonSearchQuery(status=PersonStatus.ACTIVE)

        result = SearchPeopleUseCase(repository).execute(query)

        self.assertEqual(result, (active,))
        self.assertEqual(repository.search_queries, [query])


if __name__ == "__main__":
    unittest.main()

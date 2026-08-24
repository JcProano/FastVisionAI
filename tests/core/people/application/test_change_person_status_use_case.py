import unittest

from src.core.people.application import ChangePersonStatusUseCase
from src.core.people.domain import (
    PersonNotFoundError,
    PersonStatus,
    PersonStatusTransitionError,
)
from tests.core.people.fakes import InMemoryPeopleRepository, person_record


class ChangePersonStatusUseCaseTests(unittest.TestCase):
    def test_allows_only_active_disabled_transitions(self) -> None:
        person = person_record(status=PersonStatus.ACTIVE)
        repository = InMemoryPeopleRepository((person,))
        use_case = ChangePersonStatusUseCase(repository)

        disabled = use_case.execute(person.person_id, PersonStatus.DISABLED)
        active = use_case.execute(person.person_id, PersonStatus.ACTIVE)

        self.assertIs(disabled.status, PersonStatus.DISABLED)
        self.assertIs(active.status, PersonStatus.ACTIVE)

    def test_rejects_missing_people_and_pending_transitions(self) -> None:
        pending = person_record(status=PersonStatus.PENDING_BIOMETRIC)
        use_case = ChangePersonStatusUseCase(
            InMemoryPeopleRepository((pending,))
        )

        with self.assertRaises(PersonStatusTransitionError):
            use_case.execute(pending.person_id, PersonStatus.ACTIVE)
        with self.assertRaises(PersonNotFoundError):
            use_case.execute("missing", PersonStatus.ACTIVE)


if __name__ == "__main__":
    unittest.main()

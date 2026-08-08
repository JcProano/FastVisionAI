"""Local registered-people manager."""

from src.ui.people.contracts import (
    PeopleListDTO, PeopleManagerState, PeopleOperationResultDTO,
    PersonDetailsDTO, PersonSummaryDTO,
)
from src.ui.people.controller import PeopleManagerController

__all__ = [
    "PeopleListDTO", "PeopleManagerController", "PeopleManagerState",
    "PeopleOperationResultDTO", "PersonDetailsDTO", "PersonSummaryDTO",
]

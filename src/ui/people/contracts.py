"""Safe contracts for the local registered-people manager."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class PeopleManagerState(str, Enum):
    IDLE = "idle"
    LOADING = "loading"
    EDITING = "editing"
    ENROLLING_MORE = "enrolling_more"
    DELETING = "deleting"
    SAVING = "saving"
    IMPORTING = "importing"
    EXPORTING = "exporting"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class PersonSummaryDTO:
    person_id: str
    first_name: str
    last_name: str
    display_name: str
    external_identifier: str | None
    template_count: int
    scored_template_count: int
    unscored_template_count: int
    average_quality: float | None
    minimum_quality: float | None
    maximum_quality: float | None
    created_at: datetime | None


@dataclass(frozen=True, slots=True)
class PersonDetailsDTO:
    summary: PersonSummaryDTO
    quality_profile_names: tuple[str, ...]
    quality_profile_versions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PeopleListDTO:
    state: PeopleManagerState
    query: str
    people: tuple[PersonSummaryDTO, ...]
    total_identities: int
    total_templates: int


@dataclass(frozen=True, slots=True)
class PeopleOperationResultDTO:
    state: PeopleManagerState
    success: bool
    operation: str
    message: str
    person_id: str | None = None
    affected_templates: int = 0
    identity_count: int | None = None
    template_count: int | None = None


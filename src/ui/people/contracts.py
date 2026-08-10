"""Safe contracts for the local registered-people manager."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
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
    cedula: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    birth_date: str | None = None
    sex: str | None = None
    notes: str | None = None
    civil_status: str | None = None


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
    timestamp: datetime | None = None

    def __post_init__(self) -> None:
        if self.timestamp is not None and self.timestamp.tzinfo is None:
            raise ValueError("operation timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class PeopleSearchFiltersDTO:
    text: str = ""
    cedula: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    email: str | None = None
    administrative_status: str = "TODOS"
    created_from: date | None = None
    created_to: date | None = None
    limit: int = 25
    offset: int = 0
    sort_by: str = "updated_at"
    sort_direction: str = "DESC"

    def __post_init__(self) -> None:
        if self.administrative_status not in {
            "TODOS", "ACTIVE", "DISABLED", "PENDING_BIOMETRIC",
        }:
            raise ValueError("administrative status is invalid")
        if self.limit <= 0 or self.offset < 0:
            raise ValueError("search pagination is invalid")
        if self.sort_by not in {
            "created_at", "updated_at", "first_name", "last_name", "status",
        }:
            raise ValueError("search sort field is invalid")
        if self.sort_direction not in {"ASC", "DESC"}:
            raise ValueError("search sort direction is invalid")
        if self.created_from and self.created_to and self.created_from > self.created_to:
            raise ValueError("search date range is invalid")


@dataclass(frozen=True, slots=True)
class PeopleSearchResultDTO:
    person_id: str
    first_name: str
    last_name: str
    display_name: str
    masked_cedula: str
    phone: str | None
    email: str | None
    status: str
    template_count: int
    quality_summary: str | None
    thumbnail_available: bool
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PeopleSearchPageDTO:
    people: tuple[PeopleSearchResultDTO, ...]
    page: int
    page_size: int
    total: int
    first_item: int
    last_item: int
    has_previous: bool
    has_next: bool
    message: str
    success: bool = True

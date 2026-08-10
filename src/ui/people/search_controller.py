"""Advanced, bounded SQLite people search for the administrative UI."""
from __future__ import annotations
from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.core.person_database import PersonStatus

from .contracts import (
    PeopleSearchFiltersDTO, PeopleSearchPageDTO, PeopleSearchResultDTO,
)


@dataclass(frozen=True, slots=True)
class PeopleSearchPolicy:
    default_page_size: int = 25
    allowed_page_sizes: tuple[int, ...] = (25, 50, 100)
    debounce_ms: int = 400
    presentation_timezone: str = "America/Guayaquil"

    def __post_init__(self) -> None:
        if (not self.allowed_page_sizes or any(value <= 0 for value in self.allowed_page_sizes)
                or self.default_page_size not in self.allowed_page_sizes):
            raise ValueError("people search page sizes are invalid")
        if self.debounce_ms < 0: raise ValueError("people search debounce is invalid")
        try: ZoneInfo(self.presentation_timezone)
        except ZoneInfoNotFoundError as exc: raise ValueError("people search timezone is invalid") from exc


class AdvancedPeopleSearchController:
    def __init__(self, database_controller, thumbnail_manager=None,
                 policy: PeopleSearchPolicy | None = None) -> None:
        self.database = database_controller
        self.repository = database_controller.repository
        self.thumbnails = thumbnail_manager
        self.policy = policy or PeopleSearchPolicy()
        self.timezone = ZoneInfo(self.policy.presentation_timezone)

    def search(self, filters: PeopleSearchFiltersDTO) -> PeopleSearchPageDTO:
        return self._search(filters, enforce_page_size=True)

    def _search(
        self, filters: PeopleSearchFiltersDTO, *, enforce_page_size: bool,
    ) -> PeopleSearchPageDTO:
        if enforce_page_size and filters.limit not in self.policy.allowed_page_sizes:
            raise ValueError("page size is not allowed")
        if not enforce_page_size and not 1 <= filters.limit <= 100:
            raise ValueError("recent search limit is invalid")
        try:
            arguments = self._arguments(filters)
            rows = self.repository.advanced_search(
                **arguments, limit=filters.limit, offset=filters.offset,
                sort_by=filters.sort_by, sort_direction=filters.sort_direction,
            )
            total = self.repository.count_advanced(**arguments)
            people = tuple(self._result(row) for row in rows)
            page = filters.offset // filters.limit + 1
            first = filters.offset + 1 if people else 0
            last = filters.offset + len(people) if people else 0
            message = (f"Mostrando {first}–{last} de {total}" if people
                       else "Mostrando 0 de 0")
            return PeopleSearchPageDTO(
                people, page, filters.limit, total, first, last, page > 1,
                last < total, message,
            )
        except ValueError: raise
        except Exception:
            return PeopleSearchPageDTO(
                (), max(1, filters.offset // filters.limit + 1), filters.limit,
                0, 0, 0, filters.offset > 0, False,
                "No se pudo consultar personas.", False,
            )

    def paginate(self, filters: PeopleSearchFiltersDTO, page: int) -> PeopleSearchPageDTO:
        if page <= 0: raise ValueError("page must be positive")
        return self.search(replace(filters, offset=(page - 1) * filters.limit))

    def list_recent(self, limit: int) -> PeopleSearchPageDTO:
        return self._search(PeopleSearchFiltersDTO(
            limit=limit, sort_by="created_at", sort_direction="DESC",
        ), enforce_page_size=False)

    def list_by_status(self, status: PersonStatus) -> PeopleSearchPageDTO:
        if not isinstance(status, PersonStatus): raise ValueError("status is invalid")
        return self.search(PeopleSearchFiltersDTO(
            administrative_status=status.value, limit=self.policy.default_page_size,
        ))

    def resolve_by_cedula(self, cedula: str) -> PeopleSearchResultDTO | None:
        try: record = self.repository.get_by_cedula(cedula)
        except Exception: return None
        return None if record is None else self._result(record)

    def resolve_by_person_id(self, person_id: str) -> PeopleSearchResultDTO | None:
        try: record = self.repository.get_by_person_id(person_id)
        except Exception: return None
        return None if record is None else self._result(record)

    def set_status(self, person_id: str, target_status: PersonStatus, confirmed: bool):
        return self.database.set_administrative_status(
            person_id, target_status, confirmed=confirmed,
        )

    def _arguments(self, filters: PeopleSearchFiltersDTO) -> dict[str, object]:
        status = (None if filters.administrative_status == "TODOS"
                  else PersonStatus(filters.administrative_status))
        created_from = (None if filters.created_from is None else datetime.combine(
            filters.created_from, time.min, self.timezone,
        ).astimezone(timezone.utc))
        created_to = (None if filters.created_to is None else datetime.combine(
            filters.created_to + timedelta(days=1), time.min, self.timezone,
        ).astimezone(timezone.utc))
        return {
            "text": filters.text, "cedula": filters.cedula,
            "first_name": filters.first_name, "last_name": filters.last_name,
            "phone": filters.phone, "email": filters.email, "status": status,
            "created_from": created_from, "created_to": created_to,
        }

    def _result(self, record) -> PeopleSearchResultDTO:
        template_count = 0; quality = None
        try:
            summary = self.database.biometrics.details(record.person_id).summary
            template_count = summary.template_count
            if summary.average_quality is not None:
                quality = f"{summary.average_quality:.1f}"
        except Exception: pass
        thumbnail = False
        if self.thumbnails is not None:
            try: thumbnail = bool(self.thumbnails.exists(record.person_id))
            except Exception: thumbnail = False
        return PeopleSearchResultDTO(
            record.person_id, record.first_name, record.last_name,
            f"{record.first_name} {record.last_name}",
            "N/D" if not record.cedula else "******" + record.cedula[-4:],
            record.phone, record.email, record.status.value, template_count, quality,
            thumbnail, record.updated_at.astimezone(self.timezone),
        )

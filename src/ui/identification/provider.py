"""Current UI-only identity information provider implementation."""

from __future__ import annotations

from src.ui.identification.contracts import IdentityPersonDTO
from src.ui.people.controller import PeopleManagerController
from src.ui.thumbnails import ThumbnailDTO, ThumbnailManager


class PeopleThumbnailIdentityInfoProvider:
    def __init__(
        self, people: PeopleManagerController, thumbnails: ThumbnailManager,
    ) -> None:
        self._people = people
        self._thumbnails = thumbnails

    def get_person(self, person_id: str) -> IdentityPersonDTO | None:
        try:
            item = self._people.details(person_id).summary
            return IdentityPersonDTO(
                item.person_id, item.first_name, item.last_name, item.display_name,
                item.external_identifier, legacy_without_civil_data=True,
            )
        except Exception:
            return None

    def get_thumbnail(self, person_id: str) -> ThumbnailDTO:
        return self._thumbnails.load(person_id)

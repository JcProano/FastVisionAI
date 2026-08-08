from __future__ import annotations

from src.core.person_database import PersonStatus, SQLiteIdentityDataProvider
from src.engine.gallery import FaceGallery
from src.ui.thumbnails import ThumbnailDTO, ThumbnailManager

from .contracts import IdentityPersonDTO


class SQLiteThumbnailIdentityInfoProvider:
    def __init__(self, civil: SQLiteIdentityDataProvider, thumbnails: ThumbnailManager,
                 gallery: FaceGallery) -> None:
        self._civil = civil
        self._thumbnails = thumbnails
        self._gallery = gallery

    def get_person(self, person_id: str) -> IdentityPersonDTO | None:
        record = self._civil.get_by_person_id(person_id)
        if record is not None:
            if record.status is not PersonStatus.ACTIVE:
                return None
            return IdentityPersonDTO(
                record.person_id, record.first_name, record.last_name,
                f"{record.first_name} {record.last_name}", record.cedula,
                record.address, record.phone, record.email, record.status.value,
            )
        if any(item.person_id == person_id for item in self._gallery.list_identities()):
            return IdentityPersonDTO(
                person_id, "", "", "Registro biométrico heredado sin datos civiles",
                None, legacy_without_civil_data=True,
            )
        return None

    def get_thumbnail(self, person_id: str) -> ThumbnailDTO:
        return self._thumbnails.load(person_id)

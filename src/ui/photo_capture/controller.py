"""Defense-in-depth controller for visual thumbnail capture."""

from __future__ import annotations

from src.core.person_database import PersonRepository
from src.core.security import AuthorizationPermission
from src.ui.thumbnails import ThumbnailDTO, ThumbnailManager


class PersonPhotoController:
    def __init__(self, repository: PersonRepository, thumbnails: ThumbnailManager,
                 authorization=None) -> None:
        self.repository = repository
        self.thumbnails = thumbnails
        self.authorization = authorization

    def begin(self, person_id: str) -> bool:
        self._require()
        if self.repository.get_by_person_id(person_id) is None:
            raise KeyError("unknown person_id")
        if not self.thumbnails.enabled:
            raise RuntimeError("thumbnail storage is disabled")
        return self.thumbnails.exists(person_id)

    def save(self, person_id: str, image_bytes: bytes, *, replace: bool) -> ThumbnailDTO:
        self._require()
        if self.repository.get_by_person_id(person_id) is None:
            raise KeyError("unknown person_id")
        return self.thumbnails.save(person_id, image_bytes, replace=replace)

    def _require(self) -> None:
        if self.authorization is not None and not self.authorization.can(
            AuthorizationPermission.EDIT_PERSON
        ):
            raise PermissionError("operation is not authorized")

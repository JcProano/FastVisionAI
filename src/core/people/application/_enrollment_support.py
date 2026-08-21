"""Shared compensation helpers for enrollment use cases."""

from __future__ import annotations

from ..domain.errors import PersonEnrollmentCoordinationError
from ..domain.ports import BiometricGalleryPort, PeopleRepositoryPort


def gallery_contains(gallery: BiometricGalleryPort, person_id: str) -> bool:
    return any(
        identity.person_id == person_id for identity in gallery.list_identities()
    ) or bool(gallery.templates(person_id))


def delete_pending_verified(
    repository: PeopleRepositoryPort, person_id: str | None
) -> None:
    if person_id is None:
        return
    if not repository.delete_pending(person_id):
        raise PersonEnrollmentCoordinationError(
            "pending reservation could not be removed"
        )
    if repository.get_by_person_id(person_id) is not None:
        raise PersonEnrollmentCoordinationError(
            "pending reservation removal was not verified"
        )

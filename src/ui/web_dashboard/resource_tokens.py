"""Opaque, bounded references for dashboard images and person commands."""

from __future__ import annotations

import hashlib
import secrets
import threading
from collections import OrderedDict


class WebResourceTokenStore:
    """Keep internal identifiers and image bytes out of public API payloads."""

    def __init__(self, identity_provider=None, *, capacity: int = 512) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._identity_provider = identity_provider
        self._capacity = capacity
        self._salt = secrets.token_bytes(32)
        self._people: OrderedDict[str, str] = OrderedDict()
        self._photos: OrderedDict[str, tuple[str, bytes]] = OrderedDict()
        self._lock = threading.Lock()

    def photo_url(self, photo) -> str | None:
        if not photo.available or not photo.image_bytes:
            return None
        payload = bytes(photo.image_bytes)
        token = self._token(payload)
        with self._lock:
            self._remember(self._photos, token, (_mime(photo.format), payload))
        return f"/api/thumbnails/{token}"

    def person_token(self, person_id: str) -> str:
        token = self._token(person_id.encode("utf-8"))
        with self._lock:
            self._remember(self._people, token, person_id)
        return token

    def resolve_person(self, token: str) -> str:
        self._validate(token)
        with self._lock:
            person_id = self._people.get(token)
            if person_id is not None:
                self._people.move_to_end(token)
        if person_id is None:
            raise ValueError("La persona ya no está disponible.")
        return person_id

    def thumbnail(self, token: str) -> tuple[str, bytes] | None:
        try:
            self._validate(token)
        except ValueError:
            return None
        with self._lock:
            photo = self._photos.get(token)
            person_id = self._people.get(token)
            if photo is not None:
                self._photos.move_to_end(token)
        if photo is not None:
            return photo
        if person_id is None or self._identity_provider is None:
            return None
        value = self._identity_provider.get_thumbnail(person_id)
        if not value.available or not value.image_bytes:
            return None
        return _mime(value.format), bytes(value.image_bytes)

    def _token(self, payload: bytes) -> str:
        return hashlib.sha256(self._salt + payload).hexdigest()

    def _remember(self, collection: OrderedDict, key: str, value: object) -> None:
        collection[key] = value
        collection.move_to_end(key)
        while len(collection) > self._capacity:
            collection.popitem(last=False)

    @staticmethod
    def _validate(token: str) -> None:
        if len(token) != 64 or any(
            character not in "0123456789abcdef" for character in token
        ):
            raise ValueError("Identificador inválido.")


def _mime(value: str) -> str:
    return "image/jpeg" if value.upper() in {"JPG", "JPEG"} else "image/png"

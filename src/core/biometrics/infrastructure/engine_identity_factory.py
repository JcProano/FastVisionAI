"""Adapter constructing the existing engine gallery identity contract."""

from __future__ import annotations

from typing import Any, Mapping

from src.engine.gallery.contracts import FaceIdentity


class EngineFaceIdentityFactory:
    def create(
        self,
        person_id: str,
        display_name: str,
        metadata: Mapping[str, Any] | None,
    ) -> FaceIdentity:
        return FaceIdentity(person_id, display_name, metadata)

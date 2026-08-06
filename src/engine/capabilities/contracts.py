from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Capability:
    id: str
    category: str
    experimental: bool = False

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.category.strip():
            raise ValueError("Capability id and category must be non-empty")

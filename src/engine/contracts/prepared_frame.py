"""Preprocessor output contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.engine.contracts.frame import Frame


@dataclass(frozen=True, slots=True)
class PreparedFrame:
    frame: Frame
    image: Any
    width: int
    height: int

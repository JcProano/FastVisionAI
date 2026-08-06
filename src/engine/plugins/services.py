"""Services injected into plugin factories."""

from __future__ import annotations

from dataclasses import dataclass

from src.engine.models.manager import ModelManager


@dataclass(frozen=True, slots=True)
class PluginServices:
    model_manager: ModelManager

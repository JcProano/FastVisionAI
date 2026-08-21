"""Atomic JSON write, backup rotation and redacted export adapter."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from ..domain.models import (
    ConfigurationError,
    ConfigurationProfile,
    ConfigurationSnapshot,
)
from ..domain.ports import ConfigurationLoaderPort


class AtomicConfigurationStore:
    def __init__(
        self,
        loader: ConfigurationLoaderPort,
        path: Path,
        profile: ConfigurationProfile,
        *,
        replace: Callable[[Path, Path], None] = os.replace,
        rotate: Callable[[Path], None],
        fsync_directory: Callable[[Path], None],
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.loader = loader
        self.path = path
        self.profile = profile
        self._replace = replace
        self._rotate = rotate
        self._fsync_directory = fsync_directory
        self._now = now

    def save(
        self, candidate: dict
    ) -> tuple[ConfigurationSnapshot, str | None]:
        directory = self.path.parent
        directory.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=directory
        )
        temporary = Path(name)
        warning = None
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(candidate, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            self.loader.load(temporary, self.profile)
            backups = directory / "backups"
            backups.mkdir(parents=True, exist_ok=True)
            stamp = self._now().strftime("%Y%m%dT%H%M%S%fZ")
            backup = backups / f"{self.path.stem}.{stamp}.json"
            if self.path.exists():
                shutil.copyfile(self.path, backup)
            self._replace(temporary, self.path)
            try:
                self._fsync_directory(directory)
            except Exception:
                warning = (
                    "La configuración se guardó, pero no se pudo confirmar "
                    "la sincronización del directorio."
                )
            loaded = self.loader.load(self.path, self.profile)
            try:
                self._rotate(backups)
            except Exception:
                warning = (
                    "La configuración se guardó, pero no se pudieron rotar "
                    "todas las copias antiguas."
                )
            return loaded, warning
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def export(
        self,
        value: dict,
        destination: Path,
        *,
        overwrite: bool = False,
    ) -> None:
        if destination.exists() and not overwrite:
            raise ConfigurationError(
                "El destino de exportación ya existe."
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

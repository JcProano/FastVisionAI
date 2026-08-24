"""Composition container for administrative-audit dependencies."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .infrastructure import SQLiteAuditRepository
from .service import AuditService

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AuditComponents:
    repository: object
    service: AuditService


class AuditContainer:
    @staticmethod
    def build(
        settings: dict[str, object],
        project_root: Path,
        *,
        repository_type=SQLiteAuditRepository,
        service_type=AuditService,
    ) -> AuditComponents:
        configuration = settings.get("audit", {})
        if not isinstance(configuration, dict):
            raise ValueError("audit configuration must be an object")
        enabled = bool(configuration.get("enabled", False))
        configured = Path(
            str(
                configuration.get(
                    "database_path", "data/fastvision/audit.db"
                )
            )
        )
        if configured.is_absolute() or ".." in configured.parts:
            raise ValueError(
                "audit database path must be project-relative and safe"
            )
        root = project_root.resolve()
        database = (root / configured).resolve()
        if root not in database.parents:
            raise ValueError("audit database path escapes project root")
        repository = repository_type(
            database,
            timeout=float(configuration.get("sqlite_timeout_seconds", 5.0)),
        )
        service = service_type(
            repository,
            enabled=enabled,
            metadata_max_items=int(
                configuration.get("metadata_max_items", 20)
            ),
            metadata_value_max_length=int(
                configuration.get("metadata_value_max_length", 256)
            ),
            message_max_length=int(
                configuration.get("message_max_length", 500)
            ),
        )
        if enabled:
            try:
                repository.initialize()
            except Exception:
                LOGGER.warning(
                    "Administrative audit initialization failed; "
                    "audit remains unavailable"
                )
                service.enabled = False
        return AuditComponents(repository, service)

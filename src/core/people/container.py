"""Composition container for the civil people repository."""

from pathlib import Path

from .infrastructure import SQLitePeopleRepository


class PeopleContainer:
    @staticmethod
    def build_repository(
        settings: dict[str, object],
        project_root: Path,
        *,
        repository_type=SQLitePeopleRepository,
    ):
        database = settings.get("person_database", {})
        if not isinstance(database, dict):
            raise ValueError("person_database configuration must be an object")
        if not bool(database.get("enabled", False)):
            return None
        configured = Path(
            str(database.get("path", "data/fastvision/people.db"))
        )
        if configured.is_absolute():
            raise ValueError("person database path must be relative")
        root = project_root.resolve()
        resolved = (root / configured).resolve()
        if root not in resolved.parents:
            raise ValueError("person database path escapes project root")
        repository = repository_type(
            resolved, timeout=float(database.get("timeout_seconds", 5.0))
        )
        repository.initialize()
        return repository

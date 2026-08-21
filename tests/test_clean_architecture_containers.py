"""Focused tests for bounded-context composition roots."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import Mock

from src.core.attendance.container import AttendanceContainer
from src.core.audit import AuditAction, AuditEntityType, AuditError
from src.core.audit.container import AuditContainer
from src.core.backup.container import BackupContainer
from src.core.biometrics.container import BiometricsContainer
from src.core.configuration.container import ConfigurationContainer
from src.core.configuration.domain import ConfigurationProfile
from src.core.people.container import PeopleContainer
from src.core.security.container import SecurityContainer


PROJECT_ROOT = Path("/application")


class SecurityContainerTests(unittest.TestCase):
    def test_disabled_security_does_not_initialize_persistence(self) -> None:
        repository = Mock()
        repository_type = Mock(return_value=repository)

        components = SecurityContainer.build(
            {"security": {"enabled": False}},
            PROJECT_ROOT,
            repository_type=repository_type,
        )

        self.assertFalse(components.enabled)
        self.assertFalse(components.bootstrap_enabled)
        repository.initialize.assert_not_called()


class AuditContainerTests(unittest.TestCase):
    def test_initialization_failure_disables_the_record_use_case(self) -> None:
        repository = Mock()
        repository.initialize.side_effect = OSError("unavailable")

        components = AuditContainer.build(
            {"audit": {"enabled": True}},
            PROJECT_ROOT,
            repository_type=Mock(return_value=repository),
        )

        self.assertFalse(components.service.enabled)
        with self.assertRaises(AuditError):
            components.service.record(
                AuditAction.LOGIN_FAILURE, AuditEntityType.SESSION
            )
        repository.append.assert_not_called()


class RepositoryContainerTests(unittest.TestCase):
    def test_people_builds_and_initializes_the_configured_adapter(self) -> None:
        repository = Mock()
        repository_type = Mock(return_value=repository)

        result = PeopleContainer.build_repository(
            {
                "person_database": {
                    "enabled": True,
                    "path": "state/people.db",
                    "timeout_seconds": 2,
                }
            },
            PROJECT_ROOT,
            repository_type=repository_type,
        )

        self.assertIs(result, repository)
        repository_type.assert_called_once_with(
            PROJECT_ROOT / "state/people.db", timeout=2.0
        )
        repository.initialize.assert_called_once_with()

    def test_disabled_attendance_never_builds_an_adapter(self) -> None:
        repository_type = Mock()

        result = AttendanceContainer.build(
            {"attendance": {"enabled": False}},
            Mock(),
            PROJECT_ROOT,
            repository_type=repository_type,
        )

        self.assertIsNone(result)
        repository_type.assert_not_called()


class ConfigurationContainerTests(unittest.TestCase):
    def test_builds_service_from_the_selected_profile(self) -> None:
        validator = object()
        loader = object()
        service = object()
        validator_type = Mock(return_value=validator)
        loader_type = Mock(return_value=loader)
        service_type = Mock(return_value=service)
        path = Path("config/application.json")

        result = ConfigurationContainer.build_service(
            path,
            {"profile": "PRODUCTION", "backup_count": 4},
            PROJECT_ROOT,
            validator_type=validator_type,
            loader_type=loader_type,
            service_type=service_type,
        )

        self.assertIs(result, service)
        validator_type.assert_called_once_with(PROJECT_ROOT)
        loader_type.assert_called_once_with(validator)
        service_type.assert_called_once_with(
            loader,
            path,
            ConfigurationProfile.PRODUCTION,
            backup_count=4,
        )


class BackupContainerTests(unittest.TestCase):
    def test_shares_one_dependency_graph_between_backup_and_restore(self) -> None:
        maintenance = object()
        catalog = object()
        archive = object()
        snapshots = object()
        backup_service = object()
        restore_service = object()
        maintenance_type = Mock(return_value=maintenance)
        catalog_type = Mock(return_value=catalog)
        archive_type = Mock(return_value=archive)
        snapshot_type = Mock(return_value=snapshots)
        backup_service_type = Mock(return_value=backup_service)
        restore_service_type = Mock(return_value=restore_service)
        backup_audit = object()
        restore_audit = object()
        settings = {
            "backup": {
                "maximum_archive_size_bytes": 1_000,
                "maximum_file_count": 10,
                "operation_history_limit": 20,
                "restore_timeout_seconds": 5,
                "sqlite_snapshot_timeout_seconds": 2,
            }
        }

        components = BackupContainer.build(
            settings,
            PROJECT_ROOT,
            backup_audit_callback=backup_audit,
            restore_audit_callback=restore_audit,
            maintenance_type=maintenance_type,
            catalog_type=catalog_type,
            archive_type=archive_type,
            snapshot_type=snapshot_type,
            backup_service_type=backup_service_type,
            restore_service_type=restore_service_type,
        )

        self.assertIs(components.backup_service, backup_service)
        self.assertIs(components.restore_service, restore_service)
        backup_service_type.assert_called_once_with(
            catalog,
            archive,
            snapshots,
            maintenance,
            audit_callback=backup_audit,
        )
        restore_service_type.assert_called_once_with(
            catalog,
            archive,
            snapshots,
            maintenance,
            audit_callback=restore_audit,
        )


class BiometricsContainerTests(unittest.TestCase):
    def test_composes_explicitly_disabled_recognition_and_enrollment(self) -> None:
        components = BiometricsContainer.build(
            {
                "matcher": {"top_k": 3},
                "recognition": {
                    "automatic_decision_enabled": False,
                    "match_threshold": None,
                    "ambiguity_margin": None,
                    "top_k": 3,
                    "minimum_quality_score": None,
                    "allow_low_quality": False,
                    "policy_name": "manual_validation",
                    "policy_version": "1.0",
                },
                "enrollment": {
                    "min_templates": 1,
                    "max_templates": 3,
                    "allow_low_quality": False,
                    "min_pairwise_similarity": None,
                    "max_pairwise_similarity": None,
                    "reject_exact_duplicates": True,
                },
            },
            PROJECT_ROOT,
        )

        self.assertIs(components.recognition.gallery, components.gallery)
        self.assertIs(components.enrollment.gallery, components.gallery)
        self.assertFalse(components.recognition.policy.automatic_decision_enabled)
        self.assertFalse(components.calibration_invalid)


if __name__ == "__main__":
    unittest.main()

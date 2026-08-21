"""Executable dependency rules for incrementally migrated bounded contexts."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from src.core.attendance import AttendanceRepository, SQLiteAttendanceRepository
from src.core.audit import AuditRepository, SQLiteAuditRepository
from src.core.configuration import ConfigurationLoader, JSONConfigurationLoader
from src.core.people import PersonRepository, SQLitePeopleRepository
from src.core.security import SQLiteUserRepository, UserRepository


ROOT = Path(__file__).resolve().parents[1]
ATTENDANCE = ROOT / "src/core/attendance"
PEOPLE = ROOT / "src/core/people"
BIOMETRICS = ROOT / "src/core/biometrics"
SECURITY = ROOT / "src/core/security"
AUDIT = ROOT / "src/core/audit"
BACKUP = ROOT / "src/core/backup"
CONFIGURATION = ROOT / "src/core/configuration"
EXPECTED_ATTENDANCE_USE_CASES = {
    "consume_detection_event.py": "ConsumeAttendanceDetectionUseCase",
    "evaluate_observation.py": "EvaluateAttendanceObservationUseCase",
    "manual_check_in.py": "ManualCheckInUseCase",
    "manual_check_out.py": "ManualCheckOutUseCase",
}
EXPECTED_PEOPLE_USE_CASES = {
    "begin_person_enrollment.py": "BeginPersonEnrollmentUseCase",
    "cancel_person_enrollment.py": "CancelPersonEnrollmentUseCase",
    "change_person_status.py": "ChangePersonStatusUseCase",
    "commit_person_enrollment.py": "CommitPersonEnrollmentUseCase",
    "create_person.py": "CreatePersonUseCase",
    "get_person.py": "GetPersonUseCase",
    "search_people.py": "SearchPeopleUseCase",
    "update_person.py": "UpdatePersonUseCase",
}
EXPECTED_BIOMETRICS_USE_CASES = {
    "calibrate_biometrics.py": "CalibrateBiometricsUseCase",
    "enroll_identity.py": "EnrollIdentityUseCase",
    "export_gallery.py": "ExportGalleryUseCase",
    "import_gallery.py": "ImportGalleryUseCase",
    "recognize_face.py": "RecognizeFaceUseCase",
}
EXPECTED_SECURITY_USE_CASES = {
    "authenticate_user.py": "AuthenticateUserUseCase",
    "authorize_action.py": "AuthorizeActionUseCase",
    "bootstrap_admin.py": "BootstrapAdminUseCase",
    "change_password.py": "ChangePasswordUseCase",
    "change_user_status.py": "ChangeUserStatusUseCase",
    "create_user.py": "CreateUserUseCase",
    "list_users.py": "ListUsersUseCase",
    "reset_user_password.py": "ResetUserPasswordUseCase",
    "update_user.py": "UpdateUserUseCase",
}
EXPECTED_AUDIT_USE_CASES = {
    "export_audit.py": "ExportAuditUseCase",
    "query_audit.py": "QueryAuditUseCase",
    "record_audit.py": "RecordAuditUseCase",
    "safe_record_audit.py": "SafeRecordAuditUseCase",
    "summarize_audit.py": "SummarizeAuditUseCase",
}
EXPECTED_BACKUP_USE_CASES = {
    "create_backup.py": "CreateBackupUseCase",
    "prepare_restore.py": "PrepareRestoreUseCase",
    "restore_backup.py": "RestoreBackupUseCase",
    "verify_backup.py": "VerifyBackupUseCase",
}
EXPECTED_CONFIGURATION_USE_CASES = {
    "diff_configuration.py": "DiffConfigurationUseCase",
    "export_configuration.py": "ExportConfigurationUseCase",
    "get_configuration.py": "GetConfigurationUseCase",
    "import_configuration.py": "ImportConfigurationUseCase",
    "reload_configuration.py": "ReloadConfigurationUseCase",
    "save_configuration.py": "SaveConfigurationUseCase",
    "validate_configuration.py": "ValidateConfigurationUseCase",
}


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    relative = path.relative_to(ROOT).with_suffix("")
    package = list(relative.parts)
    if package[-1] == "__init__":
        package.pop()
    else:
        package.pop()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parent = package[: len(package) - (node.level - 1)]
                suffix = [] if node.module is None else node.module.split(".")
                modules.add(".".join((*parent, *suffix)))
            elif node.module:
                modules.add(node.module)
    return modules


def assert_layer_avoids(
    test_case: unittest.TestCase,
    context: Path,
    layer: str,
    forbidden: tuple[str, ...],
) -> None:
    for path in (context / layer).glob("*.py"):
        with test_case.subTest(
            context=context.name, layer=layer, path=path.name
        ):
            imports = imported_modules(path)
            violations = {
                module
                for module in imports
                if any(
                    module == prefix or module.startswith(prefix + ".")
                    for prefix in forbidden
                )
            }
            test_case.assertEqual(violations, set())


class AttendanceArchitectureBoundaryTests(unittest.TestCase):

    def test_domain_is_framework_and_adapter_independent(self) -> None:
        assert_layer_avoids(
            self,
            ATTENDANCE,
            "domain",
            (
                "src.core.attendance.application",
                "src.core.attendance.infrastructure",
                "src.ui",
                "sqlite3",
                "cv2",
                "numpy",
            ),
        )

    def test_application_does_not_depend_on_ui_or_infrastructure(self) -> None:
        assert_layer_avoids(
            self,
            ATTENDANCE,
            "application",
            (
                "src.core.attendance.infrastructure",
                "src.core.person_database",
                "src.ui",
                "sqlite3",
                "cv2",
                "numpy",
            ),
        )

    def test_legacy_repository_name_is_only_a_compatibility_alias(self) -> None:
        self.assertIs(AttendanceRepository, SQLiteAttendanceRepository)

    def test_each_public_application_operation_has_its_own_use_case_file(self) -> None:
        discovered: dict[str, str] = {}
        for path in (ATTENDANCE / "application").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            use_cases = [
                node.name
                for node in tree.body
                if isinstance(node, ast.ClassDef) and node.name.endswith("UseCase")
            ]
            with self.subTest(path=path.name):
                self.assertLessEqual(len(use_cases), 1)
            if use_cases:
                discovered[path.name] = use_cases[0]

        self.assertEqual(discovered, EXPECTED_ATTENDANCE_USE_CASES)


class PeopleArchitectureBoundaryTests(unittest.TestCase):
    def test_domain_is_framework_and_adapter_independent(self) -> None:
        assert_layer_avoids(
            self,
            PEOPLE,
            "domain",
            (
                "src.core.people.application",
                "src.core.people.infrastructure",
                "src.core.person_database",
                "src.engine",
                "src.ui",
                "sqlite3",
                "cv2",
                "numpy",
            ),
        )

    def test_application_depends_only_on_people_domain(self) -> None:
        assert_layer_avoids(
            self,
            PEOPLE,
            "application",
            (
                "src.core.people.infrastructure",
                "src.core.person_database",
                "src.engine",
                "src.ui",
                "sqlite3",
                "cv2",
                "numpy",
            ),
        )

    def test_legacy_repository_name_is_only_a_compatibility_alias(self) -> None:
        self.assertIs(PersonRepository, SQLitePeopleRepository)

    def test_each_public_application_operation_has_its_own_use_case_file(self) -> None:
        discovered: dict[str, str] = {}
        for path in (PEOPLE / "application").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            use_cases = [
                node.name
                for node in tree.body
                if isinstance(node, ast.ClassDef) and node.name.endswith("UseCase")
            ]
            with self.subTest(path=path.name):
                self.assertLessEqual(len(use_cases), 1)
            if use_cases:
                discovered[path.name] = use_cases[0]

        self.assertEqual(discovered, EXPECTED_PEOPLE_USE_CASES)


class BiometricsArchitectureBoundaryTests(unittest.TestCase):
    def test_domain_is_framework_and_adapter_independent(self) -> None:
        assert_layer_avoids(
            self,
            BIOMETRICS,
            "domain",
            (
                "src.core.biometrics.application",
                "src.core.biometrics.infrastructure",
                "src.engine",
                "src.ui",
                "sqlite3",
                "cv2",
                "numpy",
            ),
        )

    def test_application_depends_only_on_biometrics_domain(self) -> None:
        assert_layer_avoids(
            self,
            BIOMETRICS,
            "application",
            (
                "src.core.biometrics.infrastructure",
                "src.engine",
                "src.ui",
                "sqlite3",
                "cv2",
                "numpy",
            ),
        )

    def test_each_public_application_operation_has_its_own_use_case_file(self) -> None:
        discovered: dict[str, str] = {}
        for path in (BIOMETRICS / "application").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            use_cases = [
                node.name
                for node in tree.body
                if isinstance(node, ast.ClassDef) and node.name.endswith("UseCase")
            ]
            with self.subTest(path=path.name):
                self.assertLessEqual(len(use_cases), 1)
            if use_cases:
                discovered[path.name] = use_cases[0]

        self.assertEqual(discovered, EXPECTED_BIOMETRICS_USE_CASES)


def assert_expected_use_cases(
    test_case: unittest.TestCase,
    context: Path,
    expected: dict[str, str],
) -> None:
    discovered: dict[str, str] = {}
    for path in (context / "application").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        use_cases = [
            node.name
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name.endswith("UseCase")
        ]
        with test_case.subTest(path=path.name):
            test_case.assertLessEqual(len(use_cases), 1)
        if use_cases:
            discovered[path.name] = use_cases[0]
    test_case.assertEqual(discovered, expected)


class SecurityArchitectureBoundaryTests(unittest.TestCase):
    def test_domain_is_framework_and_adapter_independent(self) -> None:
        assert_layer_avoids(
            self,
            SECURITY,
            "domain",
            (
                "src.core.security.application",
                "src.core.security.infrastructure",
                "src.ui",
                "sqlite3",
                "cv2",
                "numpy",
            ),
        )

    def test_application_does_not_depend_on_adapters_or_ui(self) -> None:
        assert_layer_avoids(
            self,
            SECURITY,
            "application",
            (
                "src.core.security.infrastructure",
                "src.core.security.repository",
                "src.core.security.passwords",
                "src.ui",
                "sqlite3",
                "cv2",
                "numpy",
            ),
        )

    def test_legacy_repository_is_only_a_compatibility_alias(self) -> None:
        self.assertIs(UserRepository, SQLiteUserRepository)

    def test_each_public_operation_has_its_own_use_case_file(self) -> None:
        assert_expected_use_cases(self, SECURITY, EXPECTED_SECURITY_USE_CASES)


class AuditArchitectureBoundaryTests(unittest.TestCase):
    def test_domain_is_framework_and_adapter_independent(self) -> None:
        assert_layer_avoids(
            self,
            AUDIT,
            "domain",
            (
                "src.core.audit.application",
                "src.core.audit.infrastructure",
                "src.ui",
                "sqlite3",
                "cv2",
                "numpy",
            ),
        )

    def test_application_does_not_depend_on_adapters_or_ui(self) -> None:
        assert_layer_avoids(
            self,
            AUDIT,
            "application",
            (
                "src.core.audit.infrastructure",
                "src.core.audit.repository",
                "src.core.audit.exporter",
                "src.ui",
                "sqlite3",
                "cv2",
                "numpy",
            ),
        )

    def test_legacy_repository_is_only_a_compatibility_alias(self) -> None:
        self.assertIs(AuditRepository, SQLiteAuditRepository)

    def test_each_public_operation_has_its_own_use_case_file(self) -> None:
        assert_expected_use_cases(self, AUDIT, EXPECTED_AUDIT_USE_CASES)


class BackupArchitectureBoundaryTests(unittest.TestCase):
    def test_domain_is_framework_and_adapter_independent(self) -> None:
        assert_layer_avoids(
            self,
            BACKUP,
            "domain",
            (
                "src.core.backup.application",
                "src.core.backup.infrastructure",
                "src.engine",
                "src.ui",
                "sqlite3",
                "cv2",
                "numpy",
            ),
        )

    def test_application_does_not_depend_on_adapters_or_ui(self) -> None:
        assert_layer_avoids(
            self,
            BACKUP,
            "application",
            (
                "src.core.backup.infrastructure",
                "src.engine",
                "src.ui",
                "sqlite3",
                "cv2",
                "numpy",
            ),
        )

    def test_each_public_operation_has_its_own_use_case_file(self) -> None:
        assert_expected_use_cases(self, BACKUP, EXPECTED_BACKUP_USE_CASES)


class ConfigurationArchitectureBoundaryTests(unittest.TestCase):
    def test_domain_is_framework_and_adapter_independent(self) -> None:
        assert_layer_avoids(
            self,
            CONFIGURATION,
            "domain",
            (
                "src.core.configuration.application",
                "src.core.configuration.infrastructure",
                "src.camera",
                "src.ui",
                "sqlite3",
                "cv2",
                "numpy",
            ),
        )

    def test_application_does_not_depend_on_adapters_or_ui(self) -> None:
        assert_layer_avoids(
            self,
            CONFIGURATION,
            "application",
            (
                "src.core.configuration.infrastructure",
                "src.core.configuration.validators",
                "src.camera",
                "src.ui",
                "sqlite3",
                "cv2",
                "numpy",
            ),
        )

    def test_legacy_loader_is_only_a_compatibility_alias(self) -> None:
        self.assertIs(ConfigurationLoader, JSONConfigurationLoader)

    def test_each_public_operation_has_its_own_use_case_file(self) -> None:
        assert_expected_use_cases(
            self, CONFIGURATION, EXPECTED_CONFIGURATION_USE_CASES
        )


if __name__ == "__main__":
    unittest.main()

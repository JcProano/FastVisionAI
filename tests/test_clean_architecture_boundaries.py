"""Executable dependency rules for incrementally migrated bounded contexts."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from src.core.attendance import AttendanceRepository, SQLiteAttendanceRepository
from src.core.people import PersonRepository, SQLitePeopleRepository


ROOT = Path(__file__).resolve().parents[1]
ATTENDANCE = ROOT / "src/core/attendance"
PEOPLE = ROOT / "src/core/people"
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


if __name__ == "__main__":
    unittest.main()

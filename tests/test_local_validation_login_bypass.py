from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.core.security import AuthorizationPermission, UserRole
from src.ui.main import (
    authenticate_startup, build_security, local_validation_login_bypass_enabled,
)
from src.ui.tk_app import local_validation_banner


class RootSpy:
    def __init__(self) -> None:
        self.withdrawn = 0
        self.deiconified = 0

    def withdraw(self) -> None:
        self.withdrawn += 1

    def deiconify(self) -> None:
        self.deiconified += 1


class LoginFactorySpy:
    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.created = 0

    def __call__(self, _root, _security):
        self.created += 1
        return self

    def run(self) -> bool:
        return self.result


class LocalValidationLoginBypassTests(unittest.TestCase):
    def security(self, root: Path):
        return build_security({
            "security": {
                "enabled": True,
                "database_path": "users.db",
                "session_idle_timeout_seconds": 1800,
            }
        }, root)

    def test_false_flag_uses_normal_login(self):
        with TemporaryDirectory() as directory:
            security = self.security(Path(directory))
            root = RootSpy(); login = LoginFactorySpy()
            self.assertTrue(authenticate_startup(
                root, security, skip_login=False, login_factory=login,
            ))
            self.assertEqual(login.created, 1)
            self.assertIsNone(security.sessions.current())
            self.assertEqual((root.withdrawn, root.deiconified), (1, 1))

    def test_true_flag_skips_login_and_creates_ephemeral_admin_with_rbac(self):
        with TemporaryDirectory() as directory:
            security = self.security(Path(directory))
            repository = security.authentication.repository
            self.assertEqual(repository.count_users(), 0)
            root = RootSpy(); login = LoginFactorySpy()
            with self.assertLogs("src.ui.main", level="WARNING") as captured:
                self.assertTrue(authenticate_startup(
                    root, security, skip_login=True, login_factory=login,
                ))
            self.assertEqual(login.created, 0)
            session = security.sessions.current()
            self.assertIsNotNone(session)
            self.assertEqual(session.role, UserRole.ADMIN)
            self.assertTrue(security.authorization.can(
                AuthorizationPermission.MANAGE_USERS
            ))
            self.assertEqual(repository.count_users(), 0)
            self.assertIn(
                "Security login bypass enabled for local validation",
                "\n".join(captured.output),
            )

    def test_flag_is_explicit_typed_and_requires_enabled_security(self):
        self.assertFalse(local_validation_login_bypass_enabled({"security": {}}))
        self.assertTrue(local_validation_login_bypass_enabled({
            "security": {"enabled": True, "skip_login_for_local_validation": True}
        }))
        with self.assertRaises(ValueError):
            local_validation_login_bypass_enabled({
                "security": {"skip_login_for_local_validation": "true"}
            })
        with self.assertRaises(ValueError):
            local_validation_login_bypass_enabled({
                "security": {
                    "enabled": False, "skip_login_for_local_validation": True,
                }
            })

    def test_dashboard_banner_and_production_default(self):
        self.assertEqual(
            local_validation_banner(True),
            "MODO VALIDACIÓN LOCAL — LOGIN OMITIDO",
        )
        self.assertEqual(local_validation_banner(False), "")
        production = json.loads(Path(
            "config/local_face_validation.prod.json"
        ).read_text(encoding="utf-8"))
        self.assertIs(
            production["security"]["skip_login_for_local_validation"], False
        )

    def test_users_database_failure_remains_fail_closed_with_flag(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "blocked").write_text("not a directory", encoding="utf-8")
            with self.assertRaises(Exception):
                build_security({
                    "security": {
                        "enabled": True,
                        "skip_login_for_local_validation": True,
                        "database_path": "blocked/users.db",
                    }
                }, root)


if __name__ == "__main__":
    unittest.main()

"""Scrypt password-hashing adapter."""

from __future__ import annotations

import hashlib
import json
import secrets

from ..domain.models import PasswordHashDTO, PasswordPolicy


class ScryptPasswordHasher:
    ALGORITHM = "scrypt"
    VERSION = 1

    def __init__(
        self,
        policy: PasswordPolicy | None = None,
        *,
        n: int = 16384,
        r: int = 8,
        p: int = 1,
        dklen: int = 64,
        salt_bytes: int = 32,
    ) -> None:
        if n < 2 or n & (n - 1) or min(r, p, dklen, salt_bytes) <= 0:
            raise ValueError("scrypt parameters invalid")
        self.policy = policy or PasswordPolicy()
        self.parameters = {
            "version": self.VERSION,
            "n": n,
            "r": r,
            "p": p,
            "dklen": dklen,
        }
        self.salt_bytes = salt_bytes

    def hash_password(self, password: str) -> PasswordHashDTO:
        self.policy.validate(password)
        salt = secrets.token_bytes(self.salt_bytes)
        digest = self._derive(password, salt, self.parameters)
        return PasswordHashDTO(
            digest,
            salt,
            self.ALGORITHM,
            json.dumps(self.parameters, sort_keys=True, separators=(",", ":")),
        )

    def verify_password(self, password: str, stored: PasswordHashDTO) -> bool:
        if stored.algorithm != self.ALGORITHM:
            return False
        try:
            parameters = json.loads(stored.parameters)
        except Exception:
            return False
        if (
            parameters != self.parameters
            or parameters.get("version") != self.VERSION
        ):
            return False
        try:
            candidate = self._derive(
                password, stored.password_salt, parameters
            )
        except Exception:
            return False
        return secrets.compare_digest(candidate, stored.password_hash)

    @staticmethod
    def _derive(password: str, salt: bytes, parameters: dict) -> bytes:
        return hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=parameters["n"],
            r=parameters["r"],
            p=parameters["p"],
            dklen=parameters["dklen"],
        )

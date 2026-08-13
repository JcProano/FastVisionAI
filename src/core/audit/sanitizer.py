"""Strict sanitization for audit text and flat metadata."""
from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Mapping

from .contracts import AuditValidationError

_SENSITIVE = re.compile(
    r"password|hash|salt|secret|token|api[_-]?key|credential|private[_-]?key", re.I
)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_ABSOLUTE = re.compile(r"^(?:/|[A-Za-z]:[\\/])")
Scalar = str | int | float | bool | None


def sanitize_message(value: object, maximum_length: int) -> str:
    text = _CONTROL.sub("", str(value)).replace("\r", " ").replace("\n", " ").strip()
    return text[:maximum_length]


def sanitize_metadata(
    value: Mapping[str, object] | None, *, maximum_items: int, value_maximum_length: int,
) -> dict[str, Scalar]:
    if value is None:
        return {}
    if not isinstance(value, Mapping) or len(value) > maximum_items:
        raise AuditValidationError("audit metadata is invalid")
    output: dict[str, Scalar] = {}
    for raw_key, raw_value in value.items():
        if not isinstance(raw_key, str) or not raw_key or len(raw_key) > 64:
            raise AuditValidationError("audit metadata key is invalid")
        key = _CONTROL.sub("", raw_key).strip()
        if _SENSITIVE.search(key):
            output[key] = "[REDACTED]"
            continue
        if isinstance(raw_value, (dict, list, tuple, set, bytes, bytearray, Path)):
            raise AuditValidationError("audit metadata must be flat")
        if raw_value is not None and not isinstance(raw_value, (str, int, float, bool)):
            raise AuditValidationError("audit metadata value is invalid")
        if isinstance(raw_value, float) and not math.isfinite(raw_value):
            raise AuditValidationError("audit metadata number is invalid")
        if isinstance(raw_value, str):
            cleaned = _CONTROL.sub("", raw_value).replace("\r", " ").replace("\n", " ").strip()
            if _ABSOLUTE.match(cleaned):
                cleaned = "[PATH_REDACTED]"
            raw_value = cleaned[:value_maximum_length]
        output[key] = raw_value
    return output


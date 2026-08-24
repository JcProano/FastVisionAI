"""Small best-effort audit boundary shared by security use cases."""

from __future__ import annotations

from collections.abc import Callable, Mapping

AuditCallback = Callable[[str, dict[str, str]], None]


def audit_safely(
    callback: AuditCallback | None,
    event: str,
    payload: Mapping[str, str],
) -> None:
    if callback is None:
        return
    try:
        callback(event, dict(payload))
    except Exception:
        pass

"""Best-effort audit callback shared by backup workflows."""


def audit_safely(callback, event: str) -> None:
    if callback is None:
        return
    try:
        callback(event, {})
    except Exception:
        pass

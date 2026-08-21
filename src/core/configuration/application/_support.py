"""Shared pure helpers for configuration use cases."""

from ..domain.diff import configuration_diff


def diff_with_policy(session, candidate, policy):
    return configuration_diff(
        session.current().as_mapping(), candidate, policy.redact
    )


def audit_safely(callback, event, profile) -> None:
    if callback is None:
        return
    try:
        callback(event, {"profile": profile.value})
    except Exception:
        pass

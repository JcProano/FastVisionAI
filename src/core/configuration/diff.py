"""Compatibility export for pure configuration diffing."""

from .domain.diff import HOT, IMMUTABLE, configuration_diff
from .validators import redact


def configuration_diff(old: dict, new: dict):
    from .domain.diff import configuration_diff as compare

    return compare(old, new, redact)


__all__ = ["HOT", "IMMUTABLE", "configuration_diff"]

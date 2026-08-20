from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit


def redact_url(value: str) -> str:
    """Return a URL safe for logs/UI while retaining useful host/protocol context."""

    try:
        parsed = urlsplit(value)
    except ValueError:
        return "[REDACTED URL]"
    if not parsed.scheme or not parsed.netloc:
        return "[REDACTED URL]"
    try:
        host = parsed.hostname or "host"
        port_number = parsed.port
    except ValueError:
        return "[REDACTED URL]"
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = f":{port_number}" if port_number is not None else ""
    credentials = "***:***@" if parsed.username is not None or parsed.password is not None else ""
    return urlunsplit((parsed.scheme, f"{credentials}{host}{port}", parsed.path, "", ""))

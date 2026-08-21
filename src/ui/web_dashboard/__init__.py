"""Read-only local/LAN web projection for the existing FastVisionAI process."""

from .controller import WebDashboardController
from .container import WebDashboardComponents, WebDashboardContainer
from .frame_store import LatestPresentationFrameStore
from .http_server import WebDashboardServer, detect_lan_ip

__all__ = [
    "LatestPresentationFrameStore",
    "WebDashboardComponents",
    "WebDashboardContainer",
    "WebDashboardController",
    "WebDashboardServer",
    "detect_lan_ip",
]

"""Configuration contract for the bounded appliance web server."""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WebDashboardPolicy:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8080
    open_browser_on_start: bool = False
    allow_remote_lan: bool = False
    video_max_fps: float = 10.0
    video_jpeg_quality: int = 75
    max_stream_clients: int = 3

    def __post_init__(self) -> None:
        if type(self.enabled) is not bool or type(self.open_browser_on_start) is not bool or type(self.allow_remote_lan) is not bool:
            raise ValueError("web dashboard flags must be boolean")
        if not isinstance(self.host, str) or not self.host:
            raise ValueError("web dashboard host is invalid")
        if isinstance(self.port, bool) or not isinstance(self.port, int) or not 1 <= self.port <= 65535:
            raise ValueError("web dashboard port is invalid")
        if isinstance(self.video_max_fps, bool) or not 0 < float(self.video_max_fps) <= 30:
            raise ValueError("web video FPS is invalid")
        if isinstance(self.video_jpeg_quality, bool) or not isinstance(self.video_jpeg_quality, int) or not 1 <= self.video_jpeg_quality <= 100:
            raise ValueError("web JPEG quality is invalid")
        if isinstance(self.max_stream_clients, bool) or not isinstance(self.max_stream_clients, int) or not 1 <= self.max_stream_clients <= 10:
            raise ValueError("web stream client limit is invalid")

    @classmethod
    def from_mapping(cls, value: object) -> "WebDashboardPolicy":
        source = value if isinstance(value, dict) else {}
        return cls(**{field: source[field] for field in cls.__dataclass_fields__ if field in source})

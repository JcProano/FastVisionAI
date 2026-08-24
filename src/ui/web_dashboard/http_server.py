"""Uvicorn lifecycle adapter for the embedded FastAPI dashboard."""

from __future__ import annotations

import logging
import socket
import threading
import time
import webbrowser

import uvicorn

from .contracts import WebDashboardPolicy
from .fastapi_app import create_fastapi_app
from .session_store import InMemoryWebSessionStore

LOGGER = logging.getLogger(__name__)


class WebDashboardServer:
    """Preserve the existing lifecycle while delegating HTTP to FastAPI/Uvicorn."""

    def __init__(
        self,
        policy: WebDashboardPolicy,
        controller,
        frame_store,
        *,
        browser_open=webbrowser.open,
        printer=print,
    ) -> None:
        self.policy = policy
        self.controller = controller
        self.frame_store = frame_store
        self.browser_open = browser_open
        self.printer = printer
        self._closing = threading.Event()
        self._streams = threading.BoundedSemaphore(policy.max_stream_clients)
        self._session_store = InMemoryWebSessionStore()
        self._lock = threading.RLock()
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._socket: socket.socket | None = None
        self._thread_error: BaseException | None = None
        self.app = create_fastapi_app(
            policy,
            controller,
            frame_store,
            closing=self._closing,
            streams=self._streams,
            sessions=self._session_store,
        )

    @property
    def running(self) -> bool:
        return (
            self._thread is not None
            and self._thread.is_alive()
            and self._server is not None
            and self._server.started
            and not self._closing.is_set()
        )

    @property
    def local_url(self) -> str:
        return f"http://127.0.0.1:{self.policy.port}"

    def start(self) -> bool:
        with self._lock:
            if self.running:
                return True
            if not self.policy.enabled:
                return False
            self._closing.clear()
            self._thread_error = None
            try:
                self._socket = _listening_socket(
                    self.policy.host, self.policy.port
                )
            except OSError as exc:
                LOGGER.warning(
                    "Web dashboard unavailable; Runtime may continue; "
                    "exception_type=%s",
                    type(exc).__name__,
                )
                return False
            config = uvicorn.Config(
                self.app,
                host=self.policy.host,
                port=self.policy.port,
                log_level="warning",
                access_log=False,
                lifespan="off",
                timeout_keep_alive=5,
                timeout_graceful_shutdown=2,
                limit_concurrency=64,
            )
            self._server = uvicorn.Server(config)
            self._thread = threading.Thread(
                target=self._serve,
                name="fastvision-web",
                daemon=True,
            )
            self._thread.start()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if self.running:
                break
            if self._thread is None or not self._thread.is_alive():
                break
            time.sleep(0.01)
        if not self.running:
            self.close()
            return False
        self._announce()
        if self.policy.open_browser_on_start:
            try:
                self.browser_open(self.local_url)
            except Exception:
                LOGGER.warning("Default browser could not be opened safely")
        return True

    def close(self) -> None:
        with self._lock:
            if self._closing.is_set() and self._thread is None:
                return
            self._closing.set()
            server = self._server
            thread = self._thread
            listening_socket = self._socket
            if server is not None:
                server.should_exit = True
        if thread is not None and thread is not threading.current_thread():
            thread.join(3.0)
        if listening_socket is not None:
            try:
                listening_socket.close()
            except OSError:
                pass
        self._session_store.close()
        with self._lock:
            self._server = None
            self._thread = None
            self._socket = None

    def _serve(self) -> None:
        server = self._server
        listening_socket = self._socket
        if server is None or listening_socket is None:
            return
        try:
            server.run(sockets=[listening_socket])
        except BaseException as exc:
            self._thread_error = exc
            LOGGER.warning(
                "Web dashboard stopped unexpectedly; exception_type=%s",
                type(exc).__name__,
            )

    def _announce(self) -> None:
        self.printer("FASTVISION AI WEB DASHBOARD")
        self.printer(f"Local: {self.local_url}")
        address = detect_lan_ip()
        if address:
            self.printer(f"Red: http://{address}:{self.policy.port}")


def _listening_socket(host: str, port: int) -> socket.socket:
    family, socktype, protocol, _, address = socket.getaddrinfo(
        host, port, type=socket.SOCK_STREAM
    )[0]
    result = socket.socket(family, socktype, protocol)
    try:
        result.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        result.bind(address)
        result.listen(128)
        result.setblocking(False)
        return result
    except BaseException:
        result.close()
        raise


def detect_lan_ip() -> str | None:
    connection = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        connection.connect(("192.0.2.1", 9))
        value = connection.getsockname()[0]
        return None if value.startswith("127.") or value == "0.0.0.0" else value
    except OSError:
        return None
    finally:
        connection.close()

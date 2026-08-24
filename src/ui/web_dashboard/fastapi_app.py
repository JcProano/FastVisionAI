"""FastAPI transport adapter for the embedded FastVision web dashboard."""

from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .mjpeg import iter_mjpeg
from .session_store import InMemoryWebSessionStore

LOGGER = logging.getLogger(__name__)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; "
        "script-src 'self'; connect-src 'self'; object-src 'none'; "
        "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
}


def create_fastapi_app(
    policy,
    controller,
    frame_store,
    *,
    closing: threading.Event,
    streams: threading.BoundedSemaphore,
    sessions: InMemoryWebSessionStore | None = None,
    static_root: Path | None = None,
) -> FastAPI:
    """Create one explicit HTTP adapter around existing application boundaries."""

    session_store = sessions or InMemoryWebSessionStore()
    assets = static_root or Path(__file__).with_name("static")
    app = FastAPI(
        title="FastVision AI local dashboard",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.web_sessions = session_store

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers[name] = value
        return response

    @app.exception_handler(KeyError)
    async def unknown_route(_request: Request, _error: KeyError):
        return _error_response(404, "Recurso no disponible")

    @app.exception_handler(PermissionError)
    async def forbidden(_request: Request, _error: PermissionError):
        return _error_response(403, "Acceso denegado")

    @app.exception_handler(ValueError)
    async def invalid_request(_request: Request, error: ValueError):
        return _error_response(400, str(error))

    @app.exception_handler(Exception)
    async def unavailable(request: Request, error: Exception):
        LOGGER.warning(
            "Web request failed safely; path=%s exception_type=%s",
            request.url.path,
            type(error).__name__,
        )
        return _error_response(503, "Servicio temporalmente no disponible")

    @app.get("/api/session")
    async def issue_session() -> Response:
        session = session_store.issue()
        response = JSONResponse({"csrf_token": session.csrf_token})
        response.set_cookie(
            "fv_session",
            session.session_id,
            httponly=True,
            samesite="strict",
            path="/",
        )
        return response

    @app.get("/api/video/status")
    async def video_status() -> dict[str, object]:
        return frame_store.status()

    @app.get("/api/video.mjpeg")
    async def video_stream() -> StreamingResponse:
        if (
            frame_store.latest() is None
            or closing.is_set()
            or frame_store.closed
        ):
            raise HTTPException(503, "Video no disponible")
        if not streams.acquire(blocking=False):
            raise HTTPException(503, "Límite de video alcanzado")

        def content():
            try:
                yield from iter_mjpeg(
                    frame_store,
                    closing,
                    maximum_fps=policy.video_max_fps,
                    jpeg_quality=policy.video_jpeg_quality,
                )
            finally:
                streams.release()

        return StreamingResponse(
            content(),
            media_type="multipart/x-mixed-replace; boundary=frame",
        )

    @app.get("/api/events")
    async def events(request: Request) -> StreamingResponse:
        async def heartbeats():
            while not closing.is_set() and not await request.is_disconnected():
                yield b"event: system_health\ndata: {}\n\n"
                for _ in range(100):
                    if closing.is_set() or await request.is_disconnected():
                        return
                    await asyncio.sleep(0.1)

        return StreamingResponse(heartbeats(), media_type="text/event-stream")

    @app.get("/api/thumbnails/{token}")
    async def thumbnail(token: str) -> Response:
        value = controller.thumbnail(token)
        if value is None:
            raise KeyError(token)
        return Response(value[1], media_type=value[0])

    @app.get("/api/{endpoint:path}")
    async def query(endpoint: str, request: Request) -> dict[str, object]:
        return controller.api(f"/api/{endpoint}", request.url.query)

    @app.post("/api/{endpoint:path}")
    async def mutate(endpoint: str, request: Request) -> dict[str, object]:
        payload = await _validated_json_request(request, session_store)
        return controller.action(f"/api/{endpoint}", payload)

    @app.delete("/api/{endpoint:path}")
    async def delete(endpoint: str, request: Request) -> dict[str, object]:
        await _validated_json_request(request, session_store)
        return controller.delete(f"/api/{endpoint}")

    app.mount(
        "/assets",
        StaticFiles(directory=assets / "assets", check_dir=False),
        name="web-assets",
    )

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise KeyError(path)
        index = assets / "index.html"
        if not index.is_file():
            raise RuntimeError("web frontend build is unavailable")
        return FileResponse(index, media_type="text/html; charset=utf-8")

    return app


async def _validated_json_request(
    request: Request, session_store: InMemoryWebSessionStore
) -> dict[str, object]:
    content_type = request.headers.get("Content-Type", "").split(";", 1)[0]
    if content_type.strip().lower() != "application/json":
        raise ValueError("Se requiere Content-Type application/json.")
    length_header = request.headers.get("Content-Length")
    if length_header is not None:
        try:
            length = int(length_header)
        except ValueError as exc:
            raise ValueError("Longitud inválida.") from exc
        if length < 0 or length > 32_768:
            raise ValueError("Solicitud demasiado grande.")
    body = await request.body()
    if len(body) > 32_768:
        raise ValueError("Solicitud demasiado grande.")
    try:
        value = await request.json()
    except Exception as exc:
        raise ValueError("JSON inválido.") from exc
    if not isinstance(value, dict):
        raise ValueError("El JSON debe ser un objeto.")
    origin = request.headers.get("Origin")
    host = request.headers.get("Host", "")
    if not host or (origin is not None and urlsplit(origin).netloc != host):
        raise PermissionError("origin mismatch")
    token = request.headers.get("X-CSRF-Token") or value.get("csrf_token")
    if not session_store.validate(
        request.cookies.get("fv_session"),
        token if isinstance(token, str) else None,
    ):
        raise PermissionError("invalid web session")
    return value


def _error_response(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)

"""Bounded standard-library HTTP/MJPEG server for a trusted local network."""
from __future__ import annotations
import json
import logging
import socket
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from .contracts import WebDashboardPolicy

LOGGER=logging.getLogger(__name__)
SECURITY_HEADERS={
    "X-Content-Type-Options":"nosniff",
    "Content-Security-Policy":"default-src 'self'; img-src 'self'; style-src 'unsafe-inline'; script-src 'none'; object-src 'none'; frame-ancestors 'none'",
    "Referrer-Policy":"no-referrer",
}


class _BoundedHTTPServer(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=True


class WebDashboardServer:
    def __init__(self,policy:WebDashboardPolicy,controller,frame_store,*,browser_open=webbrowser.open,printer=print) -> None:
        self.policy=policy;self.controller=controller;self.frame_store=frame_store
        self.browser_open=browser_open;self.printer=printer;self._httpd=None;self._thread=None
        self._closing=threading.Event();self._streams=threading.BoundedSemaphore(policy.max_stream_clients)
        self._lock=threading.Lock()

    @property
    def running(self)->bool:return self._thread is not None and self._thread.is_alive() and not self._closing.is_set()
    @property
    def local_url(self)->str:return f"http://127.0.0.1:{self.policy.port}"

    def start(self)->bool:
        with self._lock:
            if self.running:return True
            if not self.policy.enabled:return False
            self._closing.clear()
            try:self._httpd=_BoundedHTTPServer((self.policy.host,self.policy.port),self._handler())
            except OSError as exc:
                self._httpd=None;LOGGER.warning("Web dashboard unavailable; Runtime may continue; exception_type=%s",type(exc).__name__);return False
            self._thread=threading.Thread(target=self._httpd.serve_forever,name="fastvision-web",daemon=True);self._thread.start()
        self._announce()
        if self.policy.open_browser_on_start:
            try:self.browser_open(self.local_url)
            except Exception:LOGGER.warning("Default browser could not be opened safely")
        return True

    def close(self)->None:
        with self._lock:
            if self._closing.is_set():return
            self._closing.set();server=self._httpd;thread=self._thread
        if server is not None:
            try:server.shutdown()
            except Exception:pass
            try:server.server_close()
            except Exception:pass
        if thread is not None and thread is not threading.current_thread():thread.join(2.0)
        with self._lock:self._httpd=None;self._thread=None

    def _announce(self)->None:
        self.printer("FASTVISION AI WEB DASHBOARD")
        self.printer(f"Local: {self.local_url}")
        address=detect_lan_ip()
        if address:self.printer(f"Red: http://{address}:{self.policy.port}")

    def _handler(self):
        owner=self
        class Handler(BaseHTTPRequestHandler):
            server_version="FastVisionWeb/1"
            sys_version=""
            def log_message(self,format,*args):LOGGER.debug("Web request: "+format,*args)
            def do_GET(self):
                split=urlsplit(self.path);path=unquote(split.path)
                try:
                    if path=="/api/dashboard":return self._bytes(200,"application/json; charset=utf-8",owner.controller.json_bytes(),sensitive=True)
                    if path=="/api/video.mjpeg":return self._stream()
                    if path.startswith("/api/thumbnails/"):
                        token=path.removeprefix("/api/thumbnails/")
                        value=owner.controller.thumbnail(token)
                        if value is None:return self._error(404,"Recurso no disponible")
                        return self._bytes(200,value[0],value[1],sensitive=True)
                    if path.startswith("/api/"):return self._error(404,"Endpoint no disponible")
                    return self._bytes(200,"text/html; charset=utf-8",owner.controller.render(path,split.query),sensitive=True)
                except KeyError:return self._error(404,"Página no disponible")
                except PermissionError:return self._error(403,"Acceso denegado")
                except Exception:
                    LOGGER.warning("Web request failed safely; path=%s",path);return self._error(503,"Servicio temporalmente no disponible")
            def do_HEAD(self):return self._method_not_allowed()
            def do_POST(self):return self._method_not_allowed()
            def do_PUT(self):return self._method_not_allowed()
            def do_DELETE(self):return self._method_not_allowed()
            def do_PATCH(self):return self._method_not_allowed()
            def do_OPTIONS(self):return self._method_not_allowed()
            def _method_not_allowed(self):
                self.send_response(405);self.send_header("Allow","GET");self._security(True);self.end_headers()
            def _error(self,status,message):return self._bytes(status,"application/json; charset=utf-8",json.dumps({"error":message},ensure_ascii=False).encode(),sensitive=True)
            def _security(self,sensitive=False):
                for key,value in SECURITY_HEADERS.items():self.send_header(key,value)
                self.send_header("Cache-Control","no-store" if sensitive else "private, max-age=60")
            def _bytes(self,status,mime,payload,*,sensitive=False):
                self.send_response(status);self.send_header("Content-Type",mime);self.send_header("Content-Length",str(len(payload)));self._security(sensitive);self.end_headers()
                try:self.wfile.write(payload)
                except (BrokenPipeError,ConnectionResetError):pass
            def _stream(self):
                frame=owner.frame_store.latest()
                if frame is None or owner._closing.is_set() or owner.frame_store.closed:return self._error(503,"Video no disponible")
                if not owner._streams.acquire(blocking=False):return self._error(503,"Límite de video alcanzado")
                try:
                    self.send_response(200);self.send_header("Content-Type","multipart/x-mixed-replace; boundary=frame");self._security(True);self.end_headers()
                    sequence=None;period=1.0/owner.policy.video_max_fps;deadline=0.0
                    while not owner._closing.is_set() and not owner.frame_store.closed:
                        frame=owner.frame_store.wait_for_new(sequence,1.0)
                        if frame is None:continue
                        delay=deadline-time.monotonic()
                        if delay>0 and owner._closing.wait(delay):break
                        jpeg=_jpeg(frame,owner.policy.video_jpeg_quality);sequence=frame.sequence_id;deadline=time.monotonic()+period
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "+str(len(jpeg)).encode()+b"\r\n\r\n"+jpeg+b"\r\n");self.wfile.flush()
                except (BrokenPipeError,ConnectionResetError,OSError):pass
                finally:owner._streams.release()
        return Handler


def _jpeg(frame,quality:int)->bytes:
    import cv2
    import numpy as np
    rgb=np.frombuffer(frame.rgb_bytes,dtype=np.uint8).reshape((frame.height,frame.width,3))
    ok,encoded=cv2.imencode(".jpg",cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),[cv2.IMWRITE_JPEG_QUALITY,quality])
    if not ok:raise RuntimeError("presentation JPEG encoding failed")
    return encoded.tobytes()


def detect_lan_ip()->str|None:
    connection=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    try:
        connection.connect(("192.0.2.1",9));value=connection.getsockname()[0]
        return None if value.startswith("127.") or value=="0.0.0.0" else value
    except OSError:return None
    finally:connection.close()

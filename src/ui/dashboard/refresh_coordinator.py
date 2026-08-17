"""Single-worker, single-timer refresh coordination for the Tk dashboard."""
from __future__ import annotations
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from collections.abc import Callable

from .professional_contracts import DashboardLiveStateDTO, DashboardSnapshotDTO


class DashboardRefreshCoordinator:
    def __init__(self, root, controller, live_state: Callable[[], DashboardLiveStateDTO],
                 on_snapshot: Callable[[DashboardSnapshotDTO], None], *,
                 dashboard_seconds: float = 5.0, statistics_seconds: float = 10.0,
                 monotonic: Callable[[], float] = time.monotonic, executor=None) -> None:
        if dashboard_seconds <= 0 or statistics_seconds <= 0:
            raise ValueError("dashboard refresh intervals must be positive")
        if statistics_seconds < dashboard_seconds:
            raise ValueError("statistics refresh cannot be faster than dashboard refresh")
        self.root=root;self.controller=controller;self.live_state=live_state
        self.on_snapshot=on_snapshot;self.dashboard_seconds=dashboard_seconds
        self.statistics_seconds=statistics_seconds;self.monotonic=monotonic
        self._executor=executor or ThreadPoolExecutor(max_workers=1,thread_name_prefix="dashboard-read")
        self._future:Future|None=None;self._after_id=None;self._closed=False
        self._invalidated=True;self._last_statistics=float("-inf")
        self._last_snapshot:DashboardSnapshotDTO|None=None
        self._lock=threading.Lock()

    @property
    def in_flight(self)->bool:return self._future is not None and not self._future.done()
    @property
    def last_snapshot(self):return self._last_snapshot
    @property
    def invalidated(self):
        with self._lock:return self._invalidated

    def start(self)->None:
        if self._closed or self._after_id is not None:return
        self._after_id=self.root.after(0,self._tick)

    def invalidate(self,_event=None)->None:
        with self._lock:self._invalidated=True

    def _tick(self)->None:
        self._after_id=None
        if self._closed:return
        if self._future is not None:
            if not self._future.done():
                self._after_id=self.root.after(100,self._tick);return
            try:
                value=self._future.result();self._last_snapshot=value
                self.on_snapshot(value)
            except Exception:
                if self._last_snapshot is not None:
                    value=self.controller.degraded(self._last_snapshot)
                    self._last_snapshot=value;self.on_snapshot(value)
            finally:self._future=None
            self._after_id=self.root.after(int(self.dashboard_seconds*1000),self._tick)
            return
        now=self.monotonic()
        refresh_statistics=(self._last_snapshot is None or
                            now-self._last_statistics>=self.statistics_seconds)
        if refresh_statistics:self._last_statistics=now
        with self._lock:self._invalidated=False
        live=self.live_state();previous=self._last_snapshot
        self._future=self._executor.submit(self.controller.snapshot,live,
            refresh_statistics=refresh_statistics,previous=previous)
        self._after_id=self.root.after(100,self._tick)

    def close(self)->None:
        if self._closed:return
        self._closed=True
        if self._after_id is not None:
            try:self.root.after_cancel(self._after_id)
            except Exception:pass
            self._after_id=None
        if self._future is not None:self._future.cancel()
        self._executor.shutdown(wait=False,cancel_futures=True)

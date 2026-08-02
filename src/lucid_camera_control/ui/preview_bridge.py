"""Coalesce acquisition-thread frames into queued Qt UI updates."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Protocol

from PySide6.QtCore import Qt, QObject, Signal, Slot

from lucid_camera_control.diagnostics.fps import RollingFps
from lucid_camera_control.media.frame import Frame


class FramePublisher(Protocol):
    def subscribe_frames(self, listener: Callable[[Frame], None]) -> Callable[[], None]: ...

    def subscribe_acquisition_errors(
        self, listener: Callable[[Exception], None]
    ) -> Callable[[], None]: ...


class PreviewBridge(QObject):
    frame_arrived = Signal(object, float)
    acquisition_failed = Signal(object)
    _frame_pending = Signal()
    _error_pending = Signal(object)

    def __init__(self, source: FramePublisher) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._latest: tuple[Frame, float] | None = None
        self._scheduled = False
        self._fps = RollingFps()
        self._frame_pending.connect(
            self._deliver_latest,
            Qt.ConnectionType.QueuedConnection,
        )
        self._error_pending.connect(
            self.acquisition_failed,
            Qt.ConnectionType.QueuedConnection,
        )
        self._unsubscribe_frame = source.subscribe_frames(self._on_frame)
        self._unsubscribe_error = source.subscribe_acquisition_errors(self._on_error)

    def close(self) -> None:
        self._unsubscribe_frame()
        self._unsubscribe_error()

    def _on_frame(self, frame: Frame) -> None:
        fps = self._fps.add(frame.received_monotonic_ns)
        should_schedule = False
        with self._lock:
            self._latest = (frame, fps)
            if not self._scheduled:
                self._scheduled = True
                should_schedule = True
        if should_schedule:
            self._frame_pending.emit()

    def _on_error(self, error: Exception) -> None:
        self._error_pending.emit(error)

    @Slot()
    def _deliver_latest(self) -> None:
        with self._lock:
            latest = self._latest
            self._latest = None
            self._scheduled = False
        if latest is not None:
            self.frame_arrived.emit(*latest)

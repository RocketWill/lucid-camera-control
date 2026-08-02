"""Stoppable acquisition loop around a finite-timeout frame source."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Protocol

from lucid_camera_control.media.frame import Frame


class FrameSource(Protocol):
    def acquire_frame(self, timeout_ms: int) -> Frame: ...


class RecoverableFrameError(RuntimeError):
    """One frame was invalid but acquisition can continue."""


class AcquisitionWorker:
    def __init__(
        self,
        source: FrameSource,
        on_frame: Callable[[Frame], None],
        on_error: Callable[[Exception], None],
        *,
        timeout_ms: int = 200,
    ) -> None:
        self._source = source
        self._on_frame = on_frame
        self._on_error = on_error
        self._timeout_ms = timeout_ms
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="lucid-acquisition",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout_seconds: float = 2.0) -> None:
        thread = self._thread
        if thread is None:
            return
        self._stop_event.set()
        thread.join(timeout_seconds)
        if thread.is_alive():
            raise RuntimeError("Acquisition worker did not stop before timeout")
        self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                frame = self._source.acquire_frame(self._timeout_ms)
            except TimeoutError:
                continue
            except RecoverableFrameError as exc:
                self._on_error(exc)
                continue
            except Exception as exc:
                if not self._stop_event.is_set():
                    self._on_error(exc)
                break
            try:
                self._on_frame(frame)
            except Exception as exc:
                self._on_error(
                    RecoverableFrameError(
                        f"Frame listener failed: {str(exc) or type(exc).__name__}"
                    )
                )

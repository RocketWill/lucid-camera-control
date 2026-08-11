"""Bounded non-blocking raw AVI recording from owned Mono8 frames."""

from __future__ import annotations

import ctypes
import queue
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
from arena_api.__future__.save import Recorder
from arena_api.buffer import BufferFactory
from arena_api.enums import PixelFormat

from lucid_camera_control.media.frame import Frame


GIB = 1024**3
MIB = 1024**2


class RecordingBackend(Protocol):
    @property
    def output_path(self) -> Path | None: ...

    def open(self, width: int, height: int, fps: float, path: Path) -> None: ...

    def append_bgr8(self, image: np.ndarray) -> None: ...

    def close(self) -> None: ...


class ArenaRawAviBackend:
    def __init__(self) -> None:
        self._recorder: Recorder | None = None
        self._output_path: Path | None = None

    @property
    def output_path(self) -> Path | None:
        return self._output_path

    def open(self, width: int, height: int, fps: float, path: Path) -> None:
        recorder = Recorder(width, height, fps, threaded=False)
        recorder.codec = ("raw", "avi", "bgr8")
        # arena-api 2.8.2 exposes the Raw AVI codec but leaves the filename
        # validator at its MP4-only default. The native recorder itself accepts
        # AVI, so narrowly correct the SDK validator for this supported codec.
        pattern_manager = getattr(recorder, "_pattern_mngr", None)
        if pattern_manager is not None:
            pattern_manager.supported_extensions = (".avi",)
        supported_codec = getattr(recorder, "_supported_codec", None)
        if supported_codec is not None:
            # Recorder.open() sorts the raw/avi/bgr8 frozenset and incorrectly
            # treats the first token ("avi") as a PixelFormat. The native raw
            # AVI setter has already run, so retain only the correct conversion
            # format for that later Python-side lookup.
            supported_codec["_current"] = ("bgr8",)
        recorder.pattern = str(path)
        recorder.open()
        self._recorder = recorder
        self._output_path = path

    def append_bgr8(self, image: np.ndarray) -> None:
        if self._recorder is None:
            raise RuntimeError("Recorder is not open")
        contiguous = np.ascontiguousarray(image, dtype=np.uint8)
        pointer = contiguous.ctypes.data_as(ctypes.POINTER(ctypes.c_ubyte))
        buffer = BufferFactory.create(
            pointer,
            int(contiguous.nbytes),
            int(contiguous.shape[1]),
            int(contiguous.shape[0]),
            PixelFormat.BGR8,
        )
        try:
            self._recorder.append(buffer)
        finally:
            BufferFactory.destroy(buffer)

    def close(self) -> None:
        recorder, self._recorder = self._recorder, None
        if recorder is not None:
            recorder.close()
            if recorder.saved_videos:
                self._output_path = Path(recorder.saved_videos[-1])


@dataclass(frozen=True, slots=True)
class RecordingStatus:
    active: bool = False
    started_monotonic_ns: int | None = None
    frames_written: int = 0
    dropped_frames: int = 0
    output_path: Path | None = None
    error: str | None = None

    @property
    def duration_seconds(self) -> float:
        if self.started_monotonic_ns is None:
            return 0.0
        return max(0.0, (time.monotonic_ns() - self.started_monotonic_ns) / 1e9)


class RecorderService:
    def __init__(
        self,
        output_directory: Path,
        *,
        backend: RecordingBackend | None = None,
        queue_capacity: int = 120,
        minimum_start_bytes: int = 2 * GIB,
        minimum_continue_bytes: int = 512 * MIB,
    ) -> None:
        if queue_capacity < 1:
            raise ValueError("queue_capacity must be positive")
        self.output_directory = output_directory
        self._backend = backend or ArenaRawAviBackend()
        self._queue: queue.Queue[Frame] = queue.Queue(queue_capacity)
        self._minimum_start_bytes = minimum_start_bytes
        self._minimum_continue_bytes = minimum_continue_bytes
        self._latest: Frame | None = None
        self._status = RecordingStatus()
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None

    @property
    def status(self) -> RecordingStatus:
        with self._lock:
            return self._status

    def receive(self, frame: Frame) -> None:
        with self._lock:
            self._latest = frame
            active = self._status.active
        if not active:
            return
        try:
            self._queue.put_nowait(frame)
        except queue.Full:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                pass
            with self._lock:
                self._status = self._replace_status(
                    dropped_frames=self._status.dropped_frames + 1
                )
            self._queue.put_nowait(frame)

    def start(self, *, fps: float = 30.0, serial_number: str = "camera") -> None:
        with self._lock:
            if self._status.active:
                return
            frame = self._latest
        if frame is None:
            raise RuntimeError("No acquired frame is available for recording")
        self.output_directory.mkdir(parents=True, exist_ok=True)
        self._require_disk_space(self._minimum_start_bytes)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        safe_serial = "".join(
            c if c.isalnum() or c in "-_" else "_" for c in serial_number
        )
        path = self._available_path(f"{safe_serial}_{stamp}")
        self._backend.open(frame.width, frame.height, fps, path)
        with self._lock:
            self._status = RecordingStatus(True, time.monotonic_ns(), output_path=path)
        self._worker = threading.Thread(
            target=self._run,
            name="avi-recorder",
            daemon=False,
        )
        self._worker.start()

    def stop(self) -> None:
        with self._lock:
            if not self._status.active and self._worker is None:
                return
            self._status = self._replace_status(active=False)
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.join()
        self._backend.close()
        with self._lock:
            self._status = self._replace_status(output_path=self._backend.output_path)

    def _run(self) -> None:
        try:
            while self.status.active or not self._queue.empty():
                try:
                    frame = self._queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                try:
                    if shutil.disk_usage(self.output_directory).free < self._minimum_continue_bytes:
                        with self._lock:
                            self._status = self._replace_status(
                                active=False,
                                error="Recording stopped: free disk space is below 512 MiB",
                            )
                        continue
                    mono = frame.mono8_view()
                    bgr = np.repeat(mono[:, :, None], 3, axis=2)
                    self._backend.append_bgr8(bgr)
                    with self._lock:
                        self._status = self._replace_status(
                            frames_written=self._status.frames_written + 1
                        )
                finally:
                    self._queue.task_done()
        except Exception as exc:
            with self._lock:
                self._status = self._replace_status(
                    active=False,
                    error=str(exc) or type(exc).__name__,
                )
        finally:
            self._backend.close()
            with self._lock:
                self._status = self._replace_status(output_path=self._backend.output_path)

    def _require_disk_space(self, required: int) -> None:
        free = shutil.disk_usage(self.output_directory).free
        if free < required:
            raise OSError(
                f"At least {required / GIB:.1f} GiB free is required to record"
            )

    def _available_path(self, stem: str) -> Path:
        candidate = self.output_directory / f"{stem}.avi"
        count = 1
        while candidate.exists():
            candidate = self.output_directory / f"{stem}_{count}.avi"
            count += 1
        return candidate

    def _replace_status(self, **changes: object) -> RecordingStatus:
        values = {
            "active": self._status.active,
            "started_monotonic_ns": self._status.started_monotonic_ns,
            "frames_written": self._status.frames_written,
            "dropped_frames": self._status.dropped_frames,
            "output_path": self._status.output_path,
            "error": self._status.error,
        }
        values.update(changes)
        return RecordingStatus(**values)

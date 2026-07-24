"""Lossless screenshots from the latest owned acquisition frame."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import Lock

import cv2

from lucid_camera_control.media.frame import Frame


class ScreenshotService:
    def __init__(self, output_directory: Path) -> None:
        self.output_directory = output_directory
        self._latest: Frame | None = None
        self._lock = Lock()

    def receive(self, frame: Frame) -> None:
        with self._lock:
            self._latest = frame

    def capture(self, serial_number: str, now: datetime | None = None) -> Path:
        with self._lock:
            frame = self._latest
        if frame is None:
            raise RuntimeError("No acquired frame is available for screenshot")
        self.output_directory.mkdir(parents=True, exist_ok=True)
        timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S_%f")[:-3]
        safe_serial = "".join(c if c.isalnum() or c in "-_" else "_" for c in serial_number)
        stem = f"{safe_serial}_{timestamp}"
        path = self._available_path(stem, ".png")
        if not cv2.imwrite(str(path), frame.mono8_view()):
            raise OSError(f"Failed to save PNG screenshot: {path}")
        return path

    def _available_path(self, stem: str, suffix: str) -> Path:
        candidate = self.output_directory / f"{stem}{suffix}"
        count = 1
        while candidate.exists():
            candidate = self.output_directory / f"{stem}_{count}{suffix}"
            count += 1
        return candidate

"""Ports implemented by concrete camera adapters."""

from __future__ import annotations

from typing import Protocol

from lucid_camera_control.camera.models import CameraDescriptor


class CameraPort(Protocol):
    """Minimal camera lifecycle needed by the application controller."""

    def discover(self) -> tuple[CameraDescriptor, ...]: ...

    def connect(self, serial_number: str) -> CameraDescriptor: ...

    def close(self) -> None: ...

    def start_stream(self) -> None: ...

    def stop_stream(self) -> None: ...


class RecorderPort(Protocol):
    """Minimal recorder lifecycle needed by the application controller."""

    def start(self) -> None: ...

    def stop(self) -> None: ...


class NullRecorder:
    """Recorder placeholder used before the media implementation ticket."""

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None


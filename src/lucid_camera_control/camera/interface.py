"""Ports implemented by concrete camera adapters."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol
from pathlib import Path

from lucid_camera_control.camera.models import CameraDescriptor
from lucid_camera_control.camera.controls import (
    CameraControlCapabilities,
    CameraControlRequest,
    CameraControlResult,
)
from lucid_camera_control.camera.roi import RoiCapabilities, RoiRequest, RoiResult
from lucid_camera_control.media.frame import Frame
from lucid_camera_control.camera.reset import FactoryResetResult


class CameraPort(Protocol):
    """Minimal camera lifecycle needed by the application controller."""

    def discover(self) -> tuple[CameraDescriptor, ...]: ...

    def connect(self, serial_number: str) -> CameraDescriptor: ...

    def close(self) -> None: ...

    def start_stream(self) -> None: ...

    def stop_stream(self) -> None: ...

    def roi_capabilities(self) -> RoiCapabilities: ...

    def apply_roi(self, request: RoiRequest) -> RoiResult: ...

    def control_capabilities(self) -> CameraControlCapabilities: ...

    def apply_controls(self, request: CameraControlRequest) -> CameraControlResult: ...

    def factory_reset(self) -> FactoryResetResult: ...

    def subscribe_frames(self, listener: Callable[[Frame], None]) -> Callable[[], None]: ...

    def subscribe_acquisition_errors(
        self, listener: Callable[[Exception], None]
    ) -> Callable[[], None]: ...


class RecorderPort(Protocol):
    """Minimal recorder lifecycle needed by the application controller."""

    def start(self, *, fps: float, serial_number: str) -> None: ...

    def stop(self) -> None: ...


class NullRecorder:
    """Recorder placeholder used before the media implementation ticket."""

    def start(self, *, fps: float, serial_number: str) -> None:
        return None

    def stop(self) -> None:
        return None


class ScreenshotPort(Protocol):
    def capture(self, serial_number: str) -> Path: ...


class NullScreenshot:
    def capture(self, serial_number: str) -> Path:
        raise RuntimeError("Screenshot service is unavailable")

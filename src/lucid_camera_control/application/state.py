"""Immutable application state."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from lucid_camera_control.camera.models import CameraDescriptor
from lucid_camera_control.camera.roi import RoiCapabilities, RoiResult
from lucid_camera_control.camera.controls import (
    CameraControlCapabilities,
    CameraControlResult,
)
from lucid_camera_control.config.models import AppConfigV1


class CameraState(StrEnum):
    DISCONNECTED = "Disconnected"
    CONNECTED = "Connected"
    STREAMING = "Streaming"
    RECORDING = "Recording"


@dataclass(frozen=True, slots=True)
class ErrorInfo:
    operation: str
    message: str
    recoverable: bool = True


@dataclass(frozen=True, slots=True)
class ApplicationSnapshot:
    state: CameraState = CameraState.DISCONNECTED
    discovered_cameras: tuple[CameraDescriptor, ...] = ()
    active_camera: CameraDescriptor | None = None
    last_error: ErrorInfo | None = None
    roi_capabilities: RoiCapabilities | None = None
    roi_result: RoiResult | None = None
    control_capabilities: CameraControlCapabilities | None = None
    control_result: CameraControlResult | None = None
    last_screenshot_path: Path | None = None
    applied_configuration: AppConfigV1 | None = None

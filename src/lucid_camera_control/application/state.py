"""Immutable application state."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from lucid_camera_control.camera.models import CameraDescriptor
from lucid_camera_control.camera.roi import RoiCapabilities, RoiResult


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

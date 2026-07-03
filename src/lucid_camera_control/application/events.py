"""Events published after application commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from lucid_camera_control.application.state import CameraState, ErrorInfo
from lucid_camera_control.camera.models import CameraDescriptor
from lucid_camera_control.camera.roi import RoiResult


@dataclass(frozen=True, slots=True)
class CamerasDiscovered:
    cameras: tuple[CameraDescriptor, ...]


@dataclass(frozen=True, slots=True)
class StateChanged:
    previous: CameraState
    current: CameraState


@dataclass(frozen=True, slots=True)
class OperationFailed:
    error: ErrorInfo


@dataclass(frozen=True, slots=True)
class RoiApplied:
    result: RoiResult


ApplicationEvent: TypeAlias = CamerasDiscovered | StateChanged | OperationFailed | RoiApplied

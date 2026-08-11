"""Events published after application commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias
from pathlib import Path

from lucid_camera_control.application.state import CameraState, ErrorInfo
from lucid_camera_control.camera.models import CameraDescriptor
from lucid_camera_control.camera.roi import RoiResult
from lucid_camera_control.camera.controls import CameraControlResult
from lucid_camera_control.config.models import AppConfigV1
from lucid_camera_control.camera.reset import FactoryResetResult


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


@dataclass(frozen=True, slots=True)
class CameraControlsApplied:
    result: CameraControlResult


@dataclass(frozen=True, slots=True)
class ScreenshotSaved:
    path: Path


@dataclass(frozen=True, slots=True)
class ConfigurationApplied:
    config: AppConfigV1
    roi_result: RoiResult
    controls_result: CameraControlResult


@dataclass(frozen=True, slots=True)
class FactoryDefaultsLoaded:
    result: FactoryResetResult


ApplicationEvent: TypeAlias = (
    CamerasDiscovered
    | StateChanged
    | OperationFailed
    | RoiApplied
    | CameraControlsApplied
    | ScreenshotSaved
    | ConfigurationApplied
    | FactoryDefaultsLoaded
)

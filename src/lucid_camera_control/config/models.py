"""Versioned, strictly validated JSON configuration schema."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lucid_camera_control.camera.controls import CameraControlRequest
from lucid_camera_control.camera.roi import RoiRequest


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RoiConfig(StrictModel):
    enabled: bool = False
    width: int = Field(default=0, ge=0)
    height: int = Field(default=0, ge=0)
    centered: bool = True
    offset_x: int = Field(default=0, ge=0)
    offset_y: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_enabled_dimensions(self) -> "RoiConfig":
        if self.enabled and (self.width < 1 or self.height < 1):
            raise ValueError("Enabled ROI requires positive width and height")
        return self

    def request(self) -> RoiRequest:
        return RoiRequest(
            self.enabled,
            self.width,
            self.height,
            self.centered,
            self.offset_x,
            self.offset_y,
        )


class CameraControlsConfig(StrictModel):
    exposure_auto: bool = True
    exposure_time: float = Field(default=1000.0, gt=0)
    gain_auto: bool = False
    gain: float = Field(default=0.0, ge=0)
    frame_rate_enabled: bool = False
    frame_rate: float = Field(default=30.0, gt=0)
    gamma_enabled: bool | None = None
    gamma: float | None = Field(default=None, gt=0)
    black_level: float | None = Field(default=None, ge=0)
    white_balance_auto: bool | None = None
    binning: Literal[1, 2] | None = 1

    def request(self) -> CameraControlRequest:
        return CameraControlRequest(**self.model_dump())


class WindowConfig(StrictModel):
    width: int = Field(default=1100, ge=640, le=7680)
    height: int = Field(default=720, ge=480, le=4320)
    maximized: bool = False


class AppConfigV1(StrictModel):
    schema_version: Literal[1] = 1
    preferred_camera_serial: str | None = Field(default=None, max_length=256)
    roi: RoiConfig = Field(default_factory=RoiConfig)
    controls: CameraControlsConfig = Field(default_factory=CameraControlsConfig)
    screenshot_directory: Path = Field(
        default_factory=lambda: Path.home() / "Pictures" / "LUCID Camera Control"
    )
    recording_directory: Path = Field(
        default_factory=lambda: Path.home() / "Videos" / "LUCID Camera Control"
    )
    preview_contrast: float = Field(default=1.0, ge=0.1, le=3.0)
    window: WindowConfig = Field(default_factory=WindowConfig)

    @model_validator(mode="after")
    def validate_roi_binning_exclusion(self) -> "AppConfigV1":
        if self.roi.enabled and self.controls.binning == 2:
            raise ValueError("Hardware ROI and 2x2 binning are mutually exclusive")
        return self

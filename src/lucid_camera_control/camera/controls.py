"""Capability-driven camera controls and verified application flow."""

from __future__ import annotations

from dataclasses import dataclass

from lucid_camera_control.camera.nodes import NodeAccessor, NodeCapability, NodeWriteResult


@dataclass(frozen=True, slots=True)
class CameraControlCapabilities:
    exposure_auto: NodeCapability
    exposure_time: NodeCapability
    gain_auto: NodeCapability
    gain: NodeCapability
    frame_rate_enable: NodeCapability
    frame_rate: NodeCapability
    gamma_enable: NodeCapability
    gamma: NodeCapability
    black_level: NodeCapability
    white_balance_auto: NodeCapability
    binning_horizontal: NodeCapability
    binning_vertical: NodeCapability


@dataclass(frozen=True, slots=True)
class CameraControlRequest:
    exposure_auto: bool
    exposure_time: float
    gain_auto: bool
    gain: float
    frame_rate_enabled: bool
    frame_rate: float
    gamma_enabled: bool | None = None
    gamma: float | None = None
    black_level: float | None = None
    white_balance_auto: bool | None = None
    binning: int | None = 1


@dataclass(frozen=True, slots=True)
class CameraControlResult:
    requested: CameraControlRequest
    writes: tuple[NodeWriteResult, ...]
    capabilities: CameraControlCapabilities


class CameraControls:
    """Apply dependent GenICam controls in an order that keeps nodes writable."""

    def __init__(self, nodes: NodeAccessor) -> None:
        self._nodes = nodes

    def capabilities(self) -> CameraControlCapabilities:
        get = self._nodes.snapshot
        return CameraControlCapabilities(
            exposure_auto=get("ExposureAuto"),
            exposure_time=get("ExposureTime"),
            gain_auto=get("GainAuto"),
            gain=get("Gain"),
            frame_rate_enable=get("AcquisitionFrameRateEnable"),
            frame_rate=get("AcquisitionFrameRate"),
            gamma_enable=get("GammaEnable"),
            gamma=get("Gamma"),
            black_level=get("BlackLevel"),
            white_balance_auto=get("BalanceWhiteAuto"),
            binning_horizontal=get("BinningHorizontal"),
            binning_vertical=get("BinningVertical"),
        )

    def apply(self, request: CameraControlRequest) -> CameraControlResult:
        if request.binning not in (None, 1, 2):
            raise ValueError("Binning must be 1x1 or 2x2")
        writes: list[NodeWriteResult] = []
        writes.append(self._auto("ExposureAuto", request.exposure_auto))
        if not request.exposure_auto:
            writes.append(self._nodes.write_numeric("ExposureTime", request.exposure_time))
        writes.append(self._auto("GainAuto", request.gain_auto))
        if not request.gain_auto:
            writes.append(self._nodes.write_numeric("Gain", request.gain))
        writes.append(
            self._nodes.write_boolean(
                "AcquisitionFrameRateEnable", request.frame_rate_enabled
            )
        )
        if request.frame_rate_enabled:
            writes.append(
                self._nodes.write_numeric("AcquisitionFrameRate", request.frame_rate)
            )
        if request.gamma_enabled is not None:
            writes.append(self._nodes.write_boolean("GammaEnable", request.gamma_enabled))
            if request.gamma_enabled and request.gamma is not None:
                writes.append(self._nodes.write_numeric("Gamma", request.gamma))
        if request.black_level is not None:
            writes.append(self._nodes.write_numeric("BlackLevel", request.black_level))
        if request.white_balance_auto is not None:
            writes.append(self._auto("BalanceWhiteAuto", request.white_balance_auto))
        if request.binning is not None:
            writes.append(
                self._nodes.write_numeric("BinningHorizontal", request.binning)
            )
            writes.append(self._nodes.write_numeric("BinningVertical", request.binning))
        return CameraControlResult(request, tuple(writes), self.capabilities())

    def _auto(self, name: str, enabled: bool) -> NodeWriteResult:
        capability = self._nodes.snapshot(name)
        desired = "Continuous" if enabled else "Off"
        if desired not in capability.choices:
            raise ValueError(f"{name} does not support {desired}")
        return self._nodes.write_enumeration(name, desired)

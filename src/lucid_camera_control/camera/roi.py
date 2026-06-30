"""Transactional hardware ROI configuration."""

from __future__ import annotations

from dataclasses import dataclass

from lucid_camera_control.camera.nodes import (
    NodeAccessError,
    NodeAccessor,
    NodeCapability,
    NodeWriteResult,
)


@dataclass(frozen=True, slots=True)
class RoiRequest:
    enabled: bool
    width: int = 0
    height: int = 0
    centered: bool = True
    offset_x: int = 0
    offset_y: int = 0


@dataclass(frozen=True, slots=True)
class AppliedRoi:
    enabled: bool
    width: int
    height: int
    offset_x: int
    offset_y: int
    centered: bool


@dataclass(frozen=True, slots=True)
class RoiCapabilities:
    width: NodeCapability
    height: NodeCapability
    offset_x: NodeCapability
    offset_y: NodeCapability
    pixel_format: NodeCapability


@dataclass(frozen=True, slots=True)
class RoiResult:
    requested: RoiRequest
    applied: AppliedRoi
    adjustments: tuple[NodeWriteResult, ...]
    capabilities: RoiCapabilities
    payload_size: int | None
    maximum_fps: float | None


class RoiTransactionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        cause: Exception,
        rollback_errors: tuple[str, ...],
    ) -> None:
        rollback = "; ".join(rollback_errors) if rollback_errors else "successful"
        super().__init__(f"{message}: {cause}; rollback={rollback}")
        self.cause = cause
        self.rollback_errors = rollback_errors


class RoiTransaction:
    ROI_NODES = ("Width", "Height", "OffsetX", "OffsetY", "PixelFormat")
    ROLLBACK_NODES = (
        "Width",
        "Height",
        "OffsetX",
        "OffsetY",
        "PixelFormat",
        "BinningHorizontal",
        "BinningVertical",
    )

    def __init__(self, nodes: NodeAccessor) -> None:
        self._nodes = nodes

    def capabilities(self) -> RoiCapabilities:
        width, height, offset_x, offset_y, pixel_format = self._nodes.snapshot_many(
            self.ROI_NODES
        )
        return RoiCapabilities(width, height, offset_x, offset_y, pixel_format)

    def apply(self, request: RoiRequest) -> RoiResult:
        original = {
            capability.name: capability.value
            for capability in self._nodes.snapshot_many(self.ROLLBACK_NODES)
            if capability.available and capability.readable
        }
        adjustments: list[NodeWriteResult] = []
        try:
            if request.enabled:
                self._force_one_by_one_binning(adjustments)
            adjustments.extend(self._set_offsets_to_minimum())

            dimensions = self.capabilities()
            self._require_roi_nodes(dimensions)
            sensor_width = self._required_integer_max(dimensions.width)
            sensor_height = self._required_integer_max(dimensions.height)

            requested_width = request.width if request.enabled else sensor_width
            requested_height = request.height if request.enabled else sensor_height
            width = self._nodes.write_numeric("Width", requested_width)
            height = self._nodes.write_numeric("Height", requested_height)
            adjustments.extend((width, height))

            offsets = self.capabilities()
            if request.enabled and request.centered:
                requested_x = (sensor_width - int(width.applied)) // 2
                requested_y = (sensor_height - int(height.applied)) // 2
            elif request.enabled:
                requested_x = request.offset_x
                requested_y = request.offset_y
            else:
                requested_x = self._required_integer_min(offsets.offset_x)
                requested_y = self._required_integer_min(offsets.offset_y)
            offset_x = self._nodes.write_numeric("OffsetX", requested_x)
            offset_y = self._nodes.write_numeric("OffsetY", requested_y)
            adjustments.extend((offset_x, offset_y))

            pixel_format = self._nodes.write_enumeration("PixelFormat", "Mono8")
            adjustments.append(pixel_format)
        except Exception as exc:
            rollback_errors = self._rollback(original)
            raise RoiTransactionError(
                "Hardware ROI configuration failed",
                cause=exc,
                rollback_errors=rollback_errors,
            ) from exc

        refreshed = self.capabilities()
        payload = self._integer_value("PayloadSize")
        maximum_fps = self._float_max("AcquisitionFrameRate")
        applied = AppliedRoi(
            enabled=request.enabled,
            width=int(width.applied),
            height=int(height.applied),
            offset_x=int(offset_x.applied),
            offset_y=int(offset_y.applied),
            centered=request.centered if request.enabled else False,
        )
        return RoiResult(
            requested=request,
            applied=applied,
            adjustments=tuple(adjustments),
            capabilities=refreshed,
            payload_size=payload,
            maximum_fps=maximum_fps,
        )

    def _force_one_by_one_binning(self, results: list[NodeWriteResult]) -> None:
        for name in ("BinningHorizontal", "BinningVertical"):
            capability = self._nodes.snapshot(name)
            if capability.available:
                results.append(self._nodes.write_numeric(name, 1))

    def _set_offsets_to_minimum(self) -> tuple[NodeWriteResult, NodeWriteResult]:
        offset_x = self._nodes.snapshot("OffsetX")
        offset_y = self._nodes.snapshot("OffsetY")
        return (
            self._nodes.write_numeric("OffsetX", self._required_integer_min(offset_x)),
            self._nodes.write_numeric("OffsetY", self._required_integer_min(offset_y)),
        )

    def _rollback(self, original: dict[str, object]) -> tuple[str, ...]:
        errors: list[str] = []

        def restore_numeric(name: str, value: object) -> None:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return
            try:
                self._nodes.write_numeric(name, value)
            except Exception as exc:
                errors.append(f"{name}: {exc}")

        for name in ("OffsetX", "OffsetY"):
            capability = self._nodes.snapshot(name)
            if capability.available and capability.minimum is not None:
                restore_numeric(name, capability.minimum)
        for name in ("BinningHorizontal", "BinningVertical", "Width", "Height"):
            if name in original:
                restore_numeric(name, original[name])
        for name in ("OffsetX", "OffsetY"):
            if name in original:
                restore_numeric(name, original[name])
        if isinstance(original.get("PixelFormat"), str):
            try:
                self._nodes.write_enumeration("PixelFormat", original["PixelFormat"])
            except Exception as exc:
                errors.append(f"PixelFormat: {exc}")
        return tuple(errors)

    @staticmethod
    def _require_roi_nodes(capabilities: RoiCapabilities) -> None:
        for capability in (
            capabilities.width,
            capabilities.height,
            capabilities.offset_x,
            capabilities.offset_y,
            capabilities.pixel_format,
        ):
            if not capability.available:
                raise NodeAccessError(capability.name, "required ROI node is unavailable")
            if not capability.writable:
                raise NodeAccessError(
                    capability.name,
                    "required ROI node is not writable",
                    capability,
                )

    @staticmethod
    def _required_integer_min(capability: NodeCapability) -> int:
        if not isinstance(capability.minimum, int):
            raise NodeAccessError(capability.name, "integer minimum is unavailable", capability)
        return capability.minimum

    @staticmethod
    def _required_integer_max(capability: NodeCapability) -> int:
        if not isinstance(capability.maximum, int):
            raise NodeAccessError(capability.name, "integer maximum is unavailable", capability)
        return capability.maximum

    def _integer_value(self, name: str) -> int | None:
        value = self._nodes.snapshot(name).value
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    def _float_max(self, name: str) -> float | None:
        value = self._nodes.snapshot(name).maximum
        return float(value) if isinstance(value, (int, float)) else None


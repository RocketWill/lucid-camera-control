"""Arena SDK implementation of camera discovery and lifecycle."""

from __future__ import annotations

import ctypes
import time
from collections.abc import Mapping
from collections.abc import Callable
from typing import Any, Protocol

from arena_api.system import system as arena_system

from lucid_camera_control.camera.models import CameraDescriptor
from lucid_camera_control.camera.acquisition import AcquisitionWorker, RecoverableFrameError
from lucid_camera_control.camera.controls import (
    CameraControlCapabilities,
    CameraControlRequest,
    CameraControlResult,
    CameraControls,
)
from lucid_camera_control.camera.nodes import (
    NodeAccessor,
    NodeCapability,
    NodeWriteResult,
)
from lucid_camera_control.camera.roi import (
    RoiCapabilities,
    RoiRequest,
    RoiResult,
    RoiTransaction,
)
from lucid_camera_control.media.frame import Frame
from lucid_camera_control.camera.reset import FactoryResetResult, FactoryResetTransaction


class ArenaSystemLike(Protocol):
    @property
    def device_infos(self) -> list[dict[str, Any]]: ...

    def create_device(self, device_info: dict[str, Any]) -> list[Any]: ...

    def destroy_device(self, device: Any) -> None: ...


class CameraNotFoundError(LookupError):
    """The requested serial number was not found during fresh discovery."""


class CameraConnectionError(RuntimeError):
    """Arena did not create the requested camera device."""


class CameraNotConnectedError(RuntimeError):
    """An operation requires an active Arena device."""


class ArenaCameraSystem:
    """Own exactly one Arena device while exposing a testable lifecycle port."""

    def __init__(self, system: ArenaSystemLike | None = None) -> None:
        self._system = system or arena_system
        self._device: Any | None = None
        self._active_descriptor: CameraDescriptor | None = None
        self._streaming = False
        self._acquisition_worker: AcquisitionWorker | None = None
        self._frame_listeners: list[Callable[[Frame], None]] = []
        self._error_listeners: list[Callable[[Exception], None]] = []

    @property
    def active_descriptor(self) -> CameraDescriptor | None:
        return self._active_descriptor

    @property
    def is_connected(self) -> bool:
        return self._device is not None

    def discover(self) -> tuple[CameraDescriptor, ...]:
        descriptors: list[CameraDescriptor] = []
        for info in self._system.device_infos:
            descriptor = self._descriptor_from_info(info)
            if descriptor is not None:
                descriptors.append(descriptor)
        return tuple(sorted(descriptors, key=lambda item: item.serial_number))

    def connect(self, serial_number: str) -> CameraDescriptor:
        if self._device is not None:
            raise CameraConnectionError("A camera is already connected")

        requested = serial_number.strip()
        if not requested:
            raise CameraNotFoundError("Camera serial number is required")

        selected_info: dict[str, Any] | None = None
        selected_descriptor: CameraDescriptor | None = None
        for info in self._system.device_infos:
            descriptor = self._descriptor_from_info(info)
            if descriptor is not None and descriptor.serial_number == requested:
                selected_info = dict(info)
                selected_descriptor = descriptor
                break

        if selected_info is None or selected_descriptor is None:
            raise CameraNotFoundError(f"LUCID camera {requested!r} was not found")

        devices = self._system.create_device(selected_info)
        if len(devices) != 1:
            for device in devices:
                self._system.destroy_device(device)
            raise CameraConnectionError(
                f"Arena created {len(devices)} devices for serial {requested!r}"
            )

        self._device = devices[0]
        self._active_descriptor = selected_descriptor
        return selected_descriptor

    def close(self) -> None:
        if self._device is None:
            return
        stop_error: Exception | None = None
        if self._streaming:
            try:
                self.stop_stream()
            except Exception as exc:
                stop_error = exc
        device, self._device = self._device, None
        self._active_descriptor = None
        self._streaming = False
        self._acquisition_worker = None
        self._system.destroy_device(device)
        if stop_error is not None:
            raise stop_error

    def start_stream(self) -> None:
        if self._streaming:
            return
        device = self._require_device()
        device_nodes = NodeAccessor(device.nodemap)
        pixel_format = device_nodes.snapshot("PixelFormat")
        if pixel_format.value != "Mono8":
            device_nodes.write_enumeration("PixelFormat", "Mono8")
        acquisition_mode = device_nodes.snapshot("AcquisitionMode")
        if acquisition_mode.available and acquisition_mode.writable:
            device_nodes.write_enumeration("AcquisitionMode", "Continuous")
        self._configure_optional_stream_nodes(device)
        device.start_stream(20)
        self._streaming = True
        if self._frame_listeners:
            self._acquisition_worker = AcquisitionWorker(
                self,
                self._publish_frame,
                self._publish_error,
            )
            self._acquisition_worker.start()

    def stop_stream(self) -> None:
        if not self._streaming:
            return
        worker, self._acquisition_worker = self._acquisition_worker, None
        worker_error: Exception | None = None
        if worker is not None:
            try:
                worker.stop()
            except Exception as exc:
                worker_error = exc
        try:
            self._require_device().stop_stream()
        finally:
            self._streaming = False
        if worker_error is not None:
            raise worker_error

    def acquire_frame(self, timeout_ms: int) -> Frame:
        if not self._streaming:
            raise RuntimeError("Camera stream is not running")
        device = self._require_device()
        buffer = device.get_buffer(timeout=timeout_ms)
        try:
            if buffer.is_incomplete:
                raise RecoverableFrameError(
                    f"Incomplete Arena buffer frame_id={buffer.frame_id}"
                )
            pixel_format = buffer.pixel_format.name
            if pixel_format != "Mono8":
                raise RecoverableFrameError(
                    f"Expected Mono8 buffer, got {pixel_format}"
                )
            width = int(buffer.width)
            height = int(buffer.height)
            row_stride = width + int(buffer.padding_x)
            data = ctypes.string_at(buffer.pdata, row_stride * height)
            return Frame(
                sequence=int(buffer.frame_id),
                received_monotonic_ns=time.monotonic_ns(),
                camera_timestamp_ns=int(buffer.timestamp_ns),
                width=width,
                height=height,
                row_stride=row_stride,
                pixel_format=pixel_format,
                data=data,
            )
        finally:
            device.requeue_buffer(buffer)

    def subscribe_frames(self, listener: Callable[[Frame], None]) -> Callable[[], None]:
        self._frame_listeners.append(listener)
        return lambda: self._remove_listener(self._frame_listeners, listener)

    def subscribe_acquisition_errors(
        self,
        listener: Callable[[Exception], None],
    ) -> Callable[[], None]:
        self._error_listeners.append(listener)
        return lambda: self._remove_listener(self._error_listeners, listener)

    def node_capability(self, name: str) -> NodeCapability:
        return self._node_accessor().snapshot(name)

    def node_capabilities(self, names: tuple[str, ...]) -> tuple[NodeCapability, ...]:
        return self._node_accessor().snapshot_many(names)

    def write_numeric_node(self, name: str, value: int | float) -> NodeWriteResult:
        return self._node_accessor().write_numeric(name, value)

    def write_enumeration_node(self, name: str, value: str) -> NodeWriteResult:
        return self._node_accessor().write_enumeration(name, value)

    def write_boolean_node(self, name: str, value: bool) -> NodeWriteResult:
        return self._node_accessor().write_boolean(name, value)

    def roi_capabilities(self) -> RoiCapabilities:
        return RoiTransaction(self._node_accessor()).capabilities()

    def apply_roi(self, request: RoiRequest) -> RoiResult:
        return RoiTransaction(self._node_accessor()).apply(request)

    def control_capabilities(self) -> CameraControlCapabilities:
        return CameraControls(self._node_accessor()).capabilities()

    def apply_controls(self, request: CameraControlRequest) -> CameraControlResult:
        return CameraControls(self._node_accessor()).apply(request)

    def factory_reset(self) -> FactoryResetResult:
        return FactoryResetTransaction(self._node_accessor()).apply()

    def _require_device(self) -> Any:
        if self._device is None:
            raise CameraNotConnectedError("No camera is connected")
        return self._device

    def _node_accessor(self) -> NodeAccessor:
        return NodeAccessor(self._require_device().nodemap)

    @staticmethod
    def _configure_optional_stream_nodes(device: Any) -> None:
        stream_nodes = NodeAccessor(device.tl_stream_nodemap)
        for name in ("StreamAutoNegotiatePacketSize", "StreamPacketResendEnable"):
            capability = stream_nodes.snapshot(name)
            if capability.available and capability.writable:
                stream_nodes.write_boolean(name, True)
        handling = stream_nodes.snapshot("StreamBufferHandlingMode")
        if (
            handling.available
            and handling.writable
            and "NewestOnly" in handling.choices
        ):
            stream_nodes.write_enumeration("StreamBufferHandlingMode", "NewestOnly")

    def _publish_frame(self, frame: Frame) -> None:
        for listener in tuple(self._frame_listeners):
            listener(frame)

    def _publish_error(self, error: Exception) -> None:
        for listener in tuple(self._error_listeners):
            listener(error)

    @staticmethod
    def _remove_listener(listeners: list[Any], listener: Any) -> None:
        if listener in listeners:
            listeners.remove(listener)

    @classmethod
    def _descriptor_from_info(
        cls,
        info: Mapping[str, Any],
    ) -> CameraDescriptor | None:
        vendor = cls._optional_text(info.get("vendor"))
        serial = cls._optional_text(info.get("serial"))
        if vendor is None or "lucid" not in vendor.casefold() or serial is None:
            return None
        return CameraDescriptor(
            serial_number=serial,
            model_name=cls._optional_text(info.get("model")),
            vendor_name=vendor,
            user_defined_name=cls._optional_text(info.get("name")),
            ip_address=cls._optional_text(info.get("ip")),
            mac_address=cls._optional_text(info.get("mac")),
            firmware_version=cls._optional_text(info.get("version")),
        )

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

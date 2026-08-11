"""Hardware-independent application controller."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
import logging

from lucid_camera_control.application.commands import (
    ApplicationCommand,
    ApplyCameraControls,
    ApplyConfiguration,
    CaptureScreenshot,
    ResetFactoryDefaults,
    HandleDeviceLoss,
    ApplyRoi,
    CloseCamera,
    ConnectCamera,
    ExploreCameras,
    StartRecording,
    StartStream,
    StopRecording,
    StopStream,
)
from lucid_camera_control.application.events import (
    ApplicationEvent,
    CameraControlsApplied,
    ScreenshotSaved,
    ConfigurationApplied,
    FactoryDefaultsLoaded,
    CamerasDiscovered,
    OperationFailed,
    RoiApplied,
    StateChanged,
)
from lucid_camera_control.application.state import (
    ApplicationSnapshot,
    CameraState,
    ErrorInfo,
)
from lucid_camera_control.camera.interface import (
    CameraPort,
    NullRecorder,
    NullScreenshot,
    RecorderPort,
    ScreenshotPort,
)

EventListener = Callable[[ApplicationEvent, ApplicationSnapshot], None]
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


class InvalidTransitionError(RuntimeError):
    """Raised when a command is invalid for the current state."""


class ApplicationController:
    """Own camera lifecycle state without depending on Qt or Arena."""

    def __init__(
        self,
        camera: CameraPort,
        recorder: RecorderPort | None = None,
        screenshot: ScreenshotPort | None = None,
    ) -> None:
        self._camera = camera
        self._recorder = recorder or NullRecorder()
        self._screenshot = screenshot or NullScreenshot()
        self._snapshot = ApplicationSnapshot()
        self._listeners: list[EventListener] = []

    @property
    def snapshot(self) -> ApplicationSnapshot:
        return self._snapshot

    def subscribe(self, listener: EventListener) -> Callable[[], None]:
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def execute(self, command: ApplicationCommand) -> tuple[ApplicationEvent, ...]:
        try:
            events = self._dispatch(command)
        except InvalidTransitionError:
            raise
        except Exception as exc:
            logger.exception("operation_failed operation=%s", type(command).__name__)
            error = ErrorInfo(type(command).__name__, str(exc) or type(exc).__name__)
            self._snapshot = replace(self._snapshot, last_error=error)
            events = (OperationFailed(error),)

        for event in events:
            for listener in tuple(self._listeners):
                listener(event, self._snapshot)
        logger.info(
            "command_completed operation=%s state=%s events=%s",
            type(command).__name__,
            self._snapshot.state.value,
            ",".join(type(event).__name__ for event in events),
        )
        return events

    def _dispatch(self, command: ApplicationCommand) -> tuple[ApplicationEvent, ...]:
        match command:
            case ExploreCameras():
                return self._explore()
            case ConnectCamera(serial_number=serial_number):
                return self._connect(serial_number)
            case CloseCamera():
                return self._close()
            case StartStream():
                return self._start_stream()
            case StopStream():
                return self._stop_stream()
            case StartRecording():
                return self._start_recording()
            case StopRecording():
                return self._stop_recording()
            case ApplyRoi(request=request):
                return self._apply_roi(request)
            case ApplyCameraControls(request=request):
                return self._apply_controls(request)
            case CaptureScreenshot():
                return self._capture_screenshot()
            case ApplyConfiguration(config=config):
                return self._apply_configuration(config)
            case ResetFactoryDefaults():
                return self._factory_reset()
            case HandleDeviceLoss(message=message):
                return self._handle_device_loss(message)
        raise TypeError(f"Unsupported command: {type(command).__name__}")

    def _explore(self) -> tuple[ApplicationEvent, ...]:
        self._require(CameraState.DISCONNECTED, "ExploreCameras")
        cameras = tuple(self._camera.discover())
        self._snapshot = replace(
            self._snapshot,
            discovered_cameras=cameras,
            last_error=None,
        )
        return (CamerasDiscovered(cameras),)

    def _connect(self, serial_number: str) -> tuple[ApplicationEvent, ...]:
        self._require(CameraState.DISCONNECTED, "ConnectCamera")
        descriptor = self._camera.connect(serial_number)
        try:
            roi_capabilities = self._camera.roi_capabilities()
            control_capabilities = self._camera.control_capabilities()
        except Exception:
            self._camera.close()
            raise
        previous = self._snapshot.state
        self._snapshot = replace(
            self._snapshot,
            state=CameraState.CONNECTED,
            active_camera=descriptor,
            roi_capabilities=roi_capabilities,
            roi_result=None,
            control_capabilities=control_capabilities,
            control_result=None,
            last_error=None,
        )
        return (StateChanged(previous, CameraState.CONNECTED),)

    def _close(self) -> tuple[ApplicationEvent, ...]:
        previous = self._snapshot.state
        if previous is CameraState.DISCONNECTED:
            return ()

        cleanup_errors: list[str] = []
        if previous is CameraState.RECORDING:
            self._attempt_cleanup(self._recorder.stop, cleanup_errors)
        if previous in (CameraState.STREAMING, CameraState.RECORDING):
            self._attempt_cleanup(self._camera.stop_stream, cleanup_errors)
        self._attempt_cleanup(self._camera.close, cleanup_errors)

        error = (
            ErrorInfo("CloseCamera", "; ".join(cleanup_errors))
            if cleanup_errors
            else None
        )
        self._snapshot = replace(
            self._snapshot,
            state=CameraState.DISCONNECTED,
            active_camera=None,
            roi_capabilities=None,
            roi_result=None,
            control_capabilities=None,
            control_result=None,
            last_error=error,
        )
        events: list[ApplicationEvent] = [
            StateChanged(previous, CameraState.DISCONNECTED)
        ]
        if error:
            events.append(OperationFailed(error))
        return tuple(events)

    def _start_stream(self) -> tuple[ApplicationEvent, ...]:
        self._require(CameraState.CONNECTED, "StartStream")
        self._camera.start_stream()
        return self._transition(CameraState.STREAMING)

    def _stop_stream(self) -> tuple[ApplicationEvent, ...]:
        if self._snapshot.state is CameraState.CONNECTED:
            return ()
        self._require(CameraState.STREAMING, "StopStream")
        self._camera.stop_stream()
        return self._transition(CameraState.CONNECTED)

    def _start_recording(self) -> tuple[ApplicationEvent, ...]:
        self._require(CameraState.STREAMING, "StartRecording")
        active = self._snapshot.active_camera
        if active is None:
            raise RuntimeError("No active camera")
        caps = self._snapshot.control_capabilities
        fps_value = caps.frame_rate.value if caps is not None else None
        fps = float(fps_value) if isinstance(fps_value, (int, float)) else 30.0
        self._recorder.start(fps=fps, serial_number=active.serial_number)
        return self._transition(CameraState.RECORDING)

    def _stop_recording(self) -> tuple[ApplicationEvent, ...]:
        if self._snapshot.state is CameraState.STREAMING:
            return ()
        self._require(CameraState.RECORDING, "StopRecording")
        self._recorder.stop()
        return self._transition(CameraState.STREAMING)

    def _apply_roi(self, request: object) -> tuple[ApplicationEvent, ...]:
        from lucid_camera_control.camera.roi import RoiRequest

        if not isinstance(request, RoiRequest):
            raise TypeError("ApplyRoi requires RoiRequest")
        if self._snapshot.state not in (CameraState.CONNECTED, CameraState.STREAMING):
            raise InvalidTransitionError(
                "ApplyRoi requires Connected or Streaming; "
                f"current state is {self._snapshot.state.value}"
            )
        binning = self._snapshot.control_capabilities
        if (
            request.enabled
            and binning is not None
            and int(binning.binning_horizontal.value or 1) > 1
        ):
            raise InvalidTransitionError("Hardware ROI requires 1x1 binning")
        was_streaming = self._snapshot.state is CameraState.STREAMING
        if was_streaming:
            self._camera.stop_stream()
        try:
            result = self._camera.apply_roi(request)
            if was_streaming:
                self._camera.start_stream()
        except Exception:
            if was_streaming:
                self._snapshot = replace(self._snapshot, state=CameraState.CONNECTED)
            raise
        self._snapshot = replace(
            self._snapshot,
            roi_capabilities=result.capabilities,
            roi_result=result,
            applied_configuration=None,
            last_error=None,
        )
        return (RoiApplied(result),)

    def _apply_controls(self, request: object) -> tuple[ApplicationEvent, ...]:
        from lucid_camera_control.camera.controls import CameraControlRequest

        if not isinstance(request, CameraControlRequest):
            raise TypeError("ApplyCameraControls requires CameraControlRequest")
        if self._snapshot.state not in (CameraState.CONNECTED, CameraState.STREAMING):
            raise InvalidTransitionError(
                "ApplyCameraControls requires Connected or Streaming; "
                f"current state is {self._snapshot.state.value}"
            )
        if (
            request.binning is not None
            and request.binning > 1
            and self._snapshot.roi_result is not None
            and self._snapshot.roi_result.applied.enabled
        ):
            raise InvalidTransitionError("2x2 binning requires hardware ROI to be off")
        was_streaming = self._snapshot.state is CameraState.STREAMING
        if was_streaming:
            self._camera.stop_stream()
        try:
            result = self._camera.apply_controls(request)
            roi_capabilities = self._camera.roi_capabilities()
            if was_streaming:
                self._camera.start_stream()
        except Exception:
            if was_streaming:
                self._snapshot = replace(self._snapshot, state=CameraState.CONNECTED)
            raise
        self._snapshot = replace(
            self._snapshot,
            control_capabilities=result.capabilities,
            control_result=result,
            applied_configuration=None,
            roi_capabilities=roi_capabilities,
            last_error=None,
        )
        return (CameraControlsApplied(result),)

    def _capture_screenshot(self) -> tuple[ApplicationEvent, ...]:
        if self._snapshot.state not in (CameraState.STREAMING, CameraState.RECORDING):
            raise InvalidTransitionError(
                "CaptureScreenshot requires Streaming or Recording; "
                f"current state is {self._snapshot.state.value}"
            )
        active = self._snapshot.active_camera
        if active is None:
            raise RuntimeError("No active camera")
        path = self._screenshot.capture(active.serial_number)
        self._snapshot = replace(
            self._snapshot,
            last_screenshot_path=path,
            last_error=None,
        )
        return (ScreenshotSaved(path),)

    def _apply_configuration(self, config: object) -> tuple[ApplicationEvent, ...]:
        from lucid_camera_control.config.models import AppConfigV1

        if not isinstance(config, AppConfigV1):
            raise TypeError("ApplyConfiguration requires validated AppConfigV1")
        if self._snapshot.state not in (CameraState.CONNECTED, CameraState.STREAMING):
            raise InvalidTransitionError(
                "ApplyConfiguration requires Connected or Streaming; "
                f"current state is {self._snapshot.state.value}"
            )
        controls_request = self._supported_control_request(config.controls.request())
        was_streaming = self._snapshot.state is CameraState.STREAMING
        if was_streaming:
            self._camera.stop_stream()
        try:
            roi_result = self._camera.apply_roi(config.roi.request())
            controls_result = self._camera.apply_controls(controls_request)
            if was_streaming:
                self._camera.start_stream()
        except Exception:
            if was_streaming:
                self._snapshot = replace(self._snapshot, state=CameraState.CONNECTED)
            raise
        self._snapshot = replace(
            self._snapshot,
            roi_capabilities=roi_result.capabilities,
            roi_result=roi_result,
            control_capabilities=controls_result.capabilities,
            control_result=controls_result,
            applied_configuration=config,
            last_error=None,
        )
        return (ConfigurationApplied(config, roi_result, controls_result),)

    def _supported_control_request(self, request: object) -> object:
        from lucid_camera_control.camera.controls import CameraControlRequest

        if not isinstance(request, CameraControlRequest):
            raise TypeError("CameraControlRequest required")
        caps = self._snapshot.control_capabilities
        if caps is None:
            raise RuntimeError("Camera control capabilities are unavailable")
        return replace(
            request,
            gamma_enabled=request.gamma_enabled if caps.gamma_enable.available else None,
            gamma=request.gamma if caps.gamma.available else None,
            black_level=request.black_level if caps.black_level.available else None,
            white_balance_auto=request.white_balance_auto
            if caps.white_balance_auto.available
            else None,
            binning=request.binning
            if caps.binning_horizontal.available and caps.binning_vertical.available
            else None,
        )

    def _factory_reset(self) -> tuple[ApplicationEvent, ...]:
        previous = self._snapshot.state
        if previous is CameraState.DISCONNECTED:
            raise InvalidTransitionError("Factory reset requires a connected camera")
        cleanup_errors: list[str] = []
        if previous is CameraState.RECORDING:
            self._attempt_cleanup(self._recorder.stop, cleanup_errors)
        if previous in (CameraState.STREAMING, CameraState.RECORDING):
            self._attempt_cleanup(self._camera.stop_stream, cleanup_errors)
        if previous is not CameraState.CONNECTED:
            self._snapshot = replace(self._snapshot, state=CameraState.CONNECTED)
        if cleanup_errors:
            raise RuntimeError("; ".join(cleanup_errors))
        result = self._camera.factory_reset()
        self._snapshot = replace(
            self._snapshot,
            state=CameraState.CONNECTED,
            roi_capabilities=result.roi_capabilities,
            roi_result=None,
            control_capabilities=result.control_capabilities,
            control_result=None,
            applied_configuration=None,
            last_error=None,
        )
        events: list[ApplicationEvent] = []
        if previous is not CameraState.CONNECTED:
            events.append(StateChanged(previous, CameraState.CONNECTED))
        events.append(FactoryDefaultsLoaded(result))
        return tuple(events)

    def _handle_device_loss(self, message: str) -> tuple[ApplicationEvent, ...]:
        previous = self._snapshot.state
        if previous is CameraState.DISCONNECTED:
            return ()
        cleanup_errors: list[str] = []
        if previous is CameraState.RECORDING:
            self._attempt_cleanup(self._recorder.stop, cleanup_errors)
        if previous in (CameraState.STREAMING, CameraState.RECORDING):
            self._attempt_cleanup(self._camera.stop_stream, cleanup_errors)
        self._attempt_cleanup(self._camera.close, cleanup_errors)
        details = message
        if cleanup_errors:
            details += "; cleanup: " + "; ".join(cleanup_errors)
        error = ErrorInfo("DeviceLost", details, recoverable=True)
        self._snapshot = replace(
            self._snapshot,
            state=CameraState.DISCONNECTED,
            active_camera=None,
            roi_capabilities=None,
            roi_result=None,
            control_capabilities=None,
            control_result=None,
            applied_configuration=None,
            last_error=error,
        )
        return (
            StateChanged(previous, CameraState.DISCONNECTED),
            OperationFailed(error),
        )

    def _transition(
        self,
        target: CameraState,
        *,
        active_camera: object = ...,
    ) -> tuple[ApplicationEvent, ...]:
        previous = self._snapshot.state
        changes: dict[str, object] = {"state": target, "last_error": None}
        if active_camera is not ...:
            changes["active_camera"] = active_camera
        self._snapshot = replace(self._snapshot, **changes)
        return (StateChanged(previous, target),)

    def _require(self, expected: CameraState, operation: str) -> None:
        if self._snapshot.state is not expected:
            raise InvalidTransitionError(
                f"{operation} requires {expected.value}; "
                f"current state is {self._snapshot.state.value}"
            )

    @staticmethod
    def _attempt_cleanup(action: Callable[[], None], errors: list[str]) -> None:
        try:
            action()
        except Exception as exc:
            errors.append(str(exc) or type(exc).__name__)

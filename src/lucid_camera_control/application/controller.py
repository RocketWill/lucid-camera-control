"""Hardware-independent application controller."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from lucid_camera_control.application.commands import (
    ApplicationCommand,
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
    CamerasDiscovered,
    OperationFailed,
    StateChanged,
)
from lucid_camera_control.application.state import (
    ApplicationSnapshot,
    CameraState,
    ErrorInfo,
)
from lucid_camera_control.camera.interface import CameraPort, NullRecorder, RecorderPort

EventListener = Callable[[ApplicationEvent, ApplicationSnapshot], None]


class InvalidTransitionError(RuntimeError):
    """Raised when a command is invalid for the current state."""


class ApplicationController:
    """Own camera lifecycle state without depending on Qt or Arena."""

    def __init__(
        self,
        camera: CameraPort,
        recorder: RecorderPort | None = None,
    ) -> None:
        self._camera = camera
        self._recorder = recorder or NullRecorder()
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
            error = ErrorInfo(type(command).__name__, str(exc) or type(exc).__name__)
            self._snapshot = replace(self._snapshot, last_error=error)
            events = (OperationFailed(error),)

        for event in events:
            for listener in tuple(self._listeners):
                listener(event, self._snapshot)
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
        return self._transition(CameraState.CONNECTED, active_camera=descriptor)

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
        self._recorder.start()
        return self._transition(CameraState.RECORDING)

    def _stop_recording(self) -> tuple[ApplicationEvent, ...]:
        if self._snapshot.state is CameraState.STREAMING:
            return ()
        self._require(CameraState.RECORDING, "StopRecording")
        self._recorder.stop()
        return self._transition(CameraState.STREAMING)

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


from __future__ import annotations

import unittest

from lucid_camera_control.application.commands import (
    CloseCamera,
    ConnectCamera,
    ApplyRoi,
    ExploreCameras,
    StartRecording,
    StartStream,
    StopRecording,
    StopStream,
)
from lucid_camera_control.application.controller import (
    ApplicationController,
    InvalidTransitionError,
)
from lucid_camera_control.application.events import CamerasDiscovered, OperationFailed
from lucid_camera_control.application.state import CameraState
from lucid_camera_control.camera.models import CameraDescriptor
from lucid_camera_control.camera.nodes import NodeCapability, NodeKind
from lucid_camera_control.camera.roi import (
    AppliedRoi,
    RoiCapabilities,
    RoiRequest,
    RoiResult,
)


def fake_roi_capabilities() -> RoiCapabilities:
    def capability(name: str, value: object) -> NodeCapability:
        return NodeCapability(name, NodeKind.INTEGER, True, True, True, value=value)

    return RoiCapabilities(
        capability("Width", 2048),
        capability("Height", 1536),
        capability("OffsetX", 0),
        capability("OffsetY", 0),
        NodeCapability(
            "PixelFormat",
            NodeKind.ENUMERATION,
            True,
            True,
            True,
            value="Mono8",
            choices=("Mono8",),
        ),
    )


class FakeCamera:
    def __init__(self) -> None:
        self.devices = (CameraDescriptor("ABC123", "TRI0325-CC"),)
        self.calls: list[str] = []
        self.fail_on: set[str] = set()

    def _call(self, name: str) -> None:
        self.calls.append(name)
        if name in self.fail_on:
            raise RuntimeError(f"{name} failed")

    def discover(self) -> tuple[CameraDescriptor, ...]:
        self._call("discover")
        return self.devices

    def connect(self, serial_number: str) -> CameraDescriptor:
        self._call(f"connect:{serial_number}")
        return next(device for device in self.devices if device.serial_number == serial_number)

    def close(self) -> None:
        self._call("close")

    def start_stream(self) -> None:
        self._call("start_stream")

    def stop_stream(self) -> None:
        self._call("stop_stream")

    def roi_capabilities(self) -> RoiCapabilities:
        return fake_roi_capabilities()

    def apply_roi(self, request: RoiRequest) -> RoiResult:
        self._call("apply_roi")
        applied = AppliedRoi(
            request.enabled,
            request.width,
            request.height,
            request.offset_x,
            request.offset_y,
            request.centered,
        )
        return RoiResult(request, applied, (), fake_roi_capabilities(), 0, 60.0)


class FakeRecorder:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail_on: set[str] = set()

    def start(self) -> None:
        self.calls.append("start")
        if "start" in self.fail_on:
            raise RuntimeError("recorder start failed")

    def stop(self) -> None:
        self.calls.append("stop")
        if "stop" in self.fail_on:
            raise RuntimeError("recorder stop failed")


class ApplicationControllerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.camera = FakeCamera()
        self.recorder = FakeRecorder()
        self.controller = ApplicationController(self.camera, self.recorder)

    def connect_and_stream(self) -> None:
        self.controller.execute(ConnectCamera("ABC123"))
        self.controller.execute(StartStream())

    def test_discovery_publishes_immutable_descriptors(self) -> None:
        events = self.controller.execute(ExploreCameras())
        self.assertIsInstance(events[0], CamerasDiscovered)
        self.assertEqual(self.controller.snapshot.discovered_cameras, self.camera.devices)
        self.assertEqual(self.controller.snapshot.state, CameraState.DISCONNECTED)

    def test_happy_path_transitions(self) -> None:
        self.controller.execute(ConnectCamera("ABC123"))
        self.assertEqual(self.controller.snapshot.state, CameraState.CONNECTED)
        self.controller.execute(StartStream())
        self.assertEqual(self.controller.snapshot.state, CameraState.STREAMING)
        self.controller.execute(StartRecording())
        self.assertEqual(self.controller.snapshot.state, CameraState.RECORDING)
        self.controller.execute(StopRecording())
        self.controller.execute(StopStream())
        self.controller.execute(CloseCamera())
        self.assertEqual(self.controller.snapshot.state, CameraState.DISCONNECTED)

    def test_invalid_transition_has_no_side_effect(self) -> None:
        before = self.controller.snapshot
        with self.assertRaises(InvalidTransitionError):
            self.controller.execute(StartStream())
        self.assertIs(self.controller.snapshot, before)
        self.assertEqual(self.camera.calls, [])

    def test_stop_operations_are_idempotent_at_safe_state(self) -> None:
        self.controller.execute(ConnectCamera("ABC123"))
        self.assertEqual(self.controller.execute(StopStream()), ())
        self.connect_and_stream_after_existing_connection()
        self.assertEqual(self.controller.execute(StopRecording()), ())

    def connect_and_stream_after_existing_connection(self) -> None:
        self.controller.execute(StartStream())

    def test_close_recording_cleans_every_resource_in_order(self) -> None:
        self.connect_and_stream()
        self.controller.execute(StartRecording())
        self.controller.execute(CloseCamera())
        self.assertEqual(self.recorder.calls, ["start", "stop"])
        self.assertEqual(
            self.camera.calls,
            ["connect:ABC123", "start_stream", "stop_stream", "close"],
        )
        self.assertEqual(self.controller.execute(CloseCamera()), ())

    def test_close_continues_cleanup_after_failure(self) -> None:
        self.connect_and_stream()
        self.controller.execute(StartRecording())
        self.recorder.fail_on.add("stop")
        self.camera.fail_on.add("stop_stream")
        events = self.controller.execute(CloseCamera())
        self.assertTrue(any(isinstance(event, OperationFailed) for event in events))
        self.assertIn("close", self.camera.calls)
        self.assertEqual(self.controller.snapshot.state, CameraState.DISCONNECTED)
        self.assertIsNotNone(self.controller.snapshot.last_error)

    def test_adapter_failure_is_reported_without_transition(self) -> None:
        self.controller.execute(ConnectCamera("ABC123"))
        self.camera.fail_on.add("start_stream")
        events = self.controller.execute(StartStream())
        self.assertIsInstance(events[0], OperationFailed)
        self.assertEqual(self.controller.snapshot.state, CameraState.CONNECTED)
        self.assertEqual(self.controller.snapshot.last_error.operation, "StartStream")

    def test_listener_can_unsubscribe(self) -> None:
        received: list[object] = []
        unsubscribe = self.controller.subscribe(
            lambda event, snapshot: received.append((event, snapshot.state))
        )
        self.controller.execute(ExploreCameras())
        unsubscribe()
        self.controller.execute(ExploreCameras())
        self.assertEqual(len(received), 1)

    def test_apply_roi_stops_and_restarts_an_active_stream(self) -> None:
        self.connect_and_stream()
        request = RoiRequest(True, 1024, 768, True)
        self.controller.execute(ApplyRoi(request))
        self.assertEqual(
            self.camera.calls,
            [
                "connect:ABC123",
                "start_stream",
                "stop_stream",
                "apply_roi",
                "start_stream",
            ],
        )
        self.assertEqual(self.controller.snapshot.state, CameraState.STREAMING)
        self.assertEqual(self.controller.snapshot.roi_result.requested, request)

    def test_failed_streaming_roi_stays_connected_and_does_not_restart(self) -> None:
        self.connect_and_stream()
        self.camera.fail_on.add("apply_roi")
        events = self.controller.execute(ApplyRoi(RoiRequest(True, 1024, 768)))
        self.assertIsInstance(events[0], OperationFailed)
        self.assertEqual(self.controller.snapshot.state, CameraState.CONNECTED)
        self.assertEqual(self.camera.calls[-2:], ["stop_stream", "apply_roi"])


if __name__ == "__main__":
    unittest.main()

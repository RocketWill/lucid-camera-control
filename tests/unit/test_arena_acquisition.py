from __future__ import annotations

import ctypes
import threading
import unittest
from enum import Enum
from typing import Any

from lucid_camera_control.camera.acquisition import RecoverableFrameError
from lucid_camera_control.camera.arena_system import ArenaCameraSystem
from tests.unit.test_arena_system import FakeArenaSystem, lucid_info
from tests.unit.test_nodes import FakeNode, FakeNodeMap, InterfaceType


class PixelFormat(Enum):
    Mono8 = 1


class FakeBuffer:
    def __init__(self, *, incomplete: bool = False) -> None:
        self.width = 2
        self.height = 2
        self.padding_x = 1
        self.frame_id = 7
        self.timestamp_ns = 1234
        self.pixel_format = PixelFormat.Mono8
        self.is_incomplete = incomplete
        self._array = (ctypes.c_uint8 * 6)(1, 2, 99, 3, 4, 99)
        self.pdata = ctypes.cast(self._array, ctypes.POINTER(ctypes.c_uint8))


class AcquisitionDevice:
    def __init__(self, buffers: list[FakeBuffer]) -> None:
        self.nodemap = FakeNodeMap(
            {
                "PixelFormat": FakeNode(
                    InterfaceType.ENUMERATION,
                    "Mono8",
                    choices=("Mono8",),
                ),
                "AcquisitionMode": FakeNode(
                    InterfaceType.ENUMERATION,
                    "Continuous",
                    choices=("Continuous",),
                ),
            }
        )
        self.tl_stream_nodemap = FakeNodeMap(
            {
                "StreamAutoNegotiatePacketSize": FakeNode(
                    InterfaceType.BOOLEAN, False
                ),
                "StreamPacketResendEnable": FakeNode(InterfaceType.BOOLEAN, False),
                "StreamBufferHandlingMode": FakeNode(
                    InterfaceType.ENUMERATION,
                    "OldestFirst",
                    choices=("OldestFirst", "NewestOnly"),
                ),
            }
        )
        self.buffers = list(buffers)
        self.requeued: list[FakeBuffer] = []
        self.started_with: int | None = None
        self.stopped = False

    def start_stream(self, count: int) -> None:
        self.started_with = count

    def stop_stream(self) -> None:
        self.stopped = True

    def get_buffer(self, *, timeout: int) -> FakeBuffer:
        if not self.buffers:
            raise TimeoutError
        return self.buffers.pop(0)

    def requeue_buffer(self, buffer: FakeBuffer) -> None:
        self.requeued.append(buffer)


class AcquisitionSystem(FakeArenaSystem):
    def __init__(self, device: AcquisitionDevice) -> None:
        super().__init__([lucid_info("100")])
        self.device = device


class ArenaAcquisitionTests(unittest.TestCase):
    def test_owned_frame_copies_padding_and_requeues_before_return(self) -> None:
        buffer = FakeBuffer()
        device = AcquisitionDevice([buffer])
        adapter = ArenaCameraSystem(AcquisitionSystem(device))
        adapter.connect("100")
        adapter.start_stream()
        owned = adapter.acquire_frame(10)
        self.assertEqual(owned.data, bytes((1, 2, 99, 3, 4, 99)))
        self.assertEqual(owned.mono8_view().tolist(), [[1, 2], [3, 4]])
        self.assertEqual(device.requeued, [buffer])
        adapter.stop_stream()
        adapter.close()

    def test_incomplete_buffer_is_always_requeued(self) -> None:
        buffer = FakeBuffer(incomplete=True)
        device = AcquisitionDevice([buffer])
        adapter = ArenaCameraSystem(AcquisitionSystem(device))
        adapter.connect("100")
        adapter.start_stream()
        with self.assertRaises(RecoverableFrameError):
            adapter.acquire_frame(10)
        self.assertEqual(device.requeued, [buffer])
        adapter.stop_stream()
        adapter.close()

    def test_subscribed_worker_publishes_owned_frame_and_stops(self) -> None:
        device = AcquisitionDevice([FakeBuffer()])
        adapter = ArenaCameraSystem(AcquisitionSystem(device))
        adapter.connect("100")
        received = []
        done = threading.Event()
        adapter.subscribe_frames(lambda value: (received.append(value), done.set()))
        adapter.start_stream()
        self.assertTrue(done.wait(1.0))
        adapter.stop_stream()
        adapter.close()
        self.assertEqual(received[0].sequence, 7)
        self.assertTrue(device.stopped)
        self.assertEqual(
            device.tl_stream_nodemap.nodes["StreamBufferHandlingMode"].value,
            "NewestOnly",
        )


if __name__ == "__main__":
    unittest.main()

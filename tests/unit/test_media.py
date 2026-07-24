from __future__ import annotations

import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from lucid_camera_control.media.frame import Frame
from lucid_camera_control.media.recorder import RecorderService
from lucid_camera_control.media.screenshot import ScreenshotService


def frame(sequence: int, values: bytes = bytes((1, 2, 3, 4))) -> Frame:
    return Frame(sequence, sequence, None, 2, 2, 2, "Mono8", values)


class FakeBackend:
    def __init__(self, block_first: bool = False) -> None:
        self.output_path: Path | None = None
        self.opened: tuple[int, int, float, Path] | None = None
        self.images: list[np.ndarray] = []
        self.closed = 0
        self.entered = threading.Event()
        self.release = threading.Event()
        if not block_first:
            self.release.set()

    def open(self, width: int, height: int, fps: float, path: Path) -> None:
        self.opened = (width, height, fps, path)
        self.output_path = path

    def append_bgr8(self, image: np.ndarray) -> None:
        self.entered.set()
        self.release.wait(2)
        self.images.append(image.copy())

    def close(self) -> None:
        self.closed += 1


class MediaTests(unittest.TestCase):
    def test_screenshot_uses_original_owned_mono8_and_collision_safe_name(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = ScreenshotService(Path(directory))
            service.receive(frame(1, bytes((10, 20, 30, 40))))
            now = datetime(2026, 8, 11, 12, 34, 56, 789000)
            first = service.capture("ABC/123", now)
            second = service.capture("ABC/123", now)
            self.assertNotEqual(first, second)
            self.assertEqual(first.suffix, ".png")
            saved = cv2.imread(str(first), cv2.IMREAD_GRAYSCALE)
            self.assertEqual(saved.tolist(), [[10, 20], [30, 40]])

    def test_recorder_converts_mono8_to_bgr_and_finalizes_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            backend = FakeBackend()
            service = RecorderService(
                Path(directory), backend=backend, minimum_start_bytes=0
            )
            service.receive(frame(1))
            service.start(fps=25.0, serial_number="ABC")
            service.receive(frame(2))
            service.stop()
            service.stop()
            self.assertEqual(backend.opened[:3], (2, 2, 25.0))
            self.assertEqual(backend.images[0].shape, (2, 2, 3))
            self.assertEqual(backend.images[0][:, :, 0].tolist(), [[1, 2], [3, 4]])
            self.assertEqual(service.status.frames_written, 1)
            self.assertFalse(service.status.active)

    def test_full_queue_drops_oldest_without_blocking_acquisition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            backend = FakeBackend(block_first=True)
            service = RecorderService(
                Path(directory),
                backend=backend,
                queue_capacity=2,
                minimum_start_bytes=0,
            )
            service.receive(frame(0))
            service.start()
            service.receive(frame(1))
            self.assertTrue(backend.entered.wait(1))
            service.receive(frame(2))
            service.receive(frame(3))
            service.receive(frame(4))
            self.assertEqual(service.status.dropped_frames, 1)
            backend.release.set()
            service.stop()
            written = [int(image[0, 0, 0]) for image in backend.images]
            self.assertEqual(len(written), 3)

    def test_recording_refuses_to_start_below_disk_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            backend = FakeBackend()
            service = RecorderService(Path(directory), backend=backend)
            service.receive(frame(1))
            with patch(
                "lucid_camera_control.media.recorder.shutil.disk_usage",
                return_value=SimpleNamespace(free=100),
            ):
                with self.assertRaises(OSError):
                    service.start()
            self.assertIsNone(backend.opened)
            self.assertFalse(service.status.active)

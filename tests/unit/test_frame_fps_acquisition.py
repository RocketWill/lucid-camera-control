from __future__ import annotations

import threading
import unittest

from lucid_camera_control.camera.acquisition import AcquisitionWorker, RecoverableFrameError
from lucid_camera_control.diagnostics.fps import RollingFps
from lucid_camera_control.media.frame import Frame


def frame(sequence: int = 1) -> Frame:
    return Frame(sequence, sequence, None, 2, 2, 2, "Mono8", bytes((1, 2, 3, 4)))


class ScriptedSource:
    def __init__(self, script: list[object]) -> None:
        self.script = list(script)
        self.calls = 0

    def acquire_frame(self, timeout_ms: int) -> Frame:
        self.calls += 1
        if not self.script:
            raise TimeoutError
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FrameFpsAcquisitionTests(unittest.TestCase):
    def test_mono8_view_honors_row_stride_without_copying(self) -> None:
        owned = Frame(1, 1, None, 2, 2, 3, "Mono8", bytes((1, 2, 99, 3, 4, 99)))
        view = owned.mono8_view()
        self.assertEqual(view.tolist(), [[1, 2], [3, 4]])
        self.assertFalse(view.flags.writeable)

    def test_rolling_fps_uses_intervals_in_window(self) -> None:
        meter = RollingFps(window_seconds=1.0)
        self.assertEqual(meter.add(0), 0.0)
        self.assertAlmostEqual(meter.add(100_000_000), 10.0)
        self.assertAlmostEqual(meter.add(200_000_000), 10.0)
        self.assertAlmostEqual(meter.add(1_300_000_000), 0.0)

    def test_worker_continues_after_timeout_and_recoverable_error(self) -> None:
        received: list[Frame] = []
        errors: list[Exception] = []
        done = threading.Event()

        def on_frame(value: Frame) -> None:
            received.append(value)
            done.set()

        source = ScriptedSource([TimeoutError(), RecoverableFrameError("bad"), frame()])
        worker = AcquisitionWorker(source, on_frame, errors.append, timeout_ms=1)
        worker.start()
        self.assertTrue(done.wait(1.0))
        worker.stop()
        self.assertEqual(received, [frame()])
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], RecoverableFrameError)

    def test_worker_reports_fatal_error_and_exits(self) -> None:
        errors: list[Exception] = []
        reported = threading.Event()

        def on_error(error: Exception) -> None:
            errors.append(error)
            reported.set()

        worker = AcquisitionWorker(
            ScriptedSource([RuntimeError("device lost")]),
            lambda value: None,
            on_error,
            timeout_ms=1,
        )
        worker.start()
        self.assertTrue(reported.wait(1.0))
        worker.stop()
        self.assertEqual(str(errors[0]), "device lost")

    def test_frame_listener_failure_is_recoverable(self) -> None:
        errors: list[Exception] = []
        delivered: list[int] = []
        done = threading.Event()

        def on_frame(value: Frame) -> None:
            delivered.append(value.sequence)
            if value.sequence == 1:
                raise RuntimeError("display failed")
            done.set()

        worker = AcquisitionWorker(
            ScriptedSource([frame(1), frame(2)]),
            on_frame,
            errors.append,
            timeout_ms=1,
        )
        worker.start()
        self.assertTrue(done.wait(1.0))
        worker.stop()
        self.assertEqual(delivered, [1, 2])
        self.assertIsInstance(errors[0], RecoverableFrameError)


if __name__ == "__main__":
    unittest.main()

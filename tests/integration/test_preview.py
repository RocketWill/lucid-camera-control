from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from lucid_camera_control.media.frame import Frame
from lucid_camera_control.ui.preview_bridge import PreviewBridge
from lucid_camera_control.ui.preview_widget import PreviewWidget


class FakePublisher:
    def __init__(self) -> None:
        self.frame_listener = None
        self.error_listener = None

    def subscribe_frames(self, listener):
        self.frame_listener = listener
        return lambda: None

    def subscribe_acquisition_errors(self, listener):
        self.error_listener = listener
        return lambda: None


def frame(sequence: int, timestamp_ns: int, value: int) -> Frame:
    return Frame(
        sequence,
        timestamp_ns,
        None,
        2,
        2,
        2,
        "Mono8",
        bytes((value, value, value, value)),
    )


def sized_frame(width: int, height: int) -> Frame:
    return Frame(
        1,
        300_000_000,
        None,
        width,
        height,
        width,
        "Mono8",
        bytes(width * height),
    )


class PreviewIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = QApplication.instance() or QApplication([])

    def test_bridge_coalesces_to_latest_frame(self) -> None:
        publisher = FakePublisher()
        bridge = PreviewBridge(publisher)
        spy = QSignalSpy(bridge.frame_arrived)
        publisher.frame_listener(frame(1, 0, 1))
        publisher.frame_listener(frame(2, 10_000_000, 2))
        publisher.frame_listener(frame(3, 20_000_000, 3))
        QCoreApplication.processEvents()
        self.assertEqual(spy.count(), 1)
        delivered = spy.at(0)[0]
        self.assertEqual(delivered.sequence, 3)
        bridge.close()

    def test_contrast_changes_preview_copy_not_owned_frame(self) -> None:
        widget = PreviewWidget()
        owned = frame(1, 300_000_000, 80)
        original = owned.data
        widget.contrast.setValue(2.0)
        widget.show_frame(owned, 25.0)
        self.assertEqual(owned.data, original)
        self.assertIsNotNone(widget.image_label.pixmap())
        self.assertEqual(widget.fps_label.text(), "Receive FPS: 25.00")
        widget.close()

    def test_preview_fits_common_frame_ratios_without_cropping(self) -> None:
        widget = PreviewWidget()
        widget.resize(700, 500)
        widget.show()
        self.app.processEvents()

        for source_width, source_height in ((640, 480), (160, 90)):
            widget.show_frame(sized_frame(source_width, source_height), 30.0)
            pixmap = widget.image_label.pixmap()
            self.assertLessEqual(pixmap.width(), widget.image_label.width())
            self.assertLessEqual(pixmap.height(), widget.image_label.height())
            self.assertAlmostEqual(
                pixmap.width() / pixmap.height(),
                source_width / source_height,
                delta=0.02,
            )

        widget.close()


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import arena_api  # noqa: E402
import cv2  # noqa: E402
import numpy  # noqa: E402
import pydantic  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lucid_camera_control.__main__ import main  # noqa: E402
from lucid_camera_control.ui.main_window import MainWindow  # noqa: E402


class RuntimeSmokeTests(unittest.TestCase):
    def test_runtime_dependencies_import(self) -> None:
        for dependency in (arena_api, cv2, numpy, pydantic):
            self.assertIsNotNone(dependency)

    def test_main_window_starts_disconnected(self) -> None:
        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        self.assertEqual(window.status_label.text(), "Disconnected")
        window.close()
        app.processEvents()

    def test_smoke_entry_point(self) -> None:
        self.assertEqual(main(["--smoke-test"]), 0)


if __name__ == "__main__":
    unittest.main()


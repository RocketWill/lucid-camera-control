from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path

from lucid_camera_control.diagnostics.logging import configure_logging


class LoggingTests(unittest.TestCase):
    def test_rotating_log_is_created_in_requested_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = configure_logging(Path(directory))
            logger = logging.getLogger("lucid_camera_control")
            logging.getLogger("lucid_camera_control.test").info("acceptance marker")
            matching = [
                handler
                for handler in logger.handlers
                if getattr(handler, "baseFilename", None) == str(path.resolve())
            ]
            for handler in matching:
                handler.flush()
            self.assertTrue(path.exists())
            self.assertIn("acceptance marker", path.read_text(encoding="utf-8"))
            for handler in matching:
                logger.removeHandler(handler)
                handler.close()

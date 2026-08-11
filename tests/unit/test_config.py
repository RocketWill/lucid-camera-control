from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from lucid_camera_control.config.models import AppConfigV1, CameraControlsConfig, RoiConfig
from lucid_camera_control.config.store import ConfigStore


class ConfigTests(unittest.TestCase):
    def test_schema_v1_round_trip_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "camera.json"
            store = ConfigStore(Path(directory) / "last.json")
            expected = AppConfigV1(
                preferred_camera_serial="ABC123",
                roi=RoiConfig(enabled=True, width=1024, height=768),
                controls=CameraControlsConfig(binning=1, gain=3.5),
                preview_contrast=1.4,
            )
            store.export(expected, path)
            self.assertEqual(store.parse(path), expected)

    def test_unknown_schema_and_extra_keys_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            AppConfigV1.model_validate({"schema_version": 2})
        with self.assertRaises(ValidationError):
            AppConfigV1.model_validate({"schema_version": 1, "surprise": True})

    def test_invalid_roi_binning_combination_is_rejected_before_apply(self) -> None:
        with self.assertRaises(ValidationError):
            AppConfigV1(
                roi=RoiConfig(enabled=True, width=100, height=100),
                controls=CameraControlsConfig(binning=2),
            )

    def test_atomic_save_replaces_last_known_good_and_leaves_no_temp(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "last.json"
            store = ConfigStore(path)
            store.save_last_known_good(AppConfigV1(preview_contrast=1.1))
            store.save_last_known_good(AppConfigV1(preview_contrast=1.7))
            self.assertEqual(store.load_last_known_good().preview_contrast, 1.7)
            self.assertFalse(path.with_name(".last.json.tmp").exists())

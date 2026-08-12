from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

import cv2
import numpy as np

from lucid_camera_control.media.frame_exporter import (
    CollisionPolicy,
    FrameExportRequest,
    FrameExporterService,
)


def create_avi(path: Path, frame_count: int = 7) -> None:
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (8, 6)
    )
    if not writer.isOpened():
        raise RuntimeError("Test AVI writer could not open")
    try:
        for index in range(frame_count):
            writer.write(np.full((6, 8, 3), index * 20, dtype=np.uint8))
    finally:
        writer.release()


class FrameExporterTests(unittest.TestCase):
    def test_inspect_and_export_every_n_preserves_source_indexes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sample.avi"
            create_avi(source)
            service = FrameExporterService()

            metadata = service.inspect(source)
            self.assertEqual((metadata.width, metadata.height), (8, 6))
            self.assertAlmostEqual(metadata.fps, 10.0)
            self.assertEqual(metadata.estimated_frame_count, 7)

            result = service.export(
                FrameExportRequest(
                    source,
                    root / "output",
                    start_frame=1,
                    end_frame=6,
                    every_n=2,
                )
            )
            self.assertEqual(result.exported, 3)
            self.assertEqual(result.decoded, 7)
            self.assertEqual(result.failed, 0)
            self.assertFalse(result.cancelled)
            self.assertEqual(
                [path.name for path in result.files],
                [
                    "sample_frame_000001.bmp",
                    "sample_frame_000003.bmp",
                    "sample_frame_000005.bmp",
                ],
            )
            image = cv2.imread(str(result.files[0]))
            self.assertEqual(image.shape, (6, 8, 3))

    def test_new_directory_is_collision_safe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sample.avi"
            create_avi(source, 1)
            destination = root / "output"
            destination.mkdir()
            (destination / "existing.txt").write_text("keep", encoding="ascii")

            result = FrameExporterService().export(
                FrameExportRequest(source, destination)
            )
            self.assertNotEqual(result.output_directory, destination)
            self.assertEqual(result.output_directory.name, "output_001")
            self.assertTrue((destination / "existing.txt").exists())

    def test_skip_policy_does_not_overwrite_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sample.avi"
            create_avi(source, 1)
            destination = root / "output"
            destination.mkdir()
            existing = destination / "sample_frame_000000.bmp"
            existing.write_bytes(b"existing")

            result = FrameExporterService().export(
                FrameExportRequest(
                    source,
                    destination,
                    collision_policy=CollisionPolicy.SKIP,
                )
            )
            self.assertEqual(result.exported, 0)
            self.assertEqual(result.skipped, 1)
            self.assertEqual(existing.read_bytes(), b"existing")

    def test_overwrite_policy_replaces_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sample.avi"
            create_avi(source, 1)
            destination = root / "output"
            destination.mkdir()
            existing = destination / "sample_frame_000000.bmp"
            existing.write_bytes(b"existing")

            result = FrameExporterService().export(
                FrameExportRequest(
                    source,
                    destination,
                    collision_policy=CollisionPolicy.OVERWRITE,
                )
            )
            self.assertEqual(result.exported, 1)
            self.assertEqual(result.skipped, 0)
            self.assertGreater(existing.stat().st_size, len(b"existing"))

    def test_cooperative_cancel_keeps_completed_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sample.avi"
            create_avi(source, 5)
            cancel = threading.Event()

            def progress(update: object) -> None:
                if getattr(update, "exported") == 2:
                    cancel.set()

            result = FrameExporterService().export(
                FrameExportRequest(source, root / "output"),
                progress=progress,
                cancelled=cancel.is_set,
            )
            self.assertTrue(result.cancelled)
            self.assertEqual(result.exported, 2)
            self.assertEqual(len(tuple(result.output_directory.glob("*.bmp"))), 2)

    def test_request_rejects_invalid_range_and_sampling(self) -> None:
        source = Path("sample.avi")
        destination = Path("output")
        with self.assertRaises(ValueError):
            FrameExportRequest(source, destination, start_frame=2, end_frame=1)
        with self.assertRaises(ValueError):
            FrameExportRequest(source, destination, every_n=0)


if __name__ == "__main__":
    unittest.main()

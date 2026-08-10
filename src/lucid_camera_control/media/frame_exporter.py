"""Offline AVI inspection and frame export without camera dependencies."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
import math
from pathlib import Path
import time

import cv2


class CollisionPolicy(StrEnum):
    NEW_DIRECTORY = "new_directory"
    SKIP = "skip"
    OVERWRITE = "overwrite"


@dataclass(frozen=True, slots=True)
class VideoMetadata:
    width: int
    height: int
    fps: float | None
    estimated_frame_count: int | None
    estimated_duration_seconds: float | None


@dataclass(frozen=True, slots=True)
class FrameExportRequest:
    source: Path
    destination: Path
    start_frame: int = 0
    end_frame: int | None = None
    every_n: int = 1
    collision_policy: CollisionPolicy = CollisionPolicy.NEW_DIRECTORY

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", Path(self.source))
        object.__setattr__(self, "destination", Path(self.destination))
        if self.start_frame < 0:
            raise ValueError("Start frame must be zero or greater")
        if self.end_frame is not None and self.end_frame < self.start_frame:
            raise ValueError("End frame must be greater than or equal to start frame")
        if self.every_n < 1:
            raise ValueError("Sampling interval must be at least one")


@dataclass(frozen=True, slots=True)
class FrameExportProgress:
    decoded: int
    exported: int
    skipped: int
    failed: int
    estimated_total: int | None
    elapsed_seconds: float
    estimated_remaining_seconds: float | None


@dataclass(frozen=True, slots=True)
class FrameExportResult:
    output_directory: Path
    decoded: int
    exported: int
    skipped: int
    failed: int
    cancelled: bool
    elapsed_seconds: float
    files: tuple[Path, ...]


ProgressCallback = Callable[[FrameExportProgress], None]
CancellationCheck = Callable[[], bool]


class FrameExporterService:
    def inspect(self, source: Path) -> VideoMetadata:
        source = self._validated_source(source)
        capture = cv2.VideoCapture(str(source))
        try:
            if not capture.isOpened():
                raise ValueError(f"AVI could not be opened: {source}")
            width = max(0, int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)))
            height = max(0, int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
            fps_value = float(capture.get(cv2.CAP_PROP_FPS))
            count_value = float(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = fps_value if math.isfinite(fps_value) and fps_value > 0 else None
            frame_count = (
                int(count_value)
                if math.isfinite(count_value) and count_value > 0
                else None
            )
            duration = frame_count / fps if frame_count is not None and fps else None
            if width <= 0 or height <= 0:
                raise ValueError(f"AVI dimensions could not be read: {source}")
            return VideoMetadata(width, height, fps, frame_count, duration)
        finally:
            capture.release()

    def export(
        self,
        request: FrameExportRequest,
        *,
        progress: ProgressCallback | None = None,
        cancelled: CancellationCheck | None = None,
    ) -> FrameExportResult:
        source = self._validated_source(request.source)
        metadata = self.inspect(source)
        output_directory = self._prepare_destination(request)
        capture = cv2.VideoCapture(str(source))
        if not capture.isOpened():
            capture.release()
            raise ValueError(f"AVI could not be opened: {source}")

        started = time.monotonic()
        decoded = exported = skipped = failed = 0
        files: list[Path] = []
        was_cancelled = False
        estimated_total = self.estimated_output_count(metadata, request)
        padding = max(6, len(str(max(0, (metadata.estimated_frame_count or 1) - 1))))
        source_index = 0
        try:
            while True:
                if cancelled is not None and cancelled():
                    was_cancelled = True
                    break
                if request.end_frame is not None and source_index > request.end_frame:
                    break
                ok, image = capture.read()
                if not ok:
                    break
                decoded += 1
                if self._selected(source_index, request):
                    path = output_directory / (
                        f"{source.stem}_frame_{source_index:0{padding}d}.bmp"
                    )
                    if (
                        request.collision_policy is CollisionPolicy.SKIP
                        and path.exists()
                    ):
                        skipped += 1
                    else:
                        try:
                            if not cv2.imwrite(str(path), image):
                                raise OSError(f"BMP writer rejected {path}")
                        except Exception:
                            failed += 1
                        else:
                            exported += 1
                            files.append(path)
                source_index += 1
                if progress is not None:
                    progress(
                        self._progress(
                            decoded,
                            exported,
                            skipped,
                            failed,
                            estimated_total,
                            started,
                        )
                    )
        finally:
            capture.release()

        return FrameExportResult(
            output_directory,
            decoded,
            exported,
            skipped,
            failed,
            was_cancelled,
            time.monotonic() - started,
            tuple(files),
        )

    def estimated_output_count(
        self, metadata: VideoMetadata, request: FrameExportRequest
    ) -> int | None:
        if metadata.estimated_frame_count is None:
            return None
        last = metadata.estimated_frame_count - 1
        if request.end_frame is not None:
            last = min(last, request.end_frame)
        if last < request.start_frame:
            return 0
        return ((last - request.start_frame) // request.every_n) + 1

    @staticmethod
    def _selected(index: int, request: FrameExportRequest) -> bool:
        if index < request.start_frame:
            return False
        if request.end_frame is not None and index > request.end_frame:
            return False
        return (index - request.start_frame) % request.every_n == 0

    @staticmethod
    def _validated_source(source: Path) -> Path:
        source = Path(source)
        if source.suffix.casefold() != ".avi":
            raise ValueError("Source must be an AVI file")
        if not source.is_file():
            raise ValueError(f"AVI does not exist: {source}")
        return source

    @staticmethod
    def _prepare_destination(request: FrameExportRequest) -> Path:
        destination = request.destination
        if destination.exists() and not destination.is_dir():
            raise ValueError(f"Destination is not a directory: {destination}")
        if (
            request.collision_policy is CollisionPolicy.NEW_DIRECTORY
            and destination.exists()
            and any(destination.iterdir())
        ):
            base = destination
            suffix = 1
            while destination.exists():
                destination = base.with_name(f"{base.name}_{suffix:03d}")
                suffix += 1
        destination.mkdir(parents=True, exist_ok=True)
        probe = destination / ".lucid_frame_export_write_test"
        try:
            probe.touch(exist_ok=False)
            probe.unlink()
        except OSError as exc:
            raise ValueError(f"Destination is not writable: {destination}") from exc
        return destination

    @staticmethod
    def _progress(
        decoded: int,
        exported: int,
        skipped: int,
        failed: int,
        estimated_total: int | None,
        started: float,
    ) -> FrameExportProgress:
        elapsed = time.monotonic() - started
        completed = exported + skipped + failed
        remaining = None
        if elapsed >= 10 and estimated_total and completed:
            remaining = max(0.0, elapsed * (estimated_total - completed) / completed)
        return FrameExportProgress(
            decoded,
            exported,
            skipped,
            failed,
            estimated_total,
            elapsed,
            remaining,
        )

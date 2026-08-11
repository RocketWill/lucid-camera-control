"""Immutable image frame owned independently from Arena buffers."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class Frame:
    sequence: int
    received_monotonic_ns: int
    camera_timestamp_ns: int | None
    width: int
    height: int
    row_stride: int
    pixel_format: str
    data: bytes

    def mono8_view(self) -> NDArray[np.uint8]:
        if self.pixel_format != "Mono8":
            raise ValueError(f"Mono8 frame required, got {self.pixel_format}")
        expected = self.row_stride * self.height
        if len(self.data) != expected:
            raise ValueError(f"Expected {expected} bytes, got {len(self.data)}")
        rows = np.frombuffer(self.data, dtype=np.uint8).reshape(
            self.height,
            self.row_stride,
        )
        return rows[:, : self.width]

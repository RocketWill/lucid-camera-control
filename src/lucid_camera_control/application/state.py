"""Application state primitives."""

from __future__ import annotations

from enum import StrEnum


class CameraState(StrEnum):
    """Stable camera lifecycle states shown to the operator."""

    DISCONNECTED = "Disconnected"
    CONNECTED = "Connected"
    STREAMING = "Streaming"
    RECORDING = "Recording"


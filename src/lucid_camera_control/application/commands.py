"""Typed commands accepted by the application controller."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


@dataclass(frozen=True, slots=True)
class ExploreCameras:
    pass


@dataclass(frozen=True, slots=True)
class ConnectCamera:
    serial_number: str


@dataclass(frozen=True, slots=True)
class CloseCamera:
    pass


@dataclass(frozen=True, slots=True)
class StartStream:
    pass


@dataclass(frozen=True, slots=True)
class StopStream:
    pass


@dataclass(frozen=True, slots=True)
class StartRecording:
    pass


@dataclass(frozen=True, slots=True)
class StopRecording:
    pass


ApplicationCommand: TypeAlias = (
    ExploreCameras
    | ConnectCamera
    | CloseCamera
    | StartStream
    | StopStream
    | StartRecording
    | StopRecording
)


"""Hardware-independent camera models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CameraDescriptor:
    """Stable information returned by camera discovery."""

    serial_number: str
    model_name: str | None = None
    vendor_name: str | None = None
    user_defined_name: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    firmware_version: str | None = None

    @property
    def display_name(self) -> str:
        identity = self.model_name or self.user_defined_name or "LUCID Camera"
        return f"{identity} ({self.serial_number})"


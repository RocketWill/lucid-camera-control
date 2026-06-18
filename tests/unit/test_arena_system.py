from __future__ import annotations

import unittest
from typing import Any

from lucid_camera_control.camera.arena_system import (
    ArenaCameraSystem,
    CameraConnectionError,
    CameraNotConnectedError,
    CameraNotFoundError,
)


class FakeDevice:
    def __init__(self) -> None:
        self.start_count = 0
        self.stop_count = 0

    def start_stream(self) -> None:
        self.start_count += 1

    def stop_stream(self) -> None:
        self.stop_count += 1


class FakeArenaSystem:
    def __init__(self, infos: list[dict[str, Any]] | None = None) -> None:
        self.infos = infos or []
        self.device = FakeDevice()
        self.created_with: list[dict[str, Any]] = []
        self.destroyed: list[FakeDevice] = []
        self.create_result: list[FakeDevice] | None = None

    @property
    def device_infos(self) -> list[dict[str, Any]]:
        return [dict(info) for info in self.infos]

    def create_device(self, info: dict[str, Any]) -> list[FakeDevice]:
        self.created_with.append(info)
        return self.create_result if self.create_result is not None else [self.device]

    def destroy_device(self, device: FakeDevice) -> None:
        self.destroyed.append(device)


def lucid_info(serial: str, model: str = "TRI0325-CC") -> dict[str, Any]:
    return {
        "vendor": "LUCID Vision Labs",
        "serial": serial,
        "model": model,
        "name": "Inspection",
        "ip": "192.168.0.10",
        "mac": "00:11:22:33:44:55",
        "version": "1.2.3",
    }


class ArenaCameraSystemTests(unittest.TestCase):
    def test_zero_device_discovery_is_safe(self) -> None:
        adapter = ArenaCameraSystem(FakeArenaSystem())
        self.assertEqual(adapter.discover(), ())
        self.assertFalse(adapter.is_connected)

    def test_discovery_filters_non_lucid_and_maps_all_identity_fields(self) -> None:
        other = lucid_info("OTHER")
        other["vendor"] = "Other Vendor"
        system = FakeArenaSystem([lucid_info("200"), other, lucid_info("100")])
        descriptors = ArenaCameraSystem(system).discover()
        self.assertEqual([item.serial_number for item in descriptors], ["100", "200"])
        descriptor = descriptors[0]
        self.assertEqual(descriptor.model_name, "TRI0325-CC")
        self.assertEqual(descriptor.ip_address, "192.168.0.10")
        self.assertEqual(descriptor.mac_address, "00:11:22:33:44:55")
        self.assertEqual(descriptor.firmware_version, "1.2.3")

    def test_connect_refreshes_and_creates_only_selected_serial(self) -> None:
        system = FakeArenaSystem([lucid_info("100"), lucid_info("200")])
        adapter = ArenaCameraSystem(system)
        descriptor = adapter.connect("200")
        self.assertEqual(descriptor.serial_number, "200")
        self.assertEqual(len(system.created_with), 1)
        self.assertEqual(system.created_with[0]["serial"], "200")
        self.assertTrue(adapter.is_connected)

    def test_unknown_serial_does_not_create_a_device(self) -> None:
        system = FakeArenaSystem([lucid_info("100")])
        adapter = ArenaCameraSystem(system)
        with self.assertRaises(CameraNotFoundError):
            adapter.connect("999")
        self.assertEqual(system.created_with, [])

    def test_second_connect_is_rejected(self) -> None:
        adapter = ArenaCameraSystem(FakeArenaSystem([lucid_info("100")]))
        adapter.connect("100")
        with self.assertRaises(CameraConnectionError):
            adapter.connect("100")

    def test_stream_and_idempotent_close_delegate_to_selected_device(self) -> None:
        system = FakeArenaSystem([lucid_info("100")])
        adapter = ArenaCameraSystem(system)
        adapter.connect("100")
        adapter.start_stream()
        adapter.stop_stream()
        adapter.close()
        adapter.close()
        self.assertEqual(system.device.start_count, 1)
        self.assertEqual(system.device.stop_count, 1)
        self.assertEqual(system.destroyed, [system.device])
        self.assertFalse(adapter.is_connected)

    def test_stream_without_connection_is_rejected(self) -> None:
        adapter = ArenaCameraSystem(FakeArenaSystem())
        with self.assertRaises(CameraNotConnectedError):
            adapter.start_stream()

    def test_unexpected_create_count_is_cleaned_up(self) -> None:
        system = FakeArenaSystem([lucid_info("100")])
        extra_one, extra_two = FakeDevice(), FakeDevice()
        system.create_result = [extra_one, extra_two]
        adapter = ArenaCameraSystem(system)
        with self.assertRaises(CameraConnectionError):
            adapter.connect("100")
        self.assertEqual(system.destroyed, [extra_one, extra_two])
        self.assertFalse(adapter.is_connected)


if __name__ == "__main__":
    unittest.main()

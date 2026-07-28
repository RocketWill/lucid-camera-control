"""JSON parsing and atomic last-known-good persistence."""

from __future__ import annotations

import os
from pathlib import Path

from lucid_camera_control.config.models import AppConfigV1


class ConfigStore:
    def __init__(self, last_known_good_path: Path) -> None:
        self.last_known_good_path = last_known_good_path

    def parse(self, path: Path) -> AppConfigV1:
        data = path.read_text(encoding="utf-8")
        return AppConfigV1.model_validate_json(data)

    def load_last_known_good(self) -> AppConfigV1 | None:
        if not self.last_known_good_path.exists():
            return None
        return self.parse(self.last_known_good_path)

    def export(self, config: AppConfigV1, path: Path) -> None:
        self._atomic_write(config, path)

    def save_last_known_good(self, config: AppConfigV1) -> None:
        self._atomic_write(config, self.last_known_good_path)

    @staticmethod
    def _atomic_write(config: AppConfigV1, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        payload = config.model_dump_json(indent=2)
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()

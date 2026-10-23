"""Local settings, outside presets: presets folder, selected MIDI port, last preset sent (settings.json)."""

from __future__ import annotations

import json
import os
from pathlib import Path

AUTO_PORT = "Auto"
SETTINGS_FILE = "settings.json"
PRESETS_ENV = "BSP_PRESETS_DIR"  # to store presets elsewhere (synced folder…)


class LocalSettings:
    """Reading and writing local settings (stateless)."""

    def presets_root(self, project_root: Path) -> Path:
        custom = os.environ.get(PRESETS_ENV)
        root = Path(custom).expanduser() if custom else Path(project_root) / "presets"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def load(self, project_root: Path) -> dict:
        try:
            data = json.loads((Path(project_root) / SETTINGS_FILE).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def save(self, project_root: Path, settings: dict) -> None:
        text = json.dumps(settings, indent=2, ensure_ascii=False) + "\n"
        (Path(project_root) / SETTINGS_FILE).write_text(text, encoding="utf-8")

    def port_hint(self, choice: str | None) -> str | None:
        """None when the port is "Auto": beatstep-pro-handler then looks for the BSP itself."""
        return None if not choice or choice == AUTO_PORT else choice

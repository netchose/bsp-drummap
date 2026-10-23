"""Command line actions called by tasks.py: recall a preset without opening the interface.

Each method prints its result and returns an exit code (0 = success).
"""

from __future__ import annotations

from pathlib import Path

from .device import BspConnector, BspError
from .model import MODE_LABELS, DrumMapError, channel_label, note_name
from .settings import LocalSettings
from .store import PresetStore
from .workflow import DrumMapWorkflow


class DrumMapCli:
    """Stateless methods: the project folder and the port are passed as parameters."""

    def send(self, project_root: Path, name: str, port: str | None = None, backup: bool = True) -> int:
        root = LocalSettings().presets_root(project_root)
        ref = PresetStore().find(root, name)
        if ref is None:
            print(f'Preset "{name}" not found. Available presets: {self.names(root)}')
            return 1
        try:
            drum_map = PresetStore().load(ref.path)
            result = DrumMapWorkflow().send_to_bsp(root, drum_map, self.port(project_root, port), backup=backup)
        except (BspError, DrumMapError, OSError) as exc:
            print(f"Failed: {exc}")
            return 1
        if result.backup_path:
            print(f"Backup of the previous state: {result.backup_path.name}")
        if not result.report.ok:
            print(f'"{drum_map.name}" sent, but the read-back reports:')
            for problem in result.report.problems:
                print(f"  - {problem}")
            return 2
        print(f'"{drum_map.name}" sent to the BSP ({result.report.written} parameters verified).')
        return 0

    def names(self, root: Path) -> str:
        names = [ref.name for ref in PresetStore().list_presets(root).presets]
        return ", ".join(names) if names else "none"

    def port(self, project_root: Path, port: str | None) -> str | None:
        """Requested port, else the one selected in the interface, else Auto."""
        settings = LocalSettings()
        return settings.port_hint(port or settings.load(project_root).get("port"))

    def dump(self, project_root: Path, name: str, port: str | None = None, overwrite: bool = False) -> int:
        root = LocalSettings().presets_root(project_root)
        try:
            drum_map = DrumMapWorkflow().read_from_bsp(self.port(project_root, port), name=name)
            path = PresetStore().save(root, drum_map, overwrite=overwrite)
        except (BspError, DrumMapError, OSError) as exc:
            print(f"Failed: {exc}")
            return 1
        print(f"BSP drum map saved to {path.name}:")
        print(self.describe(drum_map))
        return 0

    def describe(self, drum_map) -> str:
        lines = [f"  mode {MODE_LABELS[drum_map.mode]}, Drum channel {drum_map.drum_channel}"]
        for pad in drum_map.pads:
            lines.append(f"  pad #{pad.number:>2}: {pad.note:>3} {note_name(pad.note):<4} channel {channel_label(pad.channel)}  {pad.label}")
        return "\n".join(lines)

    def presets(self, project_root: Path) -> int:
        root = LocalSettings().presets_root(project_root)
        listing = PresetStore().list_presets(root)
        for ref in listing.presets:
            print(f"{ref.name}  ({ref.path.name})")
        for problem in listing.problems:
            print(f"Warning: {problem}")
        backups = PresetStore().list_backups(root).presets
        print(f"{len(listing.presets)} preset(s), {len(backups)} automatic backup(s) in {root}")
        return 0

    def ports(self) -> int:
        connector = BspConnector()
        try:
            ports = connector.list_ports()
        except BspError as exc:
            print(f"Failed: {exc}")
            return 1
        print("Inputs:", *ports.inputs or ["none"], sep="\n  ")
        print("Outputs:", *ports.outputs or ["none"], sep="\n  ")
        print(f"Automatic choice: {connector.auto_port(ports.inputs) or 'no BSP detected'}")
        return 0

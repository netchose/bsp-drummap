"""Sequences shared by the interface and invoke: test, read, send with backup."""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .device import BspClient, BspConnector, BspReadError, DrumMapService, WriteReport
from .layout import GP_DRUM_CHANNEL, GP_DRUM_MAP_MODE
from .model import MODE_LABELS, DrumMap, DrumMapCodec
from .store import DEFAULT_KEEP, PresetStore

Opener = Callable[[str | None], BspClient]


@dataclass(frozen=True)
class SendResult:
    report: WriteReport
    backup_path: Path | None


class DrumMapWorkflow:
    """Each method opens the BSP, does its job and closes it (stateless).

    `opener` replaces the real opening, for tests with a simulated BSP.
    """

    def test_connection(self, port_hint: str | None, opener: Opener | None = None) -> str:
        service = DrumMapService()
        with closing(self.open(port_hint, opener)) as client:
            values = service.read_values(client, [GP_DRUM_MAP_MODE, GP_DRUM_CHANNEL])
        mode = service.mode_from_value(values[GP_DRUM_MAP_MODE])
        channel = service.channel_from_value(values[GP_DRUM_CHANNEL], "global Drum channel", allow_drum=False)
        return f"BSP connected: {MODE_LABELS[mode]} drum map, Drum channel {channel}."

    def open(self, port_hint: str | None, opener: Opener | None) -> BspClient:
        return (opener or BspConnector().open)(port_hint)

    def read_from_bsp(
        self, port_hint: str | None, name: str = "Read from the BSP", opener: Opener | None = None
    ) -> DrumMap:
        with closing(self.open(port_hint, opener)) as client:
            return DrumMapService().read(client, name)

    def send_to_bsp(
        self,
        root: Path,
        drum_map: DrumMap,
        port_hint: str | None,
        backup: bool = True,
        keep: int = DEFAULT_KEEP,
        opener: Opener | None = None,
    ) -> SendResult:
        DrumMapCodec().ensure_valid(drum_map)
        service = DrumMapService()
        backup_path = None
        with closing(self.open(port_hint, opener)) as client:
            if backup:
                try:
                    current = service.read(client, "Backup")
                except BspReadError as exc:
                    raise BspReadError(f"backup failed, nothing was sent: {exc}") from exc
                backup_path = PresetStore().save_backup(root, current, keep=keep)
            report = service.write(client, drum_map)
        return SendResult(report=report, backup_path=backup_path)

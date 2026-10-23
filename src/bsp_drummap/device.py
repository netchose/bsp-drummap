"""Talking to the BeatStep Pro: MIDI ports, reading and writing the drum map.

The SysEx transport (frames, paced sending, retries) comes from beatstep-pro-handler.
It is only imported when the connection opens: all the logic is tested with a
simulated BSP, without hardware or python-rtmidi.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Protocol

from .layout import (
    CHANNEL_DRUM_VALUE,
    GP_DRUM_CHANNEL,
    GP_DRUM_MAP_MODE,
    MODE_VALUES,
    PAD_NUMBERS,
    PARAM_GLOBAL,
    describe_param,
    drum_params,
    pad_channel_param,
    pad_note_param,
)
from .model import DRUM, MODE_LABELS, DrumMap, DrumMapCodec, Pad, note_name

PORT_HINTS = ("arturia be", "beatstep")  # same hints as beatstep-pro-handler
# Read requests sent in one burst. Measured on a real BSP: by 6 (the beatstep-pro-handler
# default) it drops replies and pad #6 (channel) was missing on every read;
# by 2 everything answers, in 0.2 s for a full drum map.
READ_CHUNK = 2


class BspError(RuntimeError):
    """Error while talking to the BSP; the message is ready to display."""


class BspConnectionError(BspError):
    """BSP not found or MIDI port unusable."""


class BspReadError(BspError):
    """Missing or unexpected reply from the BSP."""


class BspClient(Protocol):
    """What we use from beatstep_handler.BeatStepPro (or from a simulated BSP)."""

    def read_many(self, pairs: list[tuple[int, int]], chunk: int = ...) -> dict[tuple[int, int], int]: ...

    def write(self, param_id: int, item_id: int, value: int) -> object: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class WriteReport:
    written: int
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.problems


@dataclass(frozen=True)
class PortList:
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]


@dataclass(frozen=True)
class NoteEvent:
    note: int
    channel: int  # 1 to 16
    velocity: int


class DrumMapService:
    """Drum map ↔ raw values conversion, reading and verified writing (stateless)."""

    def read(self, client: BspClient, name: str) -> DrumMap:
        return self.from_values(self.read_values(client, drum_params()), name)

    def read_values(self, client: BspClient, params: list[int]) -> dict[int, int]:
        replies = client.read_many([(PARAM_GLOBAL, param) for param in params], chunk=READ_CHUNK)
        values = {p: replies[(PARAM_GLOBAL, p)] for p in params if (PARAM_GLOBAL, p) in replies}
        missing = [param for param in params if param not in values]
        if missing:
            names = ", ".join(describe_param(param) for param in missing)
            raise BspReadError(f"the BSP did not answer for: {names}")
        return values

    def from_values(self, values: dict[int, int], name: str) -> DrumMap:
        pads = tuple(
            Pad(
                number=n,
                note=values[pad_note_param(n)],
                channel=self.channel_from_value(
                    values[pad_channel_param(n)], describe_param(pad_channel_param(n)), allow_drum=True
                ),
            )
            for n in PAD_NUMBERS
        )
        return DrumMap(
            name=name,
            mode=self.mode_from_value(values[GP_DRUM_MAP_MODE]),
            drum_channel=self.channel_from_value(
                values[GP_DRUM_CHANNEL], describe_param(GP_DRUM_CHANNEL), allow_drum=False
            ),
            pads=pads,
        )

    def mode_from_value(self, value: int) -> str:
        for mode, raw in MODE_VALUES.items():
            if raw == value:
                return mode
        raise BspReadError(f"unknown drum map mode (value {value})")

    def channel_from_value(self, value: int, what: str, allow_drum: bool) -> int | str:
        if 0 <= value <= 15:
            return value + 1
        if allow_drum and value == CHANNEL_DRUM_VALUE:
            return DRUM
        raise BspReadError(f"{what}: unexpected value {value}")

    def write(self, client: BspClient, drum_map: DrumMap, verify: bool = True, pause: float = 0.01) -> WriteReport:
        """Writes the mode (Custom first), the Drum channel then the pads; reads back and retries once."""
        values = self.to_values(DrumMapCodec().ensure_valid(drum_map))
        self.send_values(client, values, pause)
        if not verify:
            return WriteReport(written=len(values), problems=())
        problems = self.check_values(client, values)
        if problems:
            retry = [(param, value) for param, value in values if param in problems]
            self.send_values(client, retry, pause)
            problems = self.check_values(client, retry)
        return WriteReport(written=len(values), problems=tuple(problems.values()))

    def to_values(self, drum_map: DrumMap) -> list[tuple[int, int]]:
        values = [
            (GP_DRUM_MAP_MODE, MODE_VALUES[drum_map.mode]),
            (GP_DRUM_CHANNEL, drum_map.drum_channel - 1),
        ]
        if drum_map.mode != "custom":
            return values  # outside Custom, the BSP ignores per-pad settings
        pads = sorted(drum_map.pads, key=lambda pad: pad.number)
        values += [(pad_note_param(pad.number), pad.note) for pad in pads]
        values += [(pad_channel_param(pad.number), self.channel_to_value(pad.channel)) for pad in pads]
        return values

    def channel_to_value(self, channel: int | str) -> int:
        return CHANNEL_DRUM_VALUE if channel == DRUM else channel - 1

    def send_values(self, client: BspClient, values: list[tuple[int, int]], pause: float) -> None:
        for param, value in values:
            client.write(PARAM_GLOBAL, param, value)
            if pause:
                time.sleep(pause)

    def check_values(self, client: BspClient, values: list[tuple[int, int]]) -> dict[int, str]:
        replies = client.read_many([(PARAM_GLOBAL, param) for param, _ in values], chunk=READ_CHUNK)
        problems = {}
        for param, expected in values:
            got = replies.get((PARAM_GLOBAL, param))
            if got is None:
                problems[param] = f"{describe_param(param)}: no reply"
            elif got != expected:
                problems[param] = (
                    f"{describe_param(param)}: expected {self.format_value(param, expected)}, "
                    f"read {self.format_value(param, got)}"
                )
        return problems

    def format_value(self, param: int, value: int) -> str:
        if param == GP_DRUM_MAP_MODE:
            labels = {raw: MODE_LABELS[mode] for mode, raw in MODE_VALUES.items()}
            return labels.get(value, str(value))
        if param in {pad_note_param(n) for n in PAD_NUMBERS}:
            return f"{value} ({note_name(value)})"
        if 0 <= value <= 15:
            return f"channel {value + 1}"
        if value == CHANNEL_DRUM_VALUE:
            return "Drum channel"
        return str(value)


class BspConnector:
    """MIDI ports, opening the connection and listening to the pads (stateless)."""

    def list_ports(self) -> PortList:
        rtmidi = self.import_rtmidi()
        return PortList(inputs=tuple(rtmidi.MidiIn().get_ports()), outputs=tuple(rtmidi.MidiOut().get_ports()))

    def import_rtmidi(self):
        try:
            import rtmidi
        except ImportError as exc:
            raise BspConnectionError("python-rtmidi is not installed: run `uv sync`.") from exc
        return rtmidi

    def port_hint(self, port_name: str) -> str:
        """Port name without the index added by rtmidi, so the output port can be found too."""
        return re.sub(r"\s+\d+(:\d+)?$", "", port_name).strip() or port_name

    def auto_port(self, ports: tuple[str, ...]) -> str | None:
        index = self.pick(ports, None)
        return None if index is None else ports[index]

    def pick(self, ports: tuple[str, ...] | list[str], port_hint: str | None) -> int | None:
        hints = ((port_hint.lower(),) if port_hint else ()) + PORT_HINTS
        for hint in hints:
            for index, name in enumerate(ports):
                if hint in name.lower():
                    return index
        return None

    def open(self, port_hint: str | None = None) -> BspClient:
        self.import_rtmidi()
        try:
            from beatstep_handler import BeatStepNotFound, BeatStepPro
        except ImportError as exc:
            raise BspConnectionError("beatstep-pro-handler is not installed: run `uv sync`.") from exc
        try:
            return BeatStepPro(port_name=port_hint)
        except BeatStepNotFound as exc:
            where = f' on "{port_hint}"' if port_hint else ""
            raise BspConnectionError(
                f"BeatStep Pro not found{where}: check the USB cable and the selected port."
            ) from exc
        except Exception as exc:  # busy port, driver…: keep the original message
            raise BspConnectionError(
                f"cannot open the BSP ({exc}). If MIDI Control Center is open, close it."
            ) from exc

    def listen(self, port_hint: str | None, seconds: float) -> list[NoteEvent]:
        rtmidi = self.import_rtmidi()
        midi_in = rtmidi.MidiIn()
        ports = midi_in.get_ports()
        index = self.pick(ports, port_hint)
        if index is None:
            raise BspConnectionError("BSP input port not found.")
        try:
            midi_in.open_port(index)
        except Exception as exc:
            raise BspConnectionError(f'cannot open "{ports[index]}" ({exc}).') from exc
        try:
            midi_in.ignore_types(sysex=True, timing=True, active_sense=True)
            return self.collect_notes(midi_in, seconds)
        finally:
            midi_in.close_port()

    def collect_notes(self, midi_in, seconds: float) -> list[NoteEvent]:
        events = []
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            message = midi_in.get_message()
            if message is None:
                time.sleep(0.002)
                continue
            data = message[0]
            if len(data) == 3 and data[0] & 0xF0 == 0x90 and data[2] > 0:
                events.append(NoteEvent(note=data[1], channel=(data[0] & 0x0F) + 1, velocity=data[2]))
        return events

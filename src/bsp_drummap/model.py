"""Drum map model: pads, validation, note names and the JSON preset format."""

from __future__ import annotations

from dataclasses import dataclass

PAD_COUNT = 16
DRUM = "drum"  # pad channel that follows the global Drum channel
MODES = ("custom", "spark", "general_midi", "chromatic")
MODE_LABELS = {
    "custom": "Custom",
    "spark": "Spark",
    "general_midi": "General MIDI",
    "chromatic": "Chromatic",
}
FORMAT_VERSION = 1
MAX_NAME_LENGTH = 60
MAX_LABEL_LENGTH = 24
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


class DrumMapError(ValueError):
    """Invalid drum map or preset file; the message lists the problems."""


@dataclass(frozen=True)
class Pad:
    """A Drum mode pad, numbered as in MIDI Control Center (1 to 16)."""

    number: int
    note: int
    channel: int | str  # 1 to 16, or DRUM to follow the global Drum channel
    label: str = ""  # blank: replaced by default_label(number)

    def __post_init__(self) -> None:
        if isinstance(self.label, str) and not self.label.strip():
            object.__setattr__(self, "label", default_label(self.number))


def default_label(number: int) -> str:
    """Label of an unnamed pad: "Pad-1" … "Pad-16"."""
    return f"Pad-{number}"


@dataclass(frozen=True)
class DrumMap:
    """Complete Drum mode configuration, as saved and recalled."""

    name: str
    mode: str
    drum_channel: int  # 1 to 16: global Drum channel, followed by pads set to DRUM
    pads: tuple[Pad, ...]


def note_name(note: int) -> str:
    """Note name in the Native Instruments convention: C3 = 60, C1 = 36."""
    return f"{NOTE_NAMES[note % 12]}{note // 12 - 2}"


def channel_label(channel: int | str) -> str:
    """Displayed label of a pad channel."""
    return "Drum" if channel == DRUM else str(channel)


def default_drum_map(name: str = "New preset") -> DrumMap:
    """Starting point of the editor: notes 36 to 51 (C1 to D#2), Drum channel."""
    pads = tuple(Pad(number=n, note=35 + n, channel=DRUM) for n in range(1, PAD_COUNT + 1))
    return DrumMap(name=name, mode="custom", drum_channel=10, pads=pads)


def identification_drum_map() -> DrumMap:
    """Test preset: pad #k sends note 59+k on channel k.

    Hitting a physical pad and reading the note and channel received is enough to
    know which MCC number it carries, and to check that notes and channels follow the same order.
    """
    pads = tuple(
        Pad(number=n, note=59 + n, channel=n, label=f"#{n}") for n in range(1, PAD_COUNT + 1)
    )
    return DrumMap(name="Pad identification", mode="custom", drum_channel=10, pads=pads)


class DrumMapCodec:
    """Validation and conversion from/to the JSON preset format (stateless methods)."""

    def from_dict(self, data: object) -> DrumMap:
        if not isinstance(data, dict):
            raise DrumMapError("the preset must be a JSON object")
        version = data.get("format", FORMAT_VERSION)
        if version != FORMAT_VERSION:
            raise DrumMapError(f"unsupported preset format {version!r} (expected {FORMAT_VERSION})")
        raw_pads = data.get("pads")
        if not isinstance(raw_pads, list):
            raise DrumMapError('the "pads" key must be a list')
        pads = tuple(self.pad_from_dict(item) for item in raw_pads)
        drum_map = DrumMap(
            name=str(data.get("name", "")).strip(),
            mode=data.get("mode", "custom"),
            drum_channel=data.get("drum_channel", 10),
            pads=tuple(sorted(pads, key=lambda pad: pad.number)),
        )
        return self.ensure_valid(drum_map)

    def pad_from_dict(self, item: object) -> Pad:
        if not isinstance(item, dict):
            raise DrumMapError(f"invalid pad: {item!r}")
        number = item.get("pad")
        if not self.is_int(number):
            raise DrumMapError(f"invalid pad number: {number!r}")
        return Pad(
            number=number,
            note=item.get("note"),
            channel=item.get("channel"),
            label=item.get("label", ""),
        )

    def ensure_valid(self, drum_map: DrumMap) -> DrumMap:
        problems = self.validate(drum_map)
        if problems:
            raise DrumMapError("invalid drum map: " + "; ".join(problems))
        return drum_map

    def validate(self, drum_map: DrumMap) -> list[str]:
        problems = []
        name = drum_map.name.strip() if isinstance(drum_map.name, str) else ""
        if not name:
            problems.append("the name is empty")
        elif len(name) > MAX_NAME_LENGTH:
            problems.append(f"the name is longer than {MAX_NAME_LENGTH} characters")
        if drum_map.mode not in MODES:
            problems.append(f"unknown mode {drum_map.mode!r}")
        if not self.is_channel(drum_map.drum_channel):
            problems.append(f"invalid Drum channel {drum_map.drum_channel!r} (1 to 16)")
        numbers = [pad.number for pad in drum_map.pads]
        if not all(self.is_int(n) for n in numbers) or sorted(numbers) != list(range(1, PAD_COUNT + 1)):
            problems.append("pads 1 to 16 are required, once each")
        for pad in drum_map.pads:
            problems.extend(self.pad_problems(pad))
        return problems

    def pad_problems(self, pad: Pad) -> list[str]:
        problems = []
        prefix = f"pad #{pad.number}"
        if not (self.is_int(pad.note) and 0 <= pad.note <= 127):
            problems.append(f"{prefix}: invalid note {pad.note!r} (0 to 127)")
        if pad.channel != DRUM and not self.is_channel(pad.channel):
            problems.append(f'{prefix}: invalid channel {pad.channel!r} (1 to 16 or "drum")')
        if not isinstance(pad.label, str) or len(pad.label) > MAX_LABEL_LENGTH:
            problems.append(f"{prefix}: invalid label ({MAX_LABEL_LENGTH} characters max)")
        return problems

    def to_dict(self, drum_map: DrumMap) -> dict:
        self.ensure_valid(drum_map)
        return {
            "format": FORMAT_VERSION,
            "name": drum_map.name.strip(),
            "mode": drum_map.mode,
            "drum_channel": drum_map.drum_channel,
            "pads": [
                {"pad": pad.number, "note": pad.note, "channel": pad.channel, "label": pad.label}
                for pad in sorted(drum_map.pads, key=lambda pad: pad.number)
            ],
        }

    @staticmethod
    def is_int(value: object) -> bool:
        return isinstance(value, int) and not isinstance(value, bool)

    def is_channel(self, value: object) -> bool:
        return self.is_int(value) and 1 <= value <= 16

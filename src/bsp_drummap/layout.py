"""Mapping between the pads and the BeatStep Pro global SysEx parameters.

Ids taken from the beatstep-pro-handler tables, themselves extracted from the
MIDI Control Center dictionary. All of them live in the global bank (0x41).
"""

from __future__ import annotations

PARAM_GLOBAL = 0x41  # same as beatstep_handler.PARAM_GLOBAL
GP_DRUM_MAP_MODE = 0x27  # 0 Custom, 1 Spark, 2 General MIDI, 3 Chromatic
GP_DRUM_CHANNEL = 0x44  # "Drum Send MIDI Channel", 0 to 15
CHANNEL_DRUM_VALUE = 0x42  # pad channel value meaning "follow the Drum channel"

MODE_VALUES = {"custom": 0, "spark": 1, "general_midi": 2, "chromatic": 3}
PAD_NUMBERS = tuple(range(1, 17))

# Physical layout of the BSP: MCC numbers per row, left to right, top row first.
# Pad #1 is bottom left, #9 right above it. This is the only place to change.
GRID_ROWS = (
    ("Top row", (9, 10, 11, 12, 13, 14, 15, 16)),
    ("Bottom row", (1, 2, 3, 4, 5, 6, 7, 8)),
)


def pad_note_param(pad: int) -> int:
    """"Pad #n Note" parameter: 0x30 to 0x3F."""
    _check_pad(pad)
    return 0x30 + pad - 1


def pad_channel_param(pad: int) -> int:
    """"Pad #n Midi Ch" parameter: 0x75 to 0x7C for pads 1 to 8, 0x6D to 0x74 for 9 to 16."""
    _check_pad(pad)
    return 0x75 + pad - 1 if pad <= 8 else 0x6D + pad - 9


def drum_params() -> list[int]:
    """Every parameter of a drum map, in write order."""
    return (
        [GP_DRUM_MAP_MODE, GP_DRUM_CHANNEL]
        + [pad_note_param(n) for n in PAD_NUMBERS]
        + [pad_channel_param(n) for n in PAD_NUMBERS]
    )


def describe_param(param: int) -> str:
    """Readable name of a parameter, for messages."""
    if param == GP_DRUM_MAP_MODE:
        return "drum map mode"
    if param == GP_DRUM_CHANNEL:
        return "global Drum channel"
    for n in PAD_NUMBERS:
        if param == pad_note_param(n):
            return f"pad #{n} (note)"
        if param == pad_channel_param(n):
            return f"pad #{n} (channel)"
    return f"parameter 0x{param:02X}"


def _check_pad(pad: int) -> None:
    if pad not in PAD_NUMBERS:
        raise ValueError(f"pad number outside 1 to 16: {pad!r}")

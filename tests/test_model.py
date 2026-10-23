from bsp_drummap.model import (
    DRUM,
    DrumMap,
    DrumMapCodec,
    DrumMapError,
    Pad,
    channel_label,
    default_drum_map,
    identification_drum_map,
    note_name,
)
from helpers import expect_error


def test_note_names_follow_the_ni_convention():
    assert note_name(60) == "C3"
    assert note_name(36) == "C1"
    assert note_name(37) == "C#1"
    assert note_name(0) == "C-2"
    assert note_name(127) == "G8"


def test_channel_label():
    assert channel_label(DRUM) == "Drum"
    assert channel_label(10) == "10"


def test_default_map_is_valid_and_chromatic_from_c1():
    drum_map = default_drum_map()
    assert DrumMapCodec().validate(drum_map) == []
    assert [pad.note for pad in drum_map.pads] == list(range(36, 52))
    assert all(pad.channel == DRUM for pad in drum_map.pads)


def test_identification_map_gives_each_pad_its_own_note_and_channel():
    drum_map = identification_drum_map()
    assert [(pad.note, pad.channel) for pad in drum_map.pads] == [(59 + n, n) for n in range(1, 17)]


def test_round_trip_through_dict():
    codec = DrumMapCodec()
    drum_map = identification_drum_map()
    assert codec.from_dict(codec.to_dict(drum_map)) == drum_map


def test_from_dict_sorts_pads_and_defaults_labels():
    data = DrumMapCodec().to_dict(default_drum_map("Battery"))
    data["pads"] = list(reversed(data["pads"]))
    for pad in data["pads"]:
        del pad["label"]
    drum_map = DrumMapCodec().from_dict(data)
    assert [pad.number for pad in drum_map.pads] == list(range(1, 17))
    assert [pad.label for pad in drum_map.pads] == [f"Pad-{n}" for n in range(1, 17)]


def test_validation_lists_every_problem():
    pads = list(default_drum_map().pads)
    pads[0] = Pad(number=1, note=128, channel=17, label="x" * 30)
    drum_map = DrumMap(name="  ", mode="funky", drum_channel=0, pads=tuple(pads[:15]))
    problems = DrumMapCodec().validate(drum_map)
    # name, mode, Drum channel, pad count, then note, channel and label of pad #1
    assert len(problems) == 7


def test_booleans_are_not_accepted_as_numbers():
    data = DrumMapCodec().to_dict(default_drum_map())
    data["pads"][0]["note"] = True
    exc = expect_error(DrumMapError, DrumMapCodec().from_dict, data)
    assert "invalid note" in str(exc)


def test_duplicate_pad_numbers_are_rejected():
    data = DrumMapCodec().to_dict(default_drum_map())
    data["pads"][1]["pad"] = 1
    exc = expect_error(DrumMapError, DrumMapCodec().from_dict, data)
    assert "pads 1 to 16" in str(exc)


def test_unknown_format_is_rejected():
    data = DrumMapCodec().to_dict(default_drum_map())
    data["format"] = 2
    expect_error(DrumMapError, DrumMapCodec().from_dict, data)


def test_drum_channel_value_is_accepted_for_pads():
    data = DrumMapCodec().to_dict(default_drum_map())
    data["pads"][4]["channel"] = 11
    drum_map = DrumMapCodec().from_dict(data)
    assert drum_map.pads[4].channel == 11
    assert drum_map.pads[5].channel == DRUM


def test_blank_labels_default_to_the_pad_number():
    assert [pad.label for pad in default_drum_map().pads][:2] == ["Pad-1", "Pad-2"]
    assert Pad(number=9, note=36, channel=DRUM, label="  ").label == "Pad-9"
    assert Pad(number=9, note=36, channel=DRUM, label="Kick").label == "Kick"

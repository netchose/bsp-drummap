from dataclasses import replace

from bsp_drummap.device import READ_CHUNK, BspConnector, BspReadError, DrumMapService, NoteEvent
from bsp_drummap.layout import (
    CHANNEL_DRUM_VALUE,
    GP_DRUM_CHANNEL,
    GP_DRUM_MAP_MODE,
    GRID_ROWS,
    describe_param,
    drum_params,
    pad_channel_param,
    pad_note_param,
)
from bsp_drummap.model import DRUM, DrumMapError, default_drum_map, identification_drum_map
from helpers import FakeBsp, expect_error


def written_params(bsp):
    return [item for _, item, _ in bsp.writes]


def test_parameter_ids_match_the_mcc_tables():
    assert [pad_note_param(n) for n in (1, 8, 9, 16)] == [0x30, 0x37, 0x38, 0x3F]
    assert [pad_channel_param(n) for n in (1, 8, 9, 16)] == [0x75, 0x7C, 0x6D, 0x74]
    assert len(set(drum_params())) == 34
    assert describe_param(0x6D) == "pad #9 (channel)"


def test_grid_shows_each_pad_exactly_once():
    numbers = [n for _, row in GRID_ROWS for n in row]
    assert sorted(numbers) == list(range(1, 17))


def test_read_matches_the_mcc_screenshot():
    drum_map = DrumMapService().read(FakeBsp(), "Lu")
    assert drum_map.mode == "custom"
    assert drum_map.drum_channel == 10
    assert [pad.note for pad in drum_map.pads] == list(range(60, 76))
    assert all(pad.channel == 10 for pad in drum_map.pads)


def test_reads_are_sent_in_small_chunks():
    bsp = FakeBsp()
    service = DrumMapService()
    service.write(bsp, service.read(bsp, "Lu"))
    assert READ_CHUNK == 2
    assert bsp.read_chunks and set(bsp.read_chunks) == {READ_CHUNK}


def test_read_maps_the_drum_channel_value():
    bsp = FakeBsp()
    bsp.values[pad_channel_param(3)] = CHANNEL_DRUM_VALUE
    assert DrumMapService().read(bsp, "Lu").pads[2].channel == DRUM


def test_read_names_the_silent_parameters():
    bsp = FakeBsp(silent={pad_note_param(5), GP_DRUM_CHANNEL})
    exc = expect_error(BspReadError, DrumMapService().read, bsp, "Lu")
    assert "pad #5 (note)" in str(exc) and "global Drum channel" in str(exc)


def test_read_rejects_unexpected_values():
    bsp = FakeBsp()
    bsp.values[pad_channel_param(2)] = 0x41
    exc = expect_error(BspReadError, DrumMapService().read, bsp, "Lu")
    assert "pad #2 (channel)" in str(exc)


def test_write_sets_custom_first_then_drum_channel_then_pads():
    bsp = FakeBsp()
    bsp.values[GP_DRUM_MAP_MODE] = 3  # Chromatic
    report = DrumMapService().write(bsp, identification_drum_map(), pause=0)
    assert report.ok and report.written == 34
    assert written_params(bsp)[:2] == [GP_DRUM_MAP_MODE, GP_DRUM_CHANNEL]
    assert bsp.values[GP_DRUM_MAP_MODE] == 0
    read_back = DrumMapService().read(bsp, "Lu")
    assert [(pad.note, pad.channel) for pad in read_back.pads] == [(59 + n, n) for n in range(1, 17)]


def test_pads_on_drum_use_the_special_channel_value():
    bsp = FakeBsp()
    DrumMapService().write(bsp, default_drum_map(), pause=0)
    assert bsp.values[pad_channel_param(1)] == CHANNEL_DRUM_VALUE
    assert bsp.values[pad_note_param(16)] == 51


def test_other_modes_only_write_mode_and_drum_channel():
    bsp = FakeBsp()
    report = DrumMapService().write(bsp, replace(default_drum_map(), mode="general_midi"), pause=0)
    assert report.ok and report.written == 2
    assert written_params(bsp) == [GP_DRUM_MAP_MODE, GP_DRUM_CHANNEL]
    assert bsp.values[GP_DRUM_MAP_MODE] == 2


def test_write_retries_once_then_reports_what_did_not_stick():
    bsp = FakeBsp(stuck={pad_note_param(4)})
    report = DrumMapService().write(bsp, default_drum_map(), pause=0)
    assert report.problems == ("pad #4 (note): expected 39 (D#1), read 63 (D#3)",)
    assert written_params(bsp).count(pad_note_param(4)) == 2


def test_write_reports_missing_replies():
    bsp = FakeBsp(silent={pad_channel_param(9)})
    report = DrumMapService().write(bsp, default_drum_map(), pause=0)
    assert report.problems == ("pad #9 (channel): no reply",)


def test_write_refuses_an_invalid_map_before_sending_anything():
    bsp = FakeBsp()
    expect_error(DrumMapError, DrumMapService().write, bsp, replace(default_drum_map(), name=""), pause=0)
    assert bsp.writes == []


def test_port_hint_drops_the_index_added_by_rtmidi():
    connector = BspConnector()
    assert connector.port_hint("Arturia BeatStep Pro 1") == "Arturia BeatStep Pro"
    assert connector.port_hint("MIDIIN2 (Arturia BeatStep Pro) 3") == "MIDIIN2 (Arturia BeatStep Pro)"
    linux = "Arturia BeatStep Pro:Arturia BeatStep Pro MIDI 1 24:0"
    assert connector.port_hint(linux) == "Arturia BeatStep Pro:Arturia BeatStep Pro MIDI 1"


def test_auto_port_finds_the_beatstep():
    ports = ("Microsoft GS Wavetable Synth 0", "Maschine MK3 Ctrl MIDI 1", "Arturia BeatStep Pro 2")
    assert BspConnector().auto_port(ports) == "Arturia BeatStep Pro 2"
    assert BspConnector().auto_port(("Maschine MK3 Ctrl MIDI 1",)) is None


class ScriptedMidiIn:
    def __init__(self, messages):
        self.messages = list(messages)

    def get_message(self):
        return self.messages.pop(0) if self.messages else None


def test_listening_keeps_note_on_messages_only():
    midi_in = ScriptedMidiIn([
        ([0x99, 60, 100], 0.0),  # note on, channel 10
        ([0x89, 60, 0], 0.01),  # note off
        ([0x99, 61, 0], 0.0),  # note on velocity 0 = note off
        ([0xB9, 7, 100], 0.0),  # controller
        ([0x90, 36, 90], 0.0),  # note on, channel 1
    ])
    events = BspConnector().collect_notes(midi_in, seconds=0.05)
    assert events == [NoteEvent(note=60, channel=10, velocity=100), NoteEvent(note=36, channel=1, velocity=90)]

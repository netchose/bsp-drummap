import tempfile
from pathlib import Path

from bsp_drummap.device import BspReadError
from bsp_drummap.layout import GP_DRUM_CHANNEL, pad_note_param
from bsp_drummap.model import default_drum_map
from bsp_drummap.store import BACKUP_DIR, PresetStore
from bsp_drummap.workflow import DrumMapWorkflow
from helpers import FakeBsp, expect_error


def test_send_backs_up_the_current_state_then_writes():
    bsp = FakeBsp()
    with tempfile.TemporaryDirectory() as tmp:
        result = DrumMapWorkflow().send_to_bsp(Path(tmp), default_drum_map("Battery"), None, opener=lambda hint: bsp)
        assert result.report.ok
        backup = PresetStore().load(result.backup_path)
        assert [pad.note for pad in backup.pads] == list(range(60, 76))  # the state before sending
    assert bsp.values[pad_note_param(1)] == 36
    assert bsp.closed


def test_send_without_backup_creates_no_file():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        result = DrumMapWorkflow().send_to_bsp(root, default_drum_map(), None, backup=False, opener=lambda hint: FakeBsp())
        assert result.backup_path is None
        assert not (root / BACKUP_DIR).exists()


def test_send_aborts_when_the_backup_cannot_be_read():
    bsp = FakeBsp(silent={GP_DRUM_CHANNEL})
    with tempfile.TemporaryDirectory() as tmp:
        exc = expect_error(
            BspReadError, DrumMapWorkflow().send_to_bsp, Path(tmp), default_drum_map(), None, opener=lambda hint: bsp
        )
    assert "nothing was sent" in str(exc)
    assert bsp.writes == []
    assert bsp.closed


def test_connection_test_describes_the_current_state():
    message = DrumMapWorkflow().test_connection(None, opener=lambda hint: FakeBsp())
    assert message == "BSP connected: Custom drum map, Drum channel 10."


def test_the_chosen_port_is_passed_to_the_opener():
    seen = []

    def opener(hint):
        seen.append(hint)
        return FakeBsp()

    DrumMapWorkflow().read_from_bsp("Arturia BeatStep Pro", opener=opener)
    assert seen == ["Arturia BeatStep Pro"]

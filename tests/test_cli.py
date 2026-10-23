import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from bsp_drummap.cli import DrumMapCli
from bsp_drummap.device import BspConnector
from bsp_drummap.layout import pad_note_param
from bsp_drummap.model import default_drum_map
from bsp_drummap.settings import PRESETS_ENV, LocalSettings
from bsp_drummap.store import PresetStore
from helpers import FakeBsp


@contextmanager
def project_dir():
    """Temporary project folder, without the variable that would move the presets."""
    with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ):
        os.environ.pop(PRESETS_ENV, None)
        yield Path(tmp)


def test_send_by_name_uses_the_port_saved_by_the_interface():
    bsp, seen = FakeBsp(), []

    def fake_open(self, hint):
        seen.append(hint)
        return bsp

    with project_dir() as project:
        LocalSettings().save(project, {"port": "Arturia BeatStep Pro"})
        PresetStore().save(project / "presets", default_drum_map("Battery 4"))
        with mock.patch.object(BspConnector, "open", fake_open):
            code = DrumMapCli().send(project, "battery 4")
    assert code == 0
    assert seen == ["Arturia BeatStep Pro"]
    assert bsp.values[pad_note_param(1)] == 36


def test_send_unknown_preset_fails_cleanly():
    with project_dir() as project:
        assert DrumMapCli().send(project, "Maschine") == 1


def test_dump_saves_what_the_bsp_holds():
    with project_dir() as project:
        with mock.patch.object(BspConnector, "open", lambda self, hint: FakeBsp()):
            code = DrumMapCli().dump(project, "Maschine")
        assert code == 0
        saved = PresetStore().load(project / "presets" / "maschine.json")
        assert [pad.note for pad in saved.pads] == list(range(60, 76))

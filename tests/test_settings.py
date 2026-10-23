import os
import tempfile
from pathlib import Path
from unittest import mock

from bsp_drummap.settings import AUTO_PORT, PRESETS_ENV, SETTINGS_FILE, LocalSettings


def test_presets_live_in_the_project_by_default():
    with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ):
        os.environ.pop(PRESETS_ENV, None)
        root = LocalSettings().presets_root(Path(tmp))
        assert root == Path(tmp) / "presets" and root.is_dir()


def test_presets_folder_can_be_moved_with_an_environment_variable():
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as elsewhere:
        with mock.patch.dict(os.environ, {PRESETS_ENV: elsewhere}):
            assert LocalSettings().presets_root(Path(tmp)) == Path(elsewhere)


def test_settings_round_trip_and_tolerate_a_broken_file():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        assert LocalSettings().load(project) == {}
        LocalSettings().save(project, {"port": "Arturia BeatStep Pro"})
        assert LocalSettings().load(project) == {"port": "Arturia BeatStep Pro"}
        (project / SETTINGS_FILE).write_text("not json", encoding="utf-8")
        assert LocalSettings().load(project) == {}


def test_auto_port_means_no_hint():
    assert LocalSettings().port_hint(AUTO_PORT) is None
    assert LocalSettings().port_hint(None) is None
    assert LocalSettings().port_hint("Arturia BeatStep Pro") == "Arturia BeatStep Pro"

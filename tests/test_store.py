import json
import tempfile
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from bsp_drummap.model import DrumMapError, default_drum_map, identification_drum_map
from bsp_drummap.store import BACKUP_DIR, PresetExistsError, PresetStore
from helpers import expect_error


def test_save_then_load_round_trip():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = PresetStore().save(root, identification_drum_map())
        assert path.name == "pad-identification.json"
        assert PresetStore().load(path) == identification_drum_map()
        assert not list(root.glob("*.tmp"))


def test_file_is_valid_json_with_one_pad_per_line():
    with tempfile.TemporaryDirectory() as tmp:
        text = PresetStore().save(Path(tmp), default_drum_map("Maschine")).read_text(encoding="utf-8")
        assert len([line for line in text.splitlines() if line.strip().startswith('{"pad":')]) == 16
        assert json.loads(text)["name"] == "Maschine"


def test_slug_handles_accents_and_symbols():
    assert PresetStore().slug("Kontakt 8 — Café kit") == "kontakt-8-cafe-kit"
    expect_error(DrumMapError, PresetStore().slug, "!!!")


def test_saving_twice_needs_overwrite():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        PresetStore().save(root, default_drum_map("Battery"))
        changed = replace(default_drum_map("battery"), drum_channel=11)
        expect_error(PresetExistsError, PresetStore().save, root, changed)
        path = PresetStore().save(root, changed, overwrite=True)
        assert PresetStore().load(path).drum_channel == 11


def test_listing_sorts_by_name_and_reports_broken_files():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        PresetStore().save(root, default_drum_map("Maschine"))
        PresetStore().save(root, default_drum_map("battery"))
        (root / "casse.json").write_text("{ not json", encoding="utf-8")
        listing = PresetStore().list_presets(root)
        assert [ref.name for ref in listing.presets] == ["battery", "Maschine"]
        assert len(listing.problems) == 1 and "casse.json" in listing.problems[0]


def test_duplicate_names_are_reported():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = PresetStore().save(root, default_drum_map("Kontakt"))
        (root / "copie.json").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        assert "exists twice" in PresetStore().list_presets(root).problems[0]


def test_find_by_name_or_file_name():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        PresetStore().save(root, default_drum_map("Kontakt 8"))
        assert PresetStore().find(root, "kontakt 8").name == "Kontakt 8"
        assert PresetStore().find(root, "kontakt-8").name == "Kontakt 8"
        assert PresetStore().find(root, "Battery") is None


def test_delete_removes_the_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = PresetStore().save(Path(tmp), default_drum_map("Maschine"))
        PresetStore().delete(path)
        assert not path.exists()


def test_backups_keep_only_the_most_recent():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for second in range(5):
            PresetStore().save_backup(root, default_drum_map(), keep=3, now=datetime(2026, 10, 23, 21, 0, second))
        listing = PresetStore().list_backups(root)
        assert [ref.path.name for ref in listing.presets] == [
            "2026-10-23_21-00-04.json",
            "2026-10-23_21-00-03.json",
            "2026-10-23_21-00-02.json",
        ]
        assert listing.presets[0].name == "Backup 2026-10-23 21:00:04"


def test_backups_in_the_same_second_do_not_overwrite_each_other():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        now = datetime(2026, 10, 23, 21, 0, 0)
        PresetStore().save_backup(root, default_drum_map(), now=now)
        second = PresetStore().save_backup(root, identification_drum_map(), now=now)
        assert second.name == "2026-10-23_21-00-00_2.json"
        assert PresetStore().list_backups(root).presets[0].path == second


def test_backups_are_not_listed_as_presets():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        PresetStore().save_backup(root, default_drum_map())
        assert (root / BACKUP_DIR).is_dir()
        assert PresetStore().list_presets(root).presets == ()

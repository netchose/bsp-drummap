"""Presets on disk: one JSON file per drum map, automatic backups in _backups/."""

from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from .model import DrumMap, DrumMapCodec, DrumMapError

BACKUP_DIR = "_backups"
DEFAULT_KEEP = 10


class PresetExistsError(DrumMapError):
    """A preset with this name (or the same file name) already exists."""


@dataclass(frozen=True)
class PresetRef:
    name: str
    path: Path


@dataclass(frozen=True)
class PresetListing:
    presets: tuple[PresetRef, ...]
    problems: tuple[str, ...]


class PresetStore:
    """Reading and writing presets; the folder is passed on each call (stateless)."""

    def list_presets(self, root: Path) -> PresetListing:
        refs, problems = self.scan(sorted(Path(root).glob("*.json")))
        seen: dict[str, str] = {}
        for ref in refs:
            key = ref.name.casefold()
            if key in seen:
                problems.append(f'"{ref.name}" exists twice ({seen[key]} and {ref.path.name})')
            seen.setdefault(key, ref.path.name)
        ordered = sorted(refs, key=lambda ref: ref.name.casefold())
        return PresetListing(presets=tuple(ordered), problems=tuple(problems))

    def scan(self, paths: list[Path]) -> tuple[list[PresetRef], list[str]]:
        refs, problems = [], []
        for path in paths:
            try:
                refs.append(PresetRef(name=self.load(path).name, path=path))
            except (DrumMapError, OSError) as exc:
                problems.append(f"{path.name} skipped: {exc}")
        return refs, problems

    def load(self, path: Path) -> DrumMap:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DrumMapError(f"unreadable JSON (line {exc.lineno})") from exc
        return DrumMapCodec().from_dict(data)

    def find(self, root: Path, name: str) -> PresetRef | None:
        wanted = name.strip().casefold()
        try:
            wanted_stem = self.slug(name)
        except DrumMapError:
            wanted_stem = None
        for ref in self.list_presets(root).presets:
            if ref.name.casefold() == wanted or ref.path.stem == wanted_stem:
                return ref
        return None

    def save(self, root: Path, drum_map: DrumMap, overwrite: bool = False) -> Path:
        data = DrumMapCodec().to_dict(drum_map)
        path = self.path_for(root, data["name"])
        if path.exists() and not overwrite:
            raise PresetExistsError(
                f'preset "{data['name']}" already exists ({path.name}): '
                'tick "Overwrite" to replace it'
            )
        self.write_json(path, data)
        return path

    def path_for(self, root: Path, name: str) -> Path:
        return Path(root) / f"{self.slug(name)}.json"

    def slug(self, name: str) -> str:
        ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
        slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
        if not slug:
            raise DrumMapError(f'the name "{name}" does not give a usable file name')
        return slug[:60].rstrip("-")

    def write_json(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(self.dumps(data), encoding="utf-8")
        os.replace(tmp, path)

    def dumps(self, data: dict) -> str:
        """JSON easy to edit by hand: one pad per line."""
        lines = ["{"]
        for key, value in data.items():
            if key != "pads":
                lines.append(f"  {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)},")
        pads = ",\n".join(f"    {json.dumps(pad, ensure_ascii=False)}" for pad in data["pads"])
        lines += ['  "pads": [', pads, "  ]", "}"]
        return "\n".join(lines) + "\n"

    def delete(self, path: Path) -> None:
        Path(path).unlink(missing_ok=True)

    def save_backup(
        self, root: Path, drum_map: DrumMap, keep: int = DEFAULT_KEEP, now: datetime | None = None
    ) -> Path:
        now = now or datetime.now()
        folder = Path(root) / BACKUP_DIR
        stamp = f"{now:%Y-%m-%d_%H-%M-%S}"
        path, suffix = folder / f"{stamp}.json", 2
        while path.exists():
            path, suffix = folder / f"{stamp}_{suffix}.json", suffix + 1
        backup = replace(drum_map, name=f"Backup {now:%Y-%m-%d %H:%M:%S}")
        self.write_json(path, DrumMapCodec().to_dict(backup))
        self.prune_backups(folder, keep)
        return path

    def prune_backups(self, folder: Path, keep: int) -> None:
        if keep < 1:
            raise ValueError("at least one backup must be kept")
        for old in sorted(folder.glob("*.json"))[:-keep]:
            old.unlink(missing_ok=True)

    def list_backups(self, root: Path) -> PresetListing:
        paths = sorted((Path(root) / BACKUP_DIR).glob("*.json"), reverse=True)
        refs, problems = self.scan(paths)
        return PresetListing(presets=tuple(refs), problems=tuple(problems))

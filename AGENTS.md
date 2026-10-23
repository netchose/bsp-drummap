# AGENTS.md

Guidance for AI coding agents (and humans) contributing to bsp-drummap.
User documentation lives in [README.md](README.md) (French: [READMEvf.md](READMEvf.md)).

## What the project does

Saves and recalls Arturia BeatStep Pro (BSP) drum maps over USB SysEx: drum map mode,
global Drum channel and, for each of the 16 pads, note, channel and label.
A local Streamlit interface (Recall page + Editor page) and `invoke` tasks drive it.
The SysEx transport comes from [beatstep-pro-handler](https://github.com/jamisonx-dev/beatstep-pro-handler).

## Setup and commands

- Python is pinned to 3.12 (python-rtmidi 1.5.8 has no wheel for 3.13+). Use [uv](https://docs.astral.sh/uv/).
- `uv sync` installs everything, including the dev group (pytest).
- `uv run invoke test` (or `uv run pytest -q tests`) runs the test suite. It needs no hardware.
- `uv run invoke ui` starts the interface on http://localhost:8501. Run it from the project root
  (the task does it for you) so `.streamlit/config.toml` is picked up (localhost only, dark theme).
- `uv run invoke --list` shows the other tasks (`send`, `dump`, `presets`, `ports`).

Run the tests before handing back any change. Add or update tests for behavior you change.

## Hardware safety: read this first

- **Never write to a real BSP without the user's explicit consent.** `send`, the Recall buttons,
  "Send editor to BSP" and "Restore to BSP" overwrite the device configuration.
  Reading (`Read BSP`, `invoke ports`, `DrumMapService.read`) is harmless.
- All logic must stay testable with the simulated BSP (`tests/helpers.py::FakeBsp`).
  Hardware-only code (`rtmidi`, `beatstep_handler`) is imported lazily, when a connection opens.
- Facts verified on real hardware, do not "simplify" them away:
  - configuration SysEx only works over **USB**, never DIN;
  - MIDI Control Center must be closed (it holds the port);
  - the BSP drops replies when it receives too many read requests in one burst:
    reads are sent in chunks of `READ_CHUNK = 2` (`device.py`). With chunks of 6, pad #6 (channel)
    was missing on every read; with 4, pads #13 and #14 (channel) were;
  - outside Custom mode, the BSP ignores per-pad settings: only mode and Drum channel are written.

## Code map (`src/bsp_drummap/`)

| Module | Role |
| --- | --- |
| `layout.py` | SysEx parameter ids for each pad, physical grid (`GRID_ROWS`). Only place to change the layout. |
| `model.py` | `Pad`, `DrumMap`, validation and JSON codec (`DrumMapCodec`), note names (C3 = 60). |
| `device.py` | `DrumMapService` (raw values ↔ drum map, verified write with one retry), `BspConnector` (ports, open, listen). |
| `store.py` | `PresetStore`: one JSON file per preset, automatic backups in `presets/_backups/` (last 10). |
| `workflow.py` | `DrumMapWorkflow`: open → act → close sequences shared by UI and CLI (backup before send). |
| `settings.py` | `LocalSettings`: `settings.json` (MIDI port, last preset sent), `BSP_PRESETS_DIR`. |
| `cli.py` | `DrumMapCli`, called by `tasks.py`; prints results and returns exit codes. |
| `ui.py` | `DrumMapPage`: Streamlit pages, sidebar, editor grid, pad identification. |

## Conventions

- **Language**: everything in the repo is English (UI text, messages, docstrings, comments, tests),
  except `READMEvf.md`. Keep `README.md` and `READMEvf.md` in sync when user-facing behavior changes.
- **Stateless classes**: services take what they need as arguments (folder, port, client) and keep no state.
  Test seams are parameters (`opener=` in `DrumMapWorkflow`), not globals or monkeypatching.
- **Errors**: raise `BspError` subclasses (device) or `DrumMapError` subclasses (data) with a message
  ready to show to the user; the UI and CLI display `str(exc)` as is.
- **Style**: match the surrounding code: type hints, `from __future__ import annotations`,
  frozen dataclasses, short docstrings, few comments (only for the non-obvious), lines up to ~120 characters.
- **Dependencies**: keep them minimal; discuss before adding one.

## Streamlit specifics (`ui.py`)

- Buttons never act directly: they `queue()` an action, which `run_pending_action()` executes at the start
  of the next rerun, before editor widgets exist. This is what allows filling the editor programmatically.
  New actions follow the pattern: a button with `on_click=self.queue, args=("kind", ...)` and a `do_kind` method.
- Streamlit forgets the state of widgets that are not on the current page. Every editor widget key must be
  listed in `EDITOR_KEYS`, which `keep_editor_state()` reassigns on each run.
- Messages to the user go through `self.flash(kind, text)` and are shown by `render_flash()`.

## Preset format

```json
{"format": 1, "name": "Battery", "mode": "custom", "drum_channel": 10,
 "pads": [{"pad": 1, "note": 36, "channel": "drum", "label": "Kick"}, ...]}
```

`channel` is 1–16 or `"drum"`; a blank label becomes `Pad-<n>`. Changing the format means bumping
`FORMAT_VERSION` and keeping old files loadable.

## Do not commit

`settings.json`, `presets/_backups/`, `.venv/`, `.idea/` (already in `.gitignore`), nor personal presets
unless the user asks.

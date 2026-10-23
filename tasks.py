"""Invoke tasks. List them with `uv run invoke --list`."""

import sys
from pathlib import Path

from invoke import Exit, task

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))  # in case the project is not installed

PORT_HELP = "MIDI port; defaults to the one selected in the interface, else Auto"


def _check(code: int) -> None:
    if code:
        raise Exit(code=code)


@task
def ui(c):
    """Opens the interface in the browser (http://localhost:8501)."""
    with c.cd(str(PROJECT_ROOT)):  # Streamlit reads .streamlit/config.toml from the current folder
        c.run(f'streamlit run "{PROJECT_ROOT / "app.py"}"')


@task(
    positional=["name"],
    help={
        "name": "preset name, as shown in the interface",
        "port": PORT_HELP,
        "no_backup": "do not back up the BSP state before sending",
    },
)
def send(c, name, port="", no_backup=False):
    """Sends a preset to the BSP (automatic backup, then verification read-back)."""
    from bsp_drummap.cli import DrumMapCli

    _check(DrumMapCli().send(PROJECT_ROOT, name, port or None, backup=not no_backup))


@task(
    positional=["name"],
    help={
        "name": "name of the preset to create",
        "port": PORT_HELP,
        "overwrite": "replace a preset with the same name",
    },
)
def dump(c, name, port="", overwrite=False):
    """Reads the current BSP drum map and saves it as a preset."""
    from bsp_drummap.cli import DrumMapCli

    _check(DrumMapCli().dump(PROJECT_ROOT, name, port or None, overwrite=overwrite))


@task
def presets(c):
    """Lists the presets and counts the automatic backups."""
    from bsp_drummap.cli import DrumMapCli

    _check(DrumMapCli().presets(PROJECT_ROOT))


@task
def ports(c):
    """Lists the MIDI ports and the one "Auto" would pick."""
    from bsp_drummap.cli import DrumMapCli

    _check(DrumMapCli().ports())


@task
def test(c):
    """Runs the tests (simulated BSP, no hardware needed)."""
    c.run(f'pytest -q "{PROJECT_ROOT / "tests"}"')

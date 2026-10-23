"""Streamlit interface: one-click recall page, grid editor, backups, pad listening.

Buttons only record an action; it runs at the start of the next rerun, before the
editor widgets are created. That is what allows filling the editor (reading the
BSP, loading a preset) without breaking Streamlit's rule about changing widgets
that are already displayed.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import streamlit as st

from .device import BspConnector, BspError
from .layout import GRID_ROWS, PAD_NUMBERS
from .model import (
    DRUM,
    MAX_LABEL_LENGTH,
    MAX_NAME_LENGTH,
    MODE_LABELS,
    MODES,
    DrumMap,
    DrumMapCodec,
    DrumMapError,
    Pad,
    channel_label,
    default_drum_map,
    identification_drum_map,
    note_name,
)
from .settings import AUTO_PORT, LocalSettings
from .store import PresetStore
from .workflow import DrumMapWorkflow

CHANNEL_OPTIONS = (DRUM, *range(1, 17))
CHOOSE = "— choose —"
LISTEN_SECONDS = 8
RECALL_COLUMNS = 4
SPINNER_TEXTS = {
    "test": "Connecting to the BSP…",
    "read_bsp": "Reading the BSP…",
    "send_preset": "Backing up, then sending to the BSP…",
    "send_editor": "Backing up, then sending to the BSP…",
    "restore_backup": "Restoring to the BSP…",
    "listen": f"Listening for {LISTEN_SECONDS} s: hit the BSP pads…",
}
# Streamlit forgets the state of widgets missing from the current page: these keys are
# reassigned on every run so the editor keeps its content when switching pages.
EDITOR_KEYS = (
    "ed_name",
    "ed_mode",
    "ed_drum_channel",
    "overwrite",
    "preset_choice",
    "backup_choice",
    *(f"ed_{n}_{field}" for n in PAD_NUMBERS for field in ("label", "note", "channel")),
)


class DrumMapPage:
    """Two pages sharing one sidebar. State lives in st.session_state; methods get what they need."""

    def configure_page(self) -> None:
        st.set_page_config(page_title="BSP Drum Maps", page_icon="🥁", layout="wide")

    def init_state(self, project_root: Path) -> None:
        state = st.session_state
        if state.get("initialized"):
            return
        settings = LocalSettings().load(project_root)
        state["initialized"] = True
        state["project_root"] = str(project_root)
        state["flash"] = []
        state["action"] = None
        state["listen_events"] = None
        state["port_choice"] = settings.get("port", AUTO_PORT)
        state["last_preset"] = settings.get("last_preset")
        state["preset_choice"] = CHOOSE
        state["auto_backup"] = True
        state["overwrite"] = False
        self.load_editor(default_drum_map())

    def keep_editor_state(self) -> None:
        state = st.session_state
        for key in EDITOR_KEYS:
            if key in state:
                state[key] = state[key]

    def load_editor(self, drum_map: DrumMap) -> None:
        state = st.session_state
        state["ed_name"] = drum_map.name
        state["ed_mode"] = drum_map.mode
        state["ed_drum_channel"] = drum_map.drum_channel
        for pad in drum_map.pads:
            state[f"ed_{pad.number}_label"] = pad.label
            state[f"ed_{pad.number}_note"] = pad.note
            state[f"ed_{pad.number}_channel"] = pad.channel

    def run_pending_action(self, root: Path, port_hint: str | None) -> None:
        action = st.session_state.get("action")
        if not action:
            return
        st.session_state["action"] = None
        kind, *args = action
        try:
            with st.spinner(SPINNER_TEXTS.get(kind, "One moment…")):
                getattr(self, f"do_{kind}")(root, port_hint, *args)
        except (BspError, DrumMapError, OSError) as exc:
            self.flash("error", str(exc))

    def do_test(self, root: Path, port_hint: str | None) -> None:
        self.flash("success", DrumMapWorkflow().test_connection(port_hint))

    def do_read_bsp(self, root: Path, port_hint: str | None) -> None:
        self.load_editor(DrumMapWorkflow().read_from_bsp(port_hint))
        self.flash("success", 'Drum map read from the BSP and loaded into the editor: name it, then "Save".')

    def do_send_preset(self, root: Path, port_hint: str | None, path: str) -> None:
        self.send(root, port_hint, PresetStore().load(Path(path)))

    def do_send_editor(self, root: Path, port_hint: str | None) -> None:
        self.send(root, port_hint, self.editor_drum_map())

    def do_load_preset(self, root: Path, port_hint: str | None, path: str) -> None:
        drum_map = PresetStore().load(Path(path))
        self.load_editor(drum_map)
        self.flash("info", f'"{drum_map.name}" loaded into the editor.')

    def do_save(self, root: Path, port_hint: str | None) -> None:
        drum_map = self.editor_drum_map()
        path = PresetStore().save(root, drum_map, overwrite=st.session_state["overwrite"])
        st.session_state["preset_choice"] = drum_map.name
        st.session_state["overwrite"] = False
        self.flash("success", f'Preset "{drum_map.name}" saved ({path.name}).')

    def do_duplicate(self, root: Path, port_hint: str | None) -> None:
        name = f"{str(st.session_state['ed_name']).strip()} (copy)"
        st.session_state["ed_name"] = name[:MAX_NAME_LENGTH]
        self.flash("info", 'Copy ready in the editor: adjust the name, then "Save".')

    def do_delete(self, root: Path, port_hint: str | None, path: str) -> None:
        name = st.session_state.get("preset_choice", Path(path).stem)
        PresetStore().delete(Path(path))
        st.session_state["preset_choice"] = CHOOSE
        self.flash("info", f'Preset "{name}" deleted.')

    def do_load_backup(self, root: Path, port_hint: str | None, path: str) -> None:
        self.load_editor(PresetStore().load(Path(path)))
        self.flash("info", 'Backup loaded into the editor: rename it, then "Save" to keep it.')

    def do_restore_backup(self, root: Path, port_hint: str | None, path: str) -> None:
        self.send(root, port_hint, PresetStore().load(Path(path)))

    def do_load_identify(self, root: Path, port_hint: str | None) -> None:
        self.load_editor(identification_drum_map())
        self.flash(
            "info",
            'Identification preset loaded: "Send editor to BSP", switch the BSP to DRUM mode, then "Listen".',
        )

    def do_listen(self, root: Path, port_hint: str | None) -> None:
        events = BspConnector().listen(port_hint, LISTEN_SECONDS)
        st.session_state["listen_events"] = [asdict(event) for event in events]
        if events:
            self.flash("info", f"{len(events)} hit(s) received.")
        else:
            self.flash("warning", "No note received: is the BSP in DRUM mode, and is the right port selected?")

    def send(self, root: Path, port_hint: str | None, drum_map: DrumMap) -> None:
        result = DrumMapWorkflow().send_to_bsp(
            root, drum_map, port_hint, backup=st.session_state["auto_backup"]
        )
        self.remember_last_preset(drum_map.name)
        saved = f" Backup of the previous state: {result.backup_path.name}." if result.backup_path else ""
        if result.report.ok:
            self.flash(
                "success",
                f'"{drum_map.name}" sent to the BSP ({result.report.written} parameters verified).{saved}',
            )
            return
        details = "\n".join(f"- {problem}" for problem in result.report.problems)
        self.flash("warning", f'"{drum_map.name}" sent, but the read-back reports:\n{details}\n\n{saved}')

    def remember_last_preset(self, name: str) -> None:
        st.session_state["last_preset"] = name
        project_root = Path(st.session_state["project_root"])
        settings = LocalSettings()
        data = settings.load(project_root)
        data["last_preset"] = name
        settings.save(project_root, data)

    def editor_drum_map(self) -> DrumMap:
        state = st.session_state
        pads = tuple(
            Pad(
                number=n,
                note=int(state[f"ed_{n}_note"]),
                channel=state[f"ed_{n}_channel"],
                label=str(state[f"ed_{n}_label"]).strip(),
            )
            for n in PAD_NUMBERS
        )
        drum_map = DrumMap(
            name=str(state["ed_name"]).strip(),
            mode=state["ed_mode"],
            drum_channel=int(state["ed_drum_channel"]),
            pads=pads,
        )
        return DrumMapCodec().ensure_valid(drum_map)

    def render_sidebar(self, project_root: Path) -> None:
        sidebar = st.sidebar
        sidebar.header("BeatStep Pro")
        options, auto_name, error = self.port_options()
        if error:
            sidebar.error(error)
        if st.session_state.get("port_choice") not in options:
            st.session_state["port_choice"] = AUTO_PORT
        sidebar.selectbox(
            "MIDI port (USB)",
            options,
            key="port_choice",
            on_change=self.save_port_choice,
            args=(project_root,),
            help='"Auto" picks the first port that looks like the BSP. Configuration SysEx only works over USB.',
        )
        if auto_name and st.session_state["port_choice"] == AUTO_PORT:
            sidebar.caption(f"Auto → {auto_name}")
        sidebar.button("Test connection", key="btn_test", on_click=self.queue, args=("test",))
        sidebar.checkbox(
            "Auto backup before sending",
            key="auto_backup",
            help="Reads the BSP and keeps its state in presets/_backups (last 10).",
        )

    def render_preset_manager(self, root: Path) -> None:
        sidebar = st.sidebar
        sidebar.divider()
        sidebar.header("Presets")
        listing = PresetStore().list_presets(root)
        for problem in listing.problems:
            sidebar.warning(problem)
        paths = {ref.name: str(ref.path) for ref in listing.presets}
        if st.session_state.get("preset_choice") not in paths:
            st.session_state["preset_choice"] = CHOOSE
        sidebar.selectbox("Preset", [CHOOSE, *paths], key="preset_choice")
        path = paths.get(st.session_state["preset_choice"])
        sidebar.button(
            "Send to BSP",
            key="btn_send_preset",
            type="primary",
            disabled=path is None,
            on_click=self.queue,
            args=("send_preset", path),
        )
        edit_col, delete_col = sidebar.columns(2)
        edit_col.button(
            "Edit", key="btn_edit_preset", disabled=path is None, on_click=self.queue, args=("load_preset", path)
        )
        with delete_col.popover("Delete", disabled=path is None):
            st.write(f'Delete "{st.session_state["preset_choice"]}"?')
            st.button("Confirm", key="btn_delete_preset", on_click=self.queue, args=("delete", path))

    def port_options(self) -> tuple[list[str], str | None, str | None]:
        connector = BspConnector()
        try:
            ports = connector.list_ports()
        except BspError as exc:
            return [AUTO_PORT], None, str(exc)
        hints: list[str] = []
        for name in ports.inputs:
            hint = connector.port_hint(name)
            if hint not in hints:
                hints.append(hint)
        error = None if ports.inputs else "No MIDI input port: is the BSP connected by USB?"
        return [AUTO_PORT, *hints], connector.auto_port(ports.inputs), error

    def save_port_choice(self, project_root: Path) -> None:
        settings = LocalSettings()
        data = settings.load(project_root)
        data["port"] = st.session_state["port_choice"]
        settings.save(project_root, data)

    def render_flash(self) -> None:
        for kind, text in st.session_state["flash"]:
            getattr(st, kind)(text)
        st.session_state["flash"] = []

    def render_recall(self, root: Path) -> None:
        st.title("Recall")
        st.caption("One click sends the preset to the BSP. The last preset sent is highlighted.")
        self.render_flash()
        listing = PresetStore().list_presets(root)
        for problem in listing.problems:
            st.warning(problem)
        if not listing.presets:
            st.info("No preset yet: create one in the Editor page.")
            return
        last = st.session_state.get("last_preset")
        refs = list(listing.presets)
        for start in range(0, len(refs), RECALL_COLUMNS):
            row = refs[start : start + RECALL_COLUMNS]
            for column, ref in zip(st.columns(RECALL_COLUMNS), row):
                column.button(
                    ref.name,
                    key=f"recall_{ref.path.stem}",
                    type="primary" if ref.name == last else "secondary",
                    width="stretch",
                    on_click=self.queue,
                    args=("send_preset", str(ref.path)),
                )
        if last:
            st.caption(f"Last sent: {last}")

    def render_editor(self, root: Path) -> None:
        st.title("Editor")
        self.render_preset_manager(root)
        self.render_flash()
        self.render_editor_header()
        self.render_editor_actions()
        self.render_grid()
        self.render_backups(root)
        self.render_identify()

    def render_editor_header(self) -> None:
        name_col, mode_col, channel_col = st.columns([3, 2, 2])
        name_col.text_input("Preset name", key="ed_name", max_chars=MAX_NAME_LENGTH)
        mode_col.selectbox("Drum map mode", MODES, key="ed_mode", format_func=MODE_LABELS.get)
        channel_col.selectbox(
            "Global Drum channel",
            list(range(1, 17)),
            key="ed_drum_channel",
            help='Channel used by the pads set to "Drum".',
        )
        if st.session_state["ed_mode"] != "custom":
            st.info("Outside Custom mode, the BSP ignores per-pad settings: only the mode and Drum channel are sent.")

    def render_editor_actions(self) -> None:
        read_col, save_col, copy_col, send_col, overwrite_col = st.columns([2, 2, 2, 3, 3])
        read_col.button(
            "Read BSP",
            key="btn_read",
            on_click=self.queue,
            args=("read_bsp",),
            help="Replaces the editor content with the drum map currently on the BSP.",
        )
        save_col.button("Save", key="btn_save", on_click=self.queue, args=("save",))
        copy_col.button("Duplicate", key="btn_duplicate", on_click=self.queue, args=("duplicate",))
        send_col.button(
            "Send editor to BSP", key="btn_send_editor", type="primary", on_click=self.queue, args=("send_editor",)
        )
        overwrite_col.checkbox("Overwrite if the name exists", key="overwrite")

    def render_grid(self) -> None:
        disabled = st.session_state["ed_mode"] != "custom"
        st.caption("Pad numbers = MIDI Control Center numbers, laid out as on the BSP (#1 bottom left).")
        for row_label, numbers in GRID_ROWS:
            st.markdown(f"**{row_label}**")
            for column, number in zip(st.columns(len(numbers)), numbers):
                with column.container(border=True):
                    self.render_pad(number, disabled)

    def render_pad(self, number: int, disabled: bool) -> None:
        note = int(st.session_state[f"ed_{number}_note"])
        st.markdown(f"**#{number}** · {note_name(note)}")
        st.text_input(
            "Label",
            key=f"ed_{number}_label",
            max_chars=MAX_LABEL_LENGTH,
            placeholder="Label",
            label_visibility="collapsed",
            disabled=disabled,
        )
        st.number_input("Note", min_value=0, max_value=127, step=1, key=f"ed_{number}_note", disabled=disabled)
        st.selectbox("Channel", CHANNEL_OPTIONS, key=f"ed_{number}_channel", format_func=channel_label, disabled=disabled)

    def render_backups(self, root: Path) -> None:
        listing = PresetStore().list_backups(root)
        with st.expander(f"Automatic backups ({len(listing.presets)})"):
            for problem in listing.problems:
                st.warning(problem)
            if not listing.presets:
                st.caption("A backup of the BSP is made before each send; the last 10 are kept.")
                return
            paths = {ref.name: str(ref.path) for ref in listing.presets}
            if st.session_state.get("backup_choice") not in paths:
                st.session_state["backup_choice"] = next(iter(paths))
            st.selectbox("Backup", list(paths), key="backup_choice")
            path = paths[st.session_state["backup_choice"]]
            load_col, restore_col = st.columns(2)
            load_col.button(
                "Load into editor", key="btn_backup_load", on_click=self.queue, args=("load_backup", path)
            )
            restore_col.button(
                "Restore to BSP", key="btn_backup_restore", on_click=self.queue, args=("restore_backup", path)
            )

    def render_identify(self) -> None:
        with st.expander("Identify the pads (check the order)"):
            st.markdown(
                "1. **Load identification preset**, then **Send editor to BSP**.\n"
                "2. Switch the BSP to **DRUM** mode.\n"
                f"3. **Listen**, then hit the pads left to right, bottom row then top row ({LISTEN_SECONDS} s).\n\n"
                "Each hit gives the pad (from the note received) and checks that the received channel matches."
            )
            load_col, listen_col = st.columns(2)
            load_col.button(
                "Load identification preset", key="btn_identify", on_click=self.queue, args=("load_identify",)
            )
            listen_col.button(f"Listen {LISTEN_SECONDS} s", key="btn_listen", on_click=self.queue, args=("listen",))
            events = st.session_state.get("listen_events")
            if events:
                st.dataframe(self.listen_rows(events), hide_index=True)
                st.caption('The "Pad" column assumes the editor holds the drum map currently on the BSP.')

    def listen_rows(self, events: list[dict]) -> list[dict]:
        state = st.session_state
        drum_channel = int(state["ed_drum_channel"])
        rows = []
        for index, event in enumerate(events, start=1):
            pads = [n for n in PAD_NUMBERS if int(state[f"ed_{n}_note"]) == event["note"]]
            expected = sorted(
                {drum_channel if state[f"ed_{n}_channel"] == DRUM else int(state[f"ed_{n}_channel"]) for n in pads}
            )
            rows.append(
                {
                    "Hit": index,
                    "Note received": f"{event['note']} · {note_name(event['note'])}",
                    "Channel received": event["channel"],
                    "Pad (per editor)": ", ".join(f"#{n}" for n in pads) or "none",
                    "Expected channel": ", ".join(str(c) for c in expected) or "—",
                    "Consistent": "✓" if pads and event["channel"] in expected else "✗",
                }
            )
        return rows

    def queue(self, kind: str, *args: str | None) -> None:
        st.session_state["action"] = (kind, *args)

    def flash(self, kind: str, text: str) -> None:
        st.session_state["flash"].append((kind, text))

    def launch(self, project_root: Path) -> None:
        self.configure_page()
        self.init_state(project_root)
        self.keep_editor_state()
        settings = LocalSettings()
        root = settings.presets_root(project_root)
        port_hint = settings.port_hint(st.session_state.get("port_choice"))

        def recall() -> None:
            self.render_recall(root)

        def editor() -> None:
            self.render_editor(root)

        navigation = st.navigation(
            [
                st.Page(recall, title="Recall", icon="🥁", url_path="recall", default=True),
                st.Page(editor, title="Editor", icon="🎛️", url_path="editor"),
            ]
        )
        self.run_pending_action(root, port_hint)
        self.render_sidebar(project_root)
        navigation.run()

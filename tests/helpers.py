"""Test tools: a simulated BeatStep Pro and a minimal pytest.raises equivalent."""

from bsp_drummap.layout import (
    GP_DRUM_CHANNEL,
    GP_DRUM_MAP_MODE,
    PAD_NUMBERS,
    PARAM_GLOBAL,
    pad_channel_param,
    pad_note_param,
)


def screenshot_values() -> dict[int, int]:
    """State of the MCC screenshot: Custom, pad #k → note 59+k, channel 10 everywhere."""
    values = {GP_DRUM_MAP_MODE: 0, GP_DRUM_CHANNEL: 9}
    for n in PAD_NUMBERS:
        values[pad_note_param(n)] = 59 + n
        values[pad_channel_param(n)] = 9
    return values


class FakeBsp:
    """Simulated BSP: global parameters in memory.

    silent: parameters that never answer a read.
    stuck:  parameters whose writes are ignored.
    """

    def __init__(self, values=None, silent=(), stuck=()):
        self.values = dict(screenshot_values() if values is None else values)
        self.silent = set(silent)
        self.stuck = set(stuck)
        self.writes = []
        self.read_chunks = []
        self.closed = False

    def read_many(self, pairs, chunk=6, retries=3, budget=6.0):
        self.read_chunks.append(chunk)
        return {
            (param_id, item): self.values[item]
            for param_id, item in pairs
            if param_id == PARAM_GLOBAL and item not in self.silent and item in self.values
        }

    def write(self, param_id, item_id, value, verify=False):
        self.writes.append((param_id, item_id, value))
        if param_id == PARAM_GLOBAL and item_id not in self.stuck:
            self.values[item_id] = value
        return True

    def close(self):
        self.closed = True


def expect_error(error_type, function, *args, **kwargs):
    """Calls function and returns the expected exception (fails if nothing is raised)."""
    try:
        function(*args, **kwargs)
    except error_type as exc:
        return exc
    raise AssertionError(f"{error_type.__name__} expected")

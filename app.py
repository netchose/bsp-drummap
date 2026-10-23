"""Streamlit entry point: `uv run invoke ui` (or `uv run streamlit run app.py`)."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))  # in case the project is not installed

from bsp_drummap.ui import DrumMapPage  # noqa: E402

DrumMapPage().launch(PROJECT_ROOT)

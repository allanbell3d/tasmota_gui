"""Make ``src/`` importable when a launcher is run as a plain script.

``python -m apps.desktop`` goes through ``apps/__init__.py``, which already
adds ``src/`` to ``sys.path``. ``python apps/desktop.py`` and PyInstaller
run the file directly, so the launchers import this module first.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC_PATH = Path(__file__).resolve().parents[1] / "src"
if SRC_PATH.is_dir() and str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

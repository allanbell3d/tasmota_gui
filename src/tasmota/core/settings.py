"""Persistent user settings kept outside version control.

Personal values (IP ranges, backlog commands, web password, last-used
options) live in a JSON file instead of the source code. The apps load it on
start and save it whenever a run starts and when they close, so values are
entered once and remembered.

Where the file lives (first match wins for reading; saving uses the first
writable directory):

1. ``$TASMOTA_GUI_SETTINGS_DIR`` if set.
2. An explicit directory passed by the caller (the Android app passes its
   private ``user_data_dir``).
3. Running from source: ``<project root>/.private/``.
   Packaged executable: ``<folder of the .exe>/.private/``.
4. Fallback if the above is not writable: ``%APPDATA%/TasmotaBulkTool`` on
   Windows, ``~/.config/tasmota_bulk_tool`` elsewhere.

If no settings file exists yet, a bundled seed is used when present: a
``.private/tasmota_settings.json`` next to the bundled assets (the PyInstaller
spec copies it into the executable). Otherwise the neutral defaults in
``tasmota.constants`` apply.

The ``.private/`` folder is git-ignored. Keys this module does not know are
kept when saving, so the file can carry notes (for example
``_command_notes``).
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from tasmota.constants import (
    DEFAULT_BACKLOG_COMMANDS,
    DEFAULT_IP_RANGES,
    DEFAULT_RETRIES,
    DEFAULT_THREADS,
    DEFAULT_TIMEOUT,
)
from tasmota.core.utils import candidate_asset_roots

__all__ = [
    "ENV_SETTINGS_DIR",
    "PRIVATE_DIR_NAME",
    "SETTINGS_FILENAME",
    "SettingsStore",
    "UserSettings",
]

ENV_SETTINGS_DIR = "TASMOTA_GUI_SETTINGS_DIR"
PRIVATE_DIR_NAME = ".private"
SETTINGS_FILENAME = "tasmota_settings.json"
_FALLBACK_APP_DIR = "TasmotaBulkTool"


@dataclass
class UserSettings:
    """Values remembered between sessions.

    OTA URLs are deliberately not stored: a URL pinned to one release for a
    single run should not silently apply to the next run.
    """

    ip_ranges: str = DEFAULT_IP_RANGES
    commands: List[str] = field(default_factory=lambda: list(DEFAULT_BACKLOG_COMMANDS))
    threads: int = DEFAULT_THREADS
    timeout: float = float(DEFAULT_TIMEOUT)
    retries: int = DEFAULT_RETRIES
    info_mode: str = "lite"
    output_dir: str = ""
    web_password: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    _KNOWN_KEYS = (
        "ip_ranges",
        "commands",
        "threads",
        "timeout",
        "retries",
        "info_mode",
        "output_dir",
        "web_password",
    )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = dict(self.extra)
        for key in self._KNOWN_KEYS:
            data[key] = getattr(self, key)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserSettings":
        """Build settings from parsed JSON, ignoring values of the wrong type."""
        settings = cls()
        if isinstance(data.get("ip_ranges"), str):
            settings.ip_ranges = data["ip_ranges"]
        commands = data.get("commands")
        if isinstance(commands, list):
            settings.commands = [str(cmd) for cmd in commands if isinstance(cmd, str) and cmd.strip()]
        settings.threads = _coerce(data.get("threads"), int, settings.threads)
        settings.timeout = _coerce(data.get("timeout"), float, settings.timeout)
        settings.retries = _coerce(data.get("retries"), int, settings.retries)
        if data.get("info_mode") in ("lite", "full"):
            settings.info_mode = data["info_mode"]
        if isinstance(data.get("output_dir"), str):
            settings.output_dir = data["output_dir"]
        if isinstance(data.get("web_password"), str):
            settings.web_password = data["web_password"]
        settings.extra = {k: v for k, v in data.items() if k not in cls._KNOWN_KEYS}
        return settings


def _coerce(value: Any, kind: type, default):
    if isinstance(value, bool) or value is None:
        return default
    try:
        coerced = kind(value)
    except (TypeError, ValueError):
        return default
    return coerced if coerced > 0 else default


def _project_root() -> Path:
    # src/tasmota/core/settings.py -> project root is three levels above "core".
    return Path(__file__).resolve().parents[3]


def _primary_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / PRIVATE_DIR_NAME
    return _project_root() / PRIVATE_DIR_NAME


def _fallback_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / _FALLBACK_APP_DIR
    return Path.home() / ".config" / "tasmota_bulk_tool"


class SettingsStore:
    """Load and save :class:`UserSettings` as JSON."""

    def __init__(self, directory: Optional[os.PathLike] = None) -> None:
        env_dir = os.environ.get(ENV_SETTINGS_DIR)
        if env_dir:
            self._dirs = [Path(env_dir)]
        elif directory is not None:
            self._dirs = [Path(directory)]
        else:
            self._dirs = [_primary_dir(), _fallback_dir()]
        self.loaded_from: Optional[Path] = None

    @property
    def candidate_paths(self) -> List[Path]:
        return [directory / SETTINGS_FILENAME for directory in self._dirs]

    @staticmethod
    def _seed_paths() -> Iterable[Path]:
        seen = set()
        for root in candidate_asset_roots(Path(__file__).resolve()):
            if root in seen:
                continue
            seen.add(root)
            yield root / PRIVATE_DIR_NAME / SETTINGS_FILENAME

    def load(self) -> Tuple[UserSettings, Optional[str]]:
        """Return (settings, warning). Never raises.

        A file that cannot be parsed is renamed to ``*.corrupt-<timestamp>``
        so the next save does not destroy it, and defaults are returned.
        """
        for path in list(self.candidate_paths) + list(self._seed_paths()):
            if not path.is_file():
                continue
            try:
                with path.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
                if not isinstance(data, dict):
                    raise ValueError("top level must be a JSON object")
            except (OSError, ValueError) as exc:
                warning = f"Settings file {path} could not be read ({exc})"
                if path in self.candidate_paths:
                    backup = path.with_name(f"{path.name}.corrupt-{time.strftime('%Y%m%d_%H%M%S')}")
                    try:
                        path.replace(backup)
                        warning += f"; moved it to {backup.name}"
                    except OSError:
                        pass
                return UserSettings(), warning + ". Using defaults."
            self.loaded_from = path
            return UserSettings.from_dict(data), None
        return UserSettings(), None

    def save(self, settings: UserSettings) -> Optional[str]:
        """Write settings atomically. Returns an error message or None."""
        payload = json.dumps(settings.to_dict(), indent=2, ensure_ascii=False) + "\n"
        errors = []
        for path in self.candidate_paths:
            tmp = path.with_name(path.name + ".tmp")
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp.write_text(payload, encoding="utf-8")
                os.replace(tmp, path)
                return None
            except OSError as exc:
                errors.append(f"{path}: {exc}")
                try:
                    tmp.unlink()
                except OSError:
                    pass
        return "Could not save settings: " + "; ".join(errors)

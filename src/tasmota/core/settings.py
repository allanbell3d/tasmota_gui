"""Persistent user settings kept outside version control.

Personal values (IP ranges, backlog commands, web password, last-used
options) live in a JSON file instead of the source code. The apps load it on
start and save it whenever a run starts and when they close, so values are
entered once and remembered.

Where the file lives (first existing file wins for reading; saving goes back
to the file that was read, otherwise to the first writable directory):

1. An explicit directory passed by the caller (the Android app passes its
   private ``user_data_dir``).
2. ``$TASMOTA_GUI_SETTINGS_DIR`` if set.
3. Running from source: ``<project root>/.private/``.
   Packaged executable: ``<folder of the .exe>/.private/``.
4. Fallback if the above is not writable: ``%APPDATA%/TasmotaBulkTool`` on
   Windows, ``~/.config/tasmota_bulk_tool`` elsewhere.

If no settings file exists yet, a bundled seed is used when present:
``.private/tasmota_settings.json`` inside the PyInstaller bundle (the spec
copies it in) or in the project root. Otherwise the neutral defaults in
``tasmota.constants`` apply.

A file that exists but cannot be read (locked by antivirus or a sync client)
blocks saving for the session, so the real file is never replaced by
defaults.

The ``.private/`` folder is git-ignored. Keys this module does not know are
kept when saving, so the file can carry notes (for example
``_command_notes``).
"""

from __future__ import annotations

import json
import math
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
    MAX_RETRIES,
    MAX_THREADS,
    MAX_TIMEOUT,
    MIN_RETRIES,
    MIN_THREADS,
    MIN_TIMEOUT,
)

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
    # Keys whose stored value could not be used (reported, not saved).
    issues: List[str] = field(default_factory=list, repr=False, compare=False)

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
        """Build settings from parsed JSON.

        Hand-edited files get some slack: ``ip_ranges`` may be a list of
        lines, ``commands`` a single multi-line string. A value that still
        cannot be used is kept under ``_invalid_<key>`` (and saved back), so
        an edit is never silently thrown away.
        """
        settings = cls()
        invalid: Dict[str, Any] = {}

        ip_ranges = data.get("ip_ranges")
        if isinstance(ip_ranges, list) and all(_is_scalar(line) for line in ip_ranges):
            ip_ranges = "\n".join(str(line) for line in ip_ranges)
        if isinstance(ip_ranges, str):
            settings.ip_ranges = ip_ranges
        elif "ip_ranges" in data:
            invalid["ip_ranges"] = ip_ranges

        commands = data.get("commands")
        if isinstance(commands, str):
            commands = commands.splitlines()
        if isinstance(commands, list):
            settings.commands = [cmd.strip() for cmd in commands if isinstance(cmd, str) and cmd.strip()]
            if any(not isinstance(cmd, str) for cmd in commands):
                invalid["commands"] = [cmd for cmd in commands if not isinstance(cmd, str)]
        elif "commands" in data:
            invalid["commands"] = commands

        for key, kind, low, high in (
            ("threads", int, MIN_THREADS, MAX_THREADS),
            ("timeout", float, MIN_TIMEOUT, MAX_TIMEOUT),
            ("retries", int, MIN_RETRIES, MAX_RETRIES),
        ):
            default = getattr(settings, key)
            value = _coerce(data.get(key), kind, None, low, high)
            setattr(settings, key, default if value is None else value)
            if value is None and key in data:
                invalid[key] = data[key]

        info_mode = str(data.get("info_mode", "")).strip().lower()
        if info_mode in ("lite", "full"):
            settings.info_mode = info_mode
        elif "info_mode" in data:
            invalid["info_mode"] = data["info_mode"]

        if isinstance(data.get("output_dir"), str):
            settings.output_dir = data["output_dir"]
        elif "output_dir" in data:
            invalid["output_dir"] = data["output_dir"]
        password = data.get("web_password")
        if _is_scalar(password):
            settings.web_password = str(password)  # e.g. 1234 typed without quotes
        elif "web_password" in data:
            invalid["web_password"] = password

        settings.extra = {k: v for k, v in data.items() if k not in cls._KNOWN_KEYS}
        for key in cls._KNOWN_KEYS:
            if key not in invalid:
                # The key is usable again: drop a leftover from an older edit.
                settings.extra.pop(f"_invalid_{key}", None)
        for key, value in invalid.items():
            # Keep the first unusable value if one was already set aside.
            settings.extra.setdefault(f"_invalid_{key}", value)
        settings.issues = sorted(invalid)
        return settings


def _is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float)) and not isinstance(value, bool)


def _coerce(value: Any, kind: type, default, low, high):
    """Convert to ``kind`` and clamp to [low, high]; bad or non-finite -> default."""
    if isinstance(value, bool) or value is None:
        return default
    try:
        number = float(value)
        if not math.isfinite(number):
            return default
        coerced = kind(number)
    except (TypeError, ValueError, OverflowError):
        return default
    return max(low, min(coerced, high))


def _decode(raw: bytes) -> str:
    """Decode UTF-8 (with or without BOM) or BOM-marked UTF-16.

    Notepad may add a UTF-8 BOM; Windows PowerShell 5.1 ``>`` / ``Out-File``
    writes UTF-16LE with a BOM.
    """
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


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
        if directory is not None:
            self._dirs = [Path(directory)]
        elif env_dir:
            self._dirs = [Path(env_dir)]
        else:
            self._dirs = [_primary_dir(), _fallback_dir()]
        self.loaded_from: Optional[Path] = None
        self._save_blocked: Optional[str] = None

    @property
    def candidate_paths(self) -> List[Path]:
        return [directory / SETTINGS_FILENAME for directory in self._dirs]

    @staticmethod
    def _seed_paths() -> Iterable[Path]:
        # Only the PyInstaller bundle and the project root - never arbitrary
        # parent folders, where anyone could plant a settings file.
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            yield Path(meipass) / PRIVATE_DIR_NAME / SETTINGS_FILENAME
        if not getattr(sys, "frozen", False):
            # In a frozen build the "project root" would be a temp folder.
            yield _project_root() / PRIVATE_DIR_NAME / SETTINGS_FILENAME

    def load(self) -> Tuple[UserSettings, Optional[str]]:
        """Return (settings, warning). Never raises.

        A file that cannot be parsed is renamed to ``*.corrupt-<timestamp>``
        so it is kept, and defaults are returned. A file that cannot be read
        at all is left alone and saving is disabled for this session.
        """
        for path in list(self.candidate_paths) + list(self._seed_paths()):
            if not path.is_file():
                continue
            try:
                raw = path.read_bytes()
            except OSError as exc:
                if path in self.candidate_paths:
                    self._save_blocked = f"settings file {path} could not be read earlier ({exc})"
                return UserSettings(), (
                    f"Settings file {path} could not be read ({exc}). Using defaults; "
                    "changes will not be saved this session."
                )
            try:
                text, decode_error = _decode(raw), None
            except UnicodeError as exc:
                text, decode_error = None, exc
            try:
                if decode_error is not None:
                    raise ValueError(f"not UTF-8/UTF-16 text: {decode_error}")
                data = json.loads(text)
                if not isinstance(data, dict):
                    raise ValueError("top level must be a JSON object")
            except ValueError as exc:
                warning = f"Settings file {path} is not valid JSON ({exc})"
                if path in self.candidate_paths:
                    backup = path.with_name(f"{path.name}.corrupt-{time.strftime('%Y%m%d_%H%M%S')}")
                    try:
                        path.replace(backup)
                        warning += f"; moved it to {backup.name}"
                    except OSError:
                        self._save_blocked = f"could not move the unreadable {path} aside"
                return UserSettings(), warning + ". Using defaults."
            self.loaded_from = path
            settings = UserSettings.from_dict(data)
            if settings.issues:
                keys = ", ".join(settings.issues)
                return settings, (
                    f"Settings file {path}: ignored invalid value(s) for {keys} "
                    "(kept in the file as _invalid_<key>)"
                )
            return settings, None
        return UserSettings(), None

    def save(self, settings: UserSettings) -> Optional[str]:
        """Write settings atomically. Returns an error message or None.

        Saves back to the file that was loaded (a seed only counts if it is
        one of this store's own paths), so a one-off write failure cannot
        split settings between two locations.
        """
        if self._save_blocked:
            return f"Settings not saved: {self._save_blocked}"
        payload = json.dumps(settings.to_dict(), indent=2, ensure_ascii=False) + "\n"
        errors = []
        targets = [self.loaded_from] if self.loaded_from in self.candidate_paths else self.candidate_paths
        for path in targets:
            tmp = path.with_name(path.name + ".tmp")
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp.write_text(payload, encoding="utf-8")
                os.replace(tmp, path)
                self.loaded_from = path
                return None
            except OSError as exc:
                errors.append(f"{path}: {exc}")
                try:
                    tmp.unlink()
                except OSError:
                    pass
        return "Could not save settings: " + "; ".join(errors)

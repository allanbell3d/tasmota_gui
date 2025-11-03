"""Command library helpers for Tasmota bulk tooling."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from constants import COMMAND_LIBRARY

DEFAULT_COMMANDS = [command for command, _ in COMMAND_LIBRARY]


class CommandLibraryError(RuntimeError):
    """Raised when the command library cannot be read or parsed."""


@dataclass
class CommandRecord:
    name: str
    value: str
    description: str
    category: str
    metadata: dict

    def backlog_entry(self) -> str:
        value = (self.value or "").strip()
        return f"{self.name} {value}".strip()


def _normalize_command_entry(entry) -> CommandRecord | None:
    if isinstance(entry, dict):
        normalized = {str(key).lower(): value for key, value in entry.items() if isinstance(key, str)}

        def _get(*keys):
            for key in keys:
                if key in entry:
                    return entry[key]
            for key in keys:
                lower = str(key).lower()
                if lower in normalized:
                    return normalized[lower]
            return None

        name = _get("command", "name", "cmd", "keyword")
        value = _get("value", "default")
        description = _get("description", "desc", "details")
        category = _get("category", "section")
        metadata = dict(entry)
    elif isinstance(entry, (list, tuple)) and entry:
        name = entry[0]
        value = entry[1] if len(entry) > 1 else ""
        description = entry[2] if len(entry) > 2 else ""
        category = entry[3] if len(entry) > 3 else ""
        metadata = {"raw": list(entry)}
    else:
        return None

    name = str(name or "").strip()
    if not name:
        return None

    if isinstance(value, (dict, list)):
        try:
            value = json.dumps(value)
        except Exception:
            value = str(value)
    elif value is None:
        value = ""
    else:
        value = str(value)

    description = "" if description is None else str(description)
    category = "" if category is None else str(category).strip()

    return CommandRecord(name=name, value=value, description=description, category=category, metadata=metadata)


def _candidate_roots(module_path: Path) -> Iterable[Path]:
    """Yield possible root directories for bundled assets."""

    if getattr(sys, "_MEIPASS", None):
        yield Path(sys._MEIPASS)

    for parent in module_path.parents:
        yield parent


def _default_command_library_path() -> Path:
    """Return the most likely location of the bundled command library."""

    module_path = Path(__file__).resolve()
    seen: set[Path] = set()
    for root in _candidate_roots(module_path):
        if root in seen:
            continue
        seen.add(root)
        candidate = root / "assets" / "commands" / "tasmota_commands.json"
        if candidate.exists():
            return candidate

    # Fallback to the historical project layout relative to the source tree.
    if len(module_path.parents) >= 4:
        return module_path.parents[3] / "assets" / "commands" / "tasmota_commands.json"

    return Path("assets/commands/tasmota_commands.json").resolve()


def load_command_library(path: str | None = None) -> List[CommandRecord]:
    """Load command records from a JSON file (default: project root)."""
    if path is None:
        path = _default_command_library_path()
    else:
        path = Path(path)

    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise CommandLibraryError(f"Command library file not found: {path}") from exc
    except Exception as exc:
        raise CommandLibraryError(f"Failed to load command library: {exc}") from exc

    if not isinstance(data, list):
        raise CommandLibraryError("Command library JSON must contain a list of entries.")

    records: List[CommandRecord] = []
    for entry in data:
        record = _normalize_command_entry(entry)
        if record is not None:
            records.append(record)

    return records

"""Command library management for Tasmota bulk tooling.

This module handles loading and parsing command configurations from JSON files.
Commands are used to configure Tasmota devices in bulk - things like MQTT settings,
timezone, power retention, and custom rules.

The command library supports two formats:
1. Simple tuple format: ("Command Value", "Description")
2. Rich JSON format with categories, metadata, and separate command/value fields

Main Components:
    CommandRecord: Data container for a single command entry
    CommandLibraryError: Exception raised when library loading fails
    load_command_library(): Load commands from a JSON file
    extract_categories(): Get unique categories from command records

The JSON command library file (tasmota_commands.json) supports flexible field names:
    - command/name/cmd/keyword: The Tasmota command name
    - value/default: Default value for the command
    - description/desc/details: Human-readable explanation
    - category/section: Grouping for UI display

Example JSON format:
    [
        {
            "command": "TelePeriod",
            "value": "30",
            "description": "Publish telemetry every 30 seconds",
            "category": "MQTT"
        },
        {
            "command": "SetOption56",
            "value": "1",
            "description": "Scan for strongest WiFi AP on restart",
            "category": "WiFi"
        }
    ]
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple

from tasmota.constants import COMMAND_LIBRARY
from tasmota.core.utils import candidate_asset_roots

__all__ = [
    "DEFAULT_COMMANDS",
    "CommandLibraryError",
    "CommandRecord",
    "extract_categories",
    "load_command_library",
]

DEFAULT_COMMANDS = [command for command, _ in COMMAND_LIBRARY]


def extract_categories(records: Iterable["CommandRecord"]) -> Tuple[List[str], bool]:
    """Extract sorted unique category names from command records.

    This is used by both desktop and mobile UIs to populate category
    filter dropdowns. Categories are sorted case-insensitively, and
    we track whether any records lack a category (for "Uncategorized" option).

    Args:
        records: Iterable of CommandRecord objects to scan

    Returns:
        Tuple of (sorted_categories, has_uncategorized):
        - sorted_categories: List of unique category names, sorted alphabetically
        - has_uncategorized: True if any record has empty/missing category

    Example:
        >>> categories, has_empty = extract_categories(library_records)
        >>> filter_options = ["All categories"]
        >>> if has_empty:
        ...     filter_options.append("Uncategorized")
        >>> filter_options.extend(categories)
    """
    categories: set[str] = set()
    has_uncategorized = False

    for record in records:
        category = (record.category or "").strip()
        if not category:
            has_uncategorized = True
        else:
            categories.add(category)

    # Sort case-insensitively for user-friendly display
    sorted_categories = sorted(categories, key=str.lower)
    return sorted_categories, has_uncategorized


class CommandLibraryError(RuntimeError):
    """Exception raised when the command library cannot be loaded or parsed.

    This error is raised in these situations:
    - The JSON file doesn't exist at the expected path
    - The file exists but contains invalid JSON
    - The JSON is valid but isn't a list (wrong structure)
    - File permission errors prevent reading

    The error message includes the specific cause to help with debugging.

    Example:
        try:
            commands = load_command_library("my_commands.json")
        except CommandLibraryError as e:
            print(f"Failed to load commands: {e}")
            # Fall back to default commands
            commands = []
    """


@dataclass
class CommandRecord:
    """A single command entry from the command library.

    Represents one Tasmota command with its configuration and documentation.
    Used by both the desktop and mobile UIs to display command options and
    build backlog strings for bulk execution.

    Attributes:
        name: The Tasmota command name (e.g., "TelePeriod", "SetOption56").
            This is the actual command that gets sent to devices.
        value: Default/suggested value for the command (e.g., "30", "1").
            Can be empty if the command needs no arguments.
        description: Human-readable explanation of what the command does.
            Displayed in the UI to help users understand each option.
        category: Grouping label for organizing commands in the UI
            (e.g., "MQTT", "WiFi", "Power"). Can be empty.
        metadata: Raw dictionary of all fields from the JSON entry.
            Preserves any extra fields for future extensibility.

    Example:
        record = CommandRecord(
            name="TelePeriod",
            value="30",
            description="Publish telemetry every 30 seconds",
            category="MQTT",
            metadata={"source": "official"}
        )
        # Build backlog entry: "TelePeriod 30"
        entry = record.backlog_entry()
    """

    name: str
    value: str
    description: str
    category: str
    metadata: dict

    def backlog_entry(self) -> str:
        """Build a command string suitable for Tasmota backlog.

        Combines the command name and value into a single string
        that can be sent to a device or included in a Backlog command.

        Returns:
            Command string like "TelePeriod 30" or just "Restart" if no value.
        """
        value = (self.value or "").strip()
        return f"{self.name} {value}".strip()


def _normalize_command_entry(entry) -> CommandRecord | None:
    """Convert a raw JSON entry into a CommandRecord.

    Handles flexible field naming to support various JSON formats:
    - Dict with "command"/"name"/"cmd" for the command name
    - List/tuple with positional elements
    - Missing or None values are converted to empty strings

    Args:
        entry: Raw entry from JSON - can be dict, list, or tuple

    Returns:
        CommandRecord if entry is valid and has a command name, None otherwise
    """
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


def _default_command_library_path() -> Path:
    """Return the most likely location of the bundled command library."""

    module_path = Path(__file__).resolve()
    seen: set[Path] = set()
    for root in candidate_asset_roots(module_path):
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
    """Load command records from a JSON file.

    Reads a JSON file containing Tasmota commands and converts each entry
    into a CommandRecord. The file format is flexible - see module docstring
    for supported field names and structures.

    If no path is provided, the function searches for the bundled library
    file (tasmota_commands.json) in several locations:
    1. PyInstaller's temporary directory (when bundled as .exe)
    2. Parent directories of this module (development mode)
    3. assets/commands/ relative to project root

    Args:
        path: Path to a JSON file, or None to use the bundled library.

    Returns:
        List of CommandRecord objects, one per valid command in the file.
        Invalid entries (missing command name, wrong types) are silently skipped.

    Raises:
        CommandLibraryError: If the file doesn't exist, isn't valid JSON,
            or doesn't contain a list at the top level.

    Example:
        # Load bundled library
        commands = load_command_library()

        # Load custom library
        commands = load_command_library("my_commands.json")

        # Use commands
        for cmd in commands:
            print(f"{cmd.name}: {cmd.description}")
    """
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

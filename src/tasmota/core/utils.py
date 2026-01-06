"""Utility helpers shared across the GUI implementations."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

__all__ = [
    "candidate_asset_roots",
    "is_valid_ip",
    "parse_ip_range",
    "build_ip_list",
    "validate_ip_ranges",
    "safe_extract_json",
]

JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)
IP_OCTET_RE = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")


# ============================================================
# Asset Path Resolution for Bundled Applications
# ============================================================
# When this app is packaged with PyInstaller (for Windows/Linux
# distribution), all files get bundled into a single executable.
# At runtime, PyInstaller extracts files to a temporary folder
# and sets sys._MEIPASS to point to that folder.
#
# This function helps find assets (like images, JSON files) in
# both development mode (running from source) and packaged mode.
# ============================================================


def candidate_asset_roots(module_path: Path) -> Iterable[Path]:
    """Yield possible root directories for locating bundled assets.

    This is used to find files like images, JSON data, and other resources
    that may be located in different places depending on how the app runs:

    1. **Packaged mode (PyInstaller)**: Assets are extracted to a temp
       folder. We check sys._MEIPASS first since that's where PyInstaller
       puts everything when running a bundled .exe file.

    2. **Development mode**: Assets are in the project folder. We walk
       up the directory tree from the calling module to find them.

    Args:
        module_path: The Path to the Python file that needs to find assets.
                     Typically passed as Path(__file__).resolve()

    Yields:
        Path objects representing directories to search for assets.
        The caller should check each path until they find what they need.

    Example:
        >>> for root in candidate_asset_roots(Path(__file__).resolve()):
        ...     logo = root / "assets" / "images" / "logo.png"
        ...     if logo.exists():
        ...         return str(logo)
    """
    # Check PyInstaller's temporary extraction folder first.
    # sys._MEIPASS is a private attribute that only exists when running
    # from a PyInstaller bundle. In normal Python, this returns None.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        yield Path(meipass)

    # Walk up the directory tree from the module's location.
    # This finds assets during development when running from source.
    yield from module_path.parents


def is_valid_ip(ip: str) -> bool:
    """Check if a string is a valid IPv4 address."""
    match = IP_OCTET_RE.match(ip.strip())
    if not match:
        return False
    return all(0 <= int(octet) <= 255 for octet in match.groups())


def parse_ip_range(line: str) -> Tuple[bool, List[str]]:
    """Parse an IP range like '192.168.1.1-10' into individual IPs.

    Returns (success, list_of_ips). If parsing fails, returns (False, []).
    """
    if "-" not in line:
        return False, []

    try:
        prefix, tail = line.rsplit(".", 1)
        start_str, end_str = tail.split("-", 1)
        start = int(start_str)
        end = int(end_str)

        # Validate prefix has 3 valid octets
        prefix_parts = prefix.split(".")
        if len(prefix_parts) != 3:
            return False, []
        if not all(0 <= int(p) <= 255 for p in prefix_parts):
            return False, []

        # Validate range bounds
        if not (0 <= start <= 255 and 0 <= end <= 255):
            return False, []
        if start > end:
            return False, []

        ips = [f"{prefix}.{value}" for value in range(start, end + 1)]
        return True, ips
    except (ValueError, AttributeError):
        return False, []


def build_ip_list(ranges_text: str) -> List[str]:
    """Expand a multi-line set of IP ranges into individual addresses.

    Validates IP addresses and ranges, skipping invalid entries.
    This is a convenience wrapper around validate_ip_ranges() that
    discards invalid line information.
    """
    valid_ips, _ = validate_ip_ranges(ranges_text)
    return valid_ips


def validate_ip_ranges(ranges_text: str) -> Tuple[List[str], List[str]]:
    """Validate IP ranges and return both valid IPs and invalid lines.

    This function processes multi-line text containing IP addresses and
    IP ranges (like "192.168.1.1-10"), separating valid entries from
    invalid ones. Useful when you need to report parsing errors to users.

    Args:
        ranges_text: Multi-line text with one IP or range per line.
                     Empty lines are ignored.
                     Ranges use format "prefix.start-end" (e.g., "192.168.1.1-50")

    Returns:
        Tuple of (valid_ips, invalid_lines):
        - valid_ips: List of individual IP addresses that passed validation
        - invalid_lines: List of lines that couldn't be parsed

    Example:
        >>> text = '''192.168.1.1
        ... 192.168.1.10-20
        ... not-an-ip
        ... 10.0.0.1'''
        >>> valid, invalid = validate_ip_ranges(text)
        >>> len(valid)  # 1.1, 1.10 through 1.20, and 0.1 = 13 IPs
        13
        >>> invalid
        ['not-an-ip']
    """
    valid_ips: List[str] = []
    invalid_lines: List[str] = []

    for raw in (ranges_text or "").splitlines():
        line = raw.strip()
        if not line:
            continue

        if "-" in line:
            # Attempt to parse as an IP range (e.g., "192.168.1.1-50")
            success, range_ips = parse_ip_range(line)
            if success:
                valid_ips.extend(range_ips)
            else:
                invalid_lines.append(line)
        else:
            # Single IP address
            if is_valid_ip(line):
                valid_ips.append(line)
            else:
                invalid_lines.append(line)

    return valid_ips, invalid_lines


def safe_extract_json(text: str):
    """Best-effort JSON extraction used for Tasmota responses."""
    if not text:
        return None
    if "<html" in text.lower() and "{" not in text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    match = JSON_OBJECT_RE.search(text)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            return None
    return None

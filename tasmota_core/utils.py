"""Utility helpers shared across the GUI implementations."""

from __future__ import annotations

import json
import re
from typing import List

JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def build_ip_list(ranges_text: str) -> List[str]:
    """Expand a multi-line set of IP ranges into individual addresses."""
    ips: List[str] = []
    for raw in (ranges_text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if "-" in line:
            try:
                prefix, tail = line.rsplit(".", 1)
                start, end = tail.split("-", 1)
                for value in range(int(start), int(end) + 1):
                    ips.append(f"{prefix}.{value}")
            except Exception:
                # Ignore malformed ranges but continue processing.
                continue
        else:
            ips.append(line)
    return ips


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

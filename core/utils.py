"""Utility helpers shared across the project."""

from __future__ import annotations

import time
from typing import Iterable, List


def timestamp_now() -> str:
    """Return the current time formatted for log entries."""
    return time.strftime("%H:%M:%S")


def format_log_line(ip: str, name: str, message: str, tag: str = "INFO") -> str:
    """Format a log line with a timestamp and metadata."""
    nm = f" [{name}]" if name else ""
    return f"{timestamp_now()} [{tag}] [{ip}]{nm} {message}"


def build_ip_list(ranges_text: str) -> List[str]:
    """Expand a user provided list of IP ranges into concrete addresses."""
    ips: List[str] = []
    for raw in ranges_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if "-" in line:
            try:
                prefix, tail = line.rsplit(".", 1)
                a, b = tail.split("-", 1)
                start = int(a)
                end = int(b)
            except Exception:
                continue
            for i in range(start, end + 1):
                ips.append(f"{prefix}.{i}")
        else:
            ips.append(line)
    return ips


def chunked(iterable: Iterable[str], size: int) -> List[List[str]]:
    """Split an iterable into chunks of *size* items."""
    chunk: List[str] = []
    result: List[List[str]] = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) == size:
            result.append(chunk)
            chunk = []
    if chunk:
        result.append(chunk)
    return result


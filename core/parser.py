"""Parsing helpers for the Tasmota Bulk Tool."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class DeviceResult:
    IP: str
    Name: str = ""
    Version: str = ""
    Core: str = ""
    SDK: str = ""
    Hardware: str = ""
    Module: str = ""
    TemplateName: str = ""
    Hostname: str = ""
    Mac: str = ""
    MqttTopic: str = ""
    MqttClient: str = ""
    Uptime: str = ""
    RestartReason: str = ""
    FlashSize: str = ""
    FreeMem: str = ""
    RSSI: str = ""
    IPAddress: str = ""
    Gateway: str = ""
    TelePeriod: str = ""
    FriendlyName: str = ""
    OtaUrl: str = ""
    Ok: bool = False
    Error: str = ""


def safe_extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Attempt to extract JSON from a device response."""
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


def parse_status_payload(ip: str, status0: Dict[str, Any], info_mode: str = "full") -> DeviceResult:
    """Convert a raw ``Status 0`` payload into a :class:`DeviceResult`."""
    info_mode = "lite" if str(info_mode).lower().startswith("lite") else "full"
    result = DeviceResult(IP=ip)
    if not isinstance(status0, dict):
        return result

    statusfwr = status0.get("StatusFWR", {}) or {}
    status = status0.get("Status", {}) or {}
    statusnet = status0.get("StatusNET", {}) or {}
    statusmqt = status0.get("StatusMQT", {}) or {}
    statusprm = status0.get("StatusPRM", {}) or {}
    statusmem = status0.get("StatusMEM", {}) or {}
    statussts = status0.get("StatusSTS", {}) or {}

    version = statusfwr.get("Version", "")
    if not version or "tasmota" not in version.lower():
        return result

    result.Version = version
    result.Core = statusfwr.get("Core", "")
    result.SDK = statusfwr.get("SDK", "")
    result.Hardware = statusfwr.get("Hardware", "")
    result.Hostname = statusnet.get("Hostname", "")
    result.Mac = statusnet.get("Mac", "")
    result.Name = status.get("DeviceName") or result.Hostname or "(unknown)"
    result.Module = str(status.get("Module", ""))
    result.MqttTopic = status.get("Topic", "")
    result.MqttClient = statusmqt.get("MqttClient", "")

    if info_mode == "lite":
        result.Ok = True
        return result

    result.Uptime = statusprm.get("Uptime", "")
    result.RestartReason = statusfwr.get("RestartReason", "")
    result.FlashSize = statusmem.get("FlashSize", "")
    result.FreeMem = statusmem.get("FreeMem", "")
    result.RSSI = str(statussts.get("Wifi", {}).get("RSSI", ""))
    result.IPAddress = statusnet.get("IPAddress", "")
    result.Gateway = statusnet.get("Gateway", "")
    result.TelePeriod = str(status.get("TelePeriod", ""))
    fnames = status.get("FriendlyName") or []
    if isinstance(fnames, list) and fnames:
        result.FriendlyName = fnames[0]
    result.OtaUrl = statusprm.get("OtaUrl", "")

    result.Ok = True
    return result


def normalize_command_library(data: Iterable[Any]) -> List[Dict[str, Any]]:
    """Normalise entries from the command library JSON file."""
    records: List[Dict[str, Any]] = []
    for entry in data:
        record: Dict[str, Any] = {}
        raw_category = ""
        if isinstance(entry, dict):
            normalized = {}
            for key, value in entry.items():
                if isinstance(key, str):
                    normalized.setdefault(key.lower(), value)

            def _get(*candidates):
                for key in candidates:
                    if key in entry:
                        return entry[key]
                for key in candidates:
                    lower_key = key.lower() if isinstance(key, str) else key
                    if isinstance(lower_key, str) and lower_key in normalized:
                        return normalized[lower_key]
                return None

            command_name = _get("command", "name", "cmd", "keyword")
            default_value = _get("value")
            if default_value is None:
                default_value = _get("default")
            description = _get("description", "desc", "details")
            raw_category = _get("category", "section")
            record["metadata"] = dict(entry)
        elif isinstance(entry, (list, tuple)):
            command_name = entry[0] if entry else ""
            default_value = entry[1] if len(entry) > 1 else ""
            description = entry[2] if len(entry) > 2 else ""
            raw_category = entry[3] if len(entry) > 3 else ""
            record["metadata"] = {"raw": list(entry)}
        else:
            continue

        command_name = str(command_name or "").strip()
        if not command_name:
            continue

        if isinstance(default_value, (dict, list)):
            try:
                default_value = json.dumps(default_value)
            except Exception:
                default_value = str(default_value)
        elif default_value is None:
            default_value = ""
        else:
            default_value = str(default_value)

        description = "" if description is None else str(description)

        if raw_category is None:
            category = ""
        else:
            try:
                category = str(raw_category)
            except Exception:
                category = ""
            else:
                category = category.strip()
        if not category:
            category = ""

        record.update(
            {
                "name": command_name,
                "value": default_value,
                "description": description,
                "category": category,
            }
        )
        records.append(record)

    return records


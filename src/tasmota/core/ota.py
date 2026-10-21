"""Chip detection and OTA firmware URL resolution.

Tasmota reports the chip in ``StatusFWR.Hardware`` (see ``GetDeviceHardware()``
in Tasmota's ``support_esp32.ino`` / ``support_esp8266.ino``). Examples:

    ESP8266EX, ESP8285N08            -> ESP8266 family   -> tasmota.bin.gz
    ESP32-D0WD-V3 v3.1, ESP32-PICO-D4 -> classic ESP32   -> tasmota32.bin
    ESP32-S0WD v1.0, ESP32-U4WDH-S   -> single-core ESP32 -> tasmota32solo1.bin
    ESP32-C3 v0.4, ESP8685 v0.4      -> ESP32-C3         -> tasmota32c3.bin
    ESP32-S3 v0.2                    -> ESP32-S3         -> tasmota32s3.bin

Each ESP32 variant needs its own binary. The release folders on
ota.tasmota.com (``release`` and ``release-<version>``) contain
``tasmota32<variant>.bin`` for c2, c3, c5, c6, c61, s2, s3 and solo1.

Variants without an unambiguous official binary (H2 has no Wi-Fi, P4 ships
in two revisions, S31 has no release image) are refused rather than guessed.
"""

from __future__ import annotations

import re
from typing import Mapping, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

__all__ = [
    "FAMILY_ESP32",
    "FAMILY_ESP8266",
    "FAMILY_UNKNOWN",
    "chip_family",
    "esp32_variant",
    "resolve_ota_url",
]

FAMILY_ESP8266 = "ESP8266"
FAMILY_ESP32 = "ESP32"
FAMILY_UNKNOWN = "UNKNOWN"

# Longest names first so "C61" wins over "C6" and "S31" over "S3".
_ESP32_VARIANT_RE = re.compile(r"^ESP32-(C61|C2|C3|C5|C6|H2|P4|S2|S31|S3)")
# Classic ESP32 packages that only have one CPU core.
_SINGLE_CORE_PREFIXES = ("ESP32-S0WD", "ESP32-U4WDH-S")
# Variants with a matching tasmota32<variant>.bin on ota.tasmota.com.
_SUPPORTED_VARIANTS = {"c2", "c3", "c5", "c6", "c61", "s2", "s3", "solo1"}
# The stock ESP32 image name that can be swapped for a variant image.
_ESP32_STOCK_IMAGE_RE = re.compile(r"^tasmota32\.bin$", re.IGNORECASE)


def _normalize(hardware: str) -> str:
    return str(hardware or "").strip().upper()


def chip_family(hardware: str) -> str:
    """Return FAMILY_ESP8266, FAMILY_ESP32 or FAMILY_UNKNOWN for a Hardware string."""
    hw = _normalize(hardware)
    if not hw:
        return FAMILY_UNKNOWN
    # ESP8685 is an ESP32-C3 with embedded flash despite the "ESP86" prefix.
    if hw.startswith("ESP32") or hw.startswith("ESP8685"):
        return FAMILY_ESP32
    if hw.startswith("ESP8266") or hw.startswith("ESP8285"):
        return FAMILY_ESP8266
    return FAMILY_UNKNOWN


def esp32_variant(hardware: str) -> Optional[str]:
    """Return the firmware variant suffix for an ESP32-family chip.

    Returns "" for a classic dual-core ESP32 (tasmota32.bin), a suffix such
    as "c3" or "solo1" for variants, or None if the chip is not ESP32-family.
    Unsupported variants are returned as-is (e.g. "h2") so the caller can
    report them; use ``resolve_ota_url`` to get a usable URL.
    """
    hw = _normalize(hardware)
    if chip_family(hw) != FAMILY_ESP32:
        return None
    if hw.startswith("ESP8685"):
        return "c3"
    match = _ESP32_VARIANT_RE.match(hw)
    if match:
        return match.group(1).lower()
    if hw.startswith(_SINGLE_CORE_PREFIXES):
        return "solo1"
    return ""


def _with_variant_image(url: str, variant: str) -> Optional[str]:
    """Swap a stock ``tasmota32.bin`` file name for ``tasmota32<variant>.bin``."""
    parts = urlsplit(url)
    directory, _, filename = parts.path.rpartition("/")
    if not _ESP32_STOCK_IMAGE_RE.match(filename):
        return None
    new_path = f"{directory}/tasmota32{variant}.bin"
    return urlunsplit((parts.scheme, parts.netloc, new_path, parts.query, parts.fragment))


def resolve_ota_url(hardware: str, urls: Mapping[str, str]) -> Tuple[Optional[str], str]:
    """Pick the firmware URL for a device.

    Args:
        hardware: ``StatusFWR.Hardware`` reported by the device.
        urls: Mapping with "ESP8266" and "ESP32" base URLs. The ESP32 URL is
            the classic ``tasmota32.bin``; variant chips get the same folder
            with their own image name.

    Returns:
        (url, "") on success, or (None, reason) when no safe URL exists.
    """
    family = chip_family(hardware)
    if family == FAMILY_ESP8266:
        url = str(urls.get(FAMILY_ESP8266) or "").strip()
        return (url, "") if url else (None, "No ESP8266 OTA URL configured")
    if family == FAMILY_UNKNOWN:
        return None, f"Unknown chip '{hardware}', refusing to guess firmware"

    base = str(urls.get(FAMILY_ESP32) or "").strip()
    if not base:
        return None, "No ESP32 OTA URL configured"
    variant = esp32_variant(hardware) or ""
    if not variant:
        return base, ""
    if variant not in _SUPPORTED_VARIANTS:
        return None, f"No official Tasmota image for chip '{hardware}', update it manually"
    url = _with_variant_image(base, variant)
    if url is None:
        return None, (
            f"Chip '{hardware}' needs tasmota32{variant}.bin but the ESP32 URL "
            f"does not end in tasmota32.bin: {base}"
        )
    return url, ""

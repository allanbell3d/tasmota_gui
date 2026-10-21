import pytest

from tasmota.constants import OTA_URLS
from tasmota.core.ota import FAMILY_ESP32, FAMILY_ESP8266, FAMILY_UNKNOWN, chip_family, esp32_variant, resolve_ota_url

BASE = "http://ota.tasmota.com/tasmota32/release"

# Hardware strings as produced by Tasmota's GetDeviceHardwareRevision().
@pytest.mark.parametrize(
    "hardware, expected",
    [
        ("ESP8266EX", OTA_URLS["ESP8266"]),
        ("ESP8285N08", OTA_URLS["ESP8266"]),
        ("ESP32-D0WD-V3 v3.1", f"{BASE}/tasmota32.bin"),
        ("ESP32-D0WDQ6 v1.0", f"{BASE}/tasmota32.bin"),
        ("ESP32-PICO-D4 v1.0", f"{BASE}/tasmota32.bin"),
        ("ESP32-U4WDH-D v3.0", f"{BASE}/tasmota32.bin"),
        ("ESP32-S0WD v1.0", f"{BASE}/tasmota32solo1.bin"),
        ("ESP32-S0WDQ6 v1.0", f"{BASE}/tasmota32solo1.bin"),
        ("ESP32-U4WDH-S v3.0", f"{BASE}/tasmota32solo1.bin"),
        ("ESP32-C3 v0.4", f"{BASE}/tasmota32c3.bin"),
        ("ESP8685 v0.4", f"{BASE}/tasmota32c3.bin"),
        ("ESP32-C2 v1.0", f"{BASE}/tasmota32c2.bin"),
        ("ESP32-C5 v1.0", f"{BASE}/tasmota32c5.bin"),
        ("ESP32-C6FH4 v0.0", f"{BASE}/tasmota32c6.bin"),
        ("ESP32-C61 v1.0", f"{BASE}/tasmota32c61.bin"),
        ("ESP32-S2FH4 v0.0", f"{BASE}/tasmota32s2.bin"),
        ("ESP32-S3 v0.2", f"{BASE}/tasmota32s3.bin"),
        ("ESP32-S3-PICO-1 v0.2", f"{BASE}/tasmota32s3.bin"),
    ],
)
def test_resolve_default_urls(hardware, expected):
    url, problem = resolve_ota_url(hardware, OTA_URLS)
    assert problem == ""
    assert url == expected


@pytest.mark.parametrize("hardware", ["ESP32-H2 v0.1", "ESP32-P4 v1.0", "ESP32-S31 v0.0", "", "RTL8710"])
def test_refuses_unsupported_or_unknown(hardware):
    url, problem = resolve_ota_url(hardware, OTA_URLS)
    assert url is None
    assert problem


def test_pinned_release_folder_keeps_folder_for_variants():
    urls = {"ESP32": "http://ota.tasmota.com/tasmota32/release-15.0.0/tasmota32.bin", "ESP8266": OTA_URLS["ESP8266"]}
    assert resolve_ota_url("ESP32-C3 v0.4", urls)[0] == "http://ota.tasmota.com/tasmota32/release-15.0.0/tasmota32c3.bin"
    assert resolve_ota_url("ESP32-D0WD-V3", urls)[0] == urls["ESP32"]


def test_custom_image_name_is_not_rewritten_for_variants():
    urls = {"ESP32": "http://myserver/tasmota32-ir.bin", "ESP8266": OTA_URLS["ESP8266"]}
    url, problem = resolve_ota_url("ESP32-S3 v0.2", urls)
    assert url is None and "tasmota32s3.bin" in problem
    # Classic chips use a custom URL exactly as given.
    assert resolve_ota_url("ESP32-D0WD-V3", urls)[0] == "http://myserver/tasmota32-ir.bin"


def test_family_and_variant():
    assert chip_family("ESP8266EX") == FAMILY_ESP8266
    assert chip_family("ESP8685") == FAMILY_ESP32
    assert chip_family("esp32-c3") == FAMILY_ESP32
    assert chip_family("") == FAMILY_UNKNOWN
    assert esp32_variant("ESP8266EX") is None
    assert esp32_variant("ESP32-D0WD") == ""

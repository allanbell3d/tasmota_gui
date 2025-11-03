"""Shared constants for the Tasmota bulk tooling stack."""

APP_VERSION = "v0.1.4"

DEFAULT_THREADS = 100
DEFAULT_TIMEOUT = 1
DEFAULT_RETRIES = 1
DEFAULT_BACKOFF = 1.0

DEFAULT_XLSX = "tasmota_hardware_summary.xlsx"
DEFAULT_CSV = "tasmota_hardware_summary.csv"

DEFAULT_IP_RANGES = """192.168.60.10-254
192.168.62.10-254
192.168.64.10-254
192.168.66.10-254"""

OTA_URLS = {
    "ESP32": "http://ota.tasmota.com/tasmota32/release/tasmota32.bin",
    "ESP8266": "http://ota.tasmota.com/tasmota/release/tasmota.bin.gz",
}

"""Shared constants for the Tasmota bulk tooling stack."""

APP_VERSION = "v0.1.7"

APP_TITLE_SUFFIX = "AllanBell3D Tasmota Bulk Tool (Cross-Platform GUI)"

DEFAULT_THREADS = 100
DEFAULT_TIMEOUT = 1
DEFAULT_RETRIES = 1
DEFAULT_BACKOFF = 1.0

ANDROID_THREAD_DEFAULT = 20
ANDROID_THREAD_MAX = 32
DESKTOP_THREAD_MAX = 128

DEFAULT_OUTPUT_DIR_NAME = "Logs"

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

ESP_PLATFORM_COLORS = {
    "ESP8266": (0.9, 0.96, 1.0, 1),
    "ESP32": (0.9, 1.0, 0.9, 1),
    "UNKNOWN": (1, 1, 1, 1),
}

ESP_PLATFORM_TEXT_COLOR = (0, 0, 0, 1)
CHECKBOX_BLACK = (0, 0, 0, 1)
SUMMARY_HEADER_TEXT_COLOR = (1, 1, 1, 1)

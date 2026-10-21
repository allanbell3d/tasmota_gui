"""Shared constants for the Tasmota bulk tooling stack.

This module contains all configurable values used throughout the application.
Centralizing these values here makes it easy to:
- Understand what can be configured
- Change values without hunting through code
- Maintain consistency across desktop and mobile UIs

Constants are organized into logical sections:
1. Application Identity - Version and branding
2. Network Defaults - Threading, timeouts, retries
3. Platform Limits - Android vs Desktop constraints
4. File Paths - Output file names and directories
5. Default Data - IP ranges, OTA URLs
6. UI Colors - Platform colors, buttons, notifications
7. UI Layout - Row heights, spacing
8. OTA Timing - Firmware update wait times
9. Input Validation - Safe parameter bounds
10. Log Panel - Display buffer limits
11. Default Backlog Commands - empty; personal commands live in settings
12. Tasmota HTTP Command Limits - web user, command length, backlog size
"""

# =============================================================================
# Application Identity
# =============================================================================
# These identify the application in window titles, logs, and exports.
# Update APP_VERSION when releasing new versions.
# =============================================================================
APP_VERSION = "v0.3.0"
APP_TITLE_SUFFIX = "AllanBell3D Tasmota Bulk Tool (Cross-Platform GUI)"

# =============================================================================
# Network Operation Defaults
# =============================================================================
# These control how the app communicates with Tasmota devices over HTTP.
# They can be overridden by user input in the UI.
#
# THREADS: How many devices to query simultaneously
#   - Higher = faster scans, but more CPU/network load
#   - 100 is a good balance for most home/small office networks
#
# TIMEOUT: Seconds to wait for each device to respond
#   - Too low: Misses slow devices or congested networks
#   - Too high: Scan takes forever when devices are offline
#
# RETRIES: Number of attempts before marking a device as failed
#   - Helps with devices that occasionally drop packets
#
# BACKOFF: Multiplier for exponential delay between retries
#   - Prevents overwhelming struggling devices
#   - Delay before retry n (n = 1, 2, ...) = 2^(n-1) * BACKOFF seconds
# =============================================================================
DEFAULT_THREADS = 100
DEFAULT_TIMEOUT = 1
DEFAULT_RETRIES = 1
DEFAULT_BACKOFF = 1.0

# =============================================================================
# Platform-Specific Thread Limits
# =============================================================================
# Mobile devices (Android) have less RAM and CPU than desktops.
# These limits prevent the app from overwhelming mobile hardware.
#
# ANDROID_THREAD_DEFAULT: Starting value for Android
# ANDROID_THREAD_MAX: Hard cap for Android
#
# Scan time is bound by the timeout, not the CPU: roughly
# ceil(hosts / threads) * timeout. Measured (254 unresponsive hosts, 1 s
# timeout): 20 threads 13.2 s, 32 threads 8.1 s, 64 threads 4.1 s, 128
# threads 2.2 s; CPU ~0.4 s and +5 MB RSS throughout. The old Android values
# (20 / 32) dated from when every log line was a widget; the log panel now
# renders only visible rows. Lower these if a phone or access point struggles.
# DESKTOP_THREAD_MAX: Cap for the Kivy UI when previewed on a desktop
#   (the PySide6 desktop app uses MAX_THREADS below)
# =============================================================================
ANDROID_THREAD_DEFAULT = 64
ANDROID_THREAD_MAX = 128
DESKTOP_THREAD_MAX = 128

# =============================================================================
# Output File Configuration
# =============================================================================
# After scanning, results can be exported to Excel and CSV files.
# These are saved in the output directory with timestamps appended.
#
# Example: tasmota_hardware_summary_20240115_143022.xlsx
# =============================================================================
DEFAULT_OUTPUT_DIR_NAME = "Logs"
DEFAULT_XLSX = "tasmota_hardware_summary.xlsx"
DEFAULT_CSV = "tasmota_hardware_summary.csv"

# =============================================================================
# Default IP Ranges
# =============================================================================
# Neutral example shown on first start. Your own ranges are stored in the
# private settings file (see tasmota/core/settings.py) once you edit them.
#
# Format: Each line is either:
#   - Single IP: 192.168.1.100
#   - Range: 192.168.1.10-254 (scans .10 through .254)
# =============================================================================
DEFAULT_IP_RANGES = "192.168.1.10-254"

# =============================================================================
# OTA (Over-The-Air) Firmware URLs
# =============================================================================
# Official Tasmota firmware download URLs for each chip platform.
# These are the default URLs used when triggering firmware updates.
#
# ESP8266: Original ESP chips (most common in older devices)
#   - Uses .bin.gz (compressed) to fit in limited flash memory
#
# ESP32: Newer, more powerful chips
#   - Uses uncompressed .bin (ESP32 has more flash space)
#   - This is the classic ESP32 image. Variant chips (C3, S3, single-core...)
#     automatically get tasmota32<variant>.bin from the same folder; see
#     tasmota/core/ota.py.
#
# Users can override these per session (e.g. to pin a release folder such as
# .../tasmota32/release-15.0.0/tasmota32.bin). After a successful update the
# device's OtaUrl is reset to these official release defaults.
# =============================================================================
OTA_URLS = {
    "ESP32": "http://ota.tasmota.com/tasmota32/release/tasmota32.bin",
    "ESP8266": "http://ota.tasmota.com/tasmota/release/tasmota.bin.gz",
}

# =============================================================================
# UI Color Definitions
# =============================================================================
# Colors are defined as RGBA tuples: (Red, Green, Blue, Alpha)
# Values range from 0.0 (none) to 1.0 (full intensity)
# Alpha controls transparency: 0.0 = invisible, 1.0 = opaque
#
# Platform Colors:
#   - ESP8266 devices get a light blue background
#   - ESP32 devices get a light green background
#   - Unknown devices get white (neutral)
#   This helps users quickly identify device types in lists.
# =============================================================================
ESP_PLATFORM_COLORS = {
    "ESP8266": (0.9, 0.96, 1.0, 1),   # Light blue tint
    "ESP32": (0.9, 1.0, 0.9, 1),       # Light green tint
    "UNKNOWN": (1, 1, 1, 1),           # White (no tint)
}

# Text colors for device rows and headers
ESP_PLATFORM_TEXT_COLOR = (0, 0, 0, 1)        # Black text on light backgrounds
CHECKBOX_COLOR = (1, 1, 1, 1)                  # White checkboxes (visible on dark)
SUMMARY_HEADER_TEXT_COLOR = (1, 1, 1, 1)       # White header text

# Structural UI element colors
BORDER_COLOR = (0.4, 0.4, 0.4, 1)              # Medium gray borders
SEPARATOR_COLOR = (0.6, 0.6, 0.6, 1)           # Lighter gray separators
CATEGORY_LABEL_COLOR = (0.5, 0.5, 0.5, 1)      # Muted gray for category text
FALLBACK_BG_COLOR = (0.5, 0.5, 0.5, 1)         # Default gray if platform unknown

# Button state colors (for toggle buttons like platform filters)
BUTTON_DEFAULT_BG = (0.9, 0.9, 0.9, 1)         # Light gray (unselected)
BUTTON_SELECTED_BG = (0.2, 0.5, 0.9, 1)        # Blue (selected/active)

# Toast/notification message colors
TOAST_INFO_COLOR = (0.3, 0.3, 0.3, 1)          # Dark gray for info messages
TOAST_SUCCESS_COLOR = (0.1, 0.5, 0.1, 1)       # Green for success messages
TOAST_ERROR_COLOR = (0.7, 0.2, 0.2, 1)         # Red for error messages

# Row height constants (density-independent pixels - apply dp() in UI code)
# Used by RecycleView rows to maintain consistent sizing across platforms
DEVICE_ROW_HEIGHT_DP = 72   # Summary/OTA device list rows
COMMAND_ROW_HEIGHT_DP = 80  # Command library rows (slightly taller for category text)

# =============================================================================
# OTA (Over-The-Air) Update Timing Constants
# =============================================================================
# These control how long we wait for devices during firmware updates.
# OTA updates cause devices to reboot, so we need patience!
#
# The typical OTA flow:
# 1. Send "Upgrade 1" command to trigger firmware download
# 2. Wait OTA_RESTART_WAIT_SECONDS for device to download, flash, and reboot
# 3. Poll device every OTA_VERIFICATION_INTERVAL seconds
# 4. Give up after OTA_VERIFICATION_RETRIES attempts
#
# Total max wait = OTA_RESTART_WAIT_SECONDS + (RETRIES * INTERVAL)
#               = 120 + (18 * 5) = 210 seconds (~3.5 minutes)
# =============================================================================
OTA_RESTART_WAIT_SECONDS = 120      # Wait time after triggering OTA (device reboots)
OTA_VERIFICATION_RETRIES = 18       # Number of times to poll device after OTA
OTA_VERIFICATION_INTERVAL = 5       # Seconds between each verification attempt

# =============================================================================
# Input Validation Bounds
# =============================================================================
# These define safe ranges for user-configurable parameters.
# Values outside these ranges will be clamped to prevent issues.
#
# TIMEOUT: How long to wait for device HTTP responses
#   - Too low: Devices on slow networks won't respond in time
#   - Too high: Scans take forever when devices are offline
#
# RETRIES: Number of times to retry failed requests
#   - Higher = more reliable but slower
#   - Lower = faster but may miss devices with intermittent connectivity
#
# BACKOFF: Exponential backoff multiplier between retries
#   - Prevents hammering devices that are struggling to respond
#
# THREADS: Maximum concurrent HTTP requests
#   - Higher = faster scans but more CPU/memory/network usage
#   - Too high may cause router rate limiting or memory issues
# =============================================================================
MIN_TIMEOUT = 1.0       # Minimum HTTP timeout in seconds
MAX_TIMEOUT = 300.0     # Maximum HTTP timeout (5 minutes)
MIN_RETRIES = 1         # Minimum retry attempts (at least try once)
MAX_RETRIES = 10        # Maximum retry attempts
MIN_BACKOFF = 0.0       # Minimum backoff multiplier (no delay)
MAX_BACKOFF = 10.0      # Maximum backoff multiplier
MIN_THREADS = 1         # At least one worker thread
MAX_THREADS = 1000      # Reasonable upper limit for concurrent connections

# =============================================================================
# Log Panel Configuration
# =============================================================================
# Controls the scrolling log display in the mobile UI.
# Older lines are removed when the buffer fills up to prevent memory bloat.
# =============================================================================
LOG_PANEL_MAX_LINES = 1000  # Lines kept; only visible rows are rendered (RecycleView)

# =============================================================================
# Default Backlog Commands
# =============================================================================
# Commands pre-filled in the backlog editor on first start. Intentionally
# empty: personal commands (MQTT credentials, location, rules) belong in the
# private settings file, not in source code. Each entry is one Tasmota command
# string, e.g. "TelePeriod 30".
# =============================================================================
DEFAULT_BACKLOG_COMMANDS: list = []

# =============================================================================
# Tasmota HTTP Command Limits
# =============================================================================
# WEB_USERNAME: Tasmota's fixed web admin user name (WEB_USERNAME in
#   my_user_config.h). Sent with the web password when one is configured.
#
# MAX_COMMAND_LENGTH: Tasmota rejects /cm?cmnd= payloads of
#   MQTT_MAX_PACKET_SIZE (1200 bytes on default builds) or more, answering
#   {"WARNING":"Enter command cmnd="}. We stay well below that.
#
# BACKLOG_MAX_COMMANDS: Older firmware queued at most 30 Backlog entries (the
#   documented limit) and silently dropped the rest while the queue was full.
#   Current firmware appends to an unbounded queue. Longer command lists are
#   split into chunks, and the executor waits for each chunk to drain
#   (~200 ms per command, SetOption34 default) before sending the next, so
#   both keep every command in order. Commands containing ";" or starting
#   with "Reset" (dropped inside Backlog) are always sent one by one.
# =============================================================================
WEB_USERNAME = "admin"
MAX_COMMAND_LENGTH = 1000
BACKLOG_MAX_COMMANDS = 30

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
11. Command Library - Default Tasmota commands
"""

# =============================================================================
# Application Identity
# =============================================================================
# These identify the application in window titles, logs, and exports.
# Update APP_VERSION when releasing new versions.
# =============================================================================
APP_VERSION = "v0.2.2"
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
#   - Delay = (2^attempt) * BACKOFF seconds
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
# ANDROID_THREAD_DEFAULT: Starting value for Android (conservative)
# ANDROID_THREAD_MAX: Hard cap for Android to prevent crashes
# DESKTOP_THREAD_MAX: Desktop can handle more concurrent connections
# =============================================================================
ANDROID_THREAD_DEFAULT = 20
ANDROID_THREAD_MAX = 32
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
# Pre-populated IP ranges shown in the UI when the app starts.
# Users can edit these to match their network configuration.
#
# Format: Each line is either:
#   - Single IP: 192.168.1.100
#   - Range: 192.168.1.10-254 (scans .10 through .254)
#
# The ranges below are examples - users should customize for their network.
# =============================================================================
DEFAULT_IP_RANGES = """192.168.60.10-254
192.168.62.10-254
192.168.64.10-254
192.168.66.10-254"""

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
#
# Users can override these in the OTA panel if using custom firmware.
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
LOG_PANEL_MAX_LINES = 100   # Maximum log lines to keep in memory/display

# =============================================================================
# Default Command Library
# =============================================================================
# Pre-configured Tasmota commands that appear in the backlog editor.
# Each entry is a tuple: (command_string, description)
#
# These are the author's personal defaults for their smart home setup.
# Users can modify these or use the JSON command library feature for
# more extensive command sets.
#
# Command categories:
#   - MQTT: Broker connection and topic configuration
#   - Location: GPS coordinates and timezone
#   - State: Power retention and reporting precision
#   - Options: SetOption flags for various behaviors
#   - Wi-Fi: Connectivity and stability settings
#   - Logging: Debug output configuration
#   - Rules: Watchdog automation rules
#
# NOTE: The MQTT credentials below are examples - users must change these!
# =============================================================================
COMMAND_LIBRARY = [
    # --- MQTT broker configuration ---
    ("mqtthost 192.168.64.5", "Set the MQTT broker host."),
    ("mqttuser villa", "Set the MQTT username."),
    ("mqttpassword villa", "Set the MQTT password."),
    ("FullTopic %prefix%/%topic%/", "Configure the MQTT topic."),
    ("TelePeriod 20", "Publish telemetry every 20 seconds."),

    # --- Device location ---
    ("latitude 25.163853", "Set device latitude."),
    ("longitude 55.219098", "Set device longitude."),
    ("timezone +4", "Set timezone offset."),

    # --- State retention & reporting precision ---
    ("powerretain on", "Enable the MQTT retain flag for POWER status messages."),
    ("wattres 2", "Set watt resolution to 2 decimals."),
    ("EnergyRes 2", "Set energy resolution to 2 decimals."),
    ("AmpRes 2", "Set ampere resolution to 2 decimals."),
    ("switchretain off", "Disable switch retain."),
    ("buttonretain off", "Disable button retain."),
    ("poweronstate 3", "Restore last power state after reboot."),

    # --- Operational options ---
    ("SetOption56 1", "Scan for the strongest visible Wi-Fi network at restart."),
    ("SetOption57 1", "Re-scan Wi-Fi every 44 minutes to switch to a stronger AP."),
    ("SetOption59 1", "Publish tele/%topic%/STATE alongside stat/%topic%/RESULT for power commands."),
    ("SetOption65 1", "Disable fast power-cycle recovery detection."),
    ("WifiConfig 5", "Wait until the configured AP is available again without rebooting."),

    # --- Wi-Fi stability ---
    ("WifiPower 17", "Set Wi-Fi transmit power to 17 dBm (default level)."),
    ("Sleep 0", "Disable sleep mode to reduce latency and improve Wi-Fi reliability."),
    ("MqttKeepAlive 60", "Set MQTT keepalive to 60 seconds."),
    ("SetOption36 10", "Allow up to 10 rapid boot loops before progressive safe-mode recovery."),

    # --- Logging & monitoring ---
    ("SerialLog 0", "Disable serial logging to save resources."),
    ("MqttLog 1", "Log only MQTT errors."),
    ("WebLog 2", "Set web console log level to normal."),
    ("SysLog 3", "Set system log level to debug."),
    ("LogHost 192.168.64.55", "Send syslog messages to remote host."),
    ("LogPort 514", "Set remote syslog UDP port."),

    # --- Watchdog rules ---
    ("rule1 \"\"", "Clear existing Rule1 definition."),
    ("rule2 \"\"", "Clear existing Rule2 definition."),
    ("rule3 \"\"", "Clear existing Rule3 definition."),
    (
        "Rule1 on Wifi#Disconnected do RuleTimer1 120 endon on Wifi#Connected do RuleTimer1 0 endon on Rules#Timer=1 do Mem1 1 endon on Rules#Timer=1 do Var1 1 endon on Time#Minute|1 do backlog status 4 endon on StatusMEM#Heap<14 do Var1 3 endon on StatusMEM#Heap<14 do Mem1 3 endon",
        "Track Wi-Fi disconnects and low heap conditions, recording failure codes and requesting status updates.",
    ),
    (
        "Rule2 on Time#Minute|10 do backlog status 5 endon on StatusNET#IPAddress==0.0.0.0 do if (var2==0) backlog var2 1; RuleTimer2 120; endif endon on StatusNET#IPAddress$!0.0.0.0 do Var2 0 endon on Rules#Timer=2 do backlog status 5 endon on StatusNET#IPAddress==0.0.0.0 do if (var2==1) backlog mem1 2; var1 2; endif endon on Var1#State>0 do RuleTimer5 2 endon on Rules#Timer=5 do restart 1 endon",
        "Issue periodic status requests, monitor network connectivity, and trigger restarts with failure codes when IP loss persists.",
    ),
    (
        "Rule3 on System#Boot do RuleTimer3 1200 endon on Wifi#Connected do RuleTimer3 0 endon on Rules#Timer=3 do backlog mem1 5; var1 5 endon on Mqtt#Connected do event wd=%mem1% endon on event#wd do Publish watchdog/alert {\"device\":\"%topic%\",\"failure\":%value%} endon on event#wd do Mem1 0 endon",
        "Publish watchdog alerts over MQTT, clear failure memory when connectivity is restored, and fail-safe reboot path if Wi-Fi never connects within 20 minutes after boot.",
    ),

    ("rule1 1", "Enable Rule1."),
    ("rule2 1", "Enable Rule2."),
    ("rule3 1", "Enable Rule3."),
]

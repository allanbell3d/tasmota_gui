"""Shared constants for the Tasmota bulk tooling stack."""

APP_VERSION = "v0.1.9"

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
        "Rule3 on Mqtt#Connected do event wd=%mem1% endon on event#wd do Publish watchdog/alert {\"device\":\"%topic%\",\"failure\":%value%} endon on event#wd do Mem1 0 endon",
        "Publish watchdog alerts over MQTT and clear failure memory when connectivity is restored.",
    ),
    ("rule1 1", "Enable Rule1."),
    ("rule2 1", "Enable Rule2."),
    ("rule3 1", "Enable Rule3."),
]
"""Routines for discovering and managing Tasmota devices.

This module provides the core functionality for:
- Discovering Tasmota devices on a network by scanning IP ranges
- Collecting device information (firmware version, hardware, settings)
- Sending commands to multiple devices in parallel
- Performing OTA (Over-The-Air) firmware updates
- Exporting scan results to Excel/CSV files

Main Classes:
    DeviceResult: Data container for a single device's information
    BulkRunResult: Summary of a completed scan operation
    TasmotaBulkExecutor: Orchestrates the entire scan/command process

Example usage:
    executor = TasmotaBulkExecutor(
        ips=["192.168.1.100", "192.168.1.101"],
        threads=10,
        out_dir="./logs",
        timeout=5.0,
        retries=2,
        backoff=1.0,
        send_backlog=True,
        commands=["Status 0"],
    )
    result = executor.run()
    print(f"Found {len(result.results)} devices")
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, List, Optional, Sequence, Set

import httpx

__all__ = [
    "BulkRunResult",
    "CommandResult",
    "DeviceResult",
    "LogCallback",
    "ProgressCallback",
    "TasmotaBulkExecutor",
    "split_backlog",
]

from tasmota.constants import (
    BACKLOG_MAX_COMMANDS,
    DEFAULT_CSV,
    DEFAULT_XLSX,
    MAX_BACKOFF,
    MAX_COMMAND_LENGTH,
    MAX_RETRIES,
    MAX_THREADS,
    MAX_TIMEOUT,
    MIN_BACKOFF,
    MIN_RETRIES,
    MIN_THREADS,
    MIN_TIMEOUT,
    OTA_RESTART_WAIT_SECONDS,
    OTA_URLS,
    OTA_VERIFICATION_INTERVAL,
    OTA_VERIFICATION_RETRIES,
    WEB_USERNAME,
)
from .ota import INTERMEDIATE_IMAGES, firmware_image, resolve_ota_url
from .utils import safe_extract_json

LogCallback = Callable[[str, str], None]
ProgressCallback = Callable[[int, int], None]


class _CancelledError(RuntimeError):
    """Raised inside a worker when the run is cancelled mid-request."""


class _AuthError(RuntimeError):
    """Raised on HTTP 401. ``tasmota`` is True if the body is Tasmota's own
    {"WARNING":"Need user=...&password=..."} reply."""

    def __init__(self, message: str, tasmota: bool) -> None:
        super().__init__(message)
        self.tasmota = tasmota


@dataclass
class CommandResult:
    """Outcome of one HTTP command sent to a device.

    Attributes:
        ok: True if the device accepted the command (HTTP 200 and no
            WARNING / "Command":"Unknown" reply).
        data: Parsed JSON reply, or None.
        text: Raw reply body (empty on transport errors).
        error: Human-readable reason when ok is False.
    """

    ok: bool
    data: Any = None
    text: str = ""
    error: str = ""


def _reply_error(data: Any) -> str:
    """Return an error message if a parsed Tasmota reply signals failure."""
    if not isinstance(data, dict):
        return ""
    warning = data.get("WARNING")
    if isinstance(warning, str):
        return f"Device warning: {warning}"
    if str(data.get("Command", "")).lower() == "unknown":
        return "Device reports: Command Unknown"
    return ""


def split_backlog(
    commands: Sequence[str],
    *,
    max_commands: int = BACKLOG_MAX_COMMANDS,
    max_length: int = MAX_COMMAND_LENGTH,
) -> Optional[List[str]]:
    """Group commands into ``Backlog a; b; c`` strings that Tasmota accepts.

    Each chunk holds at most ``max_commands`` commands and is at most
    ``max_length`` characters long including the ``Backlog `` prefix.

    Lengths are UTF-8 bytes, which is what Tasmota measures.

    Returns None when the commands cannot be sent as Backlog without changing
    their meaning or order: a command contains ";" (Backlog would split it),
    a command starts with "Reset" (Tasmota drops Reset inside Backlog), or a
    single command is too long to share a Backlog. The caller then sends
    every command on its own, in order.
    """
    if any(";" in cmd or cmd.strip().lower().startswith("reset") for cmd in commands):
        return None

    def size(text: str) -> int:
        return len(text.encode("utf-8"))

    prefix = "Backlog "
    chunks: List[str] = []
    current: List[str] = []
    for cmd in commands:
        if size(prefix + cmd) > max_length:
            return None
        candidate = current + [cmd]
        if len(candidate) > max_commands or size(prefix + "; ".join(candidate)) > max_length:
            chunks.append(prefix + "; ".join(current))
            current = [cmd]
        else:
            current = candidate
    if current:
        chunks.append(prefix + "; ".join(current))
    return chunks


@dataclass
class DeviceResult:
    """Information collected from a single Tasmota device.

    This dataclass stores all the details retrieved from a device during
    a network scan. Fields are populated from the device's Status 0 response.

    Attributes:
        IP: The IP address used to contact this device.
        Name: Device name (from DeviceName setting).
        Version: Tasmota firmware version string (e.g., "13.1.0").
        Core: ESP core version.
        SDK: ESP SDK version.
        Hardware: Chip type (e.g., "ESP8266EX", "ESP32-D0WD").
        Module: Configured module type number.
        TemplateName: Custom template name if using a template.
        Hostname: Network hostname.
        Mac: MAC address.
        MqttTopic: MQTT topic for this device.
        MqttClient: MQTT client identifier.
        Uptime: How long the device has been running.
        RestartReason: Why the device last restarted.
        FlashSize: Flash memory size in KB.
        FreeMem: Available heap memory in KB.
        RSSI: Wi-Fi signal strength.
        IPAddress: IP address reported by the device itself.
        Gateway: Network gateway address.
        TelePeriod: Telemetry reporting interval in seconds.
        FriendlyName: Human-readable name for the device.
        OtaUrl: Currently configured OTA update URL.
        Ok: True if the device responded successfully.
        Error: Error message if the device failed to respond.
        Action: Outcome of the commands / OTA update sent in this run, e.g.
            "OTA 14.0.0 -> 15.0.1; commands accepted" or "OTA failed: ...".
            Empty for a plain scan.
    """

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
    Action: str = ""


@dataclass
class BulkRunResult:
    """Summary of a completed bulk scan operation.

    Returned by TasmotaBulkExecutor.run() after scanning completes.

    Attributes:
        results: List of DeviceResult objects for all scanned IPs.
            Includes both successful (Ok=True) and failed (Ok=False) devices.
        xlsx_path: Path to the exported Excel file (empty if export disabled).
        csv_path: Path to the exported CSV file (empty if export disabled).
        rows_written: Number of successful devices written to export files.
            This equals the count of results where Ok=True.
    """

    results: List[DeviceResult]
    xlsx_path: str
    csv_path: str
    rows_written: int


class TasmotaBulkExecutor:
    """Orchestrate concurrent discovery and command execution for Tasmota devices.

    This is the main "engine" of the application. It handles:
    1. Scanning IP ranges to find Tasmota devices on the network
    2. Collecting device information (firmware version, hardware type, settings)
    3. Sending configuration commands to multiple devices simultaneously
    4. Performing OTA (Over-The-Air) firmware updates
    5. Exporting results to Excel and CSV files

    The executor uses a thread pool to scan many devices in parallel, which
    makes large network scans much faster than checking devices one by one.

    Thread Safety:
        This class is designed to be run from a background thread while the
        UI remains responsive. The cancel() method can be called from any
        thread to stop a running operation. Progress and log callbacks are
        invoked from worker threads, so UI code must schedule updates on
        the main thread.

    Args:
        ips: List of IP addresses to scan. Can be individual IPs or
            expanded from ranges like "192.168.1.10-254".
        threads: Number of devices to contact simultaneously.
            Higher values = faster scans but more CPU/network load.
            Clamped to MIN_THREADS..MAX_THREADS for safety.
        out_dir: Directory for saving Excel/CSV exports. If None,
            no files are exported (useful for mobile or quick scans).
        timeout: Seconds to wait for each HTTP request.
            Clamped to MIN_TIMEOUT..MAX_TIMEOUT.
        retries: Number of attempts before marking a device as failed.
            Clamped to MIN_RETRIES..MAX_RETRIES.
        backoff: Multiplier for exponential delay between retries.
            Delay before retry n (n = 1, 2, ...) = 2^(n-1) * backoff seconds.
            Clamped to MIN_BACKOFF..MAX_BACKOFF.
        send_backlog: If True, send commands to selected devices.
        commands: List of Tasmota commands to send (e.g., ["TelePeriod 20"]).
        do_upgrade: If True, perform OTA firmware updates on selected devices.
        selected_ips: IPs that should receive commands and/or firmware updates.
        ota_urls: Custom OTA URLs per platform (overrides defaults).
        info_mode: "full" collects all device info, "lite" collects basics only.
        cmd_ips: Subset of selected_ips that should receive commands.
            None means "all selected_ips"; an empty collection means none.
        fw_ips: Subset of selected_ips that should receive firmware updates.
            None means "all selected_ips"; an empty collection means none.
        web_password: Tasmota web admin password (WebPassword). Sent as the
            documented ``user=admin&password=...`` query parameters when set.
        progress_callback: Called with (done, total) as devices complete.
        log_callback: Called with (message, tag) for logging events.
        transport: Optional httpx transport (tests use httpx.MockTransport).

    Example:
        # Create executor for a subnet scan
        executor = TasmotaBulkExecutor(
            ips=["192.168.1.100", "192.168.1.101", "192.168.1.102"],
            threads=20,
            out_dir="./logs",
            timeout=3.0,
            retries=2,
            backoff=1.0,
            send_backlog=True,
            commands=["TelePeriod 30", "SetOption56 1"],
            selected_ips=["192.168.1.100"],  # Only send commands to this device
        )

        # Run synchronously
        result = executor.run()
        print(f"Found {len([r for r in result.results if r.Ok])} devices")

        # Or run asynchronously
        result = await executor.run_async()
    """

    def __init__(
        self,
        ips: Sequence[str],
        threads: int,
        out_dir: Optional[str],
        timeout: float,
        retries: int,
        backoff: float,
        send_backlog: bool,
        commands: Sequence[str],
        do_upgrade: bool = False,
        *,
        selected_ips: Optional[Iterable[str]] = None,
        ota_urls: Optional[dict] = None,
        info_mode: str = "full",
        cmd_ips: Optional[Iterable[str]] = None,
        fw_ips: Optional[Iterable[str]] = None,
        web_password: str = "",
        progress_callback: Optional[ProgressCallback] = None,
        log_callback: Optional[LogCallback] = None,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self.ips = list(ips)
        # Clamp user-configurable values to safe ranges (see constants.py for docs)
        self.threads = max(MIN_THREADS, min(int(threads), MAX_THREADS))
        self.export_results = out_dir is not None
        if self.export_results:
            self.out_dir = out_dir or os.getcwd()
            self._timestamp_suffix = time.strftime("%Y%m%d_%H%M%S")
            timestamped_xlsx = self._with_timestamp(DEFAULT_XLSX)
            timestamped_csv = self._with_timestamp(DEFAULT_CSV)
            self.xlsx_path = os.path.join(self.out_dir, timestamped_xlsx)
            self.csv_path = os.path.join(self.out_dir, timestamped_csv)
        else:
            self.out_dir = None
            self.xlsx_path = ""
            self.csv_path = ""
            self._timestamp_suffix = ""
        self.timeout = max(MIN_TIMEOUT, min(float(timeout), MAX_TIMEOUT))
        self.retries = max(MIN_RETRIES, min(int(retries), MAX_RETRIES))
        self.backoff = max(MIN_BACKOFF, min(float(backoff), MAX_BACKOFF))
        self.send_backlog = bool(send_backlog)
        self.commands = [str(cmd).strip() for cmd in commands if str(cmd).strip()]
        self.do_upgrade = bool(do_upgrade)
        self.selected_ips: Set[str] = set(selected_ips or [])
        self.cmd_ips: Set[str] = set(self.selected_ips if cmd_ips is None else cmd_ips)
        self.fw_ips: Set[str] = set(self.selected_ips if fw_ips is None else fw_ips)
        self.web_password = str(web_password or "")
        self._transport = transport
        # IPs that answered 401 with Tasmota's own "Need user=..." reply. Only
        # these receive the web password, never every host in the range.
        self._auth_ips: Set[str] = set()
        self._auth_lock = threading.Lock()
        # Pause per queued command before sending the next Backlog chunk.
        # Tasmota runs Backlog entries 200 ms apart (SetOption34 default);
        # old firmware drops entries beyond 30 while the queue is full.
        self.backlog_seconds_per_command = 0.25
        self.backlog_chunk_margin = 1.0
        # OTA timing, kept on the instance so tests can shorten it.
        self.ota_restart_wait = OTA_RESTART_WAIT_SECONDS
        self.ota_verification_retries = OTA_VERIFICATION_RETRIES
        self.ota_verification_interval = OTA_VERIFICATION_INTERVAL
        self.ota_urls = dict(OTA_URLS)
        if ota_urls:
            self.ota_urls.update({key: value for key, value in ota_urls.items() if value})
        normalized_mode = str(info_mode or "full").lower()
        self.info_mode = "lite" if normalized_mode.startswith("lite") else "full"
        self.progress_callback = progress_callback
        self.log_callback = log_callback
        self._cancel_event = threading.Event()
        self._cancel_lock = threading.Lock()
        self._was_cancelled = False
        self._progress_lock = threading.Lock()
        self._last_progress = 0

    # ------------------------------------------------------------------
    # Thread-safe property for cancellation state
    # ------------------------------------------------------------------
    @property
    def was_cancelled(self) -> bool:
        with self._cancel_lock:
            return self._was_cancelled

    @was_cancelled.setter
    def was_cancelled(self, value: bool) -> None:
        with self._cancel_lock:
            self._was_cancelled = value

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _with_timestamp(self, filename: str, *, extra_suffix: str = "") -> str:
        suffix = self._timestamp_suffix or time.strftime("%Y%m%d_%H%M%S")
        path = Path(filename)
        if not path.suffix:
            return f"{filename}_{suffix}"
        extra = f"_{extra_suffix}" if extra_suffix else ""
        return f"{path.stem}_{suffix}{extra}{path.suffix}"

    def _log(self, ip: str, name: str, message: str, tag: str = "INFO") -> None:
        if self.log_callback is None:
            return
        timestamp = time.strftime("%H:%M:%S")
        device_name = f" [{name}]" if name else ""
        line = f"{timestamp} [{tag}] [{ip}]{device_name} {message}"
        try:
            self.log_callback(line, tag)
        except Exception:
            pass  # Callback failure should not kill worker thread

    def _emit_progress(self, done: int, total: int) -> None:
        """Emit progress update, ensuring progress never goes backwards."""
        if self.progress_callback is None:
            return
        with self._progress_lock:
            # Only emit if progress increased (prevents backwards progress)
            if done < self._last_progress:
                return
            self._last_progress = done
        try:
            self.progress_callback(done, total)
        except Exception:
            pass  # Callback failure should not kill worker thread

    def _interruptible_sleep(self, seconds: float) -> bool:
        """Sleep up to ``seconds``, waking immediately on cancel.

        Returns:
            True if cancelled during sleep, False if sleep completed normally.
        """
        if seconds <= 0:
            return self._cancel_event.is_set()
        return self._cancel_event.wait(seconds)

    def cancel(self) -> None:
        """Signal that the executor should cancel the current run."""

        self.was_cancelled = True
        self._cancel_event.set()

    def _redact(self, text: str) -> str:
        """Remove the web password from exception text that may reach logs."""
        if not self.web_password or not text:
            return text
        for secret in {self.web_password, str(httpx.QueryParams({"p": self.web_password}))[2:]}:
            if secret:
                text = text.replace(secret, "***")
        return text

    def _get(self, client: httpx.Client, url: str, params: dict, *, idempotent: bool) -> httpx.Response:
        """GET with retries.

        Connection failures are always retried (the request never reached the
        device). Other failures (read timeout, broken reply) are retried only
        for read-only queries: a command might already have run.
        """
        last_error = ""
        for attempt in range(1, self.retries + 1):
            if self._cancel_event.is_set():
                raise _CancelledError("Cancelled")
            try:
                response = client.get(url, params=params, timeout=self.timeout)
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                last_error = self._redact(str(exc)) or type(exc).__name__
            except Exception as exc:  # pragma: no cover - network errors vary
                last_error = self._redact(str(exc)) or type(exc).__name__
                if not idempotent:
                    raise RuntimeError(f"{last_error} (not retried, the device may have run it)") from None
            else:
                if response.status_code == 200:
                    return response
                if response.status_code == 401:
                    # Retrying will not fix a wrong or missing password.
                    reply = safe_extract_json(response.text)
                    warning = reply.get("WARNING", "") if isinstance(reply, dict) else ""
                    raise _AuthError("HTTP 401", tasmota=str(warning).startswith("Need user"))
                last_error = f"HTTP {response.status_code}"
            if attempt < self.retries:
                if self._interruptible_sleep((2 ** (attempt - 1)) * self.backoff):
                    raise _CancelledError("Cancelled")
        raise RuntimeError(last_error)

    @staticmethod
    def _is_read_only(command: str) -> bool:
        return command.strip().lower() in ("status 0", "status 5", "template")

    def _send_cmd(self, client: httpx.Client, ip: str, command: str) -> CommandResult:
        """Send one command via Tasmota's ``/cm`` endpoint. Never raises.

        The web password is only sent after the device itself asked for it
        with a Tasmota 401 reply, so other hosts in a scanned range never
        see it.
        """
        url = f"http://{ip}/cm"
        idempotent = self._is_read_only(command)
        with self._auth_lock:
            use_auth = ip in self._auth_ips
        for _ in range(2):
            params = {"cmnd": command}
            if use_auth:
                params = {"user": WEB_USERNAME, "password": self.web_password, "cmnd": command}
            try:
                response = self._get(client, url, params, idempotent=idempotent)
            except _AuthError as exc:
                if not exc.tasmota:
                    return CommandResult(ok=False, error="HTTP 401 (not a Tasmota device?)")
                if use_auth:
                    return CommandResult(ok=False, error="HTTP 401 (wrong web password)")
                if not self.web_password:
                    return CommandResult(ok=False, error="HTTP 401 (device needs a web password)")
                with self._auth_lock:
                    self._auth_ips.add(ip)
                use_auth = True
                continue
            except Exception as exc:
                return CommandResult(ok=False, error=self._redact(str(exc)))
            data = safe_extract_json(response.text)
            error = _reply_error(data)
            return CommandResult(ok=not error, data=data, text=response.text, error=error)
        return CommandResult(ok=False, error="HTTP 401")  # pragma: no cover - loop always returns

    def _send_backlog_or_commands(
        self,
        client: httpx.Client,
        ip: str,
        name: str,
        *,
        after_upgrade: bool = False,
    ) -> bool:
        """Send the configured commands. Returns True if all were accepted."""
        if not self.commands:
            return True

        context = " after upgrade" if after_upgrade else ""
        chunks = split_backlog(self.commands)
        if chunks is None:
            # Sequential single commands keep the order exactly: each HTTP
            # request runs to completion before the next one is sent.
            self._log(
                ip,
                name,
                f"Sending {len(self.commands)} commands individually{context} (contains ';', Reset or a long command)",
                tag="CMD",
            )
            requests = list(self.commands)
        else:
            plural = "s" if len(chunks) > 1 else ""
            self._log(
                ip, name, f"Sending backlog{context} ({len(self.commands)} commands, {len(chunks)} part{plural})", tag="CMD"
            )
            requests = chunks

        all_ok = True
        for index, request in enumerate(requests):
            if self._cancel_event.is_set():
                self._log(ip, name, "Command sending cancelled", tag="WARN")
                return False
            if chunks is None:
                self._log(ip, name, f"Command: {request}", tag="CMD")
            elif index > 0:
                # Let the previous chunk drain before queueing the next one.
                queued = requests[index - 1].count("; ") + 1
                pause = queued * self.backlog_seconds_per_command + self.backlog_chunk_margin
                if self._interruptible_sleep(pause):
                    self._log(ip, name, "Command sending cancelled", tag="WARN")
                    return False
            result = self._send_cmd(client, ip, request)
            if not result.ok:
                all_ok = False
                self._log(ip, name, f"Command failed ({result.error}): {request[:80]}", tag="ERROR")
        if all_ok:
            self._log(ip, name, f"Commands accepted{context}", tag="CMD")
        return all_ok

    def _collect_info_for_ip(self, client: httpx.Client, ip: str) -> DeviceResult:
        result = DeviceResult(IP=ip)
        reply = self._send_cmd(client, ip, "Status 0")
        if not reply.ok:
            result.Error = reply.error or "No response"
            return result

        status0 = reply.data
        if not isinstance(status0, dict):
            result.Error = "Reply is not JSON (not a Tasmota device?)"
            return result
        try:
            return self._parse_status(client, ip, status0, result)
        except (AttributeError, TypeError, ValueError) as exc:
            # Malformed reply (e.g. while a device is rebooting) - not fatal.
            return DeviceResult(IP=ip, Error=f"Unexpected Status 0 reply ({type(exc).__name__})")

    def _parse_status(self, client: httpx.Client, ip: str, status0: dict, result: DeviceResult) -> DeviceResult:
        statusfwr = status0.get("StatusFWR", {}) or {}
        status = status0.get("Status", {}) or {}
        statusnet = status0.get("StatusNET", {}) or {}
        statusmqt = status0.get("StatusMQT", {}) or {}
        statusprm = status0.get("StatusPRM", {}) or {}
        statusmem = status0.get("StatusMEM", {}) or {}
        statussts = status0.get("StatusSTS", {}) or {}

        # Version is "<x.y.z>(<sha or release>-<image>)", e.g.
        # "15.0.1(release-sensors)"; the image name need not contain
        # "tasmota", so identify Tasmota by the Status 0 structure instead.
        version = str(statusfwr.get("Version", "") or "") if isinstance(statusfwr, dict) else ""
        if not version or not isinstance(status, dict) or not status:
            result.Error = "Not a Tasmota device"
            return result

        result.Version = version
        result.Core = statusfwr.get("Core", "")
        result.SDK = statusfwr.get("SDK", "")
        result.Hardware = str(statusfwr.get("Hardware", "") or "")
        result.Hostname = statusnet.get("Hostname", "")
        result.Mac = statusnet.get("Mac", "")
        result.Name = status.get("DeviceName") or result.Hostname or "(unknown)"
        result.Module = str(status.get("Module", ""))
        result.MqttTopic = status.get("Topic", "")
        result.MqttClient = statusmqt.get("MqttClient", "")
        result.TemplateName = ""

        if self.info_mode == "lite":
            result.Ok = True
            return result

        result.Uptime = statusprm.get("Uptime", "")
        result.RestartReason = statusfwr.get("RestartReason", "")
        result.FlashSize = statusmem.get("FlashSize", "")
        result.FreeMem = statusmem.get("FreeMem", "")
        result.RSSI = str((statussts.get("Wifi", {}) or {}).get("RSSI", ""))
        result.IPAddress = statusnet.get("IPAddress", "")
        result.Gateway = statusnet.get("Gateway", "")
        result.TelePeriod = str(status.get("TelePeriod", ""))
        fnames = status.get("FriendlyName") or []
        if isinstance(fnames, list) and fnames:
            result.FriendlyName = fnames[0]
        result.OtaUrl = statusprm.get("OtaUrl", "")

        # Status 5 / Template are optional - device info is valid without them.
        status5 = self._send_cmd(client, ip, "Status 5").data
        if isinstance(status5, dict):
            cfg = status5.get("StatusCFG") or status5.get("Status5") or {}
            template = cfg.get("Template") if isinstance(cfg, dict) else None
            if isinstance(template, dict):
                result.TemplateName = (template.get("NAME") or template.get("Name") or "").strip()
            elif isinstance(template, str):
                try:
                    template_json = json.loads(template)
                    if isinstance(template_json, dict):
                        result.TemplateName = (template_json.get("NAME") or template_json.get("Name") or "").strip()
                except Exception:
                    # JSON parsing failed - use raw string as fallback
                    result.TemplateName = template.strip()

        if not result.TemplateName:
            template = self._send_cmd(client, ip, "Template").data
            if isinstance(template, dict):
                result.TemplateName = (template.get("NAME") or template.get("Name") or "").strip()

        result.Ok = True
        return result

    def _set_ota_url(self, client: httpx.Client, ip: str, url: str) -> str:
        """Set OtaUrl and confirm the device stored it. Returns an error or ""."""
        reply = self._send_cmd(client, ip, f"OtaUrl {url}")
        if not reply.ok:
            return reply.error
        stored = reply.data.get("OtaUrl") if isinstance(reply.data, dict) else None
        if stored != url:
            # Tasmota keeps the old value when the text does not fit.
            return f"device kept OtaUrl {stored!r}"
        return ""

    def _restore_default_ota_url(self, client: httpx.Client, ip: str, name: str, hardware: str) -> None:
        # Point the device back at the official release so later updates
        # are not pinned to a one-off URL used for this run.
        default_url, _ = resolve_ota_url(hardware, OTA_URLS)
        if not default_url:
            return
        error = self._set_ota_url(client, ip, default_url)
        if error:
            self._log(ip, name, f"Could not re-apply official OTA URL: {error}", tag="WARN")
        else:
            self._log(ip, name, f"Re-applied official OTA URL: {default_url}", tag="OTA")

    def _upgrade_device(self, client: httpx.Client, ip: str, info: DeviceResult):
        """Run one OTA update.

        Returns (online, action, new_info): ``online`` is True if the device
        came back on a final (not minimal/safeboot) image, ``action`` is a
        short outcome for DeviceResult.Action, ``new_info`` is the device
        info read after the update (or None).
        """
        name = info.Name
        hardware = info.Hardware
        ota_url, problem = resolve_ota_url(hardware, self.ota_urls, info.Version)
        if ota_url is None:
            self._log(ip, name, f"OTA skipped: {problem}", tag="ERROR")
            return False, f"OTA skipped: {problem}", None

        self._log(ip, name, f"Sending OTA upgrade ({hardware}): {ota_url}", tag="OTA")
        error = self._set_ota_url(client, ip, ota_url)
        if error:
            self._log(ip, name, f"OTA aborted, OtaUrl not accepted: {error}", tag="ERROR")
            return False, f"OTA aborted: OtaUrl not accepted ({error})", None
        reply = self._send_cmd(client, ip, "Upgrade 1")
        if not reply.ok:
            self._log(ip, name, f"OTA aborted, Upgrade 1 not accepted: {reply.error}", tag="ERROR")
            self._restore_default_ota_url(client, ip, name, hardware)
            return False, f"OTA aborted: Upgrade 1 not accepted ({reply.error})", None
        upgrade_reply = reply.data.get("Upgrade") if isinstance(reply.data, dict) else None
        if upgrade_reply:
            self._log(ip, name, f"Device replied: {upgrade_reply}", tag="OTA")

        pinned_note = f"OtaUrl left at {ota_url} because the device may still be updating"
        self._log(ip, name, f"Waiting {self.ota_restart_wait}s for OTA process (cancellable)...", tag="OTA")
        if self._interruptible_sleep(self.ota_restart_wait):
            self._log(ip, name, f"OTA wait cancelled by user; {pinned_note}", tag="WARN")
            return False, "OTA cancelled while the device was updating", None
        self._log(ip, name, "Sending Restart 1", tag="OTA")
        self._send_cmd(client, ip, "Restart 1")

        for _ in range(self.ota_verification_retries):
            if self._interruptible_sleep(max(1, self.ota_verification_interval)):
                self._log(ip, name, f"OTA verification cancelled by user; {pinned_note}", tag="WARN")
                return False, "OTA cancelled during verification", None
            result = self._collect_info_for_ip(client, ip)
            if not result.Ok:
                continue  # Device not yet online after OTA - retry
            image = firmware_image(result.Version)
            if image in INTERMEDIATE_IMAGES:
                # ESP8266 two-step update: minimal fetches the final image next.
                self._log(ip, name, f"Device is on the {image} image, waiting for the final firmware", tag="OTA")
                continue
            if result.Version == info.Version:
                action = f"OTA: firmware unchanged ({result.Version})"
                self._log(
                    ip,
                    name,
                    f"Device online but firmware unchanged ({result.Version}); the update may not have applied",
                    tag="WARN",
                )
            else:
                action = f"OTA {info.Version} -> {result.Version}"
                self._log(ip, name, f"Firmware updated: {info.Version} -> {result.Version}", tag="OTA")
            self._restore_default_ota_url(client, ip, name, hardware)
            return True, action, result
        self._log(ip, name, f"Device did not come back online after OTA; {pinned_note}", tag="ERROR")
        return False, "OTA failed: device did not come back online", None

    def _handle_ip(self, client: httpx.Client, ip: str) -> DeviceResult:
        if self._cancel_event.is_set():
            return DeviceResult(IP=ip, Ok=False, Error="Cancelled")
        try:
            info = self._collect_info_for_ip(client, ip)
            if not info.Ok:
                self._log(ip, info.Name, f"No response ({info.Error})", tag="ERROR")
                return info
            self._log(ip, info.Name, "Info OK", tag="INFO")
            if ip not in self.selected_ips:
                return info

            actions: List[str] = []
            wants_commands = self.send_backlog and ip in self.cmd_ips and bool(self.commands)
            online = True
            if self.do_upgrade and ip in self.fw_ips:
                online, action, new_info = self._upgrade_device(client, ip, info)
                actions.append(action)
                if new_info is not None:
                    new_info.Name = new_info.Name or info.Name
                    info = new_info
            if wants_commands:
                if online:
                    ok = self._send_backlog_or_commands(client, ip, info.Name, after_upgrade=self.do_upgrade and ip in self.fw_ips)
                    actions.append("commands accepted" if ok else "commands failed (see log)")
                else:
                    actions.append("commands not sent")
            info.Action = "; ".join(actions)
            return info
        except Exception as exc:
            message = self._redact(str(exc))
            self._log(ip, "", f"FAIL {message}", tag="ERROR")
            return DeviceResult(IP=ip, Ok=False, Error=message)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def _run_sync(self) -> BulkRunResult:
        """Execute the bulk scan operation synchronously.

        This is the main workhorse method that:
        1. Scans all IPs in parallel using a thread pool
        2. Collects device information from responding devices
        3. Optionally sends commands and/or performs firmware updates
        4. Exports results to Excel/CSV files

        Returns:
            BulkRunResult with all device results and export file paths.
        """
        total = len(self.ips)
        self._last_progress = 0  # Reset progress tracker for new run
        self._emit_progress(0, total)

        # ----------------------------------------------------------------
        # PHASE 1: Parallel Device Discovery
        # ----------------------------------------------------------------
        # We use a thread pool to contact many devices simultaneously.
        # Each thread handles one IP: connect → query → optionally send commands.
        # This is much faster than checking devices one by one.
        # ----------------------------------------------------------------
        results: List[DeviceResult] = []
        if total == 0:
            self._log("-", "", "No IP addresses provided", tag="WARN")
        else:
            # Configure HTTP client with connection pooling.
            # max_connections limits how many sockets we open at once.
            # This prevents overwhelming the network or running out of file descriptors.
            limits = httpx.Limits(
                max_connections=self.threads,
                max_keepalive_connections=self.threads,
            )
            timeout = httpx.Timeout(self.timeout)

            # The 'with' blocks ensure proper cleanup: sockets are closed
            # and threads are terminated even if an error occurs.
            # trust_env=False: never route LAN device traffic (and the web
            # password) through proxies configured in the environment.
            with httpx.Client(limits=limits, timeout=timeout, transport=self._transport, trust_env=False) as client:
                with ThreadPoolExecutor(max_workers=self.threads) as executor:
                    # Submit all IPs for parallel processing.
                    # future_map lets us look up which IP each future belongs to.
                    future_map = {executor.submit(self._handle_ip, client, ip): ip for ip in self.ips}
                    completed = 0

                    # Process results as they complete (not in submission order).
                    # This lets us update progress as soon as any device responds.
                    for future in as_completed(future_map):
                        # Check for cancellation before processing each result.
                        # User can cancel from the UI at any time.
                        if self._cancel_event.is_set():
                            self.was_cancelled = True
                            for pending_future in future_map:
                                pending_future.cancel()
                            break

                        ip = future_map[future]
                        try:
                            device_result = future.result()
                        except Exception as exc:  # pragma: no cover - safety net
                            # Catch any unexpected errors that escaped _handle_ip
                            message = self._redact(str(exc))
                            self._log(ip, "", f"FAIL {message}", tag="ERROR")
                            device_result = DeviceResult(IP=ip, Ok=False, Error=message)

                        results.append(device_result)
                        completed += 1
                        self._emit_progress(completed, total)

                        # Check again after processing - cancellation may have
                        # been requested while we were handling the result.
                        if self._cancel_event.is_set():
                            self.was_cancelled = True
                            for pending_future in future_map:
                                pending_future.cancel()
                            break

        # ----------------------------------------------------------------
        # PHASE 2: Prepare Export Data
        # ----------------------------------------------------------------
        # Convert successful DeviceResult objects into dictionaries
        # suitable for DataFrame creation. Failed devices are skipped.
        # ----------------------------------------------------------------
        rows = []
        for device in results:
            if not device.Ok:
                continue
            base = {
                "Name": device.Name,
                "IP": device.IP,
                "Version": device.Version,
                "Core": device.Core,
                "SDK": device.SDK,
                "Hardware": device.Hardware,
                "Module": device.Module,
                "TemplateName": device.TemplateName,
                "Hostname": device.Hostname,
                "Mac": device.Mac,
                "MqttTopic": device.MqttTopic,
                "MqttClient": device.MqttClient,
            }
            if self.info_mode == "full":
                base.update(
                    {
                        "Uptime": device.Uptime,
                        "RestartReason": device.RestartReason,
                        "FlashSize": device.FlashSize,
                        "FreeMem": device.FreeMem,
                        "RSSI": device.RSSI,
                        "IPAddress": device.IPAddress,
                        "Gateway": device.Gateway,
                        "TelePeriod": device.TelePeriod,
                        "FriendlyName": device.FriendlyName,
                        "OtaUrl": device.OtaUrl,
                    }
                )
            if any(d.Action for d in results):
                base["Action"] = device.Action
            rows.append(base)

        # ----------------------------------------------------------------
        # PHASE 3: Export to Files
        # ----------------------------------------------------------------
        # Write results to Excel and CSV files for offline analysis.
        # Pandas is optional - mobile builds may not include it.
        # If the file is locked (open in Excel), we write to an alternate path.
        # ----------------------------------------------------------------
        rows_written = 0
        if rows:
            rows_written = len(rows)
            if self.export_results:
                # Pandas is imported dynamically because:
                # 1. It's optional (mobile builds may skip it for size)
                # 2. Import is slow, so we defer until actually needed
                pandas_module = None
                try:
                    import pandas as pandas_module  # type: ignore[import-not-found]
                except ModuleNotFoundError:
                    self._log("-", "", "Pandas not available, skipping export", tag="WARN")
                except ImportError as exc:
                    self._log("-", "", f"Pandas import error ({exc}), skipping export", tag="WARN")

                if pandas_module is not None:
                    # Sort by device name for easier reading.
                    # Case-insensitive sort puts "Kitchen" and "kitchen" together.
                    df = pandas_module.DataFrame(rows).sort_values(
                        by="Name", key=lambda column: column.str.lower()
                    )

                    # Write Excel file (requires openpyxl package)
                    try:
                        df.to_excel(self.xlsx_path, index=False, engine="openpyxl")
                        self._log("-", "", f"Excel written {self.xlsx_path}", tag="INFO")
                    except PermissionError:
                        # File might be open in Excel - write to alternate path
                        # so the user doesn't lose their data
                        alt_xlsx = os.path.join(
                            self.out_dir,
                            self._with_timestamp(DEFAULT_XLSX, extra_suffix="alt"),
                        )
                        df.to_excel(alt_xlsx, index=False, engine="openpyxl")
                        self._log("-", "", f"[WARN] Excel locked, wrote {alt_xlsx}", tag="WARN")
                        self.xlsx_path = alt_xlsx

                    # Write CSV file (no extra dependencies needed)
                    # CSV is useful for importing into other tools or scripts.
                    try:
                        df.to_csv(self.csv_path, index=False)
                        self._log("-", "", f"CSV written   {self.csv_path}", tag="INFO")
                    except PermissionError:
                        alt_csv = os.path.join(
                            self.out_dir,
                            self._with_timestamp(DEFAULT_CSV, extra_suffix="alt"),
                        )
                        df.to_csv(alt_csv, index=False)
                        self._log("-", "", f"[WARN] CSV locked, wrote {alt_csv}", tag="WARN")
                        self.csv_path = alt_csv
                    rows_written = len(df.index)
        else:
            self._log("-", "", "No successful device responses", tag="WARN")

        return BulkRunResult(results=results, xlsx_path=self.xlsx_path, csv_path=self.csv_path, rows_written=rows_written)

    async def run_async(self) -> BulkRunResult:
        """Run the executor in a background thread, returning when complete."""

        return await asyncio.to_thread(self._run_sync)

    def run(self) -> BulkRunResult:
        """Run the executor synchronously."""

        return self._run_sync()

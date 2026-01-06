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
from typing import Callable, Iterable, List, Optional, Sequence, Set

import httpx

__all__ = [
    "DeviceResult",
    "BulkRunResult",
    "TasmotaBulkExecutor",
    "LogCallback",
    "ProgressCallback",
]

from tasmota.constants import (
    DEFAULT_CSV,
    DEFAULT_XLSX,
    MAX_BACKOFF,
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
)
from .utils import safe_extract_json

LogCallback = Callable[[str, str], None]
ProgressCallback = Callable[[int, int], None]


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
            Delay = (2^attempt) * backoff seconds.
            Clamped to MIN_BACKOFF..MAX_BACKOFF.
        send_backlog: If True, send commands to selected devices.
        commands: List of Tasmota commands to send (e.g., ["TelePeriod 20"]).
        do_upgrade: If True, perform OTA firmware updates on selected devices.
        selected_ips: IPs that should receive commands and/or firmware updates.
        ota_urls: Custom OTA URLs per platform (overrides defaults).
        info_mode: "full" collects all device info, "lite" collects basics only.
        cmd_ips: Subset of selected_ips that should receive commands.
        fw_ips: Subset of selected_ips that should receive firmware updates.
        progress_callback: Called with (done, total) as devices complete.
        log_callback: Called with (message, tag) for logging events.

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
        progress_callback: Optional[ProgressCallback] = None,
        log_callback: Optional[LogCallback] = None,
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
        self.cmd_ips: Set[str] = set(cmd_ips or self.selected_ips)
        self.fw_ips: Set[str] = set(fw_ips or self.selected_ips)
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

    def _interruptible_sleep(self, seconds: float, interval: float = 1.0) -> bool:
        """Sleep for specified seconds, checking cancel event periodically.

        Args:
            seconds: Total time to sleep.
            interval: How often to check for cancellation (default 1s).

        Returns:
            True if cancelled during sleep, False if sleep completed normally.
        """
        elapsed = 0.0
        while elapsed < seconds:
            if self._cancel_event.is_set():
                return True
            sleep_time = min(interval, seconds - elapsed)
            time.sleep(sleep_time)
            elapsed += sleep_time
        return False

    def cancel(self) -> None:
        """Signal that the executor should cancel the current run."""

        self.was_cancelled = True
        self._cancel_event.set()

    def _get(self, client: httpx.Client, url: str) -> httpx.Response:
        last_error = ""
        for attempt in range(1, self.retries + 1):
            try:
                response = client.get(url, timeout=self.timeout)
                if response.status_code == 200:
                    return response
                last_error = f"HTTP {response.status_code}"
            except Exception as exc:  # pragma: no cover - network errors vary
                last_error = str(exc)
            if attempt < self.retries:
                time.sleep((2 ** (attempt - 1)) * self.backoff)
        raise RuntimeError(last_error)

    def _send_cmd(
        self,
        client: httpx.Client,
        ip: str,
        command: str,
        *,
        expect_json: bool = True,
    ):
        params = httpx.QueryParams({"cmnd": command})
        url = f"http://{ip}/cm?{params}"
        try:
            response = self._get(client, url)
            if expect_json:
                return (safe_extract_json(response.text), response.text)
            return (None, response.text)
        except Exception as exc:
            return (None, str(exc))

    def _send_backlog_or_commands(
        self,
        client: httpx.Client,
        ip: str,
        name: str,
        *,
        after_upgrade: bool = False,
    ) -> None:
        if not self.commands:
            return

        contains_semicolon = any(";" in cmd for cmd in self.commands)
        if contains_semicolon:
            context = " after upgrade" if after_upgrade else ""
            self._log(
                ip,
                name,
                f"Sending commands individually{context} (semicolons detected)",
                tag="CMD",
            )
            for command in self.commands:
                self._log(ip, name, f"Command: {command}", tag="CMD")
                self._send_cmd(client, ip, command, expect_json=False)
            return

        backlog = "; ".join(self.commands)
        message = "Sending backlog after upgrade..." if after_upgrade else "Sending backlog..."
        self._log(ip, name, message, tag="CMD")
        self._send_cmd(client, ip, f"Backlog {backlog}", expect_json=False)

    def _collect_info_for_ip(self, client: httpx.Client, ip: str) -> DeviceResult:
        result = DeviceResult(IP=ip)
        try:
            status0, _ = self._send_cmd(client, ip, "Status 0")
        except Exception:
            return result

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
        result.TemplateName = ""

        if self.info_mode == "lite":
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

        try:
            status5, _ = self._send_cmd(client, ip, "Status 5")
            if isinstance(status5, dict):
                cfg = status5.get("StatusCFG") or status5.get("Status5") or {}
                template = cfg.get("Template")
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
        except Exception:
            # Status 5 is optional - device info is still valid without template name
            pass

        if not result.TemplateName:
            try:
                template, _ = self._send_cmd(client, ip, "Template")
                if isinstance(template, dict):
                    result.TemplateName = (template.get("NAME") or template.get("Name") or "").strip()
            except Exception:
                # Template command is optional - device info is still valid without it
                pass

        result.Ok = True
        return result

    def _upgrade_device(self, client: httpx.Client, ip: str, hardware: str, name: str) -> bool:
        ota_url = self.ota_urls["ESP32"] if "ESP32" in hardware.upper() else self.ota_urls["ESP8266"]
        self._log(ip, name, f"Sending OTA upgrade: {ota_url}", tag="OTA")
        self._send_cmd(client, ip, f"OtaUrl {ota_url}", expect_json=False)
        self._send_cmd(client, ip, "Upgrade 1", expect_json=False)
        self._log(ip, name, f"Waiting {OTA_RESTART_WAIT_SECONDS}s for OTA process (cancellable)...", tag="OTA")
        if self._interruptible_sleep(OTA_RESTART_WAIT_SECONDS, interval=2.0):
            self._log(ip, name, "OTA wait cancelled by user", tag="OTA")
            return False
        self._log(ip, name, "Sending Restart 1", tag="OTA")
        self._send_cmd(client, ip, "Restart 1", expect_json=False)
        if self._interruptible_sleep(1):
            return False

        for _ in range(OTA_VERIFICATION_RETRIES):
            if self._interruptible_sleep(OTA_VERIFICATION_INTERVAL):
                self._log(ip, name, "OTA verification cancelled by user", tag="OTA")
                return False
            try:
                result = self._collect_info_for_ip(client, ip)
                if result.Ok:
                    self._log(ip, name, f"Device online, running FW: {result.Version}", tag="OTA")
                    default_url = OTA_URLS["ESP32"] if "ESP32" in hardware.upper() else OTA_URLS["ESP8266"]
                    self._send_cmd(client, ip, f"OtaUrl {default_url}", expect_json=False)
                    self._log(ip, name, f"Re-applied official OTA URL: {default_url}", tag="OTA")
                    return True
            except Exception:
                # Device not yet online after OTA - retry on next iteration
                pass
        return False

    def _handle_ip(self, client: httpx.Client, ip: str) -> DeviceResult:
        if self._cancel_event.is_set():
            return DeviceResult(IP=ip, Ok=False, Error="Cancelled")
        try:
            info = self._collect_info_for_ip(client, ip)
            if info.Ok:
                self._log(ip, info.Name, "Info OK", tag="INFO")
                if ip in self.selected_ips:
                    if self.do_upgrade and ip in self.fw_ips:
                        upgraded = self._upgrade_device(client, ip, info.Hardware, info.Name)
                        if upgraded and self.send_backlog and ip in self.cmd_ips and self.commands:
                            self._send_backlog_or_commands(
                                client,
                                ip,
                                info.Name,
                                after_upgrade=True,
                            )
                    elif self.send_backlog and ip in self.cmd_ips and self.commands:
                        self._send_backlog_or_commands(client, ip, info.Name)
            else:
                self._log(ip, info.Name, "No response", tag="ERROR")
            return info
        except Exception as exc:
            self._log(ip, "", f"FAIL {exc}", tag="ERROR")
            return DeviceResult(IP=ip, Ok=False, Error=str(exc))

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
            with httpx.Client(limits=limits, timeout=timeout) as client:
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
                            self._log(ip, "", f"FAIL {exc}", tag="ERROR")
                            device_result = DeviceResult(IP=ip, Ok=False, Error=str(exc))

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

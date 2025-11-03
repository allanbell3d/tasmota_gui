"""Routines for discovering and managing Tasmota devices."""

from __future__ import annotations

import asyncio
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence, Set

import httpx
import pandas as pd

from .constants import DEFAULT_CSV, DEFAULT_XLSX, OTA_URLS
from .utils import safe_extract_json

LogCallback = Callable[[str, str], None]
ProgressCallback = Callable[[int, int], None]


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


@dataclass
class BulkRunResult:
    results: List[DeviceResult]
    xlsx_path: str
    csv_path: str
    rows_written: int


class TasmotaBulkExecutor:
    """Coordinate concurrent discovery and command execution."""

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
        self.threads = max(1, int(threads))
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
        self.timeout = max(1.0, float(timeout))
        self.retries = max(1, int(retries))
        self.backoff = float(backoff)
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
        self.log_callback(line, tag)

    def _emit_progress(self, done: int, total: int) -> None:
        if self.progress_callback is not None:
            self.progress_callback(done, total)

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
                        result.TemplateName = template.strip()
        except Exception:
            pass

        if not result.TemplateName:
            try:
                template, _ = self._send_cmd(client, ip, "Template")
                if isinstance(template, dict):
                    result.TemplateName = (template.get("NAME") or template.get("Name") or "").strip()
            except Exception:
                pass

        result.Ok = True
        return result

    def _upgrade_device(self, client: httpx.Client, ip: str, hardware: str, name: str) -> bool:
        ota_url = self.ota_urls["ESP32"] if "ESP32" in hardware.upper() else self.ota_urls["ESP8266"]
        self._log(ip, name, f"Sending OTA upgrade: {ota_url}", tag="OTA")
        self._send_cmd(client, ip, f"OtaUrl {ota_url}", expect_json=False)
        self._send_cmd(client, ip, "Upgrade 1", expect_json=False)
        self._log(ip, name, "Waiting 120s for OTA process...", tag="OTA")
        time.sleep(120)
        self._log(ip, name, "Sending Restart 1", tag="OTA")
        self._send_cmd(client, ip, "Restart 1", expect_json=False)
        time.sleep(1)

        for _ in range(18):
            time.sleep(5)
            try:
                result = self._collect_info_for_ip(client, ip)
                if result.Ok:
                    self._log(ip, name, f"Device online, running FW: {result.Version}", tag="OTA")
                    default_url = OTA_URLS["ESP32"] if "ESP32" in hardware.upper() else OTA_URLS["ESP8266"]
                    self._send_cmd(client, ip, f"OtaUrl {default_url}", expect_json=False)
                    self._log(ip, name, f"Re-applied official OTA URL: {default_url}", tag="OTA")
                    return True
            except Exception:
                pass
        return False

    def _handle_ip(self, client: httpx.Client, ip: str) -> DeviceResult:
        try:
            info = self._collect_info_for_ip(client, ip)
            if info.Ok:
                self._log(ip, info.Name, "Info OK", tag="INFO")
                if ip in self.selected_ips:
                    if self.do_upgrade and ip in self.fw_ips:
                        upgraded = self._upgrade_device(client, ip, info.Hardware, info.Name)
                        if upgraded and self.send_backlog and ip in self.cmd_ips and self.commands:
                            backlog = "; ".join(self.commands)
                            self._log(ip, info.Name, "Sending backlog after upgrade...", tag="CMD")
                            self._send_cmd(client, ip, f"Backlog {backlog}", expect_json=False)
                    elif self.send_backlog and ip in self.cmd_ips and self.commands:
                        backlog = "; ".join(self.commands)
                        self._log(ip, info.Name, "Sending backlog...", tag="CMD")
                        self._send_cmd(client, ip, f"Backlog {backlog}", expect_json=False)
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
        total = len(self.ips)
        self._emit_progress(0, total)

        results: List[DeviceResult] = []
        if total == 0:
            self._log("-", "", "No IP addresses provided", tag="WARN")
        else:
            limits = httpx.Limits(
                max_connections=self.threads,
                max_keepalive_connections=self.threads,
            )
            timeout = httpx.Timeout(self.timeout)
            with httpx.Client(limits=limits, timeout=timeout) as client:
                with ThreadPoolExecutor(max_workers=self.threads) as executor:
                    future_map = {executor.submit(self._handle_ip, client, ip): ip for ip in self.ips}
                    completed = 0
                    for future in as_completed(future_map):
                        ip = future_map[future]
                        try:
                            device_result = future.result()
                        except Exception as exc:  # pragma: no cover - safety net
                            self._log(ip, "", f"FAIL {exc}", tag="ERROR")
                            device_result = DeviceResult(IP=ip, Ok=False, Error=str(exc))
                        results.append(device_result)
                        completed += 1
                        self._emit_progress(completed, total)

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

        rows_written = 0
        if rows:
            rows_written = len(rows)
            if self.export_results:
                df = pd.DataFrame(rows).sort_values(by="Name", key=lambda column: column.str.lower())
                try:
                    df.to_excel(self.xlsx_path, index=False, engine="openpyxl")
                    self._log("-", "", f"Excel written {self.xlsx_path}", tag="INFO")
                except PermissionError:
                    alt_xlsx = os.path.join(
                        self.out_dir,
                        self._with_timestamp(DEFAULT_XLSX, extra_suffix="alt"),
                    )
                    df.to_excel(alt_xlsx, index=False, engine="openpyxl")
                    self._log("-", "", f"[WARN] Excel locked, wrote {alt_xlsx}", tag="WARN")
                    self.xlsx_path = alt_xlsx
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

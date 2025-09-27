# ============================
# AllanBell3D Tasmota Bulk Tool (Cross-Platform GUI)
# Version 0.1.1a
# ============================

import sys, os, json, asyncio, re, time
from dataclasses import dataclass

from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QPushButton, QTextEdit, QSpinBox, QFileDialog,
    QProgressBar, QMessageBox, QDialog, QTableWidget,
    QTableWidgetItem, QCheckBox, QHeaderView, QLineEdit, QSizePolicy
)

import httpx
import pandas as pd

# ============================
# Defaults / constants
# ============================
APP_VERSION      = "0.1.1a"
APP_TITLE        = f"AllanBell3D Tasmota Bulk Tool (Cross-Platform GUI) {APP_VERSION}"
DEFAULT_THREADS  = 100
DEFAULT_TIMEOUT  = 1
DEFAULT_RETRIES  = 1
DEFAULT_BACKOFF  = 1.0
DEFAULT_XLSX     = "tasmota_hardware_summary.xlsx"
DEFAULT_CSV      = "tasmota_hardware_summary.csv"

DEFAULT_COMMANDS = [
    "mqtthost 192.168.64.5",
    "mqttuser villa",
    "mqttpassword villa",
    "FullTopic %prefix%/%topic%/",
    "TelePeriod 10",
    "latitude 25.163853",
    "longitude 55.219098",
    "timezone +4",
    "powerretain on",
    "wattres 2",
    "EnergyRes 2",
    "AmpRes 2",
    "switchretain off",
    "buttonretain off",
    "poweronstate 3",
    "SetOption56 1",
    "SetOption57 1",
    "SetOption59 1",
    "SetOption65 1",
    "WifiConfig 5",
]

DEFAULT_IP_RANGES = """192.168.60.10-254
192.168.62.10-254
192.168.64.10-254
192.168.66.10-254"""

JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

OTA_URLS = {
    "ESP32": "http://ota.tasmota.com/tasmota32/release/tasmota32.bin",
    "ESP8266": "http://ota.tasmota.com/tasmota/release/tasmota.bin.gz"
}

# ============================
# Helpers
# ============================
def build_ip_list(ranges_text: str):
    ips = []
    for raw in ranges_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if "-" in line:
            try:
                prefix, tail = line.rsplit(".", 1)
                a, b = tail.split("-", 1)
                for i in range(int(a), int(b) + 1):
                    ips.append(f"{prefix}.{i}")
            except Exception:
                pass
        else:
            ips.append(line)
    return ips

def safe_extract_json(text: str):
    if not text:
        return None
    if "<html" in text.lower() and "{" not in text:
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    m = JSON_OBJECT_RE.search(text)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None

# ============================
# Data
# ============================
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
    # Extra fields for Full mode
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

# ============================
# Worker
# ============================
class Worker(QObject):
    progress = Signal(int, int)
    log_line = Signal(str, str)  # (line, tag)
    finished = Signal(str)

    def __init__(self, ips, threads, out_dir,
                 timeout, retries, backoff,
                 send_backlog, commands, do_upgrade=False,
                 selected_ips=None, ota_urls=None, info_mode="full",
                 cmd_ips=None, fw_ips=None):
        super().__init__()
        self.ips = ips
        self.threads = max(1, int(threads))
        self.out_dir = out_dir
        self.timeout = max(1, float(timeout))
        self.retries = max(1, int(retries))
        self.backoff = float(backoff)
        self.send_backlog = send_backlog
        self.commands = commands[:] if commands else []
        self.do_upgrade = bool(do_upgrade)
        self.selected_ips = set(selected_ips or [])
        self.cmd_ips = set(cmd_ips or self.selected_ips)
        self.fw_ips = set(fw_ips or self.selected_ips)
        self.xlsx_path = os.path.join(self.out_dir, DEFAULT_XLSX)
        self.csv_path = os.path.join(self.out_dir, DEFAULT_CSV)
        self.ota_urls = ota_urls or dict(OTA_URLS)
        self.info_mode = "lite" if str(info_mode).lower().startswith("lite") else "full"

    def _log(self, ip, name, msg, tag="INFO"):
        ts = time.strftime("%H:%M:%S")
        nm = f" [{name}]" if name else ""
        line = f"{ts} [{tag}] [{ip}]{nm} {msg}"
        self.log_line.emit(line, tag)

    async def _get(self, client: httpx.AsyncClient, url: str):
        last_err = ""
        for attempt in range(1, self.retries + 1):
            try:
                r = await client.get(url, timeout=self.timeout)
                if r.status_code == 200:
                    return r
                last_err = f"HTTP {r.status_code}"
            except Exception as e:
                last_err = str(e)
            if attempt < self.retries:
                await asyncio.sleep((2 ** (attempt - 1)) * self.backoff)
        raise RuntimeError(last_err)

    async def _send_cmd(self, client, ip, cmnd: str, expect_json=True):
        enc = httpx.QueryParams({"cmnd": cmnd})
        url = f"http://{ip}/cm?{enc}"
        try:
            r = await self._get(client, url)
            return safe_extract_json(r.text) if expect_json else None, r.text
        except Exception as e:
            return None, str(e)

    async def _collect_info_for_ip(self, client, ip) -> DeviceResult:
        res = DeviceResult(IP=ip)
        try:
            s0, _ = await self._send_cmd(client, ip, "Status 0")
        except Exception:
            return res

        if not isinstance(s0, dict):
            return res

        statusfwr = s0.get("StatusFWR", {}) or {}
        status    = s0.get("Status", {}) or {}
        statusnet = s0.get("StatusNET", {}) or {}
        statusmqt = s0.get("StatusMQT", {}) or {}
        statusprm = s0.get("StatusPRM", {}) or {}
        statusmem = s0.get("StatusMEM", {}) or {}
        statussts = s0.get("StatusSTS", {}) or {}

        version = statusfwr.get("Version", "")
        if not version or "tasmota" not in version.lower():
            return res

        res.Version      = version
        res.Core         = statusfwr.get("Core", "")
        res.SDK          = statusfwr.get("SDK", "")
        res.Hardware     = statusfwr.get("Hardware", "")
        res.Hostname     = statusnet.get("Hostname", "")
        res.Mac          = statusnet.get("Mac", "")
        res.Name         = status.get("DeviceName") or res.Hostname or "(unknown)"
        res.Module       = str(status.get("Module", ""))
        res.MqttTopic    = status.get("Topic", "")
        res.MqttClient   = statusmqt.get("MqttClient", "")
        res.TemplateName = ""

        # Lite mode stops here
        if self.info_mode == "lite":
            res.Ok = True
            return res

        # Full mode extras
        res.Uptime        = statusprm.get("Uptime", "")
        res.RestartReason = statusfwr.get("RestartReason", "")
        res.FlashSize     = statusmem.get("FlashSize", "")
        res.FreeMem       = statusmem.get("FreeMem", "")
        res.RSSI          = str(statussts.get("Wifi", {}).get("RSSI", ""))
        res.IPAddress     = statusnet.get("IPAddress", "")
        res.Gateway       = statusnet.get("Gateway", "")
        res.TelePeriod    = str(status.get("TelePeriod", ""))
        fnames            = status.get("FriendlyName") or []
        if isinstance(fnames, list) and fnames:
            res.FriendlyName = fnames[0]
        res.OtaUrl        = statusprm.get("OtaUrl", "")

        # Template name (best-effort)
        try:
            s5, _ = await self._send_cmd(client, ip, "Status 5")
            if isinstance(s5, dict):
                cfg = s5.get("StatusCFG") or s5.get("Status5") or {}
                templ = cfg.get("Template")
                if isinstance(templ, dict):
                    res.TemplateName = (templ.get("NAME") or templ.get("Name") or "").strip()
                elif isinstance(templ, str):
                    try:
                        tjson = json.loads(templ)
                        if isinstance(tjson, dict):
                            res.TemplateName = (tjson.get("NAME") or tjson.get("Name") or "").strip()
                    except Exception:
                        res.TemplateName = templ.strip()
        except Exception:
            pass

        if not res.TemplateName:
            try:
                t, _ = await self._send_cmd(client, ip, "Template")
                if isinstance(t, dict):
                    res.TemplateName = (t.get("NAME") or t.get("Name") or "").strip()
            except Exception:
                pass

        res.Ok = True
        return res

    async def _upgrade_device(self, client, ip, hw, name):
        # Pick OTA URL based on hardware type (for upgrade)
        ota_url = self.ota_urls["ESP32"] if "ESP32" in hw.upper() else self.ota_urls["ESP8266"]

        # Send OTA upgrade command
        self._log(ip, name, f"Sending OTA upgrade: {ota_url}", tag="OTA")
        await self._send_cmd(client, ip, f"OtaUrl {ota_url}", expect_json=False)
        await self._send_cmd(client, ip, "Upgrade 1", expect_json=False)

        # Wait for upgrade process
        self._log(ip, name, "Waiting 120s for OTA process...", tag="OTA")
        await asyncio.sleep(120)

        # Restart device after OTA
        self._log(ip, name, "Sending Restart 1", tag="OTA")
        await self._send_cmd(client, ip, "Restart 1", expect_json=False)
        await asyncio.sleep(1)

        # Poll until device comes back online
        for attempt in range(18):  # 18 * 5s = 90s
            await asyncio.sleep(5)
            try:
                res = await self._collect_info_for_ip(client, ip)
                if res.Ok:
                    self._log(ip, name, f"Device online, running FW: {res.Version}", tag="OTA")

                    # ✅ Reapply the hardcoded release OTA URL
                    default_url = OTA_URLS["ESP32"] if "ESP32" in hw.upper() else OTA_URLS["ESP8266"]
                    await self._send_cmd(client, ip, f"OtaUrl {default_url}", expect_json=False)
                    self._log(ip, name, f"Re-applied official OTA URL: {default_url}", tag="OTA")

                    return True
            except Exception:
                pass

        return False




    async def _handle_ip(self, sem, client, ip):
        async with sem:
            try:
                info = await self._collect_info_for_ip(client, ip)
                if info.Ok:
                    self._log(ip, info.Name, "Info OK", tag="INFO")

                    # ✅ Always check if this IP was selected for actions
                    if ip in self.selected_ips:
                        if self.do_upgrade:
                            # --- Firmware Upgrade Path ---
                            ok = await self._upgrade_device(client, ip, info.Hardware, info.Name)

                            # If upgrade worked and backlog is enabled → send backlog
                            if ok and self.send_backlog:
                                backlog = "; ".join(self.commands)
                                self._log(ip, info.Name, "Sending backlog after upgrade...", tag="CMD")
                                await self._send_cmd(client, ip, f"Backlog {backlog}", expect_json=False)

                        elif self.send_backlog:
                            # --- Backlog Only Path ---
                            backlog = "; ".join(self.commands)
                            self._log(ip, info.Name, "Sending backlog...", tag="CMD")
                            await self._send_cmd(client, ip, f"Backlog {backlog}", expect_json=False)

                else:
                    self._log(ip, info.Name, "No response", tag="ERROR")

                return info

            except Exception as e:
                self._log(ip, "", f"FAIL {e}", tag="ERROR")
                return DeviceResult(IP=ip, Ok=False, Error=str(e))


    async def run_async(self):
        sem = asyncio.Semaphore(self.threads)
        results = []
        async with httpx.AsyncClient() as client:
            tasks = [self._handle_ip(sem, client, ip) for ip in self.ips]
            total = len(tasks)
            done = 0
            for coro in asyncio.as_completed(tasks):
                res = await coro
                results.append(res)
                done += 1
                self.progress.emit(done, total)

        rows = []
        for r in results:
            if not r.Ok:
                continue
            base = {
                "Name": r.Name, "IP": r.IP, "Version": r.Version,
                "Core": r.Core, "SDK": r.SDK, "Hardware": r.Hardware,
                "Module": r.Module, "TemplateName": r.TemplateName,
                "Hostname": r.Hostname, "Mac": r.Mac,
                "MqttTopic": r.MqttTopic, "MqttClient": r.MqttClient
            }
            if self.info_mode == "full":
                base.update({
                    "Uptime": r.Uptime,
                    "RestartReason": r.RestartReason,
                    "FlashSize": r.FlashSize,
                    "FreeMem": r.FreeMem,
                    "RSSI": r.RSSI,
                    "IPAddress": r.IPAddress,
                    "Gateway": r.Gateway,
                    "TelePeriod": r.TelePeriod,
                    "FriendlyName": r.FriendlyName,
                    "OtaUrl": r.OtaUrl
                })
            rows.append(base)

        if rows:
            df = pd.DataFrame(rows).sort_values(by="Name", key=lambda col: col.str.lower())
            ts_suffix = time.strftime("%Y%m%d_%H%M%S")

            # Excel write with protection
            try:
                df.to_excel(self.xlsx_path, index=False, engine="openpyxl")
                self._log("-", "", f"Excel written {self.xlsx_path}", tag="INFO")
            except PermissionError:
                alt_xlsx = os.path.join(
                    self.out_dir, f"tasmota_hardware_summary_{ts_suffix}.xlsx"
                )
                df.to_excel(alt_xlsx, index=False, engine="openpyxl")
                self._log("-", "", f"[WARN] Excel locked, wrote {alt_xlsx}", tag="WARN")

            # CSV write with protection
            try:
                df.to_csv(self.csv_path, index=False)
                self._log("-", "", f"CSV written   {self.csv_path}", tag="INFO")
            except PermissionError:
                alt_csv = os.path.join(
                    self.out_dir, f"tasmota_hardware_summary_{ts_suffix}.csv"
                )
                df.to_csv(alt_csv, index=False)
                self._log("-", "", f"[WARN] CSV locked, wrote {alt_csv}", tag="WARN")

        self.finished.emit(self.xlsx_path)

    def run(self):
        asyncio.run(self.run_async())

# ============================
# Selection Window (with filters + OTA URL edits)
# ============================
class SelectionWindow(QDialog):
    def __init__(self, parent, results, saved_state=None):
        super().__init__(parent)
        self.setWindowTitle("Select Actions")
        self.resize(1000, 600)
        self.results = sorted([r for r in results if r.Ok], key=lambda r: r.Name.lower())
        self.parent = parent
        self.saved_state = saved_state or {}

        v = QVBoxLayout(self)

        # Search / filter row
        fh = QHBoxLayout()
        self.search_box = QLineEdit(); self.search_box.setPlaceholderText("Search Name / IP / MAC...")
        self.chk_selected_only = QCheckBox("Show only selected")
        fh.addWidget(self.search_box); fh.addWidget(self.chk_selected_only)
        v.addLayout(fh)
        self.search_box.textChanged.connect(self.apply_filters)
        self.chk_selected_only.stateChanged.connect(self.apply_filters)

        # Table
        self.table = QTableWidget(len(self.results), 7)
        self.table.setHorizontalHeaderLabels(
            ["Commands","Firmware","Name","Version","Hardware","IP","Mac"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSortingEnabled(True)

        self.populate_table()
        v.addWidget(self.table)

        # Buttons row
        bh = QHBoxLayout()
        self.btn_all_cmd = QPushButton("Toggle All Commands")
        self.btn_all_fw = QPushButton("Toggle All Firmware")
        self.btn_esp8266_cmd = QPushButton("Toggle ESP82xx Commands")
        self.btn_esp8266_fw = QPushButton("Toggle ESP82xx Firmware")
        self.btn_esp32_cmd = QPushButton("Toggle ESP32 Commands")
        self.btn_esp32_fw = QPushButton("Toggle ESP32 Firmware")
        bh.addWidget(self.btn_all_cmd); bh.addWidget(self.btn_all_fw)
        bh.addWidget(self.btn_esp8266_cmd); bh.addWidget(self.btn_esp8266_fw)
        bh.addWidget(self.btn_esp32_cmd); bh.addWidget(self.btn_esp32_fw)
        v.addLayout(bh)

        self.btn_all_cmd.clicked.connect(lambda: self.toggle_rows(range(self.table.rowCount()), 0))
        self.btn_all_fw.clicked.connect(lambda: self.toggle_rows(range(self.table.rowCount()), 1))
        self.btn_esp8266_cmd.clicked.connect(lambda: self.toggle_hw("ESP8266", 0))
        self.btn_esp8266_fw.clicked.connect(lambda: self.toggle_hw("ESP8266", 1))
        self.btn_esp32_cmd.clicked.connect(lambda: self.toggle_hw("ESP32", 0))
        self.btn_esp32_fw.clicked.connect(lambda: self.toggle_hw("ESP32", 1))

        # OTA URL edits (session-only) + Restore Default buttons
        ota_row1 = QHBoxLayout()
        self.txt_esp32 = QLineEdit(self.parent.ota_urls.get("ESP32", OTA_URLS["ESP32"]))
        btn_reset_esp32 = QPushButton("Restore Default")
        btn_reset_esp32.clicked.connect(lambda: self.txt_esp32.setText(OTA_URLS["ESP32"]))
        ota_row1.addWidget(QLabel("ESP32 OTA URL:"))
        ota_row1.addWidget(self.txt_esp32)
        ota_row1.addWidget(btn_reset_esp32)
        v.addLayout(ota_row1)

        ota_row2 = QHBoxLayout()
        self.txt_esp8266 = QLineEdit(self.parent.ota_urls.get("ESP8266", OTA_URLS["ESP8266"]))
        btn_reset_esp8266 = QPushButton("Restore Default")
        btn_reset_esp8266.clicked.connect(lambda: self.txt_esp8266.setText(OTA_URLS["ESP8266"]))
        ota_row2.addWidget(QLabel("ESP82xx OTA URL:"))
        ota_row2.addWidget(self.txt_esp8266)
        ota_row2.addWidget(btn_reset_esp8266)
        v.addLayout(ota_row2)


        # Save & close
        self.btn_save = QPushButton("Save and Close")
        self.btn_save.clicked.connect(self.save_and_close)
        v.addWidget(self.btn_save)

    def populate_table(self):
        self.table.setRowCount(len(self.results))
        for i, r in enumerate(self.results):
            chk_cmd = QCheckBox(); chk_cmd.setStyleSheet("QCheckBox { margin-left:auto; margin-right:auto; }")
            chk_fw  = QCheckBox(); chk_fw.setStyleSheet("QCheckBox { margin-left:auto; margin-right:auto; }")

            if r.IP in self.saved_state:
                chk_cmd.setChecked(self.saved_state[r.IP].get("cmd", False))
                chk_fw.setChecked(self.saved_state[r.IP].get("fw", False))

            self.table.setCellWidget(i,0,chk_cmd)
            self.table.setCellWidget(i,1,chk_fw)
            self.table.setItem(i,2,QTableWidgetItem(r.Name))
            self.table.setItem(i,3,QTableWidgetItem(r.Version))
            self.table.setItem(i,4,QTableWidgetItem(r.Hardware))
            self.table.setItem(i,5,QTableWidgetItem(r.IP))
            self.table.setItem(i,6,QTableWidgetItem(r.Mac))

    def apply_filters(self):
        query = (self.search_box.text() or "").lower()
        selected_only = self.chk_selected_only.isChecked()
        for i in range(self.table.rowCount()):
            match = True
            if query:
                name = self.table.item(i, 2).text().lower() if self.table.item(i, 2) else ""
                ip   = self.table.item(i, 5).text().lower() if self.table.item(i, 5) else ""
                mac  = self.table.item(i, 6).text().lower() if self.table.item(i, 6) else ""
                match = (query in name) or (query in ip) or (query in mac)
            if selected_only:
                c = self.table.cellWidget(i, 0).isChecked()
                f = self.table.cellWidget(i, 1).isChecked()
                match = match and (c or f)
            self.table.setRowHidden(i, not match)

    def toggle_rows(self, indices, col):
        all_checked = True
        for i in indices:
            if not self.table.cellWidget(i, col).isChecked():
                all_checked = False
                break
        new_state = not all_checked
        for i in indices:
            self.table.cellWidget(i, col).setChecked(new_state)

    def toggle_hw(self, key, col):
        indices = []
        for i in range(self.table.rowCount()):
            hw = (self.table.item(i,4).text() or "").upper()
            if key == "ESP32" and "ESP32" in hw:
                indices.append(i)
            if key == "ESP8266" and any(x in hw for x in ["ESP8266","ESP8285","ESP82"]):
                indices.append(i)
        self.toggle_rows(indices, col)

    def get_selection(self):
        cmds, fws, state = [], [], {}
        for i in range(self.table.rowCount()):
            ip = self.table.item(i,5).text() if self.table.item(i,5) else ""
            c = self.table.cellWidget(i,0).isChecked()
            f = self.table.cellWidget(i,1).isChecked()
            state[ip] = {"cmd": c, "fw": f}
            if c: cmds.append(ip)
            if f: fws.append(ip)
        return cmds, fws, state

    def save_and_close(self):
        # Persist OTA URLs back to parent
        self.parent.ota_urls = {
            "ESP32": self.txt_esp32.text().strip() or OTA_URLS["ESP32"],
            "ESP8266": self.txt_esp8266.text().strip() or OTA_URLS["ESP8266"]
        }
        # Save current selections
        cmds, fws, state = self.get_selection()
        self.parent.last_cmds_selected = cmds
        self.parent.last_fw_selected = fws
        self.parent.last_state = state
        self.accept()

# ============================
# GUI
# ============================
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1100, 800)

        v = QVBoxLayout(self)

        # Info mode (Lite / Full) big buttons spanning half width each
        mode_box = QGroupBox("Info Mode")
        mh = QHBoxLayout()
        self.btn_lite = QPushButton("Lite")
        self.btn_full = QPushButton("Full")
        self.btn_lite.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.btn_full.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        mh.addWidget(self.btn_lite, 1)
        mh.addWidget(self.btn_full, 1)
        mode_box.setLayout(mh)
        v.addWidget(mode_box)

        self.info_mode = "lite"
        self._update_mode_buttons()
        self.btn_lite.clicked.connect(lambda: self.set_info_mode("lite"))
        self.btn_full.clicked.connect(lambda: self.set_info_mode("full"))

        ctl = QHBoxLayout()
        ctl.addWidget(QLabel("Threads:")); self.spin_threads = QSpinBox()
        self.spin_threads.setRange(1,1000); self.spin_threads.setValue(DEFAULT_THREADS); ctl.addWidget(self.spin_threads)
        ctl.addWidget(QLabel("Timeout (s):")); self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(1,120); self.spin_timeout.setValue(DEFAULT_TIMEOUT); ctl.addWidget(self.spin_timeout)
        ctl.addWidget(QLabel("Retries:")); self.spin_retries = QSpinBox()
        self.spin_retries.setRange(1,10); self.spin_retries.setValue(DEFAULT_RETRIES); ctl.addWidget(self.spin_retries)
        v.addLayout(ctl)

        v.addWidget(QLabel("IP ranges:")); self.txt_ranges = QTextEdit()
        self.txt_ranges.setPlainText(DEFAULT_IP_RANGES); v.addWidget(self.txt_ranges)
        v.addWidget(QLabel("Commands:")); self.txt_cmds = QTextEdit()
        self.txt_cmds.setPlainText("\n".join(DEFAULT_COMMANDS)); v.addWidget(self.txt_cmds)

        bh = QHBoxLayout()
        self.btn_start = QPushButton("Start Scan"); self.btn_start.clicked.connect(self.on_start)
        self.btn_pick = QPushButton("Pick Output Folder"); self.btn_pick.clicked.connect(self.on_pick_folder)
        self.btn_select = QPushButton("Open Selection Window"); self.btn_select.clicked.connect(self.open_selection)
        self.btn_run = QPushButton("Run Selected"); self.btn_run.clicked.connect(self.run_selected)
        bh.addWidget(self.btn_start); bh.addWidget(self.btn_pick); bh.addWidget(self.btn_select); bh.addWidget(self.btn_run)
        v.addLayout(bh)

        self.progress = QProgressBar(); v.addWidget(self.progress)

        # Log filter buttons
        lf = QHBoxLayout()
        self.btn_log_all = QPushButton("All"); self.btn_log_err = QPushButton("Errors"); self.btn_log_ota = QPushButton("OTA")
        self.btn_log_save = QPushButton("Save Log")
        lf.addWidget(self.btn_log_all); lf.addWidget(self.btn_log_err); lf.addWidget(self.btn_log_ota); lf.addWidget(self.btn_log_save)
        v.addLayout(lf)

        self.txt_log = QTextEdit(); self.txt_log.setReadOnly(True); v.addWidget(self.txt_log)
        self.all_logs = []; self.current_log_filter = "ALL"
        self.btn_log_all.clicked.connect(lambda: self.set_log_filter("ALL"))
        self.btn_log_err.clicked.connect(lambda: self.set_log_filter("ERROR"))
        self.btn_log_ota.clicked.connect(lambda: self.set_log_filter("OTA"))
        self.btn_log_save.clicked.connect(self.save_log)

        # defaults & state
        self.output_folder = os.getcwd()
        self.last_results = []
        self.last_cmds_selected = []
        self.last_fw_selected = []
        self.last_state = {}
        self.ota_urls = dict(OTA_URLS)

    # ----- Info mode -----
    def set_info_mode(self, mode):
        self.info_mode = mode
        self._update_mode_buttons()

    def _update_mode_buttons(self):
        if self.info_mode == "lite":
            self.btn_lite.setStyleSheet("background-color: lightgreen; font-weight: bold;")
            self.btn_full.setStyleSheet("")
        else:
            self.btn_full.setStyleSheet("background-color: lightblue; font-weight: bold;")
            self.btn_lite.setStyleSheet("")

    # ----- Logging helpers -----
    def append_log(self, line, tag="INFO"):
        self.all_logs.append((line, tag))
        if self.current_log_filter in ("ALL", tag):
            fmt = QTextCharFormat()
            if tag == "ERROR":
                fmt.setForeground(QColor("red"))
            elif tag == "WARN":
                fmt.setForeground(QColor("orange"))
            elif tag == "OTA":
                fmt.setForeground(QColor("blue"))
            else:
                fmt.setForeground(QColor("black"))
            cursor = self.txt_log.textCursor()
            cursor.movePosition(QTextCursor.End)
            cursor.insertText(line + "\n", fmt)
            self.txt_log.setTextCursor(cursor)

    def set_log_filter(self, f):
        self.current_log_filter = f
        self.txt_log.clear()
        for line, tag in self.all_logs:
            if f == "ALL" or tag == f:
                fmt = QTextCharFormat()
                if tag == "ERROR":
                    fmt.setForeground(QColor("red"))
                elif tag == "WARN":
                    fmt.setForeground(QColor("orange"))
                elif tag == "OTA":
                    fmt.setForeground(QColor("blue"))
                else:
                    fmt.setForeground(QColor("black"))
                cursor = self.txt_log.textCursor()
                cursor.movePosition(QTextCursor.End)
                cursor.insertText(line + "\n", fmt)
                self.txt_log.setTextCursor(cursor)

    def save_log(self):
        ts_suffix = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self.output_folder, f"tasmota_log_{ts_suffix}.txt")
        try:
            with open(path, "w", encoding="utf-8") as f:
                for line, tag in self.all_logs:
                    f.write(line + "\n")
            QMessageBox.information(self, "Log Saved", f"Saved log to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))

    # ----- Core actions -----
    def on_pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Choose output folder", self.output_folder)
        if d:
            self.output_folder = d

    def on_progress(self, c, t):
        self.progress.setMaximum(t)
        self.progress.setValue(c)
        pct = int((c / t) * 100) if t else 0
        self.progress.setFormat(f"{c} / {t} ({pct}%)")

    def on_finished(self, xlsx):
        self.append_log(f"[INFO] Finished. Excel: {xlsx}", tag="INFO")
        self.btn_start.setEnabled(True)

    def on_start(self):
        ips = build_ip_list(self.txt_ranges.toPlainText())
        info_mode = self.info_mode
        self.worker = Worker(
            ips,
            self.spin_threads.value(),
            self.output_folder,
            self.spin_timeout.value(),
            self.spin_retries.value(),
            DEFAULT_BACKOFF,
            False, [],
            ota_urls=self.ota_urls,
            info_mode=info_mode
        )
        self.worker_thread = QThread()
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_progress)
        self.worker.log_line.connect(self.append_log)
        self.worker.finished.connect(self.scan_done)
        self.worker.finished.connect(self.worker_thread.quit)
        self.btn_start.setEnabled(False)
        self.worker_thread.start()

    def scan_done(self, xlsx):
        self.append_log("[INFO] Scan completed", tag="INFO")
        try:
            df = pd.read_excel(xlsx)
        except Exception as e:
            QMessageBox.critical(self, "Read Error", f"Could not read Excel results:\n{e}")
            self.btn_start.setEnabled(True)
            return

        self.last_results.clear()
        for row in df.to_dict(orient="records"):
            r = DeviceResult(**row); r.Ok = True
            self.last_results.append(r)
        self.last_results.sort(key=lambda r: r.Name.lower())
        self.append_log(f"[INFO] Results refreshed: {len(self.last_results)} devices", tag="INFO")
        self.btn_start.setEnabled(True)

    def open_selection(self):
        if not self.last_results:
            QMessageBox.warning(self, "No scan", "Run a scan first")
            return
        dlg = SelectionWindow(self, self.last_results, self.last_state)
        if dlg.exec():
            cmds, fws, state = dlg.get_selection()
            self.last_cmds_selected = cmds
            self.last_fw_selected = fws
            self.last_state = state
            self.append_log(f"[INFO] Selection saved: {len(cmds)} cmds, {len(fws)} fw", tag="INFO")

    def run_selected(self):
        if not (self.last_cmds_selected or self.last_fw_selected):
            QMessageBox.warning(self, "No selections", "Open selection window first")
            return
        selected_ips = set(self.last_cmds_selected + self.last_fw_selected)
        info_mode = self.info_mode
        self.worker = Worker(
            list(selected_ips),
            self.spin_threads.value(),
            self.output_folder,
            self.spin_timeout.value(),
            self.spin_retries.value(),
            DEFAULT_BACKOFF,
            bool(self.last_cmds_selected),
            [ln.strip() for ln in self.txt_cmds.toPlainText().splitlines() if ln.strip()],
            do_upgrade=True if self.last_fw_selected else False,
            selected_ips=selected_ips,
            ota_urls=self.ota_urls,
            info_mode=info_mode,
            cmd_ips=set(self.last_cmds_selected),
            fw_ips=set(self.last_fw_selected)
        )
        self.worker_thread = QThread()
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_progress)
        self.worker.log_line.connect(self.append_log)
        self.worker.finished.connect(self.on_finished)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker_thread.start()

# ============================
# Entry
# ============================
def main():
    app = QApplication(sys.argv)
    w = MainWindow(); w.show()
    sys.exit(app.exec())

if __name__=="__main__":
    main()

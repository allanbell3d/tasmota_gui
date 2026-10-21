"""Main window of the AllanBell3D Tasmota Bulk Tool desktop (PySide6) UI."""

import html
import os
import sys
import time
from dataclasses import fields
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, QEvent, QObject, QThread
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor, QFontMetrics
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QPushButton, QTextEdit, QSpinBox, QDoubleSpinBox, QFileDialog,
    QProgressBar, QMessageBox, QDialog, QLineEdit, QSizePolicy,
)

from tasmota.core.commands import CommandLibraryError, load_command_library
from tasmota.core.settings import SettingsStore, UserSettings
from tasmota.constants import (
    APP_TITLE_SUFFIX,
    APP_VERSION,
    DEFAULT_BACKOFF,
    DEFAULT_OUTPUT_DIR_NAME,
    MAX_THREADS,
    OTA_URLS,
)
from tasmota.core.utils import validate_ip_ranges

# ============================
# Defaults / constants
# ============================
APP_TITLE = f"{APP_TITLE_SUFFIX} {APP_VERSION}"

# ============================
# Helpers
# ============================
def _get_default_output_directory() -> str:
    base_dir = os.getcwd()
    default_dir = os.path.join(base_dir, DEFAULT_OUTPUT_DIR_NAME)
    os.makedirs(default_dir, exist_ok=True)
    return default_dir


def _resolve_output_directory(saved: str) -> str:
    """Use the remembered output folder if it still exists."""
    if saved and os.path.isdir(saved):
        return saved
    return _get_default_output_directory()


def load_command_library_safe() -> Tuple[List, Optional[str]]:
    """Load command library, returning (records, error_message) tuple."""
    try:
        records = load_command_library()
        return (records, None)
    except CommandLibraryError as exc:
        return ([], str(exc))


from tasmota.ui.desktop.worker import Worker

from tasmota.ui.desktop.dialogs.selection import SelectionWindow

from tasmota.ui.desktop.dialogs.command_library import CommandLibraryDialog

class MainWindow(QWidget):
    MAX_LOG_LINES = 1000  # Limit log buffer to prevent memory growth

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1100, 800)

        v = QVBoxLayout(self)

        # Info mode (Lite / Full) big buttons spanning half width each
        mode_box = QGroupBox("Info Mode")
        mode_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        mh = QHBoxLayout()
        self.btn_lite = QPushButton("Lite")
        self.btn_full = QPushButton("Full")
        self.btn_lite.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.btn_full.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        mh.addWidget(self.btn_lite, 1)
        mh.addWidget(self.btn_full, 1)
        mode_box.setLayout(mh)
        mode_box.setFixedHeight(self._calculate_mode_box_height(mode_box))
        v.addWidget(mode_box)

        # Personal values (IP ranges, commands, password...) come from the
        # private settings file, see tasmota/core/settings.py.
        self._settings_store = SettingsStore()
        self.settings, settings_warning = self._settings_store.load()

        self.info_mode = self.settings.info_mode
        self._command_library_last_error = None  # Track last error to avoid duplicates
        self._update_mode_buttons()
        self.btn_lite.clicked.connect(lambda: self.set_info_mode("lite"))
        self.btn_full.clicked.connect(lambda: self.set_info_mode("full"))

        ctl = QHBoxLayout()
        ctl.addWidget(QLabel("Threads:")); self.spin_threads = QSpinBox()
        self.spin_threads.setRange(1, MAX_THREADS); self.spin_threads.setValue(self.settings.threads); ctl.addWidget(self.spin_threads)
        ctl.addWidget(QLabel("Timeout (s):")); self.spin_timeout = QDoubleSpinBox()
        self.spin_timeout.setDecimals(1); self.spin_timeout.setSingleStep(0.5)
        self.spin_timeout.setRange(1, 120); self.spin_timeout.setValue(min(120.0, self.settings.timeout)); ctl.addWidget(self.spin_timeout)
        ctl.addWidget(QLabel("Retries:")); self.spin_retries = QSpinBox()
        self.spin_retries.setRange(1,10); self.spin_retries.setValue(self.settings.retries); ctl.addWidget(self.spin_retries)
        ctl.addWidget(QLabel("Web password:")); self.txt_password = QLineEdit(self.settings.web_password)
        self.txt_password.setEchoMode(QLineEdit.Password)
        self.txt_password.setPlaceholderText("only if devices use WebPassword")
        ctl.addWidget(self.txt_password)
        v.addLayout(ctl)

        v.addWidget(QLabel("IP ranges:")); self.txt_ranges = QTextEdit()
        self.txt_ranges.setPlainText(self.settings.ip_ranges)
        self._set_text_edit_rows(self.txt_ranges, 5)
        v.addWidget(self.txt_ranges)

        cmd_header = QHBoxLayout()
        self.lbl_commands = QLabel("Commands:")
        cmd_header.addWidget(self.lbl_commands)
        cmd_header.addStretch(1)
        self.btn_cmd_library = QPushButton("Command Library…")
        self.btn_cmd_library.clicked.connect(self.open_command_library)
        cmd_header.addWidget(self.btn_cmd_library)
        v.addLayout(cmd_header)

        self.txt_cmds = QTextEdit()
        self.txt_cmds.setPlainText("\n".join(self.settings.commands))
        self.txt_cmds.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        v.addWidget(self.txt_cmds, 1)
        self.txt_cmds.setContextMenuPolicy(Qt.CustomContextMenu)
        self.txt_cmds.customContextMenuRequested.connect(self.show_cmd_context_menu)
        self.txt_cmds.installEventFilter(self)
        self._sync_command_library_button_state()

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

        self.txt_log = QTextEdit(); self.txt_log.setReadOnly(True)
        self.txt_log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        v.addWidget(self.txt_log, 1)
        self.all_logs = []; self.current_log_filter = "ALL"
        self._log_colors = {
            "ERROR": QColor("red"),
            "WARN": QColor("orange"),
            "OTA": QColor("blue"),
            "CMD": QColor("purple"),
            "INFO": QColor("black"),
            "DEFAULT": QColor("black"),
        }
        self._log_formats = {}
        self._log_color_codes = {}
        self.btn_log_all.clicked.connect(lambda: self.set_log_filter("ALL"))
        self.btn_log_err.clicked.connect(lambda: self.set_log_filter("ERROR"))
        self.btn_log_ota.clicked.connect(lambda: self.set_log_filter("OTA"))
        self.btn_log_save.clicked.connect(self.save_log)

        # defaults & state
        self.output_folder = _resolve_output_directory(self.settings.output_dir)
        self.last_results = []
        self.last_cmds_selected = []
        self.last_fw_selected = []
        self.last_state = {}
        self.ota_urls = dict(OTA_URLS)  # Session only, never saved
        self._scan_running = False
        self._close_after_run = False
        self.worker = None
        self.worker_thread = None

        if settings_warning:
            self.append_log(f"[WARN] {settings_warning}", tag="WARN")
        elif self._settings_store.loaded_from:
            self.append_log(f"[INFO] Settings loaded from {self._settings_store.loaded_from}", tag="INFO")

    # ----- Settings -----
    def _collect_settings(self) -> UserSettings:
        settings = self.settings
        settings.ip_ranges = self.txt_ranges.toPlainText()
        settings.commands = [ln.strip() for ln in self.txt_cmds.toPlainText().splitlines() if ln.strip()]
        settings.threads = self.spin_threads.value()
        settings.timeout = float(self.spin_timeout.value())
        settings.retries = self.spin_retries.value()
        settings.info_mode = self.info_mode
        settings.output_dir = self.output_folder
        settings.web_password = self.txt_password.text()
        return settings

    def _save_settings(self) -> None:
        error = self._settings_store.save(self._collect_settings())
        if error:
            self.append_log(f"[WARN] {error}", tag="WARN")

    def closeEvent(self, event) -> None:
        if self._scan_running:
            answer = QMessageBox.question(
                self,
                "Run in progress",
                "A run is still in progress. Cancel it and close when it has stopped?\n\n"
                "Devices already flashing firmware will finish on their own.",
            )
            if answer != QMessageBox.Yes:
                event.ignore()
                return
            self._close_after_run = True
            if self.worker is not None:
                self.worker.executor.cancel()
            self.append_log("[INFO] Closing after the current run stops...", tag="INFO")
            event.ignore()  # Closed from _on_worker_finished once the thread is done
            return
        self._save_settings()
        self._wait_for_worker_thread()
        super().closeEvent(event)

    # ----- Info mode -----
    def set_info_mode(self, mode: str) -> None:
        self.info_mode = mode
        self._update_mode_buttons()

    def _update_mode_buttons(self) -> None:
        if self.info_mode == "lite":
            self.btn_lite.setStyleSheet("background-color: lightgreen; font-weight: bold;")
            self.btn_full.setStyleSheet("")
        else:
            self.btn_full.setStyleSheet("background-color: lightblue; font-weight: bold;")
            self.btn_lite.setStyleSheet("")

    # ----- Logging helpers -----
    def append_log(self, line: str, tag: str = "INFO") -> None:
        self.all_logs.append((line, tag))
        # Prune old logs to prevent memory growth
        if len(self.all_logs) > self.MAX_LOG_LINES:
            self.all_logs = self.all_logs[-self.MAX_LOG_LINES:]
        if self.current_log_filter in ("ALL", tag):
            fmt = self._get_log_format(tag)
            cursor = self.txt_log.textCursor()
            cursor.movePosition(QTextCursor.End)
            cursor.insertText(line + "\n", fmt)
            self.txt_log.setTextCursor(cursor)

    # ----- Layout helpers -----
    @staticmethod
    def _set_text_edit_rows(edit: QTextEdit, rows: int) -> None:
        metrics = QFontMetrics(edit.font())
        line_height = metrics.lineSpacing()
        margins = edit.contentsMargins()
        frame = edit.frameWidth()
        extra_height = margins.top() + margins.bottom() + (frame * 2)
        edit.setFixedHeight(int(line_height * rows + extra_height))
        edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    @staticmethod
    def _calculate_mode_box_height(widget: QWidget) -> int:
        metrics = QFontMetrics(widget.font())
        line_height = metrics.lineSpacing()
        # Allow room for one line of text plus padding for the buttons and frame.
        return int(line_height * 4)

    def set_log_filter(self, f: str) -> None:
        self.current_log_filter = f
        filtered_lines = []
        for line, tag in self.all_logs:
            if f == "ALL" or tag == f:
                color = self._get_log_color_code(tag)
                filtered_lines.append(
                    f'<span style="color:{color}; white-space:pre-wrap">{html.escape(line)}</span>'
                )
        if filtered_lines:
            self.txt_log.setHtml("<br/>".join(filtered_lines))
        else:
            self.txt_log.clear()
        cursor = self.txt_log.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.txt_log.setTextCursor(cursor)

    def _get_log_color(self, tag: str) -> QColor:
        return self._log_colors.get(tag, self._log_colors["DEFAULT"])

    def _get_log_format(self, tag: str) -> QTextCharFormat:
        fmt = self._log_formats.get(tag)
        if fmt is None:
            fmt = QTextCharFormat()
            fmt.setForeground(self._get_log_color(tag))
            self._log_formats[tag] = fmt
        return fmt

    def _get_log_color_code(self, tag: str) -> str:
        code = self._log_color_codes.get(tag)
        if code is None:
            code = self._get_log_color(tag).name()
            self._log_color_codes[tag] = code
        return code

    def save_log(self) -> None:
        ts_suffix = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self.output_folder, f"tasmota_log_{ts_suffix}.txt")
        try:
            with open(path, "w", encoding="utf-8") as f:
                for line, _tag in self.all_logs:
                    f.write(line + "\n")
            QMessageBox.information(self, "Log Saved", f"Saved log to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))

    def show_cmd_context_menu(self, pos) -> None:
        menu = self.txt_cmds.createStandardContextMenu()
        if menu is None:
            return
        menu.addSeparator()
        action = menu.addAction("Command Library…")
        action.triggered.connect(self.open_command_library)
        menu.exec(self.txt_cmds.mapToGlobal(pos))

    def open_command_library(self) -> None:
        records, error = load_command_library_safe()
        if error:
            # Only show error if it's different from the last one (avoid duplicates)
            if self._command_library_last_error != error:
                self._command_library_last_error = error
                QMessageBox.critical(self, "Command Library Error", error)
            return
        self._command_library_last_error = None  # Clear on success
        if not records:
            QMessageBox.information(self, "Command Library", "No commands available in tasmota_commands.json.")
            return
        dialog = CommandLibraryDialog(self, records)
        if dialog.exec() == QDialog.Accepted and dialog.selected_commands:
            current_text = self.txt_cmds.toPlainText()
            existing_lines = current_text.splitlines()
            existing_set = {line.strip() for line in existing_lines if line.strip()}
            to_append = [cmd for cmd in dialog.selected_commands if cmd.strip() not in existing_set]
            if to_append:
                if current_text and not current_text.endswith("\n"):
                    current_text += "\n"
                current_text += "\n".join(to_append)
                self.txt_cmds.setPlainText(current_text)

    def _sync_command_library_button_state(self) -> None:
        self.btn_cmd_library.setEnabled(self.txt_cmds.isEnabled())

    def eventFilter(self, source: QObject, event: QEvent) -> bool:
        if source is self.txt_cmds and event.type() == QEvent.EnabledChange:
            self._sync_command_library_button_state()
        return super().eventFilter(source, event)

    # ----- Core actions -----
    def on_pick_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Choose output folder", self.output_folder)
        if d:
            self.output_folder = d

    def on_progress(self, c: int, t: int) -> None:
        self.progress.setMaximum(t)
        self.progress.setValue(c)
        pct = int((c / t) * 100) if t else 0
        self.progress.setFormat(f"{c} / {t} ({pct}%)")

    def _on_worker_finished(self, result, *, full_scan: bool) -> None:
        self._set_scan_running(False)
        if result is not None:
            if full_scan:
                self._replace_last_results(result)
            else:
                self._merge_last_results(result)
            label = "Scan completed" if full_scan else "Run finished"
            exported = result.rows_written and result.xlsx_path and os.path.exists(result.xlsx_path)
            if exported:
                self.append_log(f"[INFO] {label}. Excel: {result.xlsx_path}", tag="INFO")
            else:
                self.append_log(f"[INFO] {label}", tag="INFO")
            if exported and result.csv_path and os.path.exists(result.csv_path):
                self.append_log(f"[INFO] CSV export: {result.csv_path}", tag="INFO")
            if full_scan:
                self.append_log(f"[INFO] Results refreshed: {len(self.last_results)} devices", tag="INFO")
        if self._close_after_run:
            self._wait_for_worker_thread()
            self.close()

    def _wait_for_worker_thread(self) -> None:
        """Let the finished worker thread exit before the window goes away."""
        thread = self.worker_thread
        if thread is None:
            return
        try:
            thread.wait(5000)
        except RuntimeError:
            pass  # Qt object already deleted - nothing left to wait for

    def scan_done(self, result) -> None:
        self._on_worker_finished(result, full_scan=True)

    def on_finished(self, result) -> None:
        self._on_worker_finished(result, full_scan=False)

    def on_start(self) -> None:
        if self._scan_running:
            # Cancel the current scan
            if self.worker is not None:
                self.worker.executor.cancel()
                self.append_log("[INFO] Scan cancellation requested...", tag="INFO")
            return

        ips, invalid = validate_ip_ranges(self.txt_ranges.toPlainText())

        # Show validation feedback
        if invalid:
            invalid_preview = ", ".join(invalid[:5])
            if len(invalid) > 5:
                invalid_preview += f" ... (+{len(invalid) - 5} more)"
            self.append_log(f"[WARN] Skipped {len(invalid)} invalid entries: {invalid_preview}", tag="WARN")

        if not ips:
            QMessageBox.warning(self, "No Valid IPs", "No valid IP addresses found. Check your input format.\n\nExamples:\n• 192.168.1.1\n• 192.168.1.1-50")
            return

        self._save_settings()
        self._set_scan_running(True)
        self.worker, self.worker_thread = self._start_worker(
            ips=ips,
            send_backlog=False,
            commands=[],
            do_upgrade=False,
            finished_slot=self.scan_done,
        )

    def _set_scan_running(self, running: bool) -> None:
        """Update UI state based on scan running status."""
        self._scan_running = running
        self.btn_start.setText("Cancel Scan" if running else "Start Scan")
        self.btn_run.setText("Cancel Run" if running else "Run Selected")
        # Disable other controls during scan
        self.txt_ranges.setEnabled(not running)
        self.txt_cmds.setEnabled(not running)
        self.spin_threads.setEnabled(not running)
        self.spin_timeout.setEnabled(not running)
        self.spin_retries.setEnabled(not running)
        self.txt_password.setEnabled(not running)
        self.btn_pick.setEnabled(not running)
        self.btn_select.setEnabled(not running)
        self.btn_lite.setEnabled(not running)
        self.btn_full.setEnabled(not running)

    def open_selection(self) -> None:
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

    def run_selected(self) -> None:
        if self._scan_running:
            # Cancel the current run
            if self.worker is not None:
                self.worker.executor.cancel()
                self.append_log("[INFO] Run cancellation requested...", tag="INFO")
            return

        if not (self.last_cmds_selected or self.last_fw_selected):
            QMessageBox.warning(self, "No selections", "Open selection window first")
            return
        selected_ips = set(self.last_cmds_selected + self.last_fw_selected)
        commands = [ln.strip() for ln in self.txt_cmds.toPlainText().splitlines() if ln.strip()]
        self._save_settings()
        self._set_scan_running(True)
        self.worker, self.worker_thread = self._start_worker(
            ips=list(selected_ips),
            send_backlog=bool(self.last_cmds_selected),
            commands=commands,
            do_upgrade=bool(self.last_fw_selected),
            selected_ips=selected_ips,
            cmd_ips=set(self.last_cmds_selected),
            fw_ips=set(self.last_fw_selected),
            finished_slot=self.on_finished,
        )

    def _start_worker(
        self,
        *,
        ips: List[str],
        send_backlog: bool,
        commands: List[str],
        do_upgrade: bool,
        finished_slot,
        selected_ips=None,
        cmd_ips=None,
        fw_ips=None,
    ) -> Tuple[Worker, QThread]:
        worker = Worker(
            ips,
            self.spin_threads.value(),
            self.output_folder,
            self.spin_timeout.value(),
            self.spin_retries.value(),
            DEFAULT_BACKOFF,
            send_backlog,
            commands,
            do_upgrade=do_upgrade,
            selected_ips=selected_ips,
            ota_urls=self.ota_urls,
            info_mode=self.info_mode,
            cmd_ips=cmd_ips,
            fw_ips=fw_ips,
            web_password=self.txt_password.text(),
        )
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.on_progress)
        worker.log_line.connect(self.append_log)
        worker.finished.connect(finished_slot)
        worker.finished.connect(lambda *_: thread.quit())
        worker.finished.connect(lambda *_: worker.deleteLater())
        thread.finished.connect(lambda *_: thread.deleteLater())
        thread.start()
        return worker, thread

    def _replace_last_results(self, result) -> None:
        devices = [r for r in (result.results or []) if r.Ok]
        self.last_results = sorted(devices, key=lambda r: (r.Name or "").lower())

    def _merge_last_results(self, result) -> None:
        """Update devices touched by a run without dropping the rest of the scan."""
        by_ip = {r.IP: r for r in self.last_results}
        for device in result.results or []:
            if not device.Ok:
                continue
            previous = by_ip.get(device.IP)
            if previous is not None:
                # A lite run leaves full-scan fields (Uptime, OtaUrl...) empty;
                # keep the earlier values instead of blanking them.
                for field in fields(device):
                    if field.name not in ("Error", "Action") and not getattr(device, field.name):
                        setattr(device, field.name, getattr(previous, field.name))
            by_ip[device.IP] = device
        self.last_results = sorted(by_ip.values(), key=lambda r: (r.Name or "").lower())

# ============================
# Entry
# ============================
def main() -> None:
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

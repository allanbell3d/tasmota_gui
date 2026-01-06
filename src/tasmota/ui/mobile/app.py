"""Root layout and application entrypoint for the mobile UI."""

from __future__ import annotations

import threading
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem

from tasmota.core.bulk import BulkRunResult, TasmotaBulkExecutor
from tasmota.core.commands import CommandLibraryError, load_command_library
from tasmota.constants import (
    DEFAULT_BACKOFF,
    DEFAULT_IP_RANGES,
    DEFAULT_RETRIES,
    DEFAULT_THREADS,
    DEFAULT_TIMEOUT,
    OTA_URLS,
)
from tasmota.core.utils import build_ip_list, is_valid_ip, parse_ip_range, validate_ip_ranges

from .boot import BootSequence
from .command_library import CommandLibraryPanel
from .discovery import DiscoveryPanel
from .log_panel import LogPanel
from .ota import OTAPanel
from .summary import SummaryPanel


class RootLayout(TabbedPanel):
    """Main application layout with tabbed navigation between panels.

    This is the central coordinator for the mobile UI. It:
    - Creates and manages all the panel widgets (Discovery, Commands, OTA, etc.)
    - Handles communication between panels (e.g., discovery results → summary)
    - Coordinates background operations (scans, command execution, OTA updates)
    - Manages the active executor thread and provides cancellation support

    Panel Workflow:
        Discovery → user scans network → results go to Summary + OTA panels
        Commands → user selects commands → can run on selected devices
        OTA → user queues devices → firmware updates run in batch
        Summary → shows all discovered devices → can queue to Commands/OTA
        Logs → shows real-time operation logs

    Thread Safety:
        Background operations run in worker threads to keep the UI responsive.
        Kivy's Clock.schedule_once is used to marshal results back to the main thread.
        The _cancel_requested flag and active_executor.cancel() provide cancellation.
    """

    __events__ = ("on_ready",)

    def __init__(self, **kwargs):
        ready_callback: Optional[Callable[[], None]] = kwargs.pop("ready_callback", None)
        super().__init__(**kwargs)
        self.do_default_tab = False
        self.tab_height = "42dp"

        # ----------------------------------------------------------------
        # State for tracking background operations
        # ----------------------------------------------------------------
        # Only one operation (scan/commands/OTA) runs at a time.
        # These track the active thread and executor so we can cancel if needed.
        self.active_thread: Optional[threading.Thread] = None
        self.active_executor: Optional[TasmotaBulkExecutor] = None
        self.tabs_by_title: Dict[str, TabbedPanelItem] = {}
        self._ready_callback = ready_callback
        self._ready_notified = False

        # ----------------------------------------------------------------
        # Create all panel widgets
        # ----------------------------------------------------------------
        # Each panel handles one aspect of the workflow.
        # Panels receive callback functions to communicate with this coordinator.
        self.discovery_panel = DiscoveryPanel(self._on_discover, self._cancel_active_run)
        self.command_panel = CommandLibraryPanel(self._on_run_commands, self._show_ota_tab)
        self.ota_panel = OTAPanel(self._on_run_ota, self._show_commands_tab)
        self.summary_panel = SummaryPanel(
            self._queue_summary_commands,
            self._queue_summary_firmware,
        )
        self.logs_panel = LogPanel()

        # Add panels as tabs in the navigation bar
        self._add_panel_tab("Discovery", self.discovery_panel)
        self._add_panel_tab("Commands", self.command_panel)
        self._add_panel_tab("OTA", self.ota_panel)
        self._add_panel_tab("Summary", self.summary_panel)
        self._add_panel_tab("Logs", self.logs_panel)

        # Load command library in background (may take a moment on slow devices)
        self._load_command_library()
        Clock.schedule_once(lambda *_: self._show_tab("Discovery"), 0)

        # ----------------------------------------------------------------
        # Cancellation and run context state
        # ----------------------------------------------------------------
        self._active_run_context: Optional[str] = None
        self._active_busy_panels: Tuple[BoxLayout, ...] = ()
        self._cancel_requested = False

        # ----------------------------------------------------------------
        # Performance optimization: batch rapid UI updates
        # ----------------------------------------------------------------
        # During scans, we receive many progress/log updates per second.
        # Instead of updating the UI for each one (which causes stuttering),
        # we batch them and flush every 50ms. This keeps the UI smooth.
        self._pending_progress: Tuple[int, int] = (0, 0)
        self._pending_logs: List[str] = []
        self._progress_trigger = Clock.create_trigger(self._flush_progress, 0.05)
        self._log_trigger = Clock.create_trigger(self._flush_logs, 0.05)

    def _add_panel_tab(self, title: str, panel: BoxLayout):
        """Add a tab containing a panel inside a scroll view."""

        tab = TabbedPanelItem(text=title)
        wrapped = self._prepare_panel_widget(panel)
        tab.add_widget(wrapped)
        self.add_widget(tab)
        self.tabs_by_title[title] = tab

    def _prepare_panel_widget(self, panel: BoxLayout):
        """Wrap panels in a scroll view unless they opt out."""

        if getattr(panel, "skip_scroll_wrapper", False):
            container = BoxLayout(
                orientation="vertical",
                size_hint=(1, 1),
                padding=dp(12),
                spacing=dp(8),
            )
            container.add_widget(panel)
            return container

        return self._wrap_in_scroll(panel)

    def _wrap_in_scroll(self, panel: BoxLayout) -> ScrollView:
        """Wrap the provided panel in a ScrollView for small displays."""

        panel.size_hint = (1, None)

        container = BoxLayout(orientation="vertical", size_hint=(1, None), padding=dp(12), spacing=dp(8))
        container.bind(minimum_height=container.setter("height"))
        container.add_widget(panel)

        scroll = ScrollView(size_hint=(1, 1))
        scroll.add_widget(container)

        def _sync_from_minimum(_: BoxLayout, __: float):
            self._sync_panel_height(panel, scroll.height)

        panel.bind(minimum_height=_sync_from_minimum)
        Clock.schedule_once(
            lambda _: self._sync_panel_height(panel, scroll.height),
            0,
        )
        scroll.bind(height=lambda inst, value: self._sync_panel_height(panel, value))
        return scroll

    @staticmethod
    def _sync_panel_height(panel: BoxLayout, target_height: float):
        """Ensure the panel has a visible height when wrapped in a scroll view."""

        minimum = getattr(panel, "minimum_height", 0) or 0
        target = target_height or 0
        panel.height = max(minimum, target)

    def _show_tab(self, title: str):
        tab = self.tabs_by_title.get(title)
        if tab is not None:
            self.switch_to(tab)

    def _show_commands_tab(self):
        self._show_tab("Commands")

    def _show_ota_tab(self):
        self._show_tab("OTA")

    def _queue_summary_commands(self, cmd_ips: List[str], _fw_ips: List[str]) -> Dict[str, str]:
        if not cmd_ips:
            self.logs_panel.append_line("[WARN] Select devices in the summary panel before queuing commands")
            return {"status": "error", "message": "Select at least one device to queue commands."}
        result = self.command_panel.stage_command_targets(cmd_ips)
        staged = result.get("staged", 0)
        total = result.get("total", 0)
        if staged == 0:
            self.logs_panel.append_line("[WARN] Unable to stage the selected devices for commands")
            return {"status": "error", "message": "No valid devices available for commands."}
        self._show_commands_tab()
        if staged < total:
            message = f"Staged {staged} of {total} device(s) for commands."
            self.logs_panel.append_line(f"[WARN] {message}")
            return {"status": "info", "message": message}
        message = f"Staged {staged} device(s) for commands."
        self.logs_panel.append_line(f"[INFO] {message}")
        return {"status": "success", "message": message}

    def _queue_summary_firmware(self, _cmd_ips: List[str], fw_ips: List[str]) -> Dict[str, str]:
        if not fw_ips:
            self.logs_panel.append_line("[WARN] Select devices in the summary panel before queuing firmware updates")
            return {"status": "error", "message": "Select at least one device for firmware updates."}
        result = self.ota_panel.stage_ota_targets(fw_ips)
        staged = result.get("staged", 0)
        total = result.get("total", 0)
        missing = result.get("missing", 0)
        if staged == 0:
            self.logs_panel.append_line("[WARN] Unable to stage the selected devices for firmware updates")
            return {"status": "error", "message": "No valid devices available for firmware updates."}
        self._show_ota_tab()
        platform_counts = result.get("by_platform", {}) or {}
        breakdown = ", ".join(
            f"{platform}: {count}"
            for platform, count in sorted(platform_counts.items())
            if count
        )
        info_message = f"Queued {staged} device(s) for firmware updates"
        if breakdown:
            info_message += f" ({breakdown})"
        self.logs_panel.append_line(f"[INFO] {info_message}")
        if missing:
            self.logs_panel.append_line(f"[WARN] Skipped {missing} device(s) that are not available in the OTA list")
            return {
                "status": "info",
                "message": f"Queued {staged} of {total} device(s) for firmware updates.",
            }
        return {"status": "success", "message": f"Queued {staged} device(s) for firmware updates."}

    def _load_command_library(self):
        def worker():
            try:
                records = load_command_library()
            except CommandLibraryError as exc:
                Clock.schedule_once(
                    lambda dt, err=exc: self._handle_command_library_error(err),
                    0,
                )
                return
            except Exception as exc:  # pragma: no cover - defensive for mobile builds
                Clock.schedule_once(
                    lambda dt, err=exc: self._handle_command_library_error(err),
                    0,
                )
                return
            Clock.schedule_once(lambda dt, rows=records: self._apply_command_library(rows), 0)

        threading.Thread(target=worker, daemon=True).start()

    def _handle_command_library_error(self, exc: Exception):
        self.logs_panel.append_line(f"[ERROR] {exc}")
        self.command_panel.set_library([])
        self._notify_ready()

    def _apply_command_library(self, records):
        self.command_panel.set_library(records)
        self._notify_ready()

    def _notify_ready(self):
        if self._ready_notified:
            return
        self._ready_notified = True
        self.dispatch("on_ready")
        if self._ready_callback is not None:
            try:
                self._ready_callback()
            except Exception:  # pragma: no cover - defensive callback protection
                pass

    def on_ready(self, *_):  # pragma: no cover - dispatched event hook
        pass

    # ------------------------------------------------------------------
    # Throttled update handlers for performance
    # ------------------------------------------------------------------
    def _flush_progress(self, dt):
        """Apply batched progress updates (called at most every 50ms)."""
        done, total = self._pending_progress
        self.summary_panel.update_progress(done, total)
        self.discovery_panel.update_progress(done, total)

    def _flush_logs(self, dt):
        """Apply batched log lines (called at most every 50ms)."""
        logs = self._pending_logs
        self._pending_logs = []
        for line in logs:
            self.logs_panel.append_line(line)

    def _task_running(self) -> bool:
        thread = self.active_thread
        return thread is not None and thread.is_alive()

    def _guard_active_task(self, message: str, *, requested_context: Optional[str] = None) -> bool:
        if not self._task_running():
            return False
        active = self._active_run_context or "generic"
        if requested_context and requested_context != active:
            message = (
                f"[WARN] Cannot start {self._format_context_name(requested_context)} "
                f"while {self._format_context_name(active)} is running"
            )
        self.logs_panel.append_line(message)
        return True

    @staticmethod
    def _format_context_name(context: str) -> str:
        mapping = {
            "discovery": "a discovery scan",
            "commands": "a command run",
            "ota": "an OTA update",
            "generic": "another task",
        }
        return mapping.get(context, "another task")

    def _cancel_active_run(self):
        self._cancel_requested = True
        if not self._task_running():
            self.discovery_panel.set_busy(False)
            self.discovery_panel.hide_progress()
            return

        self.logs_panel.append_line("[INFO] Cancelling active scan…")
        executor = self.active_executor
        if executor is not None:
            executor.cancel()

        for panel in self._active_busy_panels:
            if hasattr(panel, "set_busy"):
                panel.set_busy(False)

        self.discovery_panel.hide_progress()

    def _read_runtime_inputs(self) -> Tuple[int, float, int, str]:
        threads = self.discovery_panel.get_thread_count()
        timeout = float(self.discovery_panel.timeout_input.text or DEFAULT_TIMEOUT)
        retries = int(self.discovery_panel.retries_input.text or DEFAULT_RETRIES)
        return threads, timeout, retries, self.discovery_panel.info_mode

    @staticmethod
    def _ensure_list(values: Optional[Iterable[str]]) -> List[str]:
        """Convert an iterable to a list, creating a copy if already a list.

        Ensures we always return a new list to prevent unintended mutations
        of the caller's data.
        """
        if not values:
            return []
        if isinstance(values, list):
            return values.copy()  # Shallow copy - more efficient than list()
        if isinstance(values, (tuple, set)):
            return list(values)
        if isinstance(values, str):
            return [values]
        return list(values)

    def _on_discover(self, params: Dict):
        if self._guard_active_task("[WARN] Discovery already running", requested_context="discovery"):
            return

        self._cancel_requested = False
        self.discovery_panel.set_busy(True)
        self.logs_panel.append_line("[INFO] Preparing discovery run…")

        def prepare():
            try:
                ip_ranges = params.get("ip_ranges", DEFAULT_IP_RANGES)
                # Validate IP ranges and collect any invalid entries for logging
                ips, invalid_lines = validate_ip_ranges(ip_ranges)
            except Exception as exc:  # pragma: no cover - defensive for mobile builds
                Clock.schedule_once(
                    lambda dt, err=exc: self._handle_discovery_prep_error(err),
                    0,
                )
                return

            # Log invalid entries if any
            if invalid_lines:
                preview = ", ".join(invalid_lines[:3])
                if len(invalid_lines) > 3:
                    preview += f" (+{len(invalid_lines) - 3} more)"
                Clock.schedule_once(
                    lambda dt: self.logs_panel.append_line(f"[WARN] Skipped {len(invalid_lines)} invalid: {preview}"),
                    0,
                )

            if not ips:
                Clock.schedule_once(lambda dt: self._handle_discovery_no_ips(), 0)
                return

            Clock.schedule_once(lambda dt: self._start_discovery_with_ips(ips, params), 0)

        threading.Thread(target=prepare, daemon=True).start()

    def _handle_discovery_prep_error(self, exc: Exception):
        self.discovery_panel.set_busy(False)
        self.logs_panel.append_line(f"[ERROR] Failed to prepare discovery: {exc}")

    def _handle_discovery_no_ips(self):
        self.discovery_panel.set_busy(False)
        self.logs_panel.append_line("[WARN] No IP addresses to scan")

    def _start_discovery_with_ips(self, ips: Iterable[str], params: Dict):
        if self._guard_active_task("[WARN] Discovery already running", requested_context="discovery"):
            self.discovery_panel.set_busy(False)
            return

        if self._cancel_requested:
            self.discovery_panel.set_busy(False)
            self.discovery_panel.hide_progress()
            self.summary_panel.update_progress(0, 0)
            self.discovery_panel.update_progress(0, 0)
            self.logs_panel.append_line("[INFO] Discovery cancelled.")
            self._cancel_requested = False
            return

        ip_list = self._ensure_list(ips)
        self.logs_panel.append_line(f"[INFO] Starting discovery of {len(ip_list)} IPs")
        self.discovery_panel.update_progress(0, len(ip_list))
        self._run_executor(
            ips=ip_list,
            threads=self.discovery_panel.clamp_threads(params.get("threads", DEFAULT_THREADS)),
            timeout=params.get("timeout", DEFAULT_TIMEOUT),
            retries=params.get("retries", DEFAULT_RETRIES),
            info_mode=params.get("info_mode", "lite"),
            send_backlog=False,
            commands=[],
            do_upgrade=False,
            cmd_ips=[],
            fw_ips=[],
            selected_ips=[],
            ota_urls=OTA_URLS,
            context="discovery",
        )

    def _on_run_commands(self, options: Dict):
        if self._guard_active_task("[WARN] Commands already running", requested_context="commands"):
            return

        staged_ips = self._ensure_list(options.get("ips"))
        if not staged_ips:
            staged_ips = self.command_panel.get_staged_ips()
        if not staged_ips:
            staged_ips, _ = self.summary_panel.get_selected_ips()
        cmd_ips = self._ensure_list(staged_ips)
        if not cmd_ips:
            self.logs_panel.append_line("[WARN] Select one or more devices before running commands")
            return

        commands = options.get("commands", [])
        if not commands:
            self.logs_panel.append_line("[WARN] No backlog commands configured")
            return
        self.command_panel.stage_command_targets(cmd_ips)
        cmd_ips = self.command_panel.get_staged_ips()
        self.logs_panel.append_line(f"[INFO] Running commands for {len(cmd_ips)} devices")
        threads, timeout, retries, info_mode = self._read_runtime_inputs()
        self._run_executor(
            ips=cmd_ips,
            threads=threads,
            timeout=timeout,
            retries=retries,
            info_mode=info_mode,
            send_backlog=True,
            commands=commands,
            do_upgrade=False,
            cmd_ips=cmd_ips,
            fw_ips=[],
            selected_ips=cmd_ips,
            ota_urls=OTA_URLS,
            context="commands",
        )

    def _on_run_ota(self, payload: Dict):
        if self._guard_active_task("[WARN] OTA already running", requested_context="ota"):
            return
        queue = payload.get("queue", {}) if isinstance(payload, dict) else {}
        fw_ips = sorted({ip for ips in queue.values() for ip in ips})
        if not fw_ips:
            self.logs_panel.append_line("[WARN] Queue one or more devices for OTA updates")
            return

        ota_urls = payload.get("urls", OTA_URLS)
        self.logs_panel.append_line(f"[INFO] Running OTA updates for {len(fw_ips)} devices")
        self.ota_panel.clear_queue()
        threads, timeout, retries, info_mode = self._read_runtime_inputs()
        self._run_executor(
            ips=fw_ips,
            threads=threads,
            timeout=timeout,
            retries=retries,
            info_mode=info_mode,
            send_backlog=False,
            commands=[],
            do_upgrade=True,
            cmd_ips=[],
            fw_ips=fw_ips,
            selected_ips=fw_ips,
            ota_urls=ota_urls,
            context="ota",
        )

    def _run_executor(
        self,
        *,
        ips: Iterable[str],
        threads: int,
        timeout: float,
        retries: int,
        info_mode: str,
        send_backlog: bool,
        commands: Iterable[str],
        do_upgrade: bool,
        cmd_ips: Iterable[str],
        fw_ips: Iterable[str],
        selected_ips: Iterable[str],
        ota_urls: Dict[str, str],
        context: str = "generic",
    ):
        busy_panels = self._panels_for_context(context)
        for panel in busy_panels:
            if hasattr(panel, "set_busy"):
                panel.set_busy(True)
        self._active_busy_panels = busy_panels
        self._active_run_context = context
        ip_list = self._ensure_list(ips)
        self.summary_panel.update_progress(0, len(ip_list))
        self.discovery_panel.update_progress(0, len(ip_list))
        self.discovery_panel.show_progress()
        threads = self.discovery_panel.clamp_threads(threads)

        def progress_cb(done: int, total: int):
            # Store pending progress and trigger throttled update
            self._pending_progress = (done, total)
            self._progress_trigger()

        def log_cb(line: str, tag: str):
            # Store pending log and trigger throttled flush
            self._pending_logs.append(line)
            self._log_trigger()

        executor = TasmotaBulkExecutor(
            ips=ip_list,
            threads=threads,
            out_dir=None,
            timeout=timeout,
            retries=retries,
            backoff=DEFAULT_BACKOFF,
            send_backlog=send_backlog,
            commands=self._ensure_list(commands),
            do_upgrade=do_upgrade,
            selected_ips=self._ensure_list(selected_ips),
            ota_urls=dict(ota_urls),
            info_mode=info_mode,
            cmd_ips=self._ensure_list(cmd_ips),
            fw_ips=self._ensure_list(fw_ips),
            progress_callback=progress_cb,
            log_callback=log_cb,
        )
        self.active_executor = executor
        self._cancel_requested = False

        def worker():
            result: Optional[BulkRunResult] = None
            try:
                result = executor.run()
            except Exception as exc:
                Clock.schedule_once(
                    lambda dt, err=exc: self.logs_panel.append_line(f"[ERROR] {err}"),
                    0,
                )
            Clock.schedule_once(lambda dt: self._on_executor_complete(result), 0)

        thread = threading.Thread(target=worker, daemon=True)
        self.active_thread = thread
        thread.start()

    def _on_executor_complete(self, result: Optional[BulkRunResult]):
        for panel in self._active_busy_panels:
            if hasattr(panel, "set_busy"):
                panel.set_busy(False)
        self._active_busy_panels = ()
        self.discovery_panel.hide_progress()
        executor = self.active_executor
        self.active_executor = None
        self.active_thread = None
        context = self._active_run_context or "generic"
        self._active_run_context = None
        was_cancelled = self._cancel_requested or (executor.was_cancelled if executor else False)
        self._cancel_requested = False
        if was_cancelled and context == "discovery":
            self.summary_panel.update_progress(0, 0)
            self.discovery_panel.update_progress(0, 0)
            self.logs_panel.append_line("[INFO] Discovery cancelled.")
            return

        if result is not None:
            replace_summary = context == "discovery"
            self.summary_panel.set_results(result.results, replace=replace_summary)
            self.ota_panel.set_results(result.results)
            self.logs_panel.append_line("[INFO] Completed run.")
        else:
            self.summary_panel.update_progress(0, 0)

    def _panels_for_context(self, context: str) -> Tuple[BoxLayout, ...]:
        mapping: Dict[str, Tuple[BoxLayout, ...]] = {
            "discovery": (self.discovery_panel,),
            "commands": (self.command_panel,),
            "ota": (self.ota_panel,),
        }
        return mapping.get(context, (self.discovery_panel, self.command_panel, self.ota_panel))


class TasmotaKivyApp(App):
    """Application wrapper."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._boot_sequence = BootSequence()

    def build(self):
        self.title = "Tasmota Bulk Tool"
        self.root_layout = RootLayout(ready_callback=self._boot_sequence.reveal)
        return self._boot_sequence.attach(self.root_layout)


def main():
    TasmotaKivyApp().run()


if __name__ == "__main__":
    main()

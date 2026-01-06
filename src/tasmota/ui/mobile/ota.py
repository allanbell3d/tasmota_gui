"""OTA planner widgets for the mobile UI."""

from __future__ import annotations

from typing import Callable, Dict, Iterable, List, Optional, Set

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from tasmota.constants import BUTTON_DEFAULT_BG, BUTTON_SELECTED_BG, DEVICE_ROW_HEIGHT_DP, OTA_URLS

from .widgets.common import BorderedBoxLayout, device_key, get_device_platform
from .widgets.device_row import DeviceRecycleView, OTARowView


class OTAPanel(BoxLayout):
    """Dedicated OTA update workflow with queue management."""

    def __init__(
        self,
        run_callback: Callable[[Dict], None],
        goto_commands_callback: Optional[Callable[[], None]] = None,
        **kwargs,
    ):
        super().__init__(orientation="vertical", spacing=dp(8), **kwargs)
        self.run_callback = run_callback
        self.goto_commands_callback = goto_commands_callback

        # Data storage for RecycleView
        self._device_data: Dict[str, Dict] = {}  # IP -> device data dict
        # Cache sorted data to avoid re-sorting on every filter change
        self._sorted_cache: List[Dict] = []
        self._cached_reverse: bool = False
        self.queue: Dict[str, Set[str]] = {"ESP8266": set(), "ESP32": set()}

        self.add_widget(Label(text="OTA Updates", size_hint_y=None, height=dp(36)))

        label_width = dp(110)

        filters_section = BorderedBoxLayout(
            orientation="vertical",
            size_hint=(1, None),
            spacing=dp(8),
            padding=dp(8),
        )
        filters_section.bind(minimum_height=filters_section.setter("height"))

        filters_grid = GridLayout(cols=1, size_hint=(1, None), spacing=dp(8))
        filters_grid.bind(minimum_height=filters_grid.setter("height"))

        reduced_row_height = dp(56 * 0.6)
        platform_row = BoxLayout(size_hint_y=None, height=reduced_row_height, spacing=dp(8))
        platform_row.add_widget(Label(text="Platform", size_hint=(None, 1), width=label_width))
        self.platform_filter_value = "All"
        platform_buttons = BoxLayout(orientation="horizontal", spacing=dp(8), size_hint=(1, 1))
        self.platform_filter_buttons = {}

        def add_platform_button(platform: str):
            button = Button(
                text=platform,
                size_hint=(0.5, 1),
                background_normal="",
            )

            def on_release(*_):
                self._toggle_platform_filter(platform)

            button.bind(on_release=on_release)
            self.platform_filter_buttons[platform] = button
            platform_buttons.add_widget(button)

        add_platform_button("ESP8266")
        add_platform_button("ESP32")
        platform_row.add_widget(platform_buttons)
        self._update_platform_filter_buttons()
        filters_grid.add_widget(platform_row)

        name_row = BoxLayout(size_hint_y=None, height=reduced_row_height, spacing=dp(8))
        name_row.add_widget(Label(text="Name", size_hint=(None, 1), width=label_width))
        self.name_filter_input = TextInput(
            hint_text="Filter",
            multiline=False,
            size_hint=(1, 1),
        )
        name_row.add_widget(self.name_filter_input)
        filters_grid.add_widget(name_row)

        ip_row = BoxLayout(size_hint_y=None, height=reduced_row_height, spacing=dp(8))
        ip_row.add_widget(Label(text="IP", size_hint=(None, 1), width=label_width))
        self.ip_filter_input = TextInput(
            hint_text="Filter",
            multiline=False,
            size_hint=(1, 1),
        )
        ip_row.add_widget(self.ip_filter_input)
        self.sort_spinner = Spinner(
            text="Name (A-Z)",
            values=("Name (A-Z)", "Name (Z-A)"),
            size_hint=(1, 1),
        )
        ip_row.add_widget(self.sort_spinner)
        filters_grid.add_widget(ip_row)

        filters_section.add_widget(filters_grid)

        selection_row = BoxLayout(size_hint_y=None, height=dp(52 * 0.6), spacing=dp(8))
        self.btn_select_all = Button(text="Select All")
        self.btn_select_all.bind(on_release=lambda *_: self._set_all_selection(True))
        selection_row.add_widget(self.btn_select_all)
        self.btn_clear_selection = Button(text="Clear")
        self.btn_clear_selection.bind(on_release=lambda *_: self._set_all_selection(False))
        selection_row.add_widget(self.btn_clear_selection)
        filters_section.add_widget(selection_row)

        self.add_widget(filters_section)

        # RecycleView for efficient row rendering (using shared component)
        self.recycle_view = DeviceRecycleView(OTARowView, row_height=dp(DEVICE_ROW_HEIGHT_DP), size_hint=(1, 1))
        self.add_widget(self.recycle_view)

        # Debounce rebuilds so rapid filter updates don't thrash the UI.
        self._rebuild_trigger = Clock.create_trigger(self._rebuild_display, 0.15)
        self.name_filter_input.bind(text=self._schedule_rebuild)
        self.ip_filter_input.bind(text=self._schedule_rebuild)
        self.sort_spinner.bind(text=self._schedule_rebuild)

        url_grid = BorderedBoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(220 * 0.4 * 1.3),
            spacing=dp(12),
            padding=dp(8),
        )
        esp8266_box = BoxLayout(orientation="vertical", spacing=dp(6), size_hint=(0.5, 1))
        esp8266_box.add_widget(
            Label(text="ESP8266 OTA URL", size_hint=(1, None), height=dp(26 * 1.3))
        )
        self.esp8266_input = TextInput(
            text=OTA_URLS["ESP8266"],
            multiline=False,
            size_hint=(1, None),
            height=dp(44 * 0.65),
        )
        esp8266_box.add_widget(self.esp8266_input)
        self.btn_queue_esp8266 = Button(text="Queue (ESP8266)", size_hint_y=None, height=dp(44 * 0.5))
        self.btn_queue_esp8266.bind(on_release=lambda *_: self._queue_selected("ESP8266"))
        esp8266_box.add_widget(self.btn_queue_esp8266)
        url_grid.add_widget(esp8266_box)

        esp32_box = BoxLayout(orientation="vertical", spacing=dp(6), size_hint=(0.5, 1))
        esp32_box.add_widget(Label(text="ESP32 OTA URL", size_hint=(1, None), height=dp(26 * 1.3)))
        self.esp32_input = TextInput(
            text=OTA_URLS["ESP32"],
            multiline=False,
            size_hint=(1, None),
            height=dp(44 * 0.65),
        )
        esp32_box.add_widget(self.esp32_input)
        self.btn_queue_esp32 = Button(text="Queue (ESP32)", size_hint_y=None, height=dp(44 * 0.5))
        self.btn_queue_esp32.bind(on_release=lambda *_: self._queue_selected("ESP32"))
        esp32_box.add_widget(self.btn_queue_esp32)
        url_grid.add_widget(esp32_box)
        self.add_widget(url_grid)

        queue_row = BoxLayout(size_hint_y=None, height=dp(52 * 0.5), spacing=dp(8))
        self.queue_status_label = Label(text="Queued: 0", size_hint=(1, 1))
        queue_row.add_widget(self.queue_status_label)
        self.btn_clear_queue = Button(text="Clear Queue", size_hint=(None, 1), width=dp(180))
        self.btn_clear_queue.bind(on_release=lambda *_: self._clear_queue())
        queue_row.add_widget(self.btn_clear_queue)
        self.add_widget(queue_row)

        action_row = BoxLayout(size_hint_y=None, height=dp(60), spacing=dp(8))
        self.btn_run = Button(text="Run OTA Updates")
        self.btn_run.bind(on_release=lambda *_: self._run_updates())
        action_row.add_widget(self.btn_run)
        self.btn_back = Button(text="Back to Commands")
        self.btn_back.bind(on_release=lambda *_: self._goto_commands())
        action_row.add_widget(self.btn_back)
        self.add_widget(action_row)

        self._rebuild_display()
        self._update_queue_status()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_results(self, results):
        """Set device results and rebuild display."""
        filtered = [device for device in results or [] if getattr(device, "Ok", False)]

        # Build data dict for RecycleView
        new_data: Dict[str, Dict] = {}
        for device in filtered:
            key = device_key(device)
            existing = self._device_data.get(key)
            platform = get_device_platform(device)
            name = device.Name or getattr(device, "Hostname", "") or device.IP
            data = {
                "ip": str(device.IP or ""),
                "name": name,
                "platform": platform,
                "version": str(getattr(device, "Version", "") or ""),
                "hardware": str(getattr(device, "Hardware", "") or ""),
                "selected": existing.get("selected", False) if existing else False,
                "queue_platform": "",  # Will be updated by _update_queue_status
            }
            new_data[key] = data

        self._device_data = new_data
        # Invalidate sorted cache when data changes
        self._sorted_cache = []
        self._schedule_rebuild()
        self._update_queue_status()

    def stage_ota_targets(self, ips: Iterable[str]) -> Dict[str, int]:
        """Stage devices for OTA by IP addresses."""
        sanitized = [str(ip).strip() for ip in ips if ip and str(ip).strip()]
        seen: Set[str] = set()
        platform_counts: Dict[str, int] = {}
        staged = 0

        for ip in sanitized:
            if not ip or ip in seen:
                continue
            seen.add(ip)
            data = self._device_data.get(ip)
            if data is None:
                continue

            # Remove from other queues
            for bucket in self.queue.values():
                bucket.discard(ip)

            # Add to appropriate queue
            platform = data.get("platform", "")
            self.queue.setdefault(platform, set()).add(ip)
            platform_counts[platform] = platform_counts.get(platform, 0) + 1
            staged += 1

        self._update_queue_status()
        return {
            "staged": staged,
            "total": len(seen),
            "missing": len(seen) - staged,
            "by_platform": platform_counts,
        }

    def clear_queue(self):
        """Public method to clear the queue."""
        self._clear_queue()

    def set_busy(self, busy: bool):
        """Enable/disable UI during operations."""
        self.btn_select_all.disabled = busy
        self.btn_clear_selection.disabled = busy
        self.btn_queue_esp8266.disabled = busy
        self.btn_queue_esp32.disabled = busy
        for button in getattr(self, "platform_filter_buttons", {}).values():
            button.disabled = busy
        self.btn_run.disabled = busy
        self.btn_clear_queue.disabled = busy
        self.esp8266_input.disabled = busy
        self.esp32_input.disabled = busy
        self.name_filter_input.disabled = busy
        self.ip_filter_input.disabled = busy
        self.sort_spinner.disabled = busy

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _goto_commands(self):
        if self.goto_commands_callback:
            self.goto_commands_callback()

    def _toggle_platform_filter(self, platform: str):
        current = getattr(self, "platform_filter_value", "All")
        if current == platform:
            self.platform_filter_value = "All"
        else:
            self.platform_filter_value = platform
        self._update_platform_filter_buttons()
        self._schedule_rebuild()

    def _update_platform_filter_buttons(self):
        selected = getattr(self, "platform_filter_value", "All")
        for platform, button in getattr(self, "platform_filter_buttons", {}).items():
            if selected == platform:
                button.background_color = BUTTON_SELECTED_BG
                button.color = (1, 1, 1, 1)
            else:
                button.background_color = BUTTON_DEFAULT_BG
                button.color = (0, 0, 0, 1)

    def _schedule_rebuild(self, *_):
        if self._rebuild_trigger is not None:
            self._rebuild_trigger()

    def _rebuild_display(self, *_):
        """Rebuild the RecycleView data based on filter and sort.

        Uses a sorted cache to avoid re-sorting when only filters change.
        The cache is invalidated when data changes or sort direction changes.
        """
        platform_filter = getattr(self, "platform_filter_value", "All")
        name_filter = (self.name_filter_input.text or "").strip().lower() if hasattr(self, "name_filter_input") else ""
        ip_filter = (self.ip_filter_input.text or "").strip().lower() if hasattr(self, "ip_filter_input") else ""
        reverse = (self.sort_spinner.text or "Name (A-Z)") == "Name (Z-A)" if hasattr(self, "sort_spinner") else False

        # Re-sort only if sort direction changed or cache is invalid
        if not self._sorted_cache or self._cached_reverse != reverse:
            def sort_key(data: Dict):
                return (data.get("name", "") or data.get("ip", "")).strip().lower()

            self._sorted_cache = sorted(self._device_data.values(), key=sort_key, reverse=reverse)
            self._cached_reverse = reverse

        # Filter from cached sorted data
        def matches_filter(data: Dict) -> bool:
            # Platform filter
            if platform_filter != "All" and data.get("platform", "") != platform_filter:
                return False
            # Name filter - check fields directly to avoid string concatenation
            if name_filter:
                name_lower = data.get("name", "").lower()
                hardware_lower = data.get("hardware", "").lower()
                if name_filter not in name_lower and name_filter not in hardware_lower:
                    return False
            # IP filter
            if ip_filter and ip_filter not in data.get("ip", "").lower():
                return False
            return True

        # Apply filters - no need to check if any filter is active, comprehension handles it
        visible_data = [d for d in self._sorted_cache if matches_filter(d)]

        # Update RecycleView data
        self.recycle_view.data = visible_data

    def _set_all_selection(self, value: bool):
        """Select or deselect all visible devices."""
        for data in self.recycle_view.data:
            data["selected"] = value
        # Force refresh
        self.recycle_view.refresh_from_data()

    def _queue_selected(self, platform: str):
        """Queue selected devices for the given platform."""
        for data in self.recycle_view.data:
            if data.get("selected", False):
                ip = data.get("ip", "").strip()
                if not ip:
                    continue
                # Remove from other queues
                for other in self.queue.values():
                    other.discard(ip)
                # Add to target queue
                if platform in self.queue:
                    self.queue[platform].add(ip)
                # Deselect
                data["selected"] = False

        self._update_queue_status()
        self.recycle_view.refresh_from_data()

    def _clear_queue(self):
        """Clear all queued devices."""
        for key in self.queue:
            self.queue[key].clear()
        self._update_queue_status()

    def _update_queue_status(self):
        """Update queue status label and device queue_platform fields."""
        valid_ips = set(self._device_data.keys())
        for key in self.queue:
            # Use set intersection for efficiency
            self.queue[key] &= valid_ips

        queued_total = sum(len(ips) for ips in self.queue.values())
        self.queue_status_label.text = f"Queued: {queued_total}"

        # Update queue_platform in data dicts
        for data in self._device_data.values():
            ip = data.get("ip", "").strip()
            queue_platform = ""
            for key, ips in self.queue.items():
                if ip in ips:
                    queue_platform = key
                    break
            data["queue_platform"] = queue_platform

        # Refresh display if data changed
        if hasattr(self, "recycle_view"):
            self._schedule_rebuild()

    def _get_ota_urls(self) -> Dict[str, str]:
        """Get configured OTA URLs."""
        return {
            "ESP8266": self.esp8266_input.text.strip() or OTA_URLS["ESP8266"],
            "ESP32": self.esp32_input.text.strip() or OTA_URLS["ESP32"],
        }

    def _run_updates(self):
        """Execute OTA updates for queued devices."""
        payload = {
            "queue": {key: sorted(ips) for key, ips in self.queue.items() if ips},
            "urls": self._get_ota_urls(),
        }
        if not any(payload["queue"].values()):
            return
        if self.run_callback:
            self.run_callback(payload)

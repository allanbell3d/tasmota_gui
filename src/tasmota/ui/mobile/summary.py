"""Summary panel widgets for the mobile UI."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from tasmota.constants import TOAST_ERROR_COLOR, TOAST_INFO_COLOR, TOAST_SUCCESS_COLOR

from .widgets.common import (
    SUMMARY_HEADER_TEXT_COLOR,
    BorderedBoxLayout,
    bind_auto_wrap,
    device_key,
    format_progress,
    get_device_platform,
)
from .widgets.device_row import DeviceRecycleView, SummaryRowView


class SummaryHeader(BorderedBoxLayout):
    """Header row for the summary table."""

    def __init__(self, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(44))
        kwargs.setdefault("spacing", dp(8))
        kwargs.setdefault("padding", (0, dp(6)))
        super().__init__(**kwargs)

        cmd_label = Label(
            text="Cmd",
            size_hint=(None, 1),
            width=dp(88),
            halign="center",
            valign="middle",
            color=SUMMARY_HEADER_TEXT_COLOR,
        )
        cmd_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        self.add_widget(cmd_label)

        ota_label = Label(
            text="OTA",
            size_hint=(None, 1),
            width=dp(88),
            halign="center",
            valign="middle",
            color=SUMMARY_HEADER_TEXT_COLOR,
        )
        ota_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        self.add_widget(ota_label)

        name_label = Label(text="Name", halign="left", valign="middle", color=SUMMARY_HEADER_TEXT_COLOR)
        bind_auto_wrap(name_label)
        self.add_widget(name_label)


class SummaryPanel(BoxLayout):
    """Displays the list of discovered devices and current progress."""

    CONTROLS_BREAKPOINT = 720

    def __init__(
        self,
        queue_commands_callback: Optional[Callable[[List[str], List[str]], Optional[Dict]]] = None,
        queue_firmware_callback: Optional[Callable[[List[str], List[str]], Optional[Dict]]] = None,
        **kwargs,
    ):
        super().__init__(orientation="vertical", spacing=dp(8), **kwargs)
        self.queue_commands_callback = queue_commands_callback
        self.queue_firmware_callback = queue_firmware_callback

        self.progress_label = Label(text="Progress: 0 / 0", size_hint_y=None, height=dp(40))
        self.summary_label = Label(text="Devices: 0", size_hint_y=None, height=dp(36))
        self.add_widget(self.progress_label)
        self.add_widget(self.summary_label)

        self.controls_wrapper = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(6),
        )
        self.controls_wrapper.bind(minimum_height=self.controls_wrapper.setter("height"))
        self.add_widget(self.controls_wrapper)

        self.filter_label = Label(
            text="Filter",
            halign="center",
            valign="middle",
            size_hint=(0.3, 1),
        )
        self.filter_label.bind(size=lambda inst, size: setattr(inst, "text_size", size))

        self.filter_input = TextInput(
            hint_text="Search devices",
            multiline=False,
            size_hint=(0.7, 1),
            height=dp(48),
        )
        self.filter_input.bind(height=self._update_filter_padding)
        self.filter_input.bind(font_size=self._update_filter_padding)
        Clock.schedule_once(lambda *_: self._update_filter_padding(), 0)

        self.sort_label = Label(
            text="Sort",
            halign="center",
            valign="middle",
            size_hint=(0.3, 1),
        )
        self.sort_label.bind(size=lambda inst, size: setattr(inst, "text_size", size))

        self.sort_spinner = Spinner(
            text="Name",
            values=("Name", "Device Type", "IP", "Firmware"),
            size_hint=(0.7, 1),
            height=dp(48),
        )

        header = SummaryHeader(size_hint_y=None, height=dp(44))

        # RecycleView for efficient row rendering (using shared component)
        self.recycle_view = DeviceRecycleView(SummaryRowView, size_hint=(1, 1))

        self.queue_actions_box = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(4),
        )
        self.queue_actions_box.bind(minimum_height=self.queue_actions_box.setter("height"))

        self.queue_buttons_row = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        self.queue_commands_button = Button(text="Queue Commands")
        self.queue_commands_button.size_hint_min_x = dp(160)
        self.queue_commands_button.bind(on_release=lambda *_: self._on_queue_commands())
        self.queue_fw_button = Button(text="Queue Firmware Updates")
        self.queue_fw_button.size_hint_min_x = dp(160)
        self.queue_fw_button.bind(on_release=lambda *_: self._on_queue_firmware())
        self.queue_buttons_row.add_widget(self.queue_commands_button)
        self.queue_buttons_row.add_widget(self.queue_fw_button)
        self.queue_actions_box.add_widget(self.queue_buttons_row)

        self.queue_feedback_label = Label(
            text="",
            size_hint=(1, None),
            height=0,
            opacity=0,
            halign="left",
            valign="middle",
            color=TOAST_INFO_COLOR,
        )
        self.queue_feedback_label.bind(
            size=lambda inst, size: setattr(inst, "text_size", (size[0], None)),
            texture_size=lambda inst, size: setattr(
                inst, "height", size[1] + dp(4) if inst.text else 0
            ),
        )
        self.queue_actions_box.add_widget(self.queue_feedback_label)

        self.add_widget(header)
        self.add_widget(self.recycle_view)
        self.add_widget(self.queue_actions_box)

        # Data storage - RecycleView uses data list directly
        self._device_data: Dict[str, Dict] = {}  # IP -> device data dict
        # Cache sorted data to avoid re-sorting on every filter change
        # Only re-sort when sort_mode changes or data is replaced
        self._sorted_cache: List[Dict] = []
        self._cached_sort_mode: str = ""
        self._rebuild_trigger = Clock.create_trigger(self._rebuild_display, 0.15)

        self.filter_input.bind(text=self._schedule_rebuild)
        self.sort_spinner.bind(text=self._schedule_rebuild)

        self._build_controls_layout(Window.width)
        self._update_queue_layout(Window.width)
        Window.bind(size=self._on_window_resize)

    def update_progress(self, done: int, total: int):
        def _apply(_: float):
            pct, capped_done, capped_total = format_progress(done, total)
            self.progress_label.text = f"Progress: {capped_done} / {capped_total} ({pct}%)"

        Clock.schedule_once(_apply, 0)

    def set_results(self, results, *, replace: bool = True):
        def _apply(_: float):
            filtered = [device for device in results or [] if getattr(device, "Ok", False)]

            if replace:
                self._device_data = {}

            for device in filtered:
                key = device_key(device)
                existing = self._device_data.get(key)

                # Build data dict for RecycleView
                platform = get_device_platform(device)
                name = device.Name or getattr(device, "Hostname", "") or device.IP
                data = {
                    "ip": str(device.IP or ""),
                    "name": name,
                    "platform": platform,
                    "version": str(getattr(device, "Version", "") or ""),
                    "hardware": str(getattr(device, "Hardware", "") or ""),
                    "cmd_selected": existing.get("cmd_selected", False) if existing else False,
                    "ota_selected": existing.get("ota_selected", False) if existing else False,
                }
                self._device_data[key] = data

            # Invalidate sorted cache when data changes
            self._sorted_cache = []
            self._schedule_rebuild()

        Clock.schedule_once(_apply, 0)

    def get_selected_ips(self) -> Tuple[List[str], List[str]]:
        cmd_ips: List[str] = []
        fw_ips: List[str] = []
        # Read from RecycleView data (which is updated by checkbox callbacks)
        for data in self.recycle_view.data:
            ip = data.get("ip", "")
            if data.get("cmd_selected", False):
                cmd_ips.append(ip)
            if data.get("ota_selected", False):
                fw_ips.append(ip)
        return cmd_ips, fw_ips

    def clear(self):
        self._device_data = {}
        self._sorted_cache = []
        self.recycle_view.data = []
        self.update_progress(0, 0)
        self.summary_label.text = "Devices: 0"

    def _on_window_resize(self, instance, size):
        width = size[0] if isinstance(size, (tuple, list)) else Window.width
        self._build_controls_layout(width)
        self._update_queue_layout(width)

    def _build_controls_layout(self, width: float):
        widgets = (self.filter_label, self.filter_input, self.sort_label, self.sort_spinner)
        for widget in widgets:
            parent = widget.parent
            if parent is not None:
                parent.remove_widget(widget)
        self.controls_wrapper.clear_widgets()

        is_wide = width >= self.CONTROLS_BREAKPOINT
        base_row_height = dp(52)
        compact_row_height = base_row_height * 0.6
        row_kwargs = dict(size_hint_y=None, spacing=dp(8))
        if is_wide:
            row = BorderedBoxLayout(**row_kwargs, height=compact_row_height, padding=(dp(6), dp(6)))
            row.add_widget(self.filter_label)
            row.add_widget(self.filter_input)
            row.add_widget(self.sort_label)
            row.add_widget(self.sort_spinner)
            self.controls_wrapper.add_widget(row)
        else:
            filter_row = BorderedBoxLayout(**row_kwargs, height=compact_row_height, padding=(dp(6), dp(6)))
            sort_row = BoxLayout(**row_kwargs, height=base_row_height)
            filter_row.add_widget(self.filter_label)
            filter_row.add_widget(self.filter_input)
            sort_row.add_widget(self.sort_label)
            sort_row.add_widget(self.sort_spinner)
            self.controls_wrapper.add_widget(filter_row)
            self.controls_wrapper.add_widget(sort_row)

        self.filter_label.size_hint_x = 0.25 if is_wide else 0.35
        self.sort_label.size_hint_x = 0.25 if is_wide else 0.35
        self.filter_label.size_hint_min_x = dp(80)
        self.sort_label.size_hint_min_x = dp(80)
        self.filter_input.size_hint_x = 1 - self.filter_label.size_hint_x
        self.sort_spinner.size_hint_x = 1 - self.sort_label.size_hint_x

    def _update_filter_padding(self, *_):
        if not hasattr(self, "filter_input"):
            return
        line_height = getattr(self.filter_input, "line_height", 0) or 0
        padding_y = max(0.0, (self.filter_input.height - line_height) / 2)
        padding_x = dp(10)
        self.filter_input.padding = (padding_x, padding_y)

    def _update_queue_layout(self, width: float):
        is_wide = width >= self.CONTROLS_BREAKPOINT
        if is_wide:
            self.queue_buttons_row.orientation = "horizontal"
            self.queue_buttons_row.height = dp(52)
            self.queue_commands_button.size_hint_x = 0.5
            self.queue_fw_button.size_hint_x = 0.5
        else:
            self.queue_buttons_row.orientation = "vertical"
            button_height = dp(52)
            self.queue_buttons_row.height = button_height * 2 + dp(8)
            self.queue_commands_button.size_hint_x = 1
            self.queue_fw_button.size_hint_x = 1

    def _set_feedback(self, message: str, status: str = "info"):
        palette = {
            "info": TOAST_INFO_COLOR,
            "success": TOAST_SUCCESS_COLOR,
            "error": TOAST_ERROR_COLOR,
        }
        self.queue_feedback_label.color = palette.get(status, TOAST_INFO_COLOR)
        self.queue_feedback_label.text = message or ""
        self.queue_feedback_label.opacity = 1 if message else 0

    def _on_queue_commands(self):
        cmd_ips, fw_ips = self.get_selected_ips()
        if not cmd_ips:
            self._set_feedback("Select at least one device to queue commands.", "error")
            return
        result = None
        if self.queue_commands_callback:
            result = self.queue_commands_callback(cmd_ips, fw_ips)
        if result and isinstance(result, dict) and result.get("message"):
            self._set_feedback(result["message"], result.get("status", "info"))
        elif cmd_ips:
            self._set_feedback(f"Staged {len(cmd_ips)} device(s) for commands.", "success")

    def _on_queue_firmware(self):
        cmd_ips, fw_ips = self.get_selected_ips()
        if not fw_ips:
            self._set_feedback("Select at least one device for firmware updates.", "error")
            return
        result = None
        if self.queue_firmware_callback:
            result = self.queue_firmware_callback(cmd_ips, fw_ips)
        if result and isinstance(result, dict) and result.get("message"):
            self._set_feedback(result["message"], result.get("status", "info"))
        elif fw_ips:
            self._set_feedback(f"Queued {len(fw_ips)} device(s) for firmware updates.", "success")

    def _schedule_rebuild(self, *_):
        if self._rebuild_trigger is not None:
            self._rebuild_trigger()

    def _rebuild_display(self, *_):
        """Rebuild the RecycleView data based on filter and sort.

        Uses a sorted cache to avoid re-sorting when only the filter changes.
        The cache is invalidated when data is replaced or sort mode changes.
        """
        query = (self.filter_input.text or "").strip().lower()
        sort_mode = self.sort_spinner.text if hasattr(self, "sort_spinner") else "Name"

        # Re-sort only if sort mode changed or cache is invalid
        if not self._sorted_cache or self._cached_sort_mode != sort_mode:
            def build_key(data: Dict):
                name = data.get("name", "").lower()
                if sort_mode == "Device Type":
                    primary = data.get("platform", "").lower()
                elif sort_mode == "IP":
                    primary = data.get("ip", "")
                elif sort_mode == "Firmware":
                    primary = data.get("version", "").lower()
                else:
                    primary = name
                return (primary, name, data.get("ip", ""))

            self._sorted_cache = sorted(self._device_data.values(), key=build_key)
            self._cached_sort_mode = sort_mode

        # Filter from cached sorted data
        if not query:
            visible_data = list(self._sorted_cache)
        else:
            def matches_filter(data: Dict) -> bool:
                values = [
                    data.get("name", ""),
                    data.get("ip", ""),
                    data.get("hardware", ""),
                    data.get("version", ""),
                    data.get("platform", ""),
                ]
                return any(query in v.lower() for v in values if v)

            visible_data = [d for d in self._sorted_cache if matches_filter(d)]

        # Update RecycleView data
        self.recycle_view.data = visible_data
        self.summary_label.text = f"Devices: {len(visible_data)}"

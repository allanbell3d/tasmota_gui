"""Summary panel widgets for the mobile UI."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from .widgets.common import (
    CHECKBOX_BLACK,
    ESP_PLATFORM_COLORS,
    SUMMARY_HEADER_TEXT_COLOR,
    BorderedBoxLayout,
    get_device_platform,
)


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
        name_label.bind(width=lambda inst, _: setattr(inst, "text_size", (inst.width, None)))
        self.add_widget(name_label)


class SummaryRow(BorderedBoxLayout):
    """Row showing a discovered device with action toggles."""

    def __init__(self, device, **kwargs):
        kwargs.setdefault("orientation", "horizontal")
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(72))
        kwargs.setdefault("spacing", dp(8))
        super().__init__(**kwargs)
        self.device = device
        self.platform = get_device_platform(device)
        checkbox_size = (dp(40), dp(40))
        self.cmd_checkbox = CheckBox(size_hint=(None, None), size=checkbox_size, color=CHECKBOX_BLACK)
        self.fw_checkbox = CheckBox(size_hint=(None, None), size=checkbox_size, color=CHECKBOX_BLACK)

        with self.canvas.before:
            self._bg_color = Color(*ESP_PLATFORM_COLORS.get(self.platform, ESP_PLATFORM_COLORS["UNKNOWN"]))
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_background, size=self._update_background)
        self._apply_platform_color()

        cmd_holder = AnchorLayout(anchor_x="center", anchor_y="center", size_hint=(None, 1), width=dp(88))
        cmd_holder.add_widget(self.cmd_checkbox)

        fw_holder = AnchorLayout(anchor_x="center", anchor_y="center", size_hint=(None, 1), width=dp(88))
        fw_holder.add_widget(self.fw_checkbox)

        info_box = BoxLayout(orientation="vertical", spacing=dp(4))
        self.name_label = Label(
            text=f"{device.Name or device.Hostname}",
            halign="left",
            valign="middle",
            color=(0, 0, 0, 1),
        )
        self.name_label.bind(width=lambda inst, _: setattr(inst, "text_size", (inst.width, None)))
        info_box.add_widget(self.name_label)
        self.meta_label = Label(
            text=self._build_meta_text(device),
            halign="left",
            valign="middle",
            font_size="12sp",
            color=(0, 0, 0, 1),
        )
        self.meta_label.bind(width=lambda inst, _: setattr(inst, "text_size", (inst.width, None)))
        info_box.add_widget(self.meta_label)
        self.hardware_label = Label(
            text=f"{device.Hardware}",
            halign="left",
            valign="middle",
            font_size="12sp",
            color=(0, 0, 0, 1),
        )
        self.hardware_label.bind(width=lambda inst, _: setattr(inst, "text_size", (inst.width, None)))
        info_box.add_widget(self.hardware_label)

        self.add_widget(cmd_holder)
        self.add_widget(fw_holder)
        self.add_widget(info_box)

    def _build_meta_text(self, device) -> str:
        parts = [str(device.IP or "").strip()]
        platform = get_device_platform(device)
        if platform:
            parts.append(platform)
        version = str(getattr(device, "Version", "") or "").strip()
        if version:
            parts.append(version)
        return " • ".join(part for part in parts if part)

    def update_device(self, device) -> None:
        self.device = device
        self.platform = get_device_platform(device)
        self.name_label.text = f"{device.Name or device.Hostname}"
        self.meta_label.text = self._build_meta_text(device)
        self.hardware_label.text = f"{device.Hardware}"
        self._apply_platform_color()

    def get_selection(self) -> Tuple[bool, bool]:
        return self.cmd_checkbox.active, self.fw_checkbox.active

    def _update_background(self, *_):
        if hasattr(self, "_bg_rect"):
            self._bg_rect.pos = self.pos
            self._bg_rect.size = self.size

    def _apply_platform_color(self):
        if hasattr(self, "_bg_color"):
            color = ESP_PLATFORM_COLORS.get(self.platform, ESP_PLATFORM_COLORS["UNKNOWN"])
            self._bg_color.rgba = color
            text_color = (0, 0, 0, 1)
            for attr in ("name_label", "meta_label", "hardware_label"):
                label = getattr(self, attr, None)
                if label is not None:
                    label.color = text_color


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
        self.scroll = ScrollView(size_hint=(1, 1))
        self.container = BoxLayout(
            orientation="vertical",
            spacing=dp(4),
            size_hint_y=None,
        )
        self.container.bind(minimum_height=self.container.setter("height"))
        self.scroll.add_widget(self.container)

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
            color=(0.3, 0.3, 0.3, 1),
        )
        self.queue_feedback_label.bind(
            size=lambda inst, size: setattr(inst, "text_size", (size[0], None)),
            texture_size=lambda inst, size: setattr(
                inst, "height", size[1] + dp(4) if inst.text else 0
            ),
        )
        self.queue_actions_box.add_widget(self.queue_feedback_label)

        # controls_wrapper is already added earlier; avoid re-adding to prevent
        # duplicate parent assignment errors when rebuilding the layout.
        self.add_widget(header)
        self.add_widget(self.scroll)
        self.add_widget(self.queue_actions_box)

        self.results = []
        self.device_map: Dict[str, Any] = {}
        self.row_map: Dict[str, SummaryRow] = {}
        self.displayed_rows: List[SummaryRow] = []
        self._rebuild_trigger = Clock.create_trigger(self._rebuild_rows, 0.15)
        self._last_display_keys: List[str] = []
        self.filter_input.bind(text=self._schedule_rebuild)
        self.sort_spinner.bind(text=self._schedule_rebuild)

        self._build_controls_layout(Window.width)
        self._update_queue_layout(Window.width)
        Window.bind(size=self._on_window_resize)

    def update_progress(self, done: int, total: int):
        def _apply(_: float):
            pct = int((done / total) * 100) if total else 0
            self.progress_label.text = f"Progress: {done} / {total} ({pct}%)"

        Clock.schedule_once(_apply, 0)

    def set_results(self, results, *, replace: bool = True):
        def _apply(_: float):
            filtered = [device for device in results or [] if getattr(device, "Ok", False)]
            if replace:
                base_device_map: Dict[str, Any] = {}
                base_row_map: Dict[str, SummaryRow] = {}
            else:
                base_device_map = dict(self.device_map)
                base_row_map = dict(self.row_map)

            for device in filtered:
                key = self._device_key(device)
                base_device_map[key] = device
                row = base_row_map.get(key)
                if row is None:
                    row = SummaryRow(device)
                else:
                    row.update_device(device)
                base_row_map[key] = row

            self.device_map = base_device_map
            self.row_map = base_row_map
            self.results = list(self.device_map.values())
            self._schedule_rebuild()

        Clock.schedule_once(_apply, 0)

    def get_selected_ips(self) -> Tuple[List[str], List[str]]:
        cmd_ips: List[str] = []
        fw_ips: List[str] = []
        for row in self.row_map.values():
            cmd_selected, fw_selected = row.get_selection()
            if cmd_selected:
                cmd_ips.append(row.device.IP)
            if fw_selected:
                fw_ips.append(row.device.IP)
        return cmd_ips, fw_ips

    def clear(self):
        self.results = []
        self.device_map = {}
        self.row_map = {}
        self._schedule_rebuild()
        self.update_progress(0, 0)

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
            "info": (0.3, 0.3, 0.3, 1),
            "success": (0.1, 0.5, 0.1, 1),
            "error": (0.7, 0.2, 0.2, 1),
        }
        self.queue_feedback_label.color = palette.get(status, palette["info"])
        self.queue_feedback_label.text = message or ""
        self.queue_feedback_label.opacity = 1 if message else 0

    def _on_queue_commands(self):
        cmd_ips, fw_ips = self.get_selected_ips()
        if not cmd_ips:
            self._set_feedback("Select at least one device to queue commands.", "error")
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
        result = None
        if self.queue_firmware_callback:
            result = self.queue_firmware_callback(cmd_ips, fw_ips)
        if result and isinstance(result, dict) and result.get("message"):
            self._set_feedback(result["message"], result.get("status", "info"))
        elif fw_ips:
            self._set_feedback(f"Queued {len(fw_ips)} device(s) for firmware updates.", "success")

    def _device_key(self, device) -> str:
        return str(
            getattr(device, "IP", "")
            or getattr(device, "Hostname", "")
            or getattr(device, "Name", "")
            or id(device)
        )

    def _schedule_rebuild(self, *_):
        if self._rebuild_trigger is not None:
            self._rebuild_trigger()

    def _rebuild_rows(self, *_):
        new_rows: List[SummaryRow] = []
        new_keys: List[str] = []
        for device in self._iter_sorted_devices():
            if not self._matches_filter(device):
                continue
            key = self._device_key(device)
            row = self.row_map.get(key)
            if row is None:
                row = SummaryRow(device)
                self.row_map[key] = row
            new_rows.append(row)
            new_keys.append(key)

        if new_keys != self._last_display_keys:
            self.container.clear_widgets()
            for row in new_rows:
                self.container.add_widget(row)
            self.displayed_rows = list(new_rows)
            self._last_display_keys = list(new_keys)
        else:
            self.displayed_rows = list(new_rows)

        self.summary_label.text = f"Devices: {len(self.displayed_rows)}"

    def _iter_sorted_devices(self) -> List:
        sort_mode = (self.sort_spinner.text or "Name") if hasattr(self, "sort_spinner") else "Name"

        def build_name(device):
            return (device.Name or device.Hostname or "").strip().lower()

        def build_key(device):
            if sort_mode == "Device Type":
                primary = get_device_platform(device).lower()
            elif sort_mode == "IP":
                primary = (device.IP or "").lower()
            elif sort_mode == "Firmware":
                primary = str(getattr(device, "Version", "") or "").lower()
            else:
                primary = build_name(device)
            return (primary, build_name(device), (device.IP or ""))

        return sorted(self.results, key=build_key)

    def _matches_filter(self, device) -> bool:
        query = (self.filter_input.text or "").strip().lower() if hasattr(self, "filter_input") else ""
        if not query:
            return True
        values = [
            str(device.Name or ""),
            str(getattr(device, "Hostname", "")),
            str(device.IP or ""),
            str(getattr(device, "Hardware", "")),
            str(getattr(device, "Version", "")),
            get_device_platform(device),
        ]
        return any(query in value.lower() for value in values if value)
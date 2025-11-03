"""Kivy entrypoint that mirrors the multi-panel Android Compose UI."""

from __future__ import annotations

import asyncio
import threading
from collections import deque
from typing import Callable, Deque, Dict, Iterable, List, Optional, Set, Tuple

from kivy.app import App
from kivy.clock import Clock
from kivy.properties import StringProperty
from kivy.graphics import Color, Line, Rectangle
from kivy.graphics.instructions import InstructionGroup
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.textinput import TextInput
from kivy.utils import escape_markup

from tasmota_core.bulk import BulkRunResult, TasmotaBulkExecutor
from tasmota_core.commands import DEFAULT_COMMANDS, CommandLibraryError, CommandRecord, load_command_library
from tasmota_core.constants import (
    DEFAULT_BACKOFF,
    DEFAULT_IP_RANGES,
    DEFAULT_RETRIES,
    DEFAULT_THREADS,
    DEFAULT_TIMEOUT,
    OTA_URLS,
)
from tasmota_core.utils import build_ip_list


def get_device_platform(device) -> str:
    """Infer the device platform (ESP8266/ESP32) from discovery metadata."""

    fragments = " ".join(
        str(getattr(device, attr, "") or "") for attr in ("Hardware", "Platform", "ChipId")
    ).upper()
    if "ESP32" in fragments:
        return "ESP32"
    if "ESP82" in fragments or "ESP8266" in fragments:
        return "ESP8266"
    return "UNKNOWN"


ESP_PLATFORM_COLORS = {
    "ESP8266": (0.9, 0.96, 1.0, 1),
    "ESP32": (0.9, 1.0, 0.9, 1),
    "UNKNOWN": (1, 1, 1, 1),
}

ESP_PLATFORM_TEXT_COLOR = (0, 0, 0, 1)
SUMMARY_HEADER_TEXT_COLOR = (1, 1, 1, 1)


def get_contrasting_text_color(rgba: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
    """Return black or white text depending on the background luminance."""

    r, g, b, _ = rgba
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return (0, 0, 0, 1) if luminance >= 0.5 else (1, 1, 1, 1)


class LogPanel(BoxLayout):
    """Scrollable log output panel."""

    MAX_LINES = 1000

    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", spacing=6, **kwargs)
        self.label = Label(text="Logs", size_hint_y=None, height=30)
        self.add_widget(self.label)

        self.scroll = ScrollView(size_hint=(1, 1))
        self.log_view = Label(
            text="",
            markup=True,
            size_hint=(1, None),
            halign="left",
            valign="top",
            font_size="14sp",
            padding=(8, 8),
        )
        self.log_lines: List[str] = []
        self._pending_lines: Deque[str] = deque()
        self.log_view.bind(texture_size=self._update_log_height)
        self.scroll.add_widget(self.log_view)
        self.scroll.bind(width=lambda *_: self._update_text_width())
        self.add_widget(self.scroll)
        self._flush_trigger = Clock.create_trigger(self._flush_pending, 0)
        Clock.schedule_once(lambda *_: self._update_text_width(), 0)

    def clear(self):
        self.log_lines.clear()
        self._pending_lines.clear()
        self.log_view.text = ""

    def append_line(self, line: str):
        self._pending_lines.append(line)
        self._flush_trigger()

    def _flush_pending(self, *_):
        if not self._pending_lines:
            return
        updated = False
        while self._pending_lines:
            formatted = self._format_line(self._pending_lines.popleft())
            self.log_lines.append(formatted)
            updated = True
        if not updated:
            return
        if len(self.log_lines) > self.MAX_LINES:
            self.log_lines = self.log_lines[-self.MAX_LINES :]
        self.log_view.text = "\n".join(self.log_lines)
        self._update_text_width()
        self.log_view.texture_update()
        self.scroll.scroll_y = 0

    def _update_log_height(self, instance: Label, size):
        instance.height = max(size[1], self.scroll.height)

    def _update_text_width(self):
        width = max(self.scroll.width - 16, 0)
        self.log_view.text_size = (width, None)

    @staticmethod
    def _format_line(line: str) -> str:
        palette = {
            "INFO": "#2E7D32",
            "WARN": "#F9A825",
            "ERROR": "#C62828",
            "DEBUG": "#1565C0",
        }
        severity = "INFO"
        if line.startswith("[") and "]" in line:
            candidate = line[1 : line.find("]")].upper()
            if candidate:
                severity = candidate
        color = palette.get(severity, "#37474F")
        return f"[color={color}]{escape_markup(line)}[/color]"


class BorderedWidgetMixin:
    """Mixin that renders borders around tables and their columns."""

    border_color = (0.4, 0.4, 0.4, 1)
    separator_color = (0.6, 0.6, 0.6, 1)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._separator_group = InstructionGroup()
        with self.canvas.after:
            Color(*self.border_color)
            self._border_line = Line(rectangle=(0, 0, 0, 0), width=1)
            self.canvas.after.add(self._separator_group)
        self._update_trigger = Clock.create_trigger(self._update_borders, -1)
        self._tracked_children: Set = set()
        self.bind(pos=self._trigger_update, size=self._trigger_update, children=self._on_children)
        self._trigger_update()

    def _on_children(self, *_):
        self._trigger_update()

    def _trigger_update(self, *_):
        self._update_trigger()

    def _update_borders(self, *_):
        if not hasattr(self, "_border_line"):
            return
        self._border_line.rectangle = (self.x, self.y, self.width, self.height)

        current_children = set(self.children)
        for widget in list(self._tracked_children):
            if widget not in current_children:
                widget.unbind(pos=self._trigger_update, size=self._trigger_update)
                self._tracked_children.remove(widget)
        for widget in current_children:
            if widget not in self._tracked_children:
                widget.bind(pos=self._trigger_update, size=self._trigger_update)
                self._tracked_children.add(widget)

        self._separator_group.clear()
        if len(self.children) <= 1:
            return
        self._separator_group.add(Color(*self.separator_color))
        for points in self._separator_points():
            self._separator_group.add(Line(points=points, width=1))

    def _separator_points(self) -> List[Tuple[float, float, float, float]]:
        points: List[Tuple[float, float, float, float]] = []
        if hasattr(self, "orientation"):
            if getattr(self, "orientation") == "horizontal":
                ordered = sorted(self.children, key=lambda child: child.x)
                for left, right in zip(ordered[:-1], ordered[1:]):
                    x = (left.right + right.x) / 2.0
                    points.append((x, self.y, x, self.top))
            elif getattr(self, "orientation") == "vertical":
                ordered = sorted(self.children, key=lambda child: child.y)
                for lower, upper in zip(ordered[:-1], ordered[1:]):
                    y = (lower.top + upper.y) / 2.0
                    points.append((self.x, y, self.right, y))
        else:
            for child in self.children:
                points.append((child.x, child.y, child.right, child.y))
                points.append((child.right, child.y, child.right, child.top))
                points.append((child.right, child.top, child.x, child.top))
                points.append((child.x, child.top, child.x, child.y))
        return points


class BorderedBoxLayout(BorderedWidgetMixin, BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class BorderedGridLayout(BorderedWidgetMixin, GridLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def _separator_points(self) -> List[Tuple[float, float, float, float]]:
        children = list(self.children)
        if len(children) <= 1:
            return []

        lines: List[Tuple[float, float, float, float]] = []
        seen: Set[Tuple[float, float, float, float]] = set()

        row_map: Dict[float, List] = {}
        for child in children:
            key = round(child.y, 2)
            row_map.setdefault(key, []).append(child)
        for widgets in row_map.values():
            widgets.sort(key=lambda item: item.x)
            for left, right in zip(widgets[:-1], widgets[1:]):
                x = (left.right + right.x) / 2.0
                key = (round(x, 2), round(self.y, 2), round(x, 2), round(self.top, 2))
                if key not in seen:
                    seen.add(key)
                    lines.append((x, self.y, x, self.top))

        col_map: Dict[float, List] = {}
        for child in children:
            key = round(child.x, 2)
            col_map.setdefault(key, []).append(child)
        for widgets in col_map.values():
            widgets.sort(key=lambda item: item.y)
            for lower, upper in zip(widgets[:-1], widgets[1:]):
                y = (lower.top + upper.y) / 2.0
                key = (round(self.x, 2), round(y, 2), round(self.right, 2), round(y, 2))
                if key not in seen:
                    seen.add(key)
                    lines.append((self.x, y, self.right, y))

        return lines


class SummaryHeader(BorderedBoxLayout):
    """Header row for the summary table."""

    def __init__(self, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, height=36, spacing=8, padding=(0, 6), **kwargs)

        cmd_label = Label(
            text="Cmd",
            size_hint=(None, 1),
            width=60,
            halign="center",
            valign="middle",
            color=SUMMARY_HEADER_TEXT_COLOR,
        )
        cmd_label.bind(size=lambda inst, _: setattr(inst, "text_size", inst.size))
        self.add_widget(cmd_label)

        ota_label = Label(
            text="OTA",
            size_hint=(None, 1),
            width=60,
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
        super().__init__(orientation="horizontal", size_hint_y=None, height=44, spacing=8, **kwargs)
        self.device = device
        self.platform = get_device_platform(device)
        self.cmd_checkbox = CheckBox(size_hint=(None, None), size=(32, 32))
        self.fw_checkbox = CheckBox(size_hint=(None, None), size=(32, 32))

        with self.canvas.before:
            self._bg_color = Color(*ESP_PLATFORM_COLORS.get(self.platform, ESP_PLATFORM_COLORS["UNKNOWN"]))
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_background, size=self._update_background)
        self._apply_platform_color()

        cmd_holder = AnchorLayout(anchor_x="center", anchor_y="center", size_hint=(None, 1), width=60)
        cmd_holder.add_widget(self.cmd_checkbox)

        fw_holder = AnchorLayout(anchor_x="center", anchor_y="center", size_hint=(None, 1), width=60)
        fw_holder.add_widget(self.fw_checkbox)

        info_box = BoxLayout(orientation="vertical", spacing=2)
        self.name_label = Label(text=f"{device.Name or device.Hostname}", halign="left", valign="middle")
        self.name_label.bind(width=lambda inst, _: setattr(inst, "text_size", (inst.width, None)))
        info_box.add_widget(self.name_label)
        self.meta_label = Label(
            text=self._build_meta_text(device),
            halign="left",
            valign="middle",
            font_size="12sp",
        )
        self.meta_label.bind(width=lambda inst, _: setattr(inst, "text_size", (inst.width, None)))
        info_box.add_widget(self.meta_label)
        self.hardware_label = Label(
            text=f"{device.Hardware}",
            halign="left",
            valign="middle",
            font_size="12sp",
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
            text_color = ESP_PLATFORM_TEXT_COLOR
            for attr in ("name_label", "meta_label", "hardware_label"):
                label = getattr(self, attr, None)
                if label is not None:
                    label.color = text_color


class SummaryPanel(BoxLayout):
    """Displays the list of discovered devices and current progress."""

    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self.progress_label = Label(text="Progress: 0 / 0", size_hint_y=None, height=32)
        self.summary_label = Label(text="Devices: 0", size_hint_y=None, height=28)
        self.add_widget(self.progress_label)
        self.add_widget(self.summary_label)

        controls = BoxLayout(size_hint_y=None, height=40, spacing=8)
        controls.add_widget(Label(text="Filter", size_hint=(None, 1), width=70))
        self.filter_input = TextInput(hint_text="Search devices", multiline=False, size_hint=(1, 1))
        controls.add_widget(self.filter_input)
        controls.add_widget(Label(text="Sort", size_hint=(None, 1), width=60))
        self.sort_spinner = Spinner(text="Name", values=("Name", "Device Type", "IP", "Firmware"), size_hint=(None, 1), width=160)
        controls.add_widget(self.sort_spinner)
        self.add_widget(controls)

        self.header = SummaryHeader()
        self.add_widget(self.header)

        self.scroll = ScrollView(size_hint=(1, 1))
        self.container = GridLayout(cols=1, spacing=6, size_hint_y=None, padding=4)
        self.container.bind(minimum_height=self.container.setter("height"))
        self.scroll.add_widget(self.container)
        self.add_widget(self.scroll)

        self.results = []
        self.row_map: Dict[str, SummaryRow] = {}
        self.displayed_rows: List[SummaryRow] = []
        self._rebuild_trigger = Clock.create_trigger(self._rebuild_rows, 0)
        self.filter_input.bind(text=self._schedule_rebuild)
        self.sort_spinner.bind(text=self._schedule_rebuild)

    def update_progress(self, done: int, total: int):
        def _apply(_: float):
            pct = int((done / total) * 100) if total else 0
            self.progress_label.text = f"Progress: {done} / {total} ({pct}%)"
        Clock.schedule_once(_apply, 0)

    def set_results(self, results):
        def _apply(_: float):
            filtered = [device for device in results or [] if getattr(device, "Ok", False)]
            self.results = filtered
            existing = self.row_map
            new_map: Dict[str, SummaryRow] = {}
            for device in self.results:
                key = self._device_key(device)
                row = existing.get(key)
                if row is None:
                    row = SummaryRow(device)
                else:
                    row.update_device(device)
                new_map[key] = row
            self.row_map = new_map
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
        self.row_map = {}
        self._schedule_rebuild()
        self.update_progress(0, 0)

    def _device_key(self, device) -> str:
        return str(getattr(device, "IP", "") or getattr(device, "Hostname", "") or getattr(device, "Name", "") or id(device))

    def _schedule_rebuild(self, *_):
        if self._rebuild_trigger is not None:
            self._rebuild_trigger()

    def _rebuild_rows(self, *_):
        self.container.clear_widgets()
        self.displayed_rows = []
        for device in self._iter_sorted_devices():
            if not self._matches_filter(device):
                continue
            key = self._device_key(device)
            row = self.row_map.get(key)
            if row is None:
                row = SummaryRow(device)
                self.row_map[key] = row
            self.container.add_widget(row)
            self.displayed_rows.append(row)
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


class CommandLibraryRow(BorderedBoxLayout):
    """Single command entry with checkbox."""

    MIN_HEIGHT = 56

    def __init__(self, record: CommandRecord, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, spacing=8, padding=(0, 6), **kwargs)
        self.record = record
        self.checkbox = CheckBox(size_hint=(None, None), size=(32, 32))

        checkbox_holder = AnchorLayout(anchor_x="center", anchor_y="center", size_hint=(None, 1), width=48)
        checkbox_holder.add_widget(self.checkbox)
        self.add_widget(checkbox_holder)

        command_box = BoxLayout(orientation="vertical", size_hint=(0.6, 1), spacing=2)

        self.command_label = Label(
            text="",
            markup=True,
            halign="left",
            valign="top",
        )
        self.command_label.size_hint_y = None
        command_box.add_widget(self.command_label)

        self.description_label = Label(
            text="",
            halign="left",
            valign="top",
            font_size="12sp",
            color=(0.7, 0.7, 0.7, 1),
        )
        self.description_label.size_hint_y = None
        self.description_label.opacity = 0
        self.description_label.height = 0
        command_box.add_widget(self.description_label)

        self.category_label = Label(
            text="",
            halign="left",
            valign="top",
            font_size="11sp",
            color=(0.6, 0.6, 0.6, 1),
        )
        self.category_label.size_hint_y = None
        self.category_label.opacity = 0
        self.category_label.height = 0
        command_box.add_widget(self.category_label)

        self.add_widget(command_box)

        self.value_label = Label(
            text="",
            halign="left",
            valign="top",
            size_hint=(0.4, None),
        )
        self.value_label.height = 0
        self.add_widget(self.value_label)

        self._labels = [self.command_label, self.value_label, self.description_label, self.category_label]

        for label in self._labels:
            if label is None:
                continue
            label.bind(width=self._on_label_width)
            label.bind(texture_size=self._on_label_texture)

        self.refresh_from_record(record)
        Clock.schedule_once(lambda *_: self._recalculate_height(), 0)

    def refresh_from_record(self, record: CommandRecord) -> None:
        """Update label contents based on the provided command record."""

        self.record = record
        command_text = (record.name or "").strip()
        description_text = (record.description or "").strip()
        category_text = (record.category or "").strip()
        value_text = (record.value or "").strip()

        self._set_label_text(self.command_label, f"[b]{command_text}[/b]" if command_text else "")
        self._set_label_text(self.description_label, description_text)
        self._set_label_text(self.category_label, f"Category: {category_text}" if category_text else "")
        self._set_label_text(self.value_label, value_text)

        self._recalculate_height()

    def build_command(self) -> str:
        value = (self.record.value or "").strip()
        return f"{self.record.name} {value}".strip()

    def _set_label_text(self, label: Label, text: str):
        label.text = text
        label.opacity = 1 if text else 0
        label.texture_update()
        if text:
            label.height = label.texture_size[1] + 4
        else:
            label.height = 0

    def _on_label_width(self, label: Label, _: float):
        label.text_size = (label.width, None)

    def _on_label_texture(self, label: Label, *_):
        if hasattr(label, "texture_size"):
            if label.text:
                label.height = label.texture_size[1] + 4
            else:
                label.height = 0
        Clock.schedule_once(lambda *_: self._recalculate_height(), 0)

    def _recalculate_height(self):
        command_height = self.command_label.texture_size[1] if self.command_label.text else 0
        description_height = (
            self.description_label.texture_size[1]
            if self.description_label is not None and self.description_label.text
            else 0
        )
        category_height = (
            self.category_label.texture_size[1]
            if self.category_label is not None and self.category_label.text
            else 0
        )
        value_height = self.value_label.texture_size[1] if self.value_label.text else 0
        content_height = max(command_height + description_height + category_height, value_height)
        self.height = max(self.MIN_HEIGHT, content_height + 16)


class CommandLibraryPanel(BoxLayout):
    """Command selection and backlog configuration."""

    def __init__(
        self,
        send_callback: Callable[[Dict], None],
        goto_ota_callback: Optional[Callable[[], None]] = None,
        **kwargs,
    ):
        super().__init__(orientation="vertical", spacing=8, **kwargs)
        self.send_callback = send_callback
        self.goto_ota_callback = goto_ota_callback
        self.library_rows: List[CommandLibraryRow] = []
        self.library_popup: Optional[Popup] = None
        self.library_records: List[CommandRecord] = []
        self._row_cache: Dict[str, CommandLibraryRow] = {}
        self._search_trigger = None

        self._ensure_library_components()

        self.backlog_label = Label(text="Backlog Commands", size_hint_y=None, height=28)
        self.backlog_input = TextInput(text="\n".join(DEFAULT_COMMANDS), multiline=True, size_hint=(1, 0.4))

        self.add_widget(self.backlog_label)
        self.add_widget(self.backlog_input)

        controls = BoxLayout(size_hint_y=None, height=40, spacing=8)
        self.btn_open_library = Button(text="Open Command Library")
        self.btn_open_library.bind(on_release=lambda *_: self._open_library_popup())
        controls.add_widget(self.btn_open_library)
        self.btn_clear_backlog = Button(text="Clear Backlog")
        self.btn_clear_backlog.bind(on_release=lambda *_: setattr(self.backlog_input, "text", ""))
        controls.add_widget(self.btn_clear_backlog)
        self.add_widget(controls)

        nav_box = BoxLayout(size_hint_y=None, height=40, spacing=8)
        nav_box.add_widget(Label(text="Need firmware?", size_hint=(0.6, 1)))
        self.btn_open_ota = Button(text="OTA Updates")
        self.btn_open_ota.bind(on_release=lambda *_: self._open_ota())
        nav_box.add_widget(self.btn_open_ota)
        self.add_widget(nav_box)

        self.btn_send = Button(text="Run Selected", size_hint_y=None, height=48)
        self.btn_send.bind(on_release=lambda *_: self._emit_send())
        self.add_widget(self.btn_send)

    def set_library(self, records: Iterable[CommandRecord]):
        self._ensure_library_components()
        self.library_records = list(records)
        self._update_category_options()
        self._refresh_library_rows()

    def _add_selected_to_backlog(self, *_):
        commands = [row.build_command() for row in self.library_rows if row.checkbox.active]
        if not commands:
            return
        existing = self.backlog_input.text.strip()
        combined = existing.splitlines() if existing else []
        for command in commands:
            if command not in combined:
                combined.append(command)
        self.backlog_input.text = "\n".join(combined)
        for row in self.library_rows:
            row.checkbox.active = False

    def _ensure_library_components(self):
        if hasattr(self, "library_container") and self.library_container is not None:
            return
        self.library_container = GridLayout(cols=1, spacing=6, size_hint_y=None, padding=4)
        self.library_container.bind(minimum_height=self.library_container.setter("height"))
        self.library_scroll = ScrollView(size_hint=(1, 1))
        self.library_scroll.add_widget(self.library_container)
        self.search_input = TextInput(hint_text="Search commands", multiline=False, size_hint_y=None, height=40)
        self.search_input.bind(text=self._on_search_text)
        self.category_spinner = Spinner(text="All categories", size_hint_y=None, height=40)
        self.category_spinner.bind(text=lambda *_: self._refresh_library_rows())
        self.btn_add_selected = Button(text="Add")
        self.btn_add_selected.bind(on_release=self._add_selected_to_backlog)
        self._search_trigger = Clock.create_trigger(lambda *_: self._refresh_library_rows(), 0.2)

    def _ensure_library_popup(self):
        self._ensure_library_components()
        if self.library_popup is not None:
            return
        content = BoxLayout(orientation="vertical", spacing=8, padding=8)
        content.add_widget(Label(text="Command Library", size_hint_y=None, height=24))
        filters = BoxLayout(orientation="vertical", spacing=6, size_hint_y=None)
        filters.add_widget(self.search_input)
        category_row = BorderedBoxLayout(size_hint_y=None, height=40, spacing=8)
        category_row.add_widget(Label(text="Category", size_hint=(None, 1), width=90))
        category_row.add_widget(self.category_spinner)
        filters.add_widget(category_row)
        filters.height = self.search_input.height + category_row.height + filters.spacing
        content.add_widget(filters)

        header = BorderedBoxLayout(orientation="horizontal", size_hint_y=None, height=28, spacing=8)
        header_select = Label(text="", size_hint=(None, 1), width=48)
        header_command = Label(text="[b]Command[/b]", markup=True, size_hint=(0.6, 1), halign="left", valign="middle")
        header_value = Label(text="[b]Value[/b]", markup=True, size_hint=(0.4, 1), halign="left", valign="middle")
        for label in (header_command, header_value):
            label.bind(width=lambda inst, _: setattr(inst, "text_size", (inst.width, None)))
        header.add_widget(header_select)
        header.add_widget(header_command)
        header.add_widget(header_value)
        content.add_widget(header)

        content.add_widget(self.library_scroll)
        button_row = BoxLayout(size_hint_y=None, height=40, spacing=8)
        button_row.add_widget(self.btn_add_selected)
        btn_close = Button(text="Close")
        btn_close.bind(on_release=lambda *_: self.library_popup.dismiss() if self.library_popup else None)
        button_row.add_widget(btn_close)
        content.add_widget(button_row)
        self.library_popup = Popup(title="Command Library", content=content, size_hint=(0.9, 0.85))

    def _open_library_popup(self):
        self._ensure_library_popup()
        if self.library_popup:
            self.library_popup.open()

    def _on_search_text(self, *_):
        if self._search_trigger is not None:
            self._search_trigger()
        else:
            self._refresh_library_rows()

    def _get_selected_category(self) -> Optional[str]:
        selected = (self.category_spinner.text or "").strip() if hasattr(self, "category_spinner") else ""
        if not selected or selected.lower() == "all categories":
            return None
        if selected.lower() == "uncategorized":
            return ""
        return selected

    def _update_category_options(self):
        if not hasattr(self, "category_spinner") or self.category_spinner is None:
            return
        categories = sorted({(record.category or "").strip() for record in self.library_records})
        values = ["All categories"]
        if "" in categories:
            values.append("Uncategorized")
        values.extend([category for category in categories if category])
        previous = self.category_spinner.text if self.category_spinner.text in values else None
        self.category_spinner.values = tuple(values)
        self.category_spinner.text = previous or values[0] if values else "All categories"

    def _record_identifier(self, record: CommandRecord) -> str:
        metadata = getattr(record, "metadata", {}) or {}
        identifier = metadata.get("id") if isinstance(metadata, dict) else None
        base = str(identifier or record.name or "").strip().lower()
        value = (record.value or "").strip().lower()
        category = (record.category or "").strip().lower()
        identifier = "::".join(part for part in (base, value, category) if part)
        return identifier or base or (record.name or "").strip().lower()

    def _refresh_library_rows(self, *_):
        self._ensure_library_components()
        self.library_container.clear_widgets()
        self.library_rows = []

        if not self.library_records:
            self.library_container.add_widget(
                Label(
                    text="No commands available.",
                    size_hint=(1, None),
                    height=40,
                    color=(0.7, 0.7, 0.7, 1),
                )
            )
            return

        search_term = (self.search_input.text or "").strip().lower() if hasattr(self, "search_input") else ""
        category_filter = self._get_selected_category()
        active_keys: Set[str] = set()

        for record in self.library_records:
            category_value = (record.category or "").strip()
            if category_filter is not None and category_value != category_filter:
                continue

            haystack = " ".join(
                part
                for part in (
                    record.name or "",
                    record.value or "",
                    record.description or "",
                    category_value,
                )
                if part
            ).lower()
            if search_term and search_term not in haystack:
                continue

            identifier = self._record_identifier(record)
            row = self._row_cache.get(identifier)
            if row is None:
                row = CommandLibraryRow(record)
                self._row_cache[identifier] = row
            else:
                row.refresh_from_record(record)
            if row.parent is not None:
                row.parent.remove_widget(row)
            self.library_container.add_widget(row)
            self.library_rows.append(row)
            active_keys.add(identifier)

        if not self.library_rows:
            self.library_container.add_widget(
                Label(
                    text="No commands match your filters.",
                    size_hint=(1, None),
                    height=40,
                    color=(0.7, 0.7, 0.7, 1),
                )
            )

        for identifier, row in self._row_cache.items():
            if identifier not in active_keys and row.parent is not None:
                row.parent.remove_widget(row)

    def _emit_send(self):
        options = {
            "commands": [line.strip() for line in self.backlog_input.text.splitlines() if line.strip()],
        }
        if self.send_callback:
            self.send_callback(options)

    def set_busy(self, busy: bool):
        self._ensure_library_components()
        self.btn_add_selected.disabled = busy
        self.btn_open_library.disabled = busy
        self.btn_clear_backlog.disabled = busy
        self.btn_send.disabled = busy
        self.btn_open_ota.disabled = busy
        self.search_input.disabled = busy
        self.category_spinner.disabled = busy

    def _open_ota(self):
        if self.goto_ota_callback:
            self.goto_ota_callback()


class OTARow(BorderedBoxLayout):
    """Single row representing a device in the OTA planner."""

    def __init__(self, device, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, height=48, spacing=8, **kwargs)
        self.device = device
        self.platform = get_device_platform(device)
        self.checkbox = CheckBox(size_hint=(None, None), size=(32, 32))
        with self.canvas.before:
            self._bg_color = Color(*ESP_PLATFORM_COLORS.get(self.platform, ESP_PLATFORM_COLORS["UNKNOWN"]))
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_background, size=self._update_background)
        checkbox_holder = AnchorLayout(anchor_x="center", anchor_y="center", size_hint=(None, 1), width=60)
        checkbox_holder.add_widget(self.checkbox)
        self.add_widget(checkbox_holder)

        info_box = BoxLayout(orientation="vertical", spacing=2)
        name = device.Name or device.Hostname or device.IP
        self.name_label = Label(text=name, halign="left", valign="middle")
        self.name_label.bind(width=lambda inst, _: setattr(inst, "text_size", (inst.width, None)))
        info_box.add_widget(self.name_label)
        self.meta_label = Label(
            text=f"{device.IP} • {self.platform}",
            halign="left",
            valign="middle",
            font_size="12sp",
        )
        self.meta_label.bind(width=lambda inst, _: setattr(inst, "text_size", (inst.width, None)))
        info_box.add_widget(self.meta_label)
        self.version_label = Label(
            text=str(device.Version or ""),
            halign="left",
            valign="middle",
            font_size="11sp",
        )
        self.version_label.bind(width=lambda inst, _: setattr(inst, "text_size", (inst.width, None)))
        info_box.add_widget(self.version_label)
        self.add_widget(info_box)

        self.queue_label = Label(text="", size_hint=(None, 1), width=110)
        self.add_widget(self.queue_label)

        self._apply_platform_styles()

    def matches_filter(self, value: str) -> bool:
        if value == "All":
            return True
        return self.platform == value

    def set_queued(self, platform: Optional[str]):
        self.queue_label.text = platform or ""

    def update_device(self, device) -> None:
        self.device = device
        self.platform = get_device_platform(device)
        name = device.Name or device.Hostname or device.IP
        self.name_label.text = name
        self.meta_label.text = f"{device.IP} • {self.platform}"
        self.version_label.text = str(device.Version or "")
        self._apply_platform_styles()

    def _apply_platform_styles(self) -> None:
        color = ESP_PLATFORM_COLORS.get(self.platform, ESP_PLATFORM_COLORS["UNKNOWN"])
        if hasattr(self, "_bg_color"):
            self._bg_color.rgba = color
        text_color = ESP_PLATFORM_TEXT_COLOR
        for label in (self.name_label, self.meta_label, self.version_label, self.queue_label):
            label.color = text_color

    def _update_background(self, *_):
        if hasattr(self, "_bg_rect"):
            self._bg_rect.pos = self.pos
            self._bg_rect.size = self.size


class OTAPanel(BoxLayout):
    """Dedicated OTA update workflow with queue management."""

    def __init__(
        self,
        run_callback: Callable[[Dict], None],
        goto_commands_callback: Optional[Callable[[], None]] = None,
        **kwargs,
    ):
        super().__init__(orientation="vertical", spacing=8, **kwargs)
        self.run_callback = run_callback
        self.goto_commands_callback = goto_commands_callback
        self.results = []
        self.rows: List[OTARow] = []
        self.row_map: Dict[str, OTARow] = {}
        self.queue: Dict[str, Set[str]] = {"ESP8266": set(), "ESP32": set()}

        self.add_widget(Label(text="OTA Updates", size_hint_y=None, height=30))

        filter_row = BoxLayout(size_hint_y=None, height=40, spacing=8)
        filter_row.add_widget(Label(text="Platform", size_hint=(None, 1), width=90))
        self.filter_spinner = Spinner(text="All", values=("All", "ESP8266", "ESP32"), size_hint=(None, 1), width=120)
        filter_row.add_widget(self.filter_spinner)
        filter_row.add_widget(Label(text="Name", size_hint=(None, 1), width=70))
        self.name_filter_input = TextInput(hint_text="Filter", multiline=False, size_hint=(None, 1), width=160)
        filter_row.add_widget(self.name_filter_input)
        filter_row.add_widget(Label(text="IP", size_hint=(None, 1), width=40))
        self.ip_filter_input = TextInput(hint_text="Filter", multiline=False, size_hint=(None, 1), width=140)
        filter_row.add_widget(self.ip_filter_input)
        self.sort_spinner = Spinner(
            text="Name (A-Z)",
            values=("Name (A-Z)", "Name (Z-A)"),
            size_hint=(None, 1),
            width=150,
        )
        filter_row.add_widget(self.sort_spinner)
        self.add_widget(filter_row)

        selection_row = BoxLayout(size_hint_y=None, height=40, spacing=8)
        self.btn_select_all = Button(text="Select All")
        self.btn_select_all.bind(on_release=lambda *_: self._set_all_selection(True))
        selection_row.add_widget(self.btn_select_all)
        self.btn_clear_selection = Button(text="Clear")
        self.btn_clear_selection.bind(on_release=lambda *_: self._set_all_selection(False))
        selection_row.add_widget(self.btn_clear_selection)
        self.add_widget(selection_row)

        self.scroll = ScrollView(size_hint=(1, 1))
        self.device_container = GridLayout(cols=1, spacing=6, size_hint_y=None, padding=4)
        self.device_container.bind(minimum_height=self.device_container.setter("height"))
        self.scroll.add_widget(self.device_container)
        self.add_widget(self.scroll)

        self._rebuild_trigger = Clock.create_trigger(self._rebuild_rows, 0)
        self.filter_spinner.bind(text=self._schedule_rebuild)
        self.name_filter_input.bind(text=self._schedule_rebuild)
        self.ip_filter_input.bind(text=self._schedule_rebuild)
        self.sort_spinner.bind(text=self._schedule_rebuild)

        url_grid = BorderedGridLayout(cols=2, size_hint_y=None, height=160, row_default_height=40, spacing=8)
        esp8266_box = BoxLayout(orientation="vertical", spacing=4)
        esp8266_box.add_widget(Label(text="ESP8266 OTA URL"))
        self.esp8266_input = TextInput(text=OTA_URLS["ESP8266"], multiline=False)
        esp8266_box.add_widget(self.esp8266_input)
        self.btn_queue_esp8266 = Button(text="Queue Selected (ESP8266)")
        self.btn_queue_esp8266.bind(on_release=lambda *_: self._queue_selected("ESP8266"))
        esp8266_box.add_widget(self.btn_queue_esp8266)
        url_grid.add_widget(esp8266_box)

        esp32_box = BoxLayout(orientation="vertical", spacing=4)
        esp32_box.add_widget(Label(text="ESP32 OTA URL"))
        self.esp32_input = TextInput(text=OTA_URLS["ESP32"], multiline=False)
        esp32_box.add_widget(self.esp32_input)
        self.btn_queue_esp32 = Button(text="Queue Selected (ESP32)")
        self.btn_queue_esp32.bind(on_release=lambda *_: self._queue_selected("ESP32"))
        esp32_box.add_widget(self.btn_queue_esp32)
        url_grid.add_widget(esp32_box)
        self.add_widget(url_grid)

        queue_row = BoxLayout(size_hint_y=None, height=40, spacing=8)
        self.queue_label = Label(text="Queued: 0", size_hint=(1, 1))
        queue_row.add_widget(self.queue_label)
        self.btn_clear_queue = Button(text="Clear Queue", size_hint=(None, 1), width=140)
        self.btn_clear_queue.bind(on_release=lambda *_: self._clear_queue())
        queue_row.add_widget(self.btn_clear_queue)
        self.add_widget(queue_row)

        action_row = BoxLayout(size_hint_y=None, height=48, spacing=8)
        self.btn_run = Button(text="Run OTA Updates")
        self.btn_run.bind(on_release=lambda *_: self._run_updates())
        action_row.add_widget(self.btn_run)
        self.btn_back = Button(text="Back to Commands")
        self.btn_back.bind(on_release=lambda *_: self._goto_commands())
        action_row.add_widget(self.btn_back)
        self.add_widget(action_row)

        self._rebuild_rows()
        self._update_queue_status()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def set_results(self, results):
        filtered = [device for device in results or [] if getattr(device, "Ok", False)]
        self.results = filtered
        existing = self.row_map
        new_map: Dict[str, OTARow] = {}
        for device in self.results:
            key = self._device_key(device)
            row = existing.get(key)
            if row is None:
                row = OTARow(device)
            else:
                row.update_device(device)
            new_map[key] = row
        self.row_map = new_map
        self.rows = list(self.row_map.values())
        self._schedule_rebuild()
        self._update_queue_status()

    def clear_queue(self):
        self._clear_queue()

    def set_busy(self, busy: bool):
        self.btn_select_all.disabled = busy
        self.btn_clear_selection.disabled = busy
        self.btn_queue_esp8266.disabled = busy
        self.btn_queue_esp32.disabled = busy
        self.btn_run.disabled = busy
        self.btn_clear_queue.disabled = busy
        self.esp8266_input.disabled = busy
        self.esp32_input.disabled = busy
        self.filter_spinner.disabled = busy
        self.name_filter_input.disabled = busy
        self.ip_filter_input.disabled = busy
        self.sort_spinner.disabled = busy

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _goto_commands(self):
        if self.goto_commands_callback:
            self.goto_commands_callback()

    def _schedule_rebuild(self, *_):
        if self._rebuild_trigger is not None:
            self._rebuild_trigger()

    def _rebuild_rows(self, *_):
        self.device_container.clear_widgets()
        for row in self._iter_filtered_rows():
            self.device_container.add_widget(row)

    def _set_all_selection(self, value: bool):
        for row in self._iter_filtered_rows():
            row.checkbox.active = value

    def _queue_selected(self, platform: str):
        selected_rows = [row for row in self.row_map.values() if row.checkbox.active]
        if not selected_rows:
            return
        for row in selected_rows:
            ip = row.device.IP
            for other in self.queue.values():
                other.discard(ip)
            if platform in self.queue:
                self.queue[platform].add(ip)
            row.checkbox.active = False
        self._update_queue_status()

    def _clear_queue(self):
        for key in self.queue:
            self.queue[key].clear()
        self._update_queue_status()

    def _update_queue_status(self):
        valid_ips = {row.device.IP for row in self.row_map.values()}
        for key in self.queue:
            self.queue[key] = {ip for ip in self.queue[key] if ip in valid_ips}
        queued_total = sum(len(ips) for ips in self.queue.values())
        self.queue_label.text = f"Queued: {queued_total}"
        for row in self.row_map.values():
            platform = None
            for key, ips in self.queue.items():
                if row.device.IP in ips:
                    platform = key
                    break
            row.set_queued(platform)

    def _device_key(self, device) -> str:
        return str(getattr(device, "IP", "") or getattr(device, "Hostname", "") or getattr(device, "Name", "") or id(device))

    def _iter_filtered_rows(self):
        for row in self._get_sorted_rows():
            if self._matches_filters(row):
                yield row

    def _get_sorted_rows(self) -> List[OTARow]:
        rows = list(self.row_map.values())
        reverse = (self.sort_spinner.text or "Name (A-Z)") == "Name (Z-A)" if hasattr(self, "sort_spinner") else False

        def key(row: OTARow):
            device = row.device
            return (device.Name or device.Hostname or device.IP or "").strip().lower()

        return sorted(rows, key=key, reverse=reverse)

    def _matches_filters(self, row: OTARow) -> bool:
        platform_filter = (self.filter_spinner.text or "All") if hasattr(self, "filter_spinner") else "All"
        if platform_filter != "All" and row.platform != platform_filter:
            return False
        name_filter = (self.name_filter_input.text or "").strip().lower() if hasattr(self, "name_filter_input") else ""
        if name_filter:
            haystack = " ".join(
                part
                for part in (
                    row.device.Name or "",
                    getattr(row.device, "Hostname", ""),
                    getattr(row.device, "Hardware", ""),
                )
                if part
            ).lower()
            if name_filter not in haystack:
                return False
        ip_filter = (self.ip_filter_input.text or "").strip().lower() if hasattr(self, "ip_filter_input") else ""
        if ip_filter and ip_filter not in str(row.device.IP or "").lower():
            return False
        return True

    def _get_ota_urls(self) -> Dict[str, str]:
        return {
            "ESP8266": self.esp8266_input.text.strip() or OTA_URLS["ESP8266"],
            "ESP32": self.esp32_input.text.strip() or OTA_URLS["ESP32"],
        }

    def _run_updates(self):
        payload = {
            "queue": {key: sorted(ips) for key, ips in self.queue.items() if ips},
            "urls": self._get_ota_urls(),
        }
        if not any(payload["queue"].values()):
            return
        if self.run_callback:
            self.run_callback(payload)

class DiscoveryPanel(BoxLayout):
    """Inputs for discovery settings."""

    info_mode = StringProperty("lite")

    def __init__(self, discover_callback: Callable[[Dict], None], **kwargs):
        super().__init__(orientation="vertical", spacing=8, **kwargs)
        self.discover_callback = discover_callback

        self.thread_input = TextInput(text=str(DEFAULT_THREADS), multiline=False, input_filter="int")
        self.timeout_input = TextInput(text=str(DEFAULT_TIMEOUT), multiline=False, input_filter="float")
        self.retries_input = TextInput(text=str(DEFAULT_RETRIES), multiline=False, input_filter="int")
        self.range_input = TextInput(text=DEFAULT_IP_RANGES, size_hint=(1, 0.5))

        header = Label(text="Discovery", size_hint_y=None, height=30)
        self.add_widget(header)

        self.add_widget(Label(text="IP Ranges", size_hint_y=None, height=24))
        self.add_widget(self.range_input)

        grid = BorderedGridLayout(cols=2, size_hint_y=None, height=90, row_default_height=30)
        grid.add_widget(Label(text="Threads"))
        grid.add_widget(self.thread_input)
        grid.add_widget(Label(text="Timeout (s)"))
        grid.add_widget(self.timeout_input)
        grid.add_widget(Label(text="Retries"))
        grid.add_widget(self.retries_input)
        self.add_widget(grid)

        mode_box = BoxLayout(size_hint_y=None, height=40)
        self.mode_spinner = Spinner(text="Lite", values=("Lite", "Full"))
        self.mode_spinner.bind(text=self._on_mode_change)
        mode_box.add_widget(Label(text="Info Mode", size_hint=(0.6, 1)))
        mode_box.add_widget(self.mode_spinner)
        self.add_widget(mode_box)

        self.btn_discover = Button(text="Discover Devices", size_hint_y=None, height=48)
        self.btn_discover.bind(on_release=lambda *_: self._emit_discover())
        self.add_widget(self.btn_discover)

    def _on_mode_change(self, spinner, value):
        self.info_mode = value.lower()

    def _emit_discover(self):
        if self.discover_callback:
            self.discover_callback(self.get_parameters())

    def get_parameters(self) -> Dict:
        return {
            "threads": int(self.thread_input.text or DEFAULT_THREADS),
            "timeout": float(self.timeout_input.text or DEFAULT_TIMEOUT),
            "retries": int(self.retries_input.text or DEFAULT_RETRIES),
            "ip_ranges": self.range_input.text,
            "info_mode": self.info_mode,
        }

    def set_busy(self, busy: bool):
        self.btn_discover.disabled = busy
        self.thread_input.disabled = busy
        self.timeout_input.disabled = busy
        self.retries_input.disabled = busy
        self.range_input.disabled = busy
        self.mode_spinner.disabled = busy


class RootLayout(TabbedPanel):
    """Tabbed layout that coordinates the panels."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.do_default_tab = False
        self.tab_height = "42dp"

        self.active_thread: Optional[threading.Thread] = None
        self.tabs_by_title: Dict[str, TabbedPanelItem] = {}

        self.discovery_panel = DiscoveryPanel(self._on_discover)
        self.command_panel = CommandLibraryPanel(self._on_run_commands, self._show_ota_tab)
        self.ota_panel = OTAPanel(self._on_run_ota, self._show_commands_tab)
        self.summary_panel = SummaryPanel()
        self.logs_panel = LogPanel()

        self._add_panel_tab("Discovery", self.discovery_panel)
        self._add_panel_tab("Commands", self.command_panel)
        self._add_panel_tab("OTA", self.ota_panel)
        self._add_panel_tab("Summary", self.summary_panel)
        self._add_panel_tab("Logs", self.logs_panel)

        self._load_command_library()
        Clock.schedule_once(lambda *_: self._show_tab("Discovery"), 0)

    def _add_panel_tab(self, title: str, panel: BoxLayout):
        """Add a tab containing a panel inside a scroll view."""

        tab = TabbedPanelItem(text=title)
        wrapped = self._wrap_in_scroll(panel)
        tab.add_widget(wrapped)
        self.add_widget(tab)
        self.tabs_by_title[title] = tab

    def _wrap_in_scroll(self, panel: BoxLayout) -> ScrollView:
        """Wrap the provided panel in a ScrollView for small displays."""

        panel.size_hint_y = None

        container = BoxLayout(orientation="vertical", size_hint=(1, None), padding=8)
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

    # ------------------------------------------------------------------
    # Data loading helpers
    # ------------------------------------------------------------------
    def _load_command_library(self):
        try:
            records = load_command_library()
        except CommandLibraryError as exc:
            self.logs_panel.append_line(f"[ERROR] {exc}")
            records = []
        self.command_panel.set_library(records)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _on_discover(self, params: Dict):
        if self.active_thread is not None and self.active_thread.is_alive():
            self.logs_panel.append_line("[WARN] Discovery already running")
            return

        ips = build_ip_list(params.get("ip_ranges", DEFAULT_IP_RANGES))
        if not ips:
            self.logs_panel.append_line("[WARN] No IP addresses to scan")
            return

        self.logs_panel.append_line(f"[INFO] Starting discovery of {len(ips)} IPs")
        self._run_executor(
            ips=ips,
            threads=params.get("threads", DEFAULT_THREADS),
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
        )

    def _on_run_commands(self, options: Dict):
        if self.active_thread is not None and self.active_thread.is_alive():
            self.logs_panel.append_line("[WARN] Task already running")
            return

        cmd_ips, _ = self.summary_panel.get_selected_ips()
        if not cmd_ips:
            self.logs_panel.append_line("[WARN] Select devices in the summary panel")
            return

        commands = options.get("commands", [])
        if not commands:
            self.logs_panel.append_line("[WARN] No backlog commands configured")
            return

        self.logs_panel.append_line(f"[INFO] Running commands for {len(cmd_ips)} devices")
        self._run_executor(
            ips=cmd_ips,
            threads=int(self.discovery_panel.thread_input.text or DEFAULT_THREADS),
            timeout=float(self.discovery_panel.timeout_input.text or DEFAULT_TIMEOUT),
            retries=int(self.discovery_panel.retries_input.text or DEFAULT_RETRIES),
            info_mode=self.discovery_panel.info_mode,
            send_backlog=True,
            commands=commands,
            do_upgrade=False,
            cmd_ips=cmd_ips,
            fw_ips=[],
            selected_ips=cmd_ips,
            ota_urls=OTA_URLS,
        )

    def _on_run_ota(self, payload: Dict):
        if self.active_thread is not None and self.active_thread.is_alive():
            self.logs_panel.append_line("[WARN] Task already running")
            return

        queue = payload.get("queue", {}) if isinstance(payload, dict) else {}
        fw_ips = sorted({ip for ips in queue.values() for ip in ips})
        if not fw_ips:
            self.logs_panel.append_line("[WARN] Queue one or more devices for OTA updates")
            return

        ota_urls = payload.get("urls", OTA_URLS)
        self.logs_panel.append_line(f"[INFO] Running OTA updates for {len(fw_ips)} devices")
        self.ota_panel.clear_queue()
        self._run_executor(
            ips=fw_ips,
            threads=int(self.discovery_panel.thread_input.text or DEFAULT_THREADS),
            timeout=float(self.discovery_panel.timeout_input.text or DEFAULT_TIMEOUT),
            retries=int(self.discovery_panel.retries_input.text or DEFAULT_RETRIES),
            info_mode=self.discovery_panel.info_mode,
            send_backlog=False,
            commands=[],
            do_upgrade=True,
            cmd_ips=[],
            fw_ips=fw_ips,
            selected_ips=fw_ips,
            ota_urls=ota_urls,
        )

    # ------------------------------------------------------------------
    # Executor wiring
    # ------------------------------------------------------------------
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
    ):
        self.discovery_panel.set_busy(True)
        self.command_panel.set_busy(True)
        self.ota_panel.set_busy(True)
        ip_list = list(ips)
        self.summary_panel.update_progress(0, len(ip_list))

        def progress_cb(done: int, total: int):
            Clock.schedule_once(lambda dt: self.summary_panel.update_progress(done, total), 0)

        def log_cb(line: str, tag: str):
            Clock.schedule_once(lambda dt: self.logs_panel.append_line(line), 0)

        executor = TasmotaBulkExecutor(
            ips=ip_list,
            threads=threads,
            out_dir=None,
            timeout=timeout,
            retries=retries,
            backoff=DEFAULT_BACKOFF,
            send_backlog=send_backlog,
            commands=list(commands),
            do_upgrade=do_upgrade,
            selected_ips=list(selected_ips),
            ota_urls=dict(ota_urls),
            info_mode=info_mode,
            cmd_ips=list(cmd_ips),
            fw_ips=list(fw_ips),
            progress_callback=progress_cb,
            log_callback=log_cb,
        )

        def worker():
            try:
                result = asyncio.run(executor.run_async())
            except Exception as exc:
                Clock.schedule_once(lambda dt: self.logs_panel.append_line(f"[ERROR] {exc}"), 0)
                result = None
            Clock.schedule_once(lambda dt: self._on_executor_complete(result), 0)

        thread = threading.Thread(target=worker, daemon=True)
        self.active_thread = thread
        thread.start()

    def _on_executor_complete(self, result: Optional[BulkRunResult]):
        self.discovery_panel.set_busy(False)
        self.command_panel.set_busy(False)
        self.ota_panel.set_busy(False)
        self.active_thread = None
        if result is not None:
            self.summary_panel.set_results(result.results)
            self.ota_panel.set_results(result.results)
            self.logs_panel.append_line("[INFO] Completed run.")
        else:
            self.summary_panel.update_progress(0, 0)


class TasmotaKivyApp(App):
    """Application wrapper."""

    def build(self):
        self.title = "Tasmota Bulk Tool"
        return RootLayout()


def main():
    TasmotaKivyApp().run()


if __name__ == "__main__":
    main()

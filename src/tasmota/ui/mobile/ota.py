"""OTA planner widgets for the mobile UI."""

from __future__ import annotations

from typing import Callable, Dict, Iterable, List, Optional, Set

from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from tasmota.core.constants import OTA_URLS

from .widgets.common import (
    CHECKBOX_BLACK,
    ESP_PLATFORM_COLORS,
    ESP_PLATFORM_TEXT_COLOR,
    BorderedBoxLayout,
    get_device_platform,
)


class OTARow(BorderedBoxLayout):
    """Single row representing a device in the OTA planner."""

    def __init__(self, device, **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, height=dp(68), spacing=dp(8), **kwargs)
        self.device = device
        self.platform = get_device_platform(device)
        self.checkbox = CheckBox(size_hint=(None, None), size=(dp(40), dp(40)), color=CHECKBOX_BLACK)
        with self.canvas.before:
            self._bg_color = Color(*ESP_PLATFORM_COLORS.get(self.platform, ESP_PLATFORM_COLORS["UNKNOWN"]))
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._update_background, size=self._update_background)
        checkbox_holder = AnchorLayout(anchor_x="center", anchor_y="center", size_hint=(None, 1), width=dp(88))
        checkbox_holder.add_widget(self.checkbox)
        self.add_widget(checkbox_holder)

        info_box = BoxLayout(orientation="vertical", spacing=dp(4))
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

        self.queue_label = Label(text="", size_hint=(None, 1), width=dp(140))
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
        super().__init__(orientation="vertical", spacing=dp(8), **kwargs)
        self.run_callback = run_callback
        self.goto_commands_callback = goto_commands_callback
        self.results = []
        self.rows: List[OTARow] = []
        self.row_map: Dict[str, OTARow] = {}
        self.queue: Dict[str, Set[str]] = {"ESP8266": set(), "ESP32": set()}

        self.add_widget(Label(text="OTA Updates", size_hint_y=None, height=dp(36)))

        filter_row = BoxLayout(size_hint_y=None, height=dp(56), spacing=dp(8))
        filter_row.add_widget(Label(text="Platform", size_hint=(None, 1), width=dp(110)))
        self.filter_spinner = Spinner(text="All", values=("All", "ESP8266", "ESP32"), size_hint=(None, 1), width=dp(140))
        filter_row.add_widget(self.filter_spinner)
        filter_row.add_widget(Label(text="Name", size_hint=(None, 1), width=dp(90)))
        self.name_filter_input = TextInput(hint_text="Filter", multiline=False, size_hint=(None, 1), width=dp(200))
        filter_row.add_widget(self.name_filter_input)
        filter_row.add_widget(Label(text="IP", size_hint=(None, 1), width=dp(60)))
        self.ip_filter_input = TextInput(hint_text="Filter", multiline=False, size_hint=(None, 1), width=dp(180))
        filter_row.add_widget(self.ip_filter_input)
        self.sort_spinner = Spinner(
            text="Name (A-Z)",
            values=("Name (A-Z)", "Name (Z-A)"),
            size_hint=(None, 1),
            width=dp(180),
        )
        filter_row.add_widget(self.sort_spinner)
        self.add_widget(filter_row)

        selection_row = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        self.btn_select_all = Button(text="Select All")
        self.btn_select_all.bind(on_release=lambda *_: self._set_all_selection(True))
        selection_row.add_widget(self.btn_select_all)
        self.btn_clear_selection = Button(text="Clear")
        self.btn_clear_selection.bind(on_release=lambda *_: self._set_all_selection(False))
        selection_row.add_widget(self.btn_clear_selection)
        self.add_widget(selection_row)

        self.scroll = ScrollView(size_hint=(1, 1))
        self.device_container = GridLayout(cols=1, spacing=dp(6), size_hint_y=None, padding=dp(8))
        self.device_container.bind(minimum_height=self.device_container.setter("height"))
        self.scroll.add_widget(self.device_container)
        self.add_widget(self.scroll)

        self._rebuild_trigger = Clock.create_trigger(self._rebuild_rows, 0)
        self.filter_spinner.bind(text=self._schedule_rebuild)
        self.name_filter_input.bind(text=self._schedule_rebuild)
        self.ip_filter_input.bind(text=self._schedule_rebuild)
        self.sort_spinner.bind(text=self._schedule_rebuild)

        url_grid = BorderedBoxLayout(
            orientation="horizontal",
            size_hint=(1, None),
            height=dp(220),
            spacing=dp(12),
            padding=dp(8),
        )
        esp8266_box = BoxLayout(orientation="vertical", spacing=dp(6), size_hint=(0.5, 1))
        esp8266_box.add_widget(Label(text="ESP8266 OTA URL"))
        self.esp8266_input = TextInput(
            text=OTA_URLS["ESP8266"],
            multiline=False,
            size_hint=(1, None),
            height=dp(44),
        )
        esp8266_box.add_widget(self.esp8266_input)
        self.btn_queue_esp8266 = Button(text="Queue Selected (ESP8266)")
        self.btn_queue_esp8266.bind(on_release=lambda *_: self._queue_selected("ESP8266"))
        esp8266_box.add_widget(self.btn_queue_esp8266)
        url_grid.add_widget(esp8266_box)

        esp32_box = BoxLayout(orientation="vertical", spacing=dp(6), size_hint=(0.5, 1))
        esp32_box.add_widget(Label(text="ESP32 OTA URL"))
        self.esp32_input = TextInput(
            text=OTA_URLS["ESP32"],
            multiline=False,
            size_hint=(1, None),
            height=dp(44),
        )
        esp32_box.add_widget(self.esp32_input)
        self.btn_queue_esp32 = Button(text="Queue Selected (ESP32)")
        self.btn_queue_esp32.bind(on_release=lambda *_: self._queue_selected("ESP32"))
        esp32_box.add_widget(self.btn_queue_esp32)
        url_grid.add_widget(esp32_box)
        self.add_widget(url_grid)

        queue_row = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        self.queue_label = Label(text="Queued: 0", size_hint=(1, 1))
        queue_row.add_widget(self.queue_label)
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

    def stage_ota_targets(self, ips: Iterable[str]) -> Dict[str, int]:
        sanitized = [str(ip).strip() for ip in ips if ip]
        seen: Set[str] = set()
        platform_counts: Dict[str, int] = {}
        staged = 0
        for ip in sanitized:
            if not ip or ip in seen:
                continue
            seen.add(ip)
            row = self._row_for_ip(ip)
            if row is None:
                continue
            for bucket in self.queue.values():
                bucket.discard(ip)
            platform = row.platform or get_device_platform(row.device)
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
    def _row_for_ip(self, ip: str) -> Optional[OTARow]:
        for row in self.row_map.values():
            if row.device.IP == ip:
                return row
        return None

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
        return str(
            getattr(device, "IP", "")
            or getattr(device, "Hostname", "")
            or getattr(device, "Name", "")
            or id(device)
        )

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

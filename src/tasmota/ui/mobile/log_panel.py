"""Log panel widget for the Kivy mobile UI."""

from __future__ import annotations

from collections import deque
from typing import Deque

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.utils import escape_markup

from tasmota.constants import LOG_PANEL_MAX_LINES


class LogPanel(BoxLayout):
    """Scrollable log output panel."""

    skip_scroll_wrapper = True

    MAX_LINES = LOG_PANEL_MAX_LINES

    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(6), **kwargs)
        self.label = Label(text="Logs", size_hint_y=None, height=dp(30))
        self.add_widget(self.label)

        self.scroll = ScrollView(size_hint=(1, 1))
        self.log_container = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            padding=(dp(8), dp(8)),
            spacing=dp(4),
        )
        self.log_container.bind(minimum_height=self.log_container.setter("height"))
        self.scroll.add_widget(self.log_container)
        self.scroll.bind(width=lambda *_: self._update_text_width())
        self.add_widget(self.scroll)

        # Use deque with maxlen to automatically discard old entries
        # This is more efficient than manual list slicing
        self.log_lines: Deque[str] = deque(maxlen=self.MAX_LINES)
        self._line_widgets: Deque[Label] = deque()
        self._pending_lines: Deque[str] = deque()
        self._flush_trigger = Clock.create_trigger(self._flush_pending, 0)
        Clock.schedule_once(lambda *_: self._update_text_width(), 0)

    def clear(self):
        self.log_lines.clear()
        self._pending_lines.clear()
        self._line_widgets.clear()
        self.log_container.clear_widgets()

    def append_line(self, line: str):
        self._pending_lines.append(line)
        self._flush_trigger()

    def _flush_pending(self, *_):
        if not self._pending_lines:
            return

        # Track how many lines existed before adding new ones
        # to determine how many widgets to remove (deque auto-discards old entries)
        count_before = len(self.log_lines)
        new_widgets = []

        while self._pending_lines:
            formatted = self._format_line(self._pending_lines.popleft())
            self.log_lines.append(formatted)  # deque with maxlen auto-discards oldest
            label = self._create_line_widget(formatted)
            self._line_widgets.append(label)
            new_widgets.append(label)

        if not new_widgets:
            return

        for widget in new_widgets:
            self.log_container.add_widget(widget)

        # Calculate overflow: items added minus growth in deque size
        # (growth is capped by maxlen, so difference = discarded items)
        count_after = len(self.log_lines)
        overflow = len(new_widgets) - (count_after - count_before)

        for _ in range(overflow):
            old_widget = self._line_widgets.popleft()
            if old_widget.parent is self.log_container:
                self.log_container.remove_widget(old_widget)

        self._update_text_width()
        self.scroll.scroll_y = 0

    def _update_text_width(self):
        width = max(self._current_text_width(), 0)
        for widget in self._line_widgets:
            widget.text_size = (width, None)
            # Don't call texture_update() - Kivy updates textures lazily when needed

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

        normalized = line.lower()
        if "no response" in normalized:
            color = "#F9A825"
        elif "device responded" in normalized:
            color = "#2E7D32"
        else:
            color = palette.get(severity, "#37474F")
        return f"[color={color}]{escape_markup(line)}[/color]"

    def _current_text_width(self) -> float:
        # Match the previous padding of 8dp on each horizontal edge.
        return self.scroll.width - dp(16)

    def _create_line_widget(self, formatted: str) -> Label:
        label = Label(
            text=formatted,
            markup=True,
            size_hint_y=None,
            halign="left",
            valign="top",
            font_size="14sp",
        )
        label.bind(texture_size=self._on_label_texture_size)
        label.text_size = (self._current_text_width(), None)
        # Don't call texture_update() - Kivy updates textures lazily when needed
        return label

    @staticmethod
    def _on_label_texture_size(label: Label, size):
        if size[1]:
            label.height = max(size[1], dp(18))

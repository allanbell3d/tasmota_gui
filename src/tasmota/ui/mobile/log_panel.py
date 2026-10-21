"""Log panel widget for the Kivy mobile UI.

Lines are shown in a RecycleView, so only the rows on screen exist as
widgets. The previous design created one markup Label per line; a discovery
scan logs one line per unreachable IP, and building and rendering those labels
on the UI thread caused visible stalls (profiled: ~1.5 ms per line, frames up
to ~240 ms while ~1000 lines arrived).

Rows wrap long lines. Each row measures its own height the first time it is
shown and stores it in the data (``key_size``), so the layout stays exact
without rendering off-screen lines.
"""

from __future__ import annotations

import re
from collections import deque
from typing import Deque, Dict, List

from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.properties import NumericProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.utils import escape_markup

from tasmota.constants import LOG_PANEL_MAX_LINES

_PALETTE = {
    "INFO": "#2E7D32",
    "WARN": "#F9A825",
    "ERROR": "#C62828",
    "DEBUG": "#1565C0",
    "OTA": "#1565C0",
    "CMD": "#6A1B9A",
}
# "[WARN] text" from the app, or "12:00:01 [OTA] [ip] text" from the executor.
_TAG_RE = re.compile(r"^(?:\d{2}:\d{2}:\d{2}\s+)?\[([A-Za-z]+)\]")
_FONT_SIZE = "14sp"
_HORIZONTAL_PADDING = dp(16)  # 8dp on each side


def _single_line_height() -> float:
    return max(sp(14) * 1.25, dp(18))


class LogLineView(RecycleDataViewBehavior, Label):
    """One log line. Reports its wrapped height back to the data list."""

    index = NumericProperty(0)

    def __init__(self, **kwargs):
        super().__init__(
            markup=True,
            halign="left",
            valign="top",
            font_size=_FONT_SIZE,
            size_hint_y=None,
            **kwargs,
        )
        self._rv = None
        self.bind(texture_size=self._report_height)

    def refresh_view_attrs(self, rv, index, data):
        self._rv = rv
        self.index = index
        self.text_size = (max(rv.width - _HORIZONTAL_PADDING, 0), None)
        return super().refresh_view_attrs(rv, index, data)

    def _report_height(self, _label, size):
        rv = self._rv
        if rv is None or not size[1] or not (0 <= self.index < len(rv.data)):
            return
        height = max(size[1], dp(18))
        item = rv.data[self.index]
        if item.get("text") != self.text or abs(item["size"][1] - height) < 1:
            return
        # Replacing the item marks only this index as modified.
        rv.data[self.index] = {"text": item["text"], "size": (0, height)}


class LogPanel(BoxLayout):
    """Scrollable log output panel."""

    skip_scroll_wrapper = True

    MAX_LINES = LOG_PANEL_MAX_LINES

    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(6), **kwargs)
        self.label = Label(text="Logs", size_hint_y=None, height=dp(30))
        self.add_widget(self.label)

        self.recycle_view = RecycleView(size_hint=(1, 1), do_scroll_x=False)
        layout = RecycleBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            default_size_hint=(1, None),
            default_size=(0, _single_line_height()),
            key_size="size",
            padding=(dp(8), dp(8)),
            spacing=dp(4),
        )
        layout.bind(minimum_height=layout.setter("height"))
        self.recycle_view.add_widget(layout)
        self.recycle_view.viewclass = LogLineView
        self.recycle_view.bind(width=self._on_width)
        self.add_widget(self.recycle_view)

        # Formatted lines currently shown (oldest first).
        self.log_lines: Deque[str] = deque(maxlen=self.MAX_LINES)
        self._pending_lines: Deque[str] = deque()
        self._flush_trigger = Clock.create_trigger(self._flush_pending, 0)
        self._last_width = 0.0

    def clear(self):
        self.log_lines.clear()
        self._pending_lines.clear()
        self.recycle_view.data = []

    def append_line(self, line: str):
        self._pending_lines.append(line)
        self._flush_trigger()

    def _flush_pending(self, *_):
        if not self._pending_lines:
            return
        at_bottom = self.recycle_view.scroll_y <= 0.01 or not self.recycle_view.data
        while self._pending_lines:
            self.log_lines.append(self._format_line(self._pending_lines.popleft()))

        data: List[Dict] = list(self.recycle_view.data)
        known = {item["text"]: item for item in data[-len(self.log_lines):]}
        guess = (0, _single_line_height())
        # Keep measured heights of lines that are still shown.
        self.recycle_view.data = [known.get(text) or {"text": text, "size": guess} for text in self.log_lines]
        if at_bottom:
            # Follow new output only if the user has not scrolled up.
            self.recycle_view.scroll_y = 0

    def _on_width(self, _rv, width):
        if abs(width - self._last_width) < 1:
            return
        self._last_width = width
        # Wrapping changes with width: re-measure every line when shown.
        guess = (0, _single_line_height())
        self.recycle_view.data = [{"text": item["text"], "size": guess} for item in self.recycle_view.data]

    @staticmethod
    def _format_line(line: str) -> str:
        match = _TAG_RE.match(line)
        severity = match.group(1).upper() if match else "INFO"
        if "no response" in line.lower():
            # Unreachable IPs are expected during a scan: amber, not red.
            color = _PALETTE["WARN"]
        else:
            color = _PALETTE.get(severity, "#37474F")
        return f"[color={color}]{escape_markup(line)}[/color]"

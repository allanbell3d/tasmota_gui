"""Log panel widget for the Kivy mobile UI.

Lines are shown in a RecycleView, so only the rows on screen exist as
widgets. The previous design created one markup Label per line; a discovery
scan logs one line per unreachable IP, and building and rendering those labels
on the UI thread caused visible stalls (profiled: ~1.5 ms per line, frames up
to ~240 ms while ~1000 lines arrived).

Row heights (lines wrap) are kept in the data (``key_size``):

* when a line arrives, its height is estimated from the width of its text
  (font metrics only, no texture), so rows that were never shown are close;
* whenever a row view is (re)used, it reports its exact rendered height.

Scrolling follows new output only while the view is at the bottom (decided in
pixels). When the user has scrolled up, the visible text stays in place while
lines are added or the oldest ones are dropped.
"""

from __future__ import annotations

import re
from collections import deque
from typing import Deque, Dict, List, Optional

from kivy.clock import Clock
from kivy.core.text import Label as CoreLabel
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
_ROW_SPACING = dp(4)
_FOLLOW_TOLERANCE = dp(24)  # "at the bottom" if within this many pixels


def _single_line_height() -> float:
    return max(sp(14) * 1.25, dp(18))


class _TextMeasure:
    """Estimate wrapped label heights from font metrics (no textures).

    Simulates the greedy word wrap of a Label: words are measured once
    (cached), a word wider than the line is broken across lines.
    """

    _CACHE_LIMIT = 5000

    def __init__(self) -> None:
        self._label = CoreLabel(font_size=sp(14))
        self._line_height: Optional[float] = None
        self._space: Optional[float] = None
        self._widths: Dict[str, float] = {}

    def _width(self, word: str) -> float:
        width = self._widths.get(word)
        if width is None:
            if len(self._widths) >= self._CACHE_LIMIT:
                self._widths.clear()
            width = self._widths[word] = float(self._label.get_extents(word)[0])
        return width

    def line_height(self) -> float:
        if self._line_height is None:
            self._line_height = float(self._label.get_extents("Ag")[1]) or _single_line_height()
            self._space = float(self._label.get_extents(" ")[0])
        return self._line_height

    def height(self, plain: str, width: float) -> float:
        line_height = self.line_height()
        if width <= 0 or self._label.get_extents(plain)[0] <= width:
            return max(line_height, dp(18))  # fits on one line (most log lines)
        lines, current = 1, 0.0
        for word in plain.split():
            word_width = self._width(word)
            if current and current + self._space + word_width <= width:
                current += self._space + word_width
                continue
            if current:
                lines += 1
            # A word longer than the line is split character-wise.
            extra = int(word_width // width) if word_width > width else 0
            lines += extra
            current = word_width - extra * width
        return max(lines * line_height, dp(18))


class LogLineView(RecycleDataViewBehavior, Label):
    """One log line. Reports its exact rendered height back to the data."""

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
        self._report_trigger = Clock.create_trigger(self._report_height, -1)

    def refresh_view_attrs(self, rv, index, data):
        self._rv = rv
        self.index = index
        self.text_size = (max(rv.width - _HORIZONTAL_PADDING, 0), None)
        result = super().refresh_view_attrs(rv, index, data)
        # A recycled view whose new text wraps to the same size fires no
        # texture_size event, so always check once the text is applied.
        self._report_trigger()
        return result

    def _report_height(self, *_):
        rv = self._rv
        if rv is None or not (0 <= self.index < len(rv.data)):
            return
        item = rv.data[self.index]
        if item.get("text") != self.text:
            return  # data moved on; the new view for this row will report
        # Render now only if Kivy's own render is still pending, and cancel
        # that one so each refresh renders the text once.
        pending = getattr(self, "_trigger_texture", None)
        if pending is None:
            self.texture_update()
        elif pending.is_triggered:
            pending.cancel()
            self.texture_update()
        height = max(self.texture_size[1], dp(18))
        if abs(item["size"][1] - height) < 1:
            return
        # Replacing the item marks only this index as modified.
        rv.data[self.index] = dict(item, size=(0, height))


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
            spacing=_ROW_SPACING,
        )
        layout.bind(minimum_height=layout.setter("height"))
        self.recycle_view.add_widget(layout)
        self.recycle_view.viewclass = LogLineView
        self.recycle_view.bind(
            width=self._on_width, on_scroll_move=self._on_user_scroll, on_scroll_stop=self._on_user_scroll
        )
        self.add_widget(self.recycle_view)

        # Formatted lines currently shown (oldest first).
        self.log_lines: Deque[str] = deque(maxlen=self.MAX_LINES)
        self._pending_lines: Deque[str] = deque()
        self._flush_trigger = Clock.create_trigger(self._flush_pending, 0)
        self._measure = _TextMeasure()
        self._last_width = 0.0
        self._anchor_from_top: Optional[float] = None
        # Follow new output until the user scrolls up. Only user scroll
        # gestures change this: ScrollView itself moves scroll_y (it pins it
        # to the top while the content is shorter than the view).
        self._following = True

    # ------------------------------------------------------------------
    def clear(self):
        self.log_lines.clear()
        self._pending_lines.clear()
        self.recycle_view.data = []
        self.recycle_view.scroll_y = 1
        self._following = True

    def append_line(self, line: str):
        self._pending_lines.append(line)
        self._flush_trigger()

    # ------------------------------------------------------------------
    def _text_width(self) -> float:
        return max(self.recycle_view.width - _HORIZONTAL_PADDING, 0)

    def _content_height(self, data: Optional[List[Dict]] = None) -> float:
        """Height of the laid-out rows, computed from the data (the layout
        manager only catches up on the next frame)."""
        data = self.recycle_view.data if data is None else data
        if not data:
            return 0.0
        rows = sum(item["size"][1] for item in data)
        return rows + _ROW_SPACING * (len(data) - 1) + 2 * dp(8)

    def _scrollable(self, data: Optional[List[Dict]] = None) -> float:
        return self._content_height(data) - self.recycle_view.height

    def _at_bottom_px(self) -> bool:
        scrollable = self._scrollable()
        return scrollable > 0 and scrollable * self.recycle_view.scroll_y <= _FOLLOW_TOLERANCE

    def _on_user_scroll(self, *_):
        if self._scrollable() > 0:
            self._following = self._at_bottom_px()
        return False

    def _make_item(self, raw: str) -> Dict:
        return {
            "text": self._format_line(raw),
            "plain": raw,
            "size": (0, self._measure.height(raw, self._text_width())),
        }

    def _flush_pending(self, *_):
        if not self._pending_lines:
            return
        rv = self.recycle_view
        follow = self._following or not rv.data or self._at_bottom_px()
        if not follow:
            # Keep the text under the reader still: remember the distance from
            # the top, minus the rows about to be dropped from the top.
            scrollable = self._scrollable()
            offset = scrollable * (1 - rv.scroll_y)
            if self._anchor_from_top is not None:
                offset = self._anchor_from_top  # layout of a previous flush still pending

        data: List[Dict] = list(rv.data)
        while self._pending_lines:
            raw = self._pending_lines.popleft()
            item = self._make_item(raw)
            self.log_lines.append(item["text"])
            data.append(item)
        dropped = len(data) - self.MAX_LINES
        if dropped > 0:
            if not follow:
                offset -= sum(item["size"][1] + _ROW_SPACING for item in data[:dropped])
            data = data[dropped:]
        rv.data = data

        if follow:
            self._anchor_from_top = None
            rv.scroll_y = 0
            self._following = True
        else:
            self._anchor_from_top = max(offset, 0.0)
            Clock.schedule_once(self._restore_anchor, -1)

    def _restore_anchor(self, *_):
        rv = self.recycle_view
        offset = self._anchor_from_top
        self._anchor_from_top = None
        if offset is None:
            return
        scrollable = self._scrollable()
        if scrollable > 0:
            rv.scroll_y = min(1.0, max(0.0, 1 - offset / scrollable))

    def _on_width(self, _rv, width):
        if abs(width - self._last_width) < 1:
            return
        self._last_width = width
        # Wrapping changes with width: re-estimate every line; visible rows
        # then report their exact height.
        text_width = self._text_width()
        self.recycle_view.data = [
            dict(item, size=(0, self._measure.height(item.get("plain", ""), text_width)))
            for item in self.recycle_view.data
        ]

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

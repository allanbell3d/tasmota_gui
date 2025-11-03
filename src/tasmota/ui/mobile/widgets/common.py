"""Shared widgets and helpers for the mobile UI."""

from __future__ import annotations

from typing import List, Set, Tuple

from kivy.clock import Clock
from kivy.graphics import Color, Line
from kivy.graphics.instructions import InstructionGroup
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout

from constants import (
    CHECKBOX_BLACK,
    ESP_PLATFORM_COLORS,
    ESP_PLATFORM_TEXT_COLOR,
    SUMMARY_HEADER_TEXT_COLOR,
)


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


class BorderedWidgetMixin:
    """Mixin that renders borders around tables and their columns."""

    border_color = (0.4, 0.4, 0.4, 1)
    separator_color = (0.6, 0.6, 0.6, 1)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._separator_group = InstructionGroup()
        with self.canvas.after:
            Color(*self.border_color)
            self._border_line = Line(rectangle=(0, 0, 0, 0), width=dp(1))
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
            self._separator_group.add(Line(points=points, width=dp(1)))

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

        row_map = {}
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

        col_map = {}
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

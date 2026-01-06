"""Shared widgets and helpers for the mobile (Kivy) UI.

This module provides reusable components used across the mobile UI panels:
- Helper functions for common Kivy patterns
- Bordered container widgets for consistent styling
- Device identification utilities

The components here solve common problems when building Kivy interfaces:
1. Text wrapping - Kivy labels don't auto-wrap by default
2. Checkbox state management - Preventing callbacks during programmatic updates
3. Visual consistency - Bordered layouts matching the app's design language
4. Device identification - Extracting platform and key info from scan results

Main Components:
    format_progress(): Calculate progress percentages for scan operations
    bind_auto_wrap(): Configure labels to wrap text at container width
    set_checkbox_silent(): Update checkbox without triggering callbacks
    device_key(): Generate unique identifier from device IP
    get_device_platform(): Determine ESP8266 vs ESP32 from device metadata
    BorderedWidgetMixin: Mixin that draws borders around widgets
    BorderedBoxLayout: BoxLayout with visible borders
    BorderedGridLayout: GridLayout with visible borders and separators
"""

from __future__ import annotations

from typing import List, Set, Tuple

from kivy.clock import Clock
from kivy.graphics import Color, Line
from kivy.graphics.instructions import InstructionGroup
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout

from tasmota.constants import (
    BORDER_COLOR,
    CATEGORY_LABEL_COLOR,
    CHECKBOX_COLOR,
    ESP_PLATFORM_COLORS,
    ESP_PLATFORM_TEXT_COLOR,
    FALLBACK_BG_COLOR,
    SEPARATOR_COLOR,
    SUMMARY_HEADER_TEXT_COLOR,
)


def format_progress(done: int, total: int) -> Tuple[int, int, int]:
    """Calculate progress percentage and capped values.

    Args:
        done: Number of completed items.
        total: Total number of items.

    Returns:
        Tuple of (percentage, capped_done, total).
    """
    if total <= 0:
        return (0, 0, 0)
    pct = min(100, int((done / total) * 100))
    capped_done = min(done, total)
    return (pct, capped_done, total)


def bind_auto_wrap(label) -> None:
    """Configure a Label to automatically wrap text to fit its width.

    Kivy Labels don't wrap text by default - they just clip or overflow.
    To enable wrapping, you need to set text_size to (width, None), but
    only after the label has its final width. This helper binds to width
    changes so the text_size is updated whenever the label resizes.

    This is especially important for responsive layouts where label widths
    change based on screen size or container dimensions.

    Args:
        label: A Kivy Label (or Label subclass) to configure

    Example:
        name_label = Label(text="Some long text...", halign="left")
        bind_auto_wrap(name_label)  # Text will now wrap at label boundaries
    """
    label.bind(width=lambda inst, _: setattr(inst, "text_size", (inst.width, None)))


def set_checkbox_silent(checkbox, callback, value: bool) -> None:
    """Set checkbox state without triggering its callback.

    When updating a checkbox programmatically (e.g., from RecycleView data),
    you often don't want to trigger the callback that normally fires when
    the user taps the checkbox. This helper temporarily disconnects the
    callback, sets the value, then reconnects it.

    This pattern is especially important in RecycleView rows where checkbox
    state comes from the data model - triggering callbacks during refresh
    would cause unwanted side effects.

    Args:
        checkbox: The Kivy CheckBox widget to update
        callback: The function currently bound to checkbox.active
        value: The boolean state to set (True = checked, False = unchecked)

    Example:
        def _on_checkbox_toggle(self, checkbox, active):
            # Handle user tap
            self.data['selected'] = active

        def refresh_view_attrs(self, rv, index, data):
            # Update from data without triggering toggle handler
            set_checkbox_silent(self.checkbox, self._on_checkbox_toggle, data['selected'])
    """
    checkbox.unbind(active=callback)
    checkbox.active = value
    checkbox.bind(active=callback)


def device_key(device) -> str:
    """Generate a unique identifier key for a device.

    This extracts the device's IP address as a string to use as a
    dictionary key or for lookups. The IP address is the primary way
    we identify Tasmota devices across the application.

    Args:
        device: A device object with an 'IP' attribute (from discovery results)

    Returns:
        The device's IP address as a string, or empty string if not available

    Example:
        >>> devices = {device_key(d): d for d in discovered}
        >>> if device_key(selected) in devices:
        ...     # Device is known
    """
    return str(getattr(device, "IP", "") or "")


def get_device_platform(device) -> str:
    """Infer the device platform (ESP8266/ESP32) from discovery metadata.

    Examines the Hardware, Platform, and ChipId attributes from the device's
    Status 0 response to determine which ESP chip family it uses.

    This is used to:
    - Select the correct OTA firmware URL (ESP8266 vs ESP32 differ)
    - Color-code device rows in the UI (blue tint vs green tint)
    - Filter devices by platform in the OTA panel

    Args:
        device: A DeviceResult object from discovery, with Hardware/Platform/ChipId attrs

    Returns:
        "ESP32", "ESP8266", or "UNKNOWN" if platform can't be determined
    """
    fragments = " ".join(
        str(getattr(device, attr, "") or "") for attr in ("Hardware", "Platform", "ChipId")
    ).upper()
    if "ESP32" in fragments:
        return "ESP32"
    if "ESP82" in fragments or "ESP8266" in fragments:
        return "ESP8266"
    return "UNKNOWN"


class BorderedWidgetMixin:
    """Mixin that draws borders and separator lines around container widgets.

    This mixin adds visual structure to BoxLayout and GridLayout containers
    by drawing:
    1. An outer border around the entire container
    2. Separator lines between child widgets (for multi-column/row layouts)

    The borders are drawn on the canvas.after layer so they appear on top
    of child widgets. They automatically update when the container or its
    children are resized or repositioned.

    Usage:
        Combine with a layout class via multiple inheritance:

        class MyBorderedBox(BorderedWidgetMixin, BoxLayout):
            pass

        container = MyBorderedBox(orientation="horizontal")
        container.add_widget(Label(text="Col 1"))
        container.add_widget(Label(text="Col 2"))
        # A vertical line will be drawn between the columns

    Class Attributes:
        border_color: RGBA tuple for the outer border (default: medium gray)
        separator_color: RGBA tuple for lines between children (default: lighter gray)

    Note:
        Pre-built classes BorderedBoxLayout and BorderedGridLayout are available
        for convenience - you don't need to use this mixin directly.
    """

    border_color = BORDER_COLOR
    separator_color = SEPARATOR_COLOR

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._separator_group = InstructionGroup()
        with self.canvas.after:
            Color(*self.border_color)
            self._border_line = Line(rectangle=(0, 0, 0, 0), width=dp(1))
            self.canvas.after.add(self._separator_group)
        self._update_trigger = Clock.create_trigger(self._update_borders, 0.05)
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
    """BoxLayout with automatic border and separator line drawing.

    A drop-in replacement for BoxLayout that adds:
    - An outer border around the container
    - Separator lines between children (vertical for horizontal orientation,
      horizontal for vertical orientation)

    Example:
        # Create a horizontal box with bordered columns
        row = BorderedBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(50))
        row.add_widget(Label(text="Name"))
        row.add_widget(Label(text="Value"))
        # A vertical separator line appears between the two labels
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


class BorderedGridLayout(BorderedWidgetMixin, GridLayout):
    """GridLayout with automatic border and grid line drawing.

    A drop-in replacement for GridLayout that adds:
    - An outer border around the container
    - Separator lines between rows and columns, creating a table-like appearance

    The grid lines are drawn based on child widget positions, so they work
    correctly regardless of column count or row heights.

    Example:
        # Create a 2-column grid with visible cell borders
        grid = BorderedGridLayout(cols=2, size_hint_y=None)
        grid.bind(minimum_height=grid.setter('height'))
        grid.add_widget(Label(text="Name"))
        grid.add_widget(Label(text="John"))
        grid.add_widget(Label(text="Age"))
        grid.add_widget(Label(text="25"))
        # Grid lines appear between all cells
    """

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

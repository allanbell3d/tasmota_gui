"""RecycleView row components for device lists in the mobile UI.

This module provides efficient, scrollable list views for displaying Tasmota
devices. It uses Kivy's RecycleView pattern, which reuses a small pool of
row widgets as the user scrolls - essential for handling large device lists
without consuming excessive memory.

The key concept is the separation of data and views:
- Data lives in RecycleView.data as a list of dictionaries
- Views (row widgets) are created once and reused via refresh_view_attrs()
- When the user scrolls, existing views are updated with new data

Main Components:
    DeviceRowView: Base row class with platform-colored background
    SummaryRowView: Row with dual checkboxes (cmd + ota selection)
    OTARowView: Row with single checkbox and queue status indicator
    DeviceRecycleView: The scrollable container that manages row recycling

Row Architecture:
    Each row displays: [Checkboxes] [Device Info] [Optional extras]

    - Checkboxes: Selection controls (varies by subclass)
    - Device Info: Name, IP/Platform/Version, Hardware
    - Background color: Blue tint for ESP8266, green for ESP32

Usage Example:
    # Create a RecycleView with SummaryRowView rows
    rv = DeviceRecycleView(SummaryRowView)

    # Populate with device data
    rv.data = [
        {"ip": "192.168.1.100", "name": "Kitchen", "platform": "ESP32", ...},
        {"ip": "192.168.1.101", "name": "Garage", "platform": "ESP8266", ...},
    ]

    # Data changes automatically update visible rows
    rv.data[0]["cmd_selected"] = True
    rv.refresh_from_data()
"""

from __future__ import annotations

from kivy.graphics import Color, Line, Rectangle
from kivy.graphics.instructions import InstructionGroup
from kivy.metrics import dp
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.checkbox import CheckBox
from kivy.uix.label import Label
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior

from tasmota.constants import DEVICE_ROW_HEIGHT_DP

from .common import (
    CHECKBOX_COLOR,
    ESP_PLATFORM_COLORS,
    ESP_PLATFORM_TEXT_COLOR,
    FALLBACK_BG_COLOR,
    SEPARATOR_COLOR,
    bind_auto_wrap,
    set_checkbox_silent,
)

# Re-export for external use

# Column separator color alias (vertical lines between checkbox and info columns)
COLUMN_SEPARATOR_COLOR = SEPARATOR_COLOR


class DeviceRowView(RecycleDataViewBehavior, BoxLayout):
    """Base RecycleView row for displaying device information.

    This is the foundation for all device list rows in the mobile UI.
    It provides:
    - Platform-colored background (blue for ESP8266, green for ESP32)
    - Three-line info display: Name, IP/Platform/Version, Hardware
    - Column separator lines between sections
    - Automatic text wrapping for long device names

    Subclasses customize the row by overriding:
    - _build_checkboxes(): Add selection checkboxes on the left
    - _build_extra_widgets(): Add widgets on the right (e.g., queue status)

    Data Binding:
        The row receives data via refresh_view_attrs() when RecycleView
        recycles the widget. Data dictionary keys map to properties:
        - ip → self.ip
        - name → self.name
        - platform → self.platform ("ESP32" or "ESP8266")
        - version → self.version
        - hardware → self.hardware

    Properties:
        index: Position in the RecycleView data list
        ip: Device IP address (e.g., "192.168.1.100")
        name: Device name or hostname
        platform: "ESP32", "ESP8266", or "UNKNOWN"
        version: Tasmota firmware version string
        hardware: Hardware description (chip type, etc.)
    """

    index = NumericProperty(0)
    ip = StringProperty("")
    name = StringProperty("")
    platform = StringProperty("")
    version = StringProperty("")
    hardware = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(DEVICE_ROW_HEIGHT_DP),
            spacing=dp(8),
            **kwargs,
        )

        # Background color - will be updated in refresh_view_attrs
        with self.canvas.before:
            self._bg_color = Color(*FALLBACK_BG_COLOR)
            self._bg_rect = Rectangle(pos=self.pos, size=self.size)
        # Column separator lines (vertical lines between checkbox columns and info)
        self._separator_group = InstructionGroup()
        self.canvas.after.add(self._separator_group)
        self._tracked_children = set()
        self.bind(pos=self._update_bg, size=self._update_bg, children=self._on_children_changed)

        # Build checkboxes (subclasses override)
        self._build_checkboxes()

        # Info labels
        info_box = BoxLayout(orientation="vertical", spacing=dp(4))

        self._name_label = Label(text="", halign="left", valign="middle", color=ESP_PLATFORM_TEXT_COLOR)
        bind_auto_wrap(self._name_label)
        info_box.add_widget(self._name_label)

        self._meta_label = Label(
            text="",
            halign="left",
            valign="middle",
            font_size="12sp",
            color=ESP_PLATFORM_TEXT_COLOR,
        )
        bind_auto_wrap(self._meta_label)
        info_box.add_widget(self._meta_label)

        self._hardware_label = Label(
            text="",
            halign="left",
            valign="middle",
            font_size="12sp",
            color=ESP_PLATFORM_TEXT_COLOR,
        )
        bind_auto_wrap(self._hardware_label)
        info_box.add_widget(self._hardware_label)

        self.add_widget(info_box)

        # Extra widgets (subclasses override)
        self._build_extra_widgets()

    def _build_checkboxes(self):
        """Override in subclasses to add checkboxes."""
        pass

    def _build_extra_widgets(self):
        """Override in subclasses to add extra widgets after info box."""
        pass

    def _on_children_changed(self, *_):
        """Track children for position/size changes to update separators."""
        current_children = set(self.children)
        # Unbind removed children
        for widget in list(self._tracked_children):
            if widget not in current_children:
                widget.unbind(pos=self._update_bg, size=self._update_bg)
                self._tracked_children.remove(widget)
        # Bind new children
        for widget in current_children:
            if widget not in self._tracked_children:
                widget.bind(pos=self._update_bg, size=self._update_bg)
                self._tracked_children.add(widget)
        self._update_bg()

    def _update_bg(self, *args):
        """Update background rectangle and column separator lines."""
        if hasattr(self, "_bg_rect"):
            self._bg_rect.pos = self.pos
            self._bg_rect.size = self.size
        # Draw vertical separator lines between columns
        if hasattr(self, "_separator_group"):
            self._separator_group.clear()
            if len(self.children) > 1:
                self._separator_group.add(Color(*COLUMN_SEPARATOR_COLOR))
                # Sort children by x position (left to right)
                ordered = sorted(self.children, key=lambda c: c.x)
                for left, right in zip(ordered[:-1], ordered[1:]):
                    # Draw vertical line at midpoint between adjacent children
                    x = (left.right + right.x) / 2.0
                    self._separator_group.add(Line(points=[x, self.y, x, self.top], width=dp(1)))

    def _update_labels(self):
        """Update label text from properties."""
        self._name_label.text = self.name

        meta_parts = [self.ip]
        if self.platform:
            meta_parts.append(self.platform)
        if self.version:
            meta_parts.append(self.version)
        self._meta_label.text = " • ".join(meta_parts)

        self._hardware_label.text = self.hardware

    def _update_background_color(self):
        """Update background color based on platform."""
        color = ESP_PLATFORM_COLORS.get(self.platform, ESP_PLATFORM_COLORS.get("UNKNOWN", FALLBACK_BG_COLOR))
        self._bg_color.rgba = color

    def refresh_view_attrs(self, rv, index, data):
        """Called when view is recycled with new data."""
        self._rv = rv
        self.index = index

        # Update properties from data
        self.ip = data.get("ip", "")
        self.name = data.get("name", "")
        self.platform = data.get("platform", "")
        self.version = data.get("version", "")
        self.hardware = data.get("hardware", "")

        # Update UI
        self._update_labels()
        self._update_background_color()
        self._update_bg()  # Force canvas update after recycling

        return super().refresh_view_attrs(rv, index, data)


class SummaryRowView(DeviceRowView):
    """Device row with dual selection checkboxes for commands and OTA.

    Used in the Summary panel where users can independently select devices for:
    - Command execution (cmd checkbox) - send backlog commands
    - Firmware update (ota checkbox) - trigger OTA upgrade

    Layout: [Cmd ☐] [OTA ☐] [Device Info]

    Additional Data Keys:
        cmd_selected: Boolean for command checkbox state
        ota_selected: Boolean for OTA checkbox state
    """

    cmd_selected = BooleanProperty(False)
    ota_selected = BooleanProperty(False)

    def _build_checkboxes(self):
        """Add cmd and ota checkboxes."""
        checkbox_size = (dp(40), dp(40))

        self.cmd_checkbox = CheckBox(size_hint=(None, None), size=checkbox_size, color=CHECKBOX_COLOR)
        self.ota_checkbox = CheckBox(size_hint=(None, None), size=checkbox_size, color=CHECKBOX_COLOR)

        self.cmd_checkbox.bind(active=self._on_cmd_toggle)
        self.ota_checkbox.bind(active=self._on_ota_toggle)

        cmd_holder = AnchorLayout(anchor_x="center", anchor_y="center", size_hint=(None, 1), width=dp(88))
        cmd_holder.add_widget(self.cmd_checkbox)
        self.add_widget(cmd_holder)

        ota_holder = AnchorLayout(anchor_x="center", anchor_y="center", size_hint=(None, 1), width=dp(88))
        ota_holder.add_widget(self.ota_checkbox)
        self.add_widget(ota_holder)

    def _on_cmd_toggle(self, checkbox, active):
        """Update data when cmd checkbox changes."""
        if hasattr(self, "_rv") and self._rv is not None:
            if 0 <= self.index < len(self._rv.data):
                self._rv.data[self.index]["cmd_selected"] = active

    def _on_ota_toggle(self, checkbox, active):
        """Update data when ota checkbox changes."""
        if hasattr(self, "_rv") and self._rv is not None:
            if 0 <= self.index < len(self._rv.data):
                self._rv.data[self.index]["ota_selected"] = active

    def refresh_view_attrs(self, rv, index, data):
        """Update checkboxes from data."""
        self.cmd_selected = data.get("cmd_selected", False)
        self.ota_selected = data.get("ota_selected", False)

        # Update checkboxes without triggering callbacks
        set_checkbox_silent(self.cmd_checkbox, self._on_cmd_toggle, self.cmd_selected)
        set_checkbox_silent(self.ota_checkbox, self._on_ota_toggle, self.ota_selected)

        return super().refresh_view_attrs(rv, index, data)


class OTARowView(DeviceRowView):
    """Device row for the OTA panel with selection and queue status.

    Used in the OTA Updates panel where users select devices to add to
    the firmware update queue. Shows which platform queue (if any) the
    device is currently in.

    Layout: [Select ☐] [Device Info] [Queue Status]

    Additional Data Keys:
        selected: Boolean for selection checkbox state
        queue_platform: "ESP8266", "ESP32", or "" if not queued
    """

    selected = BooleanProperty(False)
    queue_platform = StringProperty("")

    def _build_checkboxes(self):
        """Add single selection checkbox."""
        checkbox_size = (dp(40), dp(40))

        self.checkbox = CheckBox(size_hint=(None, None), size=checkbox_size, color=CHECKBOX_COLOR)
        self.checkbox.bind(active=self._on_select_toggle)

        checkbox_holder = AnchorLayout(anchor_x="center", anchor_y="center", size_hint=(None, 1), width=dp(88))
        checkbox_holder.add_widget(self.checkbox)
        self.add_widget(checkbox_holder)

    def _build_extra_widgets(self):
        """Add queue status label."""
        self._queue_label = Label(text="", size_hint=(None, 1), width=dp(100), color=ESP_PLATFORM_TEXT_COLOR)
        self.add_widget(self._queue_label)

    def _on_select_toggle(self, checkbox, active):
        """Update data when checkbox changes."""
        if hasattr(self, "_rv") and self._rv is not None:
            if 0 <= self.index < len(self._rv.data):
                self._rv.data[self.index]["selected"] = active

    def refresh_view_attrs(self, rv, index, data):
        """Update checkbox and queue label from data."""
        self.selected = data.get("selected", False)
        self.queue_platform = data.get("queue_platform", "")

        # Update checkbox without triggering callbacks
        set_checkbox_silent(self.checkbox, self._on_select_toggle, self.selected)

        # Update queue label
        self._queue_label.text = self.queue_platform

        return super().refresh_view_attrs(rv, index, data)


class DeviceRecycleView(RecycleView):
    """Scrollable container for device rows with efficient view recycling.

    This is a pre-configured RecycleView that handles the boilerplate of
    setting up proper layout management for device lists. It creates a
    vertical RecycleBoxLayout with appropriate spacing and padding.

    Args:
        viewclass: The row class to use (SummaryRowView, OTARowView, etc.)
        row_height: Height of each row in dp. Defaults to DEVICE_ROW_HEIGHT_DP.

    Usage:
        # Create with custom row class
        rv = DeviceRecycleView(SummaryRowView)

        # Populate with device data dicts
        rv.data = [
            {"ip": "192.168.1.100", "name": "Device1", ...},
            {"ip": "192.168.1.101", "name": "Device2", ...},
        ]

        # Update data and refresh display
        rv.data[0]["cmd_selected"] = True
        rv.refresh_from_data()
    """

    def __init__(self, viewclass, row_height=None, **kwargs):
        super().__init__(**kwargs)
        if row_height is None:
            row_height = dp(DEVICE_ROW_HEIGHT_DP)

        # Create layout manager with spacing for visual separation
        layout = RecycleBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            default_size_hint=(1, None),
            default_size=(0, row_height),
            spacing=dp(6),
            padding=dp(4),
        )
        layout.bind(minimum_height=layout.setter("height"))
        self.add_widget(layout)

        # Set viewclass after layout
        self.viewclass = viewclass

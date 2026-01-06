"""RecycleView row component for command library entries.

This module provides the row view for displaying Tasmota commands in a
scrollable list. Each row shows a command from the command library with
its name, category, and default value. Users can:
- Select commands via checkbox to include in the backlog
- Tap the command name to see the full description in a popup

The design follows the same RecycleView pattern as device_row.py:
- Data is a list of dicts in RecycleView.data
- Row widgets are recycled as the user scrolls
- Checkbox state syncs bidirectionally with data

Row Layout:
    [☐ Checkbox] [Command Name / Category] [Default Value]

Main Components:
    CommandLabelButton: Label that responds to taps (shows description popup)
    CommandRowView: The recyclable row widget
    CommandRecycleView: Scrollable container with layout management
"""

from __future__ import annotations

from kivy.graphics import Color, Line
from kivy.metrics import dp
from kivy.properties import BooleanProperty, NumericProperty, StringProperty
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.scrollview import ScrollView

from tasmota.constants import COMMAND_ROW_HEIGHT_DP

from .common import BorderedBoxLayout, CATEGORY_LABEL_COLOR, CHECKBOX_COLOR, bind_auto_wrap, set_checkbox_silent

# Column layout constants - single source of truth
COMMAND_COL_CHECKBOX_WIDTH = dp(64)
COMMAND_COL_COMMAND_HINT = 0.6
COMMAND_COL_VALUE_HINT = 0.4
COMMAND_ROW_SPACING = dp(8)
COMMAND_ROW_HEIGHT = dp(COMMAND_ROW_HEIGHT_DP)


class CommandLabelButton(ButtonBehavior, Label):
    """Label that responds to tap/click events.

    Combines Label's text display with ButtonBehavior's on_release event.
    Used for the command name so users can tap it to see the full description.
    """


class CommandRowView(RecycleDataViewBehavior, BorderedBoxLayout):
    """RecycleView row for displaying a command library entry.

    Each row shows one command with:
    - Checkbox for selection (left side)
    - Command name in bold with category below
    - Default value (right side)

    Tapping the command name opens a popup with the full description,
    helpful for commands with long explanations or examples.

    Data Binding:
        Data dictionary keys map to properties:
        - name → Command name (e.g., "TelePeriod")
        - category → Category label (e.g., "MQTT")
        - value → Default value (e.g., "30")
        - description → Full description text (shown in popup)
        - selected → Boolean checkbox state

    Properties:
        index: Position in RecycleView data list
        name: Command name (displayed in bold)
        category: Category grouping label
        value: Default/suggested value
        description: Full description (for popup)
        selected: Whether checkbox is checked
    """

    index = NumericProperty(0)
    name = StringProperty("")
    category = StringProperty("")
    value = StringProperty("")
    description = StringProperty("")
    selected = BooleanProperty(False)

    # Cached popup instance shared across all rows to avoid recreation overhead
    _cached_popup = None
    _cached_popup_label = None
    _cached_popup_scroll = None

    def __init__(self, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=COMMAND_ROW_HEIGHT,
            spacing=COMMAND_ROW_SPACING,
            padding=(0, dp(6)),
            **kwargs,
        )
        self._rv = None

        # Checkbox - use shared color constant
        checkbox_size = (dp(40), dp(40))
        self.checkbox = CheckBox(size_hint=(None, None), size=checkbox_size, color=CHECKBOX_COLOR)
        self.checkbox.bind(active=self._on_checkbox_toggle)

        checkbox_holder = AnchorLayout(
            anchor_x="center",
            anchor_y="center",
            size_hint=(None, 1),
            width=COMMAND_COL_CHECKBOX_WIDTH,
        )
        checkbox_holder.add_widget(self.checkbox)
        self.add_widget(checkbox_holder)

        # Command + category column
        command_box = BoxLayout(orientation="vertical", size_hint=(COMMAND_COL_COMMAND_HINT, 1), spacing=dp(2))

        self._command_label = CommandLabelButton(
            text="",
            markup=True,
            halign="left",
            valign="middle",
            size_hint_y=0.6,
        )
        bind_auto_wrap(self._command_label)
        self._command_label.bind(on_release=self._show_description_popup)
        command_box.add_widget(self._command_label)

        self._category_label = Label(
            text="",
            halign="left",
            valign="middle",
            font_size="11sp",
            color=CATEGORY_LABEL_COLOR,
            size_hint_y=0.4,
        )
        bind_auto_wrap(self._category_label)
        command_box.add_widget(self._category_label)

        self.add_widget(command_box)

        # Value column
        self._value_label = Label(
            text="",
            halign="left",
            valign="middle",
            size_hint=(COMMAND_COL_VALUE_HINT, 1),
        )
        bind_auto_wrap(self._value_label)
        self.add_widget(self._value_label)

    def _on_checkbox_toggle(self, checkbox, active):
        """Update data when checkbox changes."""
        if self._rv is not None and 0 <= self.index < len(self._rv.data):
            self._rv.data[self.index]["selected"] = active

    def _show_description_popup(self, *_):
        """Show popup with full command description.

        Uses a cached popup instance shared across all CommandRowView instances
        to avoid the overhead of creating new widgets on each tap.
        """
        if not self.description:
            return

        title = self.name.strip() or "Command Description"

        # Create or reuse cached popup widgets
        if CommandRowView._cached_popup is None:
            layout = BoxLayout(orientation="vertical", spacing=dp(12), padding=dp(12))

            description_label = Label(
                text="",
                halign="left",
                valign="top",
                size_hint=(1, None),
            )
            description_label.bind(texture_size=lambda inst, size: setattr(inst, "height", max(size[1], dp(10))))
            bind_auto_wrap(description_label)

            scroll = ScrollView(size_hint=(1, 1))
            scroll.add_widget(description_label)
            layout.add_widget(scroll)

            close_button = Button(text="Close", size_hint_y=None, height=dp(48))
            layout.add_widget(close_button)

            popup = Popup(title="", content=layout, size_hint=(0.9, 0.6))
            close_button.bind(on_release=lambda *_: popup.dismiss())

            # Cache the widgets
            CommandRowView._cached_popup = popup
            CommandRowView._cached_popup_label = description_label
            CommandRowView._cached_popup_scroll = scroll

        # Update cached popup with current data
        CommandRowView._cached_popup.title = title
        CommandRowView._cached_popup_label.text = self.description
        CommandRowView._cached_popup_scroll.scroll_y = 1  # Reset scroll to top
        CommandRowView._cached_popup.open()

    def _update_labels(self):
        """Update label text from properties."""
        self._command_label.text = f"[b]{self.name}[/b]" if self.name else ""
        self._category_label.text = f"Category: {self.category}" if self.category else ""
        self._value_label.text = self.value

    def refresh_view_attrs(self, rv, index, data):
        """Called when view is recycled with new data."""
        self._rv = rv
        self.index = index

        # Update properties from data
        self.name = data.get("name", "")
        self.category = data.get("category", "")
        self.value = data.get("value", "")
        self.description = data.get("description", "")
        self.selected = data.get("selected", False)

        # Update checkbox without triggering callbacks
        set_checkbox_silent(self.checkbox, self._on_checkbox_toggle, self.selected)

        # Update labels
        self._update_labels()

        return super().refresh_view_attrs(rv, index, data)


class CommandRecycleView(RecycleView):
    """Scrollable container for command library rows.

    Pre-configured RecycleView with:
    - Vertical RecycleBoxLayout for row arrangement
    - CommandRowView as the viewclass
    - Appropriate spacing and padding

    The RecycleView efficiently handles large command libraries by only
    creating widgets for visible rows, recycling them as the user scrolls.

    Usage:
        rv = CommandRecycleView()
        rv.data = [
            {"name": "TelePeriod", "value": "30", "category": "MQTT", ...},
            {"name": "SetOption56", "value": "1", "category": "WiFi", ...},
        ]

        # Get selected commands
        selected = [d for d in rv.data if d.get("selected")]
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        layout = RecycleBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            default_size_hint=(1, None),
            default_size=(0, COMMAND_ROW_HEIGHT),
            spacing=dp(6),
            padding=(0, dp(4)),  # Only vertical padding, no horizontal offset
        )
        layout.bind(minimum_height=layout.setter("height"))
        self.add_widget(layout)

        self.viewclass = CommandRowView

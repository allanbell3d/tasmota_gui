"""Command library widgets for the mobile UI."""

from __future__ import annotations

from typing import Callable, Dict, Iterable, List, Optional, Set

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from tasmota.core.commands import DEFAULT_COMMANDS, CommandRecord

from .widgets.common import BorderedBoxLayout


class CommandLabelButton(ButtonBehavior, Label):
    """Label styled control that behaves like a button."""


class CommandLibraryRow(BorderedBoxLayout):
    """Single command entry with checkbox."""

    MIN_HEIGHT = dp(68)

    def __init__(self, record: CommandRecord, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            spacing=dp(8),
            padding=(0, dp(6)),
            **kwargs,
        )
        self.record = record
        checkbox_size = (dp(40), dp(40))
        self.checkbox = CheckBox(size_hint=(None, None), size=checkbox_size)

        checkbox_holder = AnchorLayout(anchor_x="center", anchor_y="center", size_hint=(None, 1), width=dp(64))
        checkbox_holder.add_widget(self.checkbox)
        self.add_widget(checkbox_holder)

        command_box = BoxLayout(orientation="vertical", size_hint=(0.6, 1), spacing=dp(4))

        self.command_label = CommandLabelButton(
            text="",
            markup=True,
            halign="left",
            valign="top",
        )
        self.command_label.size_hint_y = None
        self.command_label.bind(on_release=self._show_description_popup)
        command_box.add_widget(self.command_label)

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

        self._labels = [self.command_label, self.value_label, self.category_label]
        self._description_text = ""

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
        self._set_label_text(self.category_label, f"Category: {category_text}" if category_text else "")
        self._set_label_text(self.value_label, value_text)
        self._description_text = description_text

        self._recalculate_height()

    def build_command(self) -> str:
        value = (self.record.value or "").strip()
        return f"{self.record.name} {value}".strip()

    def _set_label_text(self, label: Label, text: str):
        label.text = text
        label.opacity = 1 if text else 0
        label.texture_update()
        if text:
            label.height = label.texture_size[1] + dp(4)
        else:
            label.height = 0

    def _on_label_width(self, label: Label, _: float):
        label.text_size = (label.width, None)

    def _on_label_texture(self, label: Label, *_):
        if hasattr(label, "texture_size"):
            if label.text:
                label.height = label.texture_size[1] + dp(4)
            else:
                label.height = 0
        Clock.schedule_once(lambda *_: self._recalculate_height(), 0)

    def _recalculate_height(self):
        command_height = self.command_label.texture_size[1] if self.command_label.text else 0
        category_height = (
            self.category_label.texture_size[1]
            if self.category_label is not None and self.category_label.text
            else 0
        )
        value_height = self.value_label.texture_size[1] if self.value_label.text else 0
        content_height = max(command_height + category_height, value_height)
        self.height = max(self.MIN_HEIGHT, content_height + dp(16))

    def _show_description_popup(self, *_):
        if not self._description_text:
            return

        layout = BoxLayout(orientation="vertical", spacing=dp(12), padding=dp(12))
        title = (self.record.name or "Command Description").strip() or "Command Description"

        description_label = Label(
            text=self._description_text,
            halign="left",
            valign="top",
            size_hint=(1, None),
        )
        description_label.bind(
            texture_size=lambda inst, size: setattr(inst, "height", max(size[1], dp(10)))
        )
        description_label.bind(width=lambda inst, _: setattr(inst, "text_size", (inst.width, None)))
        description_label.text_size = (0, None)

        scroll = ScrollView(size_hint=(1, 1))
        scroll.add_widget(description_label)
        layout.add_widget(scroll)

        close_button = Button(text="Close", size_hint_y=None, height=dp(48))
        layout.add_widget(close_button)

        popup = Popup(title=title, content=layout, size_hint=(0.9, 0.6))
        close_button.bind(on_release=lambda *_: popup.dismiss())
        popup.open()


class CommandLibraryPanel(BoxLayout):
    """Command selection and backlog configuration."""

    def __init__(
        self,
        send_callback: Callable[[Dict], None],
        goto_ota_callback: Optional[Callable[[], None]] = None,
        **kwargs,
    ):
        super().__init__(orientation="vertical", spacing=dp(8), **kwargs)
        self.send_callback = send_callback
        self.goto_ota_callback = goto_ota_callback
        self.library_rows: List[CommandLibraryRow] = []
        self.library_popup: Optional[Popup] = None
        self.library_records: List[CommandRecord] = []
        self._row_cache: Dict[str, CommandLibraryRow] = {}
        self._search_trigger = None
        self._staged_ips: List[str] = []

        self._ensure_library_components()

        self.backlog_label = Label(text="Backlog Commands", size_hint_y=None, height=dp(36))
        self.backlog_input = TextInput(text="\n".join(DEFAULT_COMMANDS), multiline=True, size_hint=(1, 0.4))

        self.add_widget(self.backlog_label)
        self.add_widget(self.backlog_input)

        self.targets_panel = BorderedBoxLayout(
            orientation="vertical",
            size_hint=(1, None),
            spacing=dp(4),
            padding=dp(8),
        )
        self.targets_panel.bind(minimum_height=self.targets_panel.setter("height"))
        self.staged_title = Label(text="Staged Devices (0)", size_hint_y=None, height=dp(24))
        self.targets_panel.add_widget(self.staged_title)
        self.staged_targets_label = Label(
            text="No devices staged.",
            halign="left",
            valign="top",
            size_hint=(1, None),
        )
        self.staged_targets_label.bind(
            size=lambda inst, size: setattr(inst, "text_size", (size[0], None)),
            texture_size=lambda inst, size: setattr(
                inst, "height", max(size[1], dp(20)) if inst.text else dp(20)
            ),
        )
        self.targets_panel.add_widget(self.staged_targets_label)
        self.add_widget(self.targets_panel)
        self._refresh_staged_targets()

        controls = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        self.btn_open_library = Button(text="Open Command Library")
        self.btn_open_library.bind(on_release=lambda *_: self._open_library_popup())
        controls.add_widget(self.btn_open_library)
        self.btn_clear_backlog = Button(text="Clear Backlog")
        self.btn_clear_backlog.bind(on_release=lambda *_: setattr(self.backlog_input, "text", ""))
        controls.add_widget(self.btn_clear_backlog)
        self.add_widget(controls)

        nav_box = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        nav_box.add_widget(Label(text="Need firmware?", size_hint=(0.6, 1)))
        self.btn_open_ota = Button(text="OTA Updates")
        self.btn_open_ota.bind(on_release=lambda *_: self._open_ota())
        nav_box.add_widget(self.btn_open_ota)
        self.add_widget(nav_box)

        self.btn_send = Button(text="Run Selected", size_hint_y=None, height=dp(60))
        self.btn_send.bind(on_release=lambda *_: self._emit_send())
        self.add_widget(self.btn_send)

    def set_library(self, records: Iterable[CommandRecord]):
        self._ensure_library_components()
        self.library_records = list(records)
        self._update_category_options()
        self._refresh_library_rows()

    def stage_command_targets(self, ips: Iterable[str]) -> Dict[str, int]:
        unique = sorted({str(ip).strip() for ip in ips if ip})
        self._staged_ips = unique
        self._refresh_staged_targets()
        return {"staged": len(unique), "total": len(unique)}

    def get_staged_ips(self) -> List[str]:
        return list(self._staged_ips)

    def clear_staged_targets(self):
        self._staged_ips = []
        self._refresh_staged_targets()

    def _refresh_staged_targets(self):
        count = len(self._staged_ips)
        self.staged_title.text = f"Staged Devices ({count})"
        if count == 0:
            self.staged_targets_label.text = "No devices staged."
            return
        preview = self._staged_ips[:5]
        remaining = count - len(preview)
        lines = list(preview)
        if remaining > 0:
            lines.append(f"… +{remaining} more")
        self.staged_targets_label.text = "\n".join(lines)

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
        self.library_container = GridLayout(cols=1, spacing=dp(6), size_hint_y=None, padding=dp(8))
        self.library_container.bind(minimum_height=self.library_container.setter("height"))
        self.library_scroll = ScrollView(size_hint=(1, 1))
        self.library_scroll.add_widget(self.library_container)
        self.search_input = TextInput(hint_text="Search commands", multiline=False, size_hint_y=None, height=dp(48))
        self.search_input.bind(text=self._on_search_text)
        self.category_spinner = Spinner(text="All categories", size_hint_y=None, height=dp(48))
        self.category_spinner.bind(text=lambda *_: self._refresh_library_rows())
        self.btn_add_selected = Button(text="Add")
        self.btn_add_selected.bind(on_release=self._add_selected_to_backlog)
        self._search_trigger = Clock.create_trigger(lambda *_: self._refresh_library_rows(), 0.2)

    def _ensure_library_popup(self):
        self._ensure_library_components()
        if self.library_popup is not None:
            return
        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        content.add_widget(Label(text="Command Library", size_hint_y=None, height=dp(32)))
        filters = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None)
        filters.add_widget(self.search_input)
        category_row = BorderedBoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        category_row.add_widget(Label(text="Category", size_hint=(None, 1), width=dp(110)))
        category_row.add_widget(self.category_spinner)
        filters.add_widget(category_row)
        filters.height = self.search_input.height + category_row.height + filters.spacing
        content.add_widget(filters)

        header = BorderedBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(36), spacing=dp(8))
        header_select = Label(text="", size_hint=(None, 1), width=dp(64))
        header_command = Label(text="[b]Command[/b]", markup=True, size_hint=(0.6, 1), halign="left", valign="middle")
        header_value = Label(text="[b]Value[/b]", markup=True, size_hint=(0.4, 1), halign="left", valign="middle")
        for label in (header_command, header_value):
            label.bind(width=lambda inst, _: setattr(inst, "text_size", (inst.width, None)))
        header.add_widget(header_select)
        header.add_widget(header_command)
        header.add_widget(header_value)
        content.add_widget(header)

        content.add_widget(self.library_scroll)
        button_row = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
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
                    height=dp(48),
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
                    height=dp(48),
                    color=(0.7, 0.7, 0.7, 1),
                )
            )

        for identifier, row in self._row_cache.items():
            if identifier not in active_keys and row.parent is not None:
                row.parent.remove_widget(row)

    def _emit_send(self):
        options = {
            "commands": [line.strip() for line in self.backlog_input.text.splitlines() if line.strip()],
            "ips": self.get_staged_ips(),
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

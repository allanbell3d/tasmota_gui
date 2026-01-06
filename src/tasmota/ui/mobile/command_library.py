"""Command library widgets for the mobile UI."""

from __future__ import annotations

from typing import Callable, Dict, Iterable, List, Optional

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from tasmota.core.commands import DEFAULT_COMMANDS, CommandRecord, extract_categories

from .widgets.common import BorderedBoxLayout, bind_auto_wrap
from .widgets.command_row import (
    COMMAND_COL_CHECKBOX_WIDTH,
    COMMAND_COL_COMMAND_HINT,
    COMMAND_COL_VALUE_HINT,
    COMMAND_ROW_SPACING,
    CommandRecycleView,
)


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
        self.library_popup: Optional[Popup] = None
        self.library_records: List[CommandRecord] = []
        self._search_trigger = None
        self._staged_ips: List[str] = []
        self._command_data: List[Dict] = []  # Data for RecycleView

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
        sanitized = [str(ip).strip() for ip in ips if ip and str(ip).strip()]
        unique = sorted(set(sanitized))
        self._staged_ips = unique
        self._refresh_staged_targets()
        return {"staged": len(unique), "total": len(sanitized)}

    def get_staged_ips(self) -> List[str]:
        return list(self._staged_ips)

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
        """Add selected commands to backlog and clear selections."""
        if not hasattr(self, "library_recycle"):
            return
        commands = []
        for item in self.library_recycle.data:
            if item.get("selected"):
                cmd = f"{item.get('name', '')} {item.get('value', '')}".strip()
                if cmd:
                    commands.append(cmd)
                item["selected"] = False  # Clear selection
        if not commands:
            return
        existing = self.backlog_input.text.strip()
        combined = existing.splitlines() if existing else []
        for command in commands:
            if command not in combined:
                combined.append(command)
        self.backlog_input.text = "\n".join(combined)
        # Refresh to show unchecked state
        self.library_recycle.refresh_from_data()

    def _ensure_library_components(self):
        if hasattr(self, "library_recycle") and self.library_recycle is not None:
            return
        self.library_recycle = CommandRecycleView(size_hint=(1, 1))
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

        header = BorderedBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(36),
            spacing=COMMAND_ROW_SPACING,  # Same as rows
        )
        header_select = Label(text="", size_hint=(None, 1), width=COMMAND_COL_CHECKBOX_WIDTH)
        header_command = Label(
            text="[b]Command[/b]",
            markup=True,
            size_hint=(COMMAND_COL_COMMAND_HINT, 1),
            halign="left",
            valign="middle",
        )
        header_value = Label(
            text="[b]Value[/b]",
            markup=True,
            size_hint=(COMMAND_COL_VALUE_HINT, 1),
            halign="left",
            valign="middle",
        )
        for label in (header_command, header_value):
            bind_auto_wrap(label)
        header.add_widget(header_select)
        header.add_widget(header_command)
        header.add_widget(header_value)
        content.add_widget(header)

        content.add_widget(self.library_recycle)
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

        # Extract categories using shared helper
        categories, has_uncategorized = extract_categories(self.library_records)

        values = ["All categories"]
        if has_uncategorized:
            values.append("Uncategorized")
        values.extend(categories)

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

    def _matches_filter(self, record: CommandRecord, search_term: str, category_filter: Optional[str]) -> bool:
        """Check if a record matches the current search and category filters."""
        category_value = (record.category or "").strip()
        if category_filter is not None and category_value != category_filter:
            return False

        if search_term:
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
            if search_term not in haystack:
                return False

        return True

    def _refresh_library_rows(self, *_):
        """Rebuild RecycleView data based on filters."""
        self._ensure_library_components()

        if not self.library_records:
            self.library_recycle.data = []
            return

        search_term = (self.search_input.text or "").strip().lower() if hasattr(self, "search_input") else ""
        category_filter = self._get_selected_category()

        # Build selection map to preserve checkbox state
        selection_map: Dict[str, bool] = {}
        for item in self._command_data:
            key = self._record_identifier_from_data(item)
            selection_map[key] = item.get("selected", False)

        # Build filtered data list
        filtered_data: List[Dict] = []
        for record in self.library_records:
            if not self._matches_filter(record, search_term, category_filter):
                continue

            identifier = self._record_identifier(record)
            filtered_data.append({
                "name": (record.name or "").strip(),
                "category": (record.category or "").strip(),
                "value": (record.value or "").strip(),
                "description": (record.description or "").strip(),
                "selected": selection_map.get(identifier, False),
            })

        # Update RecycleView data
        self._command_data = filtered_data
        self.library_recycle.data = filtered_data

    def _record_identifier_from_data(self, data: Dict) -> str:
        """Generate identifier from data dict (mirrors _record_identifier)."""
        base = (data.get("name") or "").strip().lower()
        value = (data.get("value") or "").strip().lower()
        category = (data.get("category") or "").strip().lower()
        identifier = "::".join(part for part in (base, value, category) if part)
        return identifier or base

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

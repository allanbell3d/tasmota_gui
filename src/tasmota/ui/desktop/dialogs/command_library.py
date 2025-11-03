"""Command library dialog for the desktop UI."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QStyle,
    QStyleOptionButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from tasmota.core.commands import CommandRecord


class CommandLibraryDialog(QDialog):
    COLUMN_CHECK = 0
    COLUMN_CATEGORY = 1
    COLUMN_COMMAND = 2
    COLUMN_VALUE = 3
    COLUMN_DESCRIPTION = 4

    def __init__(self, parent=None, commands=None):
        super().__init__(parent)
        self.setWindowTitle("Command Library")
        self.resize(720, 420)
        self.setSizeGripEnabled(True)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint
        )
        self.selected_commands = []
        self.commands = list(commands or [])

        layout = QVBoxLayout(self)

        filter_row = QHBoxLayout()
        self.command_filter_edit = QLineEdit()
        self.command_filter_edit.setPlaceholderText("Filter command…")
        filter_row.addWidget(self.command_filter_edit)

        self.description_filter_edit = QLineEdit()
        self.description_filter_edit.setPlaceholderText("Filter description…")
        filter_row.addWidget(self.description_filter_edit)

        self.category_filter_combo = QComboBox()
        self.category_filter_combo.setEditable(False)
        self._populate_category_filter()
        filter_row.addWidget(self.category_filter_combo)

        layout.addLayout(filter_row)

        self.table = QTableWidget(len(self.commands), 5)
        self.table.setHorizontalHeaderLabels(["Select", "Category", "Command", "Value", "Description"])
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(self.COLUMN_CHECK, QHeaderView.Fixed)
        header.setSectionResizeMode(self.COLUMN_CATEGORY, QHeaderView.Interactive)
        header.setSectionResizeMode(self.COLUMN_COMMAND, QHeaderView.Interactive)
        header.setSectionResizeMode(self.COLUMN_VALUE, QHeaderView.Interactive)
        header.setSectionResizeMode(self.COLUMN_DESCRIPTION, QHeaderView.Interactive)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked | QAbstractItemView.EditKeyPressed
        )
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        size_adjust_policy_type = type(self.table.sizeAdjustPolicy())
        adjust_ignored = getattr(size_adjust_policy_type, "AdjustIgnored", None)
        if adjust_ignored is None:
            abstract_scroll_area = globals().get("QAbstractScrollArea")
            if abstract_scroll_area is not None:
                adjust_ignored = getattr(abstract_scroll_area, "AdjustIgnored", None)
        if adjust_ignored is not None:
            self.table.setSizeAdjustPolicy(adjust_ignored)

        for row, record in enumerate(self.commands):
            if isinstance(record, CommandRecord):
                command = record.name
                category = record.category
                value = record.value
                description = record.description
            elif isinstance(record, dict):
                command = record.get("name", "")
                category = record.get("category", "")
                value = record.get("value", "")
                description = record.get("description", "")
            else:
                command = category = value = description = ""

            check_item = QTableWidgetItem()
            check_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            check_item.setData(Qt.UserRole, command)
            self.table.setItem(row, self.COLUMN_CHECK, check_item)

            checkbox = QCheckBox()
            checkbox.setTristate(False)
            checkbox.setChecked(False)
            checkbox.setFocusPolicy(Qt.NoFocus)
            checkbox_container = QWidget()
            checkbox_container.setProperty("_checkbox_widget", checkbox)
            checkbox_layout = QHBoxLayout(checkbox_container)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            checkbox_layout.setAlignment(Qt.AlignCenter)
            checkbox_layout.addWidget(checkbox)
            self.table.setCellWidget(row, self.COLUMN_CHECK, checkbox_container)

            command_item = QTableWidgetItem(command)
            command_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            command_item.setToolTip(command)
            self.table.setItem(row, self.COLUMN_COMMAND, command_item)

            category_item = QTableWidgetItem(category)
            category_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            category_item.setToolTip(category)
            category_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, self.COLUMN_CATEGORY, category_item)

            value_item = QTableWidgetItem(value)
            value_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            value_item.setToolTip(value)
            self.table.setItem(row, self.COLUMN_VALUE, value_item)

            description_item = QTableWidgetItem(description)
            description_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            description_item.setToolTip(description)
            self.table.setItem(row, self.COLUMN_DESCRIPTION, description_item)

        header_text_item = self.table.horizontalHeaderItem(self.COLUMN_CHECK)
        text_width = self.table.fontMetrics().horizontalAdvance(
            header_text_item.text() if header_text_item else "Select"
        )
        option = QStyleOptionButton()
        style = self.table.style()
        indicator_width = max(style.pixelMetric(QStyle.PM_IndicatorWidth, option), 0)
        spacing = max(style.pixelMetric(QStyle.PM_CheckBoxLabelSpacing, option), 0)
        frame = max(style.pixelMetric(QStyle.PM_DefaultFrameWidth, option), 0)
        components = [indicator_width, spacing, frame * 2, text_width]
        checkbox_width = sum(value for value in components if value > 0)
        minimum_checkbox_width = max(indicator_width + text_width, 68)
        if checkbox_width <= 0:
            checkbox_width = max(minimum_checkbox_width, 48)
        else:
            checkbox_width = max(checkbox_width, minimum_checkbox_width)
        header.resizeSection(self.COLUMN_CHECK, checkbox_width)
        self.table.setColumnWidth(self.COLUMN_CHECK, checkbox_width)

        self.table.setSortingEnabled(True)
        layout.addWidget(self.table)

        QTimer.singleShot(0, self._update_initial_column_widths)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.btn_insert = QPushButton("Insert")
        self.btn_insert.clicked.connect(self.accept)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_insert)
        btn_row.addWidget(self.btn_cancel)
        layout.addLayout(btn_row)

        self.command_filter_edit.textChanged.connect(lambda _: self.apply_filter())
        self.description_filter_edit.textChanged.connect(lambda _: self.apply_filter())
        self.category_filter_combo.currentIndexChanged.connect(lambda _: self.apply_filter())
        self.table.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.apply_filter()

    def _populate_category_filter(self):
        if not hasattr(self, "category_filter_combo") or self.category_filter_combo is None:
            return

        all_categories = []
        seen = set()
        has_empty = False
        for record in self.commands:
            if isinstance(record, CommandRecord):
                category = (record.category or "").strip()
            elif isinstance(record, dict):
                category = str(record.get("category", "") or "").strip()
            else:
                continue
            if not category:
                has_empty = True
                continue
            key = category.lower()
            if key in seen:
                continue
            seen.add(key)
            all_categories.append(category)

        all_categories.sort(key=lambda value: value.lower())

        self.category_filter_combo.clear()
        self.category_filter_combo.addItem("All categories", None)
        if has_empty:
            self.category_filter_combo.addItem("Uncategorized", "")
        for category in all_categories:
            self.category_filter_combo.addItem(category, category)

    def _checkbox_at_row(self, row):
        widget = self.table.cellWidget(row, self.COLUMN_CHECK)
        if widget is None:
            return None
        checkbox = widget.property("_checkbox_widget")
        if isinstance(checkbox, QCheckBox):
            return checkbox
        return widget.findChild(QCheckBox)

    def _update_initial_column_widths(self):
        if not self.table:
            return

        viewport = self.table.viewport()
        if viewport is None:
            QTimer.singleShot(0, self._update_initial_column_widths)
            return

        viewport_width = viewport.width()
        if viewport_width <= 0:
            QTimer.singleShot(0, self._update_initial_column_widths)
            return

        vertical_scrollbar = self.table.verticalScrollBar()
        if vertical_scrollbar and vertical_scrollbar.isVisible():
            viewport_width -= vertical_scrollbar.width()

        header = self.table.horizontalHeader()
        if header is None:
            QTimer.singleShot(0, self._update_initial_column_widths)
            return

        checkbox_width = max(header.sectionSize(self.COLUMN_CHECK), 68)
        header.resizeSection(self.COLUMN_CHECK, checkbox_width)
        self.table.setColumnWidth(self.COLUMN_CHECK, checkbox_width)

        category_header_item = self.table.horizontalHeaderItem(self.COLUMN_CATEGORY)
        category_label = category_header_item.text() if category_header_item else "Category"
        category_text_width = self.table.fontMetrics().horizontalAdvance(category_label)
        category_min = max(category_text_width + 16, 96)
        category_width = header.sectionSize(self.COLUMN_CATEGORY)
        if category_width <= 0:
            category_width = category_min
        else:
            category_width = max(category_width, category_min)

        header.resizeSection(self.COLUMN_CATEGORY, category_width)
        self.table.setColumnWidth(self.COLUMN_CATEGORY, category_width)

        available_width = viewport_width - (checkbox_width + category_width)
        if available_width <= 0:
            QTimer.singleShot(0, self._update_initial_column_widths)
            return

        command_min = 160
        value_min = 120
        description_min = 280
        command_ratio = 0.25
        value_ratio = 0.20

        command_width = max(int(available_width * command_ratio), command_min)
        value_width = max(int(available_width * value_ratio), value_min)

        description_width = available_width - (command_width + value_width)
        if description_width < description_min:
            description_width = description_min

        total_width = command_width + value_width + description_width
        if total_width > available_width:
            overflow = total_width - available_width
            preferred_description_min = max(description_min, command_width, value_width)
            reducible_description = max(description_width - preferred_description_min, 0)
            reduce = min(reducible_description, overflow)
            description_width -= reduce
            overflow -= reduce

            if overflow > 0:
                reducible_command = max(command_width - command_min, 0)
                reduce = min(reducible_command, overflow)
                command_width -= reduce
                overflow -= reduce

            if overflow > 0:
                reducible_value = max(value_width - value_min, 0)
                reduce = min(reducible_value, overflow)
                value_width -= reduce
                overflow -= reduce

            if overflow > 0:
                description_width = max(description_width - overflow, 0)
                overflow = 0
        elif total_width < available_width:
            description_width += available_width - total_width

        largest_other = max(command_width, value_width)
        desired_description = max(description_min, largest_other + 24)
        if description_width < desired_description:
            deficit = desired_description - description_width
            reductions = 0
            reducible_command = max(command_width - command_min, 0)
            if reductions < deficit and reducible_command > 0:
                take = min(reducible_command, deficit - reductions)
                command_width -= take
                reductions += take
            if reductions < deficit:
                reducible_value = max(value_width - value_min, 0)
                if reducible_value > 0:
                    take = min(reducible_value, deficit - reductions)
                    value_width -= take
                    reductions += take
            description_width += reductions

        command_width = max(command_width, 0)
        value_width = max(value_width, 0)
        description_width = max(description_width, 0)

        total_width = command_width + value_width + description_width
        if total_width > available_width:
            overflow = total_width - available_width
            min_description_allowed = max(description_min, command_width, value_width)
            reducible_description = max(description_width - min_description_allowed, 0)
            reduce = min(reducible_description, overflow)
            description_width -= reduce
            overflow -= reduce
            if overflow > 0:
                reducible_command = max(command_width - command_min, 0)
                reduce = min(reducible_command, overflow)
                command_width -= reduce
                overflow -= reduce
            if overflow > 0:
                reducible_value = max(value_width - value_min, 0)
                reduce = min(reducible_value, overflow)
                value_width -= reduce
                overflow -= reduce
            if overflow > 0:
                description_width = max(description_width - overflow, 0)

        header.resizeSection(self.COLUMN_COMMAND, command_width)
        self.table.setColumnWidth(self.COLUMN_COMMAND, command_width)
        header.resizeSection(self.COLUMN_VALUE, value_width)
        self.table.setColumnWidth(self.COLUMN_VALUE, value_width)
        header.resizeSection(self.COLUMN_DESCRIPTION, description_width)
        self.table.setColumnWidth(self.COLUMN_DESCRIPTION, description_width)

    def apply_filter(self):
        command_query = (self.command_filter_edit.text().strip().lower()
                         if self.command_filter_edit else "")
        description_query = (self.description_filter_edit.text().strip().lower()
                              if self.description_filter_edit else "")
        category_filter = None
        if hasattr(self, "category_filter_combo") and self.category_filter_combo is not None:
            category_filter = self.category_filter_combo.currentData()

        for row in range(self.table.rowCount()):
            command_item = self.table.item(row, self.COLUMN_COMMAND)
            value_item = self.table.item(row, self.COLUMN_VALUE)
            description_item = self.table.item(row, self.COLUMN_DESCRIPTION)
            category_item = self.table.item(row, self.COLUMN_CATEGORY)

            command_text = command_item.text().lower() if command_item else ""
            value_text = value_item.text().lower() if value_item else ""
            description_text = description_item.text().lower() if description_item else ""
            category_text = category_item.text().strip() if category_item else ""

            command_match = True
            if command_query:
                command_match = (command_query in command_text) or (command_query in value_text)

            description_match = True
            if description_query:
                description_match = description_query in description_text

            category_match = True
            if category_filter is not None:
                if category_filter == "":
                    category_match = category_text == ""
                else:
                    category_match = category_text.lower() == str(category_filter).lower()

            self.table.setRowHidden(row, not (command_match and description_match and category_match))

    def on_item_double_clicked(self, item):
        if item is None:
            return

        if item.column() == self.COLUMN_VALUE:
            return
        if item.column() == self.COLUMN_CHECK:
            checkbox = self._checkbox_at_row(item.row())
            if checkbox:
                checkbox.setChecked(not checkbox.isChecked())
            return
        self.accept()

    def accept(self):
        self.selected_commands = []
        seen = set()
        for row in range(self.table.rowCount()):
            checkbox = self._checkbox_at_row(row)
            if not checkbox or not checkbox.isChecked():
                continue

            command_item = self.table.item(row, self.COLUMN_COMMAND)
            value_item = self.table.item(row, self.COLUMN_VALUE)

            command_text = command_item.text().strip() if command_item else ""
            value_text = value_item.text().strip() if value_item else ""

            if not command_text or command_text in seen:
                continue

            seen.add(command_text)
            full_command = f"{command_text} {value_text}".strip()
            if full_command:
                self.selected_commands.append(full_command)

        super().accept()



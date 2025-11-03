"""Selection dialog for the desktop UI."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from tasmota.core.constants import OTA_URLS


class SelectionWindow(QDialog):
    def __init__(self, parent, results, saved_state=None):
        super().__init__(parent)
        self.setWindowTitle("Select Actions")
        self.resize(1000, 600)
        self.results = sorted([r for r in results if r.Ok], key=lambda r: r.Name.lower())
        self.parent = parent
        self.saved_state = saved_state or {}

        v = QVBoxLayout(self)

        # Search / filter row
        fh = QHBoxLayout()
        self.search_box = QLineEdit(); self.search_box.setPlaceholderText("Search Name / IP / MAC...")
        self.chk_selected_only = QCheckBox("Show only selected")
        fh.addWidget(self.search_box); fh.addWidget(self.chk_selected_only)
        v.addLayout(fh)
        self.search_box.textChanged.connect(self.apply_filters)
        self.chk_selected_only.stateChanged.connect(self.apply_filters)

        # Table
        self.table = QTableWidget(len(self.results), 7)
        self.table.setHorizontalHeaderLabels(
            ["Commands","Firmware","Name","Version","Hardware","IP","Mac"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSortingEnabled(True)

        self.populate_table()
        v.addWidget(self.table)

        # Buttons row
        bh = QHBoxLayout()
        self.btn_all_cmd = QPushButton("Toggle All Commands")
        self.btn_all_fw = QPushButton("Toggle All Firmware")
        self.btn_esp8266_cmd = QPushButton("Toggle ESP82xx Commands")
        self.btn_esp8266_fw = QPushButton("Toggle ESP82xx Firmware")
        self.btn_esp32_cmd = QPushButton("Toggle ESP32 Commands")
        self.btn_esp32_fw = QPushButton("Toggle ESP32 Firmware")
        bh.addWidget(self.btn_all_cmd); bh.addWidget(self.btn_all_fw)
        bh.addWidget(self.btn_esp8266_cmd); bh.addWidget(self.btn_esp8266_fw)
        bh.addWidget(self.btn_esp32_cmd); bh.addWidget(self.btn_esp32_fw)
        v.addLayout(bh)

        self.btn_all_cmd.clicked.connect(lambda: self.toggle_rows(range(self.table.rowCount()), 0))
        self.btn_all_fw.clicked.connect(lambda: self.toggle_rows(range(self.table.rowCount()), 1))
        self.btn_esp8266_cmd.clicked.connect(lambda: self.toggle_hw("ESP8266", 0))
        self.btn_esp8266_fw.clicked.connect(lambda: self.toggle_hw("ESP8266", 1))
        self.btn_esp32_cmd.clicked.connect(lambda: self.toggle_hw("ESP32", 0))
        self.btn_esp32_fw.clicked.connect(lambda: self.toggle_hw("ESP32", 1))

        # OTA URL edits (session-only) + Restore Default buttons
        ota_row1 = QHBoxLayout()
        self.txt_esp32 = QLineEdit(self.parent.ota_urls.get("ESP32", OTA_URLS["ESP32"]))
        btn_reset_esp32 = QPushButton("Restore Default")
        btn_reset_esp32.clicked.connect(lambda: self.txt_esp32.setText(OTA_URLS["ESP32"]))
        ota_row1.addWidget(QLabel("ESP32 OTA URL:"))
        ota_row1.addWidget(self.txt_esp32)
        ota_row1.addWidget(btn_reset_esp32)
        v.addLayout(ota_row1)

        ota_row2 = QHBoxLayout()
        self.txt_esp8266 = QLineEdit(self.parent.ota_urls.get("ESP8266", OTA_URLS["ESP8266"]))
        btn_reset_esp8266 = QPushButton("Restore Default")
        btn_reset_esp8266.clicked.connect(lambda: self.txt_esp8266.setText(OTA_URLS["ESP8266"]))
        ota_row2.addWidget(QLabel("ESP82xx OTA URL:"))
        ota_row2.addWidget(self.txt_esp8266)
        ota_row2.addWidget(btn_reset_esp8266)
        v.addLayout(ota_row2)


        # Save & close
        self.btn_save = QPushButton("Save and Close")
        self.btn_save.clicked.connect(self.save_and_close)
        v.addWidget(self.btn_save)

    def populate_table(self):
        sort_was_enabled = self.table.isSortingEnabled()
        header = self.table.horizontalHeader()
        section = header.sortIndicatorSection()
        order = header.sortIndicatorOrder()

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.results))
        for i, r in enumerate(self.results):
            chk_cmd = QCheckBox(); chk_cmd.setStyleSheet("QCheckBox { margin-left:auto; margin-right:auto; }")
            chk_fw  = QCheckBox(); chk_fw.setStyleSheet("QCheckBox { margin-left:auto; margin-right:auto; }")

            if r.IP in self.saved_state:
                chk_cmd.setChecked(self.saved_state[r.IP].get("cmd", False))
                chk_fw.setChecked(self.saved_state[r.IP].get("fw", False))

            self.table.setCellWidget(i,0,chk_cmd)
            self.table.setCellWidget(i,1,chk_fw)
            self.table.setItem(i,2,QTableWidgetItem(r.Name))
            self.table.setItem(i,3,QTableWidgetItem(r.Version))
            self.table.setItem(i,4,QTableWidgetItem(r.Hardware))
            self.table.setItem(i,5,QTableWidgetItem(r.IP))
            self.table.setItem(i,6,QTableWidgetItem(r.Mac))

        self.table.setSortingEnabled(sort_was_enabled)
        if sort_was_enabled and section >= 0:
            self.table.sortItems(section, order)

    def apply_filters(self):
        query = (self.search_box.text() or "").lower()
        selected_only = self.chk_selected_only.isChecked()
        for i in range(self.table.rowCount()):
            match = True
            if query:
                name = self.table.item(i, 2).text().lower() if self.table.item(i, 2) else ""
                ip   = self.table.item(i, 5).text().lower() if self.table.item(i, 5) else ""
                mac  = self.table.item(i, 6).text().lower() if self.table.item(i, 6) else ""
                match = (query in name) or (query in ip) or (query in mac)
            if selected_only:
                c = self.table.cellWidget(i, 0).isChecked()
                f = self.table.cellWidget(i, 1).isChecked()
                match = match and (c or f)
            self.table.setRowHidden(i, not match)

    def toggle_rows(self, indices, col):
        all_checked = True
        for i in indices:
            if not self.table.cellWidget(i, col).isChecked():
                all_checked = False
                break
        new_state = not all_checked
        for i in indices:
            self.table.cellWidget(i, col).setChecked(new_state)

    def toggle_hw(self, key, col):
        indices = []
        for i in range(self.table.rowCount()):
            hw = (self.table.item(i,4).text() or "").upper()
            if key == "ESP32" and "ESP32" in hw:
                indices.append(i)
            if key == "ESP8266" and any(x in hw for x in ["ESP8266","ESP8285","ESP82"]):
                indices.append(i)
        self.toggle_rows(indices, col)

    def get_selection(self):
        cmds, fws, state = [], [], {}
        for i in range(self.table.rowCount()):
            ip = self.table.item(i,5).text() if self.table.item(i,5) else ""
            c = self.table.cellWidget(i,0).isChecked()
            f = self.table.cellWidget(i,1).isChecked()
            state[ip] = {"cmd": c, "fw": f}
            if c: cmds.append(ip)
            if f: fws.append(ip)
        return cmds, fws, state

    def save_and_close(self):
        # Persist OTA URLs back to parent
        self.parent.ota_urls = {
            "ESP32": self.txt_esp32.text().strip() or OTA_URLS["ESP32"],
            "ESP8266": self.txt_esp8266.text().strip() or OTA_URLS["ESP8266"]
        }
        # Save current selections
        cmds, fws, state = self.get_selection()
        self.parent.last_cmds_selected = cmds
        self.parent.last_fw_selected = fws
        self.parent.last_state = state
        self.accept()

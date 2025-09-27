# Changelog

All notable changes to **AllanBell3D Tasmota Bulk Tool (Cross-Platform GUI)** will be documented here.  
This project follows **semantic versioning**:  
- **MAJOR**: Breaking changes  
- **MINOR**: New features, backwards-compatible  
- **PATCH**: Bug fixes, small improvements  

---

## [v0.1.2f] - 2025-09-27
### Added
- Dedicated **Category** Filter field in Command Library GUI.
  
---

## [v0.1.2e] - 2025-09-27
### Added
- Dedicated **Category** column to the command library dialog
- Per-field filters, checkbox-driven selection, and responsive column sizing
- Operators can filter by category before inserting commands

### Changed
- Normalized JSON loader to read command/value/description/category metadata regardless of key casing
- Updated application banner to **v0.1.2e**
- Standardized bundled command dataset to publish `Command`, `Value`, `Description`, and `Category` fields with embedded documentation links that power the GUI library

---

## [v0.1.2d] - 2025-09-27
### Changed
- Refined command library table with scroll-per-pixel behaviour
- Adjusted size policies and smarter column-width heuristics
- Ensured command, value, and description columns remain readable across varied window sizes

---

## [v0.1.2c] - 2025-09-27
### Added
- Linked command library dialog to `tasmota_commands.json`
- JSON error reporting
- Checkbox selection with command/value pairing
- Editable default values
- Dual filters for command names and descriptions before inserting selections

---

## [v0.1.2b] - 2025-09-27
### Added
- Preliminary command library dialog populated from a structured `COMMAND_LIBRARY`
- Text filtering and multi-row selection
- Insertion logic preventing duplicate commands in the backlog editor

---

## [v0.1.2a] - 2025-09-27
### Added
- Command Library button to the main window
- Integrated into backlog editor’s context menu
- Button state kept synced with editor’s enabled status in preparation for forthcoming dialog

---

## [v0.1.1a] - 2025-09-27
### Added
- Initial GitHub commit
- Base GUI using PySide6
- IP scanning, device info collection, Excel/CSV export
- OTA firmware upgrade support (ESP32/ESP8266)
- Backlog command support
- Selection window with toggle buttons

### Fixed
- None (initial release)

---

## [Unreleased]
- Cancel running scan
- More detailed full mode exports
- Commands library

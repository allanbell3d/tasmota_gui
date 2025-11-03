# Changelog

All notable changes to **AllanBell3D Tasmota Bulk Tool (Cross-Platform GUI)** will be documented here.  
This project follows **semantic versioning**:  
- **MAJOR**: Breaking changes  
- **MINOR**: New features, backwards-compatible  
- **PATCH**: Bug fixes, small improvements  

---

## [Unreleased]
### Added
- **Cross-platform Kivy front-end** that mirrors the Compose prototype with tabbed discovery, command backlog, OTA planning, summary, and log views for mobile deployments.  The interface keeps panels scrollable on small displays while wiring them into shared networking routines.
- **Command Library popup** for mobile with search, category filters, multi-select checkboxes, and backlog de-duplication so operators can reuse the same curated JSON dataset across desktop and Android builds.
- **OTA planner workflow** that groups devices by platform, queues upgrades, and feeds backlog commands after firmware flashing, providing queue visibility and post-upgrade automation.
- **Shared core package (`tasmota_core`)** that exposes reusable async discovery, backlog, OTA orchestration, command parsing, and utility helpers so both GUI stacks share consistent behaviour and export handling.
- **Android packaging guide** describing the Buildozer workflow, requirements, and deployment commands for generating APKs directly from the Python sources.
- **Unified entrypoint** that boots the mobile UI when running `python main.py`, matching the Buildozer configuration used for Android builds.

### Changed
- **Bulk executor ergonomics** now expose progress/log callbacks, Lite vs Full discovery modes, command/firmware targeting lists, OTA URL fallbacks, and resilient export handling to support the richer mobile workflows while retaining desktop parity.
- **Result filtering** ensures only successful Tasmota responses populate the mobile summary tables so follow-up actions target valid devices.

---

## [v0.1.4] - 2025-09-27
### Fixed
- Ensured desktop and Kivy worker threads create and close their own asyncio event loops to avoid cross-thread crashes during discovery.

### Changed
- Bumped application version metadata to **v0.1.4** across source files, documentation, and Android packaging config.

---

## [v0.1.3] - 2025-09-27
### Changed
- Bumped application version metadata to **v0.1.3** across source and documentation.

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

# Changelog

All notable changes to **AllanBell3D Tasmota Bulk Tool (Cross-Platform GUI)** will be documented here.  
This project follows **semantic versioning**:  
- **MAJOR**: Breaking changes  
- **MINOR**: New features, backwards-compatible  
- **PATCH**: Bug fixes, small improvements  

---

## [Unreleased]
### Changed
- Command staging now reports partial successes by tracking sanitized versus deduplicated targets in the mobile command library, ensuring duplicate or invalid selections surface warnings.
- OTA target staging uses constant-time lookups for device rows, reducing queue updates on large inventories.

### Removed
- Dead `clear_staged_targets` helper was dropped from the command library panel.

---

## [v0.1.9] - 2025-09-30
### Added
- Scaffolded a `platform/mac/` directory to host future macOS packaging assets alongside the existing Android, Linux, and Windows helpers.

### Changed
- Bumped version metadata to **v0.1.9** across constants, desktop annotations, and Buildozer specs so artefacts report the latest release identifier.
- Refreshed README release notes, verification checklist, and timeline to document the macOS workspace and the new version.

---

## [v0.1.8] - 2025-09-29
### Added
- **Cross-platform Kivy front-end** that mirrors the Compose prototype with tabbed discovery, command backlog, OTA planning, summary, and log views for mobile deployments. The interface keeps panels scrollable on small displays while wiring them into shared networking routines.
- **Command Library popup** for mobile with search, category filters, multi-select checkboxes, and backlog de-duplication so operators can reuse the same curated JSON dataset across desktop and Android builds.
- **OTA planner workflow** that groups devices by platform, queues upgrades, and feeds backlog commands after firmware flashing, providing queue visibility and post-upgrade automation.
- **Shared core package (`tasmota.core`)** that exposes reusable async discovery, backlog, OTA orchestration, command parsing, and utility helpers so both GUI stacks share consistent behaviour and export handling.
- **Android packaging guide** describing the Buildozer workflow, requirements, and deployment commands for generating APKs directly from the Python sources.
- **Unified entrypoint** that boots the mobile UI when running `python -m apps.mobile`, matching the Buildozer configuration used for Android builds.
- **Repository layout** that groups shared code under `src/tasmota`, launchers under `apps/`, platform packaging in `platform/`, and bundled assets in `assets/`.
- Mobile-friendly Kivy front-end that mirrors the desktop layout with tabbed discovery, backlog, OTA planner, summary, and log views optimised for smaller screens.
- Command Library dialog on mobile with search, category filtering, multi-selection, and duplicate prevention so both UIs can reuse the bundled JSON command catalog.
- OTA planning workflow that groups devices by platform, queues firmware flashes, and automatically feeds backlog commands once upgrades complete.
- Shared `tasmota.core` package consolidating async discovery, backlog execution, OTA orchestration, and utility helpers for parity between mobile and desktop.
- Android packaging walkthrough describing the Buildozer workflow for generating signed APKs directly from this repository.
- Unified entry points (`python -m apps.desktop` and `python -m apps.mobile`) and streamlined repository layout that separates shared code, launchers, assets, and platform packaging assets.
- Animated splash overlay that keeps the launch logo visible until the mobile UI is interactive, then fades out smoothly so users never see an unfinished background.
- Logs tab refinements that remove nested scroll containers and auto-resize entries, making swipe navigation and long-line readability consistent on phones.

### Changed
- **Bulk executor ergonomics** now expose progress/log callbacks, Lite vs Full discovery modes, command/firmware targeting lists, OTA URL fallbacks, and resilient export handling to support the richer mobile workflows while retaining desktop parity.
- **Result filtering** ensures only successful Tasmota responses populate the mobile summary tables so follow-up actions target valid devices.
- **Runtime defaults** such as UI titles, output directories, platform-specific thread limits, and shared color palettes now live in `constants` so desktop and mobile builds stay aligned.

### Fixed
- **Splash screen overlay** now fades out only after the mobile UI finishes loading, preventing the logo from disappearing too early and ensuring the background never peeks through during boot.
- **Log panel scrolling** keeps touch interactions predictable by avoiding nested scroll views and resizing rendered log lines to match the viewport.

### Documentation
- Recorded the Android/Windows packaging and run-time debugging steps used to validate v0.1.8 in the README release verification checklist.

---

## [v0.1.6] - 2025-09-28
### Changed
- Lowered the default Android discovery thread count to 20 (clamped to 32) and applied the same ceiling to command/OTA runs so mobile scans no longer overwhelm CPUs.
- Kept non-active tabs interactive during discovery, command, and OTA operations by only disabling the panel running the current task.
- Documented the Android concurrency defaults and bumped version metadata to **v0.1.6** across source, docs, and packaging.

### Fixed
- Prevented conflicting task launches by surfacing clearer warnings when a different scan type is already running.

---

## [v0.1.5] - 2025-09-27
### Fixed
- Ensured desktop and Kivy worker threads create and close their own asyncio event loops to avoid cross-thread crashes during discovery.
- Confirmed device discovery reliability improvements.

### Changed
- Bumped application version metadata to **v0.1.5** across source files, documentation, and Android packaging config.

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

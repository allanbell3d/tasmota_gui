# Changelog

All notable changes to **AllanBell3D Tasmota Bulk Tool (Cross-Platform GUI)** will be documented here.  
This project follows **semantic versioning**:  
- **MAJOR**: Breaking changes  
- **MINOR**: New features, backwards-compatible  
- **PATCH**: Bug fixes, small improvements  

---

## [Unreleased]

---

## [v0.2.2] - 2026-01-06
### Added
- **Comprehensive docstrings** for all core classes and public methods
  - `TasmotaBulkExecutor` with full class documentation and usage examples
  - `DeviceResult` and `BulkRunResult` explaining data structures
  - `CommandRecord` and `CommandLibraryError` with field descriptions
  - All mobile UI widget classes with RecycleView patterns explained
- **`__all__` exports** for `bulk.py`, `commands.py`, and `utils.py` defining public APIs
- **Inline comments** for non-coders in complex methods (`_run_sync`, `RootLayout.__init__`)
- **Phase-based section comments** in bulk executor (PHASE 1: Thread setup, PHASE 2: Execute, PHASE 3: Aggregate)
- **tools/README.md** documenting the Tasmota documentation parsing workflow
- **Naming conventions section** in AGENTS.md covering module, class, and method naming standards

### Changed
- **AGENTS.md completely rewritten** to accurately reflect:
  - Both desktop (PySide6) and mobile (Kivy) implementations
  - Architecture overview with directory structure
  - Clear mapping from agent concepts to actual classes/modules
  - Technology stack summary table
- **Performance optimizations**:
  - `log_panel.py` now uses `deque(maxlen=MAX_LINES)` for automatic overflow handling
  - `summary.py` and `ota.py` cache sorted data to avoid re-sorting on filter changes
  - `command_row.py` caches popup widget instance across all rows
  - `ota.py` filter uses direct field checks instead of string concatenation
  - `ota.py` queue validation uses set intersection (`&=`) operator
- **Redundant list conversion fixed** in `_ensure_list()` - now returns `values.copy()` instead of `list(values)`
- **Exception handlers documented** with explanatory comments in bulk.py

### Removed
- **Redundant entry points** deleted: `main.py`, `main_android.py`, `main_desktop.py`, `main_linux.py`, `main_mac.py`
  - Use `apps/desktop.py` and `apps/mobile.py` instead
- **Unused `List` import** from log_panel.py typing (replaced by Deque)

### Documentation
- **Module docstrings** added to:
  - `bulk.py` - Async network operations and thread management
  - `commands.py` - JSON command library with format examples
  - `utils.py` - Shared utilities and asset resolution
  - `widgets/common.py` - Reusable Kivy UI components
  - `widgets/device_row.py` - RecycleView device rows with data binding
  - `widgets/command_row.py` - Command library row widgets
- **Comments for non-coders** explaining:
  - PyInstaller `_MEIPASS` private attribute for bundled assets
  - Threading patterns and lock usage
  - Progress callback batching rationale
  - RecycleView widget recycling concepts

### Internal
- **.gitignore updated** to exclude `Crap/`, `audit/`, `Logs/`, `venv_kivy/`
- **Constants consolidated** including `LOG_PANEL_MAX_LINES`, `DEVICE_ROW_HEIGHT_DP`, `COMMAND_ROW_HEIGHT_DP`
- **Shared utilities** `device_key()`, `set_checkbox_silent()`, `bind_auto_wrap()` moved to common module
- **`extract_categories()`** moved from UI modules to `commands.py` for reuse

---

## [v0.2.1] - 2026-01-05
### Added
- **Thread-safe cancellation** with proper locking in `bulk.py` preventing race conditions
- **Interruptible OTA wait** - firmware flash waits (120s) now cancellable within 2 seconds
- **IP address validation** for ranges and individual IPs with graceful error handling
- **Input validation UI** showing feedback when invalid IP entries are skipped
- **Cancel Scan/Run buttons** for Windows desktop, matching Android functionality
- **Shared `format_progress()` helper** for consistent progress display across panels
- **Shared `DeviceRowView` base class** for Summary and OTA panels (RecycleView)
- **`CommandRowView` and `CommandRecycleView`** for optimized command library
- **Centralized color constants** in `constants.py` for UI consistency
- **Type hints** added to desktop app public APIs

### Changed
- **RecycleView optimization** for SummaryPanel, OTAPanel, and CommandLibraryPanel - ~10 views recycled vs creating all widgets
- **Log panel reduced** from 1000 to 100 max visible widgets
- **BorderedWidgetMixin trigger debounced** to 50ms (was firing every frame)
- **Progress callbacks batched** to 50ms intervals reducing UI overhead from 300+/sec to ~40/sec
- **ThreadPoolExecutor** now uses context manager for proper cleanup on all exit paths
- **Desktop log buffer pruned** to 1000 entries max preventing memory growth
- **Button naming unified**: "Start Scan" / "Cancel Scan" on both platforms
- **Global error state replaced** with instance variable in desktop app
- Command staging now reports partial successes by tracking sanitized versus deduplicated targets
- OTA target staging uses constant-time lookups for device rows

### Fixed
- **Worker always emits finished signal** preventing UI hang on errors
- **Callbacks wrapped in try/except** preventing silent worker thread death
- **Null checks in desktop selection dialog** preventing crashes on missing widgets
- **Timer cleanup in desktop command library dialog** preventing timer-after-deletion crashes
- **Progress never goes backwards** via thread-safe tracking with locks

### Removed
- **~300 lines of duplicate code** via shared widget components
- **Explicit `texture_update()` calls** that caused performance issues
- Dead `clear_staged_targets` helper from command library panel

### Performance
- Android FPS during scan improved from ~5-10 to 30+ (target)
- Filter response time reduced from 500ms+ to <100ms
- Memory growth now stable instead of unbounded

---

## [v0.1.9] - 2025-10-31
### Added
- Scaffolded a `platform/mac/` directory to host future macOS packaging assets alongside the existing Android, Linux, and Windows helpers.

### Changed
- Bumped version metadata to **v0.1.9** across constants, desktop annotations, and Buildozer specs so artefacts report the latest release identifier.
- Refreshed README release notes, verification checklist, and timeline to document the macOS workspace and the new version.

---

## [v0.1.8] - 2025-10-10
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

## [v0.1.6] - 2025-09-29
### Changed
- Lowered the default Android discovery thread count to 20 (clamped to 32) and applied the same ceiling to command/OTA runs so mobile scans no longer overwhelm CPUs.
- Kept non-active tabs interactive during discovery, command, and OTA operations by only disabling the panel running the current task.
- Documented the Android concurrency defaults and bumped version metadata to **v0.1.6** across source, docs, and packaging.

### Fixed
- Prevented conflicting task launches by surfacing clearer warnings when a different scan type is already running.

---

## [v0.1.5] - 2025-09-28
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

## [v0.1.2e] - 2025-09-24
### Added
- Dedicated **Category** column to the command library dialog
- Per-field filters, checkbox-driven selection, and responsive column sizing
- Operators can filter by category before inserting commands

### Changed
- Normalized JSON loader to read command/value/description/category metadata regardless of key casing
- Updated application banner to **v0.1.2e**
- Standardized bundled command dataset to publish `Command`, `Value`, `Description`, and `Category` fields with embedded documentation links that power the GUI library

---

## [v0.1.2d] - 2025-09-22
### Changed
- Refined command library table with scroll-per-pixel behaviour
- Adjusted size policies and smarter column-width heuristics
- Ensured command, value, and description columns remain readable across varied window sizes

---

## [v0.1.2c] - 2025-09-21
### Added
- Linked command library dialog to `tasmota_commands.json`
- JSON error reporting
- Checkbox selection with command/value pairing
- Editable default values
- Dual filters for command names and descriptions before inserting selections

---

## [v0.1.2b] - 2025-09-19
### Added
- Preliminary command library dialog populated from a structured `COMMAND_LIBRARY`
- Text filtering and multi-row selection
- Insertion logic preventing duplicate commands in the backlog editor

---

## [v0.1.2a] - 2025-09-17
### Added
- Command Library button to the main window
- Integrated into backlog editor’s context menu
- Button state kept synced with editor’s enabled status in preparation for forthcoming dialog

---

## [v0.1.1a] - 2025-09-15
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
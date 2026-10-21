
## Project Overview

The **AllanBell3D Tasmota Bulk Tool** is a cross-platform GUI for discovering, querying, and updating multiple Tasmota devices in parallel across one or more subnets.

The system is modular with functionality organized into logical "agents" - each responsible for a specific slice of functionality. This document maps these conceptual agents to the actual code modules.

---

## Architecture Overview

```
src/tasmota/
├── core/                 # Platform-agnostic business logic
│   ├── bulk.py           # Network Agent + Task Agent + export
│   ├── ota.py            # Firmware Agent: chip -> official image URL
│   ├── settings.py       # Settings Agent: private settings file
│   ├── commands.py       # Command Library Agent
│   └── utils.py          # Shared utilities
├── constants.py          # Configuration constants
└── ui/
    ├── desktop/          # PySide6 (Qt) desktop implementation
    │   ├── app.py        # GUI Agent (desktop)
    │   └── dialogs/      # Modal dialogs
    └── mobile/           # Kivy mobile/touch implementation
        ├── app.py        # GUI Agent (mobile)
        ├── summary.py    # Device list panel
        ├── ota.py        # OTA update panel
        └── widgets/      # Reusable UI components
```

---

## Agents and Their Implementation

### 1. GUI Agent (Desktop)
- **Role:** Primary user interface for desktop environments
- **Technology:** PySide6 (Qt for Python)
- **Implementation:** `src/tasmota/ui/desktop/app.py`
- **Responsibilities:**
  - Render main window with device table, logs, and controls
  - Handle user actions (start OTA update, filter commands, save reports)
  - Provide live feedback with progress bars and status messages
- **Key Classes:**
  - `MainWindow` - Primary application window
  - Custom dialogs in `ui/desktop/dialogs/`

### 2. GUI Agent (Mobile)
- **Role:** Touch-friendly interface for mobile devices and tablets
- **Technology:** Kivy framework
- **Implementation:** `src/tasmota/ui/mobile/app.py`
- **Responsibilities:**
  - Responsive layout adapting to screen size
  - Swipeable tab navigation between panels
  - RecycleView for efficient scrolling of large device lists
- **Key Classes:**
  - `TasmotaKivyApp` - Kivy application entry point
  - `RootLayout` - Main container managing all panels
  - `SummaryPanel` - Device discovery results display
  - `OTAPanel` - Firmware update workflow
  - `CommandLibraryPanel` - Backlog command builder

### 3. Network Agent
- **Role:** Communicates directly with Tasmota devices over HTTP
- **Technology:** httpx (synchronous `httpx.Client`, shared by worker threads)
- **Implementation:** `src/tasmota/core/bulk.py`
- **Responsibilities:**
  - Query devices (`Status 0`, optional `Status 5` / `Template`) via `/cm?cmnd=`
  - Check every reply: HTTP 401, `{"WARNING": ...}` and
    `{"Command":"Unknown"}` count as failures (`CommandResult`)
  - Retry connection failures; retry read failures only for read-only queries
  - Send the web password only to devices that answered with Tasmota's own
    401 reply; never through environment proxies (`trust_env=False`)
- **Key Classes / functions:**
  - `TasmotaBulkExecutor._send_cmd()` - one command, never raises
  - `split_backlog()` - Backlog chunks of at most 30 commands / 1000 bytes
  - `safe_extract_json()` - resilient JSON parsing

### 4. Task Agent
- **Role:** Concurrency controller managing parallel operations
- **Technology:** `ThreadPoolExecutor` (one task per IP); `run_async()` just
  wraps the blocking run in `asyncio.to_thread`
- **Implementation:** `src/tasmota/core/bulk.py`
- **Responsibilities:**
  - Run up to `threads` devices in parallel; cancellation wakes every wait
  - OTA flow: set and confirm OtaUrl -> `Upgrade 1` -> wait -> `Restart 1` ->
    poll until the final image runs (minimal/safeboot are skipped) -> compare
    versions -> restore the official OtaUrl
  - Record the outcome per device in `DeviceResult.Action`
- **Key Classes:**
  - `TasmotaBulkExecutor` - Main executor class
  - Progress and log callbacks (called from worker threads)

### 5. Firmware Agent
- **Role:** Choose the right official image for each chip
- **Implementation:** `src/tasmota/core/ota.py`
- **Responsibilities:**
  - Map `StatusFWR.Hardware` to a family and variant (`ESP8685` = C3,
    `ESP32-S0WD` = solo1, ...)
  - Turn a configured `.../tasmota32.bin` into `.../tasmota32<variant>.bin`
    in the same folder
  - Refuse bare/unknown ESP32 packages, chips without an official image,
    specialty builds (from the image name in `Version`), single-core
    mismatches and URLs meant for the other chip family

### 6. Settings Agent
- **Role:** Remember personal values outside the source code
- **Implementation:** `src/tasmota/core/settings.py`
- **Responsibilities:**
  - Load/save `UserSettings` as JSON in `.private/` (source), next to the
    `.exe` (packaged) or the Android data folder
  - Atomic writes, keep unknown keys, move corrupt files aside, never
    overwrite a file that could not be read

### 7. Data Agent
- **Role:** Reporting and data export
- **Technology:** pandas + openpyxl (optional; skipped if missing)
- **Implementation:** `TasmotaBulkExecutor._run_sync()` in `core/bulk.py`
  (desktop passes an output folder; mobile does not export)
- **Responsibilities:**
  - Export responding devices to Excel (`.xlsx`) and CSV, with an `Action`
    column when a run sent commands or firmware
  - Write to an `_alt` file if the target is locked (open in Excel)
- **Key Classes:**
  - `DeviceResult` - Individual device scan result
  - `BulkRunResult` - Aggregated operation results

### 8. Command Library Agent
- **Role:** Repository of reusable Tasmota commands
- **Technology:** JSON file + Python dataclasses
- **Implementation:** `src/tasmota/core/commands.py`
- **Responsibilities:**
  - Load commands from `assets/commands/tasmota_commands.json`
  - Support flexible JSON field naming for extensibility
  - Provide category filtering and search
- **Key Classes:**
  - `CommandRecord` - Single command entry
  - `load_command_library()` - JSON file loader
  - `extract_categories()` - Category grouping utility

---

## Agent Interactions

1. **User Input -> GUI Agent**
   The user triggers an action (e.g., "Scan Network" or "Send OTA Update").

2. **GUI Agent -> Task Agent**
   The GUI translates the action into a batch of async tasks via `TasmotaBulkExecutor`.

3. **Task Agent -> Network Agent**
   Each task queries or updates one device using HTTP requests.

4. **Network Agent -> Data Agent**
   Responses are parsed into `DeviceResult` objects and aggregated.

5. **Data Agent -> GUI Agent**
   Results are displayed back to the user (device tables, logs, or exported files).

6. **Command Library Agent**
   Supports the workflow by providing prepared commands for the Task Agent pipeline.

---

## Naming Conventions

### Module Naming
- **Core modules:** Lowercase with underscores (`bulk.py`, `commands.py`)
- **UI panels:** Simple lowercase names (`summary.py`, `ota.py`, `discovery.py`)
- **Widget modules:** Descriptive lowercase (`device_row.py`, `command_row.py`)

### Class Naming
- **Desktop dialogs:** Suffix with `Dialog` (e.g., `CommandLibraryDialog`)
- **Mobile panels:** Suffix with `Panel` (e.g., `SummaryPanel`, `OTAPanel`)
- **RecycleView rows:** Suffix with `RowView` (e.g., `DeviceRowView`, `CommandRowView`)
- **Mixins:** Suffix with `Mixin` (e.g., `BorderedWidgetMixin`)

### Method Naming
- **Public API:** Standard Python naming (`set_results`, `clear_queue`)
- **Private/internal:** Prefix with underscore (`_rebuild_display`, `_emit_progress`)
- **Kivy callbacks:** Match Kivy conventions (`on_release`, `on_text`)

### Constants
- **Module-level:** SCREAMING_SNAKE_CASE (`DEFAULT_THREADS`, `OTA_URLS`)
- **UI constants:** Grouped by purpose with comments

---

## Example Workflow: OTA Update

1. User selects devices in Summary panel -> clicks **Queue Firmware Updates**
2. **GUI Agent** adds devices to OTA panel queue
3. User configures firmware URLs -> clicks **Run OTA Updates**
4. **Task Agent** launches parallel OTA commands via **Network Agent**
5. **Firmware Agent** picks the image for each chip; the device must echo the
   new OtaUrl before `Upgrade 1` is sent
6. After `OTA_RESTART_WAIT_SECONDS`, **Task Agent** polls until the final image
   runs, compares versions and restores the official OtaUrl
7. Results (including `Action`) aggregated by **Data Agent** and displayed in GUI

---

## Technology Stack Summary

| Component | Desktop | Mobile |
|-----------|---------|--------|
| GUI Framework | PySide6 (Qt) | Kivy |
| HTTP Client | httpx | httpx |
| Concurrency | ThreadPoolExecutor in a QThread | ThreadPoolExecutor in a thread |
| Data Export | pandas | (none) |
| Settings | `.private/` or next to the `.exe` | Android data folder |
| Entry Point | `apps/desktop.py` | `main.py` -> `apps/mobile.py` |

## Testing

`tests/` runs without any GUI toolkit. `tests/conftest.py` provides a fake
Tasmota network on top of `httpx.MockTransport` (the executor accepts a
`transport=`). CI (`.github/workflows/ci.yml`) runs `ruff check .` and
`pytest` on Python 3.10 and 3.12.

---

## Future Agents (Planned)

- **Scheduler Agent** - Cron-like job runner for scheduled updates
- **MQTT Agent** - Subscribe to MQTT topics for live monitoring
- **Backup Agent** - Export/import Tasmota configuration

---

## Glossary

- **Agent**: A modular unit responsible for one slice of functionality
- **OTA**: Over-The-Air firmware update
- **Retry/Backoff**: Network resilience strategy for unreliable devices
- **RecycleView**: Kivy widget for efficient scrolling of large lists
- **Backlog**: Tasmota command that chains multiple commands together

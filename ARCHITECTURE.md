
## Project Overview

The **AllanBell3D Tasmota Bulk Tool** is a cross-platform GUI for discovering, querying, and updating multiple Tasmota devices in parallel across one or more subnets.

The system is modular with functionality organized into logical "agents" - each responsible for a specific slice of functionality. This document maps these conceptual agents to the actual code modules.

---

## Architecture Overview

```
src/tasmota/
├── core/                 # Platform-agnostic business logic
│   ├── bulk.py           # Network Agent + Task Agent
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
- **Technology:** httpx (async HTTP client)
- **Implementation:** `src/tasmota/core/bulk.py`
- **Responsibilities:**
  - Query devices for status (`Status 0` command)
  - Dispatch OTA commands with retry/backoff logic
  - Parse JSON responses, handling malformed HTML wrappers
- **Key Classes:**
  - `TasmotaBulkExecutor._fetch()` - Single device HTTP request
  - Uses `safe_extract_json()` for resilient JSON parsing

### 4. Task Agent
- **Role:** Concurrency controller managing parallel operations
- **Technology:** Python asyncio + ThreadPoolExecutor
- **Implementation:** `src/tasmota/core/bulk.py`
- **Responsibilities:**
  - Launch up to `DEFAULT_THREADS` parallel tasks
  - Enforce retry/backoff policy for flaky devices
  - Coordinate multi-step flows (OTA -> wait -> restart)
- **Key Classes:**
  - `TasmotaBulkExecutor` - Main executor class
  - Uses `ThreadPoolExecutor` for CPU-bound work
  - Progress tracking via callbacks

### 5. Data Agent
- **Role:** Reporting and data export
- **Technology:** pandas
- **Implementation:** Export logic in `ui/desktop/app.py`
- **Responsibilities:**
  - Export results to Excel (`.xlsx`) and CSV formats
  - Only include successfully discovered devices
  - Provide structured logs for debugging or audits
- **Key Classes:**
  - `DeviceResult` - Individual device scan result
  - `BulkRunResult` - Aggregated operation results

### 6. Command Library Agent
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
5. Devices receive OTA command -> begin firmware download
6. After `OTA_RESTART_WAIT_SECONDS`, **Task Agent** polls for device recovery
7. Results aggregated by **Data Agent** and displayed in GUI

---

## Technology Stack Summary

| Component | Desktop | Mobile |
|-----------|---------|--------|
| GUI Framework | PySide6 (Qt) | Kivy |
| HTTP Client | httpx | httpx |
| Async Runtime | asyncio | asyncio |
| Data Export | pandas | pandas |
| Entry Point | `apps/desktop.py` | `apps/mobile.py` |

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

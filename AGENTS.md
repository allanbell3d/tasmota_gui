# AGENTS.md

## 📌 Project Overview
The **AllanBell3D Tasmota Bulk Tool (Cross-Platform GUI)** is designed to **discover, query, and update multiple Tasmota devices in parallel** across one or more subnets.  

The system is modular, and its functionality can be described in terms of **agents**. Each “agent” has a clear role, technology stack, and set of responsibilities. Together, they form a distributed workflow managed by the user interface.

---

## 🧩 Agents

### 1. **GUI Agent**
- **Role:** The face of the tool — provides all user interactions.
- **Technology:** PySide6 (Qt for Python).
- **Responsibilities:**
  - Render the main window with device table, logs, and controls.
  - Handle user actions (start OTA update, filter commands, save reports).
  - Provide live feedback with progress bars and status messages.
- **Notes:**  
  - Supports horizontal/vertical layouts with dynamic resizing.  
  - Includes custom dialogs for command selection and filtering.  

---

### 2. **Network Agent**
- **Role:** Talks directly to Tasmota devices.
- **Technology:** httpx (async HTTP client).
- **Responsibilities:**
  - Query devices for status (`Status 0` command).
  - Dispatch OTA commands with retry/backoff logic.
  - Parse JSON responses, even if wrapped in stray HTML or malformed.
- **Notes:**  
  - Resilient to transient network errors.  
  - Configurable timeout (`DEFAULT_TIMEOUT`) and retries.  

---

### 3. **Task Agent**
- **Role:** Concurrency controller.
- **Technology:** Python asyncio.
- **Responsibilities:**
  - Launch up to `DEFAULT_THREADS` parallel tasks.
  - Enforce retry/backoff policy for flaky devices.
  - Coordinate multi-step flows (OTA → wait → restart).
- **Notes:**  
  - Ensures the GUI stays responsive while tasks run.  
  - Supports future expansion into scheduled or chained jobs.  

---

### 4. **Data Agent**
- **Role:** Reporting and persistence.
- **Technology:** pandas.
- **Responsibilities:**
  - Export results into `tasmota_hardware_summary.xlsx` and `.csv`.
  - Only include devices successfully discovered (no empty IPs).
  - Provide structured logs for debugging or audits.
- **Notes:**  
  - Excel output includes only active devices.  
  - CSV output enables downstream integration (automation, dashboards).  

---

### 5. **Command Library Agent**
- **Role:** Repository of reusable Tasmota commands.
- **Technology:** Integrated into PySide6 (QTableWidget + QCheckBox).
- **Responsibilities:**
  - Display commands with filters (by name or description).
  - Allow multi-select of commands to apply in bulk.
  - Manage command/value/description triplets.
- **Notes:**  
  - Column widths adapt dynamically via QTimer for consistent layout.  
  - Uses checkboxes for clarity instead of QTableWidgetItem state.  

---

## 🔄 Agent Interactions

1. **User Input → GUI Agent**  
   The operator triggers an action (e.g., “Send OTA Update”).

2. **GUI Agent → Task Agent**  
   The GUI translates the action into a batch of async tasks.

3. **Task Agent → Network Agent**  
   Each task queries or updates one device using the network layer.

4. **Network Agent → Data Agent**  
   Responses are parsed and passed into structured pandas DataFrames.

5. **Data Agent → GUI Agent**  
   Results are displayed back to the user (logs, tables, or exported files).

6. **Command Library Agent**  
   Acts as a support role: it feeds prepared commands into the Task Agent pipeline.

---

## 📊 Example Workflow: OTA Update

1. User selects devices → clicks **OTA Update**.  
2. **GUI Agent** instructs **Task Agent** to launch jobs.  
3. Each job sends an OTA command via the **Network Agent**.  
4. Devices respond with status → parsed by Network → logged.  
5. After retries/timeouts, results aggregated by **Data Agent**.  
6. Final state displayed in GUI and exported to Excel/CSV.  

---

## 🚀 Future Agents (Planned)

- **Scheduler Agent**  
  - Cron-like job runner for scheduled updates (nightly/weekly).  
- **MQTT Agent**  
  - Subscribe to MQTT topics for live monitoring.  
- **Discovery Agent**  
  - Continuous subnet scanning with adaptive filters.  
- **Backup Agent**  
  - Export/import Tasmota configuration for disaster recovery.  

---

## 📖 Glossary

- **Agent**: A modular unit responsible for one slice of functionality.  
- **OTA**: Over-The-Air firmware update.  
- **Retry/Backoff**: Network resilience strategy for flaky devices.  
- **QTableWidget**: Qt widget for tabular GUI representation.  
- **pandas**: Python library for structured data handling.  

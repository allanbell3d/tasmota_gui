# Tasmota Bulk Tool (Cross-Platform GUI)

Cross-platform **PySide6 GUI tool** to manage Tasmota devices in bulk on LAN.

---

## Features
- Scan IP ranges for devices  
- Collect device info (**Lite** and **Full** modes)  
- Export results to **Excel/CSV**  
- Bulk send backlog commands  
- OTA firmware upgrade for **ESP82xx** and **ESP32**  
- GUI selection with filters and toggles  

---

## Versioning
- **Current:** `v0.1.1a (beta)`  
- **Roadmap:** Command library for easy configuration  

---

## Usage
```bash
python tasmota_gui.py
```

---

## Agents Overview (Detailed)

This project â€” **AllanBell3D Tasmota Bulk Tool (Cross-Platform GUI)** â€” manages bulk operations on Tasmota devices.  
It uses a modular architecture where each **agent** has a clear role.

### GUI Agent
Provides the user interface (PySide6). Displays devices, logs, and progress bars.

### Task Agent
Manages concurrency (asyncio). Launches parallel OTA updates and retries.

### Network Agent
Handles HTTP communication (httpx). Queries devices and sends commands.

### Data Agent
Exports results (pandas). Generates Excel/CSV reports for discovered devices.

### Command Library Agent
Stores reusable Tasmota commands. Provides filtering and selection in the GUI.

---

## Workflow

1. **GUI Agent** captures user actions.  
2. **Task Agent** spawns async jobs.  
3. **Network Agent** queries devices.  
4. **Data Agent** logs/export results.  
5. **Command Library Agent** provides reusable commands.  

---

## Agents Overview (Summary)

This project â€” **AllanBell3D Tasmota Bulk Tool (Cross-Platform GUI)** â€” manages bulk operations on Tasmota devices.  
It uses a modular architecture where each **agent** has a clear role.

### Agents

- GUI Agent  
  Provides the user interface (PySide6). Displays devices, logs, and progress bars.

- Task Agent  
  Manages concurrency (asyncio). Launches parallel OTA updates and retries.

- Network Agent  
  Handles HTTP communication (httpx). Queries devices and sends commands.

- Data Agent  
  Exports results (pandas). Generates Excel/CSV reports for discovered devices.

- Command Library Agent  
  Stores reusable Tasmota commands. Provides filtering and selection in the GUI.

### Workflow

1. GUI Agent captures user actions.  
2. Task Agent spawns async jobs.  
3. Network Agent queries devices.  
4. Data Agent logs/export results.  
5. Command Library Agent provides reusable commands.  

---

For detailed documentation, see [AGENTS.md](AGENTS.md).


- 2025-09-27 0.1.2a: Added Command Library Button
- 2025-09-27 0.1.2b: Added Preliminary Command Library
- 2025-09-27 0.1.2c: Linked Command Library To JSON database. Added selection fields, filtering by command name and description. 
- 2025-09-27 0.1.2d: Improved Commands Library window layout and added horizonal scroll bar.
- 2025-09-27 : Added Category column to Command Library in order to facilitate filtering and loaded values from JSON command database

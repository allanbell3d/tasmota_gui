# Tasmota Bulk Tool (Cross-Platform GUI)

The **AllanBell3D Tasmota Bulk Tool** provides a unified desktop (PySide6) and
mobile (Kivy) experience for discovering, configuring, and updating Tasmota
hardware at scale. It shares a common asynchronous core so automations, logging,
and command handling behave identically regardless of platform.

---

## Current Release
- **Version:** v0.2.2
- **Release date:** 2026-01-06
- **Headline updates:**
  - **Comprehensive documentation** with docstrings for all core classes and methods.
  - **Performance optimizations** using sorted data caching and deque for log buffers.
  - **Popup widget caching** in command library for faster response times.
  - **`__all__` exports** defining public APIs for core modules.
  - **Redundant entry points removed** - use `apps/desktop.py` and `apps/mobile.py`.
  - **tools/README.md** documenting the Tasmota command parsing workflow.

See the [CHANGELOG](CHANGELOG.md) for a full list of historical changes.

---

## Features at a Glance
- Scan IPv4 ranges (lite or full) with progress feedback.
- Collect, filter, and export device metadata to Excel or CSV.
- Manage a backlog of reusable Tasmota commands, including library lookups.
- Schedule OTA firmware flashes for ESP8266 and ESP32 devices with queue
  visibility.
- Cross-platform desktop and mobile interfaces backed by the same async engine.
- Configurable runtime defaults (thread limits, timeouts, output directory,
  branding) via `constants`.

---

## Quick Start
```bash
# Desktop (PySide6)
python -m apps.desktop

# Mobile / Kivy preview
python -m apps.mobile
```

The platform-specific packaging helpers now live under `platform/`:

```text
platform/
  android/   # Buildozer spec + docs for APK generation
  windows/   # PyInstaller scripts/specs
  linux/     # AppImage/Debian packaging notes
  mac/       # Reserved for future macOS packaging workflows
```

Shared source is organised beneath `src/tasmota/` while thin launchers live in
`apps/`:

```text
src/
  tasmota/
    core/      # network + command helpers shared across GUIs
    ui/
      desktop/ # PySide6 widgets and dialogs
      mobile/  # Kivy layouts and views
apps/
  desktop.py   # desktop launcher
  mobile.py    # mobile launcher
assets/
  commands/    # bundled command library JSON
```

---

## Architecture Agents

The project adopts an agent-oriented architecture with clear responsibilities:

- **GUI Agent** – Drives the PySide6 and Kivy interfaces, handling user input,
  state display, and task orchestration signals.
- **Task Agent** – Coordinates asynchronous discovery, backlog execution, and
  OTA operations while enforcing concurrency limits.
- **Network Agent** – Performs HTTP communication with Tasmota devices via
  `httpx`, parsing responses for downstream consumers.
- **Data Agent** – Aggregates scan results and exports Excel/CSV summaries using
  `pandas`.
- **Command Library Agent** – Provides filtered access to the bundled JSON
  command catalog across both UI stacks.

---

## Release Verification Checklist

To ship v0.2.1 we walked through the following end-to-end debugging steps. Run
them again before cutting a future release to make sure the desktop and mobile
experiences stay in sync:

1. **Android (Buildozer)**
   - `cd platform/android`
   - `buildozer -v android release`
   - Install the generated APK on a physical Android 13 handset and confirm the
     discovery, backlog, and OTA planner tabs populate data while logs stream to
     `tasmota.log`.
2. **Windows (PyInstaller)**
   - `cd platform/windows`
   - `pyinstaller --clean tasmota-desktop.spec`
   - Launch the packaged `TasmotaBulkTool.exe`, run a lite discovery against a
     local subnet, enqueue backlog commands, and verify log output in the
     bundled console window.
3. **Shared core sanity checks**
   - From the repository root run `python -m apps.desktop` and
     `python -m apps.mobile`
   - Ensure both entry points can import `tasmota.core`, render the tabbed UI,
     and complete a mock OTA planning session without raising exceptions.
4. **macOS packaging placeholder**
   - Confirm the `platform/mac/` directory is present to host forthcoming
     packaging scripts. (No build steps yet.)

---

## Release Timeline
- **2026-01-06 – v0.2.2**: Comprehensive documentation and code quality refactor.
  Added docstrings for all core classes, `__all__` exports, performance
  optimizations (sorted data caching, deque log buffers, popup caching),
  rewrote AGENTS.md for accuracy, removed redundant entry points.
- **2026-01-05 – v0.2.1**: Major performance and stability refactor completing
  all P0/P1/P2 audit items. RecycleView optimization for all panels, thread
  safety fixes, Cancel Scan for Windows, batched UI callbacks, shared widget
  components, and centralized color constants.
- **2025-09-30 – v0.1.9**: Reserved macOS packaging workspace, refreshed the
  release documentation, and aligned all metadata with the new version number.
- **2025-09-29 – v0.1.8**: Introduced the mobile Kivy interface, OTA planner,
  command library parity, shared core package, repository reorganisation,
  Android packaging guidance, an animated splash overlay that waits for the UI
  to be ready, and log panel refinements for smoother scrolling.
- **2025-09-28 – v0.1.6**: Tuned Android discovery thread defaults, kept inactive
  tabs responsive during long-running tasks, and documented concurrency tweaks.
- **2025-09-27 – v0.1.5**: Stabilised discovery workers and normalised version
  metadata across the project.
- **2025-09-27 – v0.1.3**: Bumped application metadata to 0.1.3.
- **2025-09-27 – v0.1.2a–f**: Iterated on the command library dialog with
  category filtering, selection ergonomics, and JSON-backed content.
- **2025-09-27 – v0.1.1a**: Initial public release with PySide6 GUI, backlog
  commands, OTA flashing, and export capabilities.

---

For deeper architectural notes see `AGENTS.md` (if present) or inline module
Docstrings within `src/tasmota/`.

# Tasmota Bulk Tool (Cross-Platform GUI)

The **AllanBell3D Tasmota Bulk Tool** discovers, configures and OTA-updates
Tasmota devices in bulk. A desktop UI (PySide6) and a mobile UI (Kivy) share
one core, so discovery, commands and firmware updates behave the same on both.

---

## Current Release
- **Version:** v0.3.0
- **Release date:** 2026-10-21
- **Headline updates:**
  - **Correct firmware for every chip.** ESP32-C2/C3/C5/C6/C61/S2/S3 and
    single-core ESP32 now get their own official image (`tasmota32c3.bin`,
    `tasmota32solo1.bin`, ...). Chips that can't be identified safely, and
    devices running a specialty build (sensors, ir, bluetooth, ...), are
    skipped rather than guessed.
  - **Updates are verified.** OtaUrl and Upgrade replies are checked, the
    firmware version is compared before and after, and the outcome of every
    device appears in the log and in the new `Action` column of the export.
  - **Web password support.** The password is sent only to devices that ask
    for it with Tasmota's own 401 reply, never to other hosts in the range.
  - **Your settings are remembered.** IP ranges, backlog commands, password and
    options are kept in a private, git-ignored settings file (see below).
  - **Safer selection.** "Toggle Visible ..." buttons only affect rows shown by
    the current filter.

See the [CHANGELOG](CHANGELOG.md) for the full list.

---

## Features at a Glance
- Scan IPv4 ranges (lite or full info) with progress and cancel.
- Filter devices and export metadata to Excel and CSV (desktop).
- Send backlog commands, chunked so Tasmota accepts them in order.
- OTA-update ESP8266 and ESP32-family devices, optionally pinned to a release
  folder for one run. Afterwards the device's OtaUrl is reset to the official
  release URL for its chip.
- Optional web password (Tasmota `WebPassword`).
- Desktop and mobile UIs backed by the same core.

---

## Quick Start
```bash
pip install -e ".[desktop,dev]"   # or: pip install -r requirements.txt PySide6

# Desktop (PySide6)
python -m apps.desktop            # python apps/desktop.py also works

# Mobile / Kivy preview
pip install kivy
python -m apps.mobile

# Tests and lint (no GUI toolkit needed)
pytest -q
ruff check .
```

---

## Personal Settings (`.private/`)

Values that belong to your installation are not in the source code. Each app
loads them on start and saves them when a run starts and when it closes:
IP ranges, backlog commands, threads/timeout/retries, info mode, output
folder and web password. Firmware URLs are deliberately *not* saved, so a URL
pinned for one run never sticks.

| Running as | Settings file |
|------------|---------------|
| Source checkout | `<repo>/.private/tasmota_settings.json` |
| Packaged `.exe` | `.private/tasmota_settings.json` next to the `.exe` (fallback: `%APPDATA%\TasmotaBulkTool\`) |
| Android | the app's private data folder (kept across app updates) |
| Override | set `TASMOTA_GUI_SETTINGS_DIR` |

- `.private/` is in `.gitignore`. The file is plain JSON. Unknown keys such as
  `_command_notes` are kept when the app saves.
- **Moving from v0.2.x:** older versions hard-coded these values in
  `src/tasmota/constants.py`. Run this once, *before* rewriting or deleting the
  git history, to copy them into `.private/`:
  ```bash
  python tools/migrate_settings_from_git.py
  ```
- A Windows build bundles `.private/tasmota_settings.json` as the first-run
  default if it exists at build time. That makes the `.exe` contain your
  commands (including MQTT credentials) and password, so don't share such a
  build.

---

## Repository Layout
```text
src/tasmota/
  constants.py   # neutral defaults, limits, URLs, colours
  core/          # bulk.py (executor), ota.py (chip -> firmware), settings.py, commands.py, utils.py
  ui/desktop/    # PySide6 window, worker, dialogs
  ui/mobile/     # Kivy panels and widgets
apps/            # desktop.py / mobile.py launchers
main.py          # Android entry point (python-for-android needs main.py)
assets/          # command library JSON, logo, Tasmota reference docs
tests/           # pytest suite (fake Tasmota devices via httpx.MockTransport)
tools/           # docs fetch/parse, JSON compare, settings migration
platform/        # packaging notes; platform/windows/tasmota-desktop.spec
buildozer.spec   # Android build (run buildozer from the repo root)
```

Architecture notes: [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Building

**Windows (PyInstaller):** the spec works from any directory.
```bash
pyinstaller --clean platform/windows/tasmota-desktop.spec
```
Output: `dist/TasmotaBulkGUI.exe`.

**Android (Buildozer):** from the repository root:
```bash
buildozer -v android debug      # or: android release
```
See [platform/android/README.md](platform/android/README.md).

---

## Release Verification Checklist

Run before cutting a release:

1. `ruff check .` and `pytest -q` (CI runs both on every push).
2. **Desktop:** `python -m apps.desktop`. Scan a subnet, open the selection
   window, filter, toggle, run commands on one device, and check the log and
   the export.
3. **Windows build:** build with the spec above, start the `.exe`, and confirm
   that settings load and that they are saved next to the `.exe`.
4. **Android:** `buildozer -v android debug`, install on a phone, run a
   discovery, a command run and an OTA on a test device.
5. **OTA on real hardware:** update at least one ESP8266 and one ESP32 (a
   variant chip if you have one), then check that the version changed and that
   OtaUrl points back to the official release.

---

## Release Timeline
- **2026-10-21 – v0.3.0**: Variant-aware, verified OTA; web password; private
  settings; selection and result-merge fixes; packaging fixes; tests and CI.
- **2026-01-06 – v0.2.2**: Documentation and code quality refactor.
- **2026-01-05 – v0.2.1**: Performance and stability refactor (RecycleView,
  thread safety, Cancel Scan on Windows).
- **2025-09-30 – v0.1.9**: Reserved macOS packaging workspace.
- **2025-09-29 – v0.1.8**: Mobile Kivy interface, OTA planner, shared core.
- **2025-09-28 – v0.1.6**: Android discovery thread defaults.
- **2025-09-27 – v0.1.1a–v0.1.5**: Initial releases and command library.

# Android Packaging with Buildozer

This project ships a Kivy entrypoint (`apps/mobile.py`), started on Android through the root `main.py` (python-for-android requires a `main.py` at the app root).  The Android package is generated with **Buildozer** so everything runs from the existing Python sources and the shared networking modules.

## Prerequisites

1. **Linux host** (or WSL2) with at least 8 GB RAM.
2. Python 3.10+ and `pip`.
3. Java JDK 11 and Android SDK/NDK installed automatically by Buildozer (no Android Studio required).
4. System packages for compilation (Ubuntu/Debian example):
   ```bash
   sudo apt-get update
   sudo apt-get install -y build-essential git zip unzip libssl-dev libffi-dev python3 python3-pip
   ```
5. Install Buildozer in a virtual environment:
   ```bash
   python3 -m venv .buildozer-venv
   source .buildozer-venv/bin/activate
   pip install --upgrade pip
   pip install buildozer==1.5.0
   ```

## Project Layout

* `apps/mobile.py` – Kivy UI entrypoint used by the Android build.
* `src/tasmota/core/` – shared discovery, command, and networking logic used by both the PySide6 and Kivy front-ends.
* `buildozer.spec` (repository root) – the only Buildozer configuration. `tests/`, `tools/`, `platform/` and `assets/reference/` are excluded from the APK.
* `main.py` (repository root) – Android entry point that loads `apps/mobile.py`.

## First-Time Build

1. Activate the Buildozer virtualenv (if not already active):
   ```bash
   source .buildozer-venv/bin/activate
   ```
2. From the project root run:
   ```bash
   buildozer android debug
   ```
   The first build downloads the Android SDK/NDK and all Python wheels, so it can take several minutes.
3. The resulting debug APK is located in `bin/` (e.g., `bin/tasmotabulk-0.3.0-debug.apk`).

## Install on a Device or Emulator

With an Android device attached via USB (and USB debugging enabled) or an emulator running:

```bash
buildozer android deploy run
```

Buildozer automatically installs the APK and starts the application.  Use the following for log output:

```bash
buildozer android logcat
```

## Updating the Build Configuration

* Modify Python dependencies inside `buildozer.spec` → `requirements`.
* Update the application version or package name in the `[app]` section.
* To perform a release build, run `buildozer android release` and sign the resulting AAB/APK as required.

## Settings on Android

Buildozer skips hidden folders, so `.private/` is never packaged. The app keeps
its settings (IP ranges, commands, web password, options) in its private
data folder (`App.user_data_dir`), which survives app updates. Enter your values once
per device; they are saved when a run starts and when the app is paused or
closed.

## Runtime defaults on Android

* Discovery now defaults to **20 worker threads** on Android (clamped to a maximum of 32) via the shared `constants.ANDROID_THREAD_DEFAULT` and `ANDROID_THREAD_MAX` values, reducing CPU contention on phones and tablets.
* Command and OTA runs reuse the same Android-specific limits so scans stay responsive while you browse other tabs.

## Troubleshooting

* **Missing dependencies** – Run `buildozer android clean` to clear the build cache and rebuild.
* **Gradle errors** – Delete the `.buildozer` directory and retry to force a clean toolchain download.
* **Large APK size** – Remove unused Python modules from `requirements` or enable [Python module blacklist](https://buildozer.readthedocs.io/en/latest/specifications.html#p4a-blacklist-requirements).

The Buildozer workflow replaces the previous Android Studio instructions and keeps the mobile build aligned with the shared Python networking stack.

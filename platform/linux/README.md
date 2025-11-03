# Linux Packaging

This folder collects notes and helper scripts for building Linux packages of the Tasmota desktop UI.

## AppImage (planned)

* Use [`appimage-builder`](https://appimage-builder.readthedocs.io/) to package `apps/desktop.py` into a standalone bundle.
* Ship desktop entry metadata under `platform/linux/appimage/` (to be added).

## Debian Package (planned)

* Generate binaries with PyInstaller using the shared `platform/windows/tasmota-desktop.spec` as a reference.
* Create `debian/` packaging metadata (control file, service scripts) that installs launchers under `/opt/tasmota-bulk`.

These placeholders ensure future platform work lands in a predictable location alongside the Android and Windows build assets.

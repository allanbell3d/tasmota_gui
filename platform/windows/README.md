# Windows Packaging

This directory hosts helper assets for producing Windows builds of the desktop GUI.

* `build_release_json_embeded.ps1` – convenience script that reads the project version from `src/tasmota/core/constants.py` and runs PyInstaller against `apps/desktop.py`.
* `tasmota-desktop.spec` – baseline PyInstaller spec file that bundles the desktop launcher and command library JSON.

Run the PowerShell script from a developer prompt with Python and PyInstaller available to generate a standalone `.exe` in the `releases/` folder.

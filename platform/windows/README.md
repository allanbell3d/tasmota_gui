# Windows Packaging

* `tasmota-desktop.spec` – PyInstaller spec for the desktop launcher. Every
  path is anchored to the repository root, so it builds from any directory:
  ```bash
  pyinstaller --clean platform/windows/tasmota-desktop.spec
  ```
  The result is `dist/TasmotaBulkGUI.exe`. It bundles the command library
  JSON and the logo. If `.private/tasmota_settings.json` exists at build time,
  it is bundled as the first-run default: such an `.exe` contains your
  commands (including MQTT credentials) and web password, so don't share it.
* Settings changed in the packaged app are saved to `.private/` next to the
  `.exe`, or to `%APPDATA%\TasmotaBulkTool\` if that folder is not writable.
* Local helper scripts such as `build_release_json_embeded.ps1` are
  git-ignored (`*.ps1`) and are not part of the repository.

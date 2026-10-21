# Build from the repository root:  buildozer -v android debug   (or: release)
#
# python-for-android starts the app from main.py at the root, which loads
# apps/mobile.py. Buildozer skips hidden folders, so .private/ is never
# packaged: on the phone, settings are kept in the app's private data folder
# and survive app updates (enter your values once per device).
[app]
title = Tasmota Bulk Tool
package.name = tasmotabulk
package.domain = com.allanbell3d
source.dir = .
source.include_exts = py,png,jpg,json,kv
source.exclude_dirs = tests,tools,platform,assets/reference,Logs,build,dist
# logo.png is the full-quality source; the app and splash use logo.jpg.
source.exclude_patterns = assets/images/logo.png
version = 0.3.0
# pandas/numpy/openpyxl are only used for the desktop Excel/CSV export; the
# mobile app never exports (out_dir=None), so they are not packaged.
requirements = python3,kivy,httpx,httpcore,anyio,certifi,idna,charset-normalizer,sniffio,h11
orientation = portrait
fullscreen = 0
android.permissions = INTERNET
android.add_assets = assets:assets
presplash.filename = assets/images/logo.jpg
presplash.keep_aspect = 0

[buildozer]
log_level = 2
warn_on_root = 1

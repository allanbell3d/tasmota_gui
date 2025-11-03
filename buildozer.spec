[app]
title = Tasmota Bulk Tool
package.name = tasmotabulk
package.domain = com.allanbell3d
source.dir = .
source.main = apps/mobile.py
source.include_exts = py,png,jpg,json,kv
version = 0.1.9
requirements = python3,kivy,httpx,httpcore,anyio,certifi,idna,charset-normalizer,sniffio,pandas,numpy,python-dateutil,pytz,openpyxl,et-xmlfile,h11
orientation = portrait
fullscreen = 0
android.permissions = INTERNET
android.add_assets = assets:assets
presplash.filename = assets/images/logo.png
presplash.keep_aspect = 0

[buildozer]
log_level = 2
warn_on_root = 1

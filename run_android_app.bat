@echo off
cd /d D:\IA\Claude\Tasmota_GUI
echo Starting Tasmota GUI (Mobile/Android)...
venv_kivy\Scripts\python.exe -m apps.mobile
pause

@echo off
REM ===========================================
REM Apply codex.diff to a chosen file (no commit/push)
REM ===========================================

cd /d "%~dp0"

if not exist codex.diff (
    echo ❌ codex.diff not found in this directory.
    pause
    exit /b 1
)

REM Ask user for the target file
set /p DEST_FILE=Enter the destination file to patch (e.g. tasmota_gui.py): 

if not exist "%DEST_FILE%" (
    echo ❌ The file "%DEST_FILE%" does not exist in this directory.
    pause
    exit /b 1
)

echo.
echo Applying codex.diff to %DEST_FILE%...

REM Attempt to apply patch with 3-way merge
git apply --3way --ignore-whitespace codex.diff

IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo ❌ 3-way patch failed, trying fallback with --reject...
    git apply --reject --ignore-whitespace codex.diff
)

echo.
echo ✅ Patch operation finished. Please review any .rej files if created.
pause

# ============================
# AllanBell3D Tasmota Bulk Tool Release Builder
# ============================

# Allow an override of the project root when invoking the script, otherwise
# resolve it automatically based on the script location. `$PSScriptRoot` will
# point at `platform\windows`, so the repository root is two levels up.
param(
    [string]$ProjectRoot
)

if (-not $ProjectRoot) {
    if ($PSScriptRoot) {
        $candidate = Join-Path $PSScriptRoot "..\.."
        if (Test-Path $candidate) {
            $ProjectRoot = (Resolve-Path $candidate).Path
        }
    }

    if (-not $ProjectRoot) {
        Write-Host "❌ Unable to determine project root. Pass -ProjectRoot explicitly."
        Pause
        exit 1
    }
}

$ConstantsFile = Join-Path $ProjectRoot "constants.py"

# Read APP_VERSION
if (Test-Path $ConstantsFile) {
    $content = Get-Content $ConstantsFile
    $versionLine = $content | Where-Object { $_ -match 'APP_VERSION\s*=\s*".+"' }
    if ($versionLine) {
        $APP_VERSION = ($versionLine -split '=')[1].Trim().Trim('"')
        Write-Host "✅ Found APP_VERSION in constants.py: $APP_VERSION"
    }
    else {
        Write-Host "❌ APP_VERSION not found in $ConstantsFile"
        Pause
        exit 1
    }
}
else {
    Write-Host "❌ constants.py not found at $ConstantsFile"
    Pause
    exit 1
}

Write-Host "🔨 Starting release build for version $APP_VERSION..."

# Release folder
$ReleaseFolder = Join-Path $ProjectRoot "releases"
if (-not (Test-Path $ReleaseFolder)) {
    New-Item -ItemType Directory -Path $ReleaseFolder | Out-Null
}

# === REAL BUILD STEP ===
# adjust entry point if needed
$EntryScript = Join-Path $ProjectRoot "apps\desktop.py"
$OutputName = "TasmotaBulkGUI_$APP_VERSION"
$SrcPath = Join-Path $ProjectRoot "src"
$CommandLibrary = Join-Path $ProjectRoot "assets\commands\tasmota_commands.json"

if (-not (Test-Path $CommandLibrary)) {
    Write-Host "❌ Command library JSON not found at $CommandLibrary"
    Pause
    exit 1
}

# Clean old build/dist
if (Test-Path "$ProjectRoot\build") { Remove-Item -Recurse -Force "$ProjectRoot\build" }
if (Test-Path "$ProjectRoot\dist") { Remove-Item -Recurse -Force "$ProjectRoot\dist" }

# Run pyinstaller
python -m PyInstaller --onefile --noconsole `
    --name $OutputName `
    --distpath $ReleaseFolder `
    --paths $SrcPath `
    --add-data "$CommandLibrary;assets/commands" `
    $EntryScript

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ PyInstaller failed with exit code $LASTEXITCODE."
    Pause
    exit $LASTEXITCODE
}

Write-Host "✅ Build finished. Executable created: $ReleaseFolder\$OutputName.exe"
Pause

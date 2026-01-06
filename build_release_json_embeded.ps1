# ============================
# AllanBell3D Tasmota Bulk Tool Release Builder
# ============================

[CmdletBinding()]
param(
    [string]$ProjectRoot
)

$ErrorActionPreference = "Stop"

function Stop-WithMessage {
    param([string]$Message)
    Write-Host "❌ $Message" -ForegroundColor Red
    Pause
    exit 1
}

if (-not $ProjectRoot) {
    if ($PSScriptRoot) {
        $ProjectRoot = $PSScriptRoot
    } elseif ($MyInvocation.MyCommand.Path) {
        $ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
    } else {
        $ProjectRoot = Get-Location
    }
}

try {
    $ProjectRoot = (Resolve-Path $ProjectRoot).Path
} catch {
    Stop-WithMessage "Unable to resolve project root: $ProjectRoot"
}

Write-Host "🔍 Using project root: $ProjectRoot"

$ConstantsFile   = Join-Path $ProjectRoot "src\tastmota\constants.py"
$EntryScript     = Join-Path $ProjectRoot "apps\desktop.py"
$SourcePath      = Join-Path $ProjectRoot "src"
$CommandLibrary  = Join-Path $ProjectRoot "assets\commands\tasmota_commands.json"
$ReleaseFolder   = Join-Path $ProjectRoot "releases"
$BuildFolder     = Join-Path $ProjectRoot "build"
$DistFolder      = Join-Path $ProjectRoot "dist"

if (-not (Test-Path $ConstantsFile)) {
    Stop-WithMessage "constants.py not found at $ConstantsFile"
}

if (-not (Test-Path $EntryScript)) {
    Stop-WithMessage "Desktop entry script not found at $EntryScript"
}

if (-not (Test-Path $CommandLibrary)) {
    Stop-WithMessage "Command library JSON not found at $CommandLibrary"
}

$versionMatch = Select-String -Path $ConstantsFile -Pattern 'APP_VERSION\s*=\s*"([^"]+)"'
if (-not $versionMatch) {
    Stop-WithMessage "APP_VERSION not found in $ConstantsFile"
}

$AppVersion = $versionMatch.Matches[0].Groups[1].Value
$CleanVersion = $AppVersion.TrimStart('v','V')
$OutputName = "TasmotaBulkGUI_v$CleanVersion"

Write-Host "🔨 Building release for version $AppVersion"

if (-not (Test-Path $ReleaseFolder)) {
    New-Item -ItemType Directory -Path $ReleaseFolder | Out-Null
}

if (Test-Path $BuildFolder) { Remove-Item -Recurse -Force $BuildFolder }
if (Test-Path $DistFolder) { Remove-Item -Recurse -Force $DistFolder }

$PyInstallerArgs = @(
    "--onefile",
    "--noconsole",
    "--noconfirm",
    "--name", $OutputName,
    "--distpath", $ReleaseFolder,
    "--workpath", $BuildFolder,
    "--specpath", $BuildFolder,
    "--paths", $SourcePath,
    "--add-data", "$CommandLibrary;assets/commands",
    $EntryScript
)

Write-Host "⚙️ Running PyInstaller..."
python -m PyInstaller @PyInstallerArgs

if ($LASTEXITCODE -ne 0) {
    Stop-WithMessage "PyInstaller failed with exit code $LASTEXITCODE"
}

$ExpectedExe = Join-Path $ReleaseFolder "$OutputName.exe"
if (-not (Test-Path $ExpectedExe)) {
    Stop-WithMessage "Expected executable not found at $ExpectedExe"
}

Write-Host "✅ Build finished. Executable created: $ExpectedExe"
Pause

# ===========================================
# Commit and Push Script (PowerShell version)
# ===========================================

Set-Location -Path $PSScriptRoot

# Extract current version from tasmota_gui.py
$CurrentVersion = (Select-String -Path "tasmota_gui.py" -Pattern '^APP_VERSION').Line.Split('=')[1].Trim().Trim('"')
Write-Host "Current version in tasmota_gui.py: $CurrentVersion"
Write-Host ""

# Ask user which file(s) to commit
$DestFile = Read-Host "Enter the file(s) to commit (e.g. tasmota_gui.py or . for all changes)"
if ($DestFile -eq ".") {
    git add -A
} else {
    git add $DestFile
}

# Ask for commit message
$CommitMsg = Read-Host "Enter commit message"

# Ask if user wants to create a tag
$TagChoice = Read-Host "Do you want to create a tag? (y/n)"

if ($TagChoice -ieq "y") {
    $TagName = Read-Host "Enter tag name (suggested: v$CurrentVersion)"
    if ([string]::IsNullOrWhiteSpace($TagName)) {
        $VersionForLog = $CurrentVersion
    } else {
        $VersionForLog = $TagName

        # ✅ Update version inside tasmota_gui.py (both comment and APP_VERSION)
        (Get-Content tasmota_gui.py) `
            -replace '# Version .*', "# Version $TagName" `
            -replace 'APP_VERSION\s*=\s*".*"', "APP_VERSION      = `"$TagName`"" |
            Set-Content tasmota_gui.py
        git add tasmota_gui.py

        # ✅ Update **Current:** line in README.md
        Write-Host "✅ Updating README.md with new version info..."
        (Get-Content README.md) -replace '(\*\*Current:\*\*).*', ("**Current:** `$TagName`  ") | Set-Content README.md
        git add README.md
    }
} else {
    $VersionForLog = $CurrentVersion
}

# Append commit log to README.md
$Date = Get-Date -Format 'yyyy-MM-dd'
Add-Content README.md ("- $Date ${VersionForLog}: $CommitMsg")
git add README.md

# Commit
git commit -m "$CommitMsg"
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Commit aborted or failed."
    Pause
    exit $LASTEXITCODE
}

# Tag if chosen
if ($TagChoice -ieq "y" -and -not [string]::IsNullOrWhiteSpace($TagName)) {
    Write-Host "✅ Creating tag $TagName..."
    git tag -a $TagName -m "$CommitMsg"
    git push origin $TagName
}

# Push main branch
Write-Host "✅ Pushing commit to origin/main..."
git push origin main

if ($LASTEXITCODE -eq 0) {
    if ($TagChoice -ieq "y" -and -not [string]::IsNullOrWhiteSpace($TagName)) {
        Write-Host "✅ Push + Tag + tasmota_gui.py + README update successful!"
    } else {
        Write-Host "✅ Push successful (commit log appended to README.md)"
    }
} else {
    Write-Host "❌ Push failed, check your Git remote or network."
}

Pause

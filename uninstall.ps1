<#
.SYNOPSIS
    Uninstalls the Google Ads API Developer Assistant extension and removes the project directory.
#>

$ErrorActionPreference = "Stop"

# Determine project root
try {
    $ProjectDirAbs = git rev-parse --show-toplevel 2>$null
    if (-not $ProjectDirAbs) { throw "Not in a git repo" }
    $ProjectDirAbs = (Get-Item -LiteralPath $ProjectDirAbs).FullName
}
catch {
    Write-Error "ERROR: This script must be run from within the google-ads-api-developer-assistant git repository."
    exit 1
}

Write-Host "This will uninstall the Google Ads API Developer Assistant extension"
Write-Host "and DELETE the entire directory: $ProjectDirAbs"
$Confirm = Read-Host "Are you sure you want to proceed? (Y/n)"

if ($Confirm -notmatch "^[Yy]$") {
    Write-Host "Uninstallation cancelled."
    exit 0
}

if (Get-Command gemini -ErrorAction SilentlyContinue) {
    Write-Host "Uninstalling Gemini extension..."
    try {
        & gemini extensions uninstall "google-ads-api-developer-assistant" 2>&1 | Out-Null
    }
    catch {
        Write-Warning "Extension was not registered or failed to uninstall. Continuing..."
    }
}
else {
    Write-Warning "'gemini' command not found. Skipping extension uninstallation."
}

Write-Host "Removing project directory: $ProjectDirAbs..."
# Move out of the directory to allow deletion
Set-Location (Split-Path $ProjectDirAbs)
Remove-Item -Recurse -Force -LiteralPath $ProjectDirAbs

Write-Host "Uninstallation complete."

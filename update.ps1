<#
.SYNOPSIS
    Updates the Google Ads API Developer Assistant and its dependencies on Windows.

.DESCRIPTION
    This script performs the following steps:
    1. Updates the 'google-ads-api-developer-assistant' repository (git pull).
    2. Reads '.gemini/settings.json' to locate configured client library repositories.
    3. Updates each found client library repository (git pull).

.EXAMPLE
    .\update.ps1
#>

$ErrorActionPreference = "Stop"

# --- Dependency Check ---
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error "ERROR: git is not installed. Please install it to continue."
    exit 1
}

# --- Project Directory Resolution ---
try {
    $ProjectDirAbs = git rev-parse --show-toplevel 2>$null
    if (-not $ProjectDirAbs) { throw "Not in a git repo" }
    $ProjectDirAbs = (Get-Item -LiteralPath $ProjectDirAbs).FullName
}
catch {
    Write-Error "ERROR: This script must be run from within the google-ads-api-developer-assistant git repository."
    exit 1
}

Write-Host "Detected project root: $ProjectDirAbs"

# --- Update Assistant Repo ---
Write-Host "Updating google-ads-api-developer-assistant..."
try {
    git pull
    if ($LASTEXITCODE -ne 0) {
        Write-Error "ERROR: Failed to update google-ads-api-developer-assistant."
        exit 1
    }
    Write-Host "Successfully updated google-ads-api-developer-assistant."
}
catch {
    Write-Error "ERROR: Failed to update google-ads-api-developer-assistant: $_"
    exit 1
}

# --- Locate and Update Client Libraries ---
$SettingsFile = Join-Path $ProjectDirAbs ".gemini\settings.json"

if (-not (Test-Path -LiteralPath $SettingsFile)) {
    Write-Error "ERROR: Settings file not found: $SettingsFile"
    Write-Error "Please run setup.ps1 first."
    exit 1
}

Write-Host "Reading $SettingsFile to find client libraries..."

try {
    $SettingsJson = Get-Content -LiteralPath $SettingsFile -Raw | ConvertFrom-Json
    
    if (-not $SettingsJson.context -or -not $SettingsJson.context.includeDirectories) {
        Write-Warning "No directories found in settings."
        exit 0
    }

    $IncludeDirs = $SettingsJson.context.includeDirectories
    Write-Host "Found $($IncludeDirs.Count) directories in settings."

    foreach ($LibPath in $IncludeDirs) {
        if ([string]::IsNullOrWhiteSpace($LibPath)) { continue }
        
        # Check if path exists
        if (-not (Test-Path -LiteralPath $LibPath)) {
            Write-Warning "Directory not found: $LibPath. Skipping."
            continue
        }

        $AbsLibPath = (Get-Item -LiteralPath $LibPath).FullName

        # Skip if it is the project directory itself or a subdirectory of it
        if ($AbsLibPath.StartsWith($ProjectDirAbs)) {
            Write-Host "Skipping internal directory: $AbsLibPath"
            continue
        }

        # Check if it is a git repository
        if (-not (Test-Path -LiteralPath (Join-Path $AbsLibPath ".git"))) {
            Write-Warning "Skipping non-git directory: $AbsLibPath"
            continue
        }

        Write-Host "Updating repository at: $AbsLibPath..."
        Push-Location $AbsLibPath
        try {
            git pull
            if ($LASTEXITCODE -eq 0) {
                 Write-Host "Successfully updated $AbsLibPath."
            } else {
                 Write-Error "ERROR: Failed to update $AbsLibPath"
                 # We exit on error to match update.sh behavior of failing fast-ish? 
                 # Actually update.sh likely fails fast due to set -e.
                 exit 1 
            }
        }
        finally {
            Pop-Location
        }
    }
}
catch {
    Write-Error "ERROR: An error occurred while processing settings or updating libraries: $_"
    exit 1
}

Write-Host "Update complete."

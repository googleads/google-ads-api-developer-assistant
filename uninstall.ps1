<#
.SYNOPSIS
    Uninstalls the Google Ads API Developer Assistant project or plugin.

.DESCRIPTION
    This script removes either the standalone project repository or the installed plugin.

.PARAMETER Type
    Required. Uninstallation type: 'project' or 'plugin'.

.PARAMETER Force
    Skip confirmation prompts.

.PARAMETER Yes
    Skip confirmation prompts (synonym for Force).

.EXAMPLE
    .\uninstall.ps1 -Type project
    Uninstalls and deletes the project directory.

.EXAMPLE
    .\uninstall.ps1 -Type plugin
    Uninstalls and deletes the installed plugin directory.
#>

param(
    [Parameter(Mandatory=$true, Position=0, HelpMessage="Uninstallation type: 'project' or 'plugin'")]
    [ValidateSet("project", "plugin", IgnoreCase=$true)]
    [string]$Type,

    [switch]$Force,
    [switch]$Yes
)

$ErrorActionPreference = "Stop"

$AutoConfirm = $Force -or $Yes

# --- Plugin Uninstallation Branch ---
if ($Type.ToLower() -eq "plugin") {
    $GeminiPluginsDir = if ($env:USERPROFILE) {
        Join-Path $env:USERPROFILE ".gemini\config\plugins"
    } else {
        Join-Path $HOME ".gemini\config\plugins"
    }
    $TargetPluginDir = Join-Path $GeminiPluginsDir "google_ads_assistant_plugin"

    if (-not (Test-Path -LiteralPath $TargetPluginDir)) {
        Write-Host "Plugin directory '$TargetPluginDir' does not exist. Nothing to uninstall."
        exit 0
    }

    Write-Host "This will uninstall the Google Ads API Developer Assistant plugin"
    Write-Host "and DELETE the directory: $TargetPluginDir"

    if (-not $AutoConfirm) {
        $Confirm = Read-Host "Are you sure you want to proceed? (Y/n)"
        if ($Confirm -notmatch "^[Yy]$") {
            Write-Host "Uninstallation cancelled."
            exit 0
        }
    }

    Write-Host "Removing plugin directory: $TargetPluginDir..."
    Remove-Item -Recurse -Force -LiteralPath $TargetPluginDir
    Write-Host "Plugin uninstallation complete."
    exit 0
}

# --- Project Uninstallation Branch ---
try {
    $ProjectDirAbs = git rev-parse --show-toplevel 2>$null
    if (-not $ProjectDirAbs) { throw "Not in a git repo" }
    $ProjectDirAbs = (Get-Item -LiteralPath $ProjectDirAbs).FullName
}
catch {
    Write-Error "ERROR: This script must be run from within the google-ads-api-developer-assistant git repository."
    exit 1
}

Write-Host "This will uninstall the Google Ads API Developer Assistant project"
Write-Host "and DELETE the entire directory: $ProjectDirAbs"

if (-not $AutoConfirm) {
    $Confirm = Read-Host "Are you sure you want to proceed? (Y/n)"
    if ($Confirm -notmatch "^[Yy]$") {
        Write-Host "Uninstallation cancelled."
        exit 0
    }
}

Write-Host "Removing project directory: $ProjectDirAbs..."
# Move out of the directory to allow deletion
Set-Location (Split-Path $ProjectDirAbs)
Remove-Item -Recurse -Force -LiteralPath $ProjectDirAbs

Write-Host "Project uninstallation complete."

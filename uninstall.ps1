<#
.SYNOPSIS
    Uninstalls the Google Ads API Developer Assistant project or plugin.

.DESCRIPTION
    This script removes either the standalone project repository, the installed plugin,
    or specific client libraries from either environment.

.PARAMETER Type
    Required. Uninstallation type: 'project' or 'plugin'.

.PARAMETER Python
    Remove only the google-ads-python client library.

.PARAMETER Php
    Remove only the google-ads-php client library.

.PARAMETER Ruby
    Remove only the google-ads-ruby client library.

.PARAMETER Java
    Remove only the google-ads-java client library.

.PARAMETER Dotnet
    Remove only the google-ads-dotnet client library.

.PARAMETER Force
    Skip confirmation prompts.

.PARAMETER Yes
    Skip confirmation prompts (synonym for Force).

.EXAMPLE
    .\uninstall.ps1 -Type project
    Uninstalls and deletes the entire project directory.

.EXAMPLE
    .\uninstall.ps1 -Type project -Java
    Removes only the Java library from the project.

.EXAMPLE
    .\uninstall.ps1 -Type plugin
    Uninstalls and deletes the entire installed plugin directory.

.EXAMPLE
    .\uninstall.ps1 -Type plugin -Java
    Removes only the Java library from the plugin.
#>

param(
    [Parameter(Mandatory=$true, Position=0, HelpMessage="Uninstallation type: 'project' or 'plugin'")]
    [ValidateSet("project", "plugin", IgnoreCase=$true)]
    [string]$Type,

    [switch]$Python,
    [switch]$Php,
    [switch]$Ruby,
    [switch]$Java,
    [switch]$Dotnet,
    [switch]$Force,
    [switch]$Yes
)

function Get-RepoName {
    param($Lang)
    switch ($Lang) {
        "python" { return "google-ads-python" }
        "php"    { return "google-ads-php" }
        "ruby"   { return "google-ads-ruby" }
        "java"   { return "google-ads-java" }
        "dotnet" { return "google-ads-dotnet" }
    }
}

$ErrorActionPreference = "Stop"

$AutoConfirm = $Force -or $Yes

$SpecifiedLangs = @()
if ($Python) { $SpecifiedLangs += "python" }
if ($Php)    { $SpecifiedLangs += "php" }
if ($Ruby)   { $SpecifiedLangs += "ruby" }
if ($Java)   { $SpecifiedLangs += "java" }
if ($Dotnet) { $SpecifiedLangs += "dotnet" }

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

    # If specific client libraries are selected
    if ($SpecifiedLangs.Count -gt 0) {
        $PluginClientLibs = Join-Path $TargetPluginDir "client_libs"
        foreach ($Lang in $SpecifiedLangs) {
            $RepoName = Get-RepoName $Lang
            $LibPath = Join-Path $PluginClientLibs $RepoName
            if (Test-Path -LiteralPath $LibPath) {
                Write-Host "Removing $RepoName from $PluginClientLibs..."
                Remove-Item -Recurse -Force -LiteralPath $LibPath
                Write-Host "Successfully removed $RepoName."
            } else {
                Write-Host "Library $RepoName not found in $PluginClientLibs."
            }
        }
        Write-Host "Plugin client library removal complete."
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

# If specific client libraries are selected
if ($SpecifiedLangs.Count -gt 0) {
    $DefaultParentDir = Join-Path $ProjectDirAbs "client_libs"
    foreach ($Lang in $SpecifiedLangs) {
        $RepoName = Get-RepoName $Lang
        $LibPath = Join-Path $DefaultParentDir $RepoName
        if (Test-Path -LiteralPath $LibPath) {
            Write-Host "Removing $RepoName from $DefaultParentDir..."
            Remove-Item -Recurse -Force -LiteralPath $LibPath
            Write-Host "Successfully removed $RepoName."
        } else {
            Write-Host "Library $RepoName not found in $DefaultParentDir."
        }
    }
    Write-Host "Project client library removal complete."
    exit 0
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

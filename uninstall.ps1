<#
.SYNOPSIS
    Uninstalls the Google Ads API Developer Assistant plugin.

.DESCRIPTION
    This script uninstalls the Google Ads API Developer Assistant plugin from ~/.gemini/config/plugins/
    or removes specific client libraries from it.

.PARAMETER All
    Remove all client libraries from plugin client_libs/.

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
    .\uninstall.ps1
    Uninstalls and deletes the entire plugin directory.

.EXAMPLE
    .\uninstall.ps1 -Force
    Uninstalls the plugin without confirmation prompts.

.EXAMPLE
    .\uninstall.ps1 -All
    Removes all client libraries from the plugin.

.EXAMPLE
    .\uninstall.ps1 -Java
    Removes only the Java library from the plugin.
#>

param(
    [switch]$All,
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
if ($All) {
    $SpecifiedLangs = @("python", "php", "ruby", "java", "dotnet")
} else {
    if ($Python) { $SpecifiedLangs += "python" }
    if ($Php)    { $SpecifiedLangs += "php" }
    if ($Ruby)   { $SpecifiedLangs += "ruby" }
    if ($Java)   { $SpecifiedLangs += "java" }
    if ($Dotnet) { $SpecifiedLangs += "dotnet" }
}

$UserHome = if ($env:USERPROFILE) { $env:USERPROFILE } else { $HOME }
$GeminiPluginsDir = Join-Path $UserHome ".gemini\config\plugins"
$TargetPluginDir = Join-Path $GeminiPluginsDir "google-ads-api-developer-assistant"
$LegacyPluginDir = Join-Path $GeminiPluginsDir "google_ads_assistant_plugin"

if ((-not (Test-Path -LiteralPath $TargetPluginDir)) -and (-not (Test-Path -LiteralPath $LegacyPluginDir))) {
    Write-Host "Plugin directory '$TargetPluginDir' does not exist. Nothing to uninstall."
    exit 0
}

# If specific client libraries are selected
if ($SpecifiedLangs.Count -gt 0) {
    $PluginDirs = @($TargetPluginDir, $LegacyPluginDir)
    foreach ($PDir in $PluginDirs) {
        $PluginClientLibs = Join-Path $PDir "client_libs"
        if (Test-Path -LiteralPath $PluginClientLibs) {
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
        }
    }
    Write-Host "Plugin client library removal complete."
    Write-Host ""
    Write-Host "Restart your Antigravity / agy host to apply changes."
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

if (Test-Path -LiteralPath $TargetPluginDir) {
    Write-Host "Removing plugin directory: $TargetPluginDir..."
    Remove-Item -Recurse -Force -LiteralPath $TargetPluginDir
}

if (Test-Path -LiteralPath $LegacyPluginDir) {
    Remove-Item -Recurse -Force -LiteralPath $LegacyPluginDir
}

Write-Host "Plugin uninstallation complete."
Write-Host ""
Write-Host "Restart your Antigravity / agy host to complete plugin uninstallation."

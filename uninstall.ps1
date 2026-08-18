<#
.SYNOPSIS
    Uninstalls the Google Ads API Developer Assistant plugin.

.DESCRIPTION
    This script uninstalls the Google Ads API Developer Assistant plugin from Antigravity (agy)
    or Claude Code (claudecode), or removes specific client libraries from it.

.PARAMETER Target
    Required. Target platform: 'agy' (Antigravity) or 'claudecode' (Claude Code).

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
    .\uninstall.ps1 -Target agy
    Uninstalls and deletes the entire Antigravity plugin directory.

.EXAMPLE
    .\uninstall.ps1 -Target claudecode -Force
    Uninstalls the Claude Code plugin without confirmation prompts.

.EXAMPLE
    .\uninstall.ps1 -Target agy -All
    Removes all client libraries from the Antigravity plugin.

.EXAMPLE
    .\uninstall.ps1 -Target claudecode -Java
    Removes only the Java library from the Claude Code plugin.
#>

param(
    [Parameter(Mandatory=$true, Position=0, HelpMessage="Target platform: 'agy' or 'claudecode'")]
    [ValidateSet("agy", "claudecode", IgnoreCase=$true)]
    [string]$Target,

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

function Get-PluginTargetDir {
    param([string]$TargetPlatform)

    $UserHome = if ($env:USERPROFILE) { $env:USERPROFILE } else { $HOME }

    switch ($TargetPlatform.ToLower()) {
        "agy" {
            return (Join-Path $UserHome ".gemini\config\plugins\google-ads-api-developer-assistant")
        }
        "claudecode" {
            return (Join-Path $UserHome ".claude\plugins\marketplace\google-ads-api-developer-assistant")
        }
        default {
            throw "Invalid target '$TargetPlatform'. Must be 'agy' or 'claudecode'."
        }
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
$TargetPluginDir = Get-PluginTargetDir -TargetPlatform $Target
$LegacyPluginDir = ""
if ($Target.ToLower() -eq "agy") {
    $LegacyPluginDir = Join-Path $UserHome ".gemini\config\plugins\google_ads_assistant_plugin"
}

if ((-not (Test-Path -LiteralPath $TargetPluginDir)) -and ([string]::IsNullOrEmpty($LegacyPluginDir) -or (-not (Test-Path -LiteralPath $LegacyPluginDir)))) {
    Write-Host "Plugin directory '$TargetPluginDir' does not exist. Nothing to uninstall."
    exit 0
}

# If specific client libraries are selected
if ($SpecifiedLangs.Count -gt 0) {
    $PluginDirs = @($TargetPluginDir)
    if ($LegacyPluginDir -and (Test-Path -LiteralPath $LegacyPluginDir)) {
        $PluginDirs += $LegacyPluginDir
    }

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
    Write-Host "Plugin client library removal for $Target complete."
    Write-Host ""
    if ($Target.ToLower() -eq "agy") {
        Write-Host "Restart your Antigravity / agy host to apply changes."
    } else {
        Write-Host "Restart your Claude Code environment to apply changes."
    }
    exit 0
}

Write-Host "This will uninstall the Google Ads API Developer Assistant plugin for $Target"
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

if ($LegacyPluginDir -and (Test-Path -LiteralPath $LegacyPluginDir)) {
    Remove-Item -Recurse -Force -LiteralPath $LegacyPluginDir
}

Write-Host "Plugin uninstallation for $Target complete."
Write-Host ""
if ($Target.ToLower() -eq "agy") {
    Write-Host "Restart your Antigravity / agy host to complete plugin uninstallation."
} else {
    Write-Host "Restart your Claude Code environment to complete plugin uninstallation."
}

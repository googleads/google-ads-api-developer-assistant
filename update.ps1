<#
.SYNOPSIS
    Updates the Google Ads API Developer Assistant plugin and its dependencies on Windows.

.DESCRIPTION
    This script updates the Google Ads API Developer Assistant repository and installed plugin:
    1. Updates the git repository (git pull).
    2. Syncs updated plugin assets to the Antigravity plugin directory.
    3. Clones or updates configured client libraries in the plugin's 'client_libs/' directory.

.PARAMETER Python
    Ensure google-ads-python is present and updated.

.PARAMETER Php
    Ensure google-ads-php is present and updated.

.PARAMETER Ruby
    Ensure google-ads-ruby is present and updated.

.PARAMETER Java
    Ensure google-ads-java is present and updated.

.PARAMETER Dotnet
    Ensure google-ads-dotnet is present and updated.

.EXAMPLE
    .\update.ps1
    Updates repository, Antigravity plugin, and all configured client libraries.

.EXAMPLE
    .\update.ps1 -Java
    Ensures Java library is present and updated in Antigravity plugin.
#>

param(
    [switch]$Python,
    [switch]$Php,
    [switch]$Ruby,
    [switch]$Java,
    [switch]$Dotnet
)

function Get-RepoUrl {
    param($Lang)
    switch ($Lang) {
        "python" { return "https://github.com/googleads/google-ads-python.git" }
        "php"    { return "https://github.com/googleads/google-ads-php.git" }
        "ruby"   { return "https://github.com/googleads/google-ads-ruby.git" }
        "java"   { return "https://github.com/googleads/google-ads-java.git" }
        "dotnet" { return "https://github.com/googleads/google-ads-dotnet.git" }
    }
}

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

function Set-LatestApiVersion {
    param(
        [string]$SearchDir,
        [string]$TargetConfigDir
    )
    if (Test-Path -LiteralPath $SearchDir) {
        $VersionDirs = Get-ChildItem -Directory -Path $SearchDir -Filter "v*" |
            Where-Object { $_.Name -match "^v\d+$" } |
            Sort-Object { [int]($_.Name.Substring(1)) }
        if ($VersionDirs) {
            $Latest = $VersionDirs[-1].Name
            if (-not (Test-Path -LiteralPath $TargetConfigDir)) {
                New-Item -ItemType Directory -Force -LiteralPath $TargetConfigDir | Out-Null
            }
            Set-Content -Path (Join-Path $TargetConfigDir "api_version.txt") -Value $Latest
            Write-Host "Configured API version $Latest in $(Join-Path $TargetConfigDir 'api_version.txt')"
        }
    }
}

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
Write-Host "Updating google-ads-api-developer-assistant repository..."

$CustomerIdFile = Join-Path $ProjectDirAbs "config\customer_id.txt"
$TempCustomerIdFile = [System.IO.Path]::GetTempFileName()

try {
    if (Test-Path -LiteralPath $CustomerIdFile) {
        Copy-Item -LiteralPath $CustomerIdFile -Destination $TempCustomerIdFile -Force
    }

    git pull
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to update google-ads-api-developer-assistant repository."
    }
    Write-Host "Successfully updated repository."

    if ((Test-Path -LiteralPath $TempCustomerIdFile) -and (Get-Item $TempCustomerIdFile).Length -gt 0) {
        Move-Item -LiteralPath $TempCustomerIdFile -Destination $CustomerIdFile -Force
    }
}
catch {
    Write-Error "ERROR: $_"
    if ((Test-Path -LiteralPath $TempCustomerIdFile) -and (Get-Item $TempCustomerIdFile).Length -gt 0) {
        if (-not (Test-Path -LiteralPath $CustomerIdFile) -or (Get-Item $CustomerIdFile).Length -eq 0) {
            Copy-Item -LiteralPath $TempCustomerIdFile -Destination $CustomerIdFile -Force
        }
    }
    exit 1
}
finally {
    if (Test-Path -LiteralPath $TempCustomerIdFile) {
        Remove-Item -LiteralPath $TempCustomerIdFile -Force -ErrorAction SilentlyContinue
    }
}

$SpecifiedLangs = @()
if ($Python) { $SpecifiedLangs += "python" }
if ($Php)    { $SpecifiedLangs += "php" }
if ($Ruby)   { $SpecifiedLangs += "ruby" }
if ($Java)   { $SpecifiedLangs += "java" }
if ($Dotnet) { $SpecifiedLangs += "dotnet" }

# --- Plugin Update ---
$UserHome = if ($env:USERPROFILE) { $env:USERPROFILE } else { $HOME }
$TargetPluginDir = Join-Path $UserHome ".gemini\config\plugins\google-ads-api-developer-assistant"
$ParentPluginDir = Split-Path $TargetPluginDir
$PluginSourceDir = Join-Path $ProjectDirAbs "plugins\google-ads-api-developer-assistant"

if (-not (Test-Path -LiteralPath $TargetPluginDir)) {
    Write-Host "Plugin not yet installed at $TargetPluginDir. Installing..."
    if (-not (Test-Path -LiteralPath $ParentPluginDir)) {
        New-Item -ItemType Directory -Force -LiteralPath $ParentPluginDir | Out-Null
    }
    Copy-Item -Recurse -Force -LiteralPath $PluginSourceDir -Destination $TargetPluginDir
}
else {
    Write-Host "Syncing plugin files to $TargetPluginDir..."
    $ItemsToSync = @("rules", "sidecars", "skills", "config", "client_libs", "plugin.json", "README.md")
    foreach ($Item in $ItemsToSync) {
        $SourceItem = Join-Path $PluginSourceDir $Item
        if (Test-Path -LiteralPath $SourceItem) {
            Copy-Item -Recurse -Force -LiteralPath $SourceItem -Destination (Join-Path $TargetPluginDir $Item)
        }
    }
}

$PluginClientLibs = Join-Path $TargetPluginDir "client_libs"
if (-not (Test-Path -LiteralPath $PluginClientLibs)) {
    New-Item -ItemType Directory -Force -LiteralPath $PluginClientLibs | Out-Null
}

if ($SpecifiedLangs.Count -gt 0) {
    foreach ($Lang in $SpecifiedLangs) {
        $RepoUrl = Get-RepoUrl $Lang
        $RepoName = Get-RepoName $Lang
        $LibPath = Join-Path $PluginClientLibs $RepoName

        if (-not (Test-Path -LiteralPath $LibPath)) {
            Write-Host "Library $RepoName not found in plugin. Cloning into $LibPath..."
            git clone $RepoUrl $LibPath
            if ($LASTEXITCODE -ne 0) { throw "Failed to clone $RepoUrl" }
        }
    }
}

Write-Host "Locating client libraries in $PluginClientLibs..."
$IncludeDirs = @()
if (Test-Path -LiteralPath $PluginClientLibs) {
    foreach ($Dir in Get-ChildItem -LiteralPath $PluginClientLibs -Directory) {
        if (Test-Path -LiteralPath (Join-Path $Dir.FullName ".git")) {
            $IncludeDirs += $Dir.FullName
        }
    }
}

if ($IncludeDirs.Count -eq 0) {
    Write-Host "No client libraries found to update in $PluginClientLibs."
} else {
    Write-Host "Found $($IncludeDirs.Count) client libraries to update."
    foreach ($LibPath in $IncludeDirs) {
        if ([string]::IsNullOrWhiteSpace($LibPath)) { continue }
        if (-not (Test-Path -LiteralPath $LibPath)) {
            Write-Warning "Directory not found: $LibPath. Skipping."
            continue
        }
        $AbsLibPath = (Get-Item -LiteralPath $LibPath).FullName
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
                exit 1
            }
        }
        finally {
            Pop-Location
        }
    }
}

$PluginPythonDir = Join-Path $TargetPluginDir "client_libs\google-ads-python\google\ads\googleads"
Set-LatestApiVersion -SearchDir $PluginPythonDir -TargetConfigDir (Join-Path $TargetPluginDir "config")
Set-LatestApiVersion -SearchDir $PluginPythonDir -TargetConfigDir (Join-Path $ProjectDirAbs "config")

Write-Host "Plugin update complete."
Write-Host ""
Write-Host "Restart your Antigravity / agy host to apply changes."

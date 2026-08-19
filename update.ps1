<#
.SYNOPSIS
    Updates the Google Ads API Developer Assistant plugin and its dependencies on Windows.

.DESCRIPTION
    This script updates the Google Ads API Developer Assistant repository and installed plugin:
    1. Updates the git repository (git pull).
    2. Syncs updated plugin assets to the platform-specific plugin directory (Antigravity or Claude Code).
    3. Clones or updates configured client libraries in the plugin's 'client_libs/' directory.

.PARAMETER Type
    Required. Target platform: 'agy' (Antigravity) or 'claude' (Claude Code).

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

.PARAMETER All
    Ensure all client libraries are present and updated.

.EXAMPLE
    .\update.ps1 -Type agy
    Updates repository, Antigravity plugin, and all configured client libraries.

.EXAMPLE
    .\update.ps1 -Type claude
    Updates repository, Claude Code plugin, and all configured client libraries.

.EXAMPLE
    .\update.ps1 -Type agy -Java
    Ensures Java library is present and updated in Antigravity plugin.
#>

param(
    [Parameter(Position=0, HelpMessage="Target platform: 'agy' or 'claude'")]
    [string]$Type,

    [switch]$Python,
    [switch]$Php,
    [switch]$Ruby,
    [switch]$Java,
    [switch]$Dotnet,
    [switch]$All
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Type)) {
    Write-Error "ERROR: Missing required -Type parameter ('agy' or 'claude')."
    exit 1
}

$TypeLower = $Type.ToLower()
if ($TypeLower -notin @("agy", "claude", "claudecode")) {
    Write-Error "ERROR: Invalid Type '$Type'. Must be 'agy' or 'claude'."
    exit 1
}

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

$CustomerIdFile = Join-Path $ProjectDirAbs "config\customer_id"
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
if ($All) {
    $SpecifiedLangs = @("python", "php", "ruby", "java", "dotnet")
} else {
    if ($Python) { $SpecifiedLangs += "python" }
    if ($Php)    { $SpecifiedLangs += "php" }
    if ($Ruby)   { $SpecifiedLangs += "ruby" }
    if ($Java)   { $SpecifiedLangs += "java" }
    if ($Dotnet) { $SpecifiedLangs += "dotnet" }
}

# --- Plugin Update & Client Libraries ---
$UserHome = if ($env:USERPROFILE) { $env:USERPROFILE } else { $HOME }
$AgyPluginTargetDir = Join-Path $UserHome ".gemini\config\plugins\google-ads-api-developer-assistant"
$PluginSourceDir = Join-Path $ProjectDirAbs "plugins\google-ads-api-developer-assistant"
$PluginSourceClientLibs = Join-Path $PluginSourceDir "client_libs"

if (-not (Test-Path -LiteralPath $PluginSourceClientLibs)) {
    New-Item -ItemType Directory -Force -LiteralPath $PluginSourceClientLibs | Out-Null
}

# Handle specific library additions in repository plugin source
if ($SpecifiedLangs.Count -gt 0) {
    foreach ($Lang in $SpecifiedLangs) {
        $RepoUrl = Get-RepoUrl $Lang
        $RepoName = Get-RepoName $Lang
        $SourceLibPath = Join-Path $PluginSourceClientLibs $RepoName

        if (-not (Test-Path -LiteralPath $SourceLibPath)) {
            Write-Host "Library $RepoName not found in repository client_libs. Cloning into $SourceLibPath..."
            git clone $RepoUrl $SourceLibPath
            if ($LASTEXITCODE -ne 0) { throw "Failed to clone $RepoUrl" }
        }
    }
}

# Locate and update all client libraries in repository
Write-Host "Locating client libraries to update..."
$IncludeDirs = @()
if (Test-Path -LiteralPath $PluginSourceClientLibs) {
    foreach ($Dir in Get-ChildItem -LiteralPath $PluginSourceClientLibs -Directory) {
        if (Test-Path -LiteralPath (Join-Path $Dir.FullName ".git")) {
            $IncludeDirs += $Dir.FullName
        }
    }
}

if ($IncludeDirs.Count -eq 0) {
    Write-Host "No client libraries found in repository to update."
} else {
    Write-Host "Found $($IncludeDirs.Count) client libraries to update."
    foreach ($LibPath in $IncludeDirs) {
        if ([string]::IsNullOrWhiteSpace($LibPath)) { continue }
        if (-not (Test-Path -LiteralPath $LibPath)) { continue }
        $AbsLibPath = (Get-Item -LiteralPath $LibPath).FullName
        if (-not (Test-Path -LiteralPath (Join-Path $AbsLibPath ".git"))) { continue }

        Write-Host "Updating repository at: $AbsLibPath..."
        Push-Location $AbsLibPath
        try {
            git pull
            if ($LASTEXITCODE -eq 0) {
                Write-Host "Successfully updated $(Split-Path $AbsLibPath -Leaf)."
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

$PluginPythonDir = Join-Path $PluginSourceDir "client_libs\google-ads-python\google\ads\googleads"
Set-LatestApiVersion -SearchDir $PluginPythonDir -TargetConfigDir (Join-Path $PluginSourceDir "config")
Set-LatestApiVersion -SearchDir $PluginPythonDir -TargetConfigDir (Join-Path $ProjectDirAbs "config")

# --- Antigravity Specific Sync ---
if ($Type.ToLower() -eq "agy") {
    $ParentPluginDir = Split-Path $AgyPluginTargetDir
    if (-not (Test-Path -LiteralPath $AgyPluginTargetDir)) {
        Write-Host "Plugin not yet installed at $AgyPluginTargetDir. Installing for agy..."
        if (-not (Test-Path -LiteralPath $ParentPluginDir)) {
            New-Item -ItemType Directory -Force -LiteralPath $ParentPluginDir | Out-Null
        }
        Copy-Item -Recurse -Force -LiteralPath $PluginSourceDir -Destination $AgyPluginTargetDir
    }
    else {
        Write-Host "Syncing plugin files to $AgyPluginTargetDir..."
        $ItemsToSync = @("rules", "sidecars", "skills", "commands", "config", "plugin.json", "mcp_config.json", "README.md", "customer_id")
        foreach ($Item in $ItemsToSync) {
            $SourceItem = Join-Path $PluginSourceDir $Item
            if (Test-Path -LiteralPath $SourceItem) {
                Copy-Item -Recurse -Force -LiteralPath $SourceItem -Destination (Join-Path $AgyPluginTargetDir $Item)
            }
        }
    }

    $TargetClientLibs = Join-Path $AgyPluginTargetDir "client_libs"
    if (-not (Test-Path -LiteralPath $TargetClientLibs)) {
        New-Item -ItemType Directory -Force -LiteralPath $TargetClientLibs | Out-Null
    }

    if (Test-Path -LiteralPath $PluginSourceClientLibs) {
        foreach ($LibDir in Get-ChildItem -LiteralPath $PluginSourceClientLibs -Directory) {
            $TargetLibPath = Join-Path $TargetClientLibs $LibDir.Name
            if (-not (Test-Path -LiteralPath $TargetLibPath)) {
                Write-Host "Copying $($LibDir.Name) to $TargetLibPath..."
                Copy-Item -Recurse -Force -LiteralPath $LibDir.FullName -Destination $TargetLibPath
            }
        }
    }

    # Also update any existing client libraries in Antigravity target directory if they are distinct git clones
    if (Test-Path -LiteralPath $TargetClientLibs) {
        foreach ($Dir in Get-ChildItem -LiteralPath $TargetClientLibs -Directory) {
            if (Test-Path -LiteralPath (Join-Path $Dir.FullName ".git")) {
                $SourcePath = Join-Path $PluginSourceClientLibs $Dir.Name
                if ((-not (Test-Path -LiteralPath $SourcePath)) -or ((Get-Item $Dir.FullName).FullName -ne (Get-Item $SourcePath).FullName)) {
                    Write-Host "Updating repository at: $($Dir.FullName)..."
                    Push-Location $Dir.FullName
                    try {
                        git pull
                        if ($LASTEXITCODE -eq 0) {
                            Write-Host "Successfully updated $($Dir.Name)."
                        } else {
                            Write-Error "ERROR: Failed to update $($Dir.FullName)"
                            exit 1
                        }
                    }
                    finally {
                        Pop-Location
                    }
                }
            }
        }
    }

    Set-LatestApiVersion -SearchDir $PluginPythonDir -TargetConfigDir (Join-Path $AgyPluginTargetDir "config")
}

Write-Host "Plugin update for $Type complete."
Write-Host ""
if ($Type.ToLower() -eq "agy") {
    Write-Host "Restart your Antigravity / agy host to apply changes."
} else {
    Write-Host "In your Claude Code session, run /reload-plugins to apply changes."
}

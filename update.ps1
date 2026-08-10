<#
.SYNOPSIS
    Updates the Google Ads API Developer Assistant and its dependencies on Windows.

.DESCRIPTION
    This script performs the following steps:
    1. If -Type project:
       a. Updates the 'google-ads-api-developer-assistant' repository (git pull).
       b. Clones or updates selected client libraries in 'client_libs/'.
       c. If -ContextPath is provided, registers the specified directory in the project configuration.
       d. Updates each found client library repository in 'client_libs/' (git pull).
    2. If -Type plugin:
       a. Locates the plugin directory at $env:USERPROFILE\.gemini\config\plugins\google_ads_assistant_plugin.
       b. Clones any newly requested client libraries into the plugin's 'client_libs/'.
       c. Updates each found client library repository in the plugin's 'client_libs/' (git pull).

.PARAMETER Type
    Required. Update type: 'project' or 'plugin'.

.PARAMETER ContextPath
    Comma-separated list of directories to add to the project configuration for context (project mode only).
#>

param(
    [Parameter(Mandatory=$true, Position=0, HelpMessage="Update type: 'project' or 'plugin'")]
    [ValidateSet("project", "plugin", IgnoreCase=$true)]
    [string]$Type,

    [switch]$Python,
    [switch]$Php,
    [switch]$Ruby,
    [switch]$Java,
    [switch]$Dotnet,
    [string[]]$ContextPath
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

$SpecifiedLangs = @()
if ($Python) { $SpecifiedLangs += "python" }
if ($Php)    { $SpecifiedLangs += "php" }
if ($Ruby)   { $SpecifiedLangs += "ruby" }
if ($Java)   { $SpecifiedLangs += "java" }
if ($Dotnet) { $SpecifiedLangs += "dotnet" }

# --- Plugin Update Branch ---
if ($Type.ToLower() -eq "plugin") {
    $GeminiPluginsDir = if ($env:USERPROFILE) {
        Join-Path $env:USERPROFILE ".gemini\config\plugins"
    } else {
        Join-Path $HOME ".gemini\config\plugins"
    }
    $TargetPluginDir = Join-Path $GeminiPluginsDir "google_ads_assistant_plugin"

    if (-not (Test-Path -LiteralPath $TargetPluginDir)) {
        Write-Error "ERROR: Plugin directory '$TargetPluginDir' does not exist. Please run install.ps1 -Type plugin first."
        exit 1
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

    Write-Host "Plugin update complete."
    exit 0
}

# --- Project Update Branch ---
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

Write-Host "Detected project root: $ProjectDirAbs"

# --- Update Assistant Repo ---
Write-Host "Updating google-ads-api-developer-assistant..."

$CustomerIdFile = Join-Path $ProjectDirAbs "customer_id.txt"
$TempCustomerIdFile = [System.IO.Path]::GetTempFileName()

try {
    if (Test-Path -LiteralPath $CustomerIdFile) {
        Write-Host "Backing up $CustomerIdFile..."
        Copy-Item -LiteralPath $CustomerIdFile -Destination $TempCustomerIdFile -Force
        $GitStatus = git ls-files --error-unmatch $CustomerIdFile 2>$null
        if ($LASTEXITCODE -eq 0) {
             Write-Host "Resetting $CustomerIdFile to avoid merge conflicts..."
             git checkout $CustomerIdFile
        }
    }

    git pull
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to update google-ads-api-developer-assistant."
    }
    Write-Host "Successfully updated google-ads-api-developer-assistant."

    if ((Test-Path -LiteralPath $TempCustomerIdFile) -and (Get-Item $TempCustomerIdFile).Length -gt 0) {
        Write-Host "Restoring preserved $CustomerIdFile..."
        Move-Item -LiteralPath $TempCustomerIdFile -Destination $CustomerIdFile -Force
        Write-Host "Restored $CustomerIdFile successfully."
    }
}
catch {
    Write-Error "ERROR: $_"
    if ((Test-Path -LiteralPath $TempCustomerIdFile) -and (Get-Item $TempCustomerIdFile).Length -gt 0) {
         if (-not (Test-Path -LiteralPath $CustomerIdFile) -or (Get-Item $CustomerIdFile).Length -eq 0) {
             Write-Host "Restoring original customer_id.txt after failure..."
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

# --- Handle Specific Library Additions ---
$InvalidContextDirs = @()
$DefaultParentDir = Join-Path $ProjectDirAbs "client_libs"

if ($SpecifiedLangs.Count -gt 0) {
    foreach ($Lang in $SpecifiedLangs) {
        $RepoUrl = Get-RepoUrl $Lang
        $RepoName = Get-RepoName $Lang
        $LibPath = Join-Path $DefaultParentDir $RepoName

        if (-not (Test-Path -LiteralPath $LibPath)) {
            Write-Host "Library $RepoName not found. Cloning into $LibPath..."
            New-Item -ItemType Directory -Force -Path $DefaultParentDir | Out-Null
            git clone $RepoUrl $LibPath
            if ($LASTEXITCODE -ne 0) { throw "Failed to clone $RepoUrl" }
        }
    }
}

# --- Handle ContextPath argument ---
if ($null -ne $ContextPath -and $ContextPath.Count -gt 0) {
    $Dirs = @()
    foreach ($Item in $ContextPath) {
        if ($Item -like "*,*") {
            $Dirs += $Item -split ','
        } else {
            $Dirs += $Item
        }
    }
    foreach ($Dir in $Dirs) {
        $Dir = $Dir.Trim()
        if ([string]::IsNullOrWhiteSpace($Dir)) { continue }
        
        if (-not (Test-Path -LiteralPath $Dir)) {
            $InvalidContextDirs += "Directory not found: $Dir"
            continue
        }
        
        $AbsDir = (Get-Item -LiteralPath $Dir).FullName
        Write-Host "Registering context path: $AbsDir..."
        
        $PythonExe = Join-Path $ProjectDirAbs ".venv\bin\python3"
        if (-not (Test-Path -LiteralPath $PythonExe)) {
            $PythonExe = Join-Path $ProjectDirAbs ".venv\Scripts\python.exe"
        }
        if (-not (Test-Path -LiteralPath $PythonExe)) {
            $PythonExe = "python3"
            if (-not (Get-Command $PythonExe -ErrorAction SilentlyContinue)) {
                $PythonExe = "python"
            }
        }
        
        & $PythonExe (Join-Path $ProjectDirAbs "update_project_context.py") $ProjectDirAbs $AbsDir
        if ($LASTEXITCODE -ne 0) {
            Write-Error "ERROR: Failed to register context path: $AbsDir"
            exit 1
        }
    }
}

# --- Locate and Update Client Libraries ---
Write-Host "Locating client libraries in $DefaultParentDir..."

$IncludeDirs = @()
if (Test-Path -LiteralPath $DefaultParentDir) {
    foreach ($Dir in Get-ChildItem -LiteralPath $DefaultParentDir -Directory) {
        if (Test-Path -LiteralPath (Join-Path $Dir.FullName ".git")) {
            $IncludeDirs += $Dir.FullName
        }
    }
}

if ($IncludeDirs.Count -eq 0) {
    Write-Host "No client libraries found to update in $DefaultParentDir."
    if ($InvalidContextDirs.Count -gt 0) {
        foreach ($Err in $InvalidContextDirs) {
            [Console]::Error.WriteLine("ERROR: $Err")
        }
    }
    Write-Host "Update complete."
    exit 0
}

Write-Host "Found $($IncludeDirs.Count) client libraries to update."

foreach ($LibPath in $IncludeDirs) {
    if ([string]::IsNullOrWhiteSpace($LibPath)) { continue }
    if (-not (Test-Path -LiteralPath $LibPath)) {
        Write-Warning "Directory not found: $LibPath. Skipping."
        continue
    }

    $AbsLibPath = (Get-Item -LiteralPath $LibPath).FullName
    if ($AbsLibPath -eq $ProjectDirAbs) {
        continue
    }

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

if ($InvalidContextDirs.Count -gt 0) {
    foreach ($Err in $InvalidContextDirs) {
        [Console]::Error.WriteLine("ERROR: $Err")
    }
}

# Pre-seed latest API version in project config
$ProjectPythonDir = Join-Path $DefaultParentDir "google-ads-python\google\ads\googleads"
Set-LatestApiVersion -SearchDir $ProjectPythonDir -TargetConfigDir (Join-Path $ProjectDirAbs "config")

Write-Host "Update complete."

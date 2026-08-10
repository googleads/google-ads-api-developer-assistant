<#
.SYNOPSIS
    Initializes the development environment for the Google Ads API Developer Assistant on Windows.

.DESCRIPTION
    This script installs the Google Ads API Developer Assistant as a standalone project
    or as a plugin for Antigravity (agy).

.PARAMETER Type
    Required. Installation type: 'project' or 'plugin'.

.PARAMETER Php
    Include google-ads-php (for 'project' type).

.PARAMETER Ruby
    Include google-ads-ruby (for 'project' type).

.PARAMETER Java
    Include google-ads-java (for 'project' type).

.PARAMETER Dotnet
    Include google-ads-dotnet (for 'project' type).

.EXAMPLE
    .\install.ps1 -Type project
    Installs the project with the Python library.

.EXAMPLE
    .\install.ps1 -Type project -Java
    Installs the project with Java and Python libraries.

.EXAMPLE
    .\install.ps1 -Type plugin
    Installs the agy plugin into ~/.gemini/config/plugins.
#>

param(
    [Parameter(Mandatory=$true, Position=0, HelpMessage="Installation type: 'project' or 'plugin'")]
    [ValidateSet("project", "plugin", IgnoreCase=$true)]
    [string]$Type,

    [switch]$Php,
    [switch]$Ruby,
    [switch]$Java,
    [switch]$Dotnet
)

$ErrorActionPreference = "Stop"

# --- Project Directory Resolution ---
# Determine the root directory of the current git repository.
try {
    $ProjectDirAbs = git rev-parse --show-toplevel 2>$null
    if (-not $ProjectDirAbs) { throw "Not in a git repo" }
    # Normalize path separator
    $ProjectDirAbs = (Get-Item -LiteralPath $ProjectDirAbs).FullName
}
catch {
    Write-Error "ERROR: This script must be run from within the google-ads-api-developer-assistant git repository."
    exit 1
}

Write-Host "Detected project root: $ProjectDirAbs"

# Helper to get repo config
function Get-RepoConfig {
    param([string]$Lang)
    switch ($Lang) {
        "python" { return @{ Name = "google-ads-python"; Url = "https://github.com/googleads/google-ads-python.git" } }
        "php"    { return @{ Name = "google-ads-php";    Url = "https://github.com/googleads/google-ads-php.git" } }
        "ruby"   { return @{ Name = "google-ads-ruby";   Url = "https://github.com/googleads/google-ads-ruby.git" } }
        "java"   { return @{ Name = "google-ads-java";   Url = "https://github.com/googleads/google-ads-java.git" } }
        "dotnet" { return @{ Name = "google-ads-dotnet"; Url = "https://github.com/googleads/google-ads-dotnet.git" } }
    }
}

# Helper to check if enabled
function Test-Enabled {
    param([string]$Lang)
    switch ($Lang) {
        "python" { return $Python }
        "php"    { return $Php }
        "ruby"   { return $Ruby }
        "java"   { return $Java }
        "dotnet" { return $Dotnet }
        default  { return $false }
    }
}

# --- Defaults ---
$Python = $true
$AnySelected = $false

if ($Php -or $Ruby -or $Java -or $Dotnet) {
    $AnySelected = $true
}

# --- Plugin Installation Branch ---
if ($Type.ToLower() -eq "plugin") {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Error "ERROR: git is not installed. Please install it to continue."
        exit 1
    }

    $PluginSource = Join-Path $ProjectDirAbs "plugins\agy"
    if (-not (Test-Path -LiteralPath $PluginSource)) {
        Write-Error "ERROR: Plugin directory not found at $PluginSource"
        exit 1
    }

    $GeminiPluginsDir = if ($env:USERPROFILE) {
        Join-Path $env:USERPROFILE ".gemini\config\plugins"
    } else {
        Join-Path $HOME ".gemini\config\plugins"
    }
    $TargetPluginDir = Join-Path $GeminiPluginsDir "google_ads_assistant_plugin"

    Write-Host "Installing agy plugin into: $TargetPluginDir"
    if (-not (Test-Path -LiteralPath $GeminiPluginsDir)) {
        New-Item -ItemType Directory -Force -LiteralPath $GeminiPluginsDir | Out-Null
    }

    if (Test-Path -LiteralPath $TargetPluginDir) {
        Remove-Item -Recurse -Force -LiteralPath $TargetPluginDir
    }

    Copy-Item -Recurse -Force -LiteralPath $PluginSource -Destination $TargetPluginDir

    # Add any additional selected client libraries to plugin structure
    $PluginClientLibsDir = Join-Path $TargetPluginDir "client_libs"
    if (-not (Test-Path -LiteralPath $PluginClientLibsDir)) {
        New-Item -ItemType Directory -Force -LiteralPath $PluginClientLibsDir | Out-Null
    }

    $OtherLangs = @("php", "ruby", "java", "dotnet")
    foreach ($Lang in $OtherLangs) {
        if (Test-Enabled -Lang $Lang) {
            $Config = Get-RepoConfig -Lang $Lang
            $TargetRepoPath = Join-Path $PluginClientLibsDir $Config.Name
            $SourceRepoPath = Join-Path $ProjectDirAbs (Join-Path "client_libs" $Config.Name)
            $RepoUrl = $Config.Url

            if (Test-Path -LiteralPath $SourceRepoPath) {
                Write-Host "Adding $($Config.Name) to plugin client_libs from $SourceRepoPath..."
                if (Test-Path -LiteralPath $TargetRepoPath) {
                    Remove-Item -Recurse -Force -LiteralPath $TargetRepoPath
                }
                Copy-Item -Recurse -Force -LiteralPath $SourceRepoPath -Destination $TargetRepoPath
            }
            else {
                Write-Host "Cloning $RepoUrl into $TargetRepoPath..."
                git clone $RepoUrl $TargetRepoPath
                if ($LASTEXITCODE -ne 0) {
                    Write-Error "ERROR: Failed to clone $RepoUrl"
                    exit 1
                }
                Write-Host "Successfully cloned $($Config.Name)."
            }
        }
    }

    Write-Host "Plugin installation complete."
    Write-Host ""
    Write-Host "Restart your Antigravity / agy host to activate the plugin."
    exit 0
}

# --- Project Installation Branch ---
# --- Configuration ---
$DefaultParentDir = Join-Path $ProjectDirAbs "client_libs"
$AllLangs = @("python", "php", "ruby", "java", "dotnet")

# If no specific languages selected, default to Python only
if (-not $AnySelected) {
    Write-Host "No additional languages selected. Defaulting to Python only."
}

# --- Dependency Check ---
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error "ERROR: git is not installed. Please install it to continue."
    exit 1
}

# --- Path Resolution and Validation ---
Write-Host "Ensuring default library directory exists: $DefaultParentDir"
if (-not (Test-Path -LiteralPath $DefaultParentDir)) {
    New-Item -ItemType Directory -Force -LiteralPath $DefaultParentDir | Out-Null
}

$LibPaths = @{}

foreach ($Lang in $AllLangs) {
    if (Test-Enabled -Lang $Lang) {
        $Config = Get-RepoConfig -Lang $Lang
        $RepoPath = Join-Path $DefaultParentDir $Config.Name
        $LibPaths[$Lang] = $RepoPath
    }
}

# --- Clone/Update Repositories ---
foreach ($Lang in $AllLangs) {
    if (Test-Enabled -Lang $Lang) {
        $Config = Get-RepoConfig -Lang $Lang
        $RepoPath = $LibPaths[$Lang]
        $RepoUrl = $Config.Url

        Write-Host "Managing repository $($Config.Name) in $RepoPath"
        
        if (Test-Path -LiteralPath (Join-Path $RepoPath ".git")) {
            Write-Host "Directory $RepoPath already exists. Updating..."
            Push-Location $RepoPath
            try {
                git pull
                if ($LASTEXITCODE -eq 0) {
                     Write-Host "Successfully updated $($Config.Name)."
                } else {
                     Write-Warning "Failed to update $($Config.Name). Continuing..."
                }
            }
            finally {
                Pop-Location
            }
        }
        elseif (Test-Path -LiteralPath $RepoPath) {
             Write-Warning "Directory $RepoPath exists but is not a git repo. Skipping."
        }
        else {
             Write-Host "Cloning $RepoUrl into $RepoPath"
             git clone $RepoUrl $RepoPath
             if ($LASTEXITCODE -ne 0) {
                 Write-Error "ERROR: Failed to clone $RepoUrl"
                 exit 1
             }
             Write-Host "Successfully cloned $($Config.Name)."
        }
    }
}








Write-Host "Installation complete."
Write-Host ""
Write-Host "IMPORTANT: You must manually configure a development environment for each language you wish to use."
Write-Host "           (e.g.,  run 'pip install google-ads' for Python, run 'composer install' for PHP, etc.)"


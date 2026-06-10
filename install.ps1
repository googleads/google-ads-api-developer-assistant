<#
.SYNOPSIS
    Initializes the development environment for the Google Ads API Developer Assistant on Windows.

.DESCRIPTION
    This script performs the following steps:
    1. Verifies that required tools (git) are installed.
    2. Clones or updates the selected Google Ads client libraries into a specified directory.
    3. Updates the '.agents/settings.json' file to include the project's API examples,
       saved code, and the cloned client libraries in the context.

.PARAMETER Python
    Include google-ads-python.

.PARAMETER Php
    Include google-ads-php.

.PARAMETER Ruby
    Include google-ads-ruby.

.PARAMETER Java
    Include google-ads-java.

.PARAMETER Dotnet
    Include google-ads-dotnet.

.EXAMPLE
    .\install.ps1 -Java
    Installs Java and Python libraries.

.EXAMPLE
    .\install.ps1
    Installs only the Python library.

.EXAMPLE
    .\install.ps1 -Java
    Installs Java and Python libraries.
#>

param(
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

# --- Configuration ---
$DefaultParentDir = Join-Path $ProjectDirAbs "client_libs"
$AllLangs = @("python", "php", "ruby", "java", "dotnet")

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

# --- Defaults ---
$Python = $true
$AnySelected = $false

if ($Php -or $Ruby -or $Java -or $Dotnet) {
    $AnySelected = $true
}

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


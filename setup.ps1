<#
.SYNOPSIS
    Initializes the development environment for the Google Ads API Developer Assistant on Windows.

.DESCRIPTION
    This script performs the following steps:
    1. Verifies that required tools (git) are installed.
    2. Clones or updates the selected Google Ads client libraries into a specified directory.
    3. Updates the '.gemini/settings.json' file to include the project's API examples,
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
    .\setup.ps1 -Python -Java
    Installs only Python and Java libraries.

.EXAMPLE
    .\setup.ps1
    Installs ALL supported libraries.
#>

param(
    [switch]$Python,
    [switch]$Php,
    [switch]$Ruby,
    [switch]$Java,
    [switch]$Dotnet
)

$ErrorActionPreference = "Stop"

# --- Configuration ---
$DefaultParentDir = Join-Path $HOME "gaada"
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
# If no specific languages selected, select all
if (-not ($Python -or $Php -or $Ruby -or $Java -or $Dotnet)) {
    Write-Host "No specific languages selected. Defaulting to ALL languages."
    $Python = $true
    $Php = $true
    $Ruby = $true
    $Java = $true
    $Dotnet = $true
}

# --- Dependency Check ---
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Error "ERROR: git is not installed. Please install it to continue."
    exit 1
}

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

        # Validation: check against project dir
        # Simple string check for subdirectory
        if ($RepoPath.StartsWith($ProjectDirAbs)) {
             Write-Error "ERROR: $Lang path ($RepoPath) cannot be a subdirectory of the project directory ($ProjectDirAbs)"
             exit 1
        }
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

# --- Modify settings.json ---
$SettingsFile = Join-Path $ProjectDirAbs ".gemini\settings.json"

if (-not (Test-Path -LiteralPath $SettingsFile)) {
    Write-Error "ERROR: Settings file not found: $SettingsFile"
    exit 1
}

Write-Host "Updating $SettingsFile with context paths..."

$ContextPathExamples = Join-Path $ProjectDirAbs "api_examples"
$ContextPathSaved = Join-Path $ProjectDirAbs "saved_code"

try {
    $SettingsJson = Get-Content -LiteralPath $SettingsFile -Raw | ConvertFrom-Json
    
    # Initialize array with default paths
    $NewPaths = @($ContextPathExamples, $ContextPathSaved)

    # Add enabled lib paths
    foreach ($Lang in $AllLangs) {
        if (Test-Enabled -Lang $Lang) {
            $NewPaths += $LibPaths[$Lang]
        }
    }

    # Update the object
    if (-not $SettingsJson.context) {
        $SettingsJson | Add-Member -MemberType NoteProperty -Name "context" -Value @{}
    }
    # Note: If context is a PSCustomObject, we can just assign.
    if (-not $SettingsJson.context.PSObject.Properties["includeDirectories"]) {
        $SettingsJson.context | Add-Member -MemberType NoteProperty -Name "includeDirectories" -Value $NewPaths
    } else {
        $SettingsJson.context.includeDirectories = $NewPaths
    }

    # Save back to file
    $SettingsJson | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $SettingsFile -Encoding UTF8
    
    Write-Host "Successfully updated $SettingsFile"
    Write-Host "New contents of context.includeDirectories:"
    Write-Host ($SettingsJson.context.includeDirectories | Out-String)
}
catch {
    Write-Error "ERROR: Failed to update settings file: $_"
    exit 1
}



Write-Host "Setup complete."
Write-Host ""
Write-Host "IMPORTANT: You must manually configure a development environment for each language you wish to use."
Write-Host "           (e.g.,  run 'pip install google-ads' for Python, run 'composer install' for PHP, etc.)"

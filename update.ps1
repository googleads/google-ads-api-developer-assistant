<#
.SYNOPSIS
    Updates the Google Ads API Developer Assistant and its dependencies on Windows.

.DESCRIPTION
    This script performs the following steps:
    1. Updates the 'google-ads-api-developer-assistant' repository (git pull).
    2. Clones or updates selected client libraries in 'client_libs/'.
    3. If -ContextPath is provided, registers the specified directory in the project configuration.
    4. Updates each found client library repository (git pull).

.PARAMETER ContextPath
    Comma-separated list of directories to add to the project configuration for context.
#>

param(
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
Write-Host "Updating google-ads-api-developer-assistant..."

$CustomerIdFile = Join-Path $ProjectDirAbs "customer_id.txt"
$TempCustomerIdFile = [System.IO.Path]::GetTempFileName()

try {
    # Backup customer_id.txt if it exists
    if (Test-Path -LiteralPath $CustomerIdFile) {
        Write-Host "Backing up $CustomerIdFile..."
        Copy-Item -LiteralPath $CustomerIdFile -Destination $TempCustomerIdFile -Force

        # Reset local changes
        $GitStatus = git ls-files --error-unmatch $CustomerIdFile 2>$null
        if ($LASTEXITCODE -eq 0) {
             Write-Host "Resetting $CustomerIdFile to avoid merge conflicts..."
             git checkout $CustomerIdFile
        }
    }

    # Update Repo
    git pull
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to update google-ads-api-developer-assistant."
    }
    Write-Host "Successfully updated google-ads-api-developer-assistant."

    # Restore customer_id.txt
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
$SpecifiedLangs = @()
if ($Python) { $SpecifiedLangs += "python" }
if ($Php)    { $SpecifiedLangs += "php" }
if ($Ruby)   { $SpecifiedLangs += "ruby" }
if ($Java)   { $SpecifiedLangs += "java" }
if ($Dotnet) { $SpecifiedLangs += "dotnet" }

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
        
        # Resolve Python interpreter path
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
    
    # Check if path exists
    if (-not (Test-Path -LiteralPath $LibPath)) {
        Write-Warning "Directory not found: $LibPath. Skipping."
        continue
    }

    $AbsLibPath = (Get-Item -LiteralPath $LibPath).FullName

    # Skip the main assistant workspace since we already updated it
    if ($AbsLibPath -eq $ProjectDirAbs) {
        continue
    }

    # Check if it is a git repository
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

Write-Host "Update complete."

<#
.SYNOPSIS
    Test script for update.ps1
#>

$ErrorActionPreference = "Stop"

# --- Test Setup ---
$TestTmpDir = [System.IO.Path]::GetTempPath() + [System.IO.Path]::GetRandomFileName()
New-Item -ItemType Directory -Force -Path $TestTmpDir | Out-Null
$UpdateScriptPath = Resolve-Path (Join-Path $PSScriptRoot ".." "update.ps1")
$RealRoot = (Get-Item (Join-Path $PSScriptRoot "..")).FullName

Write-Host "Running tests in $TestTmpDir"

# Cleanup
function Cleanup {
    if (Test-Path $TestTmpDir) {
        Remove-Item -Recurse -Force $TestTmpDir -ErrorAction SilentlyContinue
    }
}

try {
    # 1. Mock Environment
    $FakeHome = Join-Path $TestTmpDir "fake_home"
    $FakeProject = Join-Path $TestTmpDir "fake_project"
    $FakeBin = Join-Path $FakeHome "bin"
    New-Item -ItemType Directory -Force -Path $FakeBin | Out-Null
    New-Item -ItemType Directory -Force -Path $FakeProject | Out-Null

    # Add FakeBin to PATH and set HOME / USERPROFILE env
    $env:PATH = "$FakeBin$([System.IO.Path]::PathSeparator)$env:PATH"
    $env:HOME = $FakeHome
    $env:USERPROFILE = $FakeHome

    # Create Mock Scripts (Simulating environment)
    # git mock
    Set-Content -Path (Join-Path $FakeBin "git") -Value "#!/bin/bash`nif [[ `"`$1`" == `"rev-parse`" ]]; then echo `"$FakeProject`"; elif [[ `"`$1`" == `"clone`" ]]; then mkdir -p `"`$3/.git`"; echo `"Mock cloned`"; elif [[ `"`$1`" == `"pull`" ]]; then echo `"Mock pull successful`"; elif [[ `"`$1`" == `"ls-files`" ]]; then exit 0; elif [[ `"`$1`" == `"checkout`" ]]; then echo `"Mock checkout successful`"; else echo `"Mock git`"; fi"
    if ($IsLinux -or $IsMacOS) { 
        chmod +x (Join-Path $FakeBin "git")
    }

    # 2. Setup Fake Project Config
    $ProjectsDir = Join-Path $FakeHome ".gemini\config\projects"
    New-Item -ItemType Directory -Force -Path $ProjectsDir | Out-Null
    $ProjectConfigFile = Join-Path $ProjectsDir "6039b1bb-7a20-43ad-b2b7-e64ce62a74ce.json"
    
    $ProjectConfigContent = @"
{
  "id": "6039b1bb-7a20-43ad-b2b7-e64ce62a74ce",
  "name": "$FakeProject",
  "projectResources": {
    "resources": [
      {
        "folderUri": "file://$FakeProject"
      }
    ]
  }
}
"@
    Set-Content -Path $ProjectConfigFile -Value $ProjectConfigContent
    
    # Create a dummy client library to update
    $PyDir = Join-Path $FakeProject "client_libs/google-ads-python"
    New-Item -ItemType Directory -Force -Path $PyDir | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $PyDir ".git") | Out-Null

    # Copy update.ps1 and update_project_context.py to fake project root
    Copy-Item $UpdateScriptPath (Join-Path $FakeProject "update.ps1")
    Copy-Item (Join-Path $RealRoot "update_project_context.py") (Join-Path $FakeProject "update_project_context.py")

    # Setup mocked virtual environment python interpreter
    $VenvBin = Join-Path $FakeProject ".venv\bin"
    $PythonName = "python3"
    if ($IsWindows) {
        $VenvBin = Join-Path $FakeProject ".venv\Scripts"
        $PythonName = "python.exe"
    }
    New-Item -ItemType Directory -Force -Path $VenvBin | Out-Null
    
    $RealPython = Get-Command python3 -ErrorAction SilentlyContinue
    if (-not $RealPython) { $RealPython = Get-Command python }
    Copy-Item $RealPython.Source (Join-Path $VenvBin $PythonName)

    # Move current location to FakeProject to run update.ps1
    Push-Location $FakeProject

    # --- Test Case 1: Default update.ps1 ---
    Write-Host "--- Test Case 1: Default Update ---"
    & .\update.ps1
    if ($LASTEXITCODE -ne 0) { throw "update.ps1 failed" }
    Write-Host "PASS: Default run successful"

    # --- Test Case 2: Run update.ps1 with valid ContextPath ---
    Write-Host "--- Test Case 2: Add valid context directory ---"
    $ValidDir = Join-Path $TestTmpDir "valid_dir"
    New-Item -ItemType Directory -Force -Path $ValidDir | Out-Null
    
    & .\update.ps1 -ContextPath $ValidDir
    if ($LASTEXITCODE -ne 0) { throw "update.ps1 failed with ContextPath" }

    $Config = Get-Content -Raw $ProjectConfigFile | ConvertFrom-Json
    $IncludedDirs = @()
    foreach ($Res in $Config.projectResources.resources) {
        if ($Res.gitFolder) { $IncludedDirs += $Res.gitFolder.folderUri }
        if ($Res.folderUri) { $IncludedDirs += $Res.folderUri }
    }
    $ExpectedUri = "file://" + (Get-Item -LiteralPath $ValidDir).FullName
    if ($IncludedDirs -contains $ExpectedUri) { Write-Host "PASS: valid context path added" } else { throw "FAIL: missing valid context path" }

    # --- Test Case 3: Run update.ps1 with invalid ContextPath ---
    Write-Host "--- Test Case 3: Add invalid context directory ---"
    $InvalidDir = Join-Path $TestTmpDir "non_existent_dir"
    
    try {
        & .\update.ps1 -ContextPath $InvalidDir
        throw "FAIL: update.ps1 should have failed with non-existent path"
    }
    catch {
        Write-Host "PASS: invalid context path rejected"
    }

    # --- Test Case 4: Mixed list ---
    Write-Host "--- Test Case 4: Mixed list valid and invalid ---"
    $ValidDir2 = Join-Path $TestTmpDir "valid_dir2"
    New-Item -ItemType Directory -Force -Path $ValidDir2 | Out-Null
    $InvalidDir2 = Join-Path $TestTmpDir "non_existent_dir2"

    try {
        & .\update.ps1 -ContextPath "$ValidDir2,$InvalidDir2"
        throw "FAIL: update.ps1 should have failed with mixed list"
    }
    catch {
        Write-Host "PASS: mixed list failed as expected"
    }

    Pop-Location
    Write-Host "ALL TESTS PASSED"

}
catch {
    Write-Error "Test Failed: $_"
    exit 1
}
finally {
    Cleanup
}

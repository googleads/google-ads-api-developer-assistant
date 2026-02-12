<#
.SYNOPSIS
    Test script for uninstall.ps1
#>

$ErrorActionPreference = "Stop"

# --- Test Setup ---
$TestTmpDir = [System.IO.Path]::GetTempPath() + [System.IO.Path]::GetRandomFileName()
New-Item -ItemType Directory -Force -Path $TestTmpDir | Out-Null
$UninstallScriptPath = Resolve-Path (Join-Path $PSScriptRoot ".." "uninstall.ps1")

Write-Host "Running tests in $TestTmpDir"

# Cleanup
function Cleanup {
    Remove-Item -Recurse -Force $TestTmpDir -ErrorAction SilentlyContinue
}

try {
    # 1. Mock Environment
    $FakeHome = Join-Path $TestTmpDir "fake_home"
    $MockParentDir = Join-Path $TestTmpDir "mock_parent"
    $FakeProject = Join-Path $MockParentDir "google-ads-api-developer-assistant"
    $FakeBin = Join-Path $FakeHome "bin"
    
    New-Item -ItemType Directory -Force -Path $FakeBin | Out-Null
    New-Item -ItemType Directory -Force -Path $FakeProject | Out-Null

    # Add FakeBin to PATH
    $env:PATH = "$FakeBin$([System.IO.Path]::PathSeparator)$env:PATH"

    # Create Mock Scripts
    # git mock
    Set-Content -Path (Join-Path $FakeBin "git") -Value "#!/bin/bash`nif [[ `"`$1`" == `"rev-parse`" ]]; then echo `"$FakeProject`"; else echo `"Mock git`"; fi"
    if ($IsLinux) { chmod +x (Join-Path $FakeBin "git") }

    # gemini mock
    $UninstallLog = Join-Path $TestTmpDir "uninstall_log.txt"
    Set-Content -Path (Join-Path $FakeBin "gemini") -Value "#!/bin/bash`necho `"MOCK: gemini `$*`" >> `"$UninstallLog`""
    if ($IsLinux) { chmod +x (Join-Path $FakeBin "gemini") }

    # 2. Setup Fake Project
    Set-Content -Path (Join-Path $FakeProject "some_file.txt") -Value "test"

    # --- Test Case 1: Run uninstall.ps1 with 'n' ---
    Write-Host "--- Running uninstall.ps1 with 'n' (Cancellation) ---"
    # We use a temporary input file to simulate Read-Host input
    # Actually, we can use a string array and pipe it
    $Result = "n" | pwsh -File $UninstallScriptPath
    
    if (Test-Path $FakeProject) {
        Write-Host "PASS: Cancellation respected"
    } else {
        throw "FAIL: project directory was deleted on cancellation"
    }

    # --- Test Case 2: Run uninstall.ps1 with 'Y' ---
    Write-Host "--- Running uninstall.ps1 with 'Y' (Success) ---"
    $Result = "Y" | pwsh -File $UninstallScriptPath
    
    if (Test-Path $FakeProject) {
        throw "FAIL: project directory still exists"
    } else {
        Write-Host "PASS: Directory removed"
    }

    if (Get-Content $UninstallLog | Select-String "extensions uninstall google-ads-api-developer-assistant") {
        Write-Host "PASS: gemini extensions uninstall called"
    } else {
        throw "FAIL: gemini extensions uninstall NOT called"
    }

    Write-Host "ALL POWERSHELL UNINSTALL TESTS PASSED"

}
catch {
    Write-Error "Test Failed: $_"
    exit 1
}
finally {
    Cleanup
}

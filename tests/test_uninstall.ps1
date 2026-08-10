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

    # 2. Setup Fake Project
    Set-Content -Path (Join-Path $FakeProject "some_file.txt") -Value "test"

    # --- Test Case 1: Run uninstall.ps1 -Type project with 'n' ---
    Write-Host "--- Running uninstall.ps1 -Type project with 'n' (Cancellation) ---"
    $Result = "n" | pwsh -File $UninstallScriptPath -Type project
    
    if (Test-Path $FakeProject) {
        Write-Host "PASS: Project cancellation respected"
    } else {
        throw "FAIL: project directory was deleted on cancellation"
    }

    # --- Test Case 2: Run uninstall.ps1 -Type plugin with 'n' ---
    $FakePluginDir = Join-Path $FakeHome ".gemini/config/plugins/google_ads_assistant_plugin"
    New-Item -ItemType Directory -Force -Path $FakePluginDir | Out-Null
    Set-Content -Path (Join-Path $FakePluginDir "plugin.json") -Value '{"name": "google-ads-api-developer-assistant"}'

    Write-Host "--- Running uninstall.ps1 -Type plugin with 'n' (Cancellation) ---"
    $Result = "n" | pwsh -File $UninstallScriptPath -Type plugin
    if (Test-Path $FakePluginDir) {
        Write-Host "PASS: Plugin cancellation respected"
    } else {
        throw "FAIL: plugin directory was deleted on cancellation"
    }

    # --- Test Case 3: Run uninstall.ps1 -Type plugin -Force ---
    Write-Host "--- Running uninstall.ps1 -Type plugin -Force (Success) ---"
    & $UninstallScriptPath -Type plugin -Force
    if (Test-Path $FakePluginDir) {
        throw "FAIL: plugin directory still exists after -Force"
    } else {
        Write-Host "PASS: Plugin directory removed"
    }

    # --- Test Case 4: Run uninstall.ps1 -Type project -Force ---
    Write-Host "--- Running uninstall.ps1 -Type project -Force (Success) ---"
    & $UninstallScriptPath -Type project -Force
    
    if (Test-Path $FakeProject) {
        throw "FAIL: project directory still exists after -Force"
    } else {
        Write-Host "PASS: Project directory removed"
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

<#
.SYNOPSIS
    Test script for install.ps1
#>

$ErrorActionPreference = "Stop"

# --- Test Setup ---
$TestTmpDir = [System.IO.Path]::GetTempPath() + [System.IO.Path]::GetRandomFileName()
New-Item -ItemType Directory -Force -Path $TestTmpDir | Out-Null
$InstallScriptPath = Resolve-Path (Join-Path $PSScriptRoot ".." "install.ps1")

Write-Host "Running tests in $TestTmpDir"

# Cleanup
function Cleanup {
    Remove-Item -Recurse -Force $TestTmpDir -ErrorAction SilentlyContinue
}
# Register cleanup? PowerShell try/finally is better.

try {
    # 1. Mock Environment
    $FakeHome = Join-Path $TestTmpDir "fake_home"
    $FakeProject = Join-Path $TestTmpDir "fake_project"
    $FakeBin = Join-Path $FakeHome "bin"
    New-Item -ItemType Directory -Force -Path $FakeBin | Out-Null
    New-Item -ItemType Directory -Force -Path $FakeProject | Out-Null

    # Add FakeBin to PATH
    $env:PATH = "$FakeBin$([System.IO.Path]::PathSeparator)$env:PATH"

    # Create Mock Scripts (Simulating Linux environment where we test)
    # git mock
    Set-Content -Path (Join-Path $FakeBin "git") -Value "#!/bin/bash`nif [[ `"`$1`" == `"rev-parse`" ]]; then echo `"$FakeProject`"; elif [[ `"`$1`" == `"clone`" ]]; then mkdir -p `"`$3/.git`"; echo `"Mock cloned`"; else echo `"Mock git`"; fi"
    # chmod +x not needed if we stay in pwsh? Wait, pwsh on Linux uses PATH to find executables.
    # We need to make them executable.
    
    if ($IsLinux) {
        chmod +x (Join-Path $FakeBin "git")
    }

    # Python Mock
    $InstallLog = Join-Path $TestTmpDir "install_log.txt"
    Set-Content -Path (Join-Path $FakeBin "python") -Value "#!/bin/bash`necho `"MOCK: python `$*`" >> `"$InstallLog`""
    if ($IsLinux) { chmod +x (Join-Path $FakeBin "python") }

    # Composer Mock
    Set-Content -Path (Join-Path $FakeBin "composer") -Value "#!/bin/bash`necho `"MOCK: composer `$*`" >> `"$InstallLog`""
    if ($IsLinux) { chmod +x (Join-Path $FakeBin "composer") }

    # Bundle Mock
    Set-Content -Path (Join-Path $FakeBin "bundle") -Value "#!/bin/bash`necho `"MOCK: bundle `$*`" >> `"$InstallLog`""
    if ($IsLinux) { chmod +x (Join-Path $FakeBin "bundle") }
    
    # Git needs to be git.exe on Windows. This test likely only runs on Linux per the environment.
    
    # 2. Setup Fake Project

    New-Item -ItemType Directory -Force -Path (Join-Path $FakeProject "api_examples") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $FakeProject "saved/code") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $FakeProject "plugins/agy") | Out-Null
    Set-Content -Path (Join-Path $FakeProject "plugins/agy/plugin.json") -Value '{"name": "google-ads-api-developer-assistant"}'

    # Create dummy composer.json and Gemfile
    $PhpDir = Join-Path $FakeProject "client_libs/google-ads-php"
    New-Item -ItemType Directory -Force -Path $PhpDir | Out-Null
    New-Item -ItemType File -Force -Path (Join-Path $PhpDir "composer.json") | Out-Null
    
    $RubyDir = Join-Path $FakeProject "client_libs/google-ads-ruby"
    New-Item -ItemType Directory -Force -Path $RubyDir | Out-Null
    New-Item -ItemType File -Force -Path (Join-Path $RubyDir "Gemfile") | Out-Null




    # --- Test Case 1: Run install.ps1 with -Type project (Default languages) ---
    Write-Host "--- Running install.ps1 -Type project ---"
    # Ensure client_libs is clean for this test case
    Remove-Item -Recurse -Force (Join-Path $FakeProject "client_libs") -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path (Join-Path $FakeProject "client_libs") | Out-Null
    
    & $InstallScriptPath -Type project
    if ($LASTEXITCODE -ne 0) { throw "install.ps1 failed with -Type project" }
    
    # Check Python exists (filesystem check)
    $ExpectedPython = Join-Path $FakeProject "client_libs/google-ads-python"
    if (Test-Path -LiteralPath (Join-Path $ExpectedPython ".git")) { Write-Host "PASS: google-ads-python was cloned" } else { throw "FAIL: google-ads-python was not cloned" }
    
    # Check others don't exist
    $Langs = @("php", "ruby", "java", "dotnet")
    foreach ($L in $Langs) {
        $NotExpected = Join-Path $FakeProject "client_libs/google-ads-$L"
        if (Test-Path -LiteralPath $NotExpected) { throw "FAIL: google-ads-$L was cloned but should not have been" } else { Write-Host "PASS: google-ads-$L correctly missing" }
    }

    # --- Test Case 2: Run install.ps1 with -Type plugin ---
    Write-Host "--- Running install.ps1 -Type plugin ---"
    & $InstallScriptPath -Type plugin
    if ($LASTEXITCODE -ne 0) { throw "install.ps1 failed with -Type plugin" }

    $ExpectedPluginDir = Join-Path $FakeHome ".gemini/config/plugins/google_ads_assistant_plugin"
    if (Test-Path -LiteralPath (Join-Path $ExpectedPluginDir "plugin.json")) {
        Write-Host "PASS: plugin was installed into $ExpectedPluginDir"
    } else {
        throw "FAIL: plugin was not installed into $ExpectedPluginDir"
    }

    # --- Test Case 3: Run install.ps1 with -Type plugin -Java ---
    Write-Host "--- Running install.ps1 -Type plugin -Java ---"
    & $InstallScriptPath -Type plugin -Java
    if ($LASTEXITCODE -ne 0) { throw "install.ps1 failed with -Type plugin -Java" }

    $ExpectedJavaLib = Join-Path $ExpectedPluginDir "client_libs/google-ads-java"
    if (Test-Path -LiteralPath $ExpectedJavaLib) {
        Write-Host "PASS: google-ads-java was added to plugin client_libs"
    } else {
        throw "FAIL: google-ads-java was not added to plugin client_libs"
    }

    Write-Host "ALL TESTS PASSED"

}
catch {
    Write-Error "Test Failed: $_"
    exit 1
}
finally {
    Cleanup
}

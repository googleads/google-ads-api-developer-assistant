<#
.SYNOPSIS
    Test script for setup.ps1
#>

$ErrorActionPreference = "Stop"

# --- Test Setup ---
$TestTmpDir = [System.IO.Path]::GetTempPath() + [System.IO.Path]::GetRandomFileName()
New-Item -ItemType Directory -Force -Path $TestTmpDir | Out-Null
$SetupScriptPath = Resolve-Path (Join-Path $PSScriptRoot ".." "setup.ps1")

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
    New-Item -ItemType Directory -Force -Path (Join-Path $FakeProject ".gemini") | Out-Null
    Set-Content -Path (Join-Path $FakeProject ".gemini/settings.json") -Value '{"context": {"includeDirectories": []}}'
    New-Item -ItemType Directory -Force -Path (Join-Path $FakeProject "api_examples") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $FakeProject "saved_code") | Out-Null
    
    # Create dummy composer.json and Gemfile
    $PhpDir = Join-Path $FakeProject "client_libs/google-ads-php"
    New-Item -ItemType Directory -Force -Path $PhpDir | Out-Null
    New-Item -ItemType File -Force -Path (Join-Path $PhpDir "composer.json") | Out-Null
    
    $RubyDir = Join-Path $FakeProject "client_libs/google-ads-ruby"
    New-Item -ItemType Directory -Force -Path $RubyDir | Out-Null
    New-Item -ItemType File -Force -Path (Join-Path $RubyDir "Gemfile") | Out-Null

    # --- Test Case 1: Run setup.ps1 -Python -Php -Ruby -InstallDeps ---
    Write-Host "--- Running setup.ps1 -Python -Php -Ruby -InstallDeps ---"
    Remove-Item -Force $InstallLog -ErrorAction SilentlyContinue
    
    # We must run it in the FakeProject dir so git rev-parse finds it? 
    # setup.ps1 calls `git rev-parse --show-toplevel`.
    # Our mock git returns $FakeProject regardless of CWD if we mocked it correctly.
    # Ah, our mock git `rev-parse` returns `$FakeProject`.
    
    # Execute setup.ps1
    & $SetupScriptPath -Python -Php -Ruby -InstallDeps
    if ($LASTEXITCODE -ne 0) { throw "setup.ps1 failed" }
    
    $LogContent = Get-Content -Raw $InstallLog -ErrorAction SilentlyContinue
    Write-Host "Log Content:`n$LogContent"
    
    if ($LogContent -match "python .* pip install .* google-ads") { Write-Host "PASS: python pip install" } else { throw "FAIL: python pip install missed" }
    if ($LogContent -match "composer install") { Write-Host "PASS: composer install" } else { throw "FAIL: composer install missed" }
    if ($LogContent -match "bundle install") { Write-Host "PASS: bundle install" } else { throw "FAIL: bundle install missed" }

    # --- Test Case 2: Run setup.ps1 NO InstallDeps ---
    Write-Host "--- Running setup.ps1 (NO Deps) ---"
    Remove-Item -Force $InstallLog -ErrorAction SilentlyContinue
    
    & $SetupScriptPath -Python -Php -Ruby
    if ($LASTEXITCODE -ne 0) { throw "setup.ps1 failed" }
    
    if (Test-Path $InstallLog) {
        throw "FAIL: Install log exists, commands ran when they shouldn't have"
    } else {
        Write-Host "PASS: No install commands executed"
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

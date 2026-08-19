# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

<#
.SYNOPSIS
    Runs test suite for install.ps1 and update.ps1 across Antigravity and Claude Code.
#>

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

Write-Host "=== Running PowerShell Plugin Scripts Test Suite ==="

# Set up isolated temporary user profile / home directory
$TestHome = Join-Path ([System.IO.Path]::GetTempPath()) ("test_home_" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $TestHome -Force | Out-Null

$env:USERPROFILE = $TestHome
$env:HOME = $TestHome
$env:ANTIGRAVITY_APP_DIR = Join-Path $TestHome ".gemini"

# Mock claude CLI in TestHome\bin
$BinDir = Join-Path $TestHome "bin"
New-Item -ItemType Directory -Path $BinDir -Force | Out-Null
$env:PATH = "$BinDir;$env:PATH"

$MockClaudeCmd = Join-Path $BinDir "claude.cmd"
Set-Content -Path $MockClaudeCmd -Value "@echo [MOCK CLAUDE] Called with: %*`rexit /b 0" -Encoding ASCII

$MockClaudeBat = Join-Path $BinDir "claude.bat"
Set-Content -Path $MockClaudeBat -Value "@echo [MOCK CLAUDE] Called with: %*`rexit /b 0" -Encoding ASCII

$MockClaudePs1 = Join-Path $BinDir "claude.ps1"
Set-Content -Path $MockClaudePs1 -Value "Write-Output ('[MOCK CLAUDE] Called with: ' + (`$args -join ' '))" -Encoding UTF8

$AgyPluginDir = Join-Path $TestHome ".gemini\config\plugins\google-ads-api-developer-assistant"

try {
    # Test 1: install.ps1 requires -Type argument
    Write-Host "Test 1: install.ps1 enforces required Type parameter"
    $failed = $false
    try {
        $out1 = & "$ProjectRoot\install.ps1" *>&1 | Out-String
    } catch {
        $failed = $true
    }
    if (-not $failed) {
        if ($out1 -and ($out1 -match "missing mandatory parameter" -or $out1 -match "Cannot process command" -or $out1 -match "Missing required -Type parameter" -or $out1 -match "ERROR:")) {
            $failed = $true
        }
    }
    if (-not $failed) {
        Write-Error "FAIL: install.ps1 without Type parameter should fail. Output: $out1"
        exit 1
    }
    Write-Host "PASS: install.ps1 enforces required Type parameter."

    # Test 2: install.ps1 -Help displays options
    Write-Host "Test 2: install.ps1 -? / help displays options"
    $helpOutput = Get-Help "$ProjectRoot\install.ps1" | Out-String
    if ($helpOutput -notmatch "claude") {
        Write-Error "FAIL: install.ps1 help should mention claude"
        exit 1
    }
    Write-Host "PASS: install.ps1 help is valid."

    # Test 3: install.ps1 -Type agy installs plugin into .gemini/config/plugins/google-ads-api-developer-assistant
    Write-Host "Test 3: install.ps1 -Type agy installs plugin into ~/.gemini/config/plugins/google-ads-api-developer-assistant"
    & "$ProjectRoot\install.ps1" -Type agy *>&1 | Out-Null
    if (-not (Test-Path $AgyPluginDir)) {
        Write-Error "FAIL: Antigravity plugin directory was not created at $AgyPluginDir"
        exit 1
    }
    if (-not (Test-Path (Join-Path $AgyPluginDir "plugin.json"))) {
        Write-Error "FAIL: plugin.json missing in $AgyPluginDir"
        exit 1
    }
    if (-not (Test-Path (Join-Path $AgyPluginDir "config\api_version.txt"))) {
        Write-Error "FAIL: config\api_version.txt missing in $AgyPluginDir"
        exit 1
    }
    Write-Host "PASS: Antigravity plugin successfully installed."

    # Test 4: install.ps1 -Type claude executes claude CLI marketplace add and install commands
    Write-Host "Test 4: install.ps1 -Type claude executes marketplace add and plugin install"
    $claudeOutput = (& "$ProjectRoot\install.ps1" -Type claude *>&1 | Out-String)
    if ($claudeOutput -notmatch "marketplace add") {
        Write-Error "FAIL: install.ps1 -Type claude did not execute marketplace add. Output: $claudeOutput"
        exit 1
    }
    if ($claudeOutput -notmatch "plugin install google-ads-api-developer-assistant@google-ads-assistant-local") {
        Write-Error "FAIL: install.ps1 -Type claude did not execute plugin install. Output: $claudeOutput"
        exit 1
    }
    Write-Host "PASS: install.ps1 -Type claude executed Claude Code marketplace commands."

    # Test 5: update.ps1 requires -Type parameter
    Write-Host "Test 5: update.ps1 enforces required Type parameter"
    $updateFailed = $false
    try {
        $out5 = & "$ProjectRoot\update.ps1" *>&1 | Out-String
    } catch {
        $updateFailed = $true
    }
    if (-not $updateFailed) {
        if ($out5 -and ($out5 -match "missing mandatory parameter" -or $out5 -match "Cannot process command" -or $out5 -match "Missing required -Type parameter" -or $out5 -match "ERROR:")) {
            $updateFailed = $true
        }
    }
    if (-not $updateFailed) {
        Write-Error "FAIL: update.ps1 without Type parameter should fail. Output: $out5"
        exit 1
    }
    Write-Host "PASS: update.ps1 enforces required Type parameter."

    # Test 6: update.ps1 help displays options
    Write-Host "Test 6: update.ps1 help displays options"
    $updateHelp = Get-Help "$ProjectRoot\update.ps1" | Out-String
    if ($updateHelp -notmatch "claude") {
        Write-Error "FAIL: update.ps1 help should mention claude"
        exit 1
    }
    Write-Host "PASS: update.ps1 help is valid."

    # Test 7: update.ps1 -Type agy updates Antigravity plugin
    Write-Host "Test 7: update.ps1 -Type agy updates Antigravity plugin"
    & "$ProjectRoot\update.ps1" -Type agy *>&1 | Out-Null
    if (-not (Test-Path (Join-Path $AgyPluginDir "plugin.json"))) {
        Write-Error "FAIL: plugin.json missing after update in agy"
        exit 1
    }
    Write-Host "PASS: update.ps1 -Type agy executed successfully."

    # Test 8: update.ps1 -Type claude updates Claude Code plugin in repository
    Write-Host "Test 8: update.ps1 -Type claude updates Claude Code plugin in repository"
    & "$ProjectRoot\update.ps1" -Type claude *>&1 | Out-Null
    $RepoPluginJson = Join-Path $ProjectRoot "plugins\google-ads-api-developer-assistant\plugin.json"
    if (-not (Test-Path $RepoPluginJson)) {
        Write-Error "FAIL: plugin.json missing in repository plugin after update"
        exit 1
    }
    Write-Host "PASS: update.ps1 -Type claude executed successfully."

    # Test 9: update.ps1 -Type claude -Php adds google-ads-php to repository plugin client_libs
    Write-Host "Test 9: update.ps1 -Type claude -Php adds google-ads-php to repository plugin client_libs"
    & "$ProjectRoot\update.ps1" -Type claude -Php *>&1 | Out-Null
    $PhpLibDir = Join-Path $ProjectRoot "plugins\google-ads-api-developer-assistant\client_libs\google-ads-php"
    if (-not (Test-Path $PhpLibDir)) {
        Write-Error "FAIL: google-ads-php missing from repository plugin client_libs"
        exit 1
    }
    Write-Host "PASS: update.ps1 -Type claude -Php added client library successfully."

    Write-Host "=== All PowerShell Tests Passed Successfully! ==="
}
finally {
    if (Test-Path $TestHome) {
        Remove-Item -Recurse -Force $TestHome -ErrorAction SilentlyContinue
    }
}

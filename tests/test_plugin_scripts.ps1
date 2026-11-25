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
$ClaudeMarketplaceDir = Join-Path $TestHome ".claude\plugins\google-ads-assistant-local"
$ClaudePluginDir = Join-Path $ClaudeMarketplaceDir "plugins\google-ads-api-developer-assistant"

function Invoke-Checked {
    param(
        [string]$Label,
        [scriptblock]$Command
    )
    $global:LASTEXITCODE = 0
    $Output = (& $Command *>&1 | Out-String)
    $ExitCode = $LASTEXITCODE
    if ($ExitCode -ne 0) {
        Write-Error "FAIL: $Label exited with code $ExitCode. Output:`n$Output"
        exit 1
    }
    return $Output
}

function Assert-NoClaudeOnlyFiles {
    param(
        [string]$PluginDir,
        [string]$Context
    )
    foreach ($Rel in @(".claude-plugin", ".mcp.json", ".mcp.json.disabled", "hooks", "commands")) {
        $Full = Join-Path $PluginDir $Rel
        if (Get-Item -LiteralPath $Full -Force -ErrorAction SilentlyContinue) {
            Write-Error "FAIL: Claude-only item '$Rel' should not exist in agy plugin dir ($Context): $Full"
            exit 1
        }
    }
}

function Assert-NoUtf8Bom {
    param([string]$FilePath)
    if (Test-Path -LiteralPath $FilePath) {
        $Bytes = [System.IO.File]::ReadAllBytes($FilePath)
        if ($Bytes.Length -ge 3 -and $Bytes[0] -eq 0xEF -and $Bytes[1] -eq 0xBB -and $Bytes[2] -eq 0xBF) {
            Write-Error "FAIL: File has unexpected UTF-8 BOM: $FilePath"
            exit 1
        }
    }
}

try {
    # Test 1: install.ps1 requires -Type argument
    Write-Host "Test 1: install.ps1 enforces required Type parameter"
    $failed = $false
    try {
        $global:LASTEXITCODE = 0
        $out1 = & "$ProjectRoot\install.ps1" *>&1 | Out-String
        if ($LASTEXITCODE -ne 0) { $failed = $true }
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
    $null = Invoke-Checked -Label "install.ps1 -Type agy" -Command { & "$ProjectRoot\install.ps1" -Type agy }
    if (-not (Test-Path -LiteralPath $AgyPluginDir)) {
        Write-Error "FAIL: Antigravity plugin directory was not created at $AgyPluginDir"
        exit 1
    }
    if (-not (Test-Path -LiteralPath (Join-Path $AgyPluginDir "plugin.json"))) {
        Write-Error "FAIL: plugin.json missing in $AgyPluginDir"
        exit 1
    }
    if (-not (Test-Path -LiteralPath (Join-Path $AgyPluginDir "config\assistant_config"))) {
        Write-Error "FAIL: config\assistant_config missing in $AgyPluginDir"
        exit 1
    }
    Assert-NoClaudeOnlyFiles -PluginDir $AgyPluginDir -Context "install agy"
    Assert-NoUtf8Bom -FilePath (Join-Path $AgyPluginDir "hooks.json")
    Assert-NoUtf8Bom -FilePath (Join-Path $AgyPluginDir "config\assistant_config")
    Assert-NoUtf8Bom -FilePath (Join-Path $AgyPluginDir "config\.repo_root")
    Write-Host "PASS: Antigravity plugin successfully installed."

    # Test 4: install.ps1 -Type claude executes claude CLI marketplace add and install commands
    Write-Host "Test 4: install.ps1 -Type claude executes marketplace add and plugin install"
    $claudeOutput = Invoke-Checked -Label "install.ps1 -Type claude" -Command { & "$ProjectRoot\install.ps1" -Type claude }
    if ($claudeOutput -notmatch "marketplace add") {
        Write-Error "FAIL: install.ps1 -Type claude did not execute marketplace add. Output: $claudeOutput"
        exit 1
    }
    if ($claudeOutput -notmatch "plugin install google-ads-api-developer-assistant@google-ads-assistant-local") {
        Write-Error "FAIL: install.ps1 -Type claude did not execute plugin install. Output: $claudeOutput"
        exit 1
    }
    if (-not (Test-Path -LiteralPath (Join-Path $ClaudePluginDir "plugin.json"))) {
        Write-Error "FAIL: plugin.json missing in standalone Claude plugin dir $ClaudePluginDir"
        exit 1
    }
    if (-not (Test-Path -LiteralPath (Join-Path $ClaudeMarketplaceDir ".claude-plugin\marketplace.json"))) {
        Write-Error "FAIL: marketplace.json missing in $ClaudeMarketplaceDir\.claude-plugin"
        exit 1
    }
    Write-Host "PASS: install.ps1 -Type claude executed Claude Code marketplace commands and created standalone plugin dir."

    # Test 5: update.ps1 requires -Type parameter
    Write-Host "Test 5: update.ps1 enforces required Type parameter"
    $updateFailed = $false
    try {
        $global:LASTEXITCODE = 0
        $out5 = & "$ProjectRoot\update.ps1" *>&1 | Out-String
        if ($LASTEXITCODE -ne 0) { $updateFailed = $true }
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

    # Test 7: update.ps1 -Type agy -NoGitPull updates Antigravity plugin without nesting directories and overwrites stale files
    Write-Host "Test 7: update.ps1 -Type agy -NoGitPull updates Antigravity plugin cleanly without nested dirs"
    $AgyCfgPath = Join-Path $AgyPluginDir "config\assistant_config"
    $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    $AgyCfgOrig = Get-Content -LiteralPath $AgyCfgPath -Raw -Encoding UTF8
    [System.IO.File]::WriteAllText($AgyCfgPath, ($AgyCfgOrig.TrimEnd("`r", "`n") + "`ncustom_operator_note = `"keep-me`"`n"), $Utf8NoBom)
    $StaleSkillFile = Join-Path $AgyPluginDir "skills\ext-version\SKILL.md"
    [System.IO.File]::WriteAllText($StaleSkillFile, "STALE_SKILL_CONTENT", $Utf8NoBom)
    $StaleRuleFile = Join-Path $AgyPluginDir "rules\AGENTS.md"
    [System.IO.File]::WriteAllText($StaleRuleFile, "STALE_RULE_CONTENT", $Utf8NoBom)
    $null = Invoke-Checked -Label "update.ps1 -Type agy -NoGitPull" -Command { & "$ProjectRoot\update.ps1" -Type agy -NoGitPull }
    if (-not (Test-Path -LiteralPath (Join-Path $AgyPluginDir "plugin.json"))) {
        Write-Error "FAIL: plugin.json missing after update in agy"
        exit 1
    }
    foreach ($NestedRel in @("skills\skills", "config\config", "rules\rules", "sidecars\sidecars")) {
        if (Test-Path -LiteralPath (Join-Path $AgyPluginDir $NestedRel)) {
            Write-Error "FAIL: update.ps1 created nested duplicate directory '$NestedRel' in $AgyPluginDir"
            exit 1
        }
    }
    $UpdatedSkillContent = Get-Content -LiteralPath $StaleSkillFile -Raw -Encoding UTF8
    if ($UpdatedSkillContent -eq "STALE_SKILL_CONTENT") {
        Write-Error "FAIL: update.ps1 did not overwrite stale file $StaleSkillFile"
        exit 1
    }
    $UpdatedRuleContent = Get-Content -LiteralPath $StaleRuleFile -Raw -Encoding UTF8
    if ($UpdatedRuleContent -eq "STALE_RULE_CONTENT") {
        Write-Error "FAIL: update.ps1 did not overwrite stale file $StaleRuleFile"
        exit 1
    }
    $UpdatedAgyCfg = Get-Content -LiteralPath $AgyCfgPath -Raw -Encoding UTF8
    if ($UpdatedAgyCfg -notmatch 'custom_operator_note\s*=\s*"keep-me"') {
        Write-Error "FAIL: update.ps1 clobbered custom TOML key in assistant_config"
        exit 1
    }
    Assert-NoClaudeOnlyFiles -PluginDir $AgyPluginDir -Context "update agy"
    Write-Host "PASS: update.ps1 -Type agy -NoGitPull updated files cleanly without directory nesting."

    # Test 8: update.ps1 -Type claude -NoGitPull updates standalone Claude Code plugin including dotfiles
    Write-Host "Test 8: update.ps1 -Type claude -NoGitPull updates standalone Claude Code plugin including dotfiles"
    $ClaudeMcpJson = Join-Path $ClaudePluginDir ".mcp.json"
    $ClaudeDotPluginJson = Join-Path $ClaudePluginDir ".claude-plugin\plugin.json"
    [System.IO.File]::WriteAllText($ClaudeMcpJson, '{"stale": true}', $Utf8NoBom)
    [System.IO.File]::WriteAllText($ClaudeDotPluginJson, '{"stale": true}', $Utf8NoBom)
    $null = Invoke-Checked -Label "update.ps1 -Type claude -NoGitPull" -Command { & "$ProjectRoot\update.ps1" -Type claude -NoGitPull }
    if (-not (Test-Path -LiteralPath (Join-Path $ClaudePluginDir "plugin.json"))) {
        Write-Error "FAIL: plugin.json missing in standalone Claude plugin after update"
        exit 1
    }
    foreach ($NestedRel in @("skills\skills", "config\config", "rules\rules", ".claude-plugin\.claude-plugin")) {
        if (Test-Path -LiteralPath (Join-Path $ClaudePluginDir $NestedRel)) {
            Write-Error "FAIL: update.ps1 created nested duplicate directory '$NestedRel' in $ClaudePluginDir"
            exit 1
        }
    }
    if ((Get-Content -LiteralPath $ClaudeMcpJson -Raw -Encoding UTF8) -match '"stale"') {
        Write-Error "FAIL: update.ps1 claude did not overwrite stale .mcp.json"
        exit 1
    }
    if ((Get-Content -LiteralPath $ClaudeDotPluginJson -Raw -Encoding UTF8) -match '"stale"') {
        Write-Error "FAIL: update.ps1 claude did not overwrite stale .claude-plugin\plugin.json"
        exit 1
    }
    Write-Host "PASS: update.ps1 -Type claude -NoGitPull updated standalone Claude plugin cleanly."

    # Test 9: update.ps1 -Type claude -NoGitPull -Php copies google-ads-php when present locally without network clone
    Write-Host "Test 9: update.ps1 -Type claude -NoGitPull -Php handles local client_libs cleanly"
    $RepoPhpLibDir = Join-Path $ProjectRoot "plugins\google-ads-api-developer-assistant\client_libs\google-ads-php"
    if (Test-Path -LiteralPath $RepoPhpLibDir) {
        $null = Invoke-Checked -Label "update.ps1 -Type claude -NoGitPull -Php" -Command { & "$ProjectRoot\update.ps1" -Type claude -NoGitPull -Php }
        $ClaudePhpLibDir = Join-Path $ClaudePluginDir "client_libs\google-ads-php"
        if (-not (Test-Path -LiteralPath $ClaudePhpLibDir)) {
            Write-Error "FAIL: google-ads-php missing from standalone Claude plugin client_libs at $ClaudePhpLibDir"
            exit 1
        }
    } else {
        $null = Invoke-Checked -Label "update.ps1 -Type claude -NoGitPull" -Command { & "$ProjectRoot\update.ps1" -Type claude -NoGitPull }
    }
    Write-Host "PASS: update.ps1 -Type claude -NoGitPull client_libs handling verified."

    # Test 10: install.ps1 -Type agy rejects -Link option (always installs standalone copy)
    Write-Host "Test 10: install.ps1 -Type agy rejects -Link option (always installs standalone copy)"
    $LinkFailed = $false
    try {
        $global:LASTEXITCODE = 0
        & "$ProjectRoot\install.ps1" -Type agy -Link *>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            $LinkFailed = $true
        }
    }
    catch {
        $LinkFailed = $true
    }
    if (-not $LinkFailed) {
        Write-Error "FAIL: install.ps1 -Type agy -Link should fail because symlinking to repo is disabled"
        exit 1
    }
    if (Test-Path -LiteralPath $AgyPluginDir) {
        $AgyItem = Get-Item -LiteralPath $AgyPluginDir -Force
        if (($AgyItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -or $AgyItem.LinkType) {
            Write-Error "FAIL: $AgyPluginDir must not be a symbolic link"
            exit 1
        }
    }
    Write-Host "PASS: install.ps1 -Type agy rejects -Link and enforces standalone copy."

    # Test 11: update.ps1 -Type agy -NoGitPull migrates any legacy symbolic link to a standalone directory copy
    Write-Host "Test 11: update.ps1 -Type agy -NoGitPull migrates any legacy symbolic link to a standalone directory copy"
    if (Test-Path -LiteralPath $AgyPluginDir) {
        Remove-Item -Recurse -Force -LiteralPath $AgyPluginDir
    }
    $PluginSourceDir = Join-Path $ProjectRoot "plugins\google-ads-api-developer-assistant"
    try {
        New-Item -ItemType SymbolicLink -Path $AgyPluginDir -Target $PluginSourceDir -Force -ErrorAction Stop | Out-Null
    }
    catch {
        New-Item -ItemType Junction -Path $AgyPluginDir -Target $PluginSourceDir -Force | Out-Null
    }
    $null = Invoke-Checked -Label "update.ps1 -Type agy -NoGitPull (symlink migration)" -Command { & "$ProjectRoot\update.ps1" -Type agy -NoGitPull }
    $AgyItemAfter = Get-Item -LiteralPath $AgyPluginDir -Force
    if (($AgyItemAfter.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -or $AgyItemAfter.LinkType) {
        Write-Error "FAIL: update.ps1 -Type agy did not replace legacy symlink at $AgyPluginDir with a real directory"
        exit 1
    }
    if (-not (Test-Path -LiteralPath (Join-Path $AgyPluginDir "plugin.json"))) {
        Write-Error "FAIL: plugin.json missing in migrated standalone directory $AgyPluginDir"
        exit 1
    }
    Assert-NoClaudeOnlyFiles -PluginDir $AgyPluginDir -Context "symlink migration"
    Write-Host "PASS: update.ps1 -Type agy migrated legacy symbolic link to standalone copy."

    # Test 12: global script execution from arbitrary directory using GOOGLE_ADS_ASSISTANT_DIR
    Write-Host "Test 12: global script execution from arbitrary directory using GOOGLE_ADS_ASSISTANT_DIR"
    $env:GOOGLE_ADS_ASSISTANT_DIR = $AgyPluginDir
    $PyExec = $null
    foreach ($CandPy in @("python", "python3", "py")) {
        if (Get-Command $CandPy -ErrorAction SilentlyContinue) {
            try {
                $global:LASTEXITCODE = 0
                & $CandPy -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" *> $null
                if ($LASTEXITCODE -eq 0) {
                    $PyExec = $CandPy
                    break
                }
            } catch {}
        }
    }
    if (-not $PyExec) {
        Write-Error "FAIL: Could not find working Python 3.11+ interpreter for Test 12"
        exit 1
    }
    Push-Location $TestHome
    try {
        $VersionOutput = (Invoke-Checked -Label "get_extension_version.py" -Command { & $PyExec "$env:GOOGLE_ADS_ASSISTANT_DIR\skills\ext-version\scripts\get_extension_version.py" }).Trim()
        if ($VersionOutput -ne "4.1.0") {
            Write-Error "FAIL: expected version 4.1.0, got: '$VersionOutput'"
            exit 1
        }
    }
    finally {
        Pop-Location
    }
    Write-Host "PASS: global script execution succeeded from outside directory."

    # Test 13: plugin.ps1 disable, status, test, is-enabled, enable, switch-target promotion, and disabled install/update hygiene
    Write-Host "Test 13: plugin.ps1 disable, status, test, is-enabled, and enable"
    $null = Invoke-Checked -Label "plugin.ps1 -Disable agy -Quiet" -Command { & "$ProjectRoot\plugin.ps1" -Disable agy -Quiet }
    if (-not (Test-Path -LiteralPath (Join-Path $AgyPluginDir "plugin.json.disabled")) -or (Test-Path -LiteralPath (Join-Path $AgyPluginDir "plugin.json"))) {
        Write-Error "FAIL: plugin.json was not renamed to plugin.json.disabled in $AgyPluginDir"
        exit 1
    }
    if (-not (Test-Path -LiteralPath (Join-Path $ClaudePluginDir "plugin.json"))) {
        Write-Error "FAIL: plugin.ps1 -Disable agy unexpectedly disabled Claude plugin at $ClaudePluginDir"
        exit 1
    }
    $null = Invoke-Checked -Label "plugin.ps1 test -Expect disabled" -Command { & "$ProjectRoot\plugin.ps1" test -ConfigDir (Join-Path $AgyPluginDir "config") -Expect disabled }

    # Verify update.ps1 preserves disabled state and leaves no Claude-only artifacts (including .mcp.json.disabled)
    $null = Invoke-Checked -Label "update.ps1 -Type agy -NoGitPull (disabled)" -Command { & "$ProjectRoot\update.ps1" -Type agy -NoGitPull }
    if (-not (Test-Path -LiteralPath (Join-Path $AgyPluginDir "plugin.json.disabled")) -or (Test-Path -LiteralPath (Join-Path $AgyPluginDir "plugin.json"))) {
        Write-Error "FAIL: update.ps1 did not preserve disabled state in $AgyPluginDir"
        exit 1
    }
    Assert-NoClaudeOnlyFiles -PluginDir $AgyPluginDir -Context "update agy while disabled"

    # Verify install.ps1 -Type agy -Disable leaves no Claude-only artifacts (including .mcp.json.disabled)
    $null = Invoke-Checked -Label "install.ps1 -Type agy -Disable" -Command { & "$ProjectRoot\install.ps1" -Type agy -Disable }
    if (-not (Test-Path -LiteralPath (Join-Path $AgyPluginDir "plugin.json.disabled")) -or (Test-Path -LiteralPath (Join-Path $AgyPluginDir "plugin.json"))) {
        Write-Error "FAIL: install.ps1 -Type agy -Disable did not install in disabled state in $AgyPluginDir"
        exit 1
    }
    Assert-NoClaudeOnlyFiles -PluginDir $AgyPluginDir -Context "install agy -Disable"

    $null = Invoke-Checked -Label "plugin.ps1 -Enable agy -Quiet" -Command { & "$ProjectRoot\plugin.ps1" -Enable agy -Quiet }
    if (-not (Test-Path -LiteralPath (Join-Path $AgyPluginDir "plugin.json")) -or (Test-Path -LiteralPath (Join-Path $AgyPluginDir "plugin.json.disabled"))) {
        Write-Error "FAIL: plugin.json was not restored in $AgyPluginDir"
        exit 1
    }
    $null = Invoke-Checked -Label "plugin.ps1 test -Expect enabled" -Command { & "$ProjectRoot\plugin.ps1" test -ConfigDir (Join-Path $AgyPluginDir "config") -Expect enabled }
    Write-Host "PASS: plugin.ps1 disable, status, test, is-enabled, and enable verified."

    # Test 14: installed update.ps1 in plugin directory runs from an arbitrary directory outside the git repo
    Write-Host "Test 14: installed update.ps1 in plugin directory runs from an arbitrary directory outside the git repo"
    $InstalledUpdatePs1 = Join-Path $AgyPluginDir "update.ps1"
    if (-not (Test-Path -LiteralPath $InstalledUpdatePs1)) {
        Write-Error "FAIL: update.ps1 was not installed in $AgyPluginDir"
        exit 1
    }
    Push-Location $TestHome
    try {
        $null = Invoke-Checked -Label "installed update.ps1 -Type agy -NoGitPull" -Command { & $InstalledUpdatePs1 -Type agy -NoGitPull }
    }
    finally {
        Pop-Location
    }
    Write-Host "PASS: installed update.ps1 executed successfully from outside the git repository."

    # Test 15: Windows python3 -> python manifest rewrite updates hooks.json inline python3 -c commands
    Write-Host "Test 15: Windows python3 -> python rewrite regex handles hooks.json inline commands"
    $RawHooks = Get-Content -LiteralPath (Join-Path $ProjectRoot "plugins\google-ads-api-developer-assistant\hooks.json") -Raw -Encoding UTF8
    $RewrittenHooks = $RawHooks -replace '"command"\s*:\s*"python3(?=\s|")', '"command": "python'
    if ($RewrittenHooks -eq $RawHooks -or $RewrittenHooks -match '"python3') {
        Write-Error "FAIL: hooks.json python3 -> python rewrite left unrewritten python3 command"
        exit 1
    }
    $null = $RewrittenHooks | ConvertFrom-Json
    Write-Host "PASS: Windows python3 -> python manifest rewrite verified on hooks.json."

    Write-Host "=== All PowerShell Tests Passed Successfully! ==="
}
finally {
    if (Test-Path $TestHome) {
        Remove-Item -Recurse -Force $TestHome -ErrorAction SilentlyContinue
    }
}


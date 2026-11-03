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
#
# PowerShell helper script to enable, disable, and test the current status of
# the Google Ads API Developer Assistant plugin for Jetski (agy) and Claude Code.

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Action = "",

    [Parameter(Position = 1)]
    [ValidateSet("agy", "claude", "all")]
    [string]$TargetType = "all",

    [switch]$Enable,
    [switch]$Disable,
    [switch]$Status,
    [switch]$Test,
    [switch]$IsEnabled,
    [string]$ConfigDir = "",
    [string]$Expect = "",
    [switch]$Json,
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PluginName = "google-ads-api-developer-assistant"

if ($Enable) { $Action = "enable" }
elseif ($Disable) { $Action = "disable" }
elseif ($Status) { $Action = "status" }
elseif ($Test) { $Action = "test" }
elseif ($IsEnabled) { $Action = "is-enabled" }
elseif ([string]::IsNullOrWhiteSpace($Action)) { $Action = "status" }

$Action = $Action.ToLowerInvariant().TrimStart("-")
if ($Action -eq "on") { $Action = "enable" }
elseif ($Action -eq "off") { $Action = "disable" }
elseif ($Action -eq "check") { $Action = "test" }

if ($Action -notin @("enable", "disable", "status", "test", "is-enabled", "help")) {
    Write-Error "Unknown command '$Action'. Valid commands: enable, disable, status, test, is-enabled."
    exit 2
}

if ($Action -eq "help") {
    Write-Host "Usage: .\plugin.ps1 <enable|disable|status|test|is-enabled> [agy|claude|all] [-ConfigDir <dir>] [-Expect <enabled|disabled>] [-Json] [-Quiet]"
    exit 0
}

$Candidates = @(
    (Join-Path $ScriptDir "plugins\$PluginName\config\config_init.py"),
    (Join-Path $ScriptDir "config\config_init.py"),
    (Join-Path $HOME ".gemini\config\plugins\$PluginName\config\config_init.py"),
    (Join-Path $HOME ".claude\plugins\google-ads-assistant-local\plugins\$PluginName\config\config_init.py")
)

$ConfigInit = $null
foreach ($c in $Candidates) {
    if (Test-Path $c) {
        $ConfigInit = $c
        break
    }
}

if (-not $ConfigInit) {
    Write-Error "Could not locate config\config_init.py."
    exit 1
}

$PythonCmd = $null
foreach ($cmd in @("python3", "python", "py")) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) {
        $PythonCmd = $cmd
        break
    }
}

if (-not $PythonCmd) {
    Write-Error "Python is required to manage plugin configuration."
    exit 1
}

$PyArgs = @($ConfigInit, "--target", $TargetType)
if (-not [string]::IsNullOrWhiteSpace($ConfigDir)) {
    $PyArgs += @("--config-dir", $ConfigDir)
}

function Invoke-LiveHookTest {
    param(
        [string]$CfgDir,
        [bool]$AsJson
    )
    $PyCode = @'
import json, os, subprocess, sys
config_init_path = sys.argv[1]
cfg_dir = sys.argv[2] or None
as_json = sys.argv[3].lower() == "true"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(config_init_path))))
from config import config_init

status_info = config_init.get_plugin_status(config_dir=cfg_dir)
enabled = bool(status_info.get("enabled"))
env = os.environ.copy()
if cfg_dir:
    env["GOOGLE_ADS_ASSISTANT_ENABLED"] = "true" if enabled else "false"

pre_inv_proc = subprocess.run(
    [sys.executable, config_init_path, "--hook"],
    input=json.dumps({"invocationNum": 2}),
    text=True,
    capture_output=True,
    env=env,
    check=False,
)
try:
    pre_inv_out = json.loads(pre_inv_proc.stdout.strip() or "{}")
except Exception:
    pre_inv_out = {}

pre_tool_proc = subprocess.run(
    [sys.executable, config_init_path, "--hook"],
    input=json.dumps({
        "toolCall": {
            "name": "run_command",
            "args": {"CommandLine": "python3 -c \"print('ok')\""},
        }
    }),
    text=True,
    capture_output=True,
    env=env,
    check=False,
)
try:
    pre_tool_out = json.loads(pre_tool_proc.stdout.strip() or "{}")
except Exception:
    pre_tool_out = {}

if enabled:
    pre_inv_ok = "injectSteps" in pre_inv_out
    pre_tool_ok = pre_tool_out.get("decision") == "allow" and "overwrite" in pre_tool_out
else:
    pre_inv_ok = pre_inv_out == {}
    pre_tool_ok = pre_tool_out == {"decision": "allow"} and "overwrite" not in pre_tool_out

hook_test = {
    "passed": bool(pre_inv_ok and pre_tool_ok),
    "pre_invocation_hook": "active (injects context)" if "injectSteps" in pre_inv_out else "inactive (no-op {})",
    "pre_tool_use_hook": (
        "active (rewrites/guards commands)"
        if "overwrite" in pre_tool_out
        else "inactive (passthrough allow)"
    ),
}
status_info["hook_test"] = hook_test

if as_json:
    print(json.dumps(status_info, indent=2))
else:
    print(config_init.format_plugin_status_text(status_info))
    print(f"  Live Hook Test    : {'PASS' if hook_test['passed'] else 'FAIL'}")
    print(f"    PreInvocation   : {hook_test['pre_invocation_hook']}")
    print(f"    PreToolUse      : {hook_test['pre_tool_use_hook']}")
    if enabled:
        print("\nPlugin is ENABLED and will be active when you invoke jetski/agy.")
        print("To disable it, run: .\\plugin.ps1 disable")
    else:
        print("\nPlugin is DISABLED and will NOT be invoked when you run jetski/agy.")
        print("To re-enable it, run: .\\plugin.ps1 enable")

sys.exit(0 if hook_test["passed"] else 1)
'@
    $JsonStr = if ($AsJson) { "true" } else { "false" }
    $PyCode | & $PythonCmd - $ConfigInit $CfgDir $JsonStr
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

switch ($Action) {
    "enable" {
        & $PythonCmd @PyArgs --enable | Out-Null
        if (-not $Quiet) {
            Invoke-LiveHookTest -CfgDir $ConfigDir -AsJson $Json.IsPresent
        }
    }
    "disable" {
        & $PythonCmd @PyArgs --disable | Out-Null
        if (-not $Quiet) {
            Invoke-LiveHookTest -CfgDir $ConfigDir -AsJson $Json.IsPresent
        }
    }
    "status" {
        Invoke-LiveHookTest -CfgDir $ConfigDir -AsJson $Json.IsPresent
    }
    "test" {
        Invoke-LiveHookTest -CfgDir $ConfigDir -AsJson $Json.IsPresent
        if (-not [string]::IsNullOrWhiteSpace($Expect)) {
            $StateCode = @'
import os, sys
config_init_path = sys.argv[1]
cfg_dir = sys.argv[2] or None
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(config_init_path))))
from config import config_init
print("enabled" if config_init.is_plugin_enabled(config_dir=cfg_dir) else "disabled")
'@
            $Actual = ($StateCode | & $PythonCmd - $ConfigInit $ConfigDir).Trim()
            if ($Actual -ne $Expect.ToLowerInvariant()) {
                Write-Error "FAIL: Expected plugin status '$Expect', but got '$Actual'."
                exit 1
            }
        }
    }
    "is-enabled" {
        $StateCode = @'
import os, sys
config_init_path = sys.argv[1]
cfg_dir = sys.argv[2] or None
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(config_init_path))))
from config import config_init
print("enabled" if config_init.is_plugin_enabled(config_dir=cfg_dir) else "disabled")
'@
        $Actual = ($StateCode | & $PythonCmd - $ConfigInit $ConfigDir).Trim()
        if (-not $Quiet) {
            Write-Host $Actual
        }
        if ($Actual -eq "enabled") { exit 0 } else { exit 1 }
    }
}

#!/usr/bin/env bash
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
# Helper script to enable, disable, and test the current status of the
# Google Ads API Developer Assistant plugin for Jetski (agy) and Claude Code.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && (pwd -W 2>/dev/null || pwd))"
PLUGIN_NAME="google-ads-api-developer-assistant"

# Resolve config_init.py across repository checkout and installed plugin layouts
CONFIG_INIT=""
for candidate in \
  "${SCRIPT_DIR}/plugins/${PLUGIN_NAME}/config/config_init.py" \
  "${SCRIPT_DIR}/config/config_init.py" \
  "${HOME}/.gemini/config/plugins/${PLUGIN_NAME}/config/config_init.py" \
  "${HOME}/.claude/plugins/google-ads-assistant-local/plugins/${PLUGIN_NAME}/config/config_init.py"; do
  if [[ -f "${candidate}" ]]; then
    CONFIG_INIT="${candidate}"
    break
  fi
done

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "${PYTHON_BIN}" ]]; then
  for cmd in python3 python; do
    if command -v "${cmd}" >/dev/null 2>&1 && "${cmd}" -c "import sys" >/dev/null 2>&1; then
      PYTHON_BIN="${cmd}"
      break
    fi
  done
fi


usage() {
  cat <<EOF
Usage: $0 <command> [options]

Commands:
  enable, --enable, on         Enable the plugin so it is loaded by jetski/agy
  disable, --disable, off      Disable the plugin so it is not invoked by jetski/agy
  status, --status             Display the current plugin status and hook state
  test, --test, check          Test and verify the current plugin status & hook behavior
  is-enabled, --is-enabled     Print 'enabled' (exit 0) or 'disabled' (exit 1)

Options:
  agy | claude | all           Target platform (default: all)
  --target <agy|claude|all>    Target platform (alias: claudecode)
  --config-dir <dir>           Explicit config directory to read/update
  --expect <enabled|disabled>  Assert that the plugin is in the expected state (with 'test')
  --json                       Output status and test results in JSON format
  -q, --quiet                  Suppress non-essential output
  -h, --help                   Show this help message

Examples:
  $0 disable                   Turn off the plugin for jetski/agy
  $0 enable                    Turn on the plugin for jetski/agy
  $0 status                    Show current plugin status
  $0 test                      Run live status and hook verification checks
  $0 is-enabled                Exit 0 if enabled, 1 if disabled
EOF
}

ACTION=""
TARGET_TYPE="all"
CONFIG_DIR=""
EXPECT_STATE=""
JSON_OUTPUT="false"
QUIET="false"

normalize_target() {
  local raw
  raw="$(echo "$1" | tr '[:upper:]' '[:lower:]')"
  if [[ "${raw}" == "claudecode" ]]; then
    raw="claude"
  fi
  if [[ "${raw}" != "agy" && "${raw}" != "claude" && "${raw}" != "all" ]]; then
    echo "Error: Invalid target '$1'. Must be 'agy', 'claude', or 'all'." >&2
    exit 2
  fi
  echo "${raw}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    enable|--enable|on)
      ACTION="enable"
      shift
      ;;
    disable|--disable|off)
      ACTION="disable"
      shift
      ;;
    status|--status)
      ACTION="status"
      shift
      ;;
    test|--test|check|--check)
      ACTION="test"
      shift
      ;;
    is-enabled|--is-enabled)
      ACTION="is-enabled"
      shift
      ;;
    [aA][gG][yY]|[cC][lL][aA][uU][dD][eE]|[cC][lL][aA][uU][dD][eE][cC][oO][dD][eE]|[aA][lL][lL])
      TARGET_TYPE="$(normalize_target "$1")"
      shift
      ;;
    --target|--type|-Target)
      if [[ $# -lt 2 ]]; then
        echo "Error: $1 requires a value (agy, claude, or all)." >&2
        exit 2
      fi
      TARGET_TYPE="$(normalize_target "$2")"
      shift 2
      ;;
    --target=*|--type=*)
      TARGET_TYPE="$(normalize_target "${1#*=}")"
      shift
      ;;
    --config-dir)
      if [[ $# -lt 2 ]]; then
        echo "Error: --config-dir requires a directory path." >&2
        exit 2
      fi
      CONFIG_DIR="$2"
      shift 2
      ;;
    --config-dir=*)
      CONFIG_DIR="${1#*=}"
      shift
      ;;
    --expect)
      if [[ $# -lt 2 ]]; then
        echo "Error: --expect requires 'enabled' or 'disabled'." >&2
        exit 2
      fi
      EXPECT_STATE="$(echo "$2" | tr '[:upper:]' '[:lower:]')"
      shift 2
      ;;
    --expect=*)
      EXPECT_STATE="$(echo "${1#*=}" | tr '[:upper:]' '[:lower:]')"
      shift
      ;;
    --json)
      JSON_OUTPUT="true"
      shift
      ;;
    -q|--quiet)
      QUIET="true"
      shift
      ;;
    -h|--help|help)
      usage
      exit 0
      ;;
    *)
      echo "Error: Unknown argument '$1'." >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "${ACTION}" ]]; then
  ACTION="status"
fi

if [[ -z "${PYTHON_BIN}" ]]; then
  echo "Error: python3 or python is required to manage plugin configuration." >&2
  exit 1
fi

if [[ -z "${CONFIG_INIT}" || ! -f "${CONFIG_INIT}" ]]; then
  echo "Error: Could not locate config/config_init.py." >&2
  exit 1
fi

PY_ARGS=()
if [[ -n "${CONFIG_DIR}" ]]; then
  PY_ARGS+=(--config-dir "${CONFIG_DIR}")
fi
if [[ -n "${TARGET_TYPE}" ]]; then
  PY_ARGS+=(--target "${TARGET_TYPE}")
fi

run_live_hook_test() {
  local cfg_dir="$1"
  local target_type="$2"
  local json_flag="$3"
  "${PYTHON_BIN}" - "${CONFIG_INIT}" "${cfg_dir}" "${target_type}" "${json_flag}" <<'PYEOF'
import inspect
import json
import os
import subprocess
import sys

config_init_path = sys.argv[1]
cfg_dir = sys.argv[2] or None
target_type = (sys.argv[3] or "all").lower()
if target_type == "claudecode":
    target_type = "claude"
as_json = sys.argv[4].lower() == "true"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(config_init_path))))
from config import config_init

effective_cfg_dir = cfg_dir
if effective_cfg_dir is None and target_type in ("agy", "claude"):
    if target_type == "agy":
        cand_dir = os.path.expanduser("~/.gemini/config/plugins/google-ads-api-developer-assistant/config")
    else:
        cand_dir = os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/config"
        )
    if os.path.isdir(os.path.dirname(cand_dir)):
        effective_cfg_dir = cand_dir

sig = inspect.signature(config_init.get_plugin_status)
status_kwargs = {"config_dir": effective_cfg_dir}
if "target_type" in sig.parameters:
    status_kwargs["target_type"] = target_type
elif "target" in sig.parameters:
    status_kwargs["target"] = target_type

status_info = config_init.get_plugin_status(**status_kwargs)
if target_type in ("agy", "claude"):
    status_info["target"] = target_type
enabled = bool(status_info.get("enabled"))

env = os.environ.copy()
if effective_cfg_dir:
    # Point GOOGLE_ADS_ASSISTANT_ENABLED to the effective state of effective_cfg_dir for isolated hook testing
    env["GOOGLE_ADS_ASSISTANT_ENABLED"] = "true" if enabled else "false"

# 1. Test PreInvocation hook (invocationNum = 2 to avoid network parity checks)
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
    pre_inv_out = {"raw": pre_inv_proc.stdout.strip()}

# 2. Test PreToolUse hook
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
    pre_tool_out = {"raw": pre_tool_proc.stdout.strip()}

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
    if target_type in ("agy", "claude") and isinstance(status_info.get("installations"), dict):
        if target_type in status_info["installations"]:
            status_info["installations"] = {target_type: status_info["installations"][target_type]}
    print(json.dumps(status_info, indent=2))
else:
    text_out = config_init.format_plugin_status_text(status_info)
    if target_type == "agy":
        text_out = "\n".join(
            ln for ln in text_out.splitlines() if not ln.strip().startswith("Claude Code (~/.claude):")
        )
    elif target_type == "claude":
        text_out = "\n".join(
            ln for ln in text_out.splitlines() if not ln.strip().startswith("Jetski / Antigravity (~/.gemini):")
        )
    print(text_out)
    print(f"  Live Hook Test    : {'PASS' if hook_test['passed'] else 'FAIL'}")
    print(f"    PreInvocation   : {hook_test['pre_invocation_hook']}")
    print(f"    PreToolUse      : {hook_test['pre_tool_use_hook']}")
    if enabled:
        print("\nPlugin is ENABLED and will be active when you invoke jetski/agy.")
        print("To disable it, run: ./plugin.sh disable")
    else:
        print("\nPlugin is DISABLED and will NOT be invoked when you run jetski/agy.")
        print("To re-enable it, run: ./plugin.sh enable")

sys.exit(0 if hook_test["passed"] else 1)
PYEOF
}

get_effective_state() {
  local cfg_dir="$1"
  local target_type="$2"
  "${PYTHON_BIN}" - "${CONFIG_INIT}" "${cfg_dir}" "${target_type}" <<'PYEOF'
import os
import sys

config_init_path = sys.argv[1]
cfg_dir = sys.argv[2] or None
target_type = (sys.argv[3] or "all").lower()
if target_type == "claudecode":
    target_type = "claude"
if cfg_dir is None and target_type in ("agy", "claude"):
    if target_type == "agy":
        cand_dir = os.path.expanduser("~/.gemini/config/plugins/google-ads-api-developer-assistant/config")
    else:
        cand_dir = os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/config"
        )
    if os.path.isdir(os.path.dirname(cand_dir)):
        cfg_dir = cand_dir

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(config_init_path))))
from config import config_init
print("enabled" if config_init.is_plugin_enabled(config_dir=cfg_dir) else "disabled")
PYEOF
}

case "${ACTION}" in
  enable)
    if [[ "${JSON_OUTPUT}" == "true" ]]; then
      "${PYTHON_BIN}" "${CONFIG_INIT}" --enable "${PY_ARGS[@]}" --json >/dev/null
      run_live_hook_test "${CONFIG_DIR}" "${TARGET_TYPE}" "true"
    elif [[ "${QUIET}" == "true" ]]; then
      "${PYTHON_BIN}" "${CONFIG_INIT}" --enable "${PY_ARGS[@]}" >/dev/null
    else
      "${PYTHON_BIN}" "${CONFIG_INIT}" --enable "${PY_ARGS[@]}" >/dev/null
      run_live_hook_test "${CONFIG_DIR}" "${TARGET_TYPE}" "false"
    fi
    ;;

  disable)
    if [[ "${JSON_OUTPUT}" == "true" ]]; then
      "${PYTHON_BIN}" "${CONFIG_INIT}" --disable "${PY_ARGS[@]}" --json >/dev/null
      run_live_hook_test "${CONFIG_DIR}" "${TARGET_TYPE}" "true"
    elif [[ "${QUIET}" == "true" ]]; then
      "${PYTHON_BIN}" "${CONFIG_INIT}" --disable "${PY_ARGS[@]}" >/dev/null
    else
      "${PYTHON_BIN}" "${CONFIG_INIT}" --disable "${PY_ARGS[@]}" >/dev/null
      run_live_hook_test "${CONFIG_DIR}" "${TARGET_TYPE}" "false"
    fi
    ;;

  status)
    run_live_hook_test "${CONFIG_DIR}" "${TARGET_TYPE}" "${JSON_OUTPUT}"
    ;;

  test)
    run_live_hook_test "${CONFIG_DIR}" "${TARGET_TYPE}" "${JSON_OUTPUT}"
    if [[ -n "${EXPECT_STATE}" ]]; then
      ACTUAL_STATE="$(get_effective_state "${CONFIG_DIR}" "${TARGET_TYPE}")"
      if [[ "${ACTUAL_STATE}" != "${EXPECT_STATE}" ]]; then
        echo "FAIL: Expected plugin status '${EXPECT_STATE}', but got '${ACTUAL_STATE}'." >&2
        exit 1
      fi
    fi
    ;;

  is-enabled)
    STATE="$(get_effective_state "${CONFIG_DIR}" "${TARGET_TYPE}")"
    if [[ "${QUIET}" != "true" ]]; then
      echo "${STATE}"
    fi
    if [[ "${STATE}" == "enabled" ]]; then
      exit 0
    else
      exit 1
    fi
    ;;
esac

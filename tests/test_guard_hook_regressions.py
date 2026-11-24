# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Regression tests for the HITL guard hook on Antigravity (agy) and Claude Code.

Covers: --reject/--dry-run shortcut bypasses, per-CLI PreToolUse output contracts,
Claude Code plugin layout (hooks/hooks.json, .mcp.json, .claude-plugin/plugin.json),
shell writes to protected files, PostToolUseFailure audit semantics, fail-closed hook
commands, API version validation/resolution, config lookup order, and the strict
allow_tier1_financial_mutates parser.
"""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Optional

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_DIR = REPO_ROOT / "plugins" / "google-ads-api-developer-assistant"
sys.path.insert(0, str(PLUGIN_DIR))

from config import config_init  # noqa: E402

RM = "python3 skills/execute-mutation/scripts/run_mutation.py"
LIVE_SCRIPT_BODY = (
    "from google.ads.googleads.client import GoogleAdsClient\n"
    "client = GoogleAdsClient.load_from_storage(path='config/google-ads.yaml')\n"
    "svc = client.get_service('CampaignService')\n"
    "svc.mutate_campaigns(customer_id='1234567890', operations=[op])\n"
)


def _load_run_mutation_module() -> Any:
    script_path = PLUGIN_DIR / "skills" / "execute-mutation" / "scripts" / "run_mutation.py"
    spec = spec_from_file_location("run_mutation_guard_regressions", str(script_path))
    assert spec is not None and spec.loader is not None
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated workspace with a live-mutation script, mutations disabled, no real config."""
    (tmp_path / "saved" / "code").mkdir(parents=True)
    (tmp_path / "saved" / "data").mkdir(parents=True)
    (tmp_path / "saved" / "logs").mkdir(parents=True)
    (tmp_path / "saved" / "code" / "live.py").write_text(LIVE_SCRIPT_BODY, encoding="utf-8")
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    (cfg_dir / "assistant_config").write_text(
        'api_version = "v24"\ncustomer_id = "12345678"\nexecute_mutates = false\nenabled = true\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GOOGLE_ADS_ASSISTANT_CONFIG_DIR", str(cfg_dir))
    monkeypatch.setenv("GOOGLE_ADS_EXECUTE_MUTATES", "false")
    monkeypatch.setenv("GOOGLE_ADS_ASSISTANT_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_ADS_MUTATION_RECEIPT_PATH", str(tmp_path / "saved" / "data" / "last_dry_run.json"))
    monkeypatch.setenv("GOOGLE_ADS_MUTATION_AUDIT_LOG", str(tmp_path / "saved" / "logs" / "mutation_audit.jsonl"))
    for var in ("CLAUDE_PLUGIN_ROOT", "CLAUDE_CODE", "CLAUDECODE", "CLAUDE_ENV_FILE", "GOOGLE_ADS_API_VERSION"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(
        config_init, "sync_and_set_config_kv", lambda *a, **kw: str(tmp_path / "google-ads.yaml")
    )
    return tmp_path


# --- Payload builders for both CLIs -------------------------------------------------------


def _agy_shell(cmd: str, cwd: Optional[str] = None) -> dict[str, Any]:
    args: dict[str, Any] = {"CommandLine": cmd}
    if cwd:
        args["Cwd"] = cwd
    return {"conversationId": "agy-conv", "toolCall": {"name": "run_command", "args": args}}


def _claude_shell(cmd: str, cwd: Optional[str] = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "session_id": "claude-s1",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": cmd, "description": "test"},
    }
    if cwd:
        payload["cwd"] = cwd
    return payload


def _agy_write(tool: str, target: str) -> dict[str, Any]:
    return {"toolCall": {"name": tool, "args": {"TargetFile": target, "CodeContent": "x"}}}


def _claude_write(tool: str, target: str) -> dict[str, Any]:
    tool_input: dict[str, Any] = {"file_path": target}
    if tool == "Write":
        tool_input["content"] = "x"
    elif tool == "Edit":
        tool_input.update({"old_string": "a", "new_string": "b"})
    else:
        tool_input["edits"] = [{"old_string": "a", "new_string": "b"}]
    return {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input}


def _run_hook(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], payload: Any
) -> tuple[dict[str, Any], int, str]:
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    capsys.readouterr()
    rc = config_init.handle_hook()
    captured = capsys.readouterr()
    return json.loads(captured.out), rc, captured.err


def _assert_claude_shape(out: dict[str, Any]) -> None:
    """Claude Code output must be {} or only hookSpecificOutput (no agy keys)."""
    assert set(out) <= {"hookSpecificOutput"}
    if out:
        assert out["hookSpecificOutput"]["hookEventName"] == "PreToolUse"


def _assert_agy_shape(out: dict[str, Any]) -> None:
    assert "hookSpecificOutput" not in out
    assert out["decision"] in ("allow", "deny", "force_ask")


# --- Finding 1: --reject / --dry-run shortcut bypasses ------------------------------------

BYPASS_COMMANDS = [
    "python3 saved/code/live.py",
    "python3 saved/code/live.py # run_mutation.py --reject",
    "python3 saved/code/live.py # run_mutation.py --dry-run",
    f"{RM} --reject && python3 saved/code/live.py",
    f"{RM} --reject ; python3 saved/code/live.py",
    f"{RM} --reject | python3 saved/code/live.py",
    f"{RM} --reject || python3 saved/code/live.py",
    f"{RM} --reject & python3 saved/code/live.py",
    f"{RM} --reject $(python3 saved/code/live.py)",
    f"{RM} --reject `python3 saved/code/live.py`",
    f"{RM} --reject\npython3 saved/code/live.py",
    f"{RM} --dry-run --script x; python3 saved/code/live.py",
    f"{RM} --dry-run --script saved/code/live.py && python3 saved/code/live.py",
    "python3 saved/code/live.py --reject",
    "python3 saved/code/live.py --dry-run",
]


@pytest.mark.parametrize("cmd", BYPASS_COMMANDS)
def test_shortcut_bypass_repros_are_denied(workspace: Path, cmd: str) -> None:
    decision, reason = config_init.evaluate_mutation_guard(cmd, workspace_cwd=str(workspace))
    assert decision == "deny", (cmd, reason)


def test_lookalike_run_mutation_is_not_a_shortcut(workspace: Path) -> None:
    fake = workspace / "skills" / "execute-mutation" / "scripts"
    fake.mkdir(parents=True)
    (fake / "run_mutation.py").write_text(LIVE_SCRIPT_BODY, encoding="utf-8")
    decision, _ = config_init.evaluate_mutation_guard(
        f"{RM} --reject", workspace_cwd=str(workspace)
    )
    assert decision == "deny"


def test_gads_dir_reassignment_is_not_trusted(workspace: Path) -> None:
    pre = config_init._GADS_DIR_PREAMBLE_LITERAL
    cmd = f'{pre}; GADS_DIR=saved; python3 "$GADS_DIR/skills/execute-mutation/scripts/run_mutation.py" --reject'
    decision, _ = config_init.evaluate_mutation_guard(cmd, workspace_cwd=str(workspace))
    assert decision != "allow"


SAFE_SHORTCUTS = [
    f"{RM} --reject",
    f"{RM} --reject --rejection-reason 'user said no'",
    f"{RM} --dry-run --script saved/code/live.py --customer-id 1234567890 2>&1",
    f"{RM} --dry-run --script saved/code/live.py > saved/dry_run_output.txt",
    f"cd /tmp && {RM} --dry-run --script saved/code/live.py",
    f"{RM} --dry-run --script saved/code/live.py | tail -n 20",
    f'{config_init._GADS_DIR_PREAMBLE_LITERAL}\npython3 "$GADS_DIR/skills/execute-mutation/scripts/run_mutation.py" --dry-run --script saved/code/live.py',
    f'{config_init._GADS_DIR_PREAMBLE_LITERAL} && python3 "${{GADS_DIR}}/skills/execute-mutation/scripts/run_mutation.py" --reject',
]


@pytest.mark.parametrize("cmd", SAFE_SHORTCUTS)
def test_safe_run_mutation_shortcuts_still_allowed(workspace: Path, cmd: str) -> None:
    decision, reason = config_init.evaluate_mutation_guard(cmd, workspace_cwd=str(workspace))
    assert decision == "allow", (cmd, reason)


@pytest.mark.parametrize(
    "extra",
    [
        "--operation 'Remove Campaign 111'",
        "--operation 'Update campaign' --after 'status=REMOVED'",
    ],
)
def test_dry_run_shortcut_still_enforces_deletion_prohibition(workspace: Path, extra: str) -> None:
    (workspace / "saved" / "code" / "remove.py").write_text(
        "op.remove = 'customers/1/campaigns/2'\nsvc.mutate_campaigns(customer_id='1', operations=[op])\n",
        encoding="utf-8",
    )
    decision, reason = config_init.evaluate_mutation_guard(
        f"{RM} --dry-run --script saved/code/remove.py {extra}", workspace_cwd=str(workspace)
    )
    assert decision == "deny" and "DELETION" in (reason or "").upper()


def _write_receipt_with_rpc(workspace: Path, payload: dict[str, Any]) -> Path:
    rm = _load_run_mutation_module()
    rm.write_dry_run_receipt(
        customer_id="1234567890",
        operation_summary="CampaignService.mutate_campaigns",
        before_state="None",
        after_state="Campaign created",
        consequences=["Zero spend impact."],
        reversibility="REVERSIBLE",
        script_path=str(workspace / "saved" / "code" / "live.py"),
        rpc_calls=[{"service": "CampaignService", "method": "mutate_campaigns", "request_payload": payload}],
    )
    return workspace / "saved" / "data" / "last_dry_run.json"


def test_masked_payload_uses_recorded_hash(workspace: Path) -> None:
    payload = {"customer_id": "1234567890", "operations": [{"create": {"name": "owner@example.com"}}]}
    receipt_path = _write_receipt_with_rpc(workspace, payload)
    data = json.loads(receipt_path.read_text(encoding="utf-8"))
    call = data["dry_run_rpc_calls"][0]
    if not call.get("request_sha256"):
        pytest.skip("run_mutation does not record per-call request_sha256")
    # run_mutation already masks emails on storage and sets the flag; clear it so
    # the first step exercises an unmarked (tampered) payload.
    call.pop("request_payload_masked", None)
    call["request_payload"] = {"customer_id": "1234567890", "operations": [{"create": {"name": "o***@example.com"}}]}
    receipt_path.write_text(json.dumps(data), encoding="utf-8")
    ok, msg, _ = config_init._verify_dry_run_receipt_for_hook(
        script_path="saved/code/live.py", workspace_cwd=str(workspace)
    )
    assert not ok and "SHA-256 mismatch" in msg  # unmarked tampering is still caught
    call["request_payload_masked"] = True
    receipt_path.write_text(json.dumps(data), encoding="utf-8")
    ok, msg, _ = config_init._verify_dry_run_receipt_for_hook(
        script_path="saved/code/live.py", workspace_cwd=str(workspace)
    )
    assert "SHA-256 mismatch" not in msg


def test_payload_customer_id_mismatch_blocks_execute(workspace: Path) -> None:
    receipt_path = _write_receipt_with_rpc(workspace, {"customer_id": "1234567890", "operations": []})
    data = json.loads(receipt_path.read_text(encoding="utf-8"))
    data["payload_bound_facts"] = {"customer_id_mismatch": True, "payload_customer_ids": ["999"]}
    receipt_path.write_text(json.dumps(data), encoding="utf-8")
    ok, msg, _ = config_init._verify_dry_run_receipt_for_hook(
        script_path="saved/code/live.py", workspace_cwd=str(workspace)
    )
    assert not ok and "does not match --customer-id" in msg


def test_shortcut_rejects_execute_and_record_only_tokens(workspace: Path) -> None:
    assert config_init._run_mutation_shortcut_flag(f"{RM} --reject --execute", str(workspace)) is None
    assert config_init._run_mutation_shortcut_flag(f"{RM} --dry-run --record-only", str(workspace)) is None
    assert config_init._run_mutation_shortcut_flag(f"python3 -c 'x' {RM} --reject", str(workspace)) is None
    assert config_init._run_mutation_shortcut_flag(f"PYTHONPATH=evil {RM} --reject", str(workspace)) is None
    assert config_init._run_mutation_shortcut_flag(f"{RM} --reject", str(workspace)) == "--reject"


# --- Findings 2 and 12: per-CLI PreToolUse output contracts -------------------------------


@pytest.mark.parametrize("cli", ["agy", "claude"])
@pytest.mark.parametrize(
    "cmd",
    [
        f"{RM} --reject && python3 saved/code/live.py",
        "python3 saved/code/live.py # run_mutation.py --reject",
        f"{RM} --reject\npython3 saved/code/live.py",
    ],
)
def test_hook_denies_bypass_with_cli_specific_shape(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], cli: str, cmd: str
) -> None:
    payload = _agy_shell(cmd, str(workspace)) if cli == "agy" else _claude_shell(cmd, str(workspace))
    out, rc, err = _run_hook(monkeypatch, capsys, payload)
    if cli == "agy":
        _assert_agy_shape(out)
        assert out["decision"] == "deny" and rc == 0
        assert "BLOCKED BY HITL MUTATION GUARD" in out["reason"]
    else:
        _assert_claude_shape(out)
        hso = out["hookSpecificOutput"]
        assert hso["permissionDecision"] == "deny"
        assert "BLOCKED BY HITL MUTATION GUARD" in hso["permissionDecisionReason"]
        assert rc == 2 and "BLOCKED BY HITL MUTATION GUARD" in err


@pytest.mark.parametrize("cli", ["agy", "claude"])
def test_hook_force_ask_maps_to_claude_ask(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], cli: str
) -> None:
    cmd = "sed -i 's/false/true/' config/assistant_config"
    payload = _agy_shell(cmd) if cli == "agy" else _claude_shell(cmd)
    out, rc, _ = _run_hook(monkeypatch, capsys, payload)
    assert rc == 0
    if cli == "agy":
        _assert_agy_shape(out)
        assert out["decision"] == "force_ask"
    else:
        _assert_claude_shape(out)
        assert out["hookSpecificOutput"]["permissionDecision"] == "ask"


@pytest.mark.parametrize("cli", ["agy", "claude"])
def test_hook_rewrite_shape_without_auto_approval(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], cli: str
) -> None:
    cmd = "python3 skills/validate-gaql/scripts/validate_gaql.py --customer_id 1234567890"
    payload = _agy_shell(cmd) if cli == "agy" else _claude_shell(cmd)
    out, rc, _ = _run_hook(monkeypatch, capsys, payload)
    assert rc == 0
    if cli == "agy":
        _assert_agy_shape(out)
        assert out["decision"] == "allow"
        assert "export GOOGLE_ADS_ASSISTANT_DIR=" in out["overwrite"]["CommandLine"]
    else:
        _assert_claude_shape(out)
        hso = out["hookSpecificOutput"]
        # No auto-approval: Claude Code's own permission rules still apply.
        assert "permissionDecision" not in hso
        assert "export GOOGLE_ADS_ASSISTANT_DIR=" in hso["updatedInput"]["command"]
        assert hso["updatedInput"]["description"] == "test"


def test_claude_allow_without_rewrite_emits_empty_object(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    out, rc, _ = _run_hook(monkeypatch, capsys, _claude_shell("ls -la"))
    assert out == {} and rc == 0


def test_main_exits_2_on_claude_deny(workspace: Path) -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = ""
    proc = subprocess.run(
        [sys.executable, str(PLUGIN_DIR / "config" / "config_init.py"), "--hook"],
        input=json.dumps(_claude_shell(f"{RM} --reject && python3 saved/code/live.py", str(workspace))),
        capture_output=True,
        text=True,
        env=env,
        cwd=str(workspace),
        timeout=60,
        check=False,
    )
    assert proc.returncode == 2, proc.stderr
    assert json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "BLOCKED BY HITL MUTATION GUARD" in proc.stderr


@pytest.mark.parametrize(
    "payload,expected_agy,expected_claude",
    [
        (lambda t: _agy_write("write_to_file", t), "deny", None),
        (lambda t: _agy_write("replace_file_content", t), "deny", None),
        (lambda t: _agy_write("multi_replace_file_content", t), "deny", None),
        (lambda t: _claude_write("Write", t), None, "deny"),
        (lambda t: _claude_write("Edit", t), None, "deny"),
        (lambda t: _claude_write("MultiEdit", t), None, "deny"),
    ],
)
def test_file_write_tools_to_receipt_are_denied(
    workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    payload: Any,
    expected_agy: Optional[str],
    expected_claude: Optional[str],
) -> None:
    out, rc, _ = _run_hook(monkeypatch, capsys, payload(str(workspace / "saved" / "data" / "last_dry_run.json")))
    if expected_agy:
        _assert_agy_shape(out)
        assert out["decision"] == expected_agy
    else:
        _assert_claude_shape(out)
        assert out["hookSpecificOutput"]["permissionDecision"] == expected_claude
        assert rc == 2


@pytest.mark.parametrize("tool", ["Write", "Edit", "MultiEdit"])
def test_claude_file_write_to_config_asks(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tool: str
) -> None:
    out, rc, _ = _run_hook(monkeypatch, capsys, _claude_write(tool, str(workspace / "cfg" / "assistant_config")))
    _assert_claude_shape(out)
    assert out["hookSpecificOutput"]["permissionDecision"] == "ask" and rc == 0


@pytest.mark.parametrize("tool", ["write_to_file", "replace_file_content"])
def test_agy_file_write_to_config_asks(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tool: str
) -> None:
    out, _, _ = _run_hook(monkeypatch, capsys, _agy_write(tool, str(workspace / "cfg" / "financial_limits")))
    _assert_agy_shape(out)
    assert out["decision"] == "force_ask"


def test_malformed_payload_denied_for_both_clis(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    out, rc, _ = _run_hook(monkeypatch, capsys, '["toolCall"]')
    assert out["decision"] == "deny" and rc == 0
    out, rc, _ = _run_hook(monkeypatch, capsys, '["tool_input"]')
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny" and rc == 2


# --- Finding 5: shell writes to protected files -------------------------------------------


@pytest.mark.parametrize(
    "cmd,expected",
    [
        ("sed -i 's/false/true/' config/assistant_config", "force_ask"),
        ("sed --in-place 's/a/b/' config/financial_limits", "force_ask"),
        ("echo 'allow_tier1_financial_mutates = true' >> config/assistant_config", "force_ask"),
        ("echo 'execute_mutates = true' > ~/.gemini/config/plugins/google-ads-api-developer-assistant/config/assistant_config", "force_ask"),
        ("echo x | tee -a config/financial_limits", "force_ask"),
        ("cp /tmp/evil config/assistant_config", "force_ask"),
        ("mv /tmp/evil config/google-ads.yaml", "force_ask"),
        ("perl -pi -e 's/false/true/' hooks.json", "force_ask"),
        ("python3 -c \"open('config/assistant_config','a').write('execute_mutates = true')\"", "force_ask"),
        ("python3 -c \"import pathlib; pathlib.Path('config/financial_limits').write_text('')\"", "force_ask"),
        ("echo '{}' > saved/data/last_dry_run.json", "deny"),
        ("cp /tmp/x saved/data/last_dry_run.json", "deny"),
        ("truncate -s 0 saved/logs/mutation_audit.jsonl", "deny"),
        ("rm saved/logs/mutation_audit.jsonl", "deny"),
        ("python3 -c \"open('saved/data/last_dry_run.json','w').write('{}')\"", "deny"),
    ],
)
def test_shell_writes_to_protected_files(workspace: Path, cmd: str, expected: str) -> None:
    decision, _ = config_init.evaluate_mutation_guard(cmd, workspace_cwd=str(workspace))
    assert decision == expected, cmd


@pytest.mark.parametrize(
    "cmd",
    [
        "cat config/assistant_config",
        "grep api_version config/assistant_config",
        "tail -n 5 saved/logs/mutation_audit.jsonl 2>&1",
        "python3 -c \"import json;print(json.load(open('saved/data/last_dry_run.json'))['status'])\"",
        "python3 set_financial_limits.py --show",
    ],
)
def test_reads_of_protected_files_are_not_flagged(workspace: Path, cmd: str) -> None:
    assert config_init._protected_shell_write_decision(cmd) is None


# --- Finding 6: PostToolUseFailure logs EXECUTE_FAILED, not HUMAN_REJECTED ----------------


def _write_receipt(workspace: Path) -> Path:
    rm = _load_run_mutation_module()
    rm.write_dry_run_receipt(
        customer_id="1234567890",
        operation_summary="CampaignLabelService.mutate_campaign_labels",
        before_state="No label",
        after_state="Label attached",
        consequences=["Zero spend impact."],
        reversibility="REVERSIBLE",
        script_path=str(workspace / "saved" / "code" / "live.py"),
    )
    receipt = workspace / "saved" / "data" / "last_dry_run.json"
    assert receipt.is_file()
    return receipt


def _audit_statuses(workspace: Path) -> list[str]:
    log = workspace / "saved" / "logs" / "mutation_audit.jsonl"
    if not log.is_file():
        return []
    return [json.loads(line)["status"] for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_post_tool_use_failure_logs_execute_failed(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    receipt = _write_receipt(workspace)
    payload = {
        "session_id": "claude-s1",
        "hook_event_name": "PostToolUseFailure",
        "tool_name": "Bash",
        "tool_input": {"command": f"{RM} --script saved/code/live.py --execute"},
        "error": "google.ads.googleads.errors.GoogleAdsException: INTERNAL_ERROR",
        "cwd": str(workspace),
    }
    out, rc, _ = _run_hook(monkeypatch, capsys, payload)
    assert out == {} and rc == 0
    statuses = _audit_statuses(workspace)
    assert "EXECUTE_FAILED" in statuses
    assert "HUMAN_REJECTED" not in statuses
    assert json.loads(receipt.read_text(encoding="utf-8"))["status"] != "REJECTED"
    entry = json.loads((workspace / "saved" / "logs" / "mutation_audit.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert "INTERNAL_ERROR" in json.dumps(entry)


@pytest.mark.parametrize(
    "cmd",
    [
        "python3 other.py --execute",
        f"{RM} --dry-run --script saved/code/live.py ; python3 x.py --execute",
        "ls -la",
    ],
)
def test_post_tool_use_failure_requires_run_mutation_execute_in_same_segment(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], cmd: str
) -> None:
    payload = {"hook_event_name": "PostToolUseFailure", "tool_name": "Bash", "tool_input": {"command": cmd}, "error": "boom"}
    out, rc, _ = _run_hook(monkeypatch, capsys, payload)
    assert out == {} and rc == 0
    assert _audit_statuses(workspace) == []


# --- Findings 3 and 23: Claude Code plugin layout and fail-closed hook commands -----------


def test_claude_hooks_json_layout() -> None:
    data = json.loads((PLUGIN_DIR / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    hooks = data["hooks"]
    assert set(hooks) == {"SessionStart", "PreToolUse", "PostToolUseFailure"}
    matchers = {entry.get("matcher") for entry in hooks["PreToolUse"]}
    assert matchers == {"Bash", "Write|Edit|MultiEdit"}
    assert hooks["PostToolUseFailure"][0]["matcher"] == "Bash"
    for event_entries in hooks.values():
        for entry in event_entries:
            for hook in entry["hooks"]:
                assert hook["type"] == "command"
                assert "${CLAUDE_PLUGIN_ROOT}/config/config_init.py" in hook["command"]
                assert "exit 2" in hook["command"]
                assert "py -3" in hook["command"]
                assert "enabled" not in hook


def test_antigravity_hooks_json_has_no_post_tool_use_failure() -> None:
    """Antigravity never fires PostToolUseFailure (verified 2026-11-24: failed run_command
    calls arrive as PostToolUse with an empty "error"), so the agy manifest must not
    register it."""
    data = json.loads((PLUGIN_DIR / "hooks.json").read_text(encoding="utf-8"))
    events = data["config-init"]
    assert "PostToolUseFailure" not in events
    assert {"PreToolUse", "SessionStart", "PreInvocation"} <= set(events)


def test_claude_mcp_and_manifest_layout() -> None:
    mcp = json.loads((PLUGIN_DIR / ".mcp.json").read_text(encoding="utf-8"))
    server = mcp["mcpServers"]["google-ads-api-assistant"]
    assert server["args"][0] == "${CLAUDE_PLUGIN_ROOT}/sidecars/google-ads-a2a-service/server.py"
    assert server["env"]["GOOGLE_ADS_CONFIGURATION_FILE_PATH"].startswith("${CLAUDE_PLUGIN_ROOT}/")
    manifest = json.loads((PLUGIN_DIR / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    root_manifest = json.loads((PLUGIN_DIR / "plugin.json").read_text(encoding="utf-8"))
    market = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert manifest["name"] == root_manifest["name"] == market["plugins"][0]["name"]
    assert manifest["version"] == root_manifest["version"] == market["plugins"][0]["version"]
    assert "hooks" not in manifest and "mcpServers" not in manifest


def _agy_hook_commands() -> list[str]:
    data = json.loads((PLUGIN_DIR / "hooks.json").read_text(encoding="utf-8"))
    cmds: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "command" and isinstance(v, str):
                    cmds.append(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return cmds


def test_agy_hooks_have_no_cwd_relative_fallback() -> None:
    cmds = _agy_hook_commands()
    assert cmds
    for cmd in cmds:
        assert "'plugins/google-ads-api-developer-assistant/config/config_init.py'" not in cmd
        assert "'decision':'deny'" in cmd


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell required")
@pytest.mark.parametrize(
    "stdin_payload,expected",
    [
        ({"toolCall": {"name": "run_command", "args": {"CommandLine": "python3 x.py"}}}, "deny"),
        ({"invocationNum": 1}, "{}"),
    ],
)
def test_agy_hook_fails_closed_when_script_missing(tmp_path: Path, stdin_payload: dict[str, Any], expected: str) -> None:
    cmd = _agy_hook_commands()[0]
    planted = tmp_path / "plugins" / "google-ads-api-developer-assistant" / "config"
    planted.mkdir(parents=True)
    (planted / "config_init.py").write_text("print('{\"decision\": \"allow\"}')\n", encoding="utf-8")
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(tmp_path / "nohome")}
    proc = subprocess.run(
        ["bash", "-c", cmd], input=json.dumps(stdin_payload), capture_output=True, text=True,
        env=env, cwd=str(tmp_path), timeout=60, check=False,
    )
    if expected == "deny":
        assert json.loads(proc.stdout)["decision"] == "deny"
    else:
        assert proc.stdout.strip() == "{}"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell required")
def test_claude_hook_fails_closed_when_script_missing(tmp_path: Path) -> None:
    data = json.loads((PLUGIN_DIR / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    cmd = data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    env = {"PATH": os.environ.get("PATH", ""), "CLAUDE_PLUGIN_ROOT": str(tmp_path / "missing")}
    proc = subprocess.run(
        ["bash", "-c", cmd], input=json.dumps(_claude_shell("python3 x.py")), capture_output=True,
        text=True, env=env, timeout=60, check=False,
    )
    assert proc.returncode == 2
    assert "config_init.py not found" in proc.stderr


# --- Finding 35: SessionStart context and CLAUDE_ENV_FILE ---------------------------------


def test_claude_session_start_sets_context_and_env_file(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    env_file = workspace / "claude_env.sh"
    monkeypatch.setenv("CLAUDE_ENV_FILE", str(env_file))
    monkeypatch.setattr(config_init, "check_python_client_lib_parity", lambda **kw: {"api_version": "v24"})
    payload = {"session_id": "claude-s1", "hook_event_name": "SessionStart", "source": "startup"}
    out, rc, _ = _run_hook(monkeypatch, capsys, payload)
    assert rc == 0
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "HITL MUTATION" in out["hookSpecificOutput"]["additionalContext"]
    env_text = env_file.read_text(encoding="utf-8")
    assert "export GOOGLE_ADS_ASSISTANT_DIR=" in env_text
    assert "export GOOGLE_ADS_CONFIGURATION_FILE_PATH=" in env_text


def test_agy_pre_invocation_keeps_inject_steps(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(config_init, "check_python_client_lib_parity", lambda **kw: {"api_version": "v24"})
    out, rc, _ = _run_hook(monkeypatch, capsys, {"conversationId": "agy-conv", "invocationNum": 1})
    assert rc == 0 and "ephemeralMessage" in out["injectSteps"][0]


# --- Finding 27: no config sync for file writes or non-Ads commands ------------------------


def test_sync_skipped_for_file_writes_and_non_ads_commands(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[int] = []
    monkeypatch.setattr(config_init, "sync_and_set_config_kv", lambda *a, **kw: calls.append(1) or "x.yaml")
    _run_hook(monkeypatch, capsys, _claude_write("Write", str(workspace / "notes.md")))
    _run_hook(monkeypatch, capsys, _agy_shell("ls -la"))
    _run_hook(monkeypatch, capsys, _claude_shell("git status"))
    assert calls == []
    _run_hook(monkeypatch, capsys, _claude_shell("python3 skills/validate-gaql/scripts/validate_gaql.py"))
    assert calls == [1]


# --- Skill path rewrite: rooted paths pass through unmodified ------------------------------


@pytest.mark.parametrize(
    "path",
    [
        '"$GADS_DIR/skills/inspect-object/scripts/inspect_object.py"',
        '"${CLAUDE_PLUGIN_ROOT}/skills/inspect-object/scripts/inspect_object.py"',
        "/abs/plugin/skills/inspect-object/scripts/inspect_object.py",
        "~/x/skills/inspect-object/scripts/inspect_object.py",
    ],
)
def test_skill_rel_path_regex_ignores_rooted_paths(path: str) -> None:
    assert config_init._SKILL_REL_PATH_RE.search(path) is None


def test_skill_rel_path_regex_matches_bare_relative() -> None:
    assert config_init._SKILL_REL_PATH_RE.search("python3 skills/inspect-object/scripts/inspect_object.py")


def test_gads_dir_command_passes_through_rewrite(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pre = config_init._GADS_DIR_PREAMBLE_LITERAL
    script = '"$GADS_DIR/skills/validate-gaql/scripts/validate_gaql.py" --customer_id 1'
    out, _, _ = _run_hook(monkeypatch, capsys, _agy_shell(f"{pre}\npython3 {script}"))
    assert out["decision"] == "allow"
    assert f"python3 {script}" in out["overwrite"]["CommandLine"]
    assert "//" not in out["overwrite"]["CommandLine"].split("python3 ", 1)[1]


# --- Findings 10/16/24: API version validation, resolution, and config lookup order --------


@pytest.mark.parametrize("value,expected", [("v24", "v24"), (" 23 ", "v23"), ("v024", "v24")])
def test_validate_api_version_accepts(value: str, expected: str) -> None:
    assert config_init.validate_api_version(value) == expected


@pytest.mark.parametrize("value", ["latest", "../../x", "v24beta", "", "v", "24.1", "v24/../x"])
def test_validate_api_version_rejects(value: str) -> None:
    with pytest.raises(ValueError):
        config_init.validate_api_version(value)


def test_resolve_active_api_version_order(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_init, "_detect_installed_api_version", lambda: "v26")
    assert config_init.resolve_active_api_version("25") == "v25"
    assert config_init.resolve_active_api_version() == "v24"  # from assistant_config
    monkeypatch.setenv("GOOGLE_ADS_API_VERSION", "22")
    assert config_init.resolve_active_api_version() == "v22"
    monkeypatch.setenv("GOOGLE_ADS_API_VERSION", "latest")
    with pytest.raises(ValueError):
        config_init.resolve_active_api_version()
    with pytest.raises(ValueError):
        config_init.resolve_active_api_version("../../x")


def test_resolve_skips_invalid_config_and_raises_when_nothing_found(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (workspace / "cfg" / "assistant_config").write_text('api_version = "latest"\n', encoding="utf-8")
    monkeypatch.setattr(config_init, "get_assistant_config_paths", lambda **kw: [str(workspace / "cfg" / "assistant_config")])
    monkeypatch.setattr(config_init, "_detect_installed_api_version", lambda: "v26")
    assert config_init.resolve_active_api_version() == "v26"
    monkeypatch.setattr(config_init, "_detect_installed_api_version", lambda: "")
    with pytest.raises(ValueError, match="pass --api_version vN"):
        config_init.resolve_active_api_version()


def test_detect_latest_ignores_invalid_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_init, "_detect_installed_api_version", lambda: "")
    monkeypatch.setenv("GOOGLE_ADS_API_VERSION", "../../x")
    assert config_init.detect_latest_api_version() == ""
    monkeypatch.setenv("GOOGLE_ADS_API_VERSION", "25")
    assert config_init.detect_latest_api_version() == "v25"


def test_invalid_api_version_never_persisted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_init, "detect_latest_api_version", lambda: "v26")
    assert config_init.parse_assistant_config('api_version = "../../x"\n').get("api_version") is None
    text = config_init.format_assistant_config({"api_version": "latest"})
    assert 'api_version = "v26"' in text
    cfg_dir = tmp_path / "cfg"
    config_init.write_assistant_config({"api_version": "../evil"}, config_dir=str(cfg_dir))
    assert "evil" not in (cfg_dir / "assistant_config").read_text(encoding="utf-8")


def test_config_lookup_prefers_claude_plugin_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_ADS_ASSISTANT_CONFIG_DIR", raising=False)
    root = tmp_path / "claude_root"
    (root / "config").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(root))
    paths = config_init.get_assistant_config_paths()
    assert paths[0] == os.path.normpath(str(root / "config" / "assistant_config"))
    claude_idx = next(i for i, p in enumerate(paths) if "/.claude/" in p)
    gemini_idx = next(i for i, p in enumerate(paths) if "/.gemini/" in p)
    assert claude_idx < gemini_idx
    this_cfg = os.path.normpath(str(PLUGIN_DIR / "config" / "assistant_config"))
    cwd_cfg = os.path.normpath(os.path.abspath(os.path.join("config", "assistant_config")))
    if this_cfg != cwd_cfg:
        assert paths.index(this_cfg) < paths.index(cwd_cfg)


# --- Finding 17: strict allow_tier1_financial_mutates parser -------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ('execute_mutates = false\n"true"\n', None),
        ("customer_id = \"1\"\ntrue\n", None),
        ("[section]\nallow_tier1_financial_mutates = true\n", None),
        ("allow_tier1_financial_mutates = true\n", True),
        ("allow_tier1_financial_mutates = false\n", False),
        ("true", True),
        ("false", False),
        ("maybe", None),
    ],
)
def test_allow_tier1_parser_uses_only_top_level_key(text: str, expected: Optional[bool]) -> None:
    assert config_init.parse_allow_tier1_financial_mutates_value(text) is expected

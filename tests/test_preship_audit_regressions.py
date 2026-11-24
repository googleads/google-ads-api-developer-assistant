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

"""Pre-ship audit regression tests covering P0/P1/P2/P3 fixes across agy and Claude Code CLI."""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "google-ads-api-developer-assistant"
CONFIG_DIR = PLUGIN_ROOT / "config"
HOOK_GUARD_PATH = CONFIG_DIR / "hook_guard.py"
CONFIG_INIT_PATH = CONFIG_DIR / "config_init.py"
RUN_MUTATION_PATH = PLUGIN_ROOT / "skills" / "execute-mutation" / "scripts" / "run_mutation.py"
SERVER_PATH = PLUGIN_ROOT / "sidecars" / "google-ads-a2a-service" / "server.py"
SYNC_LIBS_PATH = PLUGIN_ROOT / "skills" / "sync-client-libs" / "scripts" / "sync_client_libs.py"
GET_CIDS_PATH = PLUGIN_ROOT / "skills" / "get-cids-under-mcc" / "scripts" / "get_cids_under_mcc.py"


def _load_isolated(path: Path, mod_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(mod_name, str(path))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    prev = sys.modules.get(mod_name)
    sys.modules[mod_name] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        if prev is None:
            sys.modules.pop(mod_name, None)
        else:
            sys.modules[mod_name] = prev
    return mod


@pytest.fixture(name="hg")
def fixture_hg() -> Any:
    return _load_isolated(HOOK_GUARD_PATH, "hook_guard_preship_test")


@pytest.fixture(name="ci")
def fixture_ci() -> Any:
    return _load_isolated(CONFIG_INIT_PATH, "config_init_preship_test")


@pytest.fixture(name="rm")
def fixture_rm() -> Any:
    return _load_isolated(RUN_MUTATION_PATH, "run_mutation_preship_test")


@pytest.fixture(name="srv")
def fixture_srv() -> Any:
    return _load_isolated(SERVER_PATH, "server_preship_test")


@pytest.fixture(name="isolated_env")
def fixture_isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "saved" / "code").mkdir(parents=True)
    (tmp_path / "saved" / "data").mkdir(parents=True)
    (tmp_path / "saved" / "logs").mkdir(parents=True)
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "assistant_config").write_text(
        'api_version = "v24"\ncustomer_id = "1234567890"\nexecute_mutates = false\n'
        "allow_tier1_financial_mutates = false\nenabled = true\n",
        encoding="utf-8",
    )
    (cfg / "financial_limits").write_text(
        "CampaignBudgetService.amount_micros = 50000000\n"
        "AdGroupService.cpc_bid_micros = 5000000\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("GOOGLE_ADS_ASSISTANT_CONFIG_DIR", str(cfg))
    monkeypatch.setenv("GOOGLE_ADS_MUTATION_RECEIPT_PATH", str(tmp_path / "saved" / "data" / "last_dry_run.json"))
    monkeypatch.setenv("GOOGLE_ADS_MUTATION_AUDIT_LOG", str(tmp_path / "saved" / "logs" / "mutation_audit.jsonl"))
    monkeypatch.setenv("GOOGLE_ADS_FINANCIAL_LIMITS_FILE", str(cfg / "financial_limits"))
    monkeypatch.setenv("GOOGLE_ADS_ASSISTANT_ENABLED", "true")
    monkeypatch.delenv("GOOGLE_ADS_EXECUTE_MUTATES", raising=False)
    monkeypatch.delenv("GOOGLE_ADS_ALLOW_TIER1_FINANCIAL_MUTATES", raising=False)
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.delenv("CLAUDE_CODE", raising=False)
    return tmp_path


class TestHookGuardUnitAndContracts:
    """Exercises hook_guard.py fast path, MCP interception, file-write protection, and fail-closed behavior."""

    def test_fast_enabled_env_and_file_checks(
        self, hg: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GOOGLE_ADS_ASSISTANT_ENABLED", "true")
        assert hg._fast_is_plugin_enabled() is True
        monkeypatch.setenv("GOOGLE_ADS_ASSISTANT_ENABLED", "false")
        assert hg._fast_is_plugin_enabled() is False

        monkeypatch.delenv("GOOGLE_ADS_ASSISTANT_ENABLED", raising=False)
        custom_root = tmp_path / "custom_plugin"
        (custom_root / "config").mkdir(parents=True)
        (custom_root / "config" / "assistant_config").write_text("enabled = false\n", encoding="utf-8")
        monkeypatch.setenv("PLUGIN_ROOT", str(custom_root))
        monkeypatch.delenv("GOOGLE_ADS_ASSISTANT_CONFIG_DIR", raising=False)
        assert hg._fast_is_plugin_enabled() is False
        (custom_root / "config" / "assistant_config").write_text("enabled = true\n", encoding="utf-8")
        assert hg._fast_is_plugin_enabled() is True

    def test_strict_bool_and_path_helpers(self, hg: Any, tmp_path: Path) -> None:
        assert hg._strict_bool(True) is True
        assert hg._strict_bool("true") is True
        assert hg._strict_bool("FALSE") is False
        assert hg._strict_bool(1) is False

        ok_script = tmp_path / "saved" / "code" / "demo.py"
        ok_script.parent.mkdir(parents=True)
        ok_script.write_text("pass\n", encoding="utf-8")
        assert hg._is_path_in_saved_code(str(ok_script)) is True
        assert hg._is_path_in_saved_code(str(tmp_path / "outside.py")) is False
        assert hg._is_path_in_saved_code(str(tmp_path / "saved" / "code" / "notes.txt")) is False

    @pytest.mark.parametrize(
        "tool_name,args,expected_tool",
        [
            ("call_mcp_tool", {"ServerName": "google-ads-api-assistant", "ToolName": "execute_mutation", "Arguments": {"user_confirmed": True}}, "execute_mutation"),
            ("call_mcp_tool", {"server_name": "google_ads_api_assistant", "tool_name": "create_campaign", "arguments": {"execute": True}}, "create_campaign"),
            ("call_mcp_tool", {"ServerName": "other-server", "ToolName": "execute_mutation", "Arguments": {}}, None),
            ("mcp__google-ads-api-assistant__prepare_mutation", {"script_path": "x.py"}, "prepare_mutation"),
            ("mcp__other-server__prepare_mutation", {}, None),
            ("mcp_google-ads-api-assistant_create_ad", {"execute": True}, "create_ad"),
            ("run_command", {"CommandLine": "ls"}, None),
        ],
    )
    def test_extract_mcp_call_variants(
        self, hg: Any, tool_name: str, args: dict[str, Any], expected_tool: Any
    ) -> None:
        res = hg._extract_mcp_call(tool_name, args)
        if expected_tool is None:
            assert res is None
        else:
            assert res is not None and res[0] == expected_tool

    def test_fail_closed_on_empty_malformed_nondict_and_exceptions(
        self, hg: Any, isolated_env: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Empty stdin on PreToolUse -> deny (agy and claude)
        rc = hg.handle_fast_hook(explicit_event="PreToolUse", explicit_cli="agy", raw_stdin="")
        assert rc == 0
        assert json.loads(capsys.readouterr().out)["decision"] == "deny"

        rc = hg.handle_fast_hook(explicit_event="PreToolUse", explicit_cli="claude", raw_stdin="")
        assert rc == 2
        assert json.loads(capsys.readouterr().out)["hookSpecificOutput"]["permissionDecision"] == "deny"

        # Malformed JSON on PreToolUse -> deny
        rc = hg.handle_fast_hook(explicit_event="PreToolUse", explicit_cli="agy", raw_stdin="{bad")
        assert rc == 0 and json.loads(capsys.readouterr().out)["decision"] == "deny"

        # Malformed JSON on SessionStart -> {}
        rc = hg.handle_fast_hook(explicit_event="SessionStart", explicit_cli="agy", raw_stdin="{bad")
        assert rc == 0 and capsys.readouterr().out.strip() == "{}"

        # Non-dict JSON on PreToolUse -> deny; on SessionStart -> {}
        rc = hg.handle_fast_hook(explicit_event="PreToolUse", explicit_cli="claude", raw_stdin="[]")
        assert rc == 2 and json.loads(capsys.readouterr().out)["hookSpecificOutput"]["permissionDecision"] == "deny"
        rc = hg.handle_fast_hook(explicit_event="SessionStart", explicit_cli="agy", raw_stdin="[]")
        assert rc == 0 and capsys.readouterr().out.strip() == "{}"

        # main() catches internal exceptions and fails closed on PreToolUse
        monkeypatch.setattr(hg, "handle_fast_hook", MagicMock(side_effect=RuntimeError("boom")))
        with pytest.raises(SystemExit) as exc:
            hg.main(["--event=PreToolUse", "--cli=claude"])
        assert exc.value.code == 2
        assert json.loads(capsys.readouterr().out)["hookSpecificOutput"]["permissionDecision"] == "deny"

        hg.main(["--event", "SessionStart", "--cli", "agy", "--ignored"])
        assert capsys.readouterr().out.strip() == "{}"

    def test_file_write_protection_agy_write_file_edit_file_and_symlinks(
        self, hg: Any, isolated_env: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # P0-2 & P0-8: agy write_file / edit_file with Path argument
        for tool in ("write_file", "edit_file"):
            payload = {"toolCall": {"name": tool, "args": {"Path": "saved/data/last_dry_run.json"}}}
            rc = hg.handle_fast_hook(explicit_event="PreToolUse", explicit_cli="agy", raw_stdin=json.dumps(payload))
            assert rc == 0 and json.loads(capsys.readouterr().out)["decision"] == "deny"

        for protected in (
            "config/assistant_config",
            "config/config_init.py",
            "config/hook_guard.py",
            "skills/execute-mutation/scripts/run_mutation.py",
            "sidecars/google-ads-a2a-service/server.py",
            "mcp_config.json",
            ".mcp.json",
            "sidecar.json",
            "plugin.json",
        ):
            payload = {"toolCall": {"name": "edit_file", "args": {"Path": protected}}}
            rc = hg.handle_fast_hook(explicit_event="PreToolUse", explicit_cli="agy", raw_stdin=json.dumps(payload))
            assert rc == 0 and json.loads(capsys.readouterr().out)["decision"] == "force_ask", protected

        # Symlink to last_dry_run.json must also be denied
        real_receipt = isolated_env / "saved" / "data" / "last_dry_run.json"
        real_receipt.write_text("{}", encoding="utf-8")
        sym_receipt = isolated_env / "innocent_link.txt"
        sym_receipt.symlink_to(real_receipt)
        payload = {"toolCall": {"name": "write_file", "args": {"Path": str(sym_receipt)}}}
        rc = hg.handle_fast_hook(explicit_event="PreToolUse", explicit_cli="agy", raw_stdin=json.dumps(payload))
        assert rc == 0 and json.loads(capsys.readouterr().out)["decision"] == "deny"

        # Normal file write is allowed (fast path)
        payload = {"toolCall": {"name": "write_file", "args": {"Path": "saved/code/helper.py"}}}
        rc = hg.handle_fast_hook(explicit_event="PreToolUse", explicit_cli="agy", raw_stdin=json.dumps(payload))
        assert rc == 0 and json.loads(capsys.readouterr().out)["decision"] == "allow"

    def test_mcp_pretooluse_guards_agy_and_claude(
        self, hg: Any, isolated_env: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Non-mutation MCP tool -> allow
        payload = {
            "toolCall": {
                "name": "call_mcp_tool",
                "args": {"ServerName": "google-ads-api-assistant", "ToolName": "gaql_validate", "Arguments": {"query": "SELECT campaign.id FROM campaign"}},
            }
        }
        rc = hg.handle_fast_hook(explicit_event="PreToolUse", explicit_cli="agy", raw_stdin=json.dumps(payload))
        assert rc == 0 and json.loads(capsys.readouterr().out)["decision"] == "allow"

        # prepare_mutation outside saved/code -> deny
        bad_prep = {
            "tool_name": "mcp__google-ads-api-assistant__prepare_mutation",
            "tool_input": {"script_path": "/tmp/evil.py", "operation_summary": "Update"},
        }
        rc = hg.handle_fast_hook(explicit_event="PreToolUse", explicit_cli="claude", raw_stdin=json.dumps(bad_prep))
        assert rc == 2 and json.loads(capsys.readouterr().out)["hookSpecificOutput"]["permissionDecision"] == "deny"

        # prepare_mutation with deletion text -> deny
        del_prep = {
            "tool_name": "mcp__google-ads-api-assistant__prepare_mutation",
            "tool_input": {"script_path": str(isolated_env / "saved" / "code" / "x.py"), "operation_summary": "Remove campaign 1"},
        }
        rc = hg.handle_fast_hook(explicit_event="PreToolUse", explicit_cli="claude", raw_stdin=json.dumps(del_prep))
        assert rc == 2 and "DELETION PROHIBITION" in json.loads(capsys.readouterr().out)["hookSpecificOutput"]["permissionDecisionReason"]

        # prepare_mutation benign in saved/code -> allow ({} for claude)
        ok_prep = {
            "tool_name": "mcp__google-ads-api-assistant__prepare_mutation",
            "tool_input": {"script_path": str(isolated_env / "saved" / "code" / "x.py"), "operation_summary": "Pause campaign 1"},
        }
        rc = hg.handle_fast_hook(explicit_event="PreToolUse", explicit_cli="claude", raw_stdin=json.dumps(ok_prep))
        assert rc == 0 and capsys.readouterr().out.strip() == "{}"

        # create_campaign status=REMOVED -> deny
        rem_camp = {
            "toolCall": {
                "name": "call_mcp_tool",
                "args": {"ServerName": "google-ads-api-assistant", "ToolName": "create_campaign", "Arguments": {"customer_id": "123", "status": "REMOVED"}},
            }
        }
        rc = hg.handle_fast_hook(explicit_event="PreToolUse", explicit_cli="agy", raw_stdin=json.dumps(rem_camp))
        assert rc == 0 and json.loads(capsys.readouterr().out)["decision"] == "deny"

        # create_campaign dry-run -> allow
        dry_camp = {
            "toolCall": {
                "name": "call_mcp_tool",
                "args": {"ServerName": "google-ads-api-assistant", "ToolName": "create_campaign", "Arguments": {"customer_id": "123", "validate_only": True}},
            }
        }
        rc = hg.handle_fast_hook(explicit_event="PreToolUse", explicit_cli="agy", raw_stdin=json.dumps(dry_camp))
        assert rc == 0 and json.loads(capsys.readouterr().out)["decision"] == "allow"

        # create_campaign live with execute_mutates=false -> deny
        live_camp = {
            "tool_name": "mcp__google-ads-api-assistant__create_campaign",
            "tool_input": {"customer_id": "123", "execute": True, "user_confirmed": True},
        }
        rc = hg.handle_fast_hook(explicit_event="PreToolUse", explicit_cli="claude", raw_stdin=json.dumps(live_camp))
        assert rc == 2 and json.loads(capsys.readouterr().out)["hookSpecificOutput"]["permissionDecision"] == "deny"

        # create_campaign live with execute_mutates=true but Tier 1 disabled -> deny
        monkeypatch.setenv("GOOGLE_ADS_EXECUTE_MUTATES", "true")
        rc = hg.handle_fast_hook(explicit_event="PreToolUse", explicit_cli="claude", raw_stdin=json.dumps(live_camp))
        assert rc == 2 and "TIER 1" in json.loads(capsys.readouterr().out)["hookSpecificOutput"]["permissionDecisionReason"]

        # create_campaign live with Tier 1 enabled -> ask (claude) / force_ask (agy)
        monkeypatch.setenv("GOOGLE_ADS_ALLOW_TIER1_FINANCIAL_MUTATES", "true")
        rc = hg.handle_fast_hook(explicit_event="PreToolUse", explicit_cli="claude", raw_stdin=json.dumps(live_camp))
        assert rc == 0 and json.loads(capsys.readouterr().out)["hookSpecificOutput"]["permissionDecision"] == "ask"

        # execute_mutation outside saved/code -> deny; disabled -> deny; missing receipt -> deny
        bad_exec = {"tool_name": "mcp__google-ads-api-assistant__execute_mutation", "tool_input": {"script_path": "/tmp/a.py"}}
        rc = hg.handle_fast_hook(explicit_event="PreToolUse", explicit_cli="claude", raw_stdin=json.dumps(bad_exec))
        assert rc == 2 and json.loads(capsys.readouterr().out)["hookSpecificOutput"]["permissionDecision"] == "deny"

        monkeypatch.setenv("GOOGLE_ADS_EXECUTE_MUTATES", "false")
        ok_sp = str(isolated_env / "saved" / "code" / "a.py")
        (isolated_env / "saved" / "code" / "a.py").write_text("pass\n", encoding="utf-8")
        exec_call = {"tool_name": "mcp__google-ads-api-assistant__execute_mutation", "tool_input": {"script_path": ok_sp}}
        rc = hg.handle_fast_hook(explicit_event="PreToolUse", explicit_cli="claude", raw_stdin=json.dumps(exec_call))
        assert rc == 2 and json.loads(capsys.readouterr().out)["hookSpecificOutput"]["permissionDecision"] == "deny"

        monkeypatch.setenv("GOOGLE_ADS_EXECUTE_MUTATES", "true")
        rc = hg.handle_fast_hook(explicit_event="PreToolUse", explicit_cli="claude", raw_stdin=json.dumps(exec_call))
        assert rc == 2 and json.loads(capsys.readouterr().out)["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_fast_shell_allow_disabled_passthrough_and_delegation(
        self, hg: Any, isolated_env: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Benign shell -> allow without loading config_init
        rc = hg.handle_fast_hook(
            explicit_event="PreToolUse",
            explicit_cli="agy",
            raw_stdin=json.dumps({"toolCall": {"name": "run_command", "args": {"CommandLine": "git status"}}}),
        )
        assert rc == 0 and json.loads(capsys.readouterr().out)["decision"] == "allow"

        # Disabled plugin -> passthrough
        monkeypatch.setenv("GOOGLE_ADS_ASSISTANT_ENABLED", "false")
        rc = hg.handle_fast_hook(
            explicit_event="PreToolUse",
            explicit_cli="agy",
            raw_stdin=json.dumps({"toolCall": {"name": "run_command", "args": {"CommandLine": "python3 x.py"}}}),
        )
        assert rc == 0 and json.loads(capsys.readouterr().out)["decision"] == "allow"
        rc = hg.handle_fast_hook(
            explicit_event="PreToolUse",
            explicit_cli="claude",
            raw_stdin=json.dumps({"tool_name": "Bash", "tool_input": {"command": "python3 x.py"}}),
        )
        assert rc == 0 and capsys.readouterr().out.strip() == "{}"

        # Enabled + SessionStart delegates to config_init
        monkeypatch.setenv("GOOGLE_ADS_ASSISTANT_ENABLED", "true")
        rc = hg.handle_fast_hook(
            explicit_event="SessionStart",
            explicit_cli="claude",
            raw_stdin=json.dumps({"hook_event_name": "SessionStart", "session_id": "s-fast-1"}),
        )
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        assert "Google Ads API Developer Assistant" in out["hookSpecificOutput"]["additionalContext"]


class TestP0BypassAndSecurityRegressions:
    """Verifies all P0 bypass vectors (P0-4..P0-9) and P1/P2 fixes are blocked."""

    @pytest.mark.parametrize(
        "cmd",
        [
            "python3 config/config_init.py --execute-mutates true",
            "python3 config/config_init.py --execute-mut=true",
            "python3 config/config_init.py --allow-tier1-financial-mutates true",
            "python3 config/config_init.py --allow-tier1 true",
            "python3 config/config_init.py --disable",
            "python3 config/config_init.py --plugin-enabled false",
            "python3 config/config_init.py --key execute_mutates --value true",
        ],
    )
    def test_p0_4_config_init_self_elevation_requires_force_ask(
        self, ci: Any, isolated_env: Path, cmd: str
    ) -> None:
        dec, reason = ci.evaluate_mutation_guard(cmd, workspace_cwd=str(isolated_env))
        assert dec == "force_ask", (cmd, dec, reason)

    def test_p0_5_p0_6_exec_target_and_abbreviated_execute_blocked(
        self, ci: Any, rm: Any, isolated_env: Path
    ) -> None:
        script = isolated_env / "saved" / "code" / "mut.py"
        script.write_text("print('mut')\n", encoding="utf-8")

        # PreToolUse denies --_exec-target and --exec abbreviations
        for bad_cmd in (
            f"python3 skills/execute-mutation/scripts/run_mutation.py --_exec-target {script} --dry-run",
            f"python3 skills/execute-mutation/scripts/run_mutation.py --script {script} --exec",
            f"python3 skills/execute-mutation/scripts/run_mutation.py --script {script} --ex",
        ):
            dec, _ = ci.evaluate_mutation_guard(bad_cmd, workspace_cwd=str(isolated_env))
            assert dec == "deny", bad_cmd

        # Direct run_mutation.py rejects --_exec-target without a valid single-use nonce token
        proc = subprocess.run(
            [sys.executable, str(RUN_MUTATION_PATH), "--_exec-target", str(script), "--dry-run"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert proc.returncode == 2
        assert "Direct invocation of --_exec-target is prohibited" in proc.stderr

        # Direct run_mutation.py rejects abbreviated --exec due to allow_abbrev=False
        proc2 = subprocess.run(
            [sys.executable, str(RUN_MUTATION_PATH), "--script", str(script), "--exec"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert proc2.returncode == 2

        # Direct config_init.py rejects abbreviated --execute-mut due to allow_abbrev=False
        proc3 = subprocess.run(
            [sys.executable, str(CONFIG_INIT_PATH), "--execute-mut", "true"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert proc3.returncode == 2

    def test_p0_8_ast_validate_only_decoy_multi_py_var_indirection_and_extensionless(
        self, ci: Any, isolated_env: Path
    ) -> None:
        # 1. Decoy validate_only = True cannot bypass guard when actual mutate lacks validate_only=True
        decoy = isolated_env / "saved" / "code" / "decoy.py"
        decoy.write_text(
            "validate_only = True\n"
            "svc.mutate_campaigns(customer_id='123', operations=[])\n",
            encoding="utf-8",
        )
        dec, _ = ci.evaluate_mutation_guard(f"python3 {decoy}", workspace_cwd=str(isolated_env))
        assert dec == "deny"

        # Genuine AST-verified validate_only=True on every mutate call is allowed
        genuine = isolated_env / "saved" / "code" / "genuine.py"
        genuine.write_text(
            "svc.mutate_campaigns(customer_id='123', operations=[], validate_only=True)\n",
            encoding="utf-8",
        )
        dec_ok, _ = ci.evaluate_mutation_guard(f"python3 {genuine}", workspace_cwd=str(isolated_env))
        assert dec_ok == "allow"

        # 2. Multi-.py chaining with live mutation is denied
        dec_chain, _ = ci.evaluate_mutation_guard(
            f"python3 {genuine} && python3 {decoy}", workspace_cwd=str(isolated_env)
        )
        assert dec_chain == "deny"

        # 3. Path(...).open("w") and env-var indirection writes to protected files -> force_ask / deny
        dec_open, _ = ci.evaluate_mutation_guard(
            "python3 -c \"from pathlib import Path; Path('config/assistant_config').open('w').write('x')\"",
            workspace_cwd=str(isolated_env),
        )
        assert dec_open == "force_ask"

        dec_var_cfg, _ = ci.evaluate_mutation_guard(
            "F=config/assistant_config; echo 'execute_mutates = true' >> \"$F\"",
            workspace_cwd=str(isolated_env),
        )
        assert dec_var_cfg == "force_ask"

        dec_var_rest, _ = ci.evaluate_mutation_guard(
            "U=https://googleads.googleapis.com/v24/customers/123/campaigns:mutate; curl -X POST \"$U\"",
            workspace_cwd=str(isolated_env),
        )
        assert dec_var_rest == "deny"

        # 4. Extensionless executable Python script with live mutation is denied
        extless = isolated_env / "run_live_mut"
        extless.write_text(
            "#!/usr/bin/env python3\n"
            "svc.mutate_campaigns(customer_id='123', operations=[])\n",
            encoding="utf-8",
        )
        extless.chmod(0o755)
        dec_ext, _ = ci.evaluate_mutation_guard(f"./{extless.name}", workspace_cwd=str(isolated_env))
        assert dec_ext == "deny"

    def test_p0_9_plugin_root_env_resolution_and_p1_6_space_quoting(
        self, ci: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        custom_root = tmp_path / "My Custom Plugin Root"
        (custom_root / "config").mkdir(parents=True)
        (custom_root / "skills" / "validate-gaql" / "scripts").mkdir(parents=True)
        (custom_root / "skills" / "validate-gaql" / "scripts" / "validate_gaql.py").write_text(
            "print('ok')\n", encoding="utf-8"
        )
        (custom_root / "config" / "assistant_config").write_text(
            'api_version = "v29"\ncustomer_id = "1234567890"\nenabled = true\n', encoding="utf-8"
        )
        monkeypatch.setenv("PLUGIN_ROOT", str(custom_root))
        monkeypatch.setenv("GOOGLE_ADS_ASSISTANT_ENABLED", "true")
        monkeypatch.delenv("GOOGLE_ADS_ASSISTANT_CONFIG_DIR", raising=False)
        monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
        monkeypatch.delenv("GOOGLE_ADS_ASSISTANT_DIR", raising=False)

        assert ci._resolve_hook_plugin_root() == str(custom_root)
        # Rewritten skill path with spaces must be shell-quoted
        payload = {
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "python3 skills/validate-gaql/scripts/validate_gaql.py --help"},
            }
        }
        monkeypatch.setattr(ci, "sync_and_set_config_kv", lambda *a, **kw: str(custom_root / "config" / "google-ads.yaml"))
        ci.handle_hook(explicit_event="PreToolUse", explicit_cli="agy", raw_stdin=json.dumps(payload))
        out = json.loads(capsys.readouterr().out)
        rewritten = out["overwrite"]["CommandLine"]
        assert "'My Custom Plugin Root" in rewritten or f"'{custom_root}/skills/validate-gaql/scripts/validate_gaql.py'" in rewritten

    def test_p0_1_p1_5_p2_1_server_confinement_real_dry_run_tier1_and_mcp_parity(
        self, srv: Any, isolated_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        h = srv.A2AHandler.__new__(srv.A2AHandler)

        # 1. MCP serverInfo name matches manifests, generate_code removed, reject_mutation added
        tool_names = [t["name"] for t in srv._MCP_TOOL_DEFINITIONS]
        assert "generate_code" not in tool_names
        assert "reject_mutation" in tool_names

        in_stream = io.StringIO(
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n"
        )
        out_stream = io.StringIO()
        srv.run_mcp_stdio_server(stdin=in_stream, stdout=out_stream)
        init_resp = json.loads(out_stream.getvalue().strip())
        assert init_resp["result"]["serverInfo"]["name"] == "google-ads-api-assistant"

        # 2. prepare_mutation rejects script_path outside saved/code/
        outside = isolated_env / "evil.py"
        outside.write_text("print('hi')\n", encoding="utf-8")
        res_out = h.handle_prepare_mutation(
            "t-out",
            {
                "customer_id": "1234567890",
                "operation_summary": "Update campaign",
                "consequences": ["Pauses campaign"],
                "script_path": str(outside),
            },
        )
        assert res_out["status"] == "VALIDATION_FAILED"
        assert "saved/code/" in res_out["error"]

        # 3. prepare_mutation with record_only=True cannot be run_script=True in execute_mutation
        in_saved = isolated_env / "saved" / "code" / "mut_rec.py"
        in_saved.write_text("print('mut')\n", encoding="utf-8")
        prep_rec = h.handle_prepare_mutation(
            "t-rec",
            {
                "customer_id": "1234567890",
                "operation_summary": "Update campaign 1",
                "consequences": ["Pauses campaign 1"],
                "script_path": str(in_saved),
                "record_only": True,
            },
        )
        assert prep_rec["status"] == "HITL_CONFIRMATION_REQUIRED"
        monkeypatch.setenv("GOOGLE_ADS_EXECUTE_MUTATES", "true")
        monkeypatch.setenv("GOOGLE_ADS_ALLOW_TIER1_FINANCIAL_MUTATES", "true")
        exec_rec = h.handle_execute_mutation(
            "t-exec-rec",
            {
                "user_confirmed": True,
                "confirmation_summary": "Approved",
                "script_path": str(in_saved),
                "run_script": True,
            },
        )
        assert exec_rec["status"] == "HITL_BLOCKED"
        assert "record_only" in exec_rec["error"]

        # 4. create_campaign live requires Tier 1 posture AND pending dry-run receipt
        monkeypatch.setenv("GOOGLE_ADS_ALLOW_TIER1_FINANCIAL_MUTATES", "false")
        t1_blocked = h.handle_create_campaign(
            "t-t1",
            {
                "customer_id": "1234567890",
                "budget_amount_micros": 5_000_000,
                "execute": True,
                "user_confirmed": True,
            },
        )
        assert t1_blocked["status"] == "HITL_BLOCKED"
        assert "TIER 1" in t1_blocked["error"]

        monkeypatch.setenv("GOOGLE_ADS_ALLOW_TIER1_FINANCIAL_MUTATES", "true")
        no_rec_blocked = h.handle_create_campaign(
            "t-norec",
            {
                "customer_id": "1234567890",
                "budget_amount_micros": 5_000_000,
                "execute": True,
                "user_confirmed": True,
            },
        )
        assert no_rec_blocked["status"] == "HITL_BLOCKED"
        assert "dry-run receipt" in no_rec_blocked["error"]

        # 5. prepare_mutation real dry-run subprocess branch + create_campaign dry-run -> live round-trip
        with (
            MagicMock() as _unused,
        ):
            _ = _unused
        fake_proc_fail = SimpleNamespace(returncode=2, stdout="", stderr="BLOCKED: limit")
        orig_sub_run = srv.subprocess.run
        monkeypatch.setattr(srv.subprocess, "run", lambda *a, **kw: fake_proc_fail)
        prep_sub_blocked = h.handle_prepare_mutation(
            "t-sub-blk",
            {
                "customer_id": "1234567890",
                "operation_summary": "Update campaign 1",
                "consequences": ["Pauses campaign 1"],
                "script_path": str(in_saved),
            },
        )
        assert prep_sub_blocked["status"] == "HITL_BLOCKED"

        monkeypatch.setattr(srv.subprocess, "run", orig_sub_run)
        prep_missing = h.handle_prepare_mutation(
            "t-sub-miss",
            {
                "customer_id": "1234567890",
                "operation_summary": "Update campaign 1",
                "consequences": ["Pauses campaign 1"],
                "script_path": str(isolated_env / "saved" / "code" / "does_not_exist.py"),
            },
        )
        assert prep_missing["status"] == "VALIDATION_FAILED"

        mock_camp_client = MagicMock()
        mock_camp_client.get_service.return_value.mutate.return_value = SimpleNamespace(
            mutate_operation_responses=[
                SimpleNamespace(
                    campaign_budget_result=SimpleNamespace(
                        resource_name="customers/1234567890/campaignBudgets/1"
                    ),
                    campaign_result=SimpleNamespace(resource_name=""),
                ),
                SimpleNamespace(
                    campaign_budget_result=SimpleNamespace(resource_name=""),
                    campaign_result=SimpleNamespace(
                        resource_name="customers/1234567890/campaigns/2"
                    ),
                ),
            ]
        )
        dry_camp = h.handle_create_campaign(
            "t-cc-dry",
            {
                "customer_id": "1234567890",
                "campaign_name": "RoundTrip",
                "budget_amount_micros": 5_000_000,
                "validate_only": True,
                "client": mock_camp_client,
            },
        )
        assert dry_camp["status"] == "COMPLETED"
        assert dry_camp["result"].get("receipt_id")
        live_camp = h.handle_create_campaign(
            "t-cc-live",
            {
                "customer_id": "1234567890",
                "campaign_name": "RoundTrip",
                "budget_amount_micros": 5_000_000,
                "execute": True,
                "user_confirmed": True,
                "client": mock_camp_client,
            },
        )
        assert live_camp["status"] == "COMPLETED"

        # 6. troubleshoot_conversions fails cleanly when credentials missing (no stub!) and confines csv_path
        monkeypatch.setenv("GOOGLE_ADS_CONFIGURATION_FILE_PATH", str(isolated_env / "nonexistent-google-ads.yaml"))
        tc_fail = h.handle_troubleshoot_conversions("t-tc-fail", {"customer_id": "1234567890", "api_version": "v24"})
        assert tc_fail["status"] == "FAILED"
        tc_outside = h.handle_troubleshoot_conversions("t-tc-out", {"csv_path": "/etc/passwd"})
        assert tc_outside["status"] == "VALIDATION_FAILED"

    def test_p2_2_sync_client_libs_host_allowlist_and_p2_5_get_cids_max_rows(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        scl = _load_isolated(SYNC_LIBS_PATH, "scl_preship_test")
        # Untrusted host rejected before urlopen
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        assert (
            scl.update_codebase_via_archive(
                str(out_dir),
                "googleads/google-ads-python",
                "v34.0.0",
                "https://evil.example.com/archive.tar.gz",
            )
            is False
        )
        # Local pip fallback rejects non-git / untrusted directory
        untrusted = tmp_path / "untrusted_pkg"
        untrusted.mkdir()
        assert scl._is_verified_googleads_python_checkout(str(untrusted)) is False

        # get_cids_under_mcc --max-rows caps stdout JSON and console output
        gc = _load_isolated(GET_CIDS_PATH, "gc_preship_test")
        fake_rows = [
            gc.ChildAccountRow(str(1000000000 + i), 1, False, f"Acct {i}", "ENABLED")
            for i in range(10)
        ]
        monkeypatch.setattr(gc, "get_cids_under_mcc", lambda *a, **kw: fake_rows)
        monkeypatch.setattr(
            sys, "argv", ["get_cids_under_mcc.py", "-c", "1000000000", "--json", "--max-rows", "3"]
        )
        gc.main()
        out = json.loads(capsys.readouterr().out)
        assert out["total_child_accounts"] == 10
        assert out["returned_child_accounts"] == 3
        assert out["truncated"] is True
        assert len(out["child_accounts"]) == 3

        monkeypatch.setattr(
            sys, "argv", ["get_cids_under_mcc.py", "-c", "1000000000", "--print_cids", "--max-rows", "3"]
        )
        gc.main()
        console_out = capsys.readouterr().out
        assert "truncated: showing 3 of 10" in console_out

    def test_p0_3_p1_4_p2_3_p2_4_p3_3_manifests_rules_and_latency(self, isolated_env: Path) -> None:
        # Rules file renamed to AGENTS.md (auto-loaded by agy and injected on Claude SessionStart) and < 4 KB
        agents_md = PLUGIN_ROOT / "rules" / "AGENTS.md"
        assert agents_md.is_file()
        assert not (PLUGIN_ROOT / "rules" / "google_ads_rules.md").exists()
        raw_rules = agents_md.read_text(encoding="utf-8")
        assert "4-Step HITL" in raw_rules
        assert len(raw_rules.encode("utf-8")) < 4096

        # Plugin manifest has category, logo (file exists), and suggestedPrompts
        pjson = json.loads((PLUGIN_ROOT / "plugin.json").read_text(encoding="utf-8"))
        assert pjson["category"] == "development"
        assert (PLUGIN_ROOT / pjson["logo"]).is_file()
        assert len(pjson["suggestedPrompts"]) >= 3

        # Sidecar has sandbox.allowed_http_hosts
        sjson = json.loads(
            (PLUGIN_ROOT / "sidecars" / "google-ads-a2a-service" / "sidecar.json").read_text(
                encoding="utf-8"
            )
        )
        assert "googleads.googleapis.com" in sjson["sandbox"]["allowed_http_hosts"]

        # mcp_config.json uses ${PLUGIN_ROOT} and has no _comment key
        mjson = json.loads((PLUGIN_ROOT / "mcp_config.json").read_text(encoding="utf-8"))
        assert "_comment" not in mjson
        assert mjson["mcpServers"]["google-ads-api-assistant"]["args"][0].startswith("${PLUGIN_ROOT}/")

        # All 11 skills have negative boundaries and renamed google-ads-explain / google-ads-step-by-step
        skill_dirs = sorted(p.name for p in (PLUGIN_ROOT / "skills").iterdir() if p.is_dir())
        assert "google-ads-explain" in skill_dirs
        assert "google-ads-step-by-step" in skill_dirs
        assert "explain" not in skill_dirs and "step-by-step" not in skill_dirs
        for sname in skill_dirs:
            txt = (PLUGIN_ROOT / "skills" / sname / "SKILL.md").read_text(encoding="utf-8")
            assert "Don't use for" in txt, sname

        # Synchronous hook latency on benign shell command must stay well under 150ms
        t0 = time.perf_counter()
        proc = subprocess.run(
            [sys.executable, str(HOOK_GUARD_PATH), "--cli", "agy", "--event", "PreToolUse"],
            input=json.dumps({"toolCall": {"name": "run_command", "args": {"CommandLine": "git status"}}}),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        assert proc.returncode == 0
        assert json.loads(proc.stdout)["decision"] == "allow"
        assert elapsed_ms < 150.0, f"Fast PreToolUse hook took {elapsed_ms:.1f}ms (> 150ms budget)"

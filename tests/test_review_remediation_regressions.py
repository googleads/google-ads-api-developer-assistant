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

"""Regression tests covering all P0–P3 findings from the 7c59ab9..da83000 review."""

from __future__ import annotations

import errno
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tests.api_version_utils import CURRENT_API_VERSION, PREVIOUS_API_VERSION

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = PROJECT_ROOT / "plugins" / "google-ads-api-developer-assistant"
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))
SIDECAR_DIR = PLUGIN_ROOT / "sidecars" / "google-ads-a2a-service"
if str(SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(SIDECAR_DIR))


def _load_module(name: str, rel_path: str) -> Any:
    full = PLUGIN_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, str(full))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_assistant_config(cfg_dir: Path, *, execute_mutates: bool = False) -> None:
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "assistant_config").write_text(
        f"enabled = true\n"
        f"execute_mutates = {'true' if execute_mutates else 'false'}\n"
        f"allow_tier1_financial_mutates = false\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# P0-1: Cross-channel receipt confusion & create_params_sha256 tamper binding
# ---------------------------------------------------------------------------


def test_p0_1_create_params_receipt_cannot_execute_script(tmp_path: Path, monkeypatch: Any) -> None:
    import config.config_init as ci
    import server

    run_mod = _load_module("_rm_p0_1", "skills/execute-mutation/scripts/run_mutation.py")
    receipt_file = tmp_path / "last_dry_run.json"
    audit_file = tmp_path / "mutation_audit.jsonl"
    monkeypatch.setenv("GOOGLE_ADS_MUTATION_RECEIPT_PATH", str(receipt_file))
    monkeypatch.setenv("GOOGLE_ADS_MUTATION_AUDIT_LOG", str(audit_file))

    script = tmp_path / "saved" / "code" / "invite_admin.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        "svc.mutate_customer_user_access_invitation(customer_id='1234567890', operation=op)\n",
        encoding="utf-8",
    )

    rec = run_mod.write_dry_run_receipt(
        customer_id="1234567890",
        operation_summary="Create Responsive Search Ad",
        before_state="None",
        after_state="New ad",
        consequences=["Creates paused RSA"],
        reversibility="REVERSIBLE",
        script_path=None,
        dry_run_output="Validated",
        record_only=False,
        create_params_sha256="a" * 64,
    )
    assert rec["create_params_sha256"] == "a" * 64

    # 1. run_mutation.load_and_verify_receipt rejects script execution against create_* receipt
    ok_rm, msg_rm, _ = run_mod.load_and_verify_receipt(script_path=str(script))
    assert not ok_rm
    assert "create" in msg_rm.lower() or "script" in msg_rm.lower()

    # 2. config_init._verify_dry_run_receipt_for_hook rejects script execution against create_* receipt
    ok_ci, msg_ci, _ = ci._verify_dry_run_receipt_for_hook(
        script_path=str(script), workspace_cwd=str(tmp_path)
    )
    assert not ok_ci
    assert "create" in msg_ci.lower() or "script" in msg_ci.lower()

    # 3. server.handle_execute_mutation(run_script=True) blocks create_* receipt
    _write_assistant_config(tmp_path / "config", execute_mutates=True)
    monkeypatch.setenv("GOOGLE_ADS_ASSISTANT_CONFIG_DIR", str(tmp_path / "config"))
    handler = server.A2AHandler.__new__(server.A2AHandler)
    res = handler.handle_execute_mutation(
        "task-cross",
        {
            "user_confirmed": True,
            "confirmation_summary": "Approved",
            "run_script": True,
            "script_path": str(script),
        },
    )
    assert res["status"] == "HITL_BLOCKED"

    # 4. Tampering create_params_sha256 on disk fails request_sha256 integrity check
    raw = json.loads(receipt_file.read_text(encoding="utf-8"))
    raw["create_params_sha256"] = "b" * 64
    receipt_file.write_text(json.dumps(raw), encoding="utf-8")
    ok_tamper, msg_tamper, _ = run_mod.load_and_verify_receipt()
    assert not ok_tamper
    assert "sha-256" in msg_tamper.lower() or "mismatch" in msg_tamper.lower()


# ---------------------------------------------------------------------------
# P0-2: NDJSON DISPATCHED / CLEAN_EXIT trace prevents erroneous receipt re-arming
# ---------------------------------------------------------------------------


def test_p0_2_parse_trace_file_ndjson_dispatched_and_clean_exit(tmp_path: Path) -> None:
    run_mod = _load_module("_rm_p0_2", "skills/execute-mutation/scripts/run_mutation.py")

    # Crash after DISPATCHED (no CLEAN_EXIT sentinel)
    crash_trace = tmp_path / "crash.ndjson"
    crash_trace.write_text(
        json.dumps(
            {
                "event": "DISPATCHED",
                "call": {
                    "service": "CampaignService",
                    "method": "mutate_campaigns",
                    "status": "DISPATCHED",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    trace_crash = run_mod._parse_trace_file(str(crash_trace))
    assert not trace_crash.clean_exit_seen
    assert trace_crash.any_rpc_dispatched
    assert any(c.get("status") == "DISPATCHED" for c in trace_crash)

    # Clean exit with zero dispatched calls (e.g., pre-RPC validation failure)
    clean_trace = tmp_path / "clean.ndjson"
    clean_trace.write_text(json.dumps({"event": "CLEAN_EXIT"}) + "\n", encoding="utf-8")
    trace_clean = run_mod._parse_trace_file(str(clean_trace))
    assert trace_clean.clean_exit_seen
    assert not trace_clean.any_rpc_dispatched
    assert list(trace_clean) == []


# ---------------------------------------------------------------------------
# P0-3 & P1-9 & P2-24: Receipt lock, mirror fallthrough, claim_id, ELOOP, hook lock
# ---------------------------------------------------------------------------


def test_p0_3_mirror_fallthrough_blocked_and_claim_id_enforced(tmp_path: Path, monkeypatch: Any) -> None:
    import config.config_init as ci

    run_mod = _load_module("_rm_p0_3", "skills/execute-mutation/scripts/run_mutation.py")
    p1 = tmp_path / "dir1" / "last_dry_run.json"
    p2 = tmp_path / "dir2" / "last_dry_run.json"
    p1.parent.mkdir()
    p2.parent.mkdir()
    monkeypatch.setattr(run_mod, "get_receipt_paths", lambda: [str(p1), str(p2)])

    script = tmp_path / "mut.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    rec = run_mod.write_dry_run_receipt(
        customer_id="1234567890",
        operation_summary="Pause campaign",
        before_state="ENABLED",
        after_state="PAUSED",
        consequences=["Pauses campaign"],
        reversibility="REVERSIBLE",
        script_path=str(script),
        dry_run_output="OK",
        record_only=False,
    )
    rid = rec["receipt_id"]

    # Claim with receipt_id -> yields UUID executing_claim_id
    ok1, _, claimed = run_mod.claim_receipt_for_execution(expected_receipt_id=rid)
    assert ok1 and claimed is not None
    claim_id = claimed["executing_claim_id"]
    assert len(claim_id) >= 16

    # Re-claiming while EXECUTING fails closed
    ok2, msg2, _ = run_mod.claim_receipt_for_execution(expected_receipt_id=rid)
    assert not ok2
    assert "executing" in msg2.lower()

    # Simulate split-brain: p2 still has DRY_RUN_PASSED while p1 is EXECUTING
    p2_data = json.loads(p2.read_text(encoding="utf-8"))
    p2_data["status"] = "DRY_RUN_PASSED"
    p2.write_text(json.dumps(p2_data), encoding="utf-8")
    ok3, _, _ = run_mod.claim_receipt_for_execution(expected_receipt_id=rid)
    assert not ok3

    # load_and_verify_receipt must not fall through from p1=EXECUTING to p2=DRY_RUN_PASSED
    ok_ver, _, _ = run_mod.load_and_verify_receipt(script_path=str(script))
    assert not ok_ver

    # Wrong claim_id cannot release the claim
    run_mod.release_claimed_receipt_if_not_executed(
        expected_receipt_id=rid, expected_claim_id="wrong-claim-id"
    )
    assert json.loads(p1.read_text(encoding="utf-8"))["status"] == "EXECUTING"

    # Locked hook metadata updater must NOT overwrite EXECUTING back to DRY_RUN_PASSED
    ci._update_receipt_hook_metadata_locked(
        str(p1), rid, {"hook_prompted_at_iso": "2026-01-01T00:00:00Z"}, rm_mod=run_mod
    )
    assert json.loads(p1.read_text(encoding="utf-8"))["status"] == "EXECUTING"

    # Correct claim_id releases cleanly
    run_mod.release_claimed_receipt_if_not_executed(
        expected_receipt_id=rid, expected_claim_id=claim_id
    )
    assert json.loads(p1.read_text(encoding="utf-8"))["status"] == "DRY_RUN_PASSED"
    assert "executing_claim_id" not in json.loads(p1.read_text(encoding="utf-8"))


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX O_NOFOLLOW ELOOP test")
def test_p1_9_symlinked_lockfile_fails_closed(tmp_path: Path, monkeypatch: Any) -> None:
    run_mod = _load_module("_rm_eloop", "skills/execute-mutation/scripts/run_mutation.py")
    rec_path = tmp_path / "last_dry_run.json"
    real_target = tmp_path / "outside.txt"
    real_target.write_text("x", encoding="utf-8")
    os.symlink(str(real_target), str(tmp_path / ".last_dry_run.lock"))
    monkeypatch.setattr(run_mod, "get_receipt_paths", lambda: [str(rec_path)])

    with pytest.raises(OSError) as exc_info:
        with run_mod._receipt_paths_lock([str(rec_path)]):
            pass
    assert exc_info.value.errno == errno.ELOOP


# ---------------------------------------------------------------------------
# P0-4 & P3-25: AST walker bypasses & indirect calls + legitimate Request ctor
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "script_body",
    [
        # Lambda body bypass
        "svc.mutate_campaigns(customer_id='1', operations=[op], validate_only=True)\n"
        "(lambda: svc.mutate_campaigns(customer_id='1', operations=[op]))()\n",
        # Default arg bypass
        "svc.mutate_campaigns(customer_id='1', operations=[op], validate_only=True)\n"
        "def live(x=svc.mutate_campaigns(customer_id='1', operations=[op])): pass\n",
        # Decorator bypass
        "svc.mutate_campaigns(customer_id='1', operations=[op], validate_only=True)\n"
        "@(lambda _: (lambda f: f))(svc.mutate_campaigns(customer_id='1', operations=[op]))\n"
        "def f(): pass\n",
        # Class base bypass
        "svc.mutate_campaigns(customer_id='1', operations=[op], validate_only=True)\n"
        "class C(type(svc.mutate_campaigns(customer_id='1', operations=[op]))): pass\n",
        # Request aliasing with 0
        "req = client.get_type('MutateCampaignsRequest')\n"
        "req.validate_only = True\n"
        "alias = req\n"
        "alias.validate_only = 0\n"
        "svc.mutate_campaigns(request=req)\n",
        # Protobuf ClearField
        "req = client.get_type('MutateCampaignsRequest')\n"
        "req.validate_only = True\n"
        "req.ClearField('validate_only')\n"
        "svc.mutate_campaigns(request=req)\n",
        # Dict update / duplicate key / ** unpack
        "req = {'validate_only': True, 'customer_id': '1', 'operations': [op]}\n"
        "req.update({'validate_only': 0})\n"
        "svc.mutate_campaigns(request=req)\n",
        "svc.mutate_campaigns(request={'validate_only': True, 'validate_only': 0})\n",
        "svc.mutate_campaigns(request={'validate_only': True, **{'validate_only': 0}})\n",
        # try/finally overwrite
        "req = client.get_type('MutateCampaignsRequest')\n"
        "req.validate_only = True\n"
        "try:\n    req.validate_only = 0\n"
        "finally:\n    svc.mutate_campaigns(request=req)\n",
        # for target overwrite
        "req = client.get_type('MutateCampaignsRequest')\n"
        "req.validate_only = True\n"
        "for req in [live]:\n    svc.mutate_campaigns(request=req)\n",
        # Tuple unpack overwrite
        "req = client.get_type('MutateCampaignsRequest')\n"
        "req.validate_only = True\n"
        "req, _ = live, 1\n"
        "svc.mutate_campaigns(request=req)\n",
        # Walrus overwrite
        "req = client.get_type('MutateCampaignsRequest')\n"
        "req.validate_only = True\n"
        "if (req := live) or True:\n    svc.mutate_campaigns(request=req)\n",
        # Indirect method reference
        "fn = svc.mutate_campaigns\nfn(customer_id='1', operations=[op])\n",
        # functools.partial
        "import functools\nfunctools.partial(svc.mutate_campaigns, customer_id='1', operations=[op])()\n",
    ],
)
def test_p0_4_ast_and_indirect_call_bypasses_denied(
    tmp_path: Path, monkeypatch: Any, script_body: str
) -> None:
    import config.config_init as ci

    _write_assistant_config(tmp_path / "config", execute_mutates=False)
    monkeypatch.setenv("GOOGLE_ADS_ASSISTANT_CONFIG_DIR", str(tmp_path / "config"))
    script = tmp_path / "saved" / "code" / "bypass.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(script_body, encoding="utf-8")

    decision, _ = ci.evaluate_mutation_guard(
        f"python3 {script}", workspace_cwd=str(tmp_path)
    )
    assert decision == "deny"


def test_p3_25_legitimate_request_constructor_dry_run_allowed(
    tmp_path: Path, monkeypatch: Any
) -> None:
    import config.config_init as ci

    _write_assistant_config(tmp_path / "config", execute_mutates=False)
    monkeypatch.setenv("GOOGLE_ADS_ASSISTANT_CONFIG_DIR", str(tmp_path / "config"))
    script = tmp_path / "saved" / "code" / "safe_ctor.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        "req = MutateCampaignsRequest(customer_id='1', operations=[op], validate_only=True)\n"
        "svc.mutate_campaigns(request=req)\n",
        encoding="utf-8",
    )
    decision, reason = ci.evaluate_mutation_guard(
        f"python3 {script}", workspace_cwd=str(tmp_path)
    )
    assert decision == "allow", f"Expected allow, got {decision}: {reason}"


# ---------------------------------------------------------------------------
# P0-5, P1-10, P1-15, P2-22: Shell guards, pytest, obfuscation, creds, RPCs
# ---------------------------------------------------------------------------


def test_p0_5_p1_10_p1_15_shell_and_hook_bypasses_blocked(
    tmp_path: Path, monkeypatch: Any
) -> None:
    import config.config_init as ci
    import config.hook_guard as hg

    _write_assistant_config(tmp_path / "config", execute_mutates=False)
    monkeypatch.setenv("GOOGLE_ADS_ASSISTANT_CONFIG_DIR", str(tmp_path / "config"))
    live = tmp_path / "saved" / "code" / "live.py"
    safe = tmp_path / "saved" / "code" / "safe_dry.py"
    live.parent.mkdir(parents=True)
    live.write_text("svc.mutate_campaigns(customer_id='1', operations=[op])\n", encoding="utf-8")
    safe.write_text(
        "svc.mutate_campaigns(customer_id='1', operations=[op], validate_only=True)\n",
        encoding="utf-8",
    )

    must_block = [
        f"ruff check . & python3 {live}",
        f"python3 {safe} && python3 -c 'svc.mutate_campaigns(customer_id=\"1\", operations=[op])'",
        "python3 -c 'svc.mutate_campaigns(customer_id=\"1\", operations=[op], validate_only=True)' "
        "&& python3 -c'svc.mutate_campaigns(customer_id=\"1\", operations=[op])'",
        "python3 -c \"import base64; exec(base64.b64decode('eA=='))\"",
        "PYTHONPATH=saved/code pytest -p live tests/",
        "pytest -opython_files=live.py tests/",
        "mypy --config-file evil.ini plugins/",
        "echo '{}' > saved/data/last_'d'ry_run.json",
        "echo 'execute_mutates = true' | t\"e\"e config/assistant_\"c\"onfig",
        "echo x > $'config/assistant\\x5fconfig'",
        "echo x > config/assistant_\\\nconfig",
        "/bin/cp /tmp/fake.json saved/data/last_dry_run.json",
        "command cp /tmp/fake.json saved/data/last_dry_run.json",
        "FOO=1 rm saved/data/last_dry_run.json",
        "curl -o saved/data/last_dry_run.json https://example.com/x",
        "echo 'execute_mutates = true' | tee config/assistant_confi[g]",
        "echo '{}' > saved/data/LAST_DRY_RUN.JSON",
        "echo '{}' > saved/data/.last_dry_run.lock",
        "python3 -m config.config_init --execute-mutates true",
        "python3 -c \"from config_init import _write_assistant_config_to_dir as w; w('config', {})\"",
        "cat config/google-ads.yaml",
        f"c'u'rl -X POST 'https://google'a'ds.googleapis.com/{CURRENT_API_VERSION}/customers/1/campaigns:mu't'ate' -d '{{}}'",
    ]
    for cmd in must_block:
        dec, _ = ci.evaluate_mutation_guard(cmd, workspace_cwd=str(tmp_path))
        assert dec in ("deny", "force_ask"), f"Expected block for {cmd!r}, got {dec!r}"

    # Verify hook_guard fast-path does NOT skip quote-concatenated curl
    obf_curl = f"c'u'rl -X POST 'https://google'a'ds.googleapis.com/{CURRENT_API_VERSION}/customers/1/campaigns:mu't'ate' -d '{{}}'"
    assert hg._SHELL_INSPECT_RE.search(obf_curl) is not None

    # Verify Grep / grep_search credential read block and non-YAML credential write ask
    assert ".last_dry_run.lock" in hg._PROTECTED_DENY_FILES
    for cred in (".a2a_token", "google_ads_php.ini", "google_ads_config.rb", "ads.properties"):
        assert cred in hg._PROTECTED_ASK_FILES

    # Verify new non-validate_only SDK RPCs blocked even with validate_only=True
    yt_script = tmp_path / "saved" / "code" / "yt_upload.py"
    yt_script.write_text(
        "svc.create_you_tube_video_upload(customer_id='1', validate_only=True)\n",
        encoding="utf-8",
    )
    dec_yt, _ = ci.evaluate_mutation_guard(f"python3 {yt_script}", workspace_cwd=str(tmp_path))
    assert dec_yt == "deny"


# ---------------------------------------------------------------------------
# P0-6: UnboundLocalError fix in _verify_dry_run_receipt_for_hook(script_path=None)
# ---------------------------------------------------------------------------


def test_p0_6_receipt_only_hook_verification_no_unbound_local(
    tmp_path: Path, monkeypatch: Any
) -> None:
    import config.config_init as ci

    run_mod = _load_module("_rm_p0_6", "skills/execute-mutation/scripts/run_mutation.py")
    receipt_file = tmp_path / "last_dry_run.json"
    monkeypatch.setenv("GOOGLE_ADS_MUTATION_RECEIPT_PATH", str(receipt_file))
    _write_assistant_config(tmp_path / "config", execute_mutates=True)
    monkeypatch.setenv("GOOGLE_ADS_ASSISTANT_CONFIG_DIR", str(tmp_path / "config"))

    rec = run_mod.write_dry_run_receipt(
        customer_id="1234567890",
        operation_summary="Create ad group",
        before_state="None",
        after_state="New ad group",
        consequences=["Creates paused ad group"],
        reversibility="REVERSIBLE",
        script_path=None,
        dry_run_output="Validated",
        record_only=False,
    )
    # Strip precomputed classification_tier & ato_escalation to hit the fallback lines
    raw = json.loads(receipt_file.read_text(encoding="utf-8"))
    raw.pop("classification_tier", None)
    raw.pop("ato_escalation", None)
    receipt_file.write_text(json.dumps(raw), encoding="utf-8")

    ok, msg, verified = ci._verify_dry_run_receipt_for_hook(
        script_path=None, workspace_cwd=str(tmp_path), allow_receipt_only=True
    )
    assert ok, f"Expected receipt-only verification to succeed, got: {msg}"
    assert verified and verified["receipt_id"] == rec["receipt_id"]


# ---------------------------------------------------------------------------
# P1-8, P1-11, P1-17, P2-19, P2-24, P3-25: Sidecar server.py tests & run_server
# ---------------------------------------------------------------------------


def test_p1_8_p1_11_p2_19_p2_24_p3_25_server_hardening_and_coverage(
    tmp_path: Path, monkeypatch: Any
) -> None:
    import server

    run_mod = _load_module("_rm_srv", "skills/execute-mutation/scripts/run_mutation.py")

    # 1. _configure_sandbox_writable_env creates config/ and sets CONVERSION_OUTPUT_DIR
    sandbox_root = tmp_path / "plugin_data"
    monkeypatch.setenv("PLUGIN_DATA", str(sandbox_root))
    monkeypatch.delenv("CONVERSION_OUTPUT_DIR", raising=False)
    monkeypatch.delenv("GOOGLE_ADS_MUTATION_RECEIPT_PATH", raising=False)
    monkeypatch.delenv("GOOGLE_ADS_MUTATION_AUDIT_LOG", raising=False)
    monkeypatch.delenv("GOOGLE_ADS_GAQL_CACHE_PATH", raising=False)

    configured = server._configure_sandbox_writable_env()
    assert configured == str(sandbox_root)
    assert (sandbox_root / "config").is_dir()
    assert os.environ.get("CONVERSION_OUTPUT_DIR") == str(sandbox_root / "saved" / "data")
    assert server._is_dir_writable(str(sandbox_root / "config")) is True
    assert server._is_dir_writable(str(tmp_path / "does_not_exist")) is False

    # 2. handle_troubleshoot_conversions rejects unconfined output_dir
    handler = server.A2AHandler.__new__(server.A2AHandler)
    outside_dir = tmp_path / "outside_unconfined"
    outside_dir.mkdir()
    res_unconfined = handler.handle_troubleshoot_conversions(
        "task-out",
        {
            "customer_id": "1234567890",
            "api_version": CURRENT_API_VERSION,
            "client": MagicMock(),
            "output_dir": str(outside_dir),
        },
    )
    assert res_unconfined["status"] == "VALIDATION_FAILED"

    # 3. _compute_create_params_sha256 fallback matches run_mutation ("request" key)
    params = {"customer_id": "1234567890", "api_version": CURRENT_API_VERSION}
    h_real = server.A2AHandler._compute_create_params_sha256(run_mod, "Create Ad", params)
    h_fallback = server.A2AHandler._compute_create_params_sha256(object(), "Create Ad", params)
    assert h_real == h_fallback

    # 4. _parse_strict_int rejects bool and non-integer float
    with pytest.raises(ValueError):
        server._parse_strict_int(True, "budget_amount_micros")
    with pytest.raises(ValueError):
        server._parse_strict_int(5000000.9, "budget_amount_micros")
    assert server._parse_strict_int("5000000", "budget_amount_micros") == 5000000

    # 5. Head+tail _truncate_tool_output preserves trailing traceback & BLOCKED marker
    big = ("A" * 10000) + "\nMIDDLE\n" + ("B" * 10000) + "\nBLOCKED: tail sentinel"
    trunc = server._truncate_tool_output(big, limit=2000)
    assert "AAAA" in trunc
    assert "BLOCKED: tail sentinel" in trunc
    assert "truncated" in trunc.lower()

    # 6. handle_create_account dry-run triggers ATO escalation & masks email in consequences
    receipt_file = sandbox_root / "saved" / "data" / "last_dry_run.json"
    monkeypatch.setenv("GOOGLE_ADS_MUTATION_RECEIPT_PATH", str(receipt_file))
    fake_client = MagicMock()
    fake_ca_mod = SimpleNamespace(
        create_account_under_mcc=lambda **kw: {
            "resource_name": "customers/9999999999",
            "validate_only": True,
        }
    )
    with (
        patch.object(handler, "_load_mutation_script", side_effect=lambda n: run_mod if n == "run_mutation.py" else fake_ca_mod),
        patch("server.get_effective_api_version", return_value=CURRENT_API_VERSION),
    ):
        res_acct = handler.handle_create_account(
            "task-acct",
            {
                "manager_customer_id": "1234567890",
                "descriptive_name": "Test Sub",
                "email_address": "victim.admin@example.com",
                "access_role": "admin",
                "validate_only": True,
                "client": fake_client,
            },
        )
    assert res_acct["status"] in ("COMPLETED", "HITL_CONFIRMATION_REQUIRED")
    stored_rec = json.loads(receipt_file.read_text(encoding="utf-8"))
    assert stored_rec["ato_escalation"]["is_ato_risk"] is True
    assert "victim.admin@example.com" not in json.dumps(stored_rec["consequences"])

    # 7. handle_create_campaign dry-run with budget_resource_name reports existing budget (not $5.00)
    fake_cc_mod = SimpleNamespace(
        create_campaign=lambda **kw: {"campaign_resource_name": "customers/1234567890/campaigns/1"}
    )
    with (
        patch.object(handler, "_load_mutation_script", side_effect=lambda n: run_mod if n == "run_mutation.py" else fake_cc_mod),
        patch("server.get_effective_api_version", return_value=CURRENT_API_VERSION),
    ):
        res_camp = handler.handle_create_campaign(
            "task-camp",
            {
                "customer_id": "1234567890",
                "campaign_name": "SharedBudgetCamp",
                "budget_resource_name": "customers/1234567890/campaignBudgets/999",
                "validate_only": True,
                "client": fake_client,
            },
        )
    assert res_camp["status"] in ("COMPLETED", "HITL_CONFIRMATION_REQUIRED")
    camp_rec = json.loads(receipt_file.read_text(encoding="utf-8"))
    assert "campaignBudgets/999" in " ".join(camp_rec["consequences"])
    assert "5000000 micros" not in " ".join(camp_rec["consequences"])

    # 8. run_server() unit test (mocking HTTPServer + config sync) for P1-17 coverage headroom
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    (fake_home / "google-ads.yaml").write_text("client_id: x\n", encoding="utf-8")
    monkeypatch.setenv("GOOGLE_ADS_ASSISTANT_CONFIG_DIR", str(sandbox_root / "config"))
    monkeypatch.delenv("GOOGLE_ADS_CONFIGURATION_FILE_PATH", raising=False)
    monkeypatch.setenv("GOOGLE_ADS_CONFIG_VALUE", "1234567890")
    monkeypatch.setenv("A2A_AUTH_TOKEN", "test-token-1234567890")

    fake_httpd = MagicMock()
    fake_httpd.serve_forever.side_effect = KeyboardInterrupt()
    with (
        patch("server.HTTPServer", return_value=fake_httpd) as mock_http_cls,
        patch("os.path.expanduser", side_effect=lambda p: p.replace("~", str(fake_home))),
        patch("config.config_init.sync_and_set_config_kv") as mock_sync,
    ):
        server.run_server()
    mock_http_cls.assert_called_once()
    mock_sync.assert_called_once()
    fake_httpd.server_close.assert_called_once()


# ---------------------------------------------------------------------------
# P1-13, P2-21: sync_client_libs.py sync_directories & TOML fallback
# ---------------------------------------------------------------------------


def test_p1_13_p2_21_sync_directories_and_toml_fallback(tmp_path: Path) -> None:
    scl = _load_module("_scl_reg", "skills/sync-client-libs/scripts/sync_client_libs.py")

    # 1. sync_directories preserves saved/, client_libs/, google-ads.yaml even if present in source
    src = tmp_path / "src"
    dst = tmp_path / "dst"
    (src / "saved").mkdir(parents=True)
    (src / "saved" / ".gitkeep").write_text("", encoding="utf-8")
    (src / "config").mkdir()
    (src / "config" / "assistant_config").write_text("execute_mutates = false\n", encoding="utf-8")
    (src / "google-ads.yaml").write_text("SHOULD_NOT_OVERWRITE\n", encoding="utf-8")
    (src / "new_file.txt").write_text("v2", encoding="utf-8")

    (dst / "saved").mkdir(parents=True)
    (dst / "saved" / "user_data.json").write_text('{"keep": true}', encoding="utf-8")
    (dst / "config").mkdir()
    (dst / "config" / "google-ads.yaml").write_text("user_secret: keep\n", encoding="utf-8")
    (dst / "google-ads.yaml").write_text("top_user_secret: keep\n", encoding="utf-8")

    assert scl.sync_directories(str(src), str(dst)) is True
    assert (dst / "saved" / "user_data.json").read_text(encoding="utf-8") == '{"keep": true}'
    assert (dst / "config" / "google-ads.yaml").read_text(encoding="utf-8") == "user_secret: keep\n"
    assert (dst / "google-ads.yaml").read_text(encoding="utf-8") == "top_user_secret: keep\n"
    assert (dst / "new_file.txt").read_text(encoding="utf-8") == "v2"

    # 2. TOML fallback preserves '#' inside quotes, ints, quoted booleans, and stops at [section]
    broken_toml = (
        'note = "color #ff0000" # trailing comment\n'
        "timeout_seconds = 120\n"
        'label = "true"\n'
        "execute_mutates = false\n"
        "broken = [\n"
        "[nested]\n"
        "execute_mutates = true\n"
    )
    _cid, exec_mutates_str, _enabled_str, extra = scl._parse_assistant_config_fallback(broken_toml)
    assert extra["note"] == "color #ff0000"
    assert extra["timeout_seconds"] == 120
    assert extra["label"] == "true" and isinstance(extra["label"], str)
    assert exec_mutates_str == "false"

    # 3. pyproject.toml version detection ignores python_version before [project].version
    pyproj_dir = tmp_path / "client_libs"
    (pyproj_dir / "google-ads-python").mkdir(parents=True)
    (pyproj_dir / "google-ads-python" / "pyproject.toml").write_text(
        '[tool.ruff]\npython_version = "3.11"\n\n[project]\nname = "google-ads"\nversion = "99.1.0"\n',
        encoding="utf-8",
    )
    assert scl.detect_installed_version("google-ads-python", str(pyproj_dir / "google-ads-python")) == "99.1.0"


# ---------------------------------------------------------------------------
# P1-14, P3-25: validate_conversion_upload.py PII redaction & --max-errors
# ---------------------------------------------------------------------------


def test_p1_14_p3_25_conversion_upload_pii_redaction_and_max_errors(
    tmp_path: Path, capsys: Any
) -> None:
    vcu = _load_module(
        "_vcu_reg", "skills/troubleshoot-conversions/scripts/validate_conversion_upload.py"
    )
    csv_path = tmp_path / "conv.csv"
    csv_path.write_text(
        "hashed_email,hashed_phone_number,conversion_action,conversion_date_time,conversion_value,currency_code\n"
        "secret.user@example.com,+15551234567,customers/1/conversionActions/2,2026-01-01 12:00:00+00:00,10.0,USD\n",
        encoding="utf-8",
    )
    with pytest.raises(SystemExit) as exc_info:
        vcu.validate_conversion_csv(str(csv_path), api_version=CURRENT_API_VERSION)
    assert exc_info.value.code == 1
    out = capsys.readouterr().out
    assert "Unhashed raw PII" in out
    assert "secret.user@example.com" not in out
    assert "+15551234567" not in out

    with pytest.raises(ValueError):
        vcu.validate_conversion_csv(str(csv_path), max_errors=-1)
    with pytest.raises(ValueError):
        vcu.validate_conversion_csv(str(csv_path), max_errors=True)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# P2-20: validate_gaql.py customer-scoped invalidation & delimiter-safe keys
# ---------------------------------------------------------------------------


def test_p2_20_gaql_cache_invalidation_and_delimiter_safety(
    tmp_path: Path, monkeypatch: Any
) -> None:
    vg = _load_module("_vg_reg", "skills/validate-gaql/scripts/validate_gaql.py")
    cache_file = tmp_path / "gaql_cache.json"
    monkeypatch.setenv("GOOGLE_ADS_GAQL_CACHE_PATH", str(cache_file))

    # Delimiter collision impossible with JSON-array key
    assert vg.compute_gaql_cache_key("Q", f"{CURRENT_API_VERSION}|111", None) != vg.compute_gaql_cache_key(
        "Q", CURRENT_API_VERSION, "111"
    )

    q = "SELECT campaign.id FROM campaign"
    vg.set_cached_validation(q, CURRENT_API_VERSION, {"valid": True}, customer_id="1111111111")
    vg.set_cached_validation(q, CURRENT_API_VERSION, {"valid": True}, customer_id="2222222222")

    # Invalidating only customer 1111111111 keeps customer 2222222222 intact
    removed_one = vg.invalidate_gaql_cache(customer_id="1111111111")
    assert removed_one == 1
    assert vg.get_cached_validation(q, CURRENT_API_VERSION, customer_id="1111111111") is None
    assert vg.get_cached_validation(q, CURRENT_API_VERSION, customer_id="2222222222") is not None

    # Invalidating (query, api_version) with customer_id=None removes customer-scoped entries too
    removed_all = vg.invalidate_gaql_cache(query=q, api_version=CURRENT_API_VERSION)
    assert removed_all == 1
    assert vg.get_cached_validation(q, CURRENT_API_VERSION, customer_id="2222222222") is None


# ---------------------------------------------------------------------------
# P2-18: run_mutation.py --execute rejects injected --script-args and mismatched --customer-id
# ---------------------------------------------------------------------------


def test_p2_18_execute_rejects_injected_args_and_mismatched_cid(
    tmp_path: Path, monkeypatch: Any
) -> None:
    runner_path = PLUGIN_ROOT / "skills" / "execute-mutation" / "scripts" / "run_mutation.py"
    receipt_file = tmp_path / "last_dry_run.json"
    audit_file = tmp_path / "mutation_audit.jsonl"
    monkeypatch.setenv("GOOGLE_ADS_MUTATION_RECEIPT_PATH", str(receipt_file))
    monkeypatch.setenv("GOOGLE_ADS_MUTATION_AUDIT_LOG", str(audit_file))
    _write_assistant_config(tmp_path / "config", execute_mutates=True)
    monkeypatch.setenv("GOOGLE_ADS_ASSISTANT_CONFIG_DIR", str(tmp_path / "config"))

    script = tmp_path / "saved" / "code" / "noop.py"
    script.parent.mkdir(parents=True)
    script.write_text("print('noop')\n", encoding="utf-8")

    subprocess.run(
        [
            sys.executable,
            str(runner_path),
            "--script",
            str(script),
            "--dry-run",
            "--record-only",
            "--customer-id",
            "1111111111",
            "--operation",
            "Test op",
            "--consequences",
            "None",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    # 1. Injecting --script-args when dry-run had [] must fail with exit 2
    bad_args = subprocess.run(
        [
            sys.executable,
            str(runner_path),
            "--script",
            str(script),
            "--execute",
            "--script-args=--injected",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert bad_args.returncode == 2

    # 2. Overriding --customer-id must fail with exit 2
    bad_cid = subprocess.run(
        [
            sys.executable,
            str(runner_path),
            "--script",
            str(script),
            "--execute",
            "--customer-id",
            "9999999999",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert bad_cid.returncode == 2
    assert "customer" in (bad_cid.stdout + bad_cid.stderr).lower()


# ---------------------------------------------------------------------------
# P2-23: api_version_utils actionable error message when SDK unavailable
# ---------------------------------------------------------------------------


def test_p2_23_api_version_utils_actionable_error(monkeypatch: Any) -> None:
    import tests.api_version_utils as avu

    monkeypatch.delenv("GOOGLE_ADS_API_VERSION", raising=False)
    monkeypatch.setattr(avu, "detect_importable_api_version", lambda: None)
    monkeypatch.setattr(avu._config_init, "detect_latest_api_version", lambda: None)
    monkeypatch.setattr(
        avu._config_init,
        "resolve_active_api_version",
        MagicMock(side_effect=ValueError("Could not determine Google Ads API version")),
    )
    with pytest.raises(ValueError, match="GOOGLE_ADS_API_VERSION=vN"):
        avu.get_current_api_version()
    assert PREVIOUS_API_VERSION.startswith("v")


def test_config_init_new_guard_helpers_and_win32_branches(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Exercises win32, ANSI-C, mid-token quotes, glob matching, AST, and runner-injection branches."""
    import config.config_init as ci

    # 1. _decode_ansi_c_quotes escapes (\xNN, \uNNNN, \NNN, \n, \t, \\, \')
    assert "assistant_config" in ci._decode_ansi_c_quotes(r"$'config/assistant\x5fconfig'")
    assert "A" in ci._decode_ansi_c_quotes(r"$'\u0041\101\n\t\\'")

    # 2. _collapse_midtoken_quotes preserves -c'...' and KEY="val with spaces" while collapsing splits
    assert "last_dry_run.json" in ci._collapse_midtoken_quotes("echo x > saved/data/last_'d'ry_run.json")
    assert "KEY=" in ci._collapse_midtoken_quotes('K"E"Y="val with spaces"')
    assert "-c'" in ci._collapse_midtoken_quotes("python3 -c'print(1)'")

    # 3. _deobfuscate_posix_backslashes on simulated win32
    monkeypatch.setattr(ci.sys, "platform", "win32")
    assert ci._deobfuscate_posix_backslashes(r"saved\code\live.py") == r"saved\code\live.py"
    assert ci._deobfuscate_posix_backslashes(r"config\assistant_config") == r"config\assistant_config"
    assert "assistant_config" in ci._deobfuscate_posix_backslashes(r"config\assistant_\config")
    assert ci._deobfuscate_posix_backslashes(r"\python3") == "python3"
    assert ci._deobfuscate_posix_backslashes(r"t\ee") == "tee"
    assert "assistant_config" in ci._deobfuscate_posix_backslashes(r"config/assistant_\config")
    monkeypatch.undo()

    # 4. _glob_hits_protected_basenames directory wildcards & literal globs
    prot = ci._PROTECTED_CONFIG_BASENAMES
    assert "last_dry_run.json" in ci._glob_hits_protected_basenames("rm saved/data/*", prot)
    assert "mutation_audit.jsonl" in ci._glob_hits_protected_basenames("rm saved/logs/*", prot)
    assert "assistant_config" in ci._glob_hits_protected_basenames("rm config/*", prot)
    assert "assistant_config" in ci._glob_hits_protected_basenames("tee config/assistant_confi[g]", prot)

    # 5. _has_unsafe_test_runner_injection edge cases
    assert ci._has_unsafe_test_runner_injection("pytest -q tests/") is False
    assert ci._has_unsafe_test_runner_injection("pytest -k foo tests/") is False
    assert ci._has_unsafe_test_runner_injection("pytest -qp live tests/") is True
    assert ci._has_unsafe_test_runner_injection("python3 -m pytest --plugin live tests/") is True
    assert ci._has_unsafe_test_runner_injection("mypy --config-file=evil.ini plugins/") is True
    assert ci._has_unsafe_test_runner_injection("pytest 'unterminated") is True

    # 6. _is_strictly_ast_validate_only_true advanced AST branches (Match, Comprehension, Global, Import, Try, safe)
    safe_comp = (
        "def run():\n"
        "    global X\n"
        "    import json\n"
        "    from os import path\n"
        "    vals = [x for x in [1, 2] if x > 0]\n"
        "    d = {k: k for k in vals}\n"
        "    req = {'validate_only': True, 'customer_id': '1', 'operations': [op]}\n"
        "    try:\n"
        "        pass\n"
        "    except Exception as exc:\n"
        "        raise ValueError('x') from exc\n"
        "    assert d is not None, 'ok'\n"
        "    match vals:\n"
        "        case [a, *rest] if a > 0:\n"
        "            svc.mutate_campaigns(request=req)\n"
        "        case _:\n"
        "            return None\n"
    )
    assert ci._is_strictly_ast_validate_only_true([safe_comp]) is True

    # Unsafe Match binding overwrites req
    unsafe_match = (
        "req = {'validate_only': True, 'customer_id': '1', 'operations': [op]}\n"
        "match live_obj:\n"
        "    case req:\n"
        "        svc.mutate_campaigns(request=req)\n"
    )
    assert ci._is_strictly_ast_validate_only_true([unsafe_match]) is False

    # Unsafe dynamic import
    assert ci._is_strictly_ast_validate_only_true(["import importlib\nsvc.mutate_campaigns(validate_only=True)\n"]) is False
    assert ci._is_strictly_ast_validate_only_true(["from functools import partial\nsvc.mutate_campaigns(validate_only=True)\n"]) is False

    # 7. _extract_python_c_snippets combined short flags (-uc, -c'...')
    assert ci._extract_python_c_snippets("python3 -uc 'print(1)'") == ["print(1)"]
    assert ci._extract_python_c_snippets("python3 -c'print(2)'") == ["print(2)"]

    # 8. _is_readonly_set_financial_limits_cmd branches
    assert ci._is_readonly_set_financial_limits_cmd("python3 set_financial_limits.py --show --json") is True
    assert ci._is_readonly_set_financial_limits_cmd("python3 set_financial_limits.py --config-dir /tmp --show") is True
    assert ci._is_readonly_set_financial_limits_cmd("python3 set_financial_limits.py --config-dir=/tmp --list") is True
    assert ci._is_readonly_set_financial_limits_cmd("python3 set_financial_limits.py --config-dir") is False
    assert ci._is_readonly_set_financial_limits_cmd("python3 set_financial_limits.py --reset-all") is False
    assert ci._is_readonly_set_financial_limits_cmd("python3 set_financial_limits.py --show > /tmp/x") is False

    # 9. _update_receipt_hook_metadata_locked local lock fallback (rm_mod=None) & dry-run update
    rec_path = tmp_path / "last_dry_run.json"
    rec_path.write_text(
        json.dumps({"receipt_id": "rid-1", "status": "DRY_RUN_PASSED"}), encoding="utf-8"
    )
    assert (
        ci._update_receipt_hook_metadata_locked(
            str(rec_path), "rid-1", {"hook_prompted_at_iso": "2026-11-24T00:00:00Z"}, rm_mod=None
        )
        is True
    )
    updated = json.loads(rec_path.read_text(encoding="utf-8"))
    assert updated["hook_prompted_at_iso"] == "2026-11-24T00:00:00Z"
    # Mismatched receipt_id is ignored
    assert (
        ci._update_receipt_hook_metadata_locked(
            str(rec_path), "rid-other", {"hook_prompted_at_iso": "other"}, rm_mod=None
        )
        is False
    )


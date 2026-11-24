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

"""Offline regression tests for execute-mutation review findings.

Covers: Layer 4 failed-RPC recording (#8) and grpc.aio patching (#36), strict
TOML flag parsing (#17), customer ID mismatch refusal (#18), bidirectional
amount drift (#19), MultiPartyAuthReview classification and unclassified
services (#20), targeted --reject (#21), SUCCESS + approval.decision audit
status (#22), version resolution in create_*.py (#24), and email masking in
stored receipts/audit records (#32). No live API calls; all files go to tmp.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import types
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "google-ads-api-developer-assistant"
SCRIPTS_DIR = PLUGIN_ROOT / "skills" / "execute-mutation" / "scripts"
RUN_MUTATION_PATH = SCRIPTS_DIR / "run_mutation.py"


def _load(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, str(path))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    prev = sys.modules.get(name)
    sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    finally:
        if prev is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = prev
    return mod


@pytest.fixture(name="rm")
def fixture_rm() -> Any:
    return _load(RUN_MUTATION_PATH, "run_mutation_regressions_mod")


@pytest.fixture(name="sandbox")
def fixture_sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolates receipts, audit logs and config under tmp_path."""
    (tmp_path / "saved" / "data").mkdir(parents=True)
    (tmp_path / "saved" / "logs").mkdir(parents=True)
    (tmp_path / "saved" / "code").mkdir(parents=True)
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    (cfg_dir / "assistant_config").write_text("execute_mutates = false\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "GOOGLE_ADS_MUTATION_RECEIPT_PATH",
        str(tmp_path / "saved" / "data" / "last_dry_run.json"),
    )
    monkeypatch.setenv(
        "GOOGLE_ADS_MUTATION_AUDIT_LOG",
        str(tmp_path / "saved" / "logs" / "mutation_audit.jsonl"),
    )
    monkeypatch.setenv("GOOGLE_ADS_ASSISTANT_CONFIG_DIR", str(cfg_dir))
    monkeypatch.setenv("GOOGLE_ADS_EXECUTE_MUTATES", "false")
    monkeypatch.delenv("GOOGLE_ADS_ALLOW_TIER1_FINANCIAL_MUTATES", raising=False)
    return tmp_path


def _audit_lines(sandbox: Path) -> list[dict[str, Any]]:
    log = sandbox / "saved" / "logs" / "mutation_audit.jsonl"
    if not log.exists():
        return []
    return [json.loads(x) for x in log.read_text().splitlines() if x.strip()]


def _receipt_path(sandbox: Path) -> Path:
    return sandbox / "saved" / "data" / "last_dry_run.json"


def _write_script(sandbox: Path, name: str, body: str = "print('ok')\n") -> Path:
    p = sandbox / "saved" / "code" / name
    p.write_text(body)
    return p


def _label_call(cid: str = "1234567890") -> dict[str, Any]:
    return {
        "service": "LabelService",
        "method": "mutate_labels",
        "request_payload": {
            "customer_id": cid,
            "operations": [{"create": {"name": "x"}}],
            "validate_only": True,
        },
    }


# ---------------------------------------------------------------------------
# #8 / #36 Layer 4 interceptor
# ---------------------------------------------------------------------------


class _Details:
    def __init__(self, method: str) -> None:
        self.method = method


_LABEL_METHOD = "/google.ads.googleads.v24.services.LabelService/MutateLabels"


def test_layer4_records_failed_rpc_returned_by_continuation(rm: Any) -> None:
    grpc = pytest.importorskip("grpc")

    class _FakeRpcError(grpc.RpcError, grpc.Call):  # type: ignore[misc]
        def code(self) -> Any:
            return grpc.StatusCode.INVALID_ARGUMENT

        def details(self) -> str:
            return "bad request"

        def initial_metadata(self) -> Any:
            return ()

        def trailing_metadata(self) -> Any:
            return ()

        def time_remaining(self) -> Any:
            return None

        def cancel(self) -> bool:
            return False

        def is_active(self) -> bool:
            return False

        def add_callback(self, callback: Any) -> bool:
            return False

    captured: list[dict[str, Any]] = []
    ic = rm.FinancialGuardrailInterceptor(captured)
    err = _FakeRpcError()
    resp = ic.intercept_unary_unary(
        lambda d, r: err, _Details(_LABEL_METHOD), {"validate_only": True}
    )
    assert resp is err
    assert captured[-1]["status"] == "FAILED"
    assert "INVALID_ARGUMENT" in captured[-1]["error"]
    assert "bad request" in captured[-1]["error"]


def test_layer4_records_failed_outcome_by_code_and_exception(rm: Any) -> None:
    grpc = pytest.importorskip("grpc")

    class _Outcome:
        def __init__(self, code: Any, exc: Any) -> None:
            self._code, self._exc = code, exc

        def code(self) -> Any:
            return self._code

        def exception(self) -> Any:
            return self._exc

        def details(self) -> str:
            return "denied"

    captured: list[dict[str, Any]] = []
    ic = rm.FinancialGuardrailInterceptor(captured)
    ic.intercept_unary_unary(
        lambda d, r: _Outcome(grpc.StatusCode.PERMISSION_DENIED, None),
        _Details(_LABEL_METHOD),
        {"validate_only": True},
    )
    assert captured[-1]["status"] == "FAILED"

    ok = _Outcome(grpc.StatusCode.OK, None)
    ic.intercept_unary_unary(
        lambda d, r: ok, _Details(_LABEL_METHOD), {"validate_only": True}
    )
    assert captured[-1]["status"] == "SUCCESS"
    assert captured[-1]["error"] is None


def test_layer4_raised_rpc_error_recorded_and_reraised(rm: Any) -> None:
    captured: list[dict[str, Any]] = []
    ic = rm.FinancialGuardrailInterceptor(captured)

    def _boom(d: Any, r: Any) -> Any:
        raise RuntimeError("transport down")

    with pytest.raises(RuntimeError):
        ic.intercept_unary_unary(_boom, _Details(_LABEL_METHOD), {"validate_only": True})
    assert captured[-1]["status"] == "FAILED"
    assert "transport down" in captured[-1]["error"]


def test_layer4_aio_interceptor_blocks_and_records(rm: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("grpc")
    monkeypatch.setenv("GOOGLE_ADS_EXECUTE_MUTATES", "false")
    captured: list[dict[str, Any]] = []
    aio_ic = rm.AioFinancialGuardrailInterceptor(
        rm.FinancialGuardrailInterceptor(captured)
    )

    class _Call:
        def __await__(self) -> Any:
            if False:  # pragma: no cover
                yield
            return {"ok": True}

    async def _cont(d: Any, r: Any) -> Any:
        return _Call()

    # validate_only=True passes and is recorded as SUCCESS.
    asyncio.run(aio_ic.intercept_unary_unary(_cont, _Details(_LABEL_METHOD), {"validate_only": True}))
    assert captured[-1]["status"] == "SUCCESS"
    # A live call with execute_mutates=false is blocked.
    with pytest.raises(PermissionError):
        asyncio.run(aio_ic.intercept_unary_unary(_cont, _Details(_LABEL_METHOD), {}))
    assert captured[-1]["status"] == "BLOCKED_MUTATES_DISABLED"


def test_layer4_patches_grpc_aio_channels(rm: Any, tmp_path: Path) -> None:
    pytest.importorskip("grpc")
    probe = tmp_path / "probe.py"
    out = tmp_path / "out.json"
    probe.write_text(
        "import json, sys, grpc, grpc.aio\n"
        f"json.dump({{'patched': getattr(grpc.aio.insecure_channel, '__name__', '')}}, open({str(out)!r}, 'w'))\n"
    )
    # _run_target_script_with_interception is the target-script runner: it may purge and
    # re-import every google.* module (to honor a script-local SDK). Doing that inside the
    # pytest process re-registers upb descriptors and segfaults later tests, so run it in
    # a child interpreter exactly as run_mutation.py does.
    runner = (
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('rm_child', {str(RUN_MUTATION_PATH)!r})\n"
        "m = importlib.util.module_from_spec(spec); sys.modules['rm_child'] = m\n"
        "spec.loader.exec_module(m)\n"
        f"m._run_target_script_with_interception({str(probe)!r}, [], {str(tmp_path / 'trace.json')!r})\n"
        "import grpc.aio\n"
        "assert grpc.aio.insecure_channel.__name__ != '_hooked_aio_insecure', 'patch leaked'\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", runner], capture_output=True, text=True, timeout=120, check=False
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert json.loads(out.read_text())["patched"] == "_hooked_aio_insecure"


# ---------------------------------------------------------------------------
# #17 strict TOML parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fn_name,key",
    [
        ("parse_execute_mutates_value", "execute_mutates"),
        ("parse_allow_tier1_financial_mutates_value", "allow_tier1_financial_mutates"),
    ],
)
def test_bare_true_line_does_not_enable_flags(rm: Any, fn_name: str, key: str) -> None:
    fn = getattr(rm, fn_name)
    # Valid TOML where the bare `true` is only a string value elsewhere.
    assert fn('api_version = "v24"\nnote = """\ntrue\n"""\n') is None
    assert fn(f"{key} = false\nnote = '''\ntrue\n'''\n") is False
    assert fn(f"{key} = true\n") is True
    assert fn(f"[section]\n{key} = true\n") is None  # not top-level
    # Not valid TOML (env var style values) still parse via fallback.
    assert fn("true") is True
    assert fn("FALSE") is False


# ---------------------------------------------------------------------------
# #18 customer ID mismatch, #19 drift
# ---------------------------------------------------------------------------


def test_customer_id_mismatch_refuses_receipt(rm: Any, sandbox: Path) -> None:
    script = _write_script(sandbox, "label.py")
    with pytest.raises(ValueError, match="CUSTOMER ID MISMATCH"):
        rm.write_dry_run_receipt(
            customer_id="1111111111",
            operation_summary="LabelService.mutate_labels create label",
            before_state="none",
            after_state="label x",
            consequences=["Creates label x"],
            reversibility="REVERSIBLE",
            script_path=str(script),
            rpc_calls=[_label_call("2222222222")],
        )
    assert not _receipt_path(sandbox).exists()


def test_record_only_without_payload_still_writes_receipt(sandbox: Path) -> None:
    script = _write_script(
        sandbox,
        "label.py",
        "# LabelService.mutate_labels customers/2222222222/labels/1\nprint('ok')\n",
    )
    env = dict(os.environ)
    proc = subprocess.run(
        [
            sys.executable,
            str(RUN_MUTATION_PATH),
            "--script",
            str(script),
            "--dry-run",
            "--record-only",
            "--customer-id",
            "1111111111",
            "--operation",
            "LabelService.mutate_labels on customers/2222222222/labels/1",
            "--before",
            "none",
            "--after",
            "label",
            "--consequences",
            "Creates label",
            "--reversibility",
            "REVERSIBLE",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(sandbox),
        check=False,
    )
    # --record-only has no RPC payload, so no mismatch is detectable: receipt OK.
    assert proc.returncode == 0, proc.stderr


def test_customer_id_mismatch_cli_path_via_main(rm: Any, sandbox: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    script = _write_script(sandbox, "label.py")
    fake_result = types.SimpleNamespace(returncode=0, stdout="ok", stderr="")
    monkeypatch.setattr(
        rm,
        "_execute_script_subprocess",
        lambda *a, **k: (fake_result, "t0", "t1", 1.0, [_label_call("2222222222")]),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_mutation.py", "--script", str(script), "--dry-run",
            "--customer-id", "1111111111",
            "--operation", "LabelService.mutate_labels create label",
            "--before", "none", "--after", "label x",
            "--consequences", "Creates label x", "--reversibility", "REVERSIBLE",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        rm.main()
    assert exc.value.code == 2
    assert "CUSTOMER ID MISMATCH" in capsys.readouterr().err
    assert not _receipt_path(sandbox).exists()
    assert _audit_lines(sandbox)[-1]["status"] == "BLOCKED_CUSTOMER_ID_MISMATCH"


def _budget_call(micros: int) -> dict[str, Any]:
    return {
        "service": "CampaignBudgetService",
        "method": "mutate_campaign_budgets",
        "request_payload": {
            "customer_id": "1234567890",
            "operations": [{"update": {"amount_micros": micros}}],
        },
    }


def test_amount_drift_flagged_in_both_directions(rm: Any) -> None:
    # CLI states $500 but payload is $50 (previously passed).
    low = rm.extract_payload_bound_facts(
        rpc_calls=[_budget_call(50_000_000)],
        cli_customer_id="1234567890",
        cli_after_state="Budget $500.00/day",
    )
    assert low["micro_unit_drift_detected"] is True
    assert low["micro_unit_drift_fields"][0]["field"] == "amount_micros"
    high = rm.extract_payload_bound_facts(
        rpc_calls=[_budget_call(500_000_000)],
        cli_customer_id="1234567890",
        cli_after_state="Budget $50.00/day",
    )
    assert high["micro_unit_drift_detected"] is True
    same = rm.extract_payload_bound_facts(
        rpc_calls=[_budget_call(50_000_000)],
        cli_customer_id="1234567890",
        cli_after_state="Budget $50.00/day",
    )
    assert same["micro_unit_drift_detected"] is False
    assert same["micro_unit_drift_fields"] == []


def test_amount_drift_per_field(rm: Any) -> None:
    call = {
        "service": "AdGroupService",
        "method": "mutate_ad_groups",
        "request_payload": {
            "customer_id": "1234567890",
            "operations": [
                {"create": {"cpc_bid_micros": 1_000_000, "target_cpa_micros": 90_000_000}}
            ],
        },
    }
    facts = rm.extract_payload_bound_facts(
        rpc_calls=[call],
        cli_customer_id="1234567890",
        cli_after_state="CPC $1.00 and target CPA $9.00",
    )
    assert facts["micro_unit_drift_detected"] is True
    assert [d["field"] for d in facts["micro_unit_drift_fields"]] == ["target_cpa_micros"]


# ---------------------------------------------------------------------------
# #20 MultiPartyAuthReview + unclassified services
# ---------------------------------------------------------------------------


def test_multi_party_auth_review_classified_as_ato(rm: Any) -> None:
    call = {
        "service": "MultiPartyAuthReviewService",
        "method": "resolve_multi_party_auth_review",
        "request_payload": {"customer_id": "1234567890"},
    }
    cls = rm.classify_mutation(rpc_calls=[call])
    assert cls["tier_number"] == 3
    assert cls["classification_category"] == "Account Structure & Linking"
    assert cls["is_unclassified"] is False
    ato = rm.extract_ato_escalation_details(rpc_calls=[call])
    assert ato["is_ato_risk"] is True
    assert "multi_party_auth_review_service" in ato["services"]


def test_unknown_service_card_says_review_manually(rm: Any, sandbox: Path) -> None:
    call = {
        "service": "BrandNewFutureService",
        "method": "mutate_future_things",
        "request_payload": {"customer_id": "1234567890", "validate_only": True},
    }
    cls = rm.classify_mutation(rpc_calls=[call])
    assert cls["is_unclassified"] is True
    assert "brand_new_future_service" in cls["unclassified_services"]
    receipt = rm.write_dry_run_receipt(
        customer_id="1234567890",
        operation_summary="BrandNewFutureService.mutate_future_things",
        before_state="none",
        after_state="thing",
        consequences=["Creates a thing"],
        reversibility="REVERSIBLE",
        rpc_calls=[call],
    )
    card = receipt["rendered_verification_card"]
    assert "unclassified service, review manually" in card
    assert "$0.00 direct spend impact" not in card


def test_known_tier3_card_keeps_zero_spend_line(rm: Any, sandbox: Path) -> None:
    receipt = rm.write_dry_run_receipt(
        customer_id="1234567890",
        operation_summary="LabelService.mutate_labels create label",
        before_state="none",
        after_state="label x",
        consequences=["Creates label x"],
        reversibility="REVERSIBLE",
        rpc_calls=[_label_call()],
    )
    assert "$0.00 direct spend impact" in receipt["rendered_verification_card"]
    assert "unclassified service" not in receipt["rendered_verification_card"]


# ---------------------------------------------------------------------------
# #21 targeted --reject, #22 audit status
# ---------------------------------------------------------------------------


def _seed_receipt(sandbox: Path, **overrides: Any) -> dict[str, Any]:
    data = {
        "receipt_id": "r-1",
        "status": "DRY_RUN_PASSED",
        "customer_id": "1234567890",
        "operation_summary": "LabelService.mutate_labels",
        "consequences": ["Creates label"],
        "reversibility": "REVERSIBLE",
        "script_path": "",
        "script_sha256": "",
    }
    data.update(overrides)
    _receipt_path(sandbox).write_text(json.dumps(data))
    return data


def test_reject_only_touches_matching_pending_receipt(rm: Any, sandbox: Path) -> None:
    target = _write_script(sandbox, "target.py", "print('target')\n")
    other = _write_script(sandbox, "other.py", "print('other')\n")
    _seed_receipt(
        sandbox,
        script_path=str(other),
        script_sha256=rm.compute_file_sha256(str(other)),
    )
    res = rm.reject_dry_run_receipt(script_path=str(target), reason="no")
    assert res["rejected_count"] == 0
    assert res["status"] == "NO_PENDING_RECEIPT"
    assert json.loads(_receipt_path(sandbox).read_text())["status"] == "DRY_RUN_PASSED"
    assert _audit_lines(sandbox) == []

    res = rm.reject_dry_run_receipt(script_path=str(other), reason="user said no")
    assert res["rejected_count"] == 1
    assert res["status"] == "REJECTED"
    assert res["receipt_id"] == "r-1"
    stored = json.loads(_receipt_path(sandbox).read_text())
    assert stored["status"] == "REJECTED"
    audit = _audit_lines(sandbox)[-1]
    assert audit["status"] == "HUMAN_REJECTED"
    assert audit["approval"]["decision"] == "HUMAN_REJECTED"
    assert audit["receipt_id"] == "r-1"
    assert audit["request"]["script_path"] == str(other)


def test_reject_matches_by_sha_and_skips_executed(rm: Any, sandbox: Path) -> None:
    script = _write_script(sandbox, "s.py", "print('s')\n")
    sha = rm.compute_file_sha256(str(script))
    _seed_receipt(sandbox, status="EXECUTED", script_path=str(script), script_sha256=sha)
    assert rm.reject_dry_run_receipt(script_path=str(script))["rejected_count"] == 0
    assert json.loads(_receipt_path(sandbox).read_text())["status"] == "EXECUTED"

    _seed_receipt(sandbox, script_path="/moved/elsewhere/s.py", script_sha256=sha)
    assert rm.reject_dry_run_receipt(script_path=str(script))["rejected_count"] == 1


def test_reject_cli_exits_nonzero_when_nothing_rejected(sandbox: Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(RUN_MUTATION_PATH), "--reject", "--rejection-reason", "no"],
        capture_output=True,
        text=True,
        env=dict(os.environ),
        cwd=str(sandbox),
        check=False,
    )
    assert proc.returncode == 1
    assert "nothing was rejected" in proc.stderr
    _seed_receipt(sandbox)
    proc = subprocess.run(
        [sys.executable, str(RUN_MUTATION_PATH), "--reject", "--rejection-reason", "no"],
        capture_output=True,
        text=True,
        env=dict(os.environ),
        cwd=str(sandbox),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["rejected_count"] == 1


def _audit_kwargs(**overrides: Any) -> dict[str, Any]:
    kw: dict[str, Any] = {
        "phase": "EXECUTE",
        "status": "SUCCESS",
        "customer_id": "1234567890",
        "operation_summary": "LabelService.mutate_labels",
        "before_state": "",
        "after_state": "",
        "consequences": ["Creates label"],
        "reversibility": "REVERSIBLE",
        "script_path": None,
        "script_sha256": "",
        "validate_only": False,
        "request_sent_at_iso": "t0",
        "response_received_at_iso": "t1",
        "duration_ms": 1.0,
        "exit_code": 0,
        "stdout": "",
        "stderr": "",
    }
    kw.update(overrides)
    return kw


def test_audit_success_status_with_approval_decision(rm: Any, sandbox: Path) -> None:
    rec = rm.append_mutation_audit_log(**_audit_kwargs(approval_decision="HUMAN_APPROVED"))
    assert rec["status"] == "SUCCESS"
    assert rec["execution_status"] == "SUCCESS"
    assert rec["approval"]["decision"] == "HUMAN_APPROVED"
    legacy = rm.append_mutation_audit_log(**_audit_kwargs(status="HUMAN_APPROVED"))
    assert legacy["execution_status"] == "SUCCESS"
    assert legacy["approval"]["decision"] == "HUMAN_APPROVED"


def test_main_execute_success_logs_success_status(rm: Any, sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = _write_script(sandbox, "label.py")
    monkeypatch.setenv("GOOGLE_ADS_EXECUTE_MUTATES", "true")
    receipt = {
        "receipt_id": "r-ok",
        "status": "DRY_RUN_PASSED",
        "customer_id": "1234567890",
        "operation_summary": "LabelService.mutate_labels",
        "consequences": ["Creates label"],
        "reversibility": "REVERSIBLE",
        "tier_number": 3,
        "script_path": str(script),
    }
    monkeypatch.setattr(rm, "load_and_verify_receipt", lambda **k: (True, "ok", receipt))
    fake = types.SimpleNamespace(returncode=0, stdout="done", stderr="")
    monkeypatch.setattr(rm, "_execute_script_subprocess", lambda *a, **k: (fake, "t0", "t1", 1.0, []))
    monkeypatch.setattr(sys, "argv", ["run_mutation.py", "--script", str(script), "--execute"])
    rm.main()
    entry = _audit_lines(sandbox)[-1]
    assert entry["status"] == "SUCCESS"
    assert entry["approval"]["decision"] == "HUMAN_APPROVED"


# ---------------------------------------------------------------------------
# #32 email masking
# ---------------------------------------------------------------------------


def test_emails_masked_in_stored_receipt_and_audit(rm: Any, sandbox: Path) -> None:
    call = {
        "service": "CustomerUserAccessInvitationService",
        "method": "mutate_customer_user_access_invitation",
        "request_payload": {
            "customer_id": "1234567890",
            "operation": {"create": {"email_address": "jane.doe@example.com", "access_role": "ADMIN"}},
        },
    }
    receipt = rm.write_dry_run_receipt(
        customer_id="1234567890",
        operation_summary="CustomerUserAccessInvitationService invite",
        before_state="none",
        after_state="invite sent",
        consequences=["Grants ADMIN access"],
        reversibility="REVERSIBLE",
        rpc_calls=[call],
    )
    # On-screen card (returned in memory) shows the full email.
    assert "jane.doe@example.com" in receipt["rendered_verification_card"]
    stored = json.loads(_receipt_path(sandbox).read_text())
    assert stored["ato_escalation"]["emails"] == ["j***@example.com"]
    assert "jane.doe@example.com" not in stored["rendered_verification_card"]
    assert "j***@example.com" in stored["rendered_verification_card"]
    # The stored RPC payload is masked too, so a card regenerated from the
    # stored receipt (no script source with the literal) stays masked.
    regenerated = rm.format_verification_card(stored)
    assert "jane.doe@example.com" not in regenerated
    assert "j***@example.com" in regenerated

    rm.append_mutation_audit_log(**_audit_kwargs(rpc_calls=[call], receipt=receipt))
    raw = (sandbox / "saved" / "logs" / "mutation_audit.jsonl").read_text()
    assert "jane.doe@example.com" not in raw
    assert "j***@example.com" in raw


def test_mask_email_helper(rm: Any) -> None:
    assert rm.mask_email("contact a.b+c@sub.example.org now") == "contact a***@sub.example.org now"
    assert rm.mask_email("no email here") == "no email here"


# ---------------------------------------------------------------------------
# #24 create_*.py version resolution
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "script", ["create_account", "create_ad", "create_ad_group", "create_campaign"]
)
def test_create_scripts_use_shared_resolver(script: str, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load(SCRIPTS_DIR / f"{script}.py", f"reg_{script}")
    assert not hasattr(mod, "_resolve_default_api_version")
    cfg = mod._load_config_init()
    assert hasattr(cfg, "resolve_active_api_version")
    monkeypatch.setenv("GOOGLE_ADS_API_VERSION", "24")
    assert mod._normalize_api_version(None) == "v24"
    assert mod._normalize_api_version("v25") == "v25"
    monkeypatch.setenv("GOOGLE_ADS_API_VERSION", "../../x")
    with pytest.raises(ValueError):
        mod._normalize_api_version(None)
    with pytest.raises(ValueError):
        mod._normalize_api_version("latest")


@pytest.mark.parametrize(
    "script", ["create_account", "create_ad", "create_ad_group", "create_campaign"]
)
def test_create_scripts_reject_invalid_version_via_argparse(script: str, tmp_path: Path) -> None:
    env = dict(os.environ)
    env["GOOGLE_ADS_API_VERSION"] = "latest"
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / f"{script}.py"), "--help"],
        capture_output=True, text=True, env=env, cwd=str(tmp_path), check=False,
    )
    assert proc.returncode == 0
    # Required args differ per script; pass an invalid explicit version and let
    # argparse report either the missing args or the version error, never a traceback.
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / f"{script}.py"), "--api_version", "latest"],
        capture_output=True, text=True, env=env, cwd=str(tmp_path), check=False,
    )
    assert proc.returncode == 2
    assert "Traceback" not in proc.stderr


def test_dry_run_rpc_payload_emails_masked_and_receipt_still_verifies(
    rm: Any, sandbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = _write_script(sandbox, "invite.py", "print('invite')\n")
    payload = {
        "customer_id": "1234567890",
        "operation": {"create": {"email_address": "jane.doe@example.com", "access_role": "STANDARD"}},
        "validate_only": True,
    }
    call = {
        "service": "CustomerUserAccessInvitationService",
        "method": "mutate_customer_user_access_invitation",
        "request_payload": payload,
    }
    unmasked_sha = rm.compute_mutate_request_sha256(call["service"], call["method"], payload)
    rm.write_dry_run_receipt(
        customer_id="1234567890",
        operation_summary="CustomerUserAccessInvitationService invite",
        before_state="none",
        after_state="invite sent",
        consequences=["Grants STANDARD access"],
        reversibility="REVERSIBLE",
        script_path=str(script),
        rpc_calls=[call],
    )
    raw = _receipt_path(sandbox).read_text()
    assert "jane.doe@example.com" not in raw
    stored = json.loads(raw)
    stored_call = stored["dry_run_rpc_calls"][0]
    assert stored_call["request_payload_masked"] is True
    assert stored_call["request_payload"]["operation"]["create"]["email_address"] == "j***@example.com"
    assert stored_call["request_sha256"] == unmasked_sha
    assert stored["request_sha256_list"] == [unmasked_sha]

    # run_mutation's own --execute verification accepts the masked receipt.
    ok, msg, _ = rm.load_and_verify_receipt(script_path=str(script))
    assert ok, msg

    # A masked entry without its recorded hash is refused.
    del stored["dry_run_rpc_calls"][0]["request_sha256"]
    _receipt_path(sandbox).write_text(json.dumps(stored))
    ok, msg, _ = rm.load_and_verify_receipt(script_path=str(script))
    assert not ok
    assert "masked" in msg

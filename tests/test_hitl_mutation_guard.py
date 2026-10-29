"""Unit tests for the 4-Step HITL Mutation & Consequence Verification Guard."""

from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path
import sys
from typing import Any
import pytest

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parent.parent
        / "plugins"
        / "google-ads-api-developer-assistant"
    ),
)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.config_init import evaluate_mutation_guard


@pytest.fixture(autouse=True)
def _enable_mutates_for_hitl_tests(monkeypatch: Any) -> None:
    """Enables execute_mutates=true for general HITL workflow tests unless overridden."""
    monkeypatch.setenv("GOOGLE_ADS_EXECUTE_MUTATES", "execute_mutates=true")


def _load_run_mutation_module() -> Any:
    script_path = (
        Path(__file__).resolve().parent.parent
        / "plugins"
        / "google-ads-api-developer-assistant"
        / "skills"
        / "execute-mutation"
        / "scripts"
        / "run_mutation.py"
    )
    spec = spec_from_file_location("run_mutation", str(script_path))
    assert spec is not None and spec.loader is not None
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_readonly_and_dry_run_commands_allowed(tmp_path: Path) -> None:
    """Read-only scripts and explicit validate_only=True dry-runs must be allowed."""
    # 1. Read-only skill script
    decision, reason = evaluate_mutation_guard(
        "python3 skills/validate-gaql/scripts/validate_gaql.py --customer_id 1234567890"
    )
    assert decision == "allow"
    assert reason is None

    # 2. Explicit --dry-run on run_mutation.py
    decision, reason = evaluate_mutation_guard(
        "python3 skills/execute-mutation/scripts/run_mutation.py --script saved/code/budget.py --dry-run"
    )
    assert decision == "allow"
    assert reason is None

    # 3. Script containing validate_only=True
    dry_run_script = tmp_path / "dry_run_budget.py"
    dry_run_script.write_text(
        "def run(service, req):\n"
        "    req.validate_only = True\n"
        "    return service.mutate_campaign_budgets(request=req)\n",
        encoding="utf-8",
    )
    decision, reason = evaluate_mutation_guard(f"python3 {dry_run_script}")
    assert decision == "allow"
    assert reason is None


def test_unverified_live_mutation_denied_then_force_ask_with_receipt(
    tmp_path: Path,
) -> None:
    """Live mutations without a dry-run receipt are denied; with a valid receipt they trigger force_ask."""
    run_mutation = _load_run_mutation_module()

    # Clean any existing receipts before testing denial
    for receipt_path in run_mutation.get_receipt_paths():
        if os.path.isfile(receipt_path):
            os.remove(receipt_path)

    live_script = tmp_path / "live_budget.py"
    live_script.write_text(
        "def run(service, req):\n"
        "    req.validate_only = False\n"
        "    return service.mutate_campaign_budgets(request=req)\n",
        encoding="utf-8",
    )

    # 1. Without a dry-run receipt, direct execution is hard-blocked ("deny")
    decision, reason = evaluate_mutation_guard(f"python3 {live_script} --execute")
    assert decision == "deny"
    assert reason is not None
    assert "BLOCKED BY HITL MUTATION GUARD" in reason

    # 2. Write a signed validate_only=True dry-run receipt with consequence disclosures
    receipt = run_mutation.write_dry_run_receipt(
        customer_id="1234567890",
        operation_summary="Update CampaignBudget (customers/1234567890/campaignBudgets/111)",
        before_state="$50.00/day (50,000,000 micros)",
        after_state="$250.00/day (250,000,000 micros)",
        consequences=[
            "Daily budget cap increases by +$200.00/day (+400%)",
            "Max monthly spend exposure increases to ~$7,600.00/month",
        ],
        reversibility="REVERSIBLE",
        script_path=str(live_script),
        dry_run_output="validate_only=True dry-run succeeded",
    )
    assert receipt["status"] == "DRY_RUN_PASSED"

    # 3. With a valid receipt, execution triggers "force_ask" with the consequence summary
    decision, reason = evaluate_mutation_guard(
        f"python3 skills/execute-mutation/scripts/run_mutation.py --script {live_script} --execute"
    )
    assert decision == "force_ask"
    assert reason is not None
    assert "1234567890" in reason
    assert "Daily budget cap increases by +$200.00/day" in reason

    # 4. Tampering with the script after the dry-run invalidates the SHA-256 hash and blocks execution
    live_script.write_text(
        "def run(service, req):\n"
        "    req.validate_only = False\n"
        "    # Tampered payload\n"
        "    return service.mutate_campaign_budgets(request=req)\n",
        encoding="utf-8",
    )
    decision, reason = evaluate_mutation_guard(f"python3 {live_script} --execute")
    assert decision == "deny"
    assert reason is not None
    assert "SHA-256 mismatch" in reason

    # Cleanup test receipts
    for receipt_path in run_mutation.get_receipt_paths():
        if os.path.isfile(receipt_path):
            os.remove(receipt_path)


def test_mutation_audit_trail_end_to_end(tmp_path: Path, monkeypatch: Any) -> None:
    """Verifies that dry-run, PreToolUse hook approval prompt, and live execution write a complete audit trail."""
    import json
    import subprocess

    run_mutation = _load_run_mutation_module()
    audit_log_file = tmp_path / "mutation_audit.jsonl"
    monkeypatch.setenv("GOOGLE_ADS_MUTATION_AUDIT_LOG", str(audit_log_file))

    config_yaml = tmp_path / "google-ads.yaml"
    config_yaml.write_text(
        'developer_token: "super_secret_dev_token"\n'
        'client_id: "1234567890-abcdef.apps.googleusercontent.com"\n'
        'client_secret: "super_secret_client_secret"\n'
        'refresh_token: "super_secret_refresh_token"\n'
        'login_customer_id: "9998887776"\n'
        "ads_assistant: 4.1.0\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GOOGLE_ADS_CONFIGURATION_FILE_PATH", str(config_yaml))

    for receipt_path in run_mutation.get_receipt_paths():
        if os.path.isfile(receipt_path):
            os.remove(receipt_path)

    mutation_script = tmp_path / "update_budget.py"
    mutation_script.write_text(
        "import argparse\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--customer-id', default='')\n"
        "parser.add_argument('--dry-run', action='store_true')\n"
        "parser.add_argument('--execute', action='store_true')\n"
        "args = parser.parse_args()\n"
        "if args.execute:\n"
        "    print('Mutated resource: customers/1234567890/campaignBudgets/111')\n"
        "else:\n"
        "    print('validate_only=True dry-run succeeded')\n",
        encoding="utf-8",
    )

    runner_path = (
        Path(__file__).resolve().parent.parent
        / "plugins"
        / "google-ads-api-developer-assistant"
        / "skills"
        / "execute-mutation"
        / "scripts"
        / "run_mutation.py"
    )

    # Phase 1: Run --dry-run
    dry_run_proc = subprocess.run(
        [
            sys.executable,
            str(runner_path),
            "--script",
            str(mutation_script),
            "--dry-run",
            "--customer-id",
            "1234567890",
            "--operation",
            "CampaignBudgetService.MutateCampaignBudgets on campaignBudgets/111",
            "--before",
            "$50.00/day (ENABLED)",
            "--after",
            "$75.00/day (ENABLED)",
            "--consequences",
            "Daily budget increases by +$25.00/day (+50%); Max monthly exposure $2,280.00",
            "--reversibility",
            "REVERSIBLE",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "GOOGLE ADS API MUTATION & CONSEQUENCE VERIFICATION CARD" in dry_run_proc.stdout

    # Phase 2: PreToolUse hook stamps hook_prompted_at_iso and CLI session context
    hook_ctx = {
        "conversationId": "conv-uuid-1234",
        "transcriptPath": "/tmp/transcript.jsonl",
        "modelName": "gemini-2.5-pro",
    }
    decision, reason = evaluate_mutation_guard(
        f"python3 {runner_path} --script {mutation_script} --execute",
        hook_context=hook_ctx,
    )
    assert decision == "force_ask"
    assert reason is not None

    # Phase 3: User approves in CLI -> --execute runs
    exec_proc = subprocess.run(
        [
            sys.executable,
            str(runner_path),
            "--script",
            str(mutation_script),
            "--execute",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Mutated resource: customers/1234567890/campaignBudgets/111" in exec_proc.stdout

    # Verify audit log contents
    assert audit_log_file.is_file()
    if sys.platform != "win32":
        assert oct(os.stat(str(audit_log_file)).st_mode & 0o777) == "0o600"

    raw_content = audit_log_file.read_text(encoding="utf-8")
    assert "super_secret_dev_token" not in raw_content
    assert "super_secret_client_secret" not in raw_content
    assert "super_secret_refresh_token" not in raw_content

    lines = [json.loads(line) for line in raw_content.splitlines() if line.strip()]
    assert len(lines) == 2

    dry_entry, exec_entry = lines[0], lines[1]
    assert dry_entry["phase"] == "DRY_RUN"
    assert dry_entry["status"] == "DRY_RUN_PASSED"
    assert exec_entry["phase"] == "EXECUTE"
    assert exec_entry["status"] == "SUCCESS"
    assert dry_entry["receipt_id"] == exec_entry["receipt_id"]

    # 1. Who made the request
    actor = exec_entry["actor"]
    assert actor["os_user"]
    assert actor["login_customer_id"] == "9998887776"
    assert actor["target_customer_id"] == "1234567890"
    assert actor["auth_type"] == "oauth2"
    assert actor["client_id_masked"] == "12345678..."
    assert actor["cli_conversation_id"] == "conv-uuid-1234"
    assert actor["cli_transcript_path"] == "/tmp/transcript.jsonl"
    assert actor["model_name"] == "gemini-2.5-pro"

    # 2. Request timestamp & contents
    req = exec_entry["request"]
    assert req["sent_at_iso"]
    assert req["customer_id"] == "1234567890"
    assert req["validate_only"] is False
    assert req["script_sha256"] == run_mutation.compute_file_sha256(str(mutation_script))
    assert req["payload"]["operation_summary"].startswith(
        "CampaignBudgetService.MutateCampaignBudgets"
    )

    # 3. Approval timestamps & disclosed consequences
    approval = exec_entry["approval"]
    assert approval["dry_run_validated_at_iso"]
    assert approval["hook_prompted_at_iso"]
    assert approval["user_approved_at_iso"]
    assert (
        approval["dry_run_validated_at_iso"]
        <= approval["hook_prompted_at_iso"]
        <= approval["user_approved_at_iso"]
    )
    assert approval["before_state"] == "$50.00/day (ENABLED)"
    assert approval["after_state"] == "$75.00/day (ENABLED)"
    assert len(approval["consequences"]) == 2

    # 4. Response timestamp & contents
    resp = exec_entry["response"]
    assert resp["received_at_iso"] >= req["sent_at_iso"]
    assert resp["exit_code"] == 0
    assert "customers/1234567890/campaignBudgets/111" in resp["stdout"]

    for receipt_path in run_mutation.get_receipt_paths():
        if os.path.isfile(receipt_path):
            os.remove(receipt_path)


def test_rpc_service_interception_and_redaction() -> None:
    """Verifies that _wrap_service_for_audit captures request/response payloads, timestamps, and request_id."""
    run_mutation = _load_run_mutation_module()
    captured: list[dict[str, Any]] = []

    class FakeService:
        def mutate_campaign_budgets(self, request: Any = None) -> Any:
            return {
                "request_id": "req-abc-999",
                "results": [{"resource_name": "customers/123/campaignBudgets/456"}],
            }

    svc = run_mutation._wrap_service_for_audit(
        FakeService(), "CampaignBudgetService", captured
    )
    resp = svc.mutate_campaign_budgets(
        request={
            "customer_id": "123",
            "validate_only": False,
            "developer_token": "secret_should_be_redacted",
            "operations": [
                {
                    "update": {
                        "resource_name": "customers/123/campaignBudgets/456",
                        "amount_micros": 75000000,
                    }
                }
            ],
        }
    )
    assert resp["request_id"] == "req-abc-999"
    assert len(captured) == 1
    call = captured[0]
    assert call["service"] == "CampaignBudgetService"
    assert call["method"] == "mutate_campaign_budgets"
    assert call["sent_at_iso"] <= call["received_at_iso"]
    assert call["google_ads_request_id"] == "req-abc-999"
    assert call["request_payload"]["developer_token"] == "[REDACTED]"
    assert (
        call["request_payload"]["operations"][0]["update"]["amount_micros"]
        == 75000000
    )
    assert (
        call["response_payload"]["results"][0]["resource_name"]
        == "customers/123/campaignBudgets/456"
    )


def test_subprocess_google_ads_client_interception_and_failure_audit(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Verifies subprocess GoogleAdsClient.get_service interception and failure auditing."""
    import json
    import subprocess

    run_mutation = _load_run_mutation_module()
    audit_log_file = tmp_path / "mutation_audit_rpc.jsonl"
    monkeypatch.setenv("GOOGLE_ADS_MUTATION_AUDIT_LOG", str(audit_log_file))

    for receipt_path in run_mutation.get_receipt_paths():
        if os.path.isfile(receipt_path):
            os.remove(receipt_path)

    # Create a fake google.ads.googleads.client module in tmp_path so subprocess imports it
    pkg_dir = tmp_path / "google" / "ads" / "googleads"
    pkg_dir.mkdir(parents=True)
    (tmp_path / "google" / "__init__.py").write_text(
        "__path__ = __import__('pkgutil').extend_path(__path__, __name__)\n",
        encoding="utf-8",
    )
    (tmp_path / "google" / "ads" / "__init__.py").write_text(
        "__path__ = __import__('pkgutil').extend_path(__path__, __name__)\n",
        encoding="utf-8",
    )
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    (pkg_dir / "client.py").write_text(
        "import os\n"
        "class _FakeBudgetService:\n"
        "    def mutate_campaign_budgets(self, request=None):\n"
        "        if os.environ.get('FAKE_ADS_SIMULATE_FAILURE') == '1':\n"
        "            ex = RuntimeError('QuotaCheckError.ACCOUNT_INACTIVE')\n"
        "            ex.request_id = 'req-fail-500'\n"
        "            ex.failure = {'errors': [{'message': 'Account inactive', 'error_code': {'quota_error': 'ACCOUNT_INACTIVE'}}]}\n"
        "            raise ex\n"
        "        return {\n"
        "            'request_id': 'req-live-777',\n"
        "            'results': [{'resource_name': 'customers/1234567890/campaignBudgets/999'}],\n"
        "        }\n\n"
        "class GoogleAdsClient:\n"
        "    @classmethod\n"
        "    def load_from_storage(cls, path=None, version=None):\n"
        "        return cls()\n"
        "    def get_service(self, name, *args, **kwargs):\n"
        "        return _FakeBudgetService()\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PYTHONPATH", f"{tmp_path}{os.pathsep}{os.environ.get('PYTHONPATH', '')}")

    script_file = tmp_path / "rpc_script.py"
    script_file.write_text(
        "import argparse, os, sys\n"
        "from google.ads.googleads.client import GoogleAdsClient\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--customer-id', default='1234567890')\n"
        "parser.add_argument('--dry-run', action='store_true')\n"
        "parser.add_argument('--execute', action='store_true')\n"
        "parser.add_argument('--fail', action='store_true')\n"
        "args = parser.parse_args()\n"
        "if args.fail:\n"
        "    os.environ['FAKE_ADS_SIMULATE_FAILURE'] = '1'\n"
        "client = GoogleAdsClient.load_from_storage(path='config/google-ads.yaml')\n"
        "svc = client.get_service('CampaignBudgetService')\n"
        "req = {\n"
        "    'customer_id': args.customer_id,\n"
        "    'validate_only': not args.execute,\n"
        "    'operations': [{'update': {'resource_name': 'customers/1234567890/campaignBudgets/999', 'amount_micros': 90000000}}],\n"
        "}\n"
        "try:\n"
        "    resp = svc.mutate_campaign_budgets(request=req)\n"
        "    print('RPC OK:', resp['results'][0]['resource_name'])\n"
        "except Exception as e:\n"
        "    print('RPC ERROR:', e, file=sys.stderr)\n"
        "    sys.exit(1)\n",
        encoding="utf-8",
    )

    runner_path = (
        Path(__file__).resolve().parent.parent
        / "plugins"
        / "google-ads-api-developer-assistant"
        / "skills"
        / "execute-mutation"
        / "scripts"
        / "run_mutation.py"
    )

    # 1. Dry-run succeeds and records RPC request/response
    subprocess.run(
        [
            sys.executable,
            str(runner_path),
            "--script",
            str(script_file),
            "--dry-run",
            "--customer-id",
            "1234567890",
            "--operation",
            "Update budget 999",
            "--consequences",
            "Budget increases to $90/day",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    # 2. Execute with --fail records FAILED audit entry with request_id and failure payload
    failed_proc = subprocess.run(
        [
            sys.executable,
            str(runner_path),
            "--script",
            str(script_file),
            "--execute",
            "--script-args=--fail",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert failed_proc.returncode == 1

    # 3. Execute without --fail succeeds and records live RPC payload + request_id
    ok_proc = subprocess.run(
        [
            sys.executable,
            str(runner_path),
            "--script",
            str(script_file),
            "--execute",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "RPC OK: customers/1234567890/campaignBudgets/999" in ok_proc.stdout

    entries = [
        json.loads(line)
        for line in audit_log_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(entries) == 3
    dry_rec, fail_rec, ok_rec = entries

    assert dry_rec["status"] == "DRY_RUN_PASSED"
    assert dry_rec["request"]["payload"]["validate_only"] is True
    assert dry_rec["response"]["google_ads_request_ids"] == ["req-live-777"]

    assert fail_rec["status"] == "FAILED"
    assert fail_rec["response"]["google_ads_request_ids"] == ["req-fail-500"]
    assert (
        fail_rec["response"]["payload"]["errors"][0]["error_code"]["quota_error"]
        == "ACCOUNT_INACTIVE"
    )

    assert ok_rec["status"] == "SUCCESS"
    assert ok_rec["request"]["payload"]["validate_only"] is False
    assert (
        ok_rec["request"]["payload"]["operations"][0]["update"]["amount_micros"]
        == 90000000
    )
    assert ok_rec["response"]["google_ads_request_ids"] == ["req-live-777"]
    assert (
        ok_rec["response"]["payload"]["results"][0]["resource_name"]
        == "customers/1234567890/campaignBudgets/999"
    )

    for receipt_path in run_mutation.get_receipt_paths():
        if os.path.isfile(receipt_path):
            os.remove(receipt_path)


def test_append_mutation_audit_log_direct_writes_and_content_schema(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Verifies direct writes to mutation_audit.jsonl and validates all schema fields across phases."""
    import json
    import uuid

    run_mutation = _load_run_mutation_module()
    audit_log_file = tmp_path / "logs" / "mutation_audit.jsonl"
    monkeypatch.setenv("GOOGLE_ADS_MUTATION_AUDIT_LOG", str(audit_log_file))

    config_yaml = tmp_path / "google-ads.yaml"
    config_yaml.write_text(
        'developer_token: "dev_tok_secret_123"\n'
        'client_id: "9876543210-xyz.apps.googleusercontent.com"\n'
        'client_secret: "client_sec_456"\n'
        'refresh_token: "refresh_tok_789"\n'
        'login_customer_id: "1112223334"\n'
        "ads_assistant: 4.1.0\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GOOGLE_ADS_CONFIGURATION_FILE_PATH", str(config_yaml))

    shared_receipt = {
        "receipt_id": "receipt-fixed-uuid-0001",
        "timestamp_iso": "2026-10-12T13:00:00+00:00",
        "hook_prompted_at_iso": "2026-10-12T13:00:05+00:00",
        "cli_conversation_id": "conv-abc-999",
        "cli_transcript_path": "/tmp/conv-abc-999.jsonl",
        "model_name": "claude-sonnet-4-20250514",
    }

    # Write 1: DRY_RUN_PASSED (no intercepted RPC calls -> fallback payload structure)
    rec1 = run_mutation.append_mutation_audit_log(
        phase="DRY_RUN",
        status="DRY_RUN_PASSED",
        customer_id=" 5556667778 ",
        operation_summary=" Pause Campaign 444 ",
        before_state=" status = ENABLED ",
        after_state=" status = PAUSED ",
        consequences=[" Ad serving stops immediately ", " ", "Bidding paused"],
        reversibility="reversible",
        script_path="/tmp/pause_campaign.py",
        script_sha256="abc123sha256",
        validate_only=True,
        request_sent_at_iso="2026-10-12T13:00:01+00:00",
        response_received_at_iso="2026-10-12T13:00:02+00:00",
        duration_ms=123.45,
        exit_code=0,
        stdout="Dry-run OK\n",
        stderr="",
        command=["python3", "/tmp/pause_campaign.py", "--dry-run"],
        rpc_calls=[],
        receipt=shared_receipt,
    )

    # Write 2: EXECUTE SUCCESS (with intercepted RPC call)
    rec2 = run_mutation.append_mutation_audit_log(
        phase="EXECUTE",
        status="SUCCESS",
        customer_id="5556667778",
        operation_summary="Pause Campaign 444",
        before_state="status = ENABLED",
        after_state="status = PAUSED",
        consequences=["Ad serving stops immediately", "Bidding paused"],
        reversibility="REVERSIBLE",
        script_path="/tmp/pause_campaign.py",
        script_sha256="abc123sha256",
        validate_only=False,
        request_sent_at_iso="2026-10-12T13:00:10+00:00",
        response_received_at_iso="2026-10-12T13:00:12+00:00",
        duration_ms=450.2,
        exit_code=0,
        stdout="Mutated customers/5556667778/campaigns/444\n",
        stderr="",
        command=["python3", "/tmp/pause_campaign.py", "--execute"],
        rpc_calls=[
            {
                "service": "CampaignService",
                "method": "mutate_campaigns",
                "sent_at_iso": "2026-10-12T13:00:10.500000+00:00",
                "received_at_iso": "2026-10-12T13:00:11.800000+00:00",
                "duration_ms": 1300.0,
                "status": "SUCCESS",
                "google_ads_request_id": "gads-req-001",
                "request_payload": {
                    "customer_id": "5556667778",
                    "validate_only": False,
                    "operations": [
                        {
                            "update": {
                                "resource_name": "customers/5556667778/campaigns/444",
                                "status": "PAUSED",
                            }
                        }
                    ],
                },
                "response_payload": {
                    "results": [
                        {"resource_name": "customers/5556667778/campaigns/444"}
                    ]
                },
                "error": None,
            }
        ],
        receipt=shared_receipt,
        user_approved_at_iso="2026-10-12T13:00:09+00:00",
    )

    assert audit_log_file.is_file()
    if sys.platform != "win32":
        assert oct(os.stat(str(audit_log_file)).st_mode & 0o777) == "0o600"

    lines = [
        json.loads(line)
        for line in audit_log_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) == 2
    assert lines[0] == rec1
    assert lines[1] == rec2

    # Validate UUIDs and correlation
    uuid.UUID(lines[0]["audit_id"])
    uuid.UUID(lines[1]["audit_id"])
    assert lines[0]["audit_id"] != lines[1]["audit_id"]
    assert lines[0]["receipt_id"] == "receipt-fixed-uuid-0001"
    assert lines[1]["receipt_id"] == "receipt-fixed-uuid-0001"

    # Validate Write 1 fallback request/response payload & trimmed fields
    assert lines[0]["request"]["customer_id"] == "5556667778"
    assert lines[0]["request"]["validate_only"] is True
    assert lines[0]["request"]["operation_summary"] == "Pause Campaign 444"
    assert lines[0]["request"]["payload"] == {
        "customer_id": "5556667778",
        "validate_only": True,
        "operation_summary": "Pause Campaign 444",
        "before_state": "status = ENABLED",
        "after_state": "status = PAUSED",
        "script_path": "/tmp/pause_campaign.py",
        "script_sha256": "abc123sha256",
    }
    assert lines[0]["approval"]["consequences"] == [
        "Ad serving stops immediately",
        "Bidding paused",
    ]
    assert lines[0]["approval"]["reversibility"] == "REVERSIBLE"
    assert lines[0]["response"]["error"] is None

    # Validate Write 2 RPC-derived timestamps, request_ids, and payloads
    assert lines[1]["request"]["sent_at_iso"] == "2026-10-12T13:00:10.500000+00:00"
    assert (
        lines[1]["response"]["received_at_iso"]
        == "2026-10-12T13:00:11.800000+00:00"
    )
    assert lines[1]["response"]["google_ads_request_ids"] == ["gads-req-001"]
    assert (
        lines[1]["request"]["payload"]["operations"][0]["update"]["status"]
        == "PAUSED"
    )
    assert (
        lines[1]["response"]["payload"]["results"][0]["resource_name"]
        == "customers/5556667778/campaigns/444"
    )
    assert lines[1]["approval"]["user_approved_at_iso"] == "2026-10-12T13:00:09+00:00"


def test_audit_log_actor_service_account_and_env_fallbacks(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Verifies actor metadata extraction for service_account configs and CLI env var fallbacks."""
    import json

    run_mutation = _load_run_mutation_module()
    audit_log_file = tmp_path / "sa_audit.jsonl"
    monkeypatch.setenv("GOOGLE_ADS_MUTATION_AUDIT_LOG", str(audit_log_file))

    sa_yaml = tmp_path / "google-ads.yaml"
    sa_yaml.write_text(
        'developer_token: "sa_dev_token_secret"\n'
        'json_key_file_path: "/etc/keys/google-ads-sa.json"\n'
        'impersonated_email: "ads-admin@example.com"\n'
        'login_customer_id: "4445556667"\n'
        "ads_assistant: 4.1.0\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GOOGLE_ADS_CONFIGURATION_FILE_PATH", str(sa_yaml))
    monkeypatch.setenv("CLAUDE_SESSION_ID", "claude-sess-777")
    monkeypatch.setenv("CLAUDE_TRANSCRIPT_PATH", "/tmp/claude-777.jsonl")
    monkeypatch.delenv("GEMINI_CONVERSATION_ID", raising=False)
    monkeypatch.delenv("GEMINI_TRANSCRIPT_PATH", raising=False)

    run_mutation.append_mutation_audit_log(
        phase="DRY_RUN",
        status="DRY_RUN_PASSED",
        customer_id="9990001112",
        operation_summary="Remove keyword criterion",
        before_state="Keyword '+shoes' ENABLED",
        after_state="REMOVED",
        consequences=["Keyword permanently removed"],
        reversibility="IRREVERSIBLE",
        script_path="/tmp/remove_kw.py",
        script_sha256="deadbeef",
        validate_only=True,
        request_sent_at_iso="2026-10-12T14:00:00+00:00",
        response_received_at_iso="2026-10-12T14:00:01+00:00",
        duration_ms=55.0,
        exit_code=0,
        stdout="Validated",
        stderr="",
    )

    raw = audit_log_file.read_text(encoding="utf-8")
    assert "sa_dev_token_secret" not in raw
    entry = json.loads(raw.strip())

    actor = entry["actor"]
    assert actor["auth_type"] == "service_account"
    assert actor["impersonated_email"] == "ads-admin@example.com"
    assert actor["login_customer_id"] == "4445556667"
    assert actor["target_customer_id"] == "9990001112"
    assert actor["client_id_masked"] is None
    assert actor["ads_assistant_version"] == "4.1.0"
    assert actor["cli_conversation_id"] == "claude-sess-777"
    assert actor["cli_transcript_path"] == "/tmp/claude-777.jsonl"


def test_audit_log_multiple_rpc_calls_and_deep_redaction(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Verifies multi-call aggregation and deep redaction of sensitive keys in audit log entries."""
    import json

    run_mutation = _load_run_mutation_module()
    audit_log_file = tmp_path / "multi_rpc_audit.jsonl"
    monkeypatch.setenv("GOOGLE_ADS_MUTATION_AUDIT_LOG", str(audit_log_file))

    class _ProtoPlusLikeMsg:
        @classmethod
        def to_dict(cls, instance: Any) -> dict[str, Any]:
            return {
                "customer_id": "1234567890",
                "private_key": "-----BEGIN PRIVATE KEY-----",
                "refresh_token": "secret_rt",
                "nested": {
                    "client_secret": "secret_cs",
                    "json_key": "secret_jk",
                    "resource_name": "customers/1234567890/adGroups/555",
                },
            }

    serialized = run_mutation._serialize_rpc_object(_ProtoPlusLikeMsg())
    assert serialized["private_key"] == "[REDACTED]"
    assert serialized["refresh_token"] == "[REDACTED]"
    assert serialized["nested"]["client_secret"] == "[REDACTED]"
    assert serialized["nested"]["json_key"] == "[REDACTED]"
    assert serialized["nested"]["resource_name"] == "customers/1234567890/adGroups/555"

    rpc_calls = [
        {
            "service": "CampaignService",
            "method": "mutate_campaigns",
            "sent_at_iso": "2026-10-12T15:00:01+00:00",
            "received_at_iso": "2026-10-12T15:00:02+00:00",
            "duration_ms": 100.0,
            "status": "SUCCESS",
            "google_ads_request_id": "req-first-1",
            "request_payload": {"op": "campaign_create"},
            "response_payload": {"resource_name": "customers/123/campaigns/1"},
            "error": None,
        },
        {
            "service": "AdGroupService",
            "method": "mutate_ad_groups",
            "sent_at_iso": "2026-10-12T15:00:03+00:00",
            "received_at_iso": "2026-10-12T15:00:05+00:00",
            "duration_ms": 200.0,
            "status": "SUCCESS",
            "google_ads_request_id": "req-second-2",
            "request_payload": serialized,
            "response_payload": {"resource_name": "customers/123/adGroups/555"},
            "error": None,
        },
    ]

    run_mutation.append_mutation_audit_log(
        phase="EXECUTE",
        status="SUCCESS",
        customer_id="1234567890",
        operation_summary="Create Campaign and AdGroup",
        before_state="None",
        after_state="Campaign 1 + AdGroup 555 created",
        consequences=["New campaign and ad group created"],
        reversibility="REVERSIBLE",
        script_path="/tmp/create_tree.py",
        script_sha256="hash999",
        validate_only=False,
        request_sent_at_iso="2026-10-12T15:00:00+00:00",
        response_received_at_iso="2026-10-12T15:00:06+00:00",
        duration_ms=600.0,
        exit_code=0,
        stdout="Done",
        stderr="",
        rpc_calls=rpc_calls,
    )

    entry = json.loads(audit_log_file.read_text(encoding="utf-8").strip())
    assert entry["request"]["sent_at_iso"] == "2026-10-12T15:00:01+00:00"
    assert entry["response"]["received_at_iso"] == "2026-10-12T15:00:05+00:00"
    assert entry["response"]["google_ads_request_ids"] == [
        "req-first-1",
        "req-second-2",
    ]
    assert isinstance(entry["request"]["payload"], list)
    assert len(entry["request"]["payload"]) == 2
    assert len(entry["request"]["rpc_calls"]) == 2
    assert len(entry["response"]["rpc_responses"]) == 2
    assert entry["request"]["payload"][1]["private_key"] == "[REDACTED]"


def test_dry_run_failure_writes_audit_log_and_withholds_receipt(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Verifies that a failed --dry-run writes a DRY_RUN_FAILED audit entry and does not create a receipt."""
    import json
    import subprocess

    run_mutation = _load_run_mutation_module()
    audit_log_file = tmp_path / "dry_run_fail_audit.jsonl"
    monkeypatch.setenv("GOOGLE_ADS_MUTATION_AUDIT_LOG", str(audit_log_file))

    for receipt_path in run_mutation.get_receipt_paths():
        if os.path.isfile(receipt_path):
            os.remove(receipt_path)

    failing_script = tmp_path / "failing_dry_run.py"
    failing_script.write_text(
        "import sys\n"
        "print('RequestError.BAD_RESOURCE_ID on campaignBudgets/000', file=sys.stderr)\n"
        "sys.exit(3)\n",
        encoding="utf-8",
    )

    runner_path = (
        Path(__file__).resolve().parent.parent
        / "plugins"
        / "google-ads-api-developer-assistant"
        / "skills"
        / "execute-mutation"
        / "scripts"
        / "run_mutation.py"
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(runner_path),
            "--script",
            str(failing_script),
            "--dry-run",
            "--customer-id",
            "1234567890",
            "--operation",
            "Update invalid budget",
            "--consequences",
            "Would update budget if valid",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 3

    # Verify no receipt was created
    for receipt_path in run_mutation.get_receipt_paths():
        assert not os.path.isfile(receipt_path)

    # Verify DRY_RUN_FAILED audit record was written with full error details
    assert audit_log_file.is_file()
    entries = [
        json.loads(line)
        for line in audit_log_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(entries) == 1
    entry = entries[0]
    assert entry["phase"] == "DRY_RUN"
    assert entry["status"] == "DRY_RUN_FAILED"
    assert entry["request"]["validate_only"] is True
    assert entry["response"]["exit_code"] == 3
    assert "RequestError.BAD_RESOURCE_ID" in entry["response"]["stderr"]
    assert "RequestError.BAD_RESOURCE_ID" in entry["response"]["error"]


def test_receipt_replay_protection_expiration_and_empty_consequences(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Verifies receipt replay blocking (EXECUTED), expiration (max_age_seconds), and empty consequences."""
    import json
    import subprocess
    import time
    import pytest

    run_mutation = _load_run_mutation_module()
    audit_log_file = tmp_path / "lifecycle_audit.jsonl"
    monkeypatch.setenv("GOOGLE_ADS_MUTATION_AUDIT_LOG", str(audit_log_file))

    for receipt_path in run_mutation.get_receipt_paths():
        if os.path.isfile(receipt_path):
            os.remove(receipt_path)

    # 1. Empty consequences must raise ValueError
    with pytest.raises(ValueError, match="At least one explicit consequence"):
        run_mutation.write_dry_run_receipt(
            customer_id="1234567890",
            operation_summary="Invalid empty consequences",
            before_state="Before",
            after_state="After",
            consequences=["   ", ""],
            reversibility="REVERSIBLE",
        )

    script_file = tmp_path / "replay_script.py"
    script_file.write_text(
        "def mutate(svc, req):\n"
        "    req.validate_only = False\n"
        "    return svc.mutate_campaigns(request=req)\n"
        "print('Executed live script')\n",
        encoding="utf-8",
    )

    # 2. Write valid receipt, then backdate timestamp to test expiration (>1800s)
    run_mutation.write_dry_run_receipt(
        customer_id="1234567890",
        operation_summary="Update Campaign 1",
        before_state="ENABLED",
        after_state="PAUSED",
        consequences=["Campaign stops serving"],
        reversibility="REVERSIBLE",
        script_path=str(script_file),
    )
    expired_ts = time.time() - 3600
    for receipt_path in run_mutation.get_receipt_paths():
        if os.path.isfile(receipt_path):
            with open(receipt_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["timestamp"] = expired_ts
            with open(receipt_path, "w", encoding="utf-8") as f:
                json.dump(data, f)

    ok, msg, _ = run_mutation.load_and_verify_receipt(script_path=str(script_file))
    assert ok is False
    assert "expired" in msg

    decision, reason = evaluate_mutation_guard(f"python3 {script_file} --execute")
    assert decision == "deny"
    assert reason is not None and "expired" in reason

    # 3. Missing consequences in tampered receipt file must be rejected
    for receipt_path in run_mutation.get_receipt_paths():
        if os.path.isfile(receipt_path):
            with open(receipt_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["timestamp"] = time.time()
            data["consequences"] = []
            with open(receipt_path, "w", encoding="utf-8") as f:
                json.dump(data, f)

    ok, msg, _ = run_mutation.load_and_verify_receipt(script_path=str(script_file))
    assert ok is False
    assert "missing mandatory consequence disclosures" in msg

    decision, reason = evaluate_mutation_guard(f"python3 {script_file} --execute")
    assert decision == "deny"
    assert reason is not None and "missing mandatory consequence disclosures" in reason

    # 4. Fresh receipt -> mark_receipt_executed -> replay blocked
    run_mutation.write_dry_run_receipt(
        customer_id="1234567890",
        operation_summary="Update Campaign 1",
        before_state="ENABLED",
        after_state="PAUSED",
        consequences=["Campaign stops serving"],
        reversibility="REVERSIBLE",
        script_path=str(script_file),
    )
    run_mutation.mark_receipt_executed(
        user_approved_at_iso="2026-10-12T16:00:00+00:00",
        request_sent_at_iso="2026-10-12T16:00:01+00:00",
        response_received_at_iso="2026-10-12T16:00:02+00:00",
        audit_id="audit-uuid-999",
    )

    ok, msg, loaded = run_mutation.load_and_verify_receipt(script_path=str(script_file))
    assert ok is False
    assert "EXECUTED" in msg
    assert loaded.get("audit_id") == "audit-uuid-999"
    assert loaded.get("user_approved_at_iso") == "2026-10-12T16:00:00+00:00"

    decision, reason = evaluate_mutation_guard(f"python3 {script_file} --execute")
    assert decision == "deny"
    assert reason is not None and "EXECUTED" in reason

    runner_path = (
        Path(__file__).resolve().parent.parent
        / "plugins"
        / "google-ads-api-developer-assistant"
        / "skills"
        / "execute-mutation"
        / "scripts"
        / "run_mutation.py"
    )
    replay_proc = subprocess.run(
        [sys.executable, str(runner_path), "--script", str(script_file), "--execute"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert replay_proc.returncode == 2
    assert "BLOCKED:" in replay_proc.stderr

    for receipt_path in run_mutation.get_receipt_paths():
        if os.path.isfile(receipt_path):
            os.remove(receipt_path)


def test_evaluate_mutation_guard_inline_methods_and_comments() -> None:
    """Verifies inline mutation prefix detection and ignores commented-out mutation calls."""
    run_mutation = _load_run_mutation_module()
    for receipt_path in run_mutation.get_receipt_paths():
        if os.path.isfile(receipt_path):
            os.remove(receipt_path)

    # Commented-out mutation call on its own line must be allowed
    commented_cmd = (
        'python3 -c "\n# service.mutate_campaigns(request=req)\nprint(\'hello\')"'
    )
    decision, reason = evaluate_mutation_guard(commented_cmd)
    assert decision == "allow"
    assert reason is None

    # All live mutation prefixes without validate_only=True must be denied when no receipt exists
    for method_call in (
        "svc.apply_recommendation(request=req)",
        "svc.upload_click_conversions(request=req)",
        "svc.upload_call_conversions(request=req)",
        "svc.add_batch_job_operations(request=req)",
        "svc.run_batch_job(request=req)",
    ):
        decision, reason = evaluate_mutation_guard(f'python3 -c "{method_call}"')
        assert decision == "deny", f"Expected deny for {method_call}"
        assert reason is not None and "BLOCKED BY HITL MUTATION GUARD" in reason


def test_handle_hook_command_rewriting_and_dual_host_payloads(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    """Verifies handle_hook() command rewriting (Cases A-E), Antigravity/Claude payloads, and PreInvocation."""
    import io
    import json
    from config import config_init

    fake_cfg = str(tmp_path / "config" / "google-ads.yaml")
    monkeypatch.setattr(config_init, "sync_and_set_config_kv", lambda: fake_cfg)

    # 1. PreInvocation hook (empty JSON or no toolCall/tool_input)
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    config_init.handle_hook()
    out_pre = json.loads(capsys.readouterr().out)
    assert "injectSteps" in out_pre
    assert "HITL MUTATION VERIFICATION & AUDIT MANDATE" in out_pre["injectSteps"][0]["ephemeralMessage"]

    # 2. Antigravity PreToolUse hook: rewrites Cases A, B, C, D, E and prepends export
    raw_cmd = (
        "python3 -c \"from google.ads.googleads.client import GoogleAdsClient; "
        "c1 = GoogleAdsClient.load_from_storage(); "
        "c2 = GoogleAdsClient.load_from_storage(version='v25'); "
        "p1 = os.path.expanduser('~/google-ads.yaml'); "
        "p2 = '/home/testuser/google-ads.yaml'; "
        "p3 = 'client_libs/google-ads-python/google-ads.yaml'\""
    )
    agy_payload = {
        "toolCall": {
            "args": {
                "CommandLine": raw_cmd,
            }
        }
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(agy_payload)))
    config_init.handle_hook()
    out_agy = json.loads(capsys.readouterr().out)
    assert out_agy["decision"] == "allow"
    rewritten = out_agy["overwrite"]["CommandLine"]
    assert f'export GOOGLE_ADS_CONFIGURATION_FILE_PATH="{fake_cfg}" &&' in rewritten
    assert 'GoogleAdsClient.load_from_storage(path="config/google-ads.yaml")' in rewritten
    assert 'GoogleAdsClient.load_from_storage(path="config/google-ads.yaml", version=\'v25\')' in rewritten
    assert "/home/testuser/google-ads.yaml" not in rewritten
    assert "client_libs/google-ads-python/google-ads.yaml" not in rewritten
    assert "export GOOGLE_ADS_ASSISTANT_DIR=" in rewritten

    # 2b. Antigravity PreToolUse hook: rewrites relative skills/ path when executed outside repo
    skills_cmd = "python3 skills/ext-version/scripts/get_extension_version.py"
    skills_payload = {
        "toolCall": {
            "args": {
                "CommandLine": skills_cmd,
            }
        }
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(skills_payload)))
    config_init.handle_hook()
    out_skills = json.loads(capsys.readouterr().out)
    assert out_skills["decision"] == "allow"
    rewritten_skills = out_skills["overwrite"]["CommandLine"]
    assert "export GOOGLE_ADS_ASSISTANT_DIR=" in rewritten_skills
    assert "skills/ext-version/scripts/get_extension_version.py" in rewritten_skills

    # 3. Claude Code PreToolUse hook: live mutation denied when no receipt exists
    run_mutation = _load_run_mutation_module()
    for receipt_path in run_mutation.get_receipt_paths():
        if os.path.isfile(receipt_path):
            os.remove(receipt_path)

    claude_payload = {
        "tool_input": {
            "command": "python3 -c 'svc.mutate_campaigns(request=req)'",
        },
        "session_id": "claude-s1",
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(claude_payload)))
    config_init.handle_hook()
    out_claude = json.loads(capsys.readouterr().out)
    assert out_claude["decision"] == "deny"
    assert out_claude["permissionDecision"] == "deny"
    assert "BLOCKED BY HITL MUTATION GUARD" in out_claude["permissionDecisionReason"]


def test_compute_mutate_request_sha256_canonical_normalization() -> None:
    """Verifies that compute_mutate_request_sha256 normalizes validate_only and detects any payload change."""
    run_mutation = _load_run_mutation_module()

    dry_run_req = {
        "customer_id": "1234567890",
        "validate_only": True,
        "operations": [
            {
                "update": {
                    "resource_name": "customers/1234567890/campaignBudgets/111",
                    "amount_micros": 75000000,
                },
                "update_mask": "amount_micros",
            }
        ],
    }
    live_req_reordered = {
        "operations": [
            {
                "update_mask": "amount_micros",
                "update": {
                    "amount_micros": 75000000,
                    "resource_name": "customers/1234567890/campaignBudgets/111",
                },
            }
        ],
        "validate_only": False,
        "customer_id": "1234567890",
    }

    sha_dry = run_mutation.compute_mutate_request_sha256(
        "CampaignBudgetService", "mutate_campaign_budgets", dry_run_req
    )
    sha_live = run_mutation.compute_mutate_request_sha256(
        "CampaignBudgetService", "mutate_campaign_budgets", live_req_reordered
    )
    assert len(sha_dry) == 64
    assert sha_dry == sha_live

    # Any change to customer_id, amount_micros, resource_name, or service/method must change the SHA-256
    altered_amount_req = {
        "customer_id": "1234567890",
        "validate_only": False,
        "operations": [
            {
                "update": {
                    "resource_name": "customers/1234567890/campaignBudgets/111",
                    "amount_micros": 999000000,
                },
                "update_mask": "amount_micros",
            }
        ],
    }
    assert (
        run_mutation.compute_mutate_request_sha256(
            "CampaignBudgetService", "mutate_campaign_budgets", altered_amount_req
        )
        != sha_dry
    )
    assert (
        run_mutation.compute_mutate_request_sha256(
            "CampaignService", "mutate_campaigns", live_req_reordered
        )
        != sha_dry
    )


def test_pre_rpc_sha256_verification_blocks_altered_or_extra_requests_before_sending(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Verifies that mutate request SHA-256 is checked BEFORE sending the RPC and blocks any mismatch."""
    import json
    import subprocess
    import pytest

    run_mutation = _load_run_mutation_module()
    audit_log_file = tmp_path / "pre_rpc_sha_audit.jsonl"
    monkeypatch.setenv("GOOGLE_ADS_MUTATION_AUDIT_LOG", str(audit_log_file))

    for receipt_path in run_mutation.get_receipt_paths():
        if os.path.isfile(receipt_path):
            os.remove(receipt_path)

    # 1. Direct unit test of _wrap_service_for_audit pre-RPC blocking
    class _CountingBudgetService:
        def __init__(self) -> None:
            self.sent_requests: list[Any] = []

        def mutate_campaign_budgets(self, request: Any = None) -> Any:
            self.sent_requests.append(request)
            return {
                "request_id": "req-verified-1",
                "results": [{"resource_name": "customers/123/campaignBudgets/456"}],
            }

    approved_payload = {
        "customer_id": "123",
        "validate_only": True,
        "operations": [
            {
                "update": {
                    "resource_name": "customers/123/campaignBudgets/456",
                    "amount_micros": 50000000,
                }
            }
        ],
    }
    expected_sha = run_mutation.compute_mutate_request_sha256(
        "CampaignBudgetService", "mutate_campaign_budgets", approved_payload
    )

    # 1a. Altered payload is blocked BEFORE mutate_campaign_budgets is invoked
    raw_svc_tampered = _CountingBudgetService()
    captured_tampered: list[dict[str, Any]] = []
    wrapped_tampered = run_mutation._wrap_service_for_audit(
        raw_svc_tampered,
        "CampaignBudgetService",
        captured_tampered,
        expected_request_hashes=[expected_sha],
        enforce_request_hash=True,
    )
    with pytest.raises(PermissionError, match="BLOCKED BEFORE RPC: Mutate request SHA-256 mismatch"):
        wrapped_tampered.mutate_campaign_budgets(
            request={
                "customer_id": "123",
                "validate_only": False,
                "operations": [
                    {
                        "update": {
                            "resource_name": "customers/123/campaignBudgets/456",
                            "amount_micros": 999999999,  # Altered amount!
                        }
                    }
                ],
            }
        )
    # Underlying RPC method was NEVER called
    assert len(raw_svc_tampered.sent_requests) == 0
    assert len(captured_tampered) == 1
    assert captured_tampered[0]["status"] == "BLOCKED_SHA256_MISMATCH"
    assert captured_tampered[0]["request_sha256_verified"] is False
    assert captured_tampered[0]["expected_request_sha256"] == expected_sha
    assert captured_tampered[0]["request_sha256"] != expected_sha

    # 1b. Matching payload (with validate_only=False) succeeds, but a 2nd unapproved call is blocked before sending
    raw_svc_ok = _CountingBudgetService()
    captured_ok: list[dict[str, Any]] = []
    wrapped_ok = run_mutation._wrap_service_for_audit(
        raw_svc_ok,
        "CampaignBudgetService",
        captured_ok,
        expected_request_hashes=[expected_sha],
        enforce_request_hash=True,
    )
    resp = wrapped_ok.mutate_campaign_budgets(
        request={
            "customer_id": "123",
            "validate_only": False,
            "operations": [
                {
                    "update": {
                        "resource_name": "customers/123/campaignBudgets/456",
                        "amount_micros": 50000000,
                    }
                }
            ],
        }
    )
    assert resp["request_id"] == "req-verified-1"
    assert len(raw_svc_ok.sent_requests) == 1
    assert captured_ok[0]["request_sha256"] == expected_sha
    assert captured_ok[0]["request_sha256_verified"] is True

    with pytest.raises(PermissionError, match="BLOCKED BEFORE RPC: Unapproved mutation call #2"):
        wrapped_ok.mutate_campaign_budgets(
            request={
                "customer_id": "123",
                "validate_only": False,
                "operations": [
                    {
                        "update": {
                            "resource_name": "customers/123/campaignBudgets/456",
                            "amount_micros": 50000000,
                        }
                    }
                ],
            }
        )
    # 2nd call was blocked before reaching raw_svc_ok.mutate_campaign_budgets
    assert len(raw_svc_ok.sent_requests) == 1
    assert captured_ok[1]["status"] == "BLOCKED_SHA256_MISMATCH"

    # 2. End-to-end subprocess test: script alters request payload during --execute
    live_rpc_marker = tmp_path / "live_rpc_was_sent.marker"
    pkg_dir = tmp_path / "google" / "ads" / "googleads"
    pkg_dir.mkdir(parents=True)
    (tmp_path / "google" / "__init__.py").write_text(
        "__path__ = __import__('pkgutil').extend_path(__path__, __name__)\n",
        encoding="utf-8",
    )
    (tmp_path / "google" / "ads" / "__init__.py").write_text(
        "__path__ = __import__('pkgutil').extend_path(__path__, __name__)\n",
        encoding="utf-8",
    )
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    (pkg_dir / "client.py").write_text(
        "from pathlib import Path\n"
        "class _FakeBudgetService:\n"
        "    def mutate_campaign_budgets(self, request=None):\n"
        "        if isinstance(request, dict) and not request.get('validate_only', True):\n"
        f"            Path({str(live_rpc_marker)!r}).write_text('SENT', encoding='utf-8')\n"
        "        return {\n"
        "            'request_id': 'req-e2e-111',\n"
        "            'results': [{'resource_name': 'customers/1234567890/campaignBudgets/777'}],\n"
        "        }\n\n"
        "class GoogleAdsClient:\n"
        "    @classmethod\n"
        "    def load_from_storage(cls, path=None, version=None):\n"
        "        return cls()\n"
        "    def get_service(self, name, *args, **kwargs):\n"
        "        return _FakeBudgetService()\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PYTHONPATH", f"{tmp_path}{os.pathsep}{os.environ.get('PYTHONPATH', '')}")

    bait_and_switch_script = tmp_path / "bait_and_switch.py"
    bait_and_switch_script.write_text(
        "import argparse\n"
        "from google.ads.googleads.client import GoogleAdsClient\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--customer-id', default='1234567890')\n"
        "parser.add_argument('--dry-run', action='store_true')\n"
        "parser.add_argument('--execute', action='store_true')\n"
        "args = parser.parse_args()\n"
        "client = GoogleAdsClient.load_from_storage(path='config/google-ads.yaml')\n"
        "svc = client.get_service('CampaignBudgetService')\n"
        "# Bait-and-switch: uses 50M micros in dry-run, but tries to send 500M micros in execute!\n"
        "amount = 500000000 if args.execute else 50000000\n"
        "req = {\n"
        "    'customer_id': args.customer_id,\n"
        "    'validate_only': not args.execute,\n"
        "    'operations': [{'update': {'resource_name': 'customers/1234567890/campaignBudgets/777', 'amount_micros': amount}}],\n"
        "}\n"
        "svc.mutate_campaign_budgets(request=req)\n",
        encoding="utf-8",
    )

    runner_path = (
        Path(__file__).resolve().parent.parent
        / "plugins"
        / "google-ads-api-developer-assistant"
        / "skills"
        / "execute-mutation"
        / "scripts"
        / "run_mutation.py"
    )

    # Dry-run succeeds and records request_sha256 in receipt
    dry_proc = subprocess.run(
        [
            sys.executable,
            str(runner_path),
            "--script",
            str(bait_and_switch_script),
            "--dry-run",
            "--customer-id",
            "1234567890",
            "--operation",
            "Update budget 777 to $50/day",
            "--consequences",
            "Budget set to $50/day",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Request SHA256:" in dry_proc.stdout

    # Execute must be BLOCKED BEFORE sending the live RPC because the request SHA-256 differs!
    exec_proc = subprocess.run(
        [
            sys.executable,
            str(runner_path),
            "--script",
            str(bait_and_switch_script),
            "--execute",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert exec_proc.returncode != 0
    assert "BLOCKED_SHA256_MISMATCH" in exec_proc.stderr
    assert "BLOCKED BEFORE RPC: Mutate request SHA-256 mismatch" in exec_proc.stderr
    # Crucial verification: the underlying live RPC method was NEVER invoked!
    assert not live_rpc_marker.exists()

    # Verify audit log recorded BLOCKED_SHA256_MISMATCH and request_sha256_verified=False
    entries = [
        json.loads(line)
        for line in audit_log_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(entries) == 2
    dry_audit, blocked_audit = entries
    assert dry_audit["status"] == "DRY_RUN_PASSED"
    assert dry_audit["request"]["request_sha256_verified"] is True
    assert blocked_audit["phase"] == "EXECUTE"
    assert blocked_audit["status"] == "BLOCKED_SHA256_MISMATCH"
    assert blocked_audit["request"]["request_sha256_verified"] is False
    assert (
        blocked_audit["request"]["request_sha256"]
        != blocked_audit["request"]["expected_request_sha256"]
    )
    assert (
        blocked_audit["request"]["expected_request_sha256"]
        == dry_audit["request"]["request_sha256"]
    )

    # 3. Verify that tampering with dry_run_rpc_calls in last_dry_run.json is caught by both hook and runner
    for receipt_path in run_mutation.get_receipt_paths():
        if os.path.isfile(receipt_path):
            with open(receipt_path, "r", encoding="utf-8") as f:
                r_data = json.load(f)
            r_data["dry_run_rpc_calls"][0]["request_payload"]["operations"][0]["update"][
                "amount_micros"
            ] = 500000000
            with open(receipt_path, "w", encoding="utf-8") as f:
                json.dump(r_data, f)

    ok_receipt, msg_receipt, _ = run_mutation.load_and_verify_receipt(
        script_path=str(bait_and_switch_script)
    )
    assert ok_receipt is False
    assert "SHA-256 mismatch" in msg_receipt

    decision, reason = evaluate_mutation_guard(
        f"python3 {runner_path} --script {bait_and_switch_script} --execute"
    )
    assert decision == "deny"
    assert reason is not None and "SHA-256 mismatch" in reason

    for receipt_path in run_mutation.get_receipt_paths():
        if os.path.isfile(receipt_path):
            os.remove(receipt_path)


def test_execute_mutates_config_defaults_to_false_and_blocks_live_mutations(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Verifies that execute_mutates in config/assistant_config (TOML) defaults to false and blocks live mutations across all layers."""
    import json
    import subprocess
    from config import config_init

    run_mutation = _load_run_mutation_module()
    audit_log_file = tmp_path / "mutates_disabled_audit.jsonl"
    monkeypatch.setenv("GOOGLE_ADS_MUTATION_AUDIT_LOG", str(audit_log_file))

    # 1. Remove the test fixture override so the real on-disk default is evaluated
    monkeypatch.delenv("GOOGLE_ADS_EXECUTE_MUTATES", raising=False)

    repo_root = Path(__file__).resolve().parent.parent
    plugin_assistant_cfg = (
        repo_root
        / "plugins"
        / "google-ads-api-developer-assistant"
        / "config"
        / "assistant_config"
    )
    assert not (repo_root / "config").exists()
    assert plugin_assistant_cfg.is_file()

    plugin_parsed = config_init.parse_assistant_config(
        plugin_assistant_cfg.read_text(encoding="utf-8")
    )
    assert plugin_parsed["execute_mutates"] is False
    assert "api_version" in plugin_parsed
    assert "customer_id" in plugin_parsed

    # Default state must be False
    assert config_init.is_execute_mutates_enabled() is False
    assert run_mutation.is_execute_mutates_enabled() is False

    # 2. Verify TOML parser and set_execute_mutates in an isolated config_dir
    assert config_init.parse_execute_mutates_value("execute_mutates = false") is False
    assert config_init.parse_execute_mutates_value("execute_mutates = true") is True
    assert config_init.parse_execute_mutates_value("execute_mutates=false") is False
    assert config_init.parse_execute_mutates_value("# comment\nexecute_mutates = true\n") is True
    assert config_init.parse_execute_mutates_value("invalid_line = 123") is None

    isolated_cfg_dir = tmp_path / "isolated_config"
    written_path = config_init.set_execute_mutates(False, config_dir=str(isolated_cfg_dir))
    assert Path(written_path).name == "assistant_config"
    written_text = Path(written_path).read_text(encoding="utf-8")
    assert 'api_version = "' in written_text
    assert 'customer_id = "' in written_text
    assert "execute_mutates = false\n" in written_text
    assert config_init.is_execute_mutates_enabled(config_dir=str(isolated_cfg_dir)) is False

    config_init.set_execute_mutates(True, config_dir=str(isolated_cfg_dir))
    assert "execute_mutates = true\n" in Path(written_path).read_text(encoding="utf-8")
    assert config_init.is_execute_mutates_enabled(config_dir=str(isolated_cfg_dir)) is True

    # Reset back to false in isolated_cfg_dir
    config_init.set_execute_mutates(False, config_dir=str(isolated_cfg_dir))

    # 3. Even when a valid dry-run receipt exists, PreToolUse hook and run_mutation.py block --execute when execute_mutates = false
    script_file = tmp_path / "disabled_mutate_test.py"
    marker_file = tmp_path / "should_never_run.marker"
    script_file.write_text(
        "import argparse\n"
        "from pathlib import Path\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--customer-id', default='1234567890')\n"
        "parser.add_argument('--dry-run', action='store_true')\n"
        "parser.add_argument('--execute', action='store_true')\n"
        "args = parser.parse_args()\n"
        "if args.execute:\n"
        f"    Path({str(marker_file)!r}).write_text('EXECUTED', encoding='utf-8')\n"
        "else:\n"
        "    print('Dry-run OK while execute_mutates = false')\n",
        encoding="utf-8",
    )

    runner_path = (
        repo_root
        / "plugins"
        / "google-ads-api-developer-assistant"
        / "skills"
        / "execute-mutation"
        / "scripts"
        / "run_mutation.py"
    )

    # 3a. Dry-run is still allowed when execute_mutates = false and displays DISABLED status in the card
    dry_proc = subprocess.run(
        [
            sys.executable,
            str(runner_path),
            "--script",
            str(script_file),
            "--dry-run",
            "--customer-id",
            "1234567890",
            "--operation",
            "Update CampaignBudget 555",
            "--consequences",
            "Daily budget increases to $100/day",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "Mutates Config: DISABLED (execute_mutates = false" in dry_proc.stdout

    # 3b. PreToolUse hook (evaluate_mutation_guard) denies --execute when execute_mutates = false
    decision, reason = evaluate_mutation_guard(
        f"python3 {runner_path} --script {script_file} --execute"
    )
    assert decision == "deny"
    assert reason is not None
    assert "execute_mutates = false" in reason

    # Direct inline live mutation is also denied with execute_mutates = false message
    decision_inline, reason_inline = evaluate_mutation_guard(
        "python3 -c 'svc.mutate_campaigns(request=req)'"
    )
    assert decision_inline == "deny"
    assert reason_inline is not None
    assert "execute_mutates = false" in reason_inline

    # 3c. Subprocess invocation of run_mutation.py --execute is hard-blocked before running script_file
    exec_proc = subprocess.run(
        [
            sys.executable,
            str(runner_path),
            "--script",
            str(script_file),
            "--execute",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert exec_proc.returncode == 2
    assert "execute_mutates = false" in exec_proc.stderr
    assert not marker_file.exists()

    # Verify BLOCKED_MUTATES_DISABLED audit entry was recorded
    entries = [
        json.loads(line)
        for line in audit_log_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(entries) == 2
    assert entries[0]["status"] == "DRY_RUN_PASSED"
    assert entries[1]["phase"] == "EXECUTE"
    assert entries[1]["status"] == "BLOCKED_MUTATES_DISABLED"
    assert "execute_mutates = false" in entries[1]["response"]["error"]

    # 3d. RPC interceptor (_wrap_service_for_audit) also blocks validate_only=False calls when execute_mutates = false
    class _RawService:
        def __init__(self) -> None:
            self.called = False

        def mutate_campaigns(self, request: Any = None) -> Any:
            self.called = True
            return {"results": []}

    raw_svc = _RawService()
    captured_rpc: list[dict[str, Any]] = []
    wrapped_svc = run_mutation._wrap_service_for_audit(
        raw_svc, "CampaignService", captured_rpc
    )
    with pytest.raises(PermissionError, match="execute_mutates = false"):
        wrapped_svc.mutate_campaigns(
            request={"customer_id": "1234567890", "validate_only": False, "operations": []}
        )
    assert raw_svc.called is False
    assert len(captured_rpc) == 1
    assert captured_rpc[0]["status"] == "BLOCKED_MUTATES_DISABLED"

    # 4. Enabling execute_mutates = true allows the 4-Step HITL flow to proceed to force_ask and live execution
    monkeypatch.setenv("GOOGLE_ADS_EXECUTE_MUTATES", "execute_mutates = true")
    decision_enabled, reason_enabled = evaluate_mutation_guard(
        f"python3 {runner_path} --script {script_file} --execute"
    )
    assert decision_enabled == "force_ask"
    assert reason_enabled is not None

    for receipt_path in run_mutation.get_receipt_paths():
        if os.path.isfile(receipt_path):
            os.remove(receipt_path)


def test_security_hardening_direct_script_spoofing_executable_and_sidecar(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Verifies the 3 security hardening fixes:
    1. Direct script '--dry-run' CLI flag spoofing is blocked if script lacks validate_only=True or has validate_only=False.
    2. Direct './script.py' executable invocation (without 'python' prefix) is inspected and gated by evaluate_mutation_guard.
    3. Sidecar handle_execute_mutation enforces is_execute_mutates_enabled() and writes to mutation_audit.jsonl.
    """
    import importlib.util
    import json

    run_mutation = _load_run_mutation_module()
    audit_log_file = tmp_path / "hardening_audit.jsonl"
    monkeypatch.setenv("GOOGLE_ADS_MUTATION_AUDIT_LOG", str(audit_log_file))

    for receipt_path in run_mutation.get_receipt_paths():
        if os.path.isfile(receipt_path):
            os.remove(receipt_path)

    # --- Fix 1 & 2: Direct script --dry-run spoofing and direct ./script.py execution ---
    spoof_script = tmp_path / "spoof_dry_run.py"
    spoof_script.write_text(
        "from google.ads.googleads.client import GoogleAdsClient\n"
        "client = GoogleAdsClient.load_from_storage(path='config/google-ads.yaml')\n"
        "svc = client.get_service('CampaignService')\n"
        "# Script ignores --dry-run and sends a live mutation!\n"
        "svc.mutate_campaigns(customer_id='1234567890', operations=[], validate_only=False)\n",
        encoding="utf-8",
    )

    # Even with --dry-run or --validate-only on the CLI, direct script execution is DENIED
    decision_spoof, reason_spoof = evaluate_mutation_guard(
        f"python3 {spoof_script} --dry-run"
    )
    assert decision_spoof == "deny"
    assert reason_spoof is not None

    # Direct executable invocation (./spoof_dry_run.py without 'python3' prefix) is ALSO intercepted and DENIED
    decision_exec_direct, reason_exec_direct = evaluate_mutation_guard(
        f"{spoof_script}"
    )
    assert decision_exec_direct == "deny"
    assert reason_exec_direct is not None

    # Whereas a direct script that genuinely sets validate_only=True (and no validate_only=False) is allowed
    genuine_dry_script = tmp_path / "genuine_dry_run.py"
    genuine_dry_script.write_text(
        "from google.ads.googleads.client import GoogleAdsClient\n"
        "client = GoogleAdsClient.load_from_storage(path='config/google-ads.yaml')\n"
        "svc = client.get_service('CampaignService')\n"
        "svc.mutate_campaigns(customer_id='1234567890', operations=[], validate_only=True)\n",
        encoding="utf-8",
    )
    decision_genuine, _ = evaluate_mutation_guard(f"{genuine_dry_script}")
    assert decision_genuine == "allow"

    # --- Fix 3: Sidecar handle_prepare_mutation & handle_execute_mutation enforcement ---
    repo_root = Path(__file__).resolve().parent.parent
    server_path = (
        repo_root
        / "plugins"
        / "google-ads-api-developer-assistant"
        / "sidecars"
        / "google-ads-a2a-service"
        / "server.py"
    )
    spec = importlib.util.spec_from_file_location("sidecar_server", server_path)
    assert spec is not None and spec.loader is not None
    sidecar_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sidecar_mod)

    handler = object.__new__(sidecar_mod.A2AHandler)

    # Step A: PREPARE_MUTATION writes dry-run receipt and logs DRY_RUN_PASSED to audit log
    prep_res = handler.handle_prepare_mutation(
        "task-prep-1",
        {
            "customer_id": "1234567890",
            "operation_summary": "Update CampaignBudget 999",
            "before_state": "$10/day",
            "after_state": "$25/day",
            "consequences": ["Daily budget increases by +$15/day"],
            "reversibility": "REVERSIBLE",
            "script_path": str(spoof_script),
        },
    )
    assert prep_res["status"] == "HITL_CONFIRMATION_REQUIRED"

    # Step B: With execute_mutates = false, sidecar EXECUTE_MUTATION is blocked and audited
    monkeypatch.setenv("GOOGLE_ADS_EXECUTE_MUTATES", "execute_mutates = false")
    blocked_res = handler.handle_execute_mutation(
        "task-exec-blocked",
        {
            "user_confirmed": True,
            "confirmation_summary": "User approved +$15/day budget increase",
            "script_path": str(spoof_script),
        },
    )
    assert blocked_res["status"] == "HITL_BLOCKED"
    assert "execute_mutates = false" in blocked_res["error"]

    # Step C: With execute_mutates = true, sidecar EXECUTE_MUTATION succeeds, logs SUCCESS, and marks receipt EXECUTED
    monkeypatch.setenv("GOOGLE_ADS_EXECUTE_MUTATES", "execute_mutates = true")
    ok_res = handler.handle_execute_mutation(
        "task-exec-ok",
        {
            "user_confirmed": True,
            "confirmation_summary": "User approved +$15/day budget increase",
            "script_path": str(spoof_script),
        },
    )
    assert ok_res["status"] == "COMPLETED"
    assert ok_res["result"].get("audit_id")

    entries = [
        json.loads(line)
        for line in audit_log_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [e["status"] for e in entries] == [
        "DRY_RUN_PASSED",
        "BLOCKED_MUTATES_DISABLED",
        "SUCCESS",
    ]

    for receipt_path in run_mutation.get_receipt_paths():
        if os.path.isfile(receipt_path):
            os.remove(receipt_path)


def test_financial_transaction_command_interception_matrix() -> None:
    """Verifies evaluate_mutation_guard intercepts all financial-transaction write RPCs while allowing read-only financial lookups."""
    run_mutation = _load_run_mutation_module()
    for receipt_path in run_mutation.get_receipt_paths():
        if os.path.isfile(receipt_path):
            os.remove(receipt_path)

    # All financial & spend-affecting write RPCs across billing, budgets, reservations,
    # incentives, lead credits, bidding, conversion value restatements, and spend promotions
    financial_write_calls = (
        # Account billing & budgets
        "billing_svc.mutate_billing_setup(request=req)",
        "budget_proposal_svc.mutate_account_budget_proposal(request=req)",
        "campaign_budget_svc.mutate_campaign_budgets(request=req)",
        "customer_svc.create_customer_client(request=req)",
        # Guaranteed spend, credits & incentives
        "reservation_svc.book_campaigns(request=req)",
        "incentive_svc.apply_incentive(request=req)",
        "lsa_lead_svc.provide_lead_feedback(request=req)",
        # Bidding, conversion value restatements & spend promotions
        "bidding_svc.mutate_bidding_strategies(request=req)",
        "seasonality_svc.mutate_bidding_seasonality_adjustments(request=req)",
        "exclusion_svc.mutate_bidding_data_exclusions(request=req)",
        "camp_mod_svc.mutate_campaign_bid_modifiers(request=req)",
        "ag_mod_svc.mutate_ad_group_bid_modifiers(request=req)",
        "val_rule_svc.mutate_conversion_value_rules(request=req)",
        "val_rule_set_svc.mutate_conversion_value_rule_sets(request=req)",
        "adj_upload_svc.upload_conversion_adjustments(request=req)",
        "exp_svc.graduate_experiment(request=req)",
        "exp_svc.promote_experiment(request=req)",
        "exp_svc.schedule_experiment(request=req)",
        "exp_svc.end_experiment(request=req)",
        "draft_svc.promote_campaign_draft(request=req)",
        "rec_svc.dismiss_recommendation(request=req)",
        "ga_svc.mutate(customer_id='1234567890', mutate_operations=ops)",
    )
    for call_expr in financial_write_calls:
        decision, reason = evaluate_mutation_guard(f'python3 -c "{call_expr}"')
        assert decision == "deny", f"Expected 'deny' for financial write RPC: {call_expr}"
        assert reason is not None and "BLOCKED BY HITL MUTATION GUARD" in reason

    # Read-only financial queries, quotes, and forecasts must remain allowed
    readonly_financial_calls = (
        "invoice_svc.list_invoices(request=req)",
        "payments_svc.list_payments_accounts(request=req)",
        "reservation_svc.quote_campaigns(request=req)",
        "incentive_svc.fetch_incentive(request=req)",
        "suggest_svc.suggest_smart_campaign_budget_options(request=req)",
        "ga_svc.search_stream(customer_id='1234567890', query='SELECT billing_setup.id FROM billing_setup')",
    )
    for ro_expr in readonly_financial_calls:
        decision, reason = evaluate_mutation_guard(f'python3 -c "{ro_expr}"')
        assert decision == "allow", f"Expected 'allow' for read-only financial call: {ro_expr}"
        assert reason is None


def test_non_validate_only_financial_rpcs_cannot_bypass_guard_with_validate_only_true(
    tmp_path: Path,
) -> None:
    """Verifies non-validate_only-capable financial RPCs are denied even when validate_only=True appears in the script or command."""
    run_mutation = _load_run_mutation_module()
    for receipt_path in run_mutation.get_receipt_paths():
        if os.path.isfile(receipt_path):
            os.remove(receipt_path)

    non_validate_only_financial_methods = (
        ("BillingSetupService", "mutate_billing_setup"),
        ("ReservationService", "book_campaigns"),
        ("IncentiveService", "apply_incentive"),
        ("LocalServicesLeadService", "provide_lead_feedback"),
        ("RecommendationService", "apply_recommendation"),
        ("RecommendationService", "dismiss_recommendation"),
        ("BatchJobService", "mutate_batch_job"),
        ("CustomerUserAccessService", "mutate_customer_user_access"),
        ("UserDataService", "upload_user_data"),
    )

    for svc_name, method_name in non_validate_only_financial_methods:
        # 1. Inline python3 -c spoofing validate_only=True
        inline_cmd = (
            f'python3 -c "validate_only = True; '
            f"svc = client.get_service('{svc_name}'); "
            f'svc.{method_name}(request=req)"'
        )
        decision, reason = evaluate_mutation_guard(inline_cmd)
        assert decision == "deny", (
            f"{svc_name}.{method_name} lacks validate_only support and must NOT bypass guard"
        )
        assert reason is not None and "BLOCKED BY HITL MUTATION GUARD" in reason

        # 2. Direct script file containing validate_only=True alongside non-validate_only RPC
        spoof_file = tmp_path / f"spoof_{method_name}.py"
        spoof_file.write_text(
            f"def run(client, req):\n"
            f"    validate_only = True\n"
            f"    svc = client.get_service('{svc_name}')\n"
            f"    return svc.{method_name}(request=req)\n",
            encoding="utf-8",
        )
        file_decision, file_reason = evaluate_mutation_guard(f"python3 {spoof_file}")
        assert file_decision == "deny", (
            f"Direct script calling {svc_name}.{method_name} must be denied even with validate_only=True"
        )
        assert file_reason is not None

    # Contrast: validate_only-capable financial RPCs with explicit validate_only=True ARE allowed as direct dry-runs
    validate_only_capable_financial_methods = (
        ("AccountBudgetProposalService", "mutate_account_budget_proposal"),
        ("CustomerService", "create_customer_client"),
        ("BiddingStrategyService", "mutate_bidding_strategies"),
        ("ConversionAdjustmentUploadService", "upload_conversion_adjustments"),
        ("ConversionValueRuleService", "mutate_conversion_value_rules"),
        ("ExperimentService", "graduate_experiment"),
        ("ExperimentService", "end_experiment"),
        ("CampaignDraftService", "promote_campaign_draft"),
    )
    for svc_name, method_name in validate_only_capable_financial_methods:
        dry_file = tmp_path / f"dry_{method_name}.py"
        dry_file.write_text(
            f"def dry_run(client, req):\n"
            f"    req.validate_only = True\n"
            f"    svc = client.get_service('{svc_name}')\n"
            f"    return svc.{method_name}(request=req)\n",
            encoding="utf-8",
        )
        dry_decision, dry_reason = evaluate_mutation_guard(f"python3 {dry_file}")
        assert dry_decision == "allow", (
            f"Genuine validate_only=True dry-run for {svc_name}.{method_name} should be allowed"
        )
        assert dry_reason is None


def test_financial_mutation_classification_and_mandatory_consequence_disclosures(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """Verifies financial-transaction classification and mandatory monetary/spend/billing consequence disclosures across CLI, receipt verifier, PreToolUse hook, and A2A sidecar."""
    import importlib.util
    import json
    import subprocess
    import sys

    run_mutation = _load_run_mutation_module()
    audit_log_file = tmp_path / "financial_consequences_audit.jsonl"
    monkeypatch.setenv("GOOGLE_ADS_MUTATION_AUDIT_LOG", str(audit_log_file))

    for receipt_path in run_mutation.get_receipt_paths():
        if os.path.isfile(receipt_path):
            os.remove(receipt_path)

    # 1. Classification checks: financial services, methods, nested financial payload fields, and summaries
    assert run_mutation.is_financial_mutation(
        operation_summary="BillingSetupService.mutate_billing_setup"
    )
    assert run_mutation.is_financial_mutation(
        operation_summary="AccountBudgetProposalService.mutate_account_budget_proposal"
    )
    assert run_mutation.is_financial_mutation(
        operation_summary="ReservationService.book_campaigns"
    )
    assert run_mutation.is_financial_mutation(
        operation_summary="IncentiveService.apply_incentive"
    )
    assert run_mutation.is_financial_mutation(
        operation_summary="LocalServicesLeadService.provide_lead_feedback"
    )
    assert run_mutation.is_financial_mutation(
        operation_summary="ConversionAdjustmentUploadService.upload_conversion_adjustments"
    )
    assert run_mutation.is_financial_mutation(
        operation_summary="CustomerService.create_customer_client"
    )
    assert run_mutation.is_financial_mutation(
        operation_summary="ExperimentService.graduate_experiment"
    )
    assert run_mutation.is_financial_mutation(
        operation_summary="CampaignDraftService.promote_campaign_draft"
    )
    # Atomic GoogleAdsService.mutate or AdGroupCriterion update detected as financial via nested payload fields
    assert run_mutation.is_financial_mutation(
        operation_summary="Update AdGroupCriterion 555",
        rpc_calls=[
            {
                "service": "AdGroupCriterionService",
                "method": "mutate_ad_group_criteria",
                "request_payload": {
                    "customer_id": "1234567890",
                    "operations": [
                        {
                            "update": {
                                "resource_name": "customers/1234567890/adGroupCriteria/11~555",
                                "cpc_bid_micros": "3500000",
                            }
                        }
                    ],
                },
            }
        ],
    )
    assert run_mutation.is_financial_mutation(
        operation_summary="Atomic cross-resource update",
        rpc_calls=[
            {
                "service": "GoogleAdsService",
                "method": "mutate",
                "request_payload": {
                    "customer_id": "1234567890",
                    "mutate_operations": [
                        {
                            "bidding_strategy_operation": {
                                "create": {
                                    "name": "Target ROAS 400%",
                                    "target_roas": {"target_roas": 4.0},
                                }
                            }
                        }
                    ],
                },
            }
        ],
    )

    # Non-financial operations must NOT be misclassified as financial transactions
    assert not run_mutation.is_financial_mutation(
        operation_summary="Pause Campaign 444",
        before_state="ENABLED",
        after_state="PAUSED",
    )
    assert not run_mutation.is_financial_mutation(
        operation_summary="Remove keyword criterion",
        before_state="ENABLED",
        after_state="REMOVED",
    )
    assert not run_mutation.is_financial_mutation(
        operation_summary="Create Responsive Search Ad",
        before_state="None",
        after_state="ENABLED",
        rpc_calls=[
            {
                "service": "AdGroupAdService",
                "method": "mutate_ad_group_ads",
                "request_payload": {
                    "customer_id": "1234567890",
                    "operations": [{"create": {"status": "PAUSED"}}],
                },
            }
        ],
    )

    # 2. write_dry_run_receipt rejects financial mutations lacking explicit monetary/spend/billing consequences
    fin_script = tmp_path / "mutate_account_budget.py"
    fin_script.write_text(
        "def run(svc, req):\n"
        "    req.validate_only = False\n"
        "    return svc.mutate_account_budget_proposal(request=req)\n",
        encoding="utf-8",
    )
    for vague_consequences in (
        ["Updates account configuration"],
        ["Applies requested API change immediately"],
        ["Permanent update to customer 1234567890"],
    ):
        with pytest.raises(
            ValueError,
            match="Financial mutation requires explicit monetary, currency, spend, budget, billing, credit, or bidding impact disclosure",
        ):
            run_mutation.write_dry_run_receipt(
                customer_id="1234567890",
                operation_summary="AccountBudgetProposalService.mutate_account_budget_proposal",
                before_state="Spending limit: $10,000.00",
                after_state="Spending limit: $25,000.00",
                consequences=vague_consequences,
                reversibility="REVERSIBLE",
                script_path=str(fin_script),
            )

    # 3. CLI --dry-run exits with code 2 and audits BLOCKED_FINANCIAL_CONSEQUENCE_MISSING when financial disclosure is omitted
    runner_path = (
        Path(__file__).resolve().parent.parent
        / "plugins"
        / "google-ads-api-developer-assistant"
        / "skills"
        / "execute-mutation"
        / "scripts"
        / "run_mutation.py"
    )
    bad_cli = subprocess.run(
        [
            sys.executable,
            str(runner_path),
            "--script",
            str(fin_script),
            "--dry-run",
            "--record-only",
            "--customer-id",
            "1234567890",
            "--operation",
            "BillingSetupService.mutate_billing_setup",
            "--before",
            "No active billing setup",
            "--after",
            "Active billing setup",
            "--consequences",
            "Updates account setup configuration",
            "--reversibility",
            "IRREVERSIBLE",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert bad_cli.returncode == 2
    assert "Financial mutation requires explicit monetary" in bad_cli.stderr

    # 4. A2A Sidecar PREPARE_MUTATION also rejects missing financial consequence disclosures and logs audit record
    server_path = (
        Path(__file__).resolve().parent.parent
        / "plugins"
        / "google-ads-api-developer-assistant"
        / "sidecars"
        / "google-ads-a2a-service"
        / "server.py"
    )
    spec = importlib.util.spec_from_file_location("sidecar_fin_test", server_path)
    assert spec is not None and spec.loader is not None
    sidecar_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sidecar_mod)
    handler = object.__new__(sidecar_mod.A2AHandler)

    bad_sidecar = handler.handle_prepare_mutation(
        "task-fin-missing",
        {
            "customer_id": "1234567890",
            "operation_summary": "IncentiveService.apply_incentive",
            "before_state": "No incentive applied",
            "after_state": "Incentive OFFER-999 applied",
            "consequences": ["Applies requested change to account"],
            "reversibility": "IRREVERSIBLE",
            "script_path": str(fin_script),
        },
    )
    assert bad_sidecar["status"] == "VALIDATION_FAILED"
    assert "Financial mutation requires explicit monetary" in bad_sidecar["error"]

    # 5. Explicit financial consequence disclosures succeed across receipt, Verification Card, and PreToolUse force_ask
    good_receipt = run_mutation.write_dry_run_receipt(
        customer_id="1234567890",
        operation_summary="AccountBudgetProposalService.mutate_account_budget_proposal",
        before_state="Account spending limit: $10,000.00 USD",
        after_state="Account spending limit: $25,000.00 USD",
        consequences=[
            "Raises account billing spending limit by +$15,000.00 USD (+150%)",
            "Authorizes up to $25,000.00 in billable ad charges on linked payments account",
        ],
        reversibility="REVERSIBLE",
        script_path=str(fin_script),
    )
    assert good_receipt["is_financial_transaction"] is True
    card_text = run_mutation.format_verification_card(good_receipt)
    assert "Financial Txn : YES" in card_text

    decision_ok, reason_ok = evaluate_mutation_guard(
        f"python3 {runner_path} --script {fin_script} --execute"
    )
    assert decision_ok == "force_ask"
    assert reason_ok is not None
    assert "[FINANCIAL TRANSACTION]" in reason_ok
    assert "+$15,000.00 USD" in reason_ok

    # 6. Tampering with the receipt file on disk to replace financial consequences with vague text is caught by BOTH verifiers
    for receipt_path in run_mutation.get_receipt_paths():
        if os.path.isfile(receipt_path):
            with open(receipt_path, "r", encoding="utf-8") as f:
                tampered_data = json.load(f)
            tampered_data["consequences"] = ["Updates account configuration"]
            with open(receipt_path, "w", encoding="utf-8") as f:
                json.dump(tampered_data, f)

    ok_verify, verify_msg, _ = run_mutation.load_and_verify_receipt(
        script_path=str(fin_script)
    )
    assert ok_verify is False
    assert "financial mutation is missing explicit monetary" in verify_msg

    decision_tampered, reason_tampered = evaluate_mutation_guard(
        f"python3 {runner_path} --script {fin_script} --execute"
    )
    assert decision_tampered == "deny"
    assert (
        reason_tampered is not None
        and "financial mutation in saved/data/last_dry_run.json is missing explicit monetary"
        in reason_tampered
    )

    entries = [
        json.loads(line)
        for line in audit_log_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [e["status"] for e in entries] == [
        "BLOCKED_FINANCIAL_CONSEQUENCE_MISSING",
        "BLOCKED_FINANCIAL_CONSEQUENCE_MISSING",
    ]
    assert all(e["request"]["is_financial_transaction"] is True for e in entries)

    for receipt_path in run_mutation.get_receipt_paths():
        if os.path.isfile(receipt_path):
            os.remove(receipt_path)


def test_rpc_interceptor_blocks_omitted_validate_only_and_non_validate_only_financial_rpcs(
    monkeypatch: Any,
) -> None:
    """Verifies _wrap_service_for_audit blocks omitted validate_only payloads and non-validate_only financial RPCs during dry-run and when execute_mutates=false."""
    run_mutation = _load_run_mutation_module()

    class _FinancialMockService:
        def __init__(self) -> None:
            self.invocations: list[tuple[str, Any]] = []

        # validate_only-capable financial RPCs
        def mutate_account_budget_proposal(self, request: Any = None) -> dict[str, Any]:
            self.invocations.append(("mutate_account_budget_proposal", request))
            return {"result": {"resource_name": "customers/1234567890/accountBudgetProposals/77"}, "request_id": "req-abp"}

        def upload_conversion_adjustments(self, request: Any = None) -> dict[str, Any]:
            self.invocations.append(("upload_conversion_adjustments", request))
            return {"results": [{"gclid_date_time_pair": {}}], "request_id": "req-adj"}

        # Non-validate_only-capable financial RPCs
        def mutate_billing_setup(self, request: Any = None) -> dict[str, Any]:
            self.invocations.append(("mutate_billing_setup", request))
            return {"result": {"resource_name": "customers/1234567890/billingSetups/88"}, "request_id": "req-bill"}

        def book_campaigns(self, request: Any = None) -> dict[str, Any]:
            self.invocations.append(("book_campaigns", request))
            return {"result": {}, "request_id": "req-book"}

        def apply_incentive(self, request: Any = None) -> dict[str, Any]:
            self.invocations.append(("apply_incentive", request))
            return {"coupon_code": "PROMO500", "request_id": "req-inc"}

        def provide_lead_feedback(self, request: Any = None) -> dict[str, Any]:
            self.invocations.append(("provide_lead_feedback", request))
            return {"credit_issuance_decision": "SUCCESS_NOT_REACHED_THRESHOLD", "request_id": "req-lsa"}

        def create_customer_client(self, request: Any = None) -> dict[str, Any]:
            self.invocations.append(("create_customer_client", request))
            return {"resource_name": "customers/9998887776", "request_id": "req-cust"}

        # Read-only companion financial methods on ReservationService / IncentiveService
        def quote_campaigns(self, request: Any = None) -> dict[str, Any]:
            self.invocations.append(("quote_campaigns", request))
            return {"quotes": [{"max_budget_micros": "12500000000"}]}

        def fetch_incentive(self, request: Any = None) -> dict[str, Any]:
            self.invocations.append(("fetch_incentive", request))
            return {"incentive_offer": {"amount_micros": "500000000"}}

    # --- Case 1: dry_run_mode=True (even with execute_mutates=true) ---
    monkeypatch.setenv("GOOGLE_ADS_EXECUTE_MUTATES", "execute_mutates = true")
    raw_dry = _FinancialMockService()
    dry_captured: list[dict[str, Any]] = []
    wrapped_dry = run_mutation._wrap_service_for_audit(
        raw_dry,
        "FinancialCompositeService",
        dry_captured,
        dry_run_mode=True,
    )

    # 1a. Read-only financial quotes/fetches pass unimpeded and are NOT captured as mutations
    assert wrapped_dry.quote_campaigns(request={"customer_id": "1234567890"})["quotes"]
    assert wrapped_dry.fetch_incentive(request={"country_code": "US"})["incentive_offer"]
    assert len(dry_captured) == 0
    assert len(raw_dry.invocations) == 2

    # 1b. Omitted validate_only (e.g., Protobuf3 default False stripped by MessageToDict) MUST be blocked in dry-run
    with pytest.raises(PermissionError, match="without validate_only=True"):
        wrapped_dry.mutate_account_budget_proposal(
            request={
                "customer_id": "1234567890",
                "operation": {
                    "create": {"proposed_spending_limit_micros": "25000000000"}
                },
            }
        )
    assert dry_captured[-1]["status"] == "BLOCKED_MISSING_VALIDATE_ONLY"
    assert len(raw_dry.invocations) == 2  # Underlying RPC was NOT called

    # 1c. Explicit validate_only=False MUST be blocked in dry-run
    with pytest.raises(PermissionError, match="without validate_only=True"):
        wrapped_dry.upload_conversion_adjustments(
            request={
                "customer_id": "1234567890",
                "validate_only": False,
                "conversion_adjustments": [
                    {"restatement_value": {"adjusted_value": 75.0, "currency_code": "USD"}}
                ],
            }
        )
    assert dry_captured[-1]["status"] == "BLOCKED_MISSING_VALIDATE_ONLY"
    assert len(raw_dry.invocations) == 2

    # 1d. Non-validate_only financial RPCs MUST be blocked in dry-run EVEN IF caller injects validate_only=True
    for non_vo_method in (
        "mutate_billing_setup",
        "book_campaigns",
        "apply_incentive",
        "provide_lead_feedback",
    ):
        with pytest.raises(
            PermissionError, match="does not support validate_only=True"
        ):
            getattr(wrapped_dry, non_vo_method)(
                request={"customer_id": "1234567890", "validate_only": True}
            )
        assert dry_captured[-1]["method"] == non_vo_method
        assert dry_captured[-1]["status"] == "BLOCKED_MISSING_VALIDATE_ONLY"
    assert len(raw_dry.invocations) == 2  # Zero live financial RPCs escaped during dry-run!

    # 1e. Genuine validate_only=True on validate_only-capable financial RPCs succeeds in dry-run
    abp_res = wrapped_dry.mutate_account_budget_proposal(
        request={
            "customer_id": "1234567890",
            "validate_only": True,
            "operation": {
                "create": {"proposed_spending_limit_micros": "25000000000"}
            },
        }
    )
    assert abp_res["request_id"] == "req-abp"
    cust_res = wrapped_dry.create_customer_client(
        request={
            "customer_id": "1234567890",
            "validate_only": True,
            "customer_client": {"currency_code": "USD", "time_zone": "America/New_York"},
        }
    )
    assert cust_res["request_id"] == "req-cust"
    assert dry_captured[-1]["status"] == "SUCCESS"
    assert len(raw_dry.invocations) == 4

    # --- Case 2: execute_mutates = false (outside dry_run_mode) ---
    monkeypatch.setenv("GOOGLE_ADS_EXECUTE_MUTATES", "execute_mutates = false")
    raw_disabled = _FinancialMockService()
    disabled_captured: list[dict[str, Any]] = []
    wrapped_disabled = run_mutation._wrap_service_for_audit(
        raw_disabled,
        "FinancialCompositeService",
        disabled_captured,
        dry_run_mode=False,
    )

    # 2a. Omitted validate_only is blocked by BLOCKED_MUTATES_DISABLED
    for vo_capable_method in ("mutate_account_budget_proposal", "create_customer_client"):
        with pytest.raises(PermissionError, match="execute_mutates = false"):
            getattr(wrapped_disabled, vo_capable_method)(
                request={"customer_id": "1234567890"}
            )
        assert disabled_captured[-1]["status"] == "BLOCKED_MUTATES_DISABLED"
    assert len(raw_disabled.invocations) == 0

    # 2b. Non-validate_only financial RPCs are blocked by BLOCKED_MUTATES_DISABLED even if validate_only=True is injected
    for non_vo_method in (
        "mutate_billing_setup",
        "book_campaigns",
        "apply_incentive",
        "provide_lead_feedback",
    ):
        with pytest.raises(PermissionError, match="execute_mutates = false"):
            getattr(wrapped_disabled, non_vo_method)(
                request={"customer_id": "1234567890", "validate_only": True}
            )
        assert disabled_captured[-1]["status"] == "BLOCKED_MUTATES_DISABLED"
    assert len(raw_disabled.invocations) == 0


def test_end_to_end_financial_transactions_preflight_and_atomic_sha256_workflows(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """End-to-end integration tests for:
    1. Non-validate_only guaranteed-spend reservation workflow (quote_campaigns preflight -> book_campaigns live execution, plus blocking unguarded book_campaigns in --dry-run).
    2. Atomic multi-RPC financial bundle (GoogleAdsService.mutate budget+ROAS strategy + ConversionAdjustmentUploadService restatement) with pre-RPC SHA-256 tamper protection on monetary values.
    """
    import json
    import subprocess
    import sys

    run_mutation = _load_run_mutation_module()
    audit_log_file = tmp_path / "e2e_financial_audit.jsonl"
    monkeypatch.setenv("GOOGLE_ADS_MUTATION_AUDIT_LOG", str(audit_log_file))

    for receipt_path in run_mutation.get_receipt_paths():
        if os.path.isfile(receipt_path):
            os.remove(receipt_path)

    runner_path = (
        Path(__file__).resolve().parent.parent
        / "plugins"
        / "google-ads-api-developer-assistant"
        / "skills"
        / "execute-mutation"
        / "scripts"
        / "run_mutation.py"
    )

    # Create a fake google.ads.googleads.client module in tmp_path/fake_sdk so subprocesses
    # test real GoogleAdsClient.get_service monkeypatching & pre-RPC interception end-to-end!
    fake_sdk_root = tmp_path / "fake_sdk"
    client_pkg = fake_sdk_root / "google" / "ads" / "googleads"
    client_pkg.mkdir(parents=True)
    (fake_sdk_root / "google" / "__init__.py").write_text("", encoding="utf-8")
    (fake_sdk_root / "google" / "ads" / "__init__.py").write_text("", encoding="utf-8")
    (client_pkg / "__init__.py").write_text("", encoding="utf-8")
    invocation_log = tmp_path / "rpc_invocations.jsonl"
    (client_pkg / "client.py").write_text(
        "import json, os\n"
        f"_LOG = {str(invocation_log)!r}\n"
        "def _record(svc, method, req):\n"
        "    with open(_LOG, 'a', encoding='utf-8') as f:\n"
        "        f.write(json.dumps({'service': svc, 'method': method, 'request': req}) + '\\n')\n"
        "class _ReservationService:\n"
        "    def quote_campaigns(self, request=None):\n"
        "        _record('ReservationService', 'quote_campaigns', request)\n"
        "        return {'quotes': [{'campaign': 'customers/1234567890/campaigns/777', 'max_budget_micros': '12500000000'}]}\n"
        "    def book_campaigns(self, request=None):\n"
        "        _record('ReservationService', 'book_campaigns', request)\n"
        "        return {'request_id': 'req-book-live-001', 'booked_campaigns': ['customers/1234567890/campaigns/777']}\n"
        "class _GoogleAdsService:\n"
        "    def mutate(self, request=None):\n"
        "        _record('GoogleAdsService', 'mutate', request)\n"
        "        vo = request.get('validate_only') if isinstance(request, dict) else False\n"
        "        return {\n"
        "            'request_id': 'req-ga-dry' if vo else 'req-ga-live',\n"
        "            'mutate_operation_responses': [\n"
        "                {'campaign_budget_result': {'resource_name': 'customers/1234567890/campaignBudgets/501'}},\n"
        "                {'bidding_strategy_result': {'resource_name': 'customers/1234567890/biddingStrategies/601'}},\n"
        "            ],\n"
        "        }\n"
        "class _ConversionAdjustmentUploadService:\n"
        "    def upload_conversion_adjustments(self, request=None):\n"
        "        _record('ConversionAdjustmentUploadService', 'upload_conversion_adjustments', request)\n"
        "        vo = request.get('validate_only') if isinstance(request, dict) else False\n"
        "        return {\n"
        "            'request_id': 'req-adj-dry' if vo else 'req-adj-live',\n"
        "            'results': [{'conversion_action': 'customers/1234567890/conversionActions/901'}],\n"
        "        }\n"
        "class GoogleAdsClient:\n"
        "    @classmethod\n"
        "    def load_from_storage(cls, path=None, version=None):\n"
        "        return cls()\n"
        "    def get_service(self, name, version=None):\n"
        "        if name == 'ReservationService':\n"
        "            return _ReservationService()\n"
        "        if name == 'GoogleAdsService':\n"
        "            return _GoogleAdsService()\n"
        "        if name == 'ConversionAdjustmentUploadService':\n"
        "            return _ConversionAdjustmentUploadService()\n"
        "        raise ValueError(f'Unknown service {name}')\n",
        encoding="utf-8",
    )

    sub_env = os.environ.copy()
    existing_py_path = sub_env.get("PYTHONPATH", "")
    sub_env["PYTHONPATH"] = (
        f"{fake_sdk_root}{os.pathsep}{existing_py_path}"
        if existing_py_path
        else str(fake_sdk_root)
    )
    sub_env["GOOGLE_ADS_MUTATION_AUDIT_LOG"] = str(audit_log_file)
    sub_env["GOOGLE_ADS_EXECUTE_MUTATES"] = "execute_mutates = true"

    # =========================================================================
    # WORKFLOW A: Non-validate_only ReservationService (quote_campaigns -> book_campaigns)
    # =========================================================================
    # A1. Unguarded script that mistakenly calls book_campaigns during --dry-run is BLOCKED BEFORE RPC!
    unguarded_book_script = tmp_path / "unguarded_book.py"
    unguarded_book_script.write_text(
        "from google.ads.googleads.client import GoogleAdsClient\n"
        "client = GoogleAdsClient.load_from_storage(path='config/google-ads.yaml')\n"
        "svc = client.get_service('ReservationService')\n"
        "svc.book_campaigns(request={'customer_id': '1234567890'})\n",
        encoding="utf-8",
    )
    unguarded_proc = subprocess.run(
        [
            sys.executable,
            str(runner_path),
            "--script",
            str(unguarded_book_script),
            "--dry-run",
            "--customer-id",
            "1234567890",
            "--operation",
            "ReservationService.book_campaigns",
            "--before",
            "Unbooked reservation quote: $12,500.00 USD",
            "--after",
            "Booked guaranteed reservation: $12,500.00 USD",
            "--consequences",
            "Commits $12,500.00 USD guaranteed spend booking",
            "--reversibility",
            "IRREVERSIBLE",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=sub_env,
    )
    assert unguarded_proc.returncode != 0
    assert "does not support validate_only=True" in unguarded_proc.stderr
    assert not invocation_log.exists(), "book_campaigns must NEVER reach the transport during --dry-run!"

    # A2. Proper preflighted script: runs quote_campaigns on --dry-run and book_campaigns only on --execute
    proper_book_script = tmp_path / "proper_book_reservation.py"
    proper_book_script.write_text(
        "import argparse\n"
        "from google.ads.googleads.client import GoogleAdsClient\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--customer-id', required=True)\n"
        "parser.add_argument('--dry-run', action='store_true')\n"
        "parser.add_argument('--execute', action='store_true')\n"
        "args = parser.parse_args()\n"
        "client = GoogleAdsClient.load_from_storage(path='config/google-ads.yaml')\n"
        "svc = client.get_service('ReservationService')\n"
        "if args.execute:\n"
        "    resp = svc.book_campaigns(request={'customer_id': args.customer_id, 'campaigns': ['customers/1234567890/campaigns/777']})\n"
        "    print('Booked:', resp['request_id'])\n"
        "else:\n"
        "    quote = svc.quote_campaigns(request={'customer_id': args.customer_id})\n"
        "    print('Preflight quote verified:', quote['quotes'][0]['max_budget_micros'])\n",
        encoding="utf-8",
    )

    dry_book_proc = subprocess.run(
        [
            sys.executable,
            str(runner_path),
            "--script",
            str(proper_book_script),
            "--dry-run",
            "--customer-id",
            "1234567890",
            "--operation",
            "ReservationService.book_campaigns",
            "--before",
            "Quoted reservation: $12,500.00 USD (unbooked)",
            "--after",
            "Booked reservation: $12,500.00 USD guaranteed spend",
            "--consequences",
            "Commits $12,500.00 USD guaranteed spend booking; Non-cancellable contractual billing commitment",
            "--reversibility",
            "IRREVERSIBLE",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=sub_env,
    )
    assert dry_book_proc.returncode == 0, dry_book_proc.stderr
    assert "Financial Txn : YES" in dry_book_proc.stdout

    invocations_after_dry = [
        json.loads(line)
        for line in invocation_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [c["method"] for c in invocations_after_dry] == ["quote_campaigns"]

    exec_book_proc = subprocess.run(
        [
            sys.executable,
            str(runner_path),
            "--script",
            str(proper_book_script),
            "--execute",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=sub_env,
    )
    assert exec_book_proc.returncode == 0, exec_book_proc.stderr
    assert "req-book-live-001" in exec_book_proc.stdout

    # =========================================================================
    # WORKFLOW B: Atomic Cross-Resource Financial Bundle + Conversion Value Restatement
    #             with Pre-RPC Monetary Tamper Detection
    # =========================================================================
    tamper_env_file = tmp_path / "monetary_override.txt"
    atomic_fin_script = tmp_path / "atomic_financial_bundle.py"
    atomic_fin_script.write_text(
        "import argparse, pathlib\n"
        "from google.ads.googleads.client import GoogleAdsClient\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--customer-id', required=True)\n"
        "parser.add_argument('--dry-run', action='store_true')\n"
        "parser.add_argument('--execute', action='store_true')\n"
        "args = parser.parse_args()\n"
        "is_dry = not args.execute\n"
        f"override_file = pathlib.Path({str(tamper_env_file)!r})\n"
        "budget_micros = override_file.read_text(encoding='utf-8').strip() if override_file.exists() else '150000000'\n"
        "client = GoogleAdsClient.load_from_storage(path='config/google-ads.yaml')\n"
        "ga_svc = client.get_service('GoogleAdsService')\n"
        "ga_svc.mutate(request={\n"
        "    'customer_id': args.customer_id,\n"
        "    'validate_only': is_dry,\n"
        "    'mutate_operations': [\n"
        "        {'campaign_budget_operation': {'create': {'amount_micros': budget_micros}}},\n"
        "        {'bidding_strategy_operation': {'create': {'target_roas': {'target_roas': 3.5}}}},\n"
        "    ],\n"
        "})\n"
        "adj_svc = client.get_service('ConversionAdjustmentUploadService')\n"
        "adj_svc.upload_conversion_adjustments(request={\n"
        "    'customer_id': args.customer_id,\n"
        "    'validate_only': is_dry,\n"
        "    'partial_failure': True,\n"
        "    'conversion_adjustments': [\n"
        "        {'adjustment_type': 'RESTATEMENT', 'restatement_value': {'adjusted_value': 85.50, 'currency_code': 'USD'}}\n"
        "    ],\n"
        "})\n"
        "print('Atomic financial bundle completed, dry_run=', is_dry)\n",
        encoding="utf-8",
    )

    dry_atomic = subprocess.run(
        [
            sys.executable,
            str(runner_path),
            "--script",
            str(atomic_fin_script),
            "--dry-run",
            "--customer-id",
            "1234567890",
            "--operation",
            "GoogleAdsService.mutate + ConversionAdjustmentUploadService.upload_conversion_adjustments",
            "--before",
            "No shared budget/ROAS portfolio; order conv value $140.00 USD",
            "--after",
            "New $150.00/day budget + 350% Target ROAS strategy; order conv restated to $85.50 USD",
            "--consequences",
            "Creates $150.00/day budget (~$4,560.00/month max spend exposure) with 350% Target ROAS bidding; Restates conversion value to $85.50 USD",
            "--reversibility",
            "REVERSIBLE",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=sub_env,
    )
    assert dry_atomic.returncode == 0, dry_atomic.stderr

    # B1. Tamper monetary amount_micros at runtime (150_000_000 -> 950_000_000 micros) without modifying script bytes!
    # Pre-RPC SHA-256 verification MUST catch the altered monetary amount BEFORE sending the live RPC!
    tamper_env_file.write_text("950000000", encoding="utf-8")
    inv_count_before_tamper = len(
        invocation_log.read_text(encoding="utf-8").splitlines()
    )
    tampered_exec = subprocess.run(
        [
            sys.executable,
            str(runner_path),
            "--script",
            str(atomic_fin_script),
            "--execute",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=sub_env,
    )
    assert tampered_exec.returncode != 0
    assert "BLOCKED_SHA256_MISMATCH" in tampered_exec.stderr or "SHA-256 mismatch" in tampered_exec.stderr
    inv_count_after_tamper = len(
        invocation_log.read_text(encoding="utf-8").splitlines()
    )
    assert inv_count_after_tamper == inv_count_before_tamper, (
        "Altered monetary amount_micros must be blocked BEFORE any live RPC is sent!"
    )

    # B2. Remove runtime monetary tamper -> exact approved $150.00/day + $85.50 restatement executes cleanly!
    tamper_env_file.unlink()
    clean_exec = subprocess.run(
        [
            sys.executable,
            str(runner_path),
            "--script",
            str(atomic_fin_script),
            "--execute",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=sub_env,
    )
    assert clean_exec.returncode == 0, clean_exec.stderr
    assert "Atomic financial bundle completed, dry_run= False" in clean_exec.stdout

    audit_entries = [
        json.loads(line)
        for line in audit_log_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [e["status"] for e in audit_entries] == [
        "BLOCKED_MISSING_VALIDATE_ONLY",
        "DRY_RUN_PASSED",
        "SUCCESS",
        "DRY_RUN_PASSED",
        "BLOCKED_SHA256_MISMATCH",
        "SUCCESS",
    ]
    assert all(e["request"]["is_financial_transaction"] is True for e in audit_entries)
    # Verify both Workflow A live book_campaigns and Workflow B live multi-RPC bundle have verified SHA-256 and request IDs
    assert audit_entries[2]["request"]["request_sha256_verified"] is True
    assert audit_entries[2]["response"]["google_ads_request_ids"] == ["req-book-live-001"]
    assert audit_entries[5]["request"]["request_sha256_verified"] is True
    assert audit_entries[5]["response"]["google_ads_request_ids"] == [
        "req-ga-live",
        "req-adj-live",
    ]

    for receipt_path in run_mutation.get_receipt_paths():
        if os.path.isfile(receipt_path):
            os.remove(receipt_path)


def test_real_v26_financial_protobuf_requests_serialization_sha256_and_interception(
    monkeypatch: Any,
) -> None:
    """Verifies real Google Ads API v26 protobuf request messages across financial services:
    1. Exact descriptor parity for validate_only vs non-validate_only financial RPCs.
    2. Protobuf3 default validate_only=False (omitted by to_dict / MessageToDict) is blocked in dry-run and when execute_mutates=false.
    3. Canonical SHA-256 parity across validate_only=True and validate_only=False on real financial protos, plus monetary field tamper detection.
    """
    bundled_sdk = (
        Path(__file__).resolve().parent.parent
        / "plugins"
        / "google-ads-api-developer-assistant"
        / "client_libs"
        / "google-ads-python"
    )
    if (bundled_sdk / "google" / "ads" / "googleads" / "v26").is_dir():
        monkeypatch.syspath_prepend(str(bundled_sdk))

    try:
        from google.ads.googleads.v26.services.types import (
            account_budget_proposal_service,
            ad_group_bid_modifier_service,
            bidding_data_exclusion_service,
            bidding_seasonality_adjustment_service,
            bidding_strategy_service,
            billing_setup_service,
            campaign_bid_modifier_service,
            campaign_budget_service,
            campaign_draft_service,
            conversion_adjustment_upload_service,
            conversion_value_rule_service,
            customer_service,
            experiment_service,
            google_ads_service,
            incentive_service,
            local_services_lead_service,
            reservation_service,
        )
    except ImportError:
        pytest.skip("Google Ads Python v26 SDK not available in client_libs or site-packages")

    run_mutation = _load_run_mutation_module()

    # 1. Verify exact v26 protobuf descriptor parity with _NON_VALIDATE_ONLY_MUTATION_METHODS
    proto_method_matrix = (
        ("mutate_billing_setup", billing_setup_service.MutateBillingSetupRequest, False),
        ("book_campaigns", reservation_service.BookCampaignsRequest, False),
        ("apply_incentive", incentive_service.ApplyIncentiveRequest, False),
        ("provide_lead_feedback", local_services_lead_service.ProvideLeadFeedbackRequest, False),
        ("mutate_account_budget_proposal", account_budget_proposal_service.MutateAccountBudgetProposalRequest, True),
        ("mutate_campaign_budgets", campaign_budget_service.MutateCampaignBudgetsRequest, True),
        ("create_customer_client", customer_service.CreateCustomerClientRequest, True),
        ("mutate_bidding_strategies", bidding_strategy_service.MutateBiddingStrategiesRequest, True),
        ("mutate_bidding_seasonality_adjustments", bidding_seasonality_adjustment_service.MutateBiddingSeasonalityAdjustmentsRequest, True),
        ("mutate_bidding_data_exclusions", bidding_data_exclusion_service.MutateBiddingDataExclusionsRequest, True),
        ("mutate_campaign_bid_modifiers", campaign_bid_modifier_service.MutateCampaignBidModifiersRequest, True),
        ("mutate_ad_group_bid_modifiers", ad_group_bid_modifier_service.MutateAdGroupBidModifiersRequest, True),
        ("mutate_conversion_value_rules", conversion_value_rule_service.MutateConversionValueRulesRequest, True),
        ("upload_conversion_adjustments", conversion_adjustment_upload_service.UploadConversionAdjustmentsRequest, True),
        ("graduate_experiment", experiment_service.GraduateExperimentRequest, True),
        ("promote_experiment", experiment_service.PromoteExperimentRequest, True),
        ("schedule_experiment", experiment_service.ScheduleExperimentRequest, True),
        ("end_experiment", experiment_service.EndExperimentRequest, True),
        ("promote_campaign_draft", campaign_draft_service.PromoteCampaignDraftRequest, True),
        ("mutate", google_ads_service.MutateGoogleAdsRequest, True),
    )
    for method_name, proto_cls, expected_has_vo in proto_method_matrix:
        actual_has_vo = "validate_only" in proto_cls.meta.fields
        assert actual_has_vo is expected_has_vo, (
            f"v26 {proto_cls.__name__} validate_only support changed: expected {expected_has_vo}, got {actual_has_vo}"
        )
        assert (method_name not in run_mutation._NON_VALIDATE_ONLY_MUTATION_METHODS) is expected_has_vo

    # 2. Construct real v26 financial protobuf requests and verify canonical SHA-256 & monetary tamper detection
    # 2a. AccountBudgetProposal ($25,000.00 spending limit)
    abp_dry = account_budget_proposal_service.MutateAccountBudgetProposalRequest()
    abp_dry.customer_id = "1234567890"
    abp_dry.validate_only = True
    abp_dry.operation.create.billing_setup = "customers/1234567890/billingSetups/555"
    abp_dry.operation.create.proposed_spending_limit_micros = 25_000_000_000

    abp_live = account_budget_proposal_service.MutateAccountBudgetProposalRequest()
    abp_live.customer_id = "1234567890"
    abp_live.validate_only = False  # Proto3 default False (omitted in serialized dict)
    abp_live.operation.create.billing_setup = "customers/1234567890/billingSetups/555"
    abp_live.operation.create.proposed_spending_limit_micros = 25_000_000_000

    abp_tampered = account_budget_proposal_service.MutateAccountBudgetProposalRequest()
    abp_tampered.customer_id = "1234567890"
    abp_tampered.validate_only = False
    abp_tampered.operation.create.billing_setup = "customers/1234567890/billingSetups/555"
    abp_tampered.operation.create.proposed_spending_limit_micros = 25_000_000_001

    sha_abp_dry = run_mutation.compute_mutate_request_sha256(
        "AccountBudgetProposalService", "mutate_account_budget_proposal", abp_dry
    )
    sha_abp_live = run_mutation.compute_mutate_request_sha256(
        "AccountBudgetProposalService", "mutate_account_budget_proposal", abp_live
    )
    sha_abp_tampered = run_mutation.compute_mutate_request_sha256(
        "AccountBudgetProposalService", "mutate_account_budget_proposal", abp_tampered
    )
    assert sha_abp_dry == sha_abp_live
    assert sha_abp_dry != sha_abp_tampered

    # 2b. ConversionAdjustmentUploadService restatement ($199.99 -> $49.99 USD)
    adj_dry = conversion_adjustment_upload_service.UploadConversionAdjustmentsRequest()
    adj_dry.customer_id = "1234567890"
    adj_dry.partial_failure = True
    adj_dry.validate_only = True
    adj_item = conversion_adjustment_upload_service.ConversionAdjustment()
    adj_item.conversion_action = "customers/1234567890/conversionActions/321"
    adj_item.restatement_value.adjusted_value = 199.99
    adj_item.restatement_value.currency_code = "USD"
    adj_dry.conversion_adjustments.append(adj_item)

    adj_live = conversion_adjustment_upload_service.UploadConversionAdjustmentsRequest()
    adj_live.customer_id = "1234567890"
    adj_live.partial_failure = True
    adj_live.validate_only = False
    adj_live.conversion_adjustments.append(adj_item)

    adj_tampered = conversion_adjustment_upload_service.UploadConversionAdjustmentsRequest()
    adj_tampered.customer_id = "1234567890"
    adj_tampered.partial_failure = True
    adj_tampered.validate_only = False
    adj_item_diff = conversion_adjustment_upload_service.ConversionAdjustment()
    adj_item_diff.conversion_action = "customers/1234567890/conversionActions/321"
    adj_item_diff.restatement_value.adjusted_value = 49.99
    adj_item_diff.restatement_value.currency_code = "USD"
    adj_tampered.conversion_adjustments.append(adj_item_diff)

    assert run_mutation.compute_mutate_request_sha256(
        "ConversionAdjustmentUploadService", "upload_conversion_adjustments", adj_dry
    ) == run_mutation.compute_mutate_request_sha256(
        "ConversionAdjustmentUploadService", "upload_conversion_adjustments", adj_live
    )
    assert run_mutation.compute_mutate_request_sha256(
        "ConversionAdjustmentUploadService", "upload_conversion_adjustments", adj_dry
    ) != run_mutation.compute_mutate_request_sha256(
        "ConversionAdjustmentUploadService", "upload_conversion_adjustments", adj_tampered
    )

    # 3. Real proto3 default validate_only=False (abp_live) and non-validate_only protos (BillingSetup, Incentive)
    #    MUST be blocked in dry_run_mode=True and when execute_mutates=false!
    billing_req = billing_setup_service.MutateBillingSetupRequest()
    billing_req.customer_id = "1234567890"
    billing_req.operation.create.payments_account = "paymentsAccounts/1111-2222-3333-4444"

    incentive_req = incentive_service.ApplyIncentiveRequest()
    incentive_req.customer_id = "1234567890"
    incentive_req.selected_incentive_id = 777
    incentive_req.country_code = "US"

    class _ProtoCapturingService:
        def __init__(self) -> None:
            self.calls = 0

        def mutate_account_budget_proposal(self, request: Any = None) -> dict[str, Any]:
            self.calls += 1
            return {"request_id": "req-proto-abp"}

        def mutate_billing_setup(self, request: Any = None) -> dict[str, Any]:
            self.calls += 1
            return {"request_id": "req-proto-bill"}

        def apply_incentive(self, request: Any = None) -> dict[str, Any]:
            self.calls += 1
            return {"request_id": "req-proto-inc"}

    monkeypatch.setenv("GOOGLE_ADS_EXECUTE_MUTATES", "execute_mutates = true")
    proto_svc = _ProtoCapturingService()
    proto_captured: list[dict[str, Any]] = []
    wrapped_proto_dry = run_mutation._wrap_service_for_audit(
        proto_svc,
        "ProtoFinancialService",
        proto_captured,
        dry_run_mode=True,
    )

    # Proto3 validate_only=True succeeds in dry-run
    assert wrapped_proto_dry.mutate_account_budget_proposal(request=abp_dry)["request_id"] == "req-proto-abp"
    assert proto_svc.calls == 1
    assert run_mutation.is_financial_mutation(rpc_calls=proto_captured) is True

    # Proto3 default validate_only=False (both proto-plus Message and raw _pb MessageToDict)
    # is BLOCKED BEFORE RPC in dry-run!
    with pytest.raises(PermissionError, match="without validate_only=True"):
        wrapped_proto_dry.mutate_account_budget_proposal(request=abp_live)
    with pytest.raises(PermissionError, match="without validate_only=True"):
        wrapped_proto_dry.mutate_account_budget_proposal(request=abp_live._pb)
    assert proto_svc.calls == 1
    assert proto_captured[-1]["status"] == "BLOCKED_MISSING_VALIDATE_ONLY"

    # Real MutateBillingSetupRequest and ApplyIncentiveRequest are BLOCKED BEFORE RPC in dry-run!
    with pytest.raises(PermissionError, match="does not support validate_only=True"):
        wrapped_proto_dry.mutate_billing_setup(request=billing_req)
    with pytest.raises(PermissionError, match="does not support validate_only=True"):
        wrapped_proto_dry.apply_incentive(request=incentive_req)
    assert proto_svc.calls == 1

    # And when execute_mutates = false, proto3 default validate_only=False (both proto-plus and raw _pb)
    # is BLOCKED BEFORE RPC!
    monkeypatch.setenv("GOOGLE_ADS_EXECUTE_MUTATES", "execute_mutates = false")
    proto_svc_disabled = _ProtoCapturingService()
    disabled_proto_captured: list[dict[str, Any]] = []
    wrapped_proto_disabled = run_mutation._wrap_service_for_audit(
        proto_svc_disabled,
        "ProtoFinancialService",
        disabled_proto_captured,
        dry_run_mode=False,
    )
    with pytest.raises(PermissionError, match="execute_mutates = false"):
        wrapped_proto_disabled.mutate_account_budget_proposal(request=abp_live)
    with pytest.raises(PermissionError, match="execute_mutates = false"):
        wrapped_proto_disabled.mutate_account_budget_proposal(request=abp_live._pb)
    assert proto_svc_disabled.calls == 0
    assert disabled_proto_captured[-1]["status"] == "BLOCKED_MUTATES_DISABLED"






"""Unit tests for the 4-Step HITL Mutation & Consequence Verification Guard."""

from importlib.util import module_from_spec, spec_from_file_location
import os
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.config_init import evaluate_mutation_guard


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




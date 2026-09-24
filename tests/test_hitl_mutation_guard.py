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

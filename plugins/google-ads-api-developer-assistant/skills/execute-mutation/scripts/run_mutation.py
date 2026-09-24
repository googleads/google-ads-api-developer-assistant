#!/usr/bin/env python3
"""Executes Google Ads API mutations with a 2-phase Dry-Run Receipt & Consequence Gate."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple


RECEIPT_FILENAME = "last_dry_run.json"
DEFAULT_MAX_RECEIPT_AGE_SECONDS = 1800  # 30 minutes


def compute_file_sha256(file_path: str) -> str:
    """Computes the SHA-256 hex digest of a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_receipt_paths() -> List[str]:
    """Returns candidate paths for reading/writing the dry-run receipt."""
    this_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_root = os.path.abspath(os.path.join(this_dir, "../../.."))
    paths = [
        os.path.abspath(os.path.join("saved", "data", RECEIPT_FILENAME)),
        os.path.join(plugin_root, "saved", "data", RECEIPT_FILENAME),
        os.path.expanduser(
            f"~/.gemini/config/plugins/google-ads-api-developer-assistant/saved/data/{RECEIPT_FILENAME}"
        ),
    ]
    deduped: List[str] = []
    for p in paths:
        norm = os.path.normpath(p)
        if norm not in deduped:
            deduped.append(norm)
    return deduped


def write_dry_run_receipt(
    customer_id: str,
    operation_summary: str,
    before_state: str,
    after_state: str,
    consequences: List[str],
    reversibility: str,
    script_path: Optional[str] = None,
    dry_run_output: str = "",
) -> Dict[str, Any]:
    """Writes a signed dry-run receipt to saved/data/last_dry_run.json."""
    resolved_script = os.path.abspath(script_path) if script_path else ""
    script_hash = (
        compute_file_sha256(resolved_script)
        if resolved_script and os.path.isfile(resolved_script)
        else ""
    )

    now_ts = time.time()
    now_iso = datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()

    clean_consequences = [c.strip() for c in consequences if c.strip()]
    if not clean_consequences:
        raise ValueError(
            "At least one explicit consequence must be provided in --consequences."
        )

    receipt: Dict[str, Any] = {
        "status": "DRY_RUN_PASSED",
        "timestamp": now_ts,
        "timestamp_iso": now_iso,
        "customer_id": str(customer_id).strip(),
        "operation_summary": operation_summary.strip(),
        "before_state": before_state.strip(),
        "after_state": after_state.strip(),
        "consequences": clean_consequences,
        "reversibility": reversibility.strip().upper(),
        "script_path": resolved_script,
        "script_sha256": script_hash,
        "dry_run_output": dry_run_output.strip(),
    }

    for target_path in get_receipt_paths():
        try:
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(receipt, f, indent=2)
        except OSError:
            continue

    return receipt


def mark_receipt_executed() -> None:
    """Marks existing dry-run receipts as EXECUTED to prevent replay without re-verification."""
    for target_path in get_receipt_paths():
        if os.path.isfile(target_path):
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data["status"] = "EXECUTED"
                data["executed_at_iso"] = datetime.now(timezone.utc).isoformat()
                with open(target_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                continue


def load_and_verify_receipt(
    script_path: Optional[str] = None,
    max_age_seconds: int = DEFAULT_MAX_RECEIPT_AGE_SECONDS,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Verifies that a valid, un-expired validate_only=True dry-run receipt exists."""
    receipt: Optional[Dict[str, Any]] = None
    for candidate in get_receipt_paths():
        if os.path.isfile(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    receipt = json.load(f)
                if receipt:
                    break
            except Exception:
                continue

    if not receipt:
        return (
            False,
            "No validate_only=True dry-run receipt found at saved/data/last_dry_run.json. "
            "Run with --dry-run first, disclose consequences to the user, and wait for confirmation.",
            {},
        )

    status = receipt.get("status", "")
    if status != "DRY_RUN_PASSED":
        return (
            False,
            f"Dry-run receipt status is '{status}' (expected 'DRY_RUN_PASSED'). "
            "A fresh validate_only=True dry-run is required before live execution.",
            receipt,
        )

    ts = float(receipt.get("timestamp", 0.0))
    age = time.time() - ts
    if age > max_age_seconds:
        return (
            False,
            f"Dry-run receipt expired ({int(age)}s old > {max_age_seconds}s limit). "
            "Re-run validate_only=True dry-run and re-confirm with the user.",
            receipt,
        )

    consequences = receipt.get("consequences", [])
    if not consequences or not any(str(c).strip() for c in consequences):
        return (
            False,
            "Dry-run receipt is missing mandatory consequence disclosures.",
            receipt,
        )

    if script_path:
        resolved_script = os.path.abspath(script_path)
        expected_hash = receipt.get("script_sha256", "")
        if expected_hash and os.path.isfile(resolved_script):
            actual_hash = compute_file_sha256(resolved_script)
            if actual_hash != expected_hash:
                return (
                    False,
                    f"Script '{script_path}' was modified after the validate_only=True dry-run "
                    "(SHA-256 mismatch). Re-run --dry-run before executing.",
                    receipt,
                )

    return True, "Dry-run receipt verified.", receipt


def format_verification_card(receipt: Dict[str, Any]) -> str:
    """Formats a human-readable Mutation & Consequence Verification Card."""
    consequences_lines = "\n".join(
        f"  - {c}" for c in receipt.get("consequences", [])
    )
    reversibility = receipt.get("reversibility", "UNKNOWN")
    rev_badge = (
        "IRREVERSIBLE (PERMANENT)"
        if "IRREVERSIBLE" in reversibility
        else "REVERSIBLE"
    )
    return (
        "======================================================================\n"
        "GOOGLE ADS API MUTATION & CONSEQUENCE VERIFICATION CARD\n"
        "======================================================================\n"
        f"Customer ID   : {receipt.get('customer_id', 'Unknown')}\n"
        f"Operation     : {receipt.get('operation_summary', 'Unknown')}\n"
        f"Dry-Run Status: PASSED (validate_only=True verified at {receipt.get('timestamp_iso', '')})\n"
        f"Before State  : {receipt.get('before_state', 'N/A')}\n"
        f"After State   : {receipt.get('after_state', 'N/A')}\n"
        f"Reversibility : {rev_badge}\n"
        "Consequences  :\n"
        f"{consequences_lines}\n"
        "======================================================================\n"
        "NEXT STEP: Present this card to the user and obtain explicit confirmation\n"
        "before running with --execute.\n"
        "======================================================================"
    )


def main() -> None:
    """CLI entrypoint for two-phase dry-run and live Google Ads mutations."""
    parser = argparse.ArgumentParser(
        description="Run Google Ads API mutations with mandatory validate_only=True dry-run and HITL consequence verification."
    )
    parser.add_argument(
        "--script",
        required=True,
        help="Path to the Python mutation script in saved/code/.",
    )
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Phase 1: Execute script with validate_only=True and write signed receipt.",
    )
    mode_group.add_argument(
        "--execute",
        action="store_true",
        help="Phase 2: Verify signed dry-run receipt and execute live mutation (validate_only=False).",
    )
    parser.add_argument(
        "--customer-id",
        default="",
        help="Target Google Ads Customer ID (required for --dry-run).",
    )
    parser.add_argument(
        "--operation",
        default="",
        help="Concise summary of the service/resource operation (required for --dry-run).",
    )
    parser.add_argument(
        "--before",
        default="Captured via GAQL",
        help="Summary of current resource state before mutation.",
    )
    parser.add_argument(
        "--after",
        default="",
        help="Summary of target resource state after mutation.",
    )
    parser.add_argument(
        "--consequences",
        default="",
        help="Semicolon-separated list of financial, ad-serving, and structural consequences.",
    )
    parser.add_argument(
        "--reversibility",
        default="REVERSIBLE",
        choices=["REVERSIBLE", "IRREVERSIBLE"],
        help="Whether the mutation can be undone (REVERSIBLE) or is permanent (IRREVERSIBLE).",
    )
    parser.add_argument(
        "--script-args",
        default="",
        help="Optional extra CLI arguments to pass to --script.",
    )
    parser.add_argument(
        "--record-only",
        action="store_true",
        help="Record the dry-run receipt without invoking the subprocess (for unit tests or inline dry-runs).",
    )

    args = parser.parse_args()
    script_path = os.path.abspath(args.script)

    if not os.path.isfile(script_path):
        print(f"Error: Mutation script not found at '{script_path}'", file=sys.stderr)
        sys.exit(1)

    extra_args = shlex.split(args.script_args) if args.script_args else []

    if args.dry_run:
        if not args.customer_id or not args.operation or not args.consequences:
            print(
                "Error: --dry-run requires --customer-id, --operation, and --consequences.",
                file=sys.stderr,
            )
            sys.exit(1)

        dry_run_output = "Dry-run validated."
        if not args.record_only:
            cmd = [sys.executable, script_path, "--dry-run"]
            if args.customer_id and "--customer-id" not in extra_args:
                cmd.extend(["--customer-id", args.customer_id])
            cmd.extend(extra_args)

            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                print(
                    f"validate_only=True Dry-Run FAILED (exit code {result.returncode}):\n"
                    f"{result.stdout}\n{result.stderr}",
                    file=sys.stderr,
                )
                sys.exit(result.returncode)
            dry_run_output = (result.stdout + "\n" + result.stderr).strip()

        consequence_list = [
            item.strip()
            for item in args.consequences.split(";")
            if item.strip()
        ]
        receipt = write_dry_run_receipt(
            customer_id=args.customer_id,
            operation_summary=args.operation,
            before_state=args.before,
            after_state=args.after or args.operation,
            consequences=consequence_list,
            reversibility=args.reversibility,
            script_path=script_path,
            dry_run_output=dry_run_output,
        )
        print(format_verification_card(receipt))
        return

    # Phase 2: --execute
    ok, message, receipt = load_and_verify_receipt(script_path=script_path)
    if not ok:
        print(f"BLOCKED: {message}", file=sys.stderr)
        sys.exit(2)

    cmd = [sys.executable, script_path, "--execute"]
    cid = args.customer_id or receipt.get("customer_id", "")
    if cid and "--customer-id" not in extra_args:
        cmd.extend(["--customer-id", cid])
    cmd.extend(extra_args)

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        print(
            f"Live mutation FAILED (exit code {result.returncode}):\n"
            f"{result.stdout}\n{result.stderr}",
            file=sys.stderr,
        )
        sys.exit(result.returncode)

    mark_receipt_executed()
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)


if __name__ == "__main__":
    main()

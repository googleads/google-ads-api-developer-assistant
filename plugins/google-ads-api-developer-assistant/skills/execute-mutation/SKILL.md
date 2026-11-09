---
name: execute-mutation
description: Executes Google Ads API write/mutation operations using the mandatory 4-Step Human-in-the-Loop (HITL) Verification & Consequence Disclosure Protocol (GAQL Before-State lookup, validate_only=True dry-run receipt, consequence matrix evaluation, and hook-gated live execution).
---

# Execute Mutation Skill (4-Step HITL & Consequence Protocol)

When a user requests a write or mutation operation against the Google Ads API (`create`, `update`, `apply_recommendation`, or offline conversion uploads), you MUST follow this 4-step workflow.

> **Hard Policy — Only `create` and `update` Mutations Allowed (Deletion Prohibited):**
> Only **`create`** and **`update`** operations are permitted. Deletion (`remove` / `remove_all` operations, `remove_*` RPC calls, or setting `status = REMOVED`) is **strictly prohibited** across all layers (`PreToolUse` hook, `run_mutation.py` pre-RPC & receipt verifiers, and A2A sidecar). If a user asks to delete or remove a resource, refuse the deletion and offer to update its `status` to `PAUSED` instead.

> **Prerequisite — User Mutate Configuration (`config/assistant_config` & `config/financial_limits`):**
> By default, live mutations are disabled (`execute_mutates = false` in `config/assistant_config`). While `validate_only=True` dry-runs (`--dry-run`) for `create` and `update` operations are allowed, any live mutation (`--execute` or `validate_only=False`) is deterministically blocked by both the `PreToolUse` hook (`config/config_init.py`) and `run_mutation.py` unless `config/assistant_config` is set to:
> ```toml
> execute_mutates = true
> ```
> In addition, `config/financial_limits` configures per-service, per-field upper limits (`Service.field`) across all financial Google Ads API mutate operations (in the exact numeric format and monetary unit required by each API service: `micros` (`int64`), `currency_units` (`double`), `decimal_ratio` (`double`), or `micros_proportion` (`int64`)). By default, each `Service.field` is set to `0` (`int64`) or `0.0` (`double`) so that financial fields are **not modifiable by default**. The user must supply a value `> 0` to make a field modifiable; the supplied value is the **upper limit**. Any mutation that attempts to modify a field whose value is `0` / `0.0` (not modifiable by default) or exceeds its configured upper limit (`> 0`) returns an error, informs the user at the HITL step, logs `BLOCKED_FINANCIAL_LIMIT_EXCEEDED` to `saved/logs/mutation_audit.jsonl`, and refuses to execute. Users can inspect or update limits via `skills/execute-mutation/scripts/set_financial_limits.py` (or `./set_financial_limits.py`).

Live mutations without both `execute_mutates = true` in `config/assistant_config` and a verified `validate_only=True` dry-run receipt (`saved/data/last_dry_run.json`) are deterministically blocked by the `PreToolUse` hook.

---

## Step 1: Pre-Mutation State & Blast Radius Lookup (Mandatory Read)

Before writing or running any mutation code:
1. Query the target resource(s) via `GoogleAdsService.search_stream` to capture the **Before State**:
   - Exact resource name(s) (e.g., `customers/1234567890/campaigns/987654321`).
   - Current `status` (`ENABLED`, `PAUSED`, `REMOVED`).
   - Current financial/bidding settings (`campaign_budget.amount_micros`, `ad_group.cpc_bid_micros`, `bidding_strategy_type`). Convert all `micros` values to local currency by dividing by `1,000,000`.
2. Query the downstream **Blast Radius** (e.g., count of active child `ad_group` and `ad_group_ad` resources, 7-day impressions/clicks/cost, or linked campaigns if mutating a shared budget/asset/negative keyword list).

---

## Step 2: Consequence Matrix Evaluation

Evaluate and articulate the exact consequences of the requested change across these categories:

| Mutation Category | Mandatory Consequence Disclosures |
| :--- | :--- |
| **Budgets & Bidding** (`CampaignBudget`, `BiddingStrategy`, `cpc_bid_micros`, bid modifiers, seasonality/data exclusions) | • Exact currency delta (`$X.XX/day` $\rightarrow$ `$Y.YY/day`, `+/-Z%`).<br>• Maximum monthly spend exposure (`daily_budget * 30.4`).<br>• Smart Bidding impact: warn if changing budget/targets by $>20\%$ may trigger learning phase fluctuations. |
| **Account Billing, Reservations, Credits & Value Restatements** (`BillingSetup`, `AccountBudgetProposal`, `ReservationService.book_campaigns`, `IncentiveService.apply_incentive`, `LocalServicesLeadService.provide_lead_feedback`, `ConversionValueRule`, `ConversionAdjustmentUploadService`, `CustomerService.create_customer_client`, `ExperimentService.graduate_experiment` / `promote_experiment`, `CampaignDraftService.promote_campaign_draft`) | • **Mandatory monetary/financial disclosure** (enforced by `run_mutation.py` and `PreToolUse` hook): explicitly state payment account linkage, account spending limit in local currency, guaranteed-spend booking commitment, promotional credit/incentive amount, LSA lead credit request, or restated conversion value / Target ROAS revenue impact. |
| **Status Changes** (`PAUSED` $\leftrightarrow$ `ENABLED`) | • Count of child entities affected (e.g., *"Pausing this campaign immediately halts ad serving for N active Ad Groups and M active Ads"*).<br>• Immediate spend/traffic resumption warning when changing `PAUSED` $\rightarrow$ `ENABLED`. |
| **Deletion / `remove` Operations** (`remove` / `REMOVE` / `REMOVED`) | • **PROHIBITED (HARD BLOCKED):** Deletion (`remove` / `remove_all` operations, `remove_*` RPCs, or setting `status = REMOVED`) is strictly prohibited; only `create` and `update` mutations are allowed. Recommend updating `status = PAUSED` instead. |
| **Targeting & Exclusions** (`CampaignCriterion`, `AssetGroupListingGroupFilter`) | • Traffic expansion vs. restriction impact (e.g., adding or updating a negative keyword or webpage filter restricts or expands budget exposure across queries/URLs).<br>• For `AssetGroupListingGroupFilter`, verify atomic listing tree completeness (root `SUBDIVISION` + sibling `"Everything else"` node). |
| **Conversions & Goals** (`ConversionAction`, `CampaignConversionGoal`) | • Automated bidding impact: warn that changing primary conversion goals alters `MaximizeConversions` / `TargetCPA` / `TargetROAS` optimization signals across campaigns. |

---

## Step 3: Mandatory `validate_only=True` Dry-Run & Signed Receipt

1. Generate the mutation script in `saved/code/<mutation_name>.py` following the standard template below (supporting `--dry-run` with `validate_only=True` by default, and `--execute` with `validate_only=False` and `response_content_type = ResponseContentType.MUTABLE_RESOURCE`).
   - **Non-`validate_only` Financial RPCs** (`BillingSetupService.mutate_billing_setup`, `ReservationService.book_campaigns`, `IncentiveService.apply_incentive`, `LocalServicesLeadService.provide_lead_feedback`): Because these request messages have no `validate_only` field, `--dry-run` deterministically blocks any attempt to invoke the write RPC directly. During `--dry-run`, execute read-only preflight validation (`ReservationService.quote_campaigns`, `IncentiveService.fetch_incentive`, `PaymentsAccountService.list_payments_accounts`, or GAQL `search_stream`) and guard the live write call behind `if not validate_only:`.
2. Lint the generated script with `ruff check --fix saved/code/<mutation_name>.py`.
3. Execute the dry-run via `run_mutation.py` to validate against the Google Ads API and generate the signed verification receipt (`saved/data/last_dry_run.json`):
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-$HOME/.gemini/config/plugins/google-ads-api-developer-assistant}}/skills/execute-mutation/scripts/run_mutation.py" \
     --script saved/code/<mutation_name>.py \
     --dry-run \
     --customer-id "<customer_id>" \
     --operation "<Service.Method on Resource>" \
     --before "<Current State Summary>" \
     --after "<Proposed State Summary>" \
     --consequences "<Consequence 1>; <Consequence 2>" \
     --reversibility "<REVERSIBLE|IRREVERSIBLE>"
   ```

---

## Step 4: User Verification Prompt & Hook-Gated Execution

1. After `--dry-run` succeeds, present the **Mutation & Consequence Verification Card** output to the user and ask for explicit confirmation (`ask_question` in `agy` or an explicit confirmation prompt in `Claude Code CLI`).
2. **Wait for the user's response.** Do NOT invoke `--execute` in the same turn as `--dry-run`.
3. Verify that `config/assistant_config` contains `execute_mutates = true` (or update it via `python3 "${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-$HOME/.gemini/config/plugins/google-ads-api-developer-assistant}}/config/config_init.py" --execute-mutates true` if the user explicitly requests enabling mutations). Once confirmed by the user, execute the live mutation:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-$HOME/.gemini/config/plugins/google-ads-api-developer-assistant}}/skills/execute-mutation/scripts/run_mutation.py" \
     --script saved/code/<mutation_name>.py \
     --execute
   ```
   The `PreToolUse` lifecycle hook (`config/config_init.py`) will verify `execute_mutates = true` in `config/assistant_config` and the cryptographic dry-run receipt in `saved/data/last_dry_run.json`, record `hook_prompted_at_iso` and CLI session metadata (`conversationId` / `session_id`, `transcriptPath`), and trigger a native CLI confirmation prompt (`"decision": "force_ask"`) displaying the consequence summary before the API call executes.
4. **Automatic Mutation Audit Trail (`saved/logs/mutation_audit.jsonl`)**: Both `--dry-run` and `--execute` phases automatically intercept `GoogleAdsClient` mutation RPCs, verify canonical request SHA-256 digests before sending any live RPC, and append a structured JSONL audit record (`0600` permissions) containing:
   - `actor`: OS user, hostname, `login_customer_id`, `target_customer_id`, auth type, and CLI session/transcript identifiers.
   - `request`: `sent_at_iso`, `validate_only`, script path/SHA-256, canonical `request_sha256` / `request_sha256_verified`, and serialized Protobuf `Mutate*Request` payload(s).
   - `approval`: `dry_run_validated_at_iso`, `hook_prompted_at_iso`, `user_approved_at_iso`, and disclosed before/after state and consequences.
   - `response`: `received_at_iso`, `duration_ms`, `google_ads_request_ids`, and serialized Protobuf `Mutate*Response` (or `GoogleAdsFailure`) payload(s).

---

## Required Mutation Script Pattern (`saved/code/*.py`)

All mutation scripts generated in `saved/code/` MUST accept `--dry-run` (default) and `--execute` flags:

```python
"""Template for HITL-verified Google Ads API mutations."""

import argparse
import sys
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException


def run_mutation(client: GoogleAdsClient, customer_id: str, validate_only: bool = True) -> None:
    """Executes the Google Ads mutation with validate_only control."""
    service = client.get_service("CampaignBudgetService")
    operation = client.get_type("CampaignBudgetOperation")
    # Populate operation.update or operation.create (note: operation.remove is prohibited) and update_mask
    request = client.get_type("MutateCampaignBudgetsRequest")
    request.customer_id = customer_id
    request.operations = [operation]
    request.validate_only = validate_only
    if not validate_only:
        request.response_content_type = (
            client.enums.ResponseContentTypeEnum.ResponseContentType.MUTABLE_RESOURCE
        )

    try:
        response = service.mutate_campaign_budgets(request=request)
        if validate_only:
            print("validate_only=True dry-run succeeded: zero API or policy errors.")
        else:
            for result in response.results:
                print(f"Mutated resource: {result.resource_name}")
    except GoogleAdsException as ex:
        for error in ex.failure.errors:
            print(f"Error: {error.message}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--customer-id", required=True)
    parser.add_argument("--api-version", default="v25")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--execute", action="store_true", help="Run live (validate_only=False)")
    args = parser.parse_args()

    is_dry_run = not args.execute
    ads_client = GoogleAdsClient.load_from_storage(
        path="config/google-ads.yaml", version=args.api_version
    )
    run_mutation(ads_client, args.customer_id, validate_only=is_dry_run)
```

---

## Built-In Resource Creation Scripts (`skills/execute-mutation/scripts/`)

The skill includes ready-to-use, HITL-compliant creation scripts supporting `--dry-run` (`validate_only=True`, default), `--execute` (`validate_only=False`), and `--json`:

1. **Create Account under MCC (`create_account.py`)** — `CustomerService.create_customer_client`
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-$HOME/.gemini/config/plugins/google-ads-api-developer-assistant}}/skills/execute-mutation/scripts/create_account.py" \
     --manager-customer-id "<mcc_customer_id>" \
     --descriptive-name "<account_name>" \
     --currency-code "USD" \
     --time-zone "America/New_York" \
     --dry-run
   ```
2. **Create Campaign (`create_campaign.py`)** — `CampaignBudgetService.mutate_campaign_budgets` + `CampaignService.mutate_campaigns`
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-$HOME/.gemini/config/plugins/google-ads-api-developer-assistant}}/skills/execute-mutation/scripts/create_campaign.py" \
     --customer-id "<customer_id>" \
     --campaign-name "<campaign_name>" \
     --budget-amount-micros 5000000 \
     --channel-type "SEARCH" \
     --status "PAUSED" \
     --dry-run
   ```
3. **Create Ad Group (`create_ad_group.py`)** — `AdGroupService.mutate_ad_groups`
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-$HOME/.gemini/config/plugins/google-ads-api-developer-assistant}}/skills/execute-mutation/scripts/create_ad_group.py" \
     --customer-id "<customer_id>" \
     --campaign-id "<campaign_id>" \
     --ad-group-name "<ad_group_name>" \
     --cpc-bid-micros 1000000 \
     --status "ENABLED" \
     --dry-run
   ```
4. **Create Responsive Search Ad (`create_ad.py`)** — `AdGroupAdService.mutate_ad_group_ads`
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-$HOME/.gemini/config/plugins/google-ads-api-developer-assistant}}/skills/execute-mutation/scripts/create_ad.py" \
     --customer-id "<customer_id>" \
     --ad-group-id "<ad_group_id>" \
     --final-url "https://www.example.com" \
     --headline "Headline 1" --headline "Headline 2" --headline "Headline 3" \
     --description "Description 1" --description "Description 2" \
     --status "PAUSED" \
     --dry-run
   ```


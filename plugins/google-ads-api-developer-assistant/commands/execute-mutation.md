---
description: Executes Google Ads API write/mutation operations using the mandatory 4-Step HITL Verification & Consequence Disclosure Protocol.
argument-description: <mutation_request> The mutation operation or script to validate and execute
---

# Execute Mutation (`/execute-mutation`)

Executes Google Ads API write/mutation operations (`create` and `update` only; deletion/`remove` operations are strictly prohibited) using the mandatory 4-Step Human-in-the-Loop (HITL) Verification & Consequence Disclosure Protocol.

> **Hard Policy — Only `create` and `update` Mutations Allowed (Deletion Prohibited):**
> Only **`create`** and **`update`** operations are permitted. Deletion (`remove` / `remove_all` operations, `remove_*` RPC calls, or setting `status = REMOVED`) is strictly prohibited across all layers. To stop delivery without deleting a resource, update its `status` to `PAUSED`.

## Instructions:
1. **Step 1 — Pre-Mutation State & Blast Radius Lookup**:
   - Query the target resource(s) via `GoogleAdsService.search_stream` to capture the **Before State** (resource names, current `status`, and financial/bidding settings converted from micros to currency).
   - Query downstream blast radius (active child entities, 7- to 30-day spend/conversions, or shared resource links).

2. **Step 2 — Mandatory `validate_only=True` Dry-Run & Signed Receipt**:
   - Generate and lint the mutation script in `saved/code/<mutation_name>.py` supporting `--dry-run` (`validate_only=True`) and `--execute` (`validate_only=False` with `ResponseContentType.MUTABLE_RESOURCE`).
   - Run the dry-run via `run_mutation.py` to generate the SHA-256 verification receipt (`saved/data/last_dry_run.json`):
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

3. **Step 3 — Consequence Disclosure & User Confirmation**:
   - Present the **Mutation & Consequence Verification Card** to the user and wait for explicit confirmation in a separate turn before invoking `--execute`.

4. **Step 4 — Hook-Gated Live Execution & Audit Trail**:
   - Ensure `execute_mutates = true` in `config/assistant_config`.
   - Execute the verified mutation:
     ```bash
     python3 "${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-$HOME/.gemini/config/plugins/google-ads-api-developer-assistant}}/skills/execute-mutation/scripts/run_mutation.py" \
       --script saved/code/<mutation_name>.py \
       --execute
     ```

## Built-In Creation Scripts (`skills/execute-mutation/scripts/`):
- `create_account.py`: Creates a client customer account under an MCC via `CustomerService.create_customer_client`.
- `create_campaign.py`: Creates a campaign (and optional `CampaignBudget`) via `CampaignService.mutate_campaigns`.
- `create_ad_group.py`: Creates an ad group under a campaign via `AdGroupService.mutate_ad_groups`.
- `create_ad.py`: Creates a Responsive Search Ad under an ad group via `AdGroupAdService.mutate_ad_group_ads`.


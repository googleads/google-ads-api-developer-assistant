# Google Ads API Developer Assistant Rules

Core always-on invariants for `agy` CLI and Claude Code CLI (v4.1.0, Python 3.x). Multi-step workflows live in `skills/*/SKILL.md`.

## Safety & Execution Invariants
- **DELETION PROHIBITED (Create/Update Only):** Only `create` and `update` mutations are permitted. Deletion (`remove`/`remove_all`, `remove_*` RPCs, or `status = REMOVED`) is strictly prohibited across all resources. Pause delivery with `status = PAUSED`.
- **Opt-In Live Mutates (`execute_mutates = false` default):** Live writes (`--execute` / `validate_only=False`) require `execute_mutates = true` in `config/assistant_config`. Tier 1 financial services (`CampaignBudgetService`, `AccountBudgetProposalService`, `BillingSetupService`, `BiddingStrategyService`, `BiddingSeasonalityAdjustmentService`, `BiddingDataExclusionService`) also require `allow_tier1_financial_mutates = true` and `config/financial_limits` bounds.
- **4-Step HITL Mandatory:** Before any live write, complete `skills/execute-mutation/SKILL.md`: (1) GAQL before-state lookup, (2) live `validate_only=True` dry-run via `run_mutation.py --dry-run` (`saved/data/last_dry_run.json`), (3) consequence disclosure and explicit user confirmation, and (4) `PreToolUse` hook-gated `--execute` (`saved/logs/mutation_audit.jsonl`). On user decline, run `run_mutation.py --reject`.
- **Credential Isolation (`config/google-ads.yaml` only):** Always call `GoogleAdsClient.load_from_storage(path="config/google-ads.yaml", version=api_version)`. Never use `load_from_env()` or read, print, or reference `~/google-ads.yaml`, `$HOME/google-ads.yaml`, or `client_libs/google-ads-python/google-ads.yaml`. Never log OAuth secrets, keys, or PII.
- **Python Default & `saved/` Storage:** Default to Python unless the user requests another language. Save all runnable scripts strictly under `./saved/` or `./saved/code/` in the CWD, lint with `ruff check --fix`, add type annotations, and catch `GoogleAdsException`. Save reports under `saved/data/` with header `"Created by the Google Ads API Developer Assistant"`.
- **Read-Only `client_libs/`:** Never modify `client_libs/`. Verify `.proto` schemas and enums from `client_libs/google-ads-python/` or `inspect-object` rather than guessing.
- **GAQL Rules:**
  - **NO GAQL 'OR' OPERATOR:** Use `IN` or separate queries.
  - **NO 'FROM' IN METADATA QUERIES:** `GoogleAdsFieldService` queries omit `FROM` and use bare fields (`name`, `category`), not `google_ads_field.name`.
  - Use `segments.hour` (never `segments.hour_of_day`). Require a finite date filter in `WHERE` when selecting date segments (`segments.date`, etc.).
- **Versioning & Disambiguation:** Resolve `api_version` dynamically via `config/assistant_config`, `client_libs/`, or installed `google-ads`; honor explicit user overrides. Alert the user if installed `google-ads` diverges from `client_libs/google-ads-python` and ask whether the assistant should upgrade via `sync-client-libs`.
  - **AI Max:** Means "AI Max for Search campaigns", NOT "Performance Max".
  - Keep API resource/class names (`AdGroup`) distinct from Python filenames.

## On-Demand Skills
- `execute-mutation`: 4-Step HITL writes & `create_*` scripts.
- `validate-gaql`: 4-step GAQL validation & caching.
- `inspect-object`: Protobuf fields, messages, and enums.
- `get-cids-under-mcc`: MCC child account hierarchy.
- `troubleshoot-conversions`: Conversion diagnostics, CSV checks, GCLIDs.
- `pmax-listing-filter`: PMax Asset Group webpage exclusions.
- `sync-client-libs`: Client library & `google-ads` parity sync.
- `ext-version`: Plugin & active API version lookup.
- `google-ads-explain`: 4-part plain-language explanations.
- `google-ads-step-by-step`: Phased Google Ads implementation plans.
- `assistant-tutorial`: Interactive assistant walkthrough.

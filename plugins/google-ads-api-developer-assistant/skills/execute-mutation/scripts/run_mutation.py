#!/usr/bin/env python3
"""Executes Google Ads API mutations with a 2-phase Dry-Run Receipt, Consequence Gate & Audit Log."""

import argparse
from datetime import datetime, timezone
import functools
import getpass
import hashlib
import json
import os
import re
import runpy
import shlex
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid


RECEIPT_FILENAME = "last_dry_run.json"
AUDIT_LOG_FILENAME = "mutation_audit.jsonl"
ASSISTANT_CONFIG_FILENAME = "assistant_config"
EXECUTE_MUTATES_FILENAME = ASSISTANT_CONFIG_FILENAME
FINANCIAL_LIMITS_FILENAME = "financial_limits"
DEFAULT_MAX_RECEIPT_AGE_SECONDS = 1800  # 30 minutes
_TRACE_ENV_VAR = "_GOOGLE_ADS_MUTATION_TRACE_FILE"
_EXPECTED_HASHES_ENV_VAR = "_GOOGLE_ADS_EXPECTED_REQUEST_SHA256"
_ENFORCE_HASH_ENV_VAR = "_GOOGLE_ADS_ENFORCE_REQUEST_SHA256"
_DRY_RUN_MODE_ENV_VAR = "_GOOGLE_ADS_DRY_RUN_MODE"

_MUTATION_METHOD_PREFIXES = (
    "mutate",
    "remove_",
    "delete_",
    "apply_recommendation",
    "dismiss_recommendation",
    "upload_click_conversions",
    "upload_call_conversions",
    "upload_conversion_adjustments",
    "upload_user_data",
    "add_batch_job_operations",
    "run_batch_job",
    "book_campaigns",
    "apply_incentive",
    "provide_lead_feedback",
    "create_customer_client",
    "promote_campaign_draft",
    "graduate_experiment",
    "promote_experiment",
    "schedule_experiment",
    "end_experiment",
)

# Google Ads API write RPCs whose request messages have NO `validate_only` field.
# These methods execute live changes immediately if invoked and must never be sent
# during `--dry-run` or allowed to bypass HITL checks via `validate_only=True`.
_NON_VALIDATE_ONLY_MUTATION_METHODS = frozenset({
    "mutate_billing_setup",
    "book_campaigns",
    "apply_incentive",
    "provide_lead_feedback",
    "apply_recommendation",
    "dismiss_recommendation",
    "mutate_batch_job",
    "add_batch_job_operations",
    "run_batch_job",
    "mutate_customer_user_access",
    "mutate_customer_user_access_invitation",
    "upload_user_data",
})

_FINANCIAL_SERVICES = frozenset({
    "billingsetupservice",
    "accountbudgetproposalservice",
    "campaignbudgetservice",
    "biddingstrategyservice",
    "biddingseasonalityadjustmentservice",
    "biddingdataexclusionservice",
    "campaignbidmodifierservice",
    "adgroupbidmodifierservice",
    "conversionvalueruleservice",
    "conversionvaluerulesetservice",
    "conversionadjustmentuploadservice",
    "reservationservice",
    "incentiveservice",
    "localservicesleadservice",
    "goalservice",
    "campaigngoalconfigservice",
    "customerlifecyclegoalservice",
    "campaignlifecyclegoalservice",
})

_FINANCIAL_METHODS = frozenset({
    "mutate_billing_setup",
    "mutate_account_budget_proposal",
    "mutate_campaign_budgets",
    "mutate_bidding_strategies",
    "mutate_bidding_seasonality_adjustments",
    "mutate_bidding_data_exclusions",
    "mutate_campaign_bid_modifiers",
    "mutate_ad_group_bid_modifiers",
    "mutate_conversion_value_rules",
    "mutate_conversion_value_rule_sets",
    "upload_conversion_adjustments",
    "book_campaigns",
    "apply_incentive",
    "provide_lead_feedback",
    "create_customer_client",
    "graduate_experiment",
    "promote_experiment",
    "schedule_experiment",
    "promote_campaign_draft",
    "mutate_goals",
    "mutate_campaign_goal_configs",
    "mutate_customer_lifecycle_goals",
    "mutate_campaign_lifecycle_goals",
})

_FINANCIAL_PAYLOAD_KEYS = frozenset({
    "amount_micros",
    "total_amount_micros",
    "recommended_budget_amount_micros",
    "new_budget_amount_micros",
    "new_campaign_budget_amount_micros",
    "budget_micros_to_move",
    "budget_amount_micros",
    "campaign_budget_amount_micros",
    "spending_limit_micros",
    "proposed_spending_limit_micros",
    "approved_spending_limit_micros",
    "campaign_budget",
    "campaign_budget_operation",
    "account_budget_proposal",
    "billing_setup",
    "payments_account",
    "payments_account_info",
    "purchase_order_number",
    "cpc_bid_micros",
    "cpm_bid_micros",
    "cpv_bid_micros",
    "target_cpa_micros",
    "target_cpm_micros",
    "target_roas",
    "cpc_bid_ceiling_micros",
    "cpc_bid_floor_micros",
    "percent_cpc_bid_micros",
    "commission_rate_micros",
    "fixed_cpm_micros",
    "target_spend_micros",
    "bid_modifier",
    "target_cpa_multiplier",
    "target_roas_multiplier",
    "target_multiplier",
    "value_multiplier",
    "high_lifetime_value_multiplier",
    "bidding_strategy",
    "bidding_strategy_operation",
    "campaign_bid_modifier_operation",
    "ad_group_bid_modifier_operation",
    "bidding_seasonality_adjustment_operation",
    "bidding_data_exclusion_operation",
    "seasonality_modifier",
    "manual_cpc",
    "manual_cpm",
    "manual_cpv",
    "maximize_conversions",
    "maximize_conversion_value",
    "target_cpa",
    "target_impression_share",
    "target_spend",
    "conversion_value",
    "unit_price",
    "local_transaction_cost",
    "adjusted_value",
    "restatement_value",
    "default_value",
    "additional_value",
    "additional_high_lifetime_value",
    "transaction_amount_micros",
    "lifetime_value_micros",
    "average_purchase_value_micros",
    "money_amount_off",
    "orders_over_amount",
    "conversion_value_rule_operation",
    "conversion_value_rule_set_operation",
    "selected_incentive_id",
    "credit_issuance_decision",
    "report_charged_lead",
})

_FINANCIAL_SUMMARY_RE = re.compile(
    r"(?i)(?:"
    r"billing[_\s]*setup|payments[_\s]*account|account[_\s]*budget|"
    r"campaign[_\s]*budget|\bbudget(?:s|ing)?\b|"
    r"bidding[_\s]*(?:strategy|strategies|seasonality|data[_\s]*exclusion)|"
    r"bid[_\s]*modifier|\b(?:cpc|cpm|cpv|cpa)[_\s]*bid|target[_\s]*(?:cpa|roas|cpm|spend)|"
    r"maximize[_\s]*conversion[_\s]*value|"
    r"book[_\s]*campaigns|\breservation(?:s|service)?\b|"
    r"apply[_\s]*incentive|\bincentive(?:s|service)?\b|"
    r"provide[_\s]*lead[_\s]*feedback|lead[_\s]*credit|"
    r"conversion[_\s]*value[_\s]*rule|upload[_\s]*conversion[_\s]*adjustments|"
    r"restatement[_\s]*value|adjusted[_\s]*value|"
    r"create[_\s]*customer[_\s]*client|"
    r"(?:graduate|promote|schedule)[_\s]*experiment|promote[_\s]*campaign[_\s]*draft|"
    r"(?:amount|bid|cpa|cpm|cpv|spend|spending_limit)[_\s]*micros|\bmicros\b|"
    r"[$€£¥₹]\s*\d|\b(?:USD|EUR|GBP|JPY|CAD|AUD|CHF|INR|BRL|MXN)\s*\d"
    r")"
)

_FINANCIAL_CONSEQUENCE_RE = re.compile(
    r"(?i)(?:"
    r"[$€£¥₹]\s*\d|"
    r"\b\d+(?:[.,]\d+)?\s*(?:%|percent|micros|/(?:day|mo|month|wk|week|yr|year))\b|"
    r"\b(?:USD|EUR|GBP|JPY|CAD|AUD|CHF|INR|BRL|MXN)\b|"
    r"\b(?:spend|spending|budget|budgets|billing|billable|billed|payment|payments|"
    r"invoice|invoices|charge|charges|charged|cost|costs|monetary|financial|currency|"
    r"price|pricing|fee|fees|credit|credits|credited|refund|incentive|coupon|voucher|"
    r"promotional|booking|booked|guaranteed|reservation|commitment|"
    r"bid|bids|bidding|cpc|cpm|cpv|cpa|roas|modifier|"
    r"conversion\s+value|restatement|retraction|revenue)\b"
    r")"
)

_SENSITIVE_KEYS = frozenset({
    "client_secret",
    "refresh_token",
    "private_key",
    "json_key",
})


def _payload_contains_financial_fields(obj: Any, _depth: int = 0) -> bool:
    """Recursively checks whether a serialized RPC payload contains financial fields."""
    if _depth > 12:
        return False
    if isinstance(obj, dict):
        for k, v in obj.items():
            key_lower = str(k).strip().lower()
            if key_lower in _FINANCIAL_PAYLOAD_KEYS and v not in (None, "", [], {}):
                return True
            if _payload_contains_financial_fields(v, _depth + 1):
                return True
    elif isinstance(obj, list):
        for item in obj:
            if _payload_contains_financial_fields(item, _depth + 1):
                return True
    return False


def is_financial_mutation(
    operation_summary: str = "",
    before_state: str = "",
    after_state: str = "",
    rpc_calls: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """Determines whether a Google Ads API mutation involves a financial transaction.

    Checks intercepted RPC services, methods, and request payload fields as well as
    the operation summary and before/after state descriptions.
    """
    for call in rpc_calls or []:
        if not isinstance(call, dict):
            continue
        svc = str(call.get("service", "")).strip().lower()
        method = str(call.get("method", "")).strip().lower()
        if svc in _FINANCIAL_SERVICES or method in _FINANCIAL_METHODS:
            return True
        if _payload_contains_financial_fields(call.get("request_payload")):
            return True

    combined_text = " | ".join(
        part.strip()
        for part in (operation_summary, before_state, after_state)
        if part and str(part).strip()
    )
    if combined_text and _FINANCIAL_SUMMARY_RE.search(combined_text):
        return True
    return False


def has_financial_consequence_disclosure(consequences: List[str]) -> bool:
    """Returns True if at least one consequence explicitly discloses financial/monetary impact."""
    for item in consequences or []:
        text = str(item).strip()
        if text and _FINANCIAL_CONSEQUENCE_RE.search(text):
            return True
    return False


def compute_file_sha256(file_path: str) -> str:
    """Computes the SHA-256 hex digest of a file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _normalize_request_for_hash(obj: Any) -> Any:
    """Normalizes a serialized RPC request payload by recursively stripping validate_only."""
    if isinstance(obj, dict):
        return {
            str(k): _normalize_request_for_hash(v)
            for k, v in sorted(obj.items(), key=lambda item: str(item[0]))
            if str(k) != "validate_only"
        }
    if isinstance(obj, list):
        return [_normalize_request_for_hash(item) for item in obj]
    return obj


def compute_mutate_request_sha256(
    service_name: str,
    method_name: str,
    req_payload: Any,
) -> str:
    """Computes a canonical SHA-256 hex digest of a Google Ads mutate request payload.

    Normalizes out `validate_only` so that the `validate_only=True` dry-run request
    and the `validate_only=False` live request produce the exact same SHA-256 digest
    if and only if the target service, method, customer_id, and operations are identical.
    """
    serialized = _serialize_rpc_object(req_payload)
    normalized = _normalize_request_for_hash(serialized)
    canonical_envelope = {
        "service": str(service_name).strip(),
        "method": str(method_name).strip(),
        "request": normalized,
    }
    canonical_json = json.dumps(
        canonical_envelope,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def compute_aggregate_request_sha256(
    request_hashes: List[str],
    fallback_payload: Optional[Dict[str, Any]] = None,
) -> str:
    """Computes an aggregate SHA-256 digest across one or more mutate requests."""
    clean_hashes = [str(h).strip() for h in request_hashes if str(h).strip()]
    if len(clean_hashes) == 1:
        return clean_hashes[0]
    if len(clean_hashes) > 1:
        canonical_list = json.dumps(clean_hashes, separators=(",", ":"))
        return hashlib.sha256(canonical_list.encode("utf-8")).hexdigest()
    if fallback_payload is not None:
        return compute_mutate_request_sha256(
            "ScriptExecution", "mutate", fallback_payload
        )
    return ""


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


def get_audit_log_paths() -> List[str]:
    """Returns candidate paths for appending to the mutation audit trail (mutation_audit.jsonl)."""
    env_override = os.environ.get("GOOGLE_ADS_MUTATION_AUDIT_LOG", "").strip()
    if env_override:
        return [os.path.abspath(env_override)]

    this_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_root = os.path.abspath(os.path.join(this_dir, "../../.."))
    paths = [
        os.path.abspath(os.path.join("saved", "logs", AUDIT_LOG_FILENAME)),
        os.path.join(plugin_root, "saved", "logs", AUDIT_LOG_FILENAME),
        os.path.expanduser(
            f"~/.gemini/config/plugins/google-ads-api-developer-assistant/saved/logs/{AUDIT_LOG_FILENAME}"
        ),
    ]
    deduped: List[str] = []
    for p in paths:
        norm = os.path.normpath(p)
        if norm not in deduped:
            deduped.append(norm)
    return deduped


def parse_execute_mutates_value(raw_text: str) -> Optional[bool]:
    """Parses 'execute_mutates = <true, false>' from TOML or key=value text and returns a boolean."""
    try:
        import tomllib  # type: ignore

        parsed_toml = tomllib.loads(raw_text)
        if isinstance(parsed_toml, dict) and "execute_mutates" in parsed_toml:
            em_val = parsed_toml["execute_mutates"]
            if isinstance(em_val, bool):
                return em_val
            if isinstance(em_val, str) and em_val.strip().lower() in ("true", "false"):
                return em_val.strip().lower() == "true"
    except Exception:
        pass

    for raw_line in raw_text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.match(
            r"^execute_mutates\s*[=:]\s*['\"]?(true|false)['\"]?\s*$",
            line,
            re.IGNORECASE,
        )
        if match:
            return match.group(1).lower() == "true"
        bare = line.strip("'\"").lower()
        if bare in ("true", "false"):
            return bare == "true"
    return None


def get_execute_mutates_paths() -> List[str]:
    """Returns candidate paths for reading the execute_mutates setting in config/assistant_config."""
    this_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_root = os.path.abspath(os.path.join(this_dir, "../../.."))
    repo_root = os.path.abspath(os.path.join(plugin_root, "../.."))
    paths = [
        os.path.abspath(os.path.join("config", ASSISTANT_CONFIG_FILENAME)),
        os.path.join(plugin_root, "config", ASSISTANT_CONFIG_FILENAME),
        os.path.join(repo_root, "config", ASSISTANT_CONFIG_FILENAME),
        os.path.expanduser(
            f"~/.gemini/config/plugins/google-ads-api-developer-assistant/config/{ASSISTANT_CONFIG_FILENAME}"
        ),
    ]
    deduped: List[str] = []
    for p in paths:
        norm = os.path.normpath(p)
        if norm not in deduped:
            deduped.append(norm)
    return deduped


def is_execute_mutates_enabled() -> bool:
    """Returns whether the plugin is configured to support mutations (defaults to False)."""
    env_override = os.environ.get("GOOGLE_ADS_EXECUTE_MUTATES", "").strip()
    if env_override:
        parsed_env = parse_execute_mutates_value(env_override)
        if parsed_env is not None:
            return parsed_env
        return False

    for candidate in get_execute_mutates_paths():
        if os.path.isfile(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    parsed = parse_execute_mutates_value(f.read())
                if parsed is not None:
                    return parsed
                return False
            except OSError:
                continue

    return False


def _load_set_financial_limits_module():
    from importlib.util import module_from_spec, spec_from_file_location

    this_dir = os.path.dirname(os.path.abspath(__file__))
    sfl_path = os.path.join(this_dir, "set_financial_limits.py")
    spec = spec_from_file_location("_set_financial_limits_mod", sfl_path)
    if spec and spec.loader:
        mod = module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    raise RuntimeError(f"Unable to load {sfl_path}")


_SFL_MOD = _load_set_financial_limits_module()
FINANCIAL_LIMIT_SPECS: Dict[str, Dict[str, Any]] = _SFL_MOD.FINANCIAL_LIMIT_SPECS
LIMIT_KEY_ALIASES: Dict[str, str] = _SFL_MOD.LIMIT_KEY_ALIASES
resolve_limit_key = _SFL_MOD.resolve_limit_key
resolve_limit_keys = _SFL_MOD.resolve_limit_keys
flatten_toml_limits = _SFL_MOD.flatten_toml_limits

_FINANCIAL_LIMIT_META: Dict[str, Tuple[str, str]] = {
    k: (spec["api_format"], spec["monetary_unit"])
    for k, spec in FINANCIAL_LIMIT_SPECS.items()
}

_API_FIELD_TO_LIMIT_KEY: Dict[str, str] = dict(LIMIT_KEY_ALIASES)

# Map lowercase service names and RPC method names to canonical PascalCase Service names
_SERVICE_NAME_LOOKUP: Dict[str, str] = {}
_METHOD_TO_SERVICE_LOOKUP: Dict[str, str] = {
    "mutate_ad_group_bid_modifiers": "AdGroupBidModifierService",
    "mutate_ad_group_criteria": "AdGroupCriterionService",
    "mutate_ad_groups": "AdGroupService",
    "mutate_assets": "AssetService",
    "add_batch_job_operations": "BatchJobService",
    "mutate_bidding_seasonality_adjustments": "BiddingSeasonalityAdjustmentService",
    "mutate_bidding_strategies": "BiddingStrategyService",
    "mutate_campaign_bid_modifiers": "CampaignBidModifierService",
    "mutate_campaign_budgets": "CampaignBudgetService",
    "mutate_campaign_criteria": "CampaignCriterionService",
    "mutate_campaign_goal_configs": "CampaignGoalConfigService",
    "mutate_campaigns": "CampaignService",
    "mutate_conversion_actions": "ConversionActionService",
    "upload_conversion_adjustments": "ConversionAdjustmentUploadService",
    "upload_click_conversions": "ConversionUploadService",
    "upload_call_conversions": "ConversionUploadService",
    "mutate_conversion_value_rules": "ConversionValueRuleService",
    "mutate_goals": "GoalService",
    "mutate": "GoogleAdsService",
    "mutate_keyword_plan_ad_group_keywords": "KeywordPlanAdGroupKeywordService",
    "mutate_keyword_plan_ad_groups": "KeywordPlanAdGroupService",
    "mutate_keyword_plan_campaigns": "KeywordPlanCampaignService",
    "add_offline_user_data_job_operations": "OfflineUserDataJobService",
    "apply_recommendation": "RecommendationService",
    "upload_user_data": "UserDataService",
}

for _spec_key, _spec_val in FINANCIAL_LIMIT_SPECS.items():
    _svc = _spec_val.get("service", "")
    if _svc and _svc != "ALL":
        _SERVICE_NAME_LOOKUP[_svc.lower()] = _svc

# Map nested operation/wrapper keys inside GoogleAdsService.mutate / BatchJobService
_PARENT_KEY_TO_SERVICE: Dict[str, str] = {
    "ad_group_bid_modifier_operation": "AdGroupBidModifierService",
    "ad_group_bid_modifier": "AdGroupBidModifierService",
    "ad_group_criterion_operation": "AdGroupCriterionService",
    "ad_group_criterion": "AdGroupCriterionService",
    "ad_group_operation": "AdGroupService",
    "ad_group": "AdGroupService",
    "asset_operation": "AssetService",
    "promotion_asset": "AssetService",
    "price_asset": "AssetService",
    "price_offering": "AssetService",
    "money_amount_off": "AssetService",
    "orders_over_amount": "AssetService",
    "price": "AssetService",
    "bidding_seasonality_adjustment_operation": "BiddingSeasonalityAdjustmentService",
    "bidding_seasonality_adjustment": "BiddingSeasonalityAdjustmentService",
    "bidding_strategy_operation": "BiddingStrategyService",
    "bidding_strategy": "BiddingStrategyService",
    "campaign_bid_modifier_operation": "CampaignBidModifierService",
    "campaign_bid_modifier": "CampaignBidModifierService",
    "campaign_budget_operation": "CampaignBudgetService",
    "campaign_budget": "CampaignBudgetService",
    "campaign_criterion_operation": "CampaignCriterionService",
    "campaign_criterion": "CampaignCriterionService",
    "campaign_goal_config_operation": "CampaignGoalConfigService",
    "campaign_goal_config": "CampaignGoalConfigService",
    "campaign_operation": "CampaignService",
    "campaign": "CampaignService",
    "commission": "CampaignService",
    "conversion_action_operation": "ConversionActionService",
    "conversion_action": "ConversionActionService",
    "value_settings": "ConversionActionService",
    "conversion_value_rule_operation": "ConversionValueRuleService",
    "conversion_value_rule": "ConversionValueRuleService",
    "goal_operation": "GoalService",
    "goal": "GoalService",
    "keyword_plan_ad_group_keyword_operation": "KeywordPlanAdGroupKeywordService",
    "keyword_plan_ad_group_operation": "KeywordPlanAdGroupService",
    "keyword_plan_campaign_operation": "KeywordPlanCampaignService",
}

_ALL_TRACKED_FIELD_NAMES = set(_SFL_MOD._FIELD_UNIT_META.keys()) | set(
    LIMIT_KEY_ALIASES.keys()
)

_CODE_FINANCIAL_ASSIGN_RE = re.compile(
    r"\b("
    + "|".join(re.escape(k) for k in sorted(_ALL_TRACKED_FIELD_NAMES, key=len, reverse=True))
    + r"|action\.value)\s*(?:=|:)\s*['\"]?([0-9]+(?:_[0-9]+)*(?:\.[0-9]+)?)['\"]?"
)
_TEXT_MICROS_VALUE_RE = re.compile(
    r"\b([0-9]{1,3}(?:[,_][0-9]{3})+|[0-9]{4,})\s*micros\b",
    re.IGNORECASE,
)


def get_financial_limits_paths() -> List[str]:
    """Returns candidate paths for reading config/financial_limits."""
    return _SFL_MOD.get_financial_limits_paths()


def parse_financial_limits(raw_text: str) -> Dict[str, Union[int, float]]:
    """Parses TOML (`Service.field = value` or `[Service]`) or key=value text from config/financial_limits."""
    return _SFL_MOD.parse_financial_limits(raw_text)


def read_financial_limits() -> Tuple[Dict[str, Union[int, float]], Optional[str]]:
    """Reads the highest-precedence config/financial_limits file and returns (limits, path)."""
    return _SFL_MOD.read_financial_limits()


def _coerce_numeric(val: Any) -> Optional[float]:
    """Converts an int, float, or numeric string to float, or returns None."""
    if isinstance(val, bool) or val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        s = val.strip().replace("_", "").replace(",", "")
        if re.match(r"^[0-9]+(?:\.[0-9]+)?$", s):
            try:
                return float(s)
            except ValueError:
                return None
    return None


def _resolve_canonical_service(
    service_name: str = "",
    method_name: str = "",
    context_text: str = "",
) -> str:
    """Resolves a service name, method name, or context text to a canonical Google Ads Service name."""
    svc_clean = service_name.strip().lower()
    if svc_clean in _SERVICE_NAME_LOOKUP:
        return _SERVICE_NAME_LOOKUP[svc_clean]

    m_clean = method_name.strip().lower()
    if m_clean in _METHOD_TO_SERVICE_LOOKUP:
        return _METHOD_TO_SERVICE_LOOKUP[m_clean]

    ctx_lower = context_text.lower()
    for s_low, s_canon in _SERVICE_NAME_LOOKUP.items():
        if s_low in ctx_lower:
            return s_canon
    for m_low, s_canon in _METHOD_TO_SERVICE_LOOKUP.items():
        if m_low != "mutate" and m_low in ctx_lower:
            return s_canon
    return ""


def _resolve_candidate_limit_keys(
    field_name: str,
    service_name: str = "",
    method_name: str = "",
    ancestor_keys: Tuple[str, ...] = (),
    context_text: str = "",
    limits: Optional[Dict[str, Union[int, float]]] = None,
) -> List[str]:
    """Returns ordered candidate `Service.field` limit keys for an observed field."""
    f_lower = field_name.strip().lower()
    if f_lower == "action.value":
        f_lower = "value"
    elif f_lower in ("click_conversion_value", "call_conversion_value"):
        f_lower = "conversion_value"

    candidates: List[str] = []
    canon_svc = _resolve_canonical_service(service_name, method_name, context_text)

    # Check ancestor payload keys for inner resource service disambiguation
    inferred_inner_svc = ""
    for anc in reversed(ancestor_keys):
        if anc in _PARENT_KEY_TO_SERVICE:
            inferred_inner_svc = _PARENT_KEY_TO_SERVICE[anc]
            break

    if canon_svc in ("GoogleAdsService", "BatchJobService") and inferred_inner_svc:
        inner_key = f"{inferred_inner_svc}.{f_lower}"
        outer_key = f"{canon_svc}.{f_lower}"
        valid_pair = [
            k for k in (inner_key, outer_key) if k in FINANCIAL_LIMIT_SPECS
        ]
        if len(valid_pair) == 2 and limits is not None:
            pos_keys = [
                k for k in valid_pair if float(limits.get(k, 0) or 0) > 0
            ]
            if pos_keys:
                return pos_keys
            return valid_pair
        if valid_pair:
            return valid_pair

    if canon_svc:
        direct_key = f"{canon_svc}.{f_lower}"
        if direct_key in FINANCIAL_LIMIT_SPECS:
            candidates.append(direct_key)

    if not candidates and inferred_inner_svc:
        inner_key = f"{inferred_inner_svc}.{f_lower}"
        if inner_key in FINANCIAL_LIMIT_SPECS:
            candidates.append(inner_key)

    if not candidates and f_lower in LIMIT_KEY_ALIASES:
        alias_key = LIMIT_KEY_ALIASES[f_lower]
        if alias_key in FINANCIAL_LIMIT_SPECS:
            candidates.append(alias_key)

    if not candidates and f_lower.endswith("_micros"):
        candidates.append("all_micros_transactions")

    return candidates


def _extract_payload_financial_amounts(
    obj: Any,
    service_name: str = "",
    method_name: str = "",
    parent_key: str = "",
    out: Optional[List[Tuple[str, str, float]]] = None,
    limits: Optional[Dict[str, Union[int, float]]] = None,
    _depth: int = 0,
    _ancestors: Tuple[str, ...] = (),
) -> List[Tuple[str, str, float]]:
    """Recursively extracts (limit_key, field_name, numeric_value) tuples from an RPC payload."""
    if out is None:
        out = []
    if _depth > 12:
        return out

    svc_lower = service_name.strip().lower()
    m_lower = method_name.strip().lower()

    if isinstance(obj, dict):
        for k, v in obj.items():
            k_lower = str(k).strip().lower()
            num_val = _coerce_numeric(v)
            if num_val is not None:
                if k_lower == "value" and not (
                    parent_key
                    in (
                        "action",
                        "conversion_value_rule",
                        "conversion_value_rule_operation",
                    )
                    or svc_lower == "conversionvalueruleservice"
                    or m_lower == "mutate_conversion_value_rules"
                ):
                    continue

                if k_lower in _ALL_TRACKED_FIELD_NAMES:
                    cand_keys = _resolve_candidate_limit_keys(
                        k_lower,
                        service_name=service_name,
                        method_name=method_name,
                        ancestor_keys=_ancestors + ((parent_key,) if parent_key else ()),
                        limits=limits,
                    )
                    display_field = (
                        "action.value" if k_lower == "value" else k_lower
                    )
                    for lk in cand_keys:
                        out.append((lk, display_field, num_val))
                elif k_lower.endswith("_micros"):
                    out.append(("all_micros_transactions", k_lower, num_val))
            else:
                _extract_payload_financial_amounts(
                    v,
                    service_name=service_name,
                    method_name=method_name,
                    parent_key=k_lower,
                    out=out,
                    limits=limits,
                    _depth=_depth + 1,
                    _ancestors=_ancestors + ((k_lower,) if k_lower else ()),
                )
    elif isinstance(obj, list):
        for item in obj:
            _extract_payload_financial_amounts(
                item,
                service_name=service_name,
                method_name=method_name,
                parent_key=parent_key,
                out=out,
                limits=limits,
                _depth=_depth + 1,
                _ancestors=_ancestors,
            )
    return out


def _infer_limit_key_from_context(context_text: str) -> str:
    """Infers the primary Service.field micros limit key from an operation summary or service name."""
    lower = context_text.lower()
    if "total_amount_micros" in lower:
        return "CampaignBudgetService.total_amount_micros"
    if (
        "money_amount_off" in lower
        or "orders_over_amount" in lower
        or "promotion_asset" in lower
        or "price_asset" in lower
        or "assetservice" in lower
    ):
        return "AssetService.amount_micros"
    if "commission_rate" in lower:
        return "CampaignService.commission_rate_micros"
    if "location_fraction" in lower:
        return "BiddingStrategyService.location_fraction_micros"
    if "percent_cpc" in lower:
        return "AdGroupService.percent_cpc_bid_micros"
    if (
        "transaction_amount_micros" in lower
        or "lifetime_value_micros" in lower
        or "average_purchase_value_micros" in lower
        or "userdataservice" in lower
        or "offlineuserdatajob" in lower
    ):
        return "UserDataService.transaction_amount_micros"
    if "bid_ceiling" in lower or "bid_floor" in lower:
        return "BiddingStrategyService.cpc_bid_ceiling_micros"
    if "target_cpa" in lower or "cpa_bid" in lower:
        return "BiddingStrategyService.target_cpa_micros"
    if "target_spend" in lower:
        return "BiddingStrategyService.target_spend_micros"
    if "cpm_bid" in lower or "target_cpm" in lower or "fixed_cpm" in lower:
        return "AdGroupService.cpm_bid_micros"
    if "cpv_bid" in lower or "target_cpv" in lower:
        return "AdGroupService.cpv_bid_micros"
    if "cpc_bid" in lower or "target_cpc" in lower:
        return "AdGroupService.cpc_bid_micros"
    if "budget" in lower:
        return "CampaignBudgetService.amount_micros"
    return "all_micros_transactions"


def _evaluate_observed_amount(
    limit_key: str,
    field_name: str,
    observed_val: float,
    limits: Dict[str, Union[int, float]],
    config_path: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Checks an observed amount against its Service.field limit.

    - If the configured limit is 0 / 0.0 (and no positive global fallback applies),
      the field is NOT modifiable by default (blocked for any value, including 0).
    - If the user supplies a value > 0, the field is modifiable and the supplied
      value is enforced as the upper limit.
    """
    fmt, unit = _FINANCIAL_LIMIT_META.get(limit_key, ("int64", "micros"))
    effective_key = limit_key
    raw_limit = limits.get(limit_key, 0)
    limit_val = float(0 if raw_limit is None else raw_limit)

    if limit_val <= 0:
        if unit == "micros" and float(limits.get("all_micros_transactions", 0) or 0) > 0:
            effective_key = "all_micros_transactions"
            limit_val = float(limits["all_micros_transactions"])
        elif (
            unit == "currency_units"
            and float(limits.get("all_currency_unit_transactions", 0.0) or 0.0) > 0.0
        ):
            effective_key = "all_currency_unit_transactions"
            limit_val = float(limits["all_currency_unit_transactions"])

    if fmt == "int64":
        obs_str = str(int(round(observed_val)))
        lim_str = str(int(round(limit_val)))
    else:
        obs_str = str(float(observed_val))
        lim_str = str(float(limit_val))
    cfg_display = config_path or "config/financial_limits"

    if limit_val <= 0:
        msg = (
            f"BLOCKED BY FINANCIAL UPPER LIMIT (HITL GUARD): Financial field "
            f"'{effective_key}' (API field '{field_name}' = {obs_str} {unit}) is not modifiable "
            f"by default because its value in {cfg_display} is {lim_str}. Supply a value > 0 "
            f"for '{effective_key}' in {cfg_display} to make this field modifiable up to that "
            f"upper limit [API format: {fmt}, monetary unit: {unit}]. Refusing to execute command."
        )
        return {
            "limit_key": effective_key,
            "field_name": field_name,
            "observed_value": int(round(observed_val)) if fmt == "int64" else float(observed_val),
            "upper_limit": int(round(limit_val)) if fmt == "int64" else float(limit_val),
            "monetary_unit": unit,
            "api_format": fmt,
            "config_path": cfg_display,
            "message": msg,
        }

    if observed_val > limit_val:
        msg = (
            f"BLOCKED BY FINANCIAL UPPER LIMIT (HITL GUARD): Financial transaction on "
            f"'{effective_key}' (API field '{field_name}' = {obs_str} {unit}) exceeds the "
            f"configured upper limit of {lim_str} {unit} [API format: {fmt}, monetary unit: {unit}] "
            f"in {cfg_display}. Refusing to execute command."
        )
        return {
            "limit_key": effective_key,
            "field_name": field_name,
            "observed_value": int(round(observed_val)) if fmt == "int64" else float(observed_val),
            "upper_limit": int(round(limit_val)) if fmt == "int64" else float(limit_val),
            "monetary_unit": unit,
            "api_format": fmt,
            "config_path": cfg_display,
            "message": msg,
        }
    return None


def check_financial_transaction_limits(
    operation_summary: str = "",
    after_state: str = "",
    rpc_calls: Optional[List[Dict[str, Any]]] = None,
    script_path: Optional[str] = None,
    code_text: Optional[str] = "",
    limits: Optional[Dict[str, Union[int, float]]] = None,
    config_path: Optional[str] = None,
    receipt: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, Optional[str], List[Dict[str, Any]]]:
    """Checks all financial amounts in RPC payloads, scripts, and state against config/financial_limits.

    Returns:
        Tuple[bool, Optional[str], List[Dict[str, Any]]]:
            (within_limits, error_message_if_exceeded, list_of_violations)
    """
    if isinstance(receipt, dict):
        if not operation_summary:
            operation_summary = str(receipt.get("operation_summary", ""))
        if not after_state:
            after_state = str(receipt.get("after_state", ""))
        if rpc_calls is None and isinstance(receipt.get("dry_run_rpc_calls"), list):
            rpc_calls = receipt.get("dry_run_rpc_calls")
        if not script_path and receipt.get("script_path"):
            script_path = str(receipt.get("script_path"))

    if limits is None:
        limits, config_path = read_financial_limits()

    observations: List[Tuple[str, str, float]] = []

    # 1. Inspect intercepted RPC call request payloads
    for call in rpc_calls or []:
        if not isinstance(call, dict):
            continue
        _extract_payload_financial_amounts(
            call.get("request_payload"),
            service_name=str(call.get("service", "")),
            method_name=str(call.get("method", "")),
            out=observations,
            limits=limits,
        )

    # 2. Inspect Python mutation script source code and/or command text
    combined_code_parts: List[str] = []
    if code_text:
        combined_code_parts.append(code_text)
    if script_path and os.path.isfile(script_path):
        try:
            with open(script_path, "r", encoding="utf-8") as f:
                combined_code_parts.append(f.read())
        except OSError:
            pass
    if combined_code_parts:
        raw_code = "\n".join(combined_code_parts)
        uncommented = "\n".join(
            line.split("#", 1)[0] for line in raw_code.splitlines()
        )
        ctx_for_code = f"{operation_summary}\n{uncommented}"
        for match in _CODE_FINANCIAL_ASSIGN_RE.finditer(uncommented):
            fld = match.group(1).strip().lower()
            raw_num = match.group(2).replace("_", "")
            try:
                num_val = float(raw_num)
            except ValueError:
                continue
            cand_keys = _resolve_candidate_limit_keys(
                fld,
                context_text=ctx_for_code,
                limits=limits,
            )
            if (
                fld == "amount_micros"
                and (
                    "money_amount_off" in uncommented
                    or "orders_over_amount" in uncommented
                    or "PriceOffering" in uncommented
                    or "PromotionAsset" in uncommented
                    or "PriceAsset" in uncommented
                    or "AssetService" in uncommented
                )
                and "RecommendationService" not in uncommented
            ):
                cand_keys = ["AssetService.amount_micros"]
            for lk in cand_keys:
                observations.append((lk, fld, num_val))

    # 3. Inspect operation_summary and after_state text if no structured RPC/script observations were found
    summary_text = f"{operation_summary}\n{after_state}"
    if summary_text.strip() and not observations:
        for match in _CODE_FINANCIAL_ASSIGN_RE.finditer(summary_text):
            fld = match.group(1).strip().lower()
            raw_num = match.group(2).replace("_", "")
            try:
                num_val = float(raw_num)
            except ValueError:
                continue
            for lk in _resolve_candidate_limit_keys(
                fld, context_text=summary_text, limits=limits
            ):
                observations.append((lk, fld, num_val))

        inferred_key = _infer_limit_key_from_context(summary_text)
        for m_match in _TEXT_MICROS_VALUE_RE.finditer(summary_text):
            raw_m = m_match.group(1).replace(",", "").replace("_", "")
            try:
                m_val = float(raw_m)
                observations.append((inferred_key, f"{inferred_key}", m_val))
            except ValueError:
                continue

    violations: List[Dict[str, Any]] = []
    seen_violation_keys: set[Tuple[str, str, float]] = set()
    for lkey, fld_name, obs_val in observations:
        dedup_token = (lkey, fld_name, obs_val)
        if dedup_token in seen_violation_keys:
            continue
        seen_violation_keys.add(dedup_token)
        violation = _evaluate_observed_amount(
            lkey, fld_name, obs_val, limits, config_path
        )
        if violation is not None:
            violations.append(violation)

    if violations:
        combined_msg = " | ".join(v["message"] for v in violations)
        return False, combined_msg, violations
    return True, None, []


_PROHIBITED_DELETION_RPC_PREFIXES = (
    "remove_",
    "delete_",
)
_PROHIBITED_DELETION_RPC_METHODS = frozenset({
    "remove",
    "delete",
    "remove_automatically_created_assets",
    "remove_data_link",
    "remove_product_link",
    "remove_product_link_invitation",
    "remove_you_tube_video_upload",
})
_CODE_PROHIBITED_DELETION_RE = re.compile(
    r"(?:"
    r"[A-Za-z0-9_)\]]\s*\.\s*(?:remove|delete)_[a-z0-9_]+\s*\("
    r"|\.\s*remove(?:_all)?\s*=(?!=)"
    r"|\[\s*['\"]remove(?:_all)?['\"]\s*\]\s*=(?!=)"
    r"|['\"]remove(?:_all)?['\"]\s*:\s*(?!None\b|False\b|['\"]{2}|\[\]|\{\})[^\s,\}\]]"
    r"|\bsetattr\s*\([^,]+,\s*['\"]remove(?:_all)?['\"]"
    r"|\bstatus\s*=\s*(?:['\"]REMOVED['\"]|[A-Za-z0-9_.]*\.REMOVED\b)"
    r"|['\"]status['\"]\s*:\s*['\"]REMOVED['\"]"
    r"|\b(?:proposal_type|proposed_proposal_type)\s*=\s*(?:['\"]REMOVE['\"]|[A-Za-z0-9_.]*\.REMOVE\b)"
    r"|['\"](?:proposal_type|proposed_proposal_type)['\"]\s*:\s*['\"]REMOVE['\"]"
    r")"
)
_SUMMARY_PROHIBITED_DELETION_RE = re.compile(
    r"(?i)(?:"
    r"^\s*(?:remove|delete|removing|deleting|deletion)\b"
    r"|\b(?:remove|delete)_[a-z0-9_]+\b"
    r"|\.(?:remove|remove_all|delete)\b"
    r"|\b(?:operation|op)\s*[:=]\s*['\"]?(?:remove|delete)\b"
    r"|\b(?:remove|delete)\s+(?:campaign|ad[_\s]*group|ad|asset|criterion|criteria|keyword|"
    r"budget|label|feed|conversion|bidding|customer|account|link|video|experiment|draft|"
    r"user[_\s]*list|audience|extension|rule|set|target|modifier|item|resource|entity|goal)s?\b"
    r")"
)
_AFTER_STATE_PROHIBITED_DELETION_RE = re.compile(
    r"(?i)(?:"
    r"^\s*(?:REMOVED|DELETED|REMOVE|DELETE)\s*$"
    r"|\bstatus\s*[:=]\s*['\"]?REMOVED\b"
    r"|\bREMOVED\s*\((?:deleted|permanent|irreversible)\)"
    r"|\bpermanently\s+(?:removed|deleted)\b"
    r")"
)


def _extract_payload_deletion_violations(
    obj: Any,
    service_name: str = "",
    method_name: str = "",
    out: Optional[List[Dict[str, Any]]] = None,
    _depth: int = 0,
) -> List[Dict[str, Any]]:
    """Recursively inspects an RPC call method and payload for prohibited deletion/remove operations."""
    if out is None:
        out = []
    if _depth > 12:
        return out

    svc_prefix = f"{service_name.strip()}." if service_name.strip() else ""
    m_clean = method_name.strip()
    m_lower = m_clean.lower()

    if _depth == 0 and m_lower and (
        m_lower.startswith(_PROHIBITED_DELETION_RPC_PREFIXES)
        or m_lower in _PROHIBITED_DELETION_RPC_METHODS
    ):
        msg = (
            f"BLOCKED BY DELETION PROHIBITION (HITL GUARD): Deletion/remove mutations are prohibited; "
            f"only 'create' and 'update' operations are allowed (attempted RPC method "
            f"'{svc_prefix}{m_clean}'). To stop delivery without deleting a resource, update its status to PAUSED."
        )
        out.append({
            "reason_type": "rpc_method",
            "field_or_method": f"{svc_prefix}{m_clean}",
            "observed_value": m_clean,
            "message": msg,
        })

    if isinstance(obj, dict):
        for k, v in obj.items():
            k_lower = str(k).strip().lower()
            if k_lower in ("remove", "remove_all") and v not in (None, "", False, [], {}):
                msg = (
                    f"BLOCKED BY DELETION PROHIBITION (HITL GUARD): Deletion/remove mutations are prohibited; "
                    f"only 'create' and 'update' operations are allowed (observed '{k_lower}' operation on "
                    f"{v!r} in {svc_prefix}{m_clean or 'mutate'}). To stop delivery without deleting a resource, "
                    f"update its status to PAUSED."
                )
                out.append({
                    "reason_type": "payload_remove_operation",
                    "field_or_method": k_lower,
                    "observed_value": v,
                    "message": msg,
                })
            elif (
                k_lower in ("status", "proposal_type", "proposed_proposal_type")
                and isinstance(v, str)
                and v.strip().upper() in ("REMOVED", "REMOVE")
            ):
                msg = (
                    f"BLOCKED BY DELETION PROHIBITION (HITL GUARD): Deletion/remove mutations are prohibited; "
                    f"only 'create' and 'update' operations are allowed (observed '{k_lower}={v.strip()}' in "
                    f"{svc_prefix}{m_clean or 'mutate'}). To stop delivery without deleting a resource, "
                    f"update its status to PAUSED."
                )
                out.append({
                    "reason_type": "payload_removed_status",
                    "field_or_method": k_lower,
                    "observed_value": v.strip(),
                    "message": msg,
                })
            else:
                _extract_payload_deletion_violations(
                    v,
                    service_name=service_name,
                    method_name=method_name,
                    out=out,
                    _depth=_depth + 1,
                )
    elif isinstance(obj, list):
        for item in obj:
            _extract_payload_deletion_violations(
                item,
                service_name=service_name,
                method_name=method_name,
                out=out,
                _depth=_depth + 1,
            )
    return out


def check_prohibited_deletion_mutation(
    operation_summary: str = "",
    after_state: str = "",
    rpc_calls: Optional[List[Dict[str, Any]]] = None,
    script_path: Optional[str] = None,
    code_text: Optional[str] = "",
    receipt: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, Optional[str], List[Dict[str, Any]]]:
    """Checks RPC payloads, Python scripts, and operation metadata for prohibited deletion/remove operations.

    Only `create` and `update` mutations are allowed; deletion (`remove`) operations are strictly prohibited.

    Returns:
        Tuple[bool, Optional[str], List[Dict[str, Any]]]:
            (is_allowed, error_message_if_prohibited, list_of_violations)
    """
    if isinstance(receipt, dict):
        if not operation_summary:
            operation_summary = str(receipt.get("operation_summary", ""))
        if not after_state:
            after_state = str(receipt.get("after_state", ""))
        if rpc_calls is None and isinstance(receipt.get("dry_run_rpc_calls"), list):
            rpc_calls = receipt.get("dry_run_rpc_calls")
        if not script_path and receipt.get("script_path"):
            script_path = str(receipt.get("script_path"))

    violations: List[Dict[str, Any]] = []

    # 1. Inspect intercepted RPC calls and request payloads
    for call in rpc_calls or []:
        if not isinstance(call, dict):
            continue
        _extract_payload_deletion_violations(
            call.get("request_payload"),
            service_name=str(call.get("service", "")),
            method_name=str(call.get("method", "")),
            out=violations,
        )

    # 2. Inspect Python mutation script source code and/or command text
    combined_code_parts: List[str] = []
    if code_text:
        combined_code_parts.append(code_text)
    if script_path and os.path.isfile(script_path):
        try:
            with open(script_path, "r", encoding="utf-8") as f:
                combined_code_parts.append(f.read())
        except OSError:
            pass
    if combined_code_parts:
        raw_code = "\n".join(combined_code_parts)
        uncommented = "\n".join(
            line.split("#", 1)[0] for line in raw_code.splitlines()
        )
        for match in _CODE_PROHIBITED_DELETION_RE.finditer(uncommented):
            snippet = match.group(0).strip()
            msg = (
                f"BLOCKED BY DELETION PROHIBITION (HITL GUARD): Deletion/remove mutations are prohibited; "
                f"only 'create' and 'update' operations are allowed (detected prohibited deletion syntax "
                f"'{snippet}' in mutation code). To stop delivery without deleting a resource, update its status to PAUSED."
            )
            violations.append({
                "reason_type": "code_deletion_syntax",
                "field_or_method": snippet,
                "observed_value": snippet,
                "message": msg,
            })

    # 3. Inspect operation_summary and after_state metadata
    op_clean = operation_summary.strip()
    if op_clean and _SUMMARY_PROHIBITED_DELETION_RE.search(op_clean):
        msg = (
            f"BLOCKED BY DELETION PROHIBITION (HITL GUARD): Deletion/remove mutations are prohibited; "
            f"only 'create' and 'update' operations are allowed (operation_summary='{op_clean}'). "
            f"To stop delivery without deleting a resource, update its status to PAUSED."
        )
        violations.append({
            "reason_type": "operation_summary_deletion",
            "field_or_method": "operation_summary",
            "observed_value": op_clean,
            "message": msg,
        })

    after_clean = after_state.strip()
    if (
        after_clean
        and after_clean != op_clean
        and _AFTER_STATE_PROHIBITED_DELETION_RE.search(after_clean)
    ):
        msg = (
            f"BLOCKED BY DELETION PROHIBITION (HITL GUARD): Deletion/remove mutations are prohibited; "
            f"only 'create' and 'update' operations are allowed (after_state='{after_clean}'). "
            f"To stop delivery without deleting a resource, update its status to PAUSED."
        )
        violations.append({
            "reason_type": "after_state_deletion",
            "field_or_method": "after_state",
            "observed_value": after_clean,
            "message": msg,
        })

    if violations:
        dedup_msgs: List[str] = []
        for v in violations:
            m = v["message"]
            if m not in dedup_msgs:
                dedup_msgs.append(m)
        return False, " | ".join(dedup_msgs), violations
    return True, None, []


def _find_google_ads_yaml() -> Optional[str]:
    """Locates the active config/google-ads.yaml file if present."""
    this_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_root = os.path.abspath(os.path.join(this_dir, "../../.."))
    candidates = [
        os.environ.get("GOOGLE_ADS_CONFIGURATION_FILE_PATH", ""),
        os.path.abspath(os.path.join("config", "google-ads.yaml")),
        os.path.join(plugin_root, "config", "google-ads.yaml"),
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/config/google-ads.yaml"
        ),
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return os.path.abspath(path)
    return None


def resolve_actor_metadata(
    customer_id: str,
    receipt: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Collects non-secret actor and session identity metadata for the audit log."""
    try:
        os_user = getpass.getuser()
    except Exception:
        os_user = (
            os.environ.get("USER")
            or os.environ.get("USERNAME")
            or "unknown"
        )

    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "unknown"

    login_cid: Optional[str] = None
    impersonated_email: Optional[str] = None
    client_id_masked: Optional[str] = None
    auth_type = "unknown"
    assistant_version: Optional[str] = None

    yaml_path = _find_google_ads_yaml()
    if yaml_path:
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line or line.startswith("#") or ":" not in line:
                        continue
                    k, v = line.split(":", 1)
                    key = k.strip()
                    val = v.strip().strip("'\"")
                    if key == "login_customer_id" and val:
                        login_cid = val
                    elif key == "impersonated_email" and val:
                        impersonated_email = val
                    elif key == "json_key_file_path" and val:
                        auth_type = "service_account"
                    elif key == "client_id" and val and not val.startswith("INSERT_"):
                        if auth_type == "unknown":
                            auth_type = "oauth2"
                        client_id_masked = (
                            f"{val[:8]}..." if len(val) > 8 else "***"
                        )
                    elif key == "ads_assistant" and val:
                        assistant_version = val
        except OSError:
            pass

    receipt_data = receipt or {}
    cli_conv_id = (
        receipt_data.get("cli_conversation_id")
        or os.environ.get("GEMINI_CONVERSATION_ID")
        or os.environ.get("CLAUDE_SESSION_ID")
    )
    cli_transcript = (
        receipt_data.get("cli_transcript_path")
        or os.environ.get("GEMINI_TRANSCRIPT_PATH")
        or os.environ.get("CLAUDE_TRANSCRIPT_PATH")
    )
    model_name = receipt_data.get("model_name")

    return {
        "os_user": os_user,
        "hostname": hostname,
        "login_customer_id": login_cid,
        "target_customer_id": str(customer_id or receipt_data.get("customer_id", "")).strip(),
        "auth_type": auth_type,
        "impersonated_email": impersonated_email,
        "client_id_masked": client_id_masked,
        "ads_assistant_version": assistant_version,
        "cli_conversation_id": cli_conv_id,
        "cli_transcript_path": cli_transcript,
        "model_name": model_name,
    }


def _serialize_rpc_object(obj: Any, _depth: int = 0) -> Any:
    """Safely converts Protobuf messages, proto-plus objects, or Python objects into JSON-safe types."""
    if _depth > 8:
        return str(obj)
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if isinstance(obj, dict):
        return {
            str(k): (
                "[REDACTED]"
                if str(k).lower() in _SENSITIVE_KEYS
                else _serialize_rpc_object(v, _depth + 1)
            )
            for k, v in obj.items()
        }
    if isinstance(obj, (list, tuple, set)):
        return [_serialize_rpc_object(item, _depth + 1) for item in obj]

    # 1. proto-plus Message (type(obj).to_dict(obj))
    obj_type = type(obj)
    to_dict_fn = getattr(obj_type, "to_dict", None)
    if callable(to_dict_fn):
        try:
            raw_dict = to_dict_fn(obj)
            if isinstance(raw_dict, dict):
                return _serialize_rpc_object(raw_dict, _depth + 1)
        except Exception:
            pass

    # 2. Standard google.protobuf.message.Message or wrapped _pb
    pb_candidate = getattr(obj, "_pb", obj)
    if hasattr(pb_candidate, "DESCRIPTOR"):
        try:
            from google.protobuf.json_format import MessageToDict

            pb_dict = MessageToDict(
                pb_candidate, preserving_proto_field_name=True
            )
            if isinstance(pb_dict, dict):
                return _serialize_rpc_object(pb_dict, _depth + 1)
        except Exception:
            pass

    # 3. Fallback: inspect known Google Ads request/response/error attributes
    known_attrs = (
        "customer_id",
        "operations",
        "operation",
        "conversions",
        "conversion_adjustments",
        "selected_incentive_id",
        "feedback_type",
        "campaign_budget",
        "experiment",
        "campaign_draft",
        "email_address",
        "customer_client",
        "validate_only",
        "partial_failure",
        "response_content_type",
        "resource_name",
        "results",
        "mutate_operation_responses",
        "partial_failure_error",
        "request_id",
        "errors",
        "message",
        "error_code",
        "paths",
        "update",
        "create",
        "remove",
        "update_mask",
    )
    extracted: Dict[str, Any] = {}
    if hasattr(obj, "__dict__"):
        for k, v in vars(obj).items():
            if not k.startswith("_") and not callable(v):
                if k.lower() in _SENSITIVE_KEYS:
                    extracted[k] = "[REDACTED]"
                else:
                    extracted[k] = _serialize_rpc_object(v, _depth + 1)
    for attr in known_attrs:
        if attr not in extracted and hasattr(obj, attr):
            try:
                val = getattr(obj, attr)
                if not callable(val):
                    extracted[attr] = _serialize_rpc_object(val, _depth + 1)
            except Exception:
                continue
    if extracted:
        return extracted

    return str(obj)


def _wrap_service_for_audit(
    service: Any,
    service_name: str,
    captured_calls: List[Dict[str, Any]],
    expected_request_hashes: Optional[List[str]] = None,
    enforce_request_hash: bool = False,
    dry_run_mode: bool = False,
) -> Any:
    """Wraps mutation methods on a GoogleAdsClient service instance to verify SHA-256 and record payloads."""
    should_enforce = enforce_request_hash or (expected_request_hashes is not None)
    expected_list = list(expected_request_hashes) if expected_request_hashes else []

    for attr_name in dir(service):
        if attr_name.startswith("_"):
            continue
        if not attr_name.startswith(_MUTATION_METHOD_PREFIXES):
            continue
        try:
            orig_method = getattr(service, attr_name)
        except Exception:
            continue
        if not callable(orig_method) or getattr(orig_method, "_is_audit_wrapped", False):
            continue

        def _make_wrapper(method_fn: Any, svc_name: str, m_name: str) -> Any:
            @functools.wraps(method_fn)
            def _wrapped(*args: Any, **kwargs: Any) -> Any:
                sent_at_iso = datetime.now(timezone.utc).isoformat()
                t0 = time.perf_counter()

                if "request" in kwargs:
                    req_payload = _serialize_rpc_object(kwargs["request"])
                elif args:
                    req_payload = _serialize_rpc_object(
                        args[0] if len(args) == 1 else list(args)
                    )
                else:
                    req_payload = _serialize_rpc_object(kwargs)

                req_sha256 = compute_mutate_request_sha256(
                    svc_name, m_name, req_payload
                )
                call_index = len(captured_calls)

                call_record: Dict[str, Any] = {
                    "service": svc_name,
                    "method": m_name,
                    "sent_at_iso": sent_at_iso,
                    "request_sha256": req_sha256,
                    "request_payload": req_payload,
                }

                supports_validate_only = (
                    m_name not in _NON_VALIDATE_ONLY_MUTATION_METHODS
                )
                payload_vo = (
                    req_payload.get("validate_only")
                    if isinstance(req_payload, dict)
                    else None
                )
                is_validate_only_true = supports_validate_only and (
                    payload_vo is True
                    or (payload_vo is None and kwargs.get("validate_only") is True)
                )

                # Pre-RPC Deletion Prohibition Guard: block any deletion/remove mutation before calling the API.
                allowed_non_delete, delete_err, delete_violations = (
                    check_prohibited_deletion_mutation(rpc_calls=[call_record])
                )
                if not allowed_non_delete and delete_err:
                    err_msg = f"BLOCKED BEFORE RPC: {delete_err}"
                    call_record.update({
                        "received_at_iso": datetime.now(timezone.utc).isoformat(),
                        "duration_ms": round((time.perf_counter() - t0) * 1000.0, 3),
                        "status": "BLOCKED_PROHIBITED_DELETION",
                        "expected_request_sha256": None,
                        "request_sha256_verified": False,
                        "google_ads_request_id": None,
                        "deletion_violations": delete_violations,
                        "response_payload": {
                            "exception_type": "PermissionError",
                            "message": err_msg,
                        },
                        "error": err_msg,
                    })
                    captured_calls.append(call_record)
                    raise PermissionError(err_msg)

                # Pre-RPC Dry-Run Guard: block any mutation call during --dry-run that lacks
                # an explicit validate_only=True (including omitted validate_only or
                # non-validate_only RPCs such as mutate_billing_setup, book_campaigns, apply_incentive).
                if dry_run_mode and not is_validate_only_true:
                    if not supports_validate_only:
                        err_msg = (
                            f"BLOCKED BEFORE RPC: {svc_name}.{m_name} does not support "
                            f"validate_only=True dry-run requests and would execute a live "
                            f"mutation immediately. Guard live calls behind '--execute' and "
                            f"perform read-only preflight queries during '--dry-run'."
                        )
                    else:
                        err_msg = (
                            f"BLOCKED BEFORE RPC: Dry-run intercepted mutation call to "
                            f"{svc_name}.{m_name} without validate_only=True "
                            f"(observed validate_only={payload_vo!r}). All mutation RPCs executed "
                            f"during '--dry-run' MUST explicitly set validate_only=True."
                        )
                    call_record.update({
                        "received_at_iso": datetime.now(timezone.utc).isoformat(),
                        "duration_ms": round((time.perf_counter() - t0) * 1000.0, 3),
                        "status": "BLOCKED_MISSING_VALIDATE_ONLY",
                        "expected_request_sha256": None,
                        "request_sha256_verified": False,
                        "google_ads_request_id": None,
                        "response_payload": {
                            "exception_type": "PermissionError",
                            "message": err_msg,
                        },
                        "error": err_msg,
                    })
                    captured_calls.append(call_record)
                    raise PermissionError(err_msg)

                # Pre-RPC Financial Upper Limit Guard: block any financial transaction exceeding
                # a configured upper limit (> 0) in config/financial_limits before calling the API.
                within_fin_limits, fin_limit_err, fin_violations = (
                    check_financial_transaction_limits(rpc_calls=[call_record])
                )
                if not within_fin_limits and fin_limit_err:
                    call_record.update({
                        "received_at_iso": datetime.now(timezone.utc).isoformat(),
                        "duration_ms": round((time.perf_counter() - t0) * 1000.0, 3),
                        "status": "BLOCKED_FINANCIAL_LIMIT_EXCEEDED",
                        "expected_request_sha256": None,
                        "request_sha256_verified": False,
                        "google_ads_request_id": None,
                        "financial_limit_violations": fin_violations,
                        "response_payload": {
                            "exception_type": "PermissionError",
                            "message": fin_limit_err,
                        },
                        "error": fin_limit_err,
                    })
                    captured_calls.append(call_record)
                    raise PermissionError(fin_limit_err)

                # Pre-RPC Mutates Config check: block live mutations (including omitted validate_only
                # or non-validate_only RPCs) if execute_mutates = false.
                is_live_rpc = (not is_validate_only_true) or should_enforce
                if is_live_rpc and not is_execute_mutates_enabled():
                    err_msg = (
                        f"BLOCKED BEFORE RPC: Mutate support is disabled by configuration "
                        f"(execute_mutates = false in config/assistant_config). Cannot execute live "
                        f"mutation call to {svc_name}.{m_name}."
                    )
                    call_record.update({
                        "received_at_iso": datetime.now(timezone.utc).isoformat(),
                        "duration_ms": round((time.perf_counter() - t0) * 1000.0, 3),
                        "status": "BLOCKED_MUTATES_DISABLED",
                        "expected_request_sha256": None,
                        "request_sha256_verified": False,
                        "google_ads_request_id": None,
                        "response_payload": {
                            "exception_type": "PermissionError",
                            "message": err_msg,
                        },
                        "error": err_msg,
                    })
                    captured_calls.append(call_record)
                    raise PermissionError(err_msg)

                # Pre-RPC SHA-256 verification: ensure live request matches dry-run BEFORE sending
                if should_enforce:
                    if call_index >= len(expected_list):
                        err_msg = (
                            f"BLOCKED BEFORE RPC: Unapproved mutation call #{call_index + 1} to "
                            f"{svc_name}.{m_name} (request_sha256={req_sha256}) was not present in "
                            f"the validate_only=True dry-run receipt (expected {len(expected_list)} call(s))."
                        )
                        call_record.update({
                            "received_at_iso": datetime.now(timezone.utc).isoformat(),
                            "duration_ms": round((time.perf_counter() - t0) * 1000.0, 3),
                            "status": "BLOCKED_SHA256_MISMATCH",
                            "expected_request_sha256": None,
                            "request_sha256_verified": False,
                            "google_ads_request_id": None,
                            "response_payload": {
                                "exception_type": "PermissionError",
                                "message": err_msg,
                            },
                            "error": err_msg,
                        })
                        captured_calls.append(call_record)
                        raise PermissionError(err_msg)

                    expected_sha = expected_list[call_index]
                    if req_sha256 != expected_sha:
                        err_msg = (
                            f"BLOCKED BEFORE RPC: Mutate request SHA-256 mismatch on call #{call_index + 1} "
                            f"to {svc_name}.{m_name} (expected {expected_sha} from validate_only=True dry-run, "
                            f"got {req_sha256}). The live mutate request payload was altered after dry-run."
                        )
                        call_record.update({
                            "received_at_iso": datetime.now(timezone.utc).isoformat(),
                            "duration_ms": round((time.perf_counter() - t0) * 1000.0, 3),
                            "status": "BLOCKED_SHA256_MISMATCH",
                            "expected_request_sha256": expected_sha,
                            "request_sha256_verified": False,
                            "google_ads_request_id": None,
                            "response_payload": {
                                "exception_type": "PermissionError",
                                "message": err_msg,
                            },
                            "error": err_msg,
                        })
                        captured_calls.append(call_record)
                        raise PermissionError(err_msg)

                    call_record["expected_request_sha256"] = expected_sha
                    call_record["request_sha256_verified"] = True
                else:
                    call_record["expected_request_sha256"] = req_sha256
                    call_record["request_sha256_verified"] = True

                try:
                    response = method_fn(*args, **kwargs)
                    received_at_iso = datetime.now(timezone.utc).isoformat()
                    duration_ms = round((time.perf_counter() - t0) * 1000.0, 3)
                    resp_payload = _serialize_rpc_object(response)
                    req_id = getattr(response, "request_id", None)
                    if not req_id and isinstance(resp_payload, dict):
                        req_id = resp_payload.get("request_id")
                    call_record.update({
                        "received_at_iso": received_at_iso,
                        "duration_ms": duration_ms,
                        "status": "SUCCESS",
                        "google_ads_request_id": req_id,
                        "response_payload": resp_payload,
                        "error": None,
                    })
                    captured_calls.append(call_record)
                    return response
                except Exception as ex:
                    received_at_iso = datetime.now(timezone.utc).isoformat()
                    duration_ms = round((time.perf_counter() - t0) * 1000.0, 3)
                    req_id = getattr(ex, "request_id", None)
                    failure_obj = getattr(ex, "failure", None)
                    err_payload = (
                        _serialize_rpc_object(failure_obj)
                        if failure_obj is not None
                        else {"exception_type": type(ex).__name__, "message": str(ex)}
                    )
                    call_record.update({
                        "received_at_iso": received_at_iso,
                        "duration_ms": duration_ms,
                        "status": "FAILED",
                        "google_ads_request_id": req_id,
                        "response_payload": err_payload,
                        "error": str(ex),
                    })
                    captured_calls.append(call_record)
                    raise

            setattr(_wrapped, "_is_audit_wrapped", True)
            return _wrapped

        try:
            setattr(
                service,
                attr_name,
                _make_wrapper(orig_method, service_name, attr_name),
            )
        except Exception:
            continue

    return service


def _run_target_script_with_interception(
    script_path: str,
    script_args: List[str],
    trace_file: str,
) -> None:
    """Executes the target mutation script while intercepting GoogleAdsClient service calls."""
    captured_calls: List[Dict[str, Any]] = []
    enforce_hash = os.environ.get(_ENFORCE_HASH_ENV_VAR, "") == "1"
    dry_run_mode = os.environ.get(_DRY_RUN_MODE_ENV_VAR, "") == "1"
    expected_hashes: Optional[List[str]] = None
    raw_expected = os.environ.get(_EXPECTED_HASHES_ENV_VAR, "").strip()
    if raw_expected:
        try:
            parsed = json.loads(raw_expected)
            if isinstance(parsed, list):
                expected_hashes = [str(item) for item in parsed]
        except Exception:
            expected_hashes = []

    script_dir = os.path.dirname(os.path.abspath(script_path))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    for p in list(sys.path):
        if p and os.path.isdir(os.path.join(p, "google")):
            current_paths = getattr(sys.modules.get("google"), "__path__", [])
            if p not in current_paths:
                for m in list(sys.modules.keys()):
                    if m == "google" or m.startswith("google."):
                        sys.modules.pop(m, None)
            break

    try:
        from google.ads.googleads.client import GoogleAdsClient

        orig_get_service = GoogleAdsClient.get_service

        @functools.wraps(orig_get_service)
        def _hooked_get_service(self: Any, name: str, *args: Any, **kwargs: Any) -> Any:
            svc = orig_get_service(self, name, *args, **kwargs)
            return _wrap_service_for_audit(
                svc,
                name,
                captured_calls,
                expected_request_hashes=expected_hashes,
                enforce_request_hash=enforce_hash,
                dry_run_mode=dry_run_mode,
            )

        GoogleAdsClient.get_service = _hooked_get_service  # type: ignore[method-assign]
    except Exception:
        pass

    sys.argv = [script_path, *script_args]
    try:
        runpy.run_path(script_path, run_name="__main__")
    finally:
        if trace_file:
            try:
                with open(trace_file, "w", encoding="utf-8") as f:
                    json.dump(captured_calls, f)
            except OSError:
                pass


def _execute_script_subprocess(
    script_path: str,
    script_args: List[str],
    expected_request_hashes: Optional[List[str]] = None,
    enforce_request_hash: bool = False,
    dry_run_mode: bool = False,
) -> Tuple[subprocess.CompletedProcess[str], str, str, float, List[Dict[str, Any]]]:
    """Runs the mutation script in a subprocess with RPC audit interception and pre-RPC SHA-256 verification."""
    fd, trace_path = tempfile.mkstemp(prefix="ads_mutation_trace_", suffix=".json")
    os.close(fd)

    env = os.environ.copy()
    env[_TRACE_ENV_VAR] = trace_path
    if dry_run_mode:
        env[_DRY_RUN_MODE_ENV_VAR] = "1"
    else:
        env.pop(_DRY_RUN_MODE_ENV_VAR, None)
    if enforce_request_hash or expected_request_hashes is not None:
        env[_ENFORCE_HASH_ENV_VAR] = "1"
        env[_EXPECTED_HASHES_ENV_VAR] = json.dumps(expected_request_hashes or [])
    else:
        env.pop(_ENFORCE_HASH_ENV_VAR, None)
        env.pop(_EXPECTED_HASHES_ENV_VAR, None)

    cmd = [
        sys.executable,
        os.path.abspath(__file__),
        "--_exec-target",
        script_path,
        *script_args,
    ]
    sent_at_iso = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env)
    duration_ms = round((time.perf_counter() - t0) * 1000.0, 3)
    received_at_iso = datetime.now(timezone.utc).isoformat()

    captured_calls: List[Dict[str, Any]] = []
    if os.path.isfile(trace_path):
        try:
            with open(trace_path, "r", encoding="utf-8") as f:
                raw = f.read().strip()
                if raw:
                    data = json.loads(raw)
                    if isinstance(data, list):
                        captured_calls = data
        except Exception:
            pass
        finally:
            try:
                os.remove(trace_path)
            except OSError:
                pass

    return result, sent_at_iso, received_at_iso, duration_ms, captured_calls


def append_mutation_audit_log(
    *,
    phase: str,
    status: str,
    customer_id: str,
    operation_summary: str,
    before_state: str,
    after_state: str,
    consequences: List[str],
    reversibility: str,
    script_path: Optional[str],
    script_sha256: str,
    validate_only: bool,
    request_sent_at_iso: str,
    response_received_at_iso: str,
    duration_ms: float,
    exit_code: int,
    stdout: str,
    stderr: str,
    command: Optional[List[str]] = None,
    rpc_calls: Optional[List[Dict[str, Any]]] = None,
    receipt: Optional[Dict[str, Any]] = None,
    user_approved_at_iso: Optional[str] = None,
) -> Dict[str, Any]:
    """Writes a structured audit entry to saved/logs/mutation_audit.jsonl."""
    receipt_data = receipt or {}
    calls: List[Dict[str, Any]] = []
    for raw_call in rpc_calls or []:
        c_copy = dict(raw_call)
        if not c_copy.get("request_sha256"):
            c_copy["request_sha256"] = compute_mutate_request_sha256(
                str(c_copy.get("service", "")),
                str(c_copy.get("method", "")),
                c_copy.get("request_payload"),
            )
        calls.append(c_copy)

    effective_sent_at = (
        str(calls[0].get("sent_at_iso"))
        if calls and calls[0].get("sent_at_iso")
        else request_sent_at_iso
    )
    effective_received_at = (
        str(calls[-1].get("received_at_iso"))
        if calls and calls[-1].get("received_at_iso")
        else response_received_at_iso
    )

    fallback_request_payload = {
        "customer_id": str(customer_id).strip(),
        "validate_only": validate_only,
        "operation_summary": operation_summary.strip(),
        "before_state": before_state.strip(),
        "after_state": after_state.strip(),
        "script_path": script_path or "",
        "script_sha256": script_sha256,
    }

    if calls:
        request_payload: Any = (
            calls[0].get("request_payload")
            if len(calls) == 1
            else [c.get("request_payload") for c in calls]
        )
        response_payload: Any = (
            calls[0].get("response_payload")
            if len(calls) == 1
            else [c.get("response_payload") for c in calls]
        )
    else:
        request_payload = fallback_request_payload
        response_payload = {
            "stdout": stdout.strip(),
            "stderr": stderr.strip(),
            "exit_code": exit_code,
        }

    call_hashes = [
        str(c["request_sha256"]) for c in calls if c.get("request_sha256")
    ]
    aggregate_request_sha256 = compute_aggregate_request_sha256(
        call_hashes, fallback_request_payload
    )
    receipt_has_rpc_hashes = bool(receipt_data.get("request_sha256_list"))
    if calls and not receipt_has_rpc_hashes:
        expected_receipt_sha256 = aggregate_request_sha256
    else:
        expected_receipt_sha256 = str(
            receipt_data.get("request_sha256") or aggregate_request_sha256
        )
    if calls:
        request_sha256_verified = all(
            bool(c.get("request_sha256_verified", True)) for c in calls
        ) and (
            phase != "EXECUTE"
            or not receipt_has_rpc_hashes
            or aggregate_request_sha256 == expected_receipt_sha256
        )
    else:
        request_sha256_verified = (
            phase != "EXECUTE"
            or not receipt_data.get("request_sha256")
            or aggregate_request_sha256 == expected_receipt_sha256
        )

    is_financial = bool(receipt_data.get("is_financial_transaction")) or is_financial_mutation(
        operation_summary=operation_summary,
        before_state=before_state,
        after_state=after_state,
        rpc_calls=calls,
    )

    request_ids = [
        str(c["google_ads_request_id"])
        for c in calls
        if c.get("google_ads_request_id")
    ]
    rpc_errors = [str(c["error"]) for c in calls if c.get("error")]
    error_summary: Optional[str] = None
    if exit_code != 0 or status in (
        "FAILED",
        "DRY_RUN_FAILED",
        "BLOCKED_MUTATES_DISABLED",
        "BLOCKED_SHA256_MISMATCH",
        "BLOCKED_MISSING_VALIDATE_ONLY",
        "BLOCKED_FINANCIAL_CONSEQUENCE_MISSING",
        "BLOCKED_FINANCIAL_LIMIT_EXCEEDED",
    ):
        error_summary = (
            "; ".join(rpc_errors)
            if rpc_errors
            else (stderr.strip() or stdout.strip() or f"Process exited with code {exit_code}")
        )

    audit_record: Dict[str, Any] = {
        "audit_id": str(uuid.uuid4()),
        "receipt_id": str(receipt_data.get("receipt_id") or uuid.uuid4()),
        "phase": phase,
        "status": status,
        "actor": resolve_actor_metadata(customer_id=customer_id, receipt=receipt_data),
        "request": {
            "sent_at_iso": effective_sent_at,
            "customer_id": str(customer_id).strip(),
            "validate_only": validate_only,
            "is_financial_transaction": is_financial,
            "operation_summary": operation_summary.strip(),
            "script_path": script_path or "",
            "script_sha256": script_sha256,
            "request_sha256": aggregate_request_sha256,
            "request_sha256_list": call_hashes,
            "expected_request_sha256": expected_receipt_sha256,
            "request_sha256_verified": request_sha256_verified,
            "command": command or [],
            "payload": request_payload,
            "rpc_calls": [
                {
                    "service": c.get("service"),
                    "method": c.get("method"),
                    "sent_at_iso": c.get("sent_at_iso"),
                    "request_sha256": c.get("request_sha256"),
                    "expected_request_sha256": c.get(
                        "expected_request_sha256", c.get("request_sha256")
                    ),
                    "request_sha256_verified": bool(
                        c.get("request_sha256_verified", True)
                    ),
                    "request_payload": c.get("request_payload"),
                }
                for c in calls
            ],
        },
        "approval": {
            "dry_run_validated_at_iso": receipt_data.get("timestamp_iso"),
            "hook_prompted_at_iso": receipt_data.get("hook_prompted_at_iso"),
            "user_approved_at_iso": user_approved_at_iso,
            "is_financial_transaction": is_financial,
            "before_state": before_state.strip(),
            "after_state": after_state.strip(),
            "consequences": [c.strip() for c in consequences if str(c).strip()],
            "reversibility": reversibility.strip().upper(),
        },
        "response": {
            "received_at_iso": effective_received_at,
            "duration_ms": duration_ms,
            "exit_code": exit_code,
            "google_ads_request_ids": request_ids,
            "payload": response_payload,
            "rpc_responses": [
                {
                    "service": c.get("service"),
                    "method": c.get("method"),
                    "received_at_iso": c.get("received_at_iso"),
                    "duration_ms": c.get("duration_ms"),
                    "status": c.get("status"),
                    "google_ads_request_id": c.get("google_ads_request_id"),
                    "response_payload": c.get("response_payload"),
                    "error": c.get("error"),
                }
                for c in calls
            ],
            "stdout": stdout.strip(),
            "stderr": stderr.strip(),
            "error": error_summary,
        },
    }

    serialized_line = json.dumps(audit_record, default=str) + "\n"
    for log_path in get_audit_log_paths():
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(serialized_line)
            if sys.platform != "win32" and os.path.isfile(log_path):
                try:
                    os.chmod(log_path, 0o600)
                except OSError:
                    pass
        except OSError:
            continue

    return audit_record


def _remove_stale_receipts() -> None:
    """Removes any existing dry-run receipt files when a dry-run or limit check fails."""
    for target_path in get_receipt_paths():
        if os.path.isfile(target_path):
            try:
                os.remove(target_path)
            except OSError:
                pass


def write_dry_run_receipt(
    customer_id: str,
    operation_summary: str,
    before_state: str,
    after_state: str,
    consequences: List[str],
    reversibility: str,
    script_path: Optional[str] = None,
    dry_run_output: str = "",
    request_sent_at_iso: Optional[str] = None,
    response_received_at_iso: Optional[str] = None,
    rpc_calls: Optional[List[Dict[str, Any]]] = None,
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

    normalized_calls: List[Dict[str, Any]] = []
    request_sha256_list: List[str] = []
    for raw_call in rpc_calls or []:
        c_copy = dict(raw_call)
        c_sha = str(c_copy.get("request_sha256") or "")
        if not c_sha:
            c_sha = compute_mutate_request_sha256(
                str(c_copy.get("service", "")),
                str(c_copy.get("method", "")),
                c_copy.get("request_payload"),
            )
            c_copy["request_sha256"] = c_sha
        request_sha256_list.append(c_sha)
        normalized_calls.append(c_copy)

    # Enforce prohibition of deletion/remove mutations (only create and update are allowed)
    allowed_non_delete, delete_err, _ = check_prohibited_deletion_mutation(
        operation_summary=operation_summary,
        after_state=after_state,
        rpc_calls=normalized_calls,
        script_path=resolved_script if resolved_script else None,
    )
    if not allowed_non_delete and delete_err:
        _remove_stale_receipts()
        raise ValueError(delete_err)

    # Enforce configured financial transaction upper limits at the HITL step
    within_fin_limits, fin_limit_err, _ = check_financial_transaction_limits(
        operation_summary=operation_summary,
        after_state=after_state,
        rpc_calls=normalized_calls,
        script_path=resolved_script if resolved_script else None,
    )
    if not within_fin_limits and fin_limit_err:
        _remove_stale_receipts()
        raise ValueError(fin_limit_err)

    is_financial = is_financial_mutation(
        operation_summary=operation_summary,
        before_state=before_state,
        after_state=after_state,
        rpc_calls=normalized_calls,
    )
    if is_financial and not has_financial_consequence_disclosure(clean_consequences):
        raise ValueError(
            "Financial mutation requires explicit monetary, currency, spend, budget, "
            "billing, credit, or bidding impact disclosure in --consequences "
            f"(operation: '{operation_summary.strip()}')."
        )

    fallback_req_meta = {
        "customer_id": str(customer_id).strip(),
        "operation_summary": operation_summary.strip(),
        "before_state": before_state.strip(),
        "after_state": after_state.strip(),
        "script_path": resolved_script,
        "script_sha256": script_hash,
    }
    request_sha256 = compute_aggregate_request_sha256(
        request_sha256_list, fallback_req_meta
    )

    receipt: Dict[str, Any] = {
        "receipt_id": str(uuid.uuid4()),
        "status": "DRY_RUN_PASSED",
        "timestamp": now_ts,
        "timestamp_iso": now_iso,
        "request_sent_at_iso": request_sent_at_iso or now_iso,
        "response_received_at_iso": response_received_at_iso or now_iso,
        "customer_id": str(customer_id).strip(),
        "operation_summary": operation_summary.strip(),
        "is_financial_transaction": is_financial,
        "before_state": before_state.strip(),
        "after_state": after_state.strip(),
        "consequences": clean_consequences,
        "reversibility": reversibility.strip().upper(),
        "script_path": resolved_script,
        "script_sha256": script_hash,
        "request_sha256": request_sha256,
        "request_sha256_list": request_sha256_list,
        "dry_run_output": dry_run_output.strip(),
    }
    if normalized_calls:
        receipt["dry_run_rpc_calls"] = normalized_calls

    for target_path in get_receipt_paths():
        try:
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(receipt, f, indent=2)
            if sys.platform != "win32" and os.path.isfile(target_path):
                try:
                    os.chmod(target_path, 0o600)
                except OSError:
                    pass
        except OSError:
            continue

    return receipt


def mark_receipt_executed(
    user_approved_at_iso: Optional[str] = None,
    request_sent_at_iso: Optional[str] = None,
    response_received_at_iso: Optional[str] = None,
    audit_id: Optional[str] = None,
) -> None:
    """Marks existing dry-run receipts as EXECUTED to prevent replay without re-verification."""
    executed_iso = response_received_at_iso or datetime.now(timezone.utc).isoformat()
    for target_path in get_receipt_paths():
        if os.path.isfile(target_path):
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data["status"] = "EXECUTED"
                data["executed_at_iso"] = executed_iso
                if user_approved_at_iso:
                    data["user_approved_at_iso"] = user_approved_at_iso
                if request_sent_at_iso:
                    data["live_request_sent_at_iso"] = request_sent_at_iso
                if response_received_at_iso:
                    data["live_response_received_at_iso"] = response_received_at_iso
                if audit_id:
                    data["audit_id"] = audit_id
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

    dry_run_calls = receipt.get("dry_run_rpc_calls")
    effective_script = script_path or str(receipt.get("script_path", ""))

    # Enforce prohibition of deletion/remove mutations (only create and update are allowed)
    allowed_non_delete, delete_err, _ = check_prohibited_deletion_mutation(
        operation_summary=str(receipt.get("operation_summary", "")),
        after_state=str(receipt.get("after_state", "")),
        rpc_calls=dry_run_calls if isinstance(dry_run_calls, list) else None,
        script_path=effective_script if effective_script else None,
        receipt=receipt,
    )
    if not allowed_non_delete and delete_err:
        return (
            False,
            delete_err,
            receipt,
        )

    is_financial = bool(receipt.get("is_financial_transaction")) or is_financial_mutation(
        operation_summary=str(receipt.get("operation_summary", "")),
        before_state=str(receipt.get("before_state", "")),
        after_state=str(receipt.get("after_state", "")),
        rpc_calls=dry_run_calls if isinstance(dry_run_calls, list) else None,
    )
    if is_financial and not has_financial_consequence_disclosure(
        [str(c) for c in consequences]
    ):
        return (
            False,
            "Dry-run receipt for financial mutation is missing explicit monetary, currency, "
            "spend, budget, billing, credit, or bidding impact disclosure in consequences.",
            receipt,
        )

    # Verify financial transaction upper limits against current config/financial_limits
    within_fin_limits, fin_limit_err, _ = check_financial_transaction_limits(
        operation_summary=str(receipt.get("operation_summary", "")),
        after_state=str(receipt.get("after_state", "")),
        rpc_calls=dry_run_calls if isinstance(dry_run_calls, list) else None,
        script_path=effective_script if effective_script else None,
    )
    if not within_fin_limits and fin_limit_err:
        return (
            False,
            fin_limit_err,
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

    # Verify canonical mutate request SHA-256 integrity on the receipt
    recorded_req_sha = str(receipt.get("request_sha256", "")).strip()
    recorded_sha_list = receipt.get("request_sha256_list")
    if isinstance(dry_run_calls, list) and dry_run_calls:
        recomputed_list: List[str] = []
        for idx, call in enumerate(dry_run_calls):
            if not isinstance(call, dict):
                return (
                    False,
                    f"Dry-run receipt RPC call #{idx + 1} is malformed. Re-run --dry-run before executing.",
                    receipt,
                )
            recomputed_sha = compute_mutate_request_sha256(
                str(call.get("service", "")),
                str(call.get("method", "")),
                call.get("request_payload"),
            )
            call_sha = str(call.get("request_sha256", "")).strip()
            if call_sha and call_sha != recomputed_sha:
                return (
                    False,
                    f"Dry-run receipt mutate request SHA-256 mismatch on RPC call #{idx + 1} "
                    "(dry-run request payload was tampered with). Re-run --dry-run before executing.",
                    receipt,
                )
            recomputed_list.append(recomputed_sha)

        if isinstance(recorded_sha_list, list) and recorded_sha_list != recomputed_list:
            return (
                False,
                "Dry-run receipt request_sha256_list mismatch (SHA-256 mismatch). "
                "Re-run --dry-run before executing.",
                receipt,
            )
        recomputed_agg = compute_aggregate_request_sha256(recomputed_list)
        if recorded_req_sha and recorded_req_sha != recomputed_agg:
            return (
                False,
                "Dry-run receipt aggregate request_sha256 mismatch (SHA-256 mismatch). "
                "Re-run --dry-run before executing.",
                receipt,
            )
    elif recorded_req_sha:
        fallback_meta = {
            "customer_id": str(receipt.get("customer_id", "")).strip(),
            "operation_summary": str(receipt.get("operation_summary", "")).strip(),
            "before_state": str(receipt.get("before_state", "")).strip(),
            "after_state": str(receipt.get("after_state", "")).strip(),
            "script_path": str(receipt.get("script_path", "")),
            "script_sha256": str(receipt.get("script_sha256", "")),
        }
        recomputed_fallback_sha = compute_aggregate_request_sha256([], fallback_meta)
        if recorded_req_sha != recomputed_fallback_sha:
            return (
                False,
                "Dry-run receipt request_sha256 mismatch (receipt parameters were modified after dry-run). "
                "Re-run --dry-run before executing.",
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
    mutates_enabled = is_execute_mutates_enabled()
    mutates_cfg_line = (
        "ENABLED (execute_mutates = true)"
        if mutates_enabled
        else "DISABLED (execute_mutates = false — set execute_mutates = true in config/assistant_config before --execute)"
    )
    financial_line = ""
    if receipt.get("is_financial_transaction"):
        fin_limits, _ = read_financial_limits()
        has_active_cap = any(float(v or 0) > 0 for v in fin_limits.values())
        cap_note = (
            "; within configured upper limits in config/financial_limits"
            if has_active_cap
            else ""
        )
        financial_line = (
            f"Financial Txn : YES (explicit monetary/spend/billing impact disclosure verified{cap_note})\n"
        )
    return (
        "======================================================================\n"
        "GOOGLE ADS API MUTATION & CONSEQUENCE VERIFICATION CARD\n"
        "======================================================================\n"
        f"Customer ID   : {receipt.get('customer_id', 'Unknown')}\n"
        f"Operation     : {receipt.get('operation_summary', 'Unknown')}\n"
        f"{financial_line}"
        f"Mutates Config: {mutates_cfg_line}\n"
        f"Dry-Run Status: PASSED (validate_only=True verified at {receipt.get('timestamp_iso', '')})\n"
        f"Request SHA256: {receipt.get('request_sha256', 'N/A')}\n"
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
    if len(sys.argv) >= 3 and sys.argv[1] == "--_exec-target":
        target_script = sys.argv[2]
        target_args = sys.argv[3:]
        trace_file = os.environ.get(_TRACE_ENV_VAR, "")
        _run_target_script_with_interception(target_script, target_args, trace_file)
        return

    parser = argparse.ArgumentParser(
        description="Run Google Ads API mutations with mandatory validate_only=True dry-run, HITL consequence verification, and audit logging."
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

    args, unknown_args = parser.parse_known_args()
    script_path = os.path.abspath(args.script)

    if not os.path.isfile(script_path):
        print(f"Error: Mutation script not found at '{script_path}'", file=sys.stderr)
        sys.exit(1)

    script_sha256 = compute_file_sha256(script_path)
    extra_args = (
        shlex.split(args.script_args) if args.script_args else []
    ) + unknown_args

    if args.dry_run:
        if not args.customer_id or not args.operation or not args.consequences:
            print(
                "Error: --dry-run requires --customer-id, --operation, and --consequences.",
                file=sys.stderr,
            )
            sys.exit(1)

        consequence_list = [
            item.strip()
            for item in args.consequences.split(";")
            if item.strip()
        ]
        script_args = ["--dry-run"]
        if args.customer_id and "--customer-id" not in extra_args:
            script_args.extend(["--customer-id", args.customer_id])
        script_args.extend(extra_args)

        dry_run_output = "Dry-run validated."
        sent_at_iso = datetime.now(timezone.utc).isoformat()
        received_at_iso = sent_at_iso
        duration_ms = 0.0
        captured_calls: List[Dict[str, Any]] = []

        # Pre-flight Deletion Prohibition check before executing target script
        pre_ok, pre_del_err, _ = check_prohibited_deletion_mutation(
            operation_summary=args.operation,
            after_state=args.after or args.operation,
            script_path=script_path,
        )
        if not pre_ok and pre_del_err:
            _remove_stale_receipts()
            append_mutation_audit_log(
                phase="DRY_RUN",
                status="BLOCKED_PROHIBITED_DELETION",
                customer_id=args.customer_id,
                operation_summary=args.operation,
                before_state=args.before,
                after_state=args.after or args.operation,
                consequences=consequence_list,
                reversibility=args.reversibility,
                script_path=script_path,
                script_sha256=script_sha256,
                validate_only=True,
                request_sent_at_iso=sent_at_iso,
                response_received_at_iso=received_at_iso,
                duration_ms=0.0,
                exit_code=2,
                stdout="",
                stderr=pre_del_err,
                command=[sys.executable, script_path, *script_args],
                rpc_calls=[],
            )
            print(pre_del_err, file=sys.stderr)
            sys.exit(2)

        if not args.record_only:
            result, sent_at_iso, received_at_iso, duration_ms, captured_calls = (
                _execute_script_subprocess(
                    script_path,
                    script_args,
                    dry_run_mode=True,
                )
            )
            if result.returncode != 0:
                if any(
                    c.get("status") == "BLOCKED_PROHIBITED_DELETION"
                    for c in captured_calls
                ):
                    dry_fail_status = "BLOCKED_PROHIBITED_DELETION"
                    _remove_stale_receipts()
                elif any(
                    c.get("status") == "BLOCKED_FINANCIAL_LIMIT_EXCEEDED"
                    for c in captured_calls
                ):
                    dry_fail_status = "BLOCKED_FINANCIAL_LIMIT_EXCEEDED"
                    _remove_stale_receipts()
                elif any(
                    c.get("status") == "BLOCKED_MISSING_VALIDATE_ONLY"
                    for c in captured_calls
                ):
                    dry_fail_status = "BLOCKED_MISSING_VALIDATE_ONLY"
                else:
                    dry_fail_status = "DRY_RUN_FAILED"
                effective_dry_exit = (
                    2
                    if dry_fail_status
                    in ("BLOCKED_FINANCIAL_LIMIT_EXCEEDED", "BLOCKED_PROHIBITED_DELETION")
                    else result.returncode
                )
                append_mutation_audit_log(
                    phase="DRY_RUN",
                    status=dry_fail_status,
                    customer_id=args.customer_id,
                    operation_summary=args.operation,
                    before_state=args.before,
                    after_state=args.after or args.operation,
                    consequences=consequence_list,
                    reversibility=args.reversibility,
                    script_path=script_path,
                    script_sha256=script_sha256,
                    validate_only=True,
                    request_sent_at_iso=sent_at_iso,
                    response_received_at_iso=received_at_iso,
                    duration_ms=duration_ms,
                    exit_code=effective_dry_exit,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    command=[sys.executable, script_path, *script_args],
                    rpc_calls=captured_calls,
                )
                print(
                    f"validate_only=True Dry-Run FAILED (exit code {effective_dry_exit}):\n"
                    f"{result.stdout}\n{result.stderr}",
                    file=sys.stderr,
                )
                sys.exit(effective_dry_exit)
            dry_run_output = (result.stdout + "\n" + result.stderr).strip()

        try:
            receipt = write_dry_run_receipt(
                customer_id=args.customer_id,
                operation_summary=args.operation,
                before_state=args.before,
                after_state=args.after or args.operation,
                consequences=consequence_list,
                reversibility=args.reversibility,
                script_path=script_path,
                dry_run_output=dry_run_output,
                request_sent_at_iso=sent_at_iso,
                response_received_at_iso=received_at_iso,
                rpc_calls=captured_calls,
            )
        except ValueError as exc:
            err_msg = (
                str(exc)
                if str(exc).startswith("BLOCKED")
                else f"BLOCKED: {exc}"
            )
            if "BLOCKED BY DELETION PROHIBITION" in str(exc):
                audit_status = "BLOCKED_PROHIBITED_DELETION"
            elif "BLOCKED BY FINANCIAL UPPER LIMIT" in str(exc):
                audit_status = "BLOCKED_FINANCIAL_LIMIT_EXCEEDED"
            else:
                audit_status = "BLOCKED_FINANCIAL_CONSEQUENCE_MISSING"
            append_mutation_audit_log(
                phase="DRY_RUN",
                status=audit_status,
                customer_id=args.customer_id,
                operation_summary=args.operation,
                before_state=args.before,
                after_state=args.after or args.operation,
                consequences=consequence_list,
                reversibility=args.reversibility,
                script_path=script_path,
                script_sha256=script_sha256,
                validate_only=True,
                request_sent_at_iso=sent_at_iso,
                response_received_at_iso=received_at_iso,
                duration_ms=duration_ms,
                exit_code=2,
                stdout=dry_run_output,
                stderr=err_msg,
                command=[sys.executable, script_path, *script_args],
                rpc_calls=captured_calls,
            )
            print(err_msg, file=sys.stderr)
            sys.exit(2)

        append_mutation_audit_log(
            phase="DRY_RUN",
            status="DRY_RUN_PASSED",
            customer_id=args.customer_id,
            operation_summary=args.operation,
            before_state=args.before,
            after_state=args.after or args.operation,
            consequences=consequence_list,
            reversibility=args.reversibility,
            script_path=script_path,
            script_sha256=script_sha256,
            validate_only=True,
            request_sent_at_iso=sent_at_iso,
            response_received_at_iso=received_at_iso,
            duration_ms=duration_ms,
            exit_code=0,
            stdout=dry_run_output,
            stderr="",
            command=[sys.executable, script_path, *script_args],
            rpc_calls=captured_calls,
            receipt=receipt,
        )
        print(format_verification_card(receipt))
        return

    # Phase 2: --execute
    if not is_execute_mutates_enabled():
        blocked_iso = datetime.now(timezone.utc).isoformat()
        err_msg = (
            "BLOCKED: Mutate support is disabled by configuration "
            "(execute_mutates = false in config/assistant_config). "
            "Set 'execute_mutates = true' in config/assistant_config to enable live mutations."
        )
        _, _, existing_receipt = load_and_verify_receipt(script_path=script_path)
        cid_blocked = args.customer_id or str(existing_receipt.get("customer_id", ""))
        op_blocked = str(args.operation or existing_receipt.get("operation_summary", ""))
        before_blocked = str(existing_receipt.get("before_state", args.before))
        after_blocked = str(existing_receipt.get("after_state", args.after or op_blocked))
        rev_blocked = str(existing_receipt.get("reversibility", args.reversibility))
        conseq_blocked = [
            str(c) for c in existing_receipt.get("consequences", []) if str(c).strip()
        ]
        append_mutation_audit_log(
            phase="EXECUTE",
            status="BLOCKED_MUTATES_DISABLED",
            customer_id=cid_blocked,
            operation_summary=op_blocked,
            before_state=before_blocked,
            after_state=after_blocked,
            consequences=conseq_blocked,
            reversibility=rev_blocked,
            script_path=script_path,
            script_sha256=script_sha256,
            validate_only=False,
            request_sent_at_iso=blocked_iso,
            response_received_at_iso=blocked_iso,
            duration_ms=0.0,
            exit_code=2,
            stdout="",
            stderr=err_msg,
            command=[sys.executable, script_path, "--execute", *extra_args],
            rpc_calls=[],
            receipt=existing_receipt if existing_receipt else None,
        )
        print(err_msg, file=sys.stderr)
        sys.exit(2)

    ok, message, receipt = load_and_verify_receipt(script_path=script_path)
    if not ok:
        err_out = (
            message
            if message.startswith("BLOCKED")
            else f"BLOCKED: {message}"
        )
        if (
            "BLOCKED BY DELETION PROHIBITION" in message
            or "BLOCKED BY FINANCIAL UPPER LIMIT" in message
        ):
            blocked_iso = datetime.now(timezone.utc).isoformat()
            cid_blocked = args.customer_id or str(receipt.get("customer_id", ""))
            op_blocked = str(args.operation or receipt.get("operation_summary", ""))
            before_blocked = str(receipt.get("before_state", args.before))
            after_blocked = str(receipt.get("after_state", args.after or op_blocked))
            rev_blocked = str(receipt.get("reversibility", args.reversibility))
            conseq_blocked = [
                str(c) for c in receipt.get("consequences", []) if str(c).strip()
            ]
            audit_block_status = (
                "BLOCKED_PROHIBITED_DELETION"
                if "BLOCKED BY DELETION PROHIBITION" in message
                else "BLOCKED_FINANCIAL_LIMIT_EXCEEDED"
            )
            append_mutation_audit_log(
                phase="EXECUTE",
                status=audit_block_status,
                customer_id=cid_blocked,
                operation_summary=op_blocked,
                before_state=before_blocked,
                after_state=after_blocked,
                consequences=conseq_blocked,
                reversibility=rev_blocked,
                script_path=script_path,
                script_sha256=script_sha256,
                validate_only=False,
                request_sent_at_iso=blocked_iso,
                response_received_at_iso=blocked_iso,
                duration_ms=0.0,
                exit_code=2,
                stdout="",
                stderr=err_out,
                command=[sys.executable, script_path, "--execute", *extra_args],
                rpc_calls=receipt.get("dry_run_rpc_calls")
                if isinstance(receipt.get("dry_run_rpc_calls"), list)
                else [],
                receipt=receipt if receipt else None,
            )
        print(err_out, file=sys.stderr)
        sys.exit(2)

    # Record exact timestamp when the user approved the mutation and execution commenced
    user_approved_at_iso = datetime.now(timezone.utc).isoformat()

    cid = args.customer_id or str(receipt.get("customer_id", ""))
    script_args = ["--execute"]
    if cid and "--customer-id" not in extra_args:
        script_args.extend(["--customer-id", cid])
    script_args.extend(extra_args)

    expected_rpc_hashes = [
        str(h).strip()
        for h in receipt.get("request_sha256_list", [])
        if str(h).strip()
    ]

    result, sent_at_iso, received_at_iso, duration_ms, captured_calls = (
        _execute_script_subprocess(
            script_path,
            script_args,
            expected_request_hashes=expected_rpc_hashes if expected_rpc_hashes else None,
            enforce_request_hash=bool(expected_rpc_hashes),
        )
    )

    consequences_from_receipt = [
        str(c) for c in receipt.get("consequences", []) if str(c).strip()
    ]
    operation_summary = str(args.operation or receipt.get("operation_summary", ""))
    before_state = str(receipt.get("before_state", args.before))
    after_state = str(receipt.get("after_state", args.after or operation_summary))
    reversibility = str(receipt.get("reversibility", args.reversibility))

    blocked_by_deletion = any(
        c.get("status") == "BLOCKED_PROHIBITED_DELETION" for c in captured_calls
    )
    blocked_by_fin_limit = any(
        c.get("status") == "BLOCKED_FINANCIAL_LIMIT_EXCEEDED" for c in captured_calls
    )
    blocked_by_sha_mismatch = any(
        c.get("status") == "BLOCKED_SHA256_MISMATCH" for c in captured_calls
    )
    actual_rpc_hashes = [
        str(c.get("request_sha256", "")).strip()
        for c in captured_calls
        if str(c.get("request_sha256", "")).strip()
    ]
    missing_expected_calls = (
        result.returncode == 0
        and bool(expected_rpc_hashes)
        and actual_rpc_hashes != expected_rpc_hashes
    )

    if (
        result.returncode != 0
        or blocked_by_deletion
        or blocked_by_fin_limit
        or blocked_by_sha_mismatch
        or missing_expected_calls
    ):
        if blocked_by_deletion:
            failure_status = "BLOCKED_PROHIBITED_DELETION"
        elif blocked_by_fin_limit:
            failure_status = "BLOCKED_FINANCIAL_LIMIT_EXCEEDED"
        elif blocked_by_sha_mismatch or missing_expected_calls:
            failure_status = "BLOCKED_SHA256_MISMATCH"
        else:
            failure_status = "FAILED"
        effective_exit_code = (
            2
            if (blocked_by_deletion or blocked_by_fin_limit)
            else (result.returncode if result.returncode != 0 else 2)
        )
        stderr_out = result.stderr
        if missing_expected_calls and not stderr_out:
            stderr_out = (
                f"BLOCKED: Expected {len(expected_rpc_hashes)} verified mutate RPC call(s) "
                f"matching dry-run SHA-256 {expected_rpc_hashes}, but observed {actual_rpc_hashes}."
            )
        append_mutation_audit_log(
            phase="EXECUTE",
            status=failure_status,
            customer_id=cid,
            operation_summary=operation_summary,
            before_state=before_state,
            after_state=after_state,
            consequences=consequences_from_receipt,
            reversibility=reversibility,
            script_path=script_path,
            script_sha256=script_sha256,
            validate_only=False,
            request_sent_at_iso=sent_at_iso,
            response_received_at_iso=received_at_iso,
            duration_ms=duration_ms,
            exit_code=effective_exit_code,
            stdout=result.stdout,
            stderr=stderr_out,
            command=[sys.executable, script_path, *script_args],
            rpc_calls=captured_calls,
            receipt=receipt,
            user_approved_at_iso=user_approved_at_iso,
        )
        print(
            f"Live mutation {failure_status} (exit code {effective_exit_code}):\n"
            f"{result.stdout}\n{stderr_out}",
            file=sys.stderr,
        )
        sys.exit(effective_exit_code)

    audit_entry = append_mutation_audit_log(
        phase="EXECUTE",
        status="SUCCESS",
        customer_id=cid,
        operation_summary=operation_summary,
        before_state=before_state,
        after_state=after_state,
        consequences=consequences_from_receipt,
        reversibility=reversibility,
        script_path=script_path,
        script_sha256=script_sha256,
        validate_only=False,
        request_sent_at_iso=sent_at_iso,
        response_received_at_iso=received_at_iso,
        duration_ms=duration_ms,
        exit_code=0,
        stdout=result.stdout,
        stderr=result.stderr,
        command=[sys.executable, script_path, *script_args],
        rpc_calls=captured_calls,
        receipt=receipt,
        user_approved_at_iso=user_approved_at_iso,
    )
    mark_receipt_executed(
        user_approved_at_iso=user_approved_at_iso,
        request_sent_at_iso=audit_entry["request"]["sent_at_iso"],
        response_received_at_iso=audit_entry["response"]["received_at_iso"],
        audit_id=audit_entry["audit_id"],
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)


if __name__ == "__main__":
    main()

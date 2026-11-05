#!/usr/bin/env python3
"""Helper utility to view, configure, and reset Google Ads API financial transaction upper limits."""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple, Union


FINANCIAL_LIMITS_FILENAME = "financial_limits"

# Canonical specification of all financial transaction types, their Google Ads API
# services, API request fields, required numeric format, and monetary unit.
FINANCIAL_LIMIT_SPECS: Dict[str, Dict[str, Any]] = {
    "all_micros_transactions": {
        "category": "1. Global Fallback Upper Limits (Optional)",
        "services": [
            "All Google Ads API services using micros-denominated monetary fields"
        ],
        "api_fields": ["Any *_micros monetary field when its specific limit below is set to 0"],
        "api_format": "int64",
        "monetary_unit": "micros",
        "unit_description": "int64, 1,000,000 micros = 1.00 unit of account currency",
        "default": 0,
    },
    "all_currency_unit_transactions": {
        "category": "1. Global Fallback Upper Limits (Optional)",
        "services": [
            "All Google Ads API services using standard currency unit fields"
        ],
        "api_fields": [
            "Any standard currency unit field when its specific limit below is set to 0.0"
        ],
        "api_format": "double",
        "monetary_unit": "currency_units",
        "unit_description": "double/float, 1.0 = 1.00 unit of account currency, NOT micros",
        "default": 0.0,
    },
    "campaign_budget_amount_micros": {
        "category": "2. Budgets, Account Spending Limits & Guaranteed Reservations",
        "services": [
            "CampaignBudgetService (mutate_campaign_budgets)",
            "GoogleAdsService (mutate)",
            "ExperimentService (graduate_experiment)",
        ],
        "api_fields": ["amount_micros", "recommended_budget_amount_micros"],
        "api_format": "int64",
        "monetary_unit": "micros",
        "unit_description": "int64, 1,000,000 micros = 1.00 unit of account currency; e.g., 100000000 = 100.00/day",
        "default": 0,
    },
    "campaign_budget_total_amount_micros": {
        "category": "2. Budgets, Account Spending Limits & Guaranteed Reservations",
        "services": [
            "CampaignBudgetService (mutate_campaign_budgets)",
            "GoogleAdsService (mutate)",
        ],
        "api_fields": ["total_amount_micros"],
        "api_format": "int64",
        "monetary_unit": "micros",
        "unit_description": "int64, 1,000,000 micros = 1.00 unit of account currency; e.g., 1000000000 = 1,000.00 lifetime total",
        "default": 0,
    },
    "account_budget_spending_limit_micros": {
        "category": "2. Budgets, Account Spending Limits & Guaranteed Reservations",
        "services": [
            "AccountBudgetProposalService (mutate_account_budget_proposal)"
        ],
        "api_fields": [
            "proposed_spending_limit_micros",
            "approved_spending_limit_micros",
            "spending_limit_micros",
        ],
        "api_format": "int64",
        "monetary_unit": "micros",
        "unit_description": "int64, 1,000,000 micros = 1.00 unit of account currency; e.g., 25000000000 = 25,000.00 account limit",
        "default": 0,
    },
    "reservation_booking_max_budget_micros": {
        "category": "2. Budgets, Account Spending Limits & Guaranteed Reservations",
        "services": ["ReservationService (book_campaigns, quote_campaigns)"],
        "api_fields": ["max_budget_micros"],
        "api_format": "int64",
        "monetary_unit": "micros",
        "unit_description": "int64, 1,000,000 micros = 1.00 unit of account currency; e.g., 10000000000 = 10,000.00 reservation commitment",
        "default": 0,
    },
    "cpc_bid_micros": {
        "category": "3. Bidding & Bid Ceilings (Micros)",
        "services": [
            "AdGroupService (mutate_ad_groups)",
            "AdGroupCriterionService (mutate_ad_group_criteria)",
            "CampaignCriterionService (mutate_campaign_criteria)",
            "GoogleAdsService (mutate)",
        ],
        "api_fields": ["cpc_bid_micros", "target_cpc_micros"],
        "api_format": "int64",
        "monetary_unit": "micros",
        "unit_description": "int64, 1,000,000 micros = 1.00 unit of account currency; e.g., 10000000 = 10.00 max CPC",
        "default": 0,
    },
    "cpm_bid_micros": {
        "category": "3. Bidding & Bid Ceilings (Micros)",
        "services": [
            "AdGroupService",
            "AdGroupCriterionService",
            "BiddingStrategyService",
            "CampaignService",
            "GoogleAdsService",
        ],
        "api_fields": ["cpm_bid_micros", "target_cpm_micros", "fixed_cpm_micros"],
        "api_format": "int64",
        "monetary_unit": "micros",
        "unit_description": "int64, 1,000,000 micros = 1.00 unit of account currency per 1,000 impressions; e.g., 20000000 = 20.00 CPM",
        "default": 0,
    },
    "cpv_bid_micros": {
        "category": "3. Bidding & Bid Ceilings (Micros)",
        "services": [
            "AdGroupService",
            "AdGroupCriterionService",
            "CampaignService",
            "GoogleAdsService",
        ],
        "api_fields": ["cpv_bid_micros", "target_cpv_micros"],
        "api_format": "int64",
        "monetary_unit": "micros",
        "unit_description": "int64, 1,000,000 micros = 1.00 unit of account currency; e.g., 2000000 = 2.00 CPV",
        "default": 0,
    },
    "target_cpa_micros": {
        "category": "3. Bidding & Bid Ceilings (Micros)",
        "services": [
            "BiddingStrategyService (mutate_bidding_strategies)",
            "CampaignService (mutate_campaigns)",
            "AdGroupService (mutate_ad_groups)",
            "GoogleAdsService (mutate)",
        ],
        "api_fields": [
            "target_cpa_micros",
            "manual_cpa_bid_micros",
            "target_cpa_bid_micros",
        ],
        "api_format": "int64",
        "monetary_unit": "micros",
        "unit_description": "int64, 1,000,000 micros = 1.00 unit of account currency; e.g., 50000000 = 50.00 Target CPA",
        "default": 0,
    },
    "cpc_bid_ceiling_micros": {
        "category": "3. Bidding & Bid Ceilings (Micros)",
        "services": [
            "BiddingStrategyService",
            "CampaignService",
            "GoogleAdsService (TargetCpa, TargetRoas, TargetSpend, TargetImpressionShare, MaximizeConversions, MaximizeConversionValue, PercentCpc)",
        ],
        "api_fields": ["cpc_bid_ceiling_micros", "cpc_bid_floor_micros"],
        "api_format": "int64",
        "monetary_unit": "micros",
        "unit_description": "int64, 1,000,000 micros = 1.00 unit of account currency; e.g., 15000000 = 15.00 CPC bid ceiling",
        "default": 0,
    },
    "target_spend_micros": {
        "category": "3. Bidding & Bid Ceilings (Micros)",
        "services": [
            "BiddingStrategyService",
            "CampaignService",
            "GoogleAdsService (TargetSpend)",
        ],
        "api_fields": ["target_spend_micros"],
        "api_format": "int64",
        "monetary_unit": "micros",
        "unit_description": "int64, 1,000,000 micros = 1.00 unit of account currency; e.g., 100000000 = 100.00 target spend",
        "default": 0,
    },
    "percent_cpc_bid_micros": {
        "category": "4. Percentage-Based Bidding (Micros Proportion)",
        "services": [
            "AdGroupService",
            "AdGroupCriterionService",
            "CampaignService",
            "GoogleAdsService (PercentCpc, TargetImpressionShare)",
        ],
        "api_fields": ["percent_cpc_bid_micros", "location_fraction_micros"],
        "api_format": "int64",
        "monetary_unit": "micros_proportion",
        "unit_description": "int64, 1,000,000 = 100%; e.g., 250000 = 25% of item/hotel price",
        "default": 0,
    },
    "conversion_upload_value": {
        "category": "5. Conversions, Restatements & Value Rules (Standard Currency Units)",
        "services": [
            "ConversionUploadService (upload_click_conversions, upload_call_conversions)"
        ],
        "api_fields": ["conversion_value"],
        "api_format": "double",
        "monetary_unit": "currency_units",
        "unit_description": "double/float, standard currency units, NOT micros; e.g., 500.0 = 500.00 currency units",
        "default": 0.0,
    },
    "conversion_adjustment_restatement_value": {
        "category": "5. Conversions, Restatements & Value Rules (Standard Currency Units)",
        "services": [
            "ConversionAdjustmentUploadService (upload_conversion_adjustments)"
        ],
        "api_fields": ["adjusted_value", "restatement_value.adjusted_value"],
        "api_format": "double",
        "monetary_unit": "currency_units",
        "unit_description": "double/float, standard currency units, NOT micros; e.g., 500.0 = 500.00 currency units",
        "default": 0.0,
    },
    "conversion_action_default_value": {
        "category": "5. Conversions, Restatements & Value Rules (Standard Currency Units)",
        "services": [
            "ConversionActionService (mutate_conversion_actions)",
            "GoogleAdsService (mutate)",
        ],
        "api_fields": ["default_value", "value_settings.default_value"],
        "api_format": "double",
        "monetary_unit": "currency_units",
        "unit_description": "double/float, standard currency units, NOT micros; e.g., 100.0 = 100.00 currency units",
        "default": 0.0,
    },
    "conversion_value_rule_action_value": {
        "category": "5. Conversions, Restatements & Value Rules (Standard Currency Units)",
        "services": [
            "ConversionValueRuleService (mutate_conversion_value_rules)",
            "GoogleAdsService (mutate)",
        ],
        "api_fields": ["value", "action.value"],
        "api_format": "double",
        "monetary_unit": "currency_units",
        "unit_description": "for ADD/SET operations (or decimal_ratio for MULTIPLY operation) (double/float, NOT micros; e.g., 100.0)",
        "default": 0.0,
    },
    "target_roas": {
        "category": "6. ROAS Targets, Bid Modifiers & Seasonality Multipliers (Decimal Ratio)",
        "services": [
            "BiddingStrategyService",
            "CampaignService",
            "AdGroupService",
            "GoogleAdsService (TargetRoas, MaximizeConversionValue)",
        ],
        "api_fields": ["target_roas"],
        "api_format": "double",
        "monetary_unit": "decimal_ratio",
        "unit_description": "double/float, conversion value per 1.00 currency unit spent; e.g., 5.0 = 500% ROAS",
        "default": 0.0,
    },
    "bid_modifier": {
        "category": "6. ROAS Targets, Bid Modifiers & Seasonality Multipliers (Decimal Ratio)",
        "services": [
            "CampaignBidModifierService",
            "AdGroupBidModifierService",
            "CampaignCriterionService",
            "AdGroupCriterionService",
            "GoogleAdsService",
        ],
        "api_format": "double",
        "api_fields": ["bid_modifier"],
        "monetary_unit": "decimal_ratio",
        "unit_description": "double/float, bid multiplier; e.g., 2.0 = +100% bid adjustment",
        "default": 0.0,
    },
    "seasonality_conversion_rate_modifier": {
        "category": "6. ROAS Targets, Bid Modifiers & Seasonality Multipliers (Decimal Ratio)",
        "services": [
            "BiddingSeasonalityAdjustmentService (mutate_bidding_seasonality_adjustments)",
            "GoogleAdsService (mutate)",
        ],
        "api_fields": ["conversion_rate_modifier", "seasonality_modifier"],
        "api_format": "double",
        "monetary_unit": "decimal_ratio",
        "unit_description": "double/float, conversion rate multiplier; e.g., 1.5 = +50% seasonality adjustment",
        "default": 0.0,
    },
}

# Friendly aliases mapping API field names and service names to canonical config keys.
LIMIT_KEY_ALIASES: Dict[str, str] = {
    "amount_micros": "campaign_budget_amount_micros",
    "recommended_budget_amount_micros": "campaign_budget_amount_micros",
    "campaign_budget": "campaign_budget_amount_micros",
    "campaignbudgetservice": "campaign_budget_amount_micros",
    "total_amount_micros": "campaign_budget_total_amount_micros",
    "proposed_spending_limit_micros": "account_budget_spending_limit_micros",
    "account_budget_proposed_spending_limit_micros": "account_budget_spending_limit_micros",
    "approved_spending_limit_micros": "account_budget_spending_limit_micros",
    "spending_limit_micros": "account_budget_spending_limit_micros",
    "account_budget_proposal": "account_budget_spending_limit_micros",
    "accountbudgetproposalservice": "account_budget_spending_limit_micros",
    "max_budget_micros": "reservation_booking_max_budget_micros",
    "book_campaigns": "reservation_booking_max_budget_micros",
    "reservationservice": "reservation_booking_max_budget_micros",
    "target_cpc_micros": "cpc_bid_micros",
    "target_cpm_micros": "cpm_bid_micros",
    "fixed_cpm_micros": "cpm_bid_micros",
    "target_cpv_micros": "cpv_bid_micros",
    "manual_cpa_bid_micros": "target_cpa_micros",
    "target_cpa_bid_micros": "target_cpa_micros",
    "cpc_bid_floor_micros": "cpc_bid_ceiling_micros",
    "location_fraction_micros": "percent_cpc_bid_micros",
    "conversion_value": "conversion_upload_value",
    "click_conversion_value": "conversion_upload_value",
    "call_conversion_value": "conversion_upload_value",
    "conversionuploadservice": "conversion_upload_value",
    "adjusted_value": "conversion_adjustment_restatement_value",
    "restatement_value": "conversion_adjustment_restatement_value",
    "conversionadjustmentuploadservice": "conversion_adjustment_restatement_value",
    "default_value": "conversion_action_default_value",
    "conversionactionservice": "conversion_action_default_value",
    "action.value": "conversion_value_rule_action_value",
    "conversion_value_rule": "conversion_value_rule_action_value",
    "conversionvalueruleservice": "conversion_value_rule_action_value",
    "conversion_rate_modifier": "seasonality_conversion_rate_modifier",
    "seasonality_modifier": "seasonality_conversion_rate_modifier",
    "biddingseasonalityadjustmentservice": "seasonality_conversion_rate_modifier",
}


def resolve_limit_key(raw_key: str) -> str:
    """Resolves a key, CLI flag name, API field name, or service alias to a canonical key."""
    cleaned = raw_key.strip().lower().replace("-", "_")
    if cleaned in FINANCIAL_LIMIT_SPECS:
        return cleaned
    if cleaned in LIMIT_KEY_ALIASES:
        return LIMIT_KEY_ALIASES[cleaned]
    raise ValueError(
        f"Unknown financial transaction type '{raw_key}'. "
        f"Valid transaction types are: {', '.join(FINANCIAL_LIMIT_SPECS.keys())}"
    )


def parse_and_validate_limit_amount(
    key: str, raw_value: Union[str, int, float]
) -> Union[int, float]:
    """Validates and converts a limit amount into the exact numeric format required by the API."""
    canonical_key = resolve_limit_key(key)
    spec = FINANCIAL_LIMIT_SPECS[canonical_key]
    api_format = spec["api_format"]
    monetary_unit = spec["monetary_unit"]
    unit_desc = spec["unit_description"]

    if isinstance(raw_value, bool):
        raise ValueError(
            f"Invalid value '{raw_value}' for '{canonical_key}'. Expected {api_format} ({monetary_unit})."
        )

    raw_str = str(raw_value).strip().replace(",", "").replace("_", "")
    if not raw_str:
        raise ValueError(
            f"Empty value provided for '{canonical_key}'. Expected {api_format} ({monetary_unit})."
        )

    if api_format == "int64":
        # Reject non-integer decimal numbers for micros fields so users do not
        # accidentally enter standard currency decimals where the API requires int64 micros.
        if isinstance(raw_value, float):
            if not raw_value.is_integer():
                raise ValueError(
                    f"Invalid amount '{raw_value}' for '{canonical_key}': "
                    f"Google Ads API requires an int64 integer in '{monetary_unit}' "
                    f"({unit_desc}). Do not pass decimal fractions for micros fields."
                )
            val_int = int(raw_value)
        else:
            if "." in raw_str:
                raise ValueError(
                    f"Invalid amount '{raw_value}' for '{canonical_key}': "
                    f"Google Ads API requires an int64 integer in '{monetary_unit}' "
                    f"({unit_desc}). Example: 50000000 for 50.00 currency units."
                )
            try:
                val_int = int(raw_str)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid amount '{raw_value}' for '{canonical_key}': "
                    f"must be an int64 integer in '{monetary_unit}' ({unit_desc})."
                ) from exc

        if val_int < 0:
            raise ValueError(
                f"Invalid amount '{val_int}' for '{canonical_key}': upper limit must be >= 0 "
                f"(0 = no upper limit)."
            )
        return val_int

    # double / float format
    try:
        val_float = float(raw_str)
    except ValueError as exc:
        raise ValueError(
            f"Invalid amount '{raw_value}' for '{canonical_key}': "
            f"must be a numeric value (double/float) in '{monetary_unit}' ({unit_desc})."
        ) from exc

    if val_float < 0.0:
        raise ValueError(
            f"Invalid amount '{val_float}' for '{canonical_key}': upper limit must be >= 0.0 "
            f"(0.0 = no upper limit)."
        )
    return val_float


def get_financial_limits_paths(
    config_dir: Optional[str] = None,
    config_file: Optional[str] = None,
) -> List[str]:
    """Returns candidate paths for reading/writing config/financial_limits."""
    if config_file:
        return [os.path.abspath(config_file)]

    env_file = os.environ.get("GOOGLE_ADS_FINANCIAL_LIMITS_FILE", "").strip()
    if env_file:
        return [os.path.abspath(env_file)]

    if config_dir:
        return [os.path.join(os.path.abspath(config_dir), FINANCIAL_LIMITS_FILENAME)]

    this_dir = os.path.dirname(os.path.abspath(__file__))
    candidates: List[str] = [
        os.path.abspath(os.path.join("config", FINANCIAL_LIMITS_FILENAME)),
    ]

    # Resolve relative to either skills/execute-mutation/scripts/, config/, or repo root
    if os.path.basename(this_dir) == "scripts":
        plugin_root = os.path.abspath(os.path.join(this_dir, "../../.."))
        candidates.append(
            os.path.join(plugin_root, "config", FINANCIAL_LIMITS_FILENAME)
        )
    elif os.path.basename(this_dir) == "config":
        candidates.append(os.path.join(this_dir, FINANCIAL_LIMITS_FILENAME))
    else:
        candidates.append(
            os.path.join(
                this_dir,
                "plugins",
                "google-ads-api-developer-assistant",
                "config",
                FINANCIAL_LIMITS_FILENAME,
            )
        )

    candidates.extend([
        os.path.expanduser(
            f"~/.gemini/config/plugins/google-ads-api-developer-assistant/config/{FINANCIAL_LIMITS_FILENAME}"
        ),
        os.path.expanduser(
            f"~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/config/{FINANCIAL_LIMITS_FILENAME}"
        ),
    ])

    deduped: List[str] = []
    for p in candidates:
        norm = os.path.normpath(p)
        if norm not in deduped:
            deduped.append(norm)
    return deduped


def parse_financial_limits(raw_text: str) -> Dict[str, Union[int, float]]:
    """Parses TOML or key=value text from config/financial_limits."""
    limits: Dict[str, Union[int, float]] = {
        k: spec["default"] for k, spec in FINANCIAL_LIMIT_SPECS.items()
    }
    if not raw_text or not raw_text.strip():
        return limits

    parsed_dict: Dict[str, Any] = {}
    try:
        import tomllib  # type: ignore

        loaded = tomllib.loads(raw_text)
        if isinstance(loaded, dict):
            parsed_dict = loaded
    except Exception:
        pass

    if not parsed_dict:
        for raw_line in raw_text.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line or "=" not in line:
                continue
            k_part, v_part = line.split("=", 1)
            k_clean = k_part.strip()
            v_clean = v_part.strip().strip("'\"")
            parsed_dict[k_clean] = v_clean

    for raw_k, raw_v in parsed_dict.items():
        try:
            canonical_k = resolve_limit_key(str(raw_k))
            spec = FINANCIAL_LIMIT_SPECS[canonical_k]
            if spec["api_format"] == "int64":
                limits[canonical_k] = int(float(str(raw_v).replace("_", "").strip()))
            else:
                limits[canonical_k] = float(str(raw_v).replace("_", "").strip())
        except Exception:
            continue

    return limits


def read_financial_limits(
    config_dir: Optional[str] = None,
    config_file: Optional[str] = None,
) -> Tuple[Dict[str, Union[int, float]], Optional[str]]:
    """Reads the active financial_limits configuration file and returns (limits, active_path)."""
    defaults: Dict[str, Union[int, float]] = {
        k: spec["default"] for k, spec in FINANCIAL_LIMIT_SPECS.items()
    }
    for candidate in get_financial_limits_paths(
        config_dir=config_dir, config_file=config_file
    ):
        if os.path.isfile(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    return parse_financial_limits(f.read()), candidate
            except OSError:
                continue
    return defaults, None


def format_financial_limits_config(limits: Dict[str, Union[int, float]]) -> str:
    """Formats the complete config/financial_limits file with monetary unit documentation."""
    lines = [
        "# ==============================================================================",
        "# Google Ads API Financial Transaction Upper Limits Configuration",
        "# ==============================================================================",
        "# Specify upper limits for financial transactions across Google Ads API services.",
        "# All values MUST be in the exact numeric format required by the Google Ads API",
        "# call for each service (see the monetary unit noted for each entry below).",
        "#",
        "# If any mutation attempts a financial transaction exceeding a configured upper",
        "# limit (> 0), the mutate functions and HITL guard will return an error, inform",
        "# the user at the HITL step, and refuse to execute the command.",
        "#",
        "# Setting a value to 0 (or 0.0 for float fields) means NO upper limit is enforced",
        "# for that transaction type (unlimited).",
        "#",
        "# MONETARY & NUMERIC UNITS USED BY GOOGLE ADS API SERVICES:",
        "# 1. micros (int64):",
        "#    1 unit of account currency = 1,000,000 micros (e.g., 50000000 = 50.00 currency units).",
        "# 2. currency_units (double / float):",
        "#    Standard account/conversion currency units (NOT micros; e.g., 100.50 = 100.50 currency units).",
        "# 3. decimal_ratio (double / float):",
        "#    Decimal ratio or multiplier (e.g., 2.5 = 250% Target ROAS; 1.5 = +50% bid modifier).",
        "# 4. micros_proportion (int64):",
        "#    Proportion in micros where 1,000,000 = 100% (e.g., 200000 = 20% Percent CPC bid).",
        "# ==============================================================================",
        "",
    ]

    current_category = ""
    for key, spec in FINANCIAL_LIMIT_SPECS.items():
        cat = spec["category"]
        if cat != current_category:
            current_category = cat
            lines.append(f"# --- {cat} ---")
            lines.append("")

        services_str = ", ".join(spec["services"])
        fields_str = ", ".join(spec["api_fields"])
        service_label = "Service" if len(spec["services"]) == 1 else "Services"
        field_label = "API Field" if len(spec["api_fields"]) == 1 else "API Fields"
        monetary_unit = spec["monetary_unit"]
        unit_desc = spec["unit_description"]

        val = limits.get(key, spec["default"])
        if spec["api_format"] == "int64":
            formatted_val = str(int(val))
        else:
            formatted_val = str(float(val))

        lines.append(f"# {service_label}: {services_str}")
        lines.append(f"# {field_label}: {fields_str}")
        lines.append(f"# Monetary Unit: {monetary_unit} ({unit_desc})")
        lines.append(f"{key} = {formatted_val}")
        lines.append("")

    return "\n".join(lines)


def write_financial_limits(
    updates: Dict[str, Union[int, float]],
    config_dir: Optional[str] = None,
    config_file: Optional[str] = None,
    sync_global: bool = True,
) -> str:
    """Writes updated financial limits to config/financial_limits and returns the primary path."""
    current_limits, active_path = read_financial_limits(
        config_dir=config_dir, config_file=config_file
    )
    validated_updates: Dict[str, Union[int, float]] = {}
    for raw_k, raw_v in updates.items():
        canonical_k = resolve_limit_key(raw_k)
        validated_updates[canonical_k] = parse_and_validate_limit_amount(
            canonical_k, raw_v
        )

    current_limits.update(validated_updates)
    content = format_financial_limits_config(current_limits)

    target_paths: List[str] = []
    if config_file:
        target_paths.append(os.path.abspath(config_file))
    elif config_dir:
        target_paths.append(
            os.path.join(os.path.abspath(config_dir), FINANCIAL_LIMITS_FILENAME)
        )
    else:
        env_file = os.environ.get("GOOGLE_ADS_FINANCIAL_LIMITS_FILE", "").strip()
        if env_file:
            target_paths.append(os.path.abspath(env_file))
        else:
            this_dir = os.path.dirname(os.path.abspath(__file__))
            if os.path.basename(this_dir) == "scripts":
                plugin_root = os.path.abspath(os.path.join(this_dir, "../../.."))
                target_paths.append(
                    os.path.join(plugin_root, "config", FINANCIAL_LIMITS_FILENAME)
                )
            elif os.path.basename(this_dir) == "config":
                target_paths.append(os.path.join(this_dir, FINANCIAL_LIMITS_FILENAME))
            else:
                target_paths.append(
                    os.path.join(
                        this_dir,
                        "plugins",
                        "google-ads-api-developer-assistant",
                        "config",
                        FINANCIAL_LIMITS_FILENAME,
                    )
                )

            if active_path and os.path.normpath(active_path) not in [
                os.path.normpath(p) for p in target_paths
            ]:
                target_paths.insert(0, active_path)

            if sync_global:
                for global_dir in (
                    os.path.expanduser(
                        "~/.gemini/config/plugins/google-ads-api-developer-assistant/config"
                    ),
                    os.path.expanduser(
                        "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/config"
                    ),
                ):
                    if os.path.isdir(global_dir) or os.path.isdir(
                        os.path.dirname(global_dir)
                    ):
                        g_path = os.path.join(global_dir, FINANCIAL_LIMITS_FILENAME)
                        if os.path.normpath(g_path) not in [
                            os.path.normpath(p) for p in target_paths
                        ]:
                            target_paths.append(g_path)

    primary_written: Optional[str] = None
    for path in target_paths:
        try:
            parent_dir = os.path.dirname(os.path.abspath(path))
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            if sys.platform != "win32" and os.path.isfile(path):
                try:
                    os.chmod(path, 0o600)
                except OSError:
                    pass
            if primary_written is None:
                primary_written = path
        except OSError:
            continue

    if primary_written is None:
        raise OSError("Failed to write financial_limits configuration file.")
    return primary_written


def format_limit_display_value(key: str, val: Union[int, float]) -> str:
    """Formats a limit value with human-readable unit conversion for display."""
    spec = FINANCIAL_LIMIT_SPECS[key]
    unit = spec["monetary_unit"]
    if float(val) <= 0:
        return f"{val} (UNLIMITED)"
    if unit == "micros":
        currency_equiv = int(val) / 1_000_000.0
        return f"{int(val)} micros ({currency_equiv:,.2f} currency units)"
    if unit == "micros_proportion":
        pct = (int(val) / 1_000_000.0) * 100.0
        return f"{int(val)} micros_proportion ({pct:.2f}%)"
    if unit == "currency_units":
        return f"{float(val)} currency_units"
    if unit == "decimal_ratio":
        pct = float(val) * 100.0
        return f"{float(val)} decimal_ratio ({pct:.1f}%)"
    return str(val)


def format_limits_table(
    limits: Dict[str, Union[int, float]], active_path: Optional[str]
) -> str:
    """Formats all financial transaction limits as a readable report."""
    lines = [
        "==========================================================================================",
        "GOOGLE ADS API FINANCIAL TRANSACTION UPPER LIMITS",
        f"Configuration File: {active_path or 'config/financial_limits (defaults)'}",
        "==========================================================================================",
    ]
    current_cat = ""
    for key, spec in FINANCIAL_LIMIT_SPECS.items():
        if spec["category"] != current_cat:
            current_cat = spec["category"]
            lines.append(f"\n[{current_cat}]")
        val = limits.get(key, spec["default"])
        display_val = format_limit_display_value(key, val)
        lines.append(f"  • {key} = {display_val}")
        lines.append(
            f"      Monetary Unit : {spec['monetary_unit']} ({spec['api_format']}) — {spec['unit_description']}"
        )
        lines.append(f"      API Fields    : {', '.join(spec['api_fields'])}")
        lines.append(f"      API Services  : {', '.join(spec['services'])}")
    lines.append(
        "\n=========================================================================================="
    )
    return "\n".join(lines)


def run_interactive_prompt(
    config_dir: Optional[str] = None,
    config_file: Optional[str] = None,
) -> str:
    """Interactively prompts the user to set upper limits for financial transaction types."""
    current_limits, active_path = read_financial_limits(
        config_dir=config_dir, config_file=config_file
    )
    print(
        "Configure Google Ads API Financial Transaction Upper Limits\n"
        "Press Enter to keep the current value, or enter 0 to remove the upper limit.\n"
        "All values must be entered in the exact API format noted for each transaction type.\n"
    )
    updates: Dict[str, Union[int, float]] = {}
    for key, spec in FINANCIAL_LIMIT_SPECS.items():
        cur_val = current_limits.get(key, spec["default"])
        prompt = (
            f"{key}\n"
            f"  Services     : {', '.join(spec['services'])}\n"
            f"  API Fields   : {', '.join(spec['api_fields'])}\n"
            f"  Monetary Unit: {spec['monetary_unit']} ({spec['api_format']}) — {spec['unit_description']}\n"
            f"  Current Limit: {format_limit_display_value(key, cur_val)}\n"
            f"  New value [{cur_val}]: "
        )
        try:
            raw_in = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nInteractive configuration ended.")
            break
        if not raw_in:
            continue
        updates[key] = parse_and_validate_limit_amount(key, raw_in)

    if updates:
        written = write_financial_limits(
            updates, config_dir=config_dir, config_file=config_file
        )
        print(f"\nUpdated {len(updates)} financial limit(s) in {written}")
        return written
    print("\nNo changes made.")
    return active_path or ""


def build_arg_parser() -> argparse.ArgumentParser:
    """Builds the CLI argument parser for set_financial_limits.py."""
    parser = argparse.ArgumentParser(
        description=(
            "Configure upper limits for Google Ads API financial transactions in config/financial_limits. "
            "All values must be specified in the exact numeric format required by the Google Ads API call "
            "for each service (int64 micros, double currency_units, double decimal_ratio, or int64 micros_proportion)."
        )
    )
    parser.add_argument(
        "--list",
        "--show",
        dest="show",
        action="store_true",
        help="List all financial transaction types, their monetary units, API services, and current upper limits.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output financial transaction limits and metadata in JSON format.",
    )
    parser.add_argument(
        "--set",
        dest="set_items",
        action="append",
        default=[],
        metavar="TYPE=AMOUNT",
        help=(
            "Set an upper limit for a financial transaction type in API format "
            "(e.g., --set campaign_budget_amount_micros=100000000 --set conversion_upload_value=500.0). "
            "May be specified multiple times."
        ),
    )
    parser.add_argument(
        "--type",
        dest="txn_type",
        default=None,
        help="Financial transaction type key (or API field / service alias) to configure with --amount.",
    )
    parser.add_argument(
        "--amount",
        dest="amount",
        default=None,
        help="Upper limit amount in the exact format required by the API call (used with --type).",
    )
    parser.add_argument(
        "--reset",
        dest="reset_keys",
        action="append",
        default=[],
        metavar="TYPE",
        help="Reset the specified financial transaction type upper limit to 0 (unlimited).",
    )
    parser.add_argument(
        "--reset-all",
        action="store_true",
        help="Reset all financial transaction upper limits to 0 / 0.0 (unlimited).",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactively prompt for each financial transaction type.",
    )
    parser.add_argument(
        "--config-dir",
        default=None,
        help="Optional configuration directory containing financial_limits.",
    )
    parser.add_argument(
        "--config-file",
        default=None,
        help="Optional explicit path to a financial_limits file.",
    )

    # Dedicated per-transaction-type CLI flags
    type_group = parser.add_argument_group(
        "Transaction Type Flags (values in exact Google Ads API format)"
    )
    for key, spec in FINANCIAL_LIMIT_SPECS.items():
        flag_name = "--" + key.replace("_", "-")
        type_group.add_argument(
            flag_name,
            dest=f"limit__{key}",
            default=None,
            metavar=f"{spec['api_format'].upper()}_{spec['monetary_unit'].upper()}",
            help=(
                f"Upper limit for {key} [{spec['monetary_unit']} ({spec['api_format']}): "
                f"{spec['unit_description']}]"
            ),
        )

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint for viewing and setting financial transaction upper limits."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.interactive:
        try:
            run_interactive_prompt(
                config_dir=args.config_dir, config_file=args.config_file
            )
            return 0
        except ValueError as exc:
            print(f"[set_financial_limits] Error: {exc}", file=sys.stderr)
            return 2

    updates: Dict[str, Union[int, float]] = {}

    try:
        if args.reset_all:
            for k, spec in FINANCIAL_LIMIT_SPECS.items():
                updates[k] = spec["default"]

        for rk in args.reset_keys:
            canonical = resolve_limit_key(rk)
            updates[canonical] = FINANCIAL_LIMIT_SPECS[canonical]["default"]

        if (args.txn_type is not None) ^ (args.amount is not None):
            print(
                "[set_financial_limits] Error: --type and --amount must be provided together.",
                file=sys.stderr,
            )
            return 2

        if args.txn_type is not None and args.amount is not None:
            canonical = resolve_limit_key(args.txn_type)
            updates[canonical] = parse_and_validate_limit_amount(canonical, args.amount)

        for item in args.set_items:
            if "=" not in item:
                raise ValueError(
                    f"Invalid --set argument '{item}'. Expected format: TYPE=AMOUNT "
                    f"(e.g., --set campaign_budget_amount_micros=100000000)."
                )
            k_part, v_part = item.split("=", 1)
            canonical = resolve_limit_key(k_part)
            updates[canonical] = parse_and_validate_limit_amount(canonical, v_part)

        for key in FINANCIAL_LIMIT_SPECS:
            flag_val = getattr(args, f"limit__{key}", None)
            if flag_val is not None:
                updates[key] = parse_and_validate_limit_amount(key, flag_val)

    except ValueError as exc:
        print(f"[set_financial_limits] Error: {exc}", file=sys.stderr)
        return 2

    written_path: Optional[str] = None
    if updates:
        try:
            written_path = write_financial_limits(
                updates,
                config_dir=args.config_dir,
                config_file=args.config_file,
            )
        except Exception as exc:
            print(f"[set_financial_limits] Error writing config: {exc}", file=sys.stderr)
            return 1

    limits, active_path = read_financial_limits(
        config_dir=args.config_dir, config_file=args.config_file
    )
    effective_path = written_path or active_path

    if args.json:
        payload = {
            "config_file": effective_path,
            "limits": limits,
            "updated": updates,
            "specifications": {
                k: {
                    "value": limits.get(k, spec["default"]),
                    "monetary_unit": spec["monetary_unit"],
                    "api_format": spec["api_format"],
                    "unit_description": spec["unit_description"],
                    "services": spec["services"],
                    "api_fields": spec["api_fields"],
                }
                for k, spec in FINANCIAL_LIMIT_SPECS.items()
            },
        }
        print(json.dumps(payload, indent=2))
        return 0

    if updates and not args.show:
        print(f"Updated financial transaction upper limits in: {effective_path}")
        for k, v in updates.items():
            spec = FINANCIAL_LIMIT_SPECS[k]
            print(
                f"  • {k} = {format_limit_display_value(k, v)} "
                f"[unit: {spec['monetary_unit']} ({spec['api_format']})]"
            )
        return 0

    print(format_limits_table(limits, effective_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())

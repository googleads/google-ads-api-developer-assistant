#!/usr/bin/env python3
"""Helper utility to view, configure, and reset Google Ads API financial transaction upper limits by Service.field."""

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple, Union


FINANCIAL_LIMITS_FILENAME = "financial_limits"

# Field-level metadata: (api_format, monetary_unit, unit_description, default_value)
_FIELD_UNIT_META: Dict[str, Tuple[str, str, str, Union[int, float]]] = {
    "amount_micros": (
        "int64",
        "micros",
        "int64, 1,000,000 micros = 1.00 unit of account currency; e.g., 100000000 = 100.00",
        0,
    ),
    "total_amount_micros": (
        "int64",
        "micros",
        "int64, 1,000,000 micros = 1.00 unit of account currency; e.g., 1000000000 = 1,000.00 lifetime total",
        0,
    ),
    "new_budget_amount_micros": (
        "int64",
        "micros",
        "int64, 1,000,000 micros = 1.00 unit of account currency; e.g., 100000000 = 100.00/day",
        0,
    ),
    "new_campaign_budget_amount_micros": (
        "int64",
        "micros",
        "int64, 1,000,000 micros = 1.00 unit of account currency; e.g., 100000000 = 100.00/day",
        0,
    ),
    "budget_micros_to_move": (
        "int64",
        "micros",
        "int64, 1,000,000 micros = 1.00 unit of account currency; e.g., 50000000 = 50.00 budget transfer",
        0,
    ),
    "campaign_budget_amount_micros": (
        "int64",
        "micros",
        "int64, 1,000,000 micros = 1.00 unit of account currency; e.g., 100000000 = 100.00/day",
        0,
    ),
    "cpc_bid_micros": (
        "int64",
        "micros",
        "int64, 1,000,000 micros = 1.00 unit of account currency; e.g., 10000000 = 10.00 max CPC",
        0,
    ),
    "target_cpc_micros": (
        "int64",
        "micros",
        "int64, 1,000,000 micros = 1.00 unit of account currency; e.g., 10000000 = 10.00 target CPC",
        0,
    ),
    "cpm_bid_micros": (
        "int64",
        "micros",
        "int64, 1,000,000 micros = 1.00 unit of account currency per 1,000 impressions; e.g., 20000000 = 20.00 CPM",
        0,
    ),
    "target_cpm_micros": (
        "int64",
        "micros",
        "int64, 1,000,000 micros = 1.00 unit of account currency per 1,000 impressions; e.g., 20000000 = 20.00 target CPM",
        0,
    ),
    "fixed_cpm_micros": (
        "int64",
        "micros",
        "int64, 1,000,000 micros = 1.00 unit of account currency per 1,000 impressions; e.g., 20000000 = 20.00 fixed CPM",
        0,
    ),
    "cpv_bid_micros": (
        "int64",
        "micros",
        "int64, 1,000,000 micros = 1.00 unit of account currency; e.g., 2000000 = 2.00 CPV",
        0,
    ),
    "target_cpv_micros": (
        "int64",
        "micros",
        "int64, 1,000,000 micros = 1.00 unit of account currency; e.g., 2000000 = 2.00 target CPV",
        0,
    ),
    "target_cpa_micros": (
        "int64",
        "micros",
        "int64, 1,000,000 micros = 1.00 unit of account currency; e.g., 50000000 = 50.00 Target CPA",
        0,
    ),
    "manual_cpa_bid_micros": (
        "int64",
        "micros",
        "int64, 1,000,000 micros = 1.00 unit of account currency; e.g., 50000000 = 50.00 manual CPA",
        0,
    ),
    "target_cpa_bid_micros": (
        "int64",
        "micros",
        "int64, 1,000,000 micros = 1.00 unit of account currency; e.g., 50000000 = 50.00 Target CPA bid",
        0,
    ),
    "cpc_bid_ceiling_micros": (
        "int64",
        "micros",
        "int64, 1,000,000 micros = 1.00 unit of account currency; e.g., 15000000 = 15.00 CPC bid ceiling",
        0,
    ),
    "cpc_bid_floor_micros": (
        "int64",
        "micros",
        "int64, 1,000,000 micros = 1.00 unit of account currency; e.g., 15000000 = 15.00 CPC bid floor",
        0,
    ),
    "target_spend_micros": (
        "int64",
        "micros",
        "int64, 1,000,000 micros = 1.00 unit of account currency; e.g., 100000000 = 100.00 target spend",
        0,
    ),
    "percent_cpc_bid_micros": (
        "int64",
        "micros_proportion",
        "int64, 1,000,000 = 100%; e.g., 250000 = 25% of item/hotel price",
        0,
    ),
    "location_fraction_micros": (
        "int64",
        "micros_proportion",
        "int64, 1,000,000 = 100%; e.g., 500000 = 50% target impression share",
        0,
    ),
    "commission_rate_micros": (
        "int64",
        "micros_proportion",
        "int64, 1,000,000 = 100%; e.g., 150000 = 15% commission rate",
        0,
    ),
    "conversion_value": (
        "double",
        "currency_units",
        "double/float, standard currency units, NOT micros; e.g., 500.0 = 500.00 currency units",
        0.0,
    ),
    "unit_price": (
        "double",
        "currency_units",
        "double/float, standard currency units, NOT micros; e.g., 100.0 = 100.00 item unit price",
        0.0,
    ),
    "local_transaction_cost": (
        "double",
        "currency_units",
        "double/float, standard currency units, NOT micros; e.g., 50.0 = 50.00 local transaction cost",
        0.0,
    ),
    "adjusted_value": (
        "double",
        "currency_units",
        "double/float, standard currency units, NOT micros; e.g., 500.0 = 500.00 restated value",
        0.0,
    ),
    "default_value": (
        "double",
        "currency_units",
        "double/float, standard currency units, NOT micros; e.g., 100.0 = 100.00 default conversion value",
        0.0,
    ),
    "value": (
        "double",
        "currency_units",
        "for ADD/SET operations (or decimal_ratio for MULTIPLY operation) (double/float, NOT micros; e.g., 100.0)",
        0.0,
    ),
    "additional_value": (
        "double",
        "currency_units",
        "double/float, standard currency units, NOT micros; e.g., 50.0 = 50.00 additional new-customer value",
        0.0,
    ),
    "additional_high_lifetime_value": (
        "double",
        "currency_units",
        "double/float, standard currency units, NOT micros; e.g., 100.0 = 100.00 additional high-LTV value",
        0.0,
    ),
    "transaction_amount_micros": (
        "int64",
        "micros",
        "int64, 1,000,000 micros = 1.00 unit of currency; e.g., 500000000 = 500.00 transaction amount",
        0,
    ),
    "lifetime_value_micros": (
        "int64",
        "micros",
        "int64, 1,000,000 micros = 1.00 unit of currency; e.g., 500000000 = 500.00 user lifetime value",
        0,
    ),
    "average_purchase_value_micros": (
        "int64",
        "micros",
        "int64, 1,000,000 micros = 1.00 unit of currency; e.g., 250000000 = 250.00 average purchase value",
        0,
    ),
    "target_roas": (
        "double",
        "decimal_ratio",
        "double/float, conversion value per 1.00 currency unit spent; e.g., 5.0 = 500% ROAS",
        0.0,
    ),
    "bid_modifier": (
        "double",
        "decimal_ratio",
        "double/float, bid multiplier; e.g., 2.0 = +100% bid adjustment",
        0.0,
    ),
    "conversion_rate_modifier": (
        "double",
        "decimal_ratio",
        "double/float, conversion rate multiplier; e.g., 1.5 = +50% seasonality adjustment",
        0.0,
    ),
    "target_cpa_multiplier": (
        "double",
        "decimal_ratio",
        "double/float, recommendation Target CPA multiplier; e.g., 1.2 = 120% of current Target CPA",
        0.0,
    ),
    "target_roas_multiplier": (
        "double",
        "decimal_ratio",
        "double/float, recommendation Target ROAS multiplier; e.g., 0.9 = 90% of current Target ROAS",
        0.0,
    ),
    "target_multiplier": (
        "double",
        "decimal_ratio",
        "double/float, recommendation target multiplier; e.g., 1.2 = 120% of current target",
        0.0,
    ),
    "value_multiplier": (
        "double",
        "decimal_ratio",
        "double/float, customer lifecycle value multiplier; e.g., 1.5 = 150% conversion value multiplier",
        0.0,
    ),
    "high_lifetime_value_multiplier": (
        "double",
        "decimal_ratio",
        "double/float, high-LTV customer lifecycle value multiplier; e.g., 2.0 = 200% conversion value multiplier",
        0.0,
    ),
}

# Service-by-service mapping of mutable financial fields in Google Ads API v26:
# (service_name, rpc_methods_str, [(field_name, protobuf_context_note), ...])
_SERVICE_FIELD_DEFINITIONS: List[Tuple[str, str, List[Tuple[str, str]]]] = [
    (
        "AdGroupBidModifierService",
        "mutate_ad_group_bid_modifiers",
        [
            ("bid_modifier", "AdGroupBidModifier.bid_modifier"),
        ],
    ),
    (
        "AdGroupCriterionService",
        "mutate_ad_group_criteria",
        [
            ("bid_modifier", "AdGroupCriterion.bid_modifier"),
            ("cpc_bid_micros", "AdGroupCriterion.cpc_bid_micros"),
            ("cpm_bid_micros", "AdGroupCriterion.cpm_bid_micros"),
            ("cpv_bid_micros", "AdGroupCriterion.cpv_bid_micros"),
            ("percent_cpc_bid_micros", "AdGroupCriterion.percent_cpc_bid_micros"),
        ],
    ),
    (
        "AdGroupService",
        "mutate_ad_groups",
        [
            ("cpc_bid_micros", "AdGroup.cpc_bid_micros"),
            ("cpm_bid_micros", "AdGroup.cpm_bid_micros"),
            ("cpv_bid_micros", "AdGroup.cpv_bid_micros"),
            ("fixed_cpm_micros", "AdGroup.fixed_cpm_micros"),
            ("percent_cpc_bid_micros", "AdGroup.percent_cpc_bid_micros"),
            ("target_cpa_micros", "AdGroup.target_cpa_micros"),
            ("target_cpc_micros", "AdGroup.target_cpc_micros"),
            ("target_cpm_micros", "AdGroup.target_cpm_micros"),
            ("target_cpv_micros", "AdGroup.target_cpv_micros"),
            ("target_roas", "AdGroup.target_roas"),
        ],
    ),
    (
        "AssetService",
        "mutate_assets",
        [
            ("amount_micros", "PromotionAsset.money_amount_off.amount_micros, PromotionAsset.orders_over_amount.amount_micros, PriceOffering.price.amount_micros"),
        ],
    ),
    (
        "BatchJobService",
        "add_batch_job_operations",
        [
            ("amount_micros", "CampaignBudget.amount_micros, Money.amount_micros"),
            ("bid_modifier", "AdGroupBidModifier.bid_modifier, AdGroupCriterion.bid_modifier, CampaignBidModifier.bid_modifier, CampaignCriterion.bid_modifier"),
            ("commission_rate_micros", "Commission.commission_rate_micros"),
            ("conversion_rate_modifier", "BiddingSeasonalityAdjustment.conversion_rate_modifier"),
            ("cpc_bid_ceiling_micros", "MaximizeConversions.cpc_bid_ceiling_micros, MaximizeConversionValue.cpc_bid_ceiling_micros, TargetCpa.cpc_bid_ceiling_micros, TargetRoas.cpc_bid_ceiling_micros, TargetSpend.cpc_bid_ceiling_micros, TargetImpressionShare.cpc_bid_ceiling_micros, PercentCpc.cpc_bid_ceiling_micros"),
            ("cpc_bid_floor_micros", "MaximizeConversions.cpc_bid_floor_micros, MaximizeConversionValue.cpc_bid_floor_micros, TargetCpa.cpc_bid_floor_micros, TargetRoas.cpc_bid_floor_micros"),
            ("cpc_bid_micros", "AdGroup.cpc_bid_micros, AdGroupCriterion.cpc_bid_micros, KeywordPlanCampaign.cpc_bid_micros, KeywordPlanAdGroup.cpc_bid_micros, KeywordPlanAdGroupKeyword.cpc_bid_micros"),
            ("cpm_bid_micros", "AdGroup.cpm_bid_micros, AdGroupCriterion.cpm_bid_micros"),
            ("cpv_bid_micros", "AdGroup.cpv_bid_micros, AdGroupCriterion.cpv_bid_micros"),
            ("default_value", "ValueSettings.default_value"),
            ("fixed_cpm_micros", "AdGroup.fixed_cpm_micros"),
            ("location_fraction_micros", "TargetImpressionShare.location_fraction_micros"),
            ("manual_cpa_bid_micros", "CategoryBid.manual_cpa_bid_micros"),
            ("percent_cpc_bid_micros", "AdGroup.percent_cpc_bid_micros, AdGroupCriterion.percent_cpc_bid_micros"),
            ("target_cpa_bid_micros", "CategoryBid.target_cpa_bid_micros"),
            ("target_cpa_micros", "AdGroup.target_cpa_micros, TargetCpa.target_cpa_micros, MaximizeConversions.target_cpa_micros"),
            ("target_cpc_micros", "AdGroup.target_cpc_micros, TargetCpc.target_cpc_micros"),
            ("target_cpm_micros", "AdGroup.target_cpm_micros"),
            ("target_cpv_micros", "AdGroup.target_cpv_micros"),
            ("target_roas", "AdGroup.target_roas, TargetRoas.target_roas, MaximizeConversionValue.target_roas"),
            ("target_spend_micros", "TargetSpend.target_spend_micros"),
            ("total_amount_micros", "CampaignBudget.total_amount_micros"),
            ("value", "ValueRuleAction.value"),
        ],
    ),
    (
        "BiddingSeasonalityAdjustmentService",
        "mutate_bidding_seasonality_adjustments",
        [
            ("conversion_rate_modifier", "BiddingSeasonalityAdjustment.conversion_rate_modifier"),
        ],
    ),
    (
        "BiddingStrategyService",
        "mutate_bidding_strategies",
        [
            ("cpc_bid_ceiling_micros", "MaximizeConversions.cpc_bid_ceiling_micros, MaximizeConversionValue.cpc_bid_ceiling_micros, TargetCpa.cpc_bid_ceiling_micros, TargetRoas.cpc_bid_ceiling_micros, TargetSpend.cpc_bid_ceiling_micros, TargetImpressionShare.cpc_bid_ceiling_micros"),
            ("cpc_bid_floor_micros", "MaximizeConversions.cpc_bid_floor_micros, MaximizeConversionValue.cpc_bid_floor_micros, TargetCpa.cpc_bid_floor_micros, TargetRoas.cpc_bid_floor_micros"),
            ("location_fraction_micros", "TargetImpressionShare.location_fraction_micros"),
            ("target_cpa_micros", "TargetCpa.target_cpa_micros, MaximizeConversions.target_cpa_micros"),
            ("target_roas", "TargetRoas.target_roas, MaximizeConversionValue.target_roas"),
            ("target_spend_micros", "TargetSpend.target_spend_micros"),
        ],
    ),
    (
        "CampaignBidModifierService",
        "mutate_campaign_bid_modifiers",
        [
            ("bid_modifier", "CampaignBidModifier.bid_modifier"),
        ],
    ),
    (
        "CampaignBudgetService",
        "mutate_campaign_budgets",
        [
            ("amount_micros", "CampaignBudget.amount_micros"),
            ("total_amount_micros", "CampaignBudget.total_amount_micros"),
        ],
    ),
    (
        "CampaignCriterionService",
        "mutate_campaign_criteria",
        [
            ("bid_modifier", "CampaignCriterion.bid_modifier"),
        ],
    ),
    (
        "CampaignGoalConfigService",
        "mutate_campaign_goal_configs",
        [
            ("additional_high_lifetime_value", "CustomerLifecycleOptimizationValueSettings.additional_high_lifetime_value"),
            ("additional_value", "CustomerLifecycleOptimizationValueSettings.additional_value"),
            ("high_lifetime_value_multiplier", "CustomerLifecycleOptimizationValueSettings.high_lifetime_value_multiplier"),
            ("value_multiplier", "CustomerLifecycleOptimizationValueSettings.value_multiplier"),
        ],
    ),
    (
        "CampaignService",
        "mutate_campaigns",
        [
            ("commission_rate_micros", "Commission.commission_rate_micros"),
            ("cpc_bid_ceiling_micros", "MaximizeConversions.cpc_bid_ceiling_micros, MaximizeConversionValue.cpc_bid_ceiling_micros, TargetCpa.cpc_bid_ceiling_micros, TargetRoas.cpc_bid_ceiling_micros, TargetSpend.cpc_bid_ceiling_micros, TargetImpressionShare.cpc_bid_ceiling_micros, PercentCpc.cpc_bid_ceiling_micros"),
            ("cpc_bid_floor_micros", "MaximizeConversions.cpc_bid_floor_micros, MaximizeConversionValue.cpc_bid_floor_micros, TargetCpa.cpc_bid_floor_micros, TargetRoas.cpc_bid_floor_micros"),
            ("location_fraction_micros", "TargetImpressionShare.location_fraction_micros"),
            ("manual_cpa_bid_micros", "CategoryBid.manual_cpa_bid_micros"),
            ("target_cpa_bid_micros", "CategoryBid.target_cpa_bid_micros"),
            ("target_cpa_micros", "TargetCpa.target_cpa_micros, MaximizeConversions.target_cpa_micros"),
            ("target_cpc_micros", "TargetCpc.target_cpc_micros"),
            ("target_roas", "TargetRoas.target_roas, MaximizeConversionValue.target_roas"),
            ("target_spend_micros", "TargetSpend.target_spend_micros"),
        ],
    ),
    (
        "ConversionActionService",
        "mutate_conversion_actions",
        [
            ("default_value", "ValueSettings.default_value"),
        ],
    ),
    (
        "ConversionAdjustmentUploadService",
        "upload_conversion_adjustments",
        [
            ("adjusted_value", "RestatementValue.adjusted_value"),
        ],
    ),
    (
        "ConversionUploadService",
        "upload_click_conversions, upload_call_conversions",
        [
            ("conversion_value", "ClickConversion.conversion_value, CallConversion.conversion_value"),
            ("local_transaction_cost", "CartData.local_transaction_cost"),
            ("unit_price", "CartData.Item.unit_price"),
        ],
    ),
    (
        "ConversionValueRuleService",
        "mutate_conversion_value_rules",
        [
            ("value", "ValueRuleAction.value"),
        ],
    ),
    (
        "GoalService",
        "mutate_goals",
        [
            ("additional_high_lifetime_value", "CustomerLifecycleOptimizationValueSettings.additional_high_lifetime_value"),
            ("additional_value", "CustomerLifecycleOptimizationValueSettings.additional_value"),
            ("high_lifetime_value_multiplier", "CustomerLifecycleOptimizationValueSettings.high_lifetime_value_multiplier"),
            ("value_multiplier", "CustomerLifecycleOptimizationValueSettings.value_multiplier"),
        ],
    ),
    (
        "GoogleAdsService",
        "mutate",
        [
            ("amount_micros", "CampaignBudget.amount_micros, Money.amount_micros"),
            ("bid_modifier", "AdGroupBidModifier.bid_modifier, AdGroupCriterion.bid_modifier, CampaignBidModifier.bid_modifier, CampaignCriterion.bid_modifier"),
            ("commission_rate_micros", "Commission.commission_rate_micros"),
            ("conversion_rate_modifier", "BiddingSeasonalityAdjustment.conversion_rate_modifier"),
            ("cpc_bid_ceiling_micros", "MaximizeConversions.cpc_bid_ceiling_micros, MaximizeConversionValue.cpc_bid_ceiling_micros, TargetCpa.cpc_bid_ceiling_micros, TargetRoas.cpc_bid_ceiling_micros, TargetSpend.cpc_bid_ceiling_micros, TargetImpressionShare.cpc_bid_ceiling_micros, PercentCpc.cpc_bid_ceiling_micros"),
            ("cpc_bid_floor_micros", "MaximizeConversions.cpc_bid_floor_micros, MaximizeConversionValue.cpc_bid_floor_micros, TargetCpa.cpc_bid_floor_micros, TargetRoas.cpc_bid_floor_micros"),
            ("cpc_bid_micros", "AdGroup.cpc_bid_micros, AdGroupCriterion.cpc_bid_micros, KeywordPlanCampaign.cpc_bid_micros, KeywordPlanAdGroup.cpc_bid_micros, KeywordPlanAdGroupKeyword.cpc_bid_micros"),
            ("cpm_bid_micros", "AdGroup.cpm_bid_micros, AdGroupCriterion.cpm_bid_micros"),
            ("cpv_bid_micros", "AdGroup.cpv_bid_micros, AdGroupCriterion.cpv_bid_micros"),
            ("default_value", "ValueSettings.default_value"),
            ("fixed_cpm_micros", "AdGroup.fixed_cpm_micros"),
            ("location_fraction_micros", "TargetImpressionShare.location_fraction_micros"),
            ("manual_cpa_bid_micros", "CategoryBid.manual_cpa_bid_micros"),
            ("percent_cpc_bid_micros", "AdGroup.percent_cpc_bid_micros, AdGroupCriterion.percent_cpc_bid_micros"),
            ("target_cpa_bid_micros", "CategoryBid.target_cpa_bid_micros"),
            ("target_cpa_micros", "AdGroup.target_cpa_micros, TargetCpa.target_cpa_micros, MaximizeConversions.target_cpa_micros"),
            ("target_cpc_micros", "AdGroup.target_cpc_micros, TargetCpc.target_cpc_micros"),
            ("target_cpm_micros", "AdGroup.target_cpm_micros"),
            ("target_cpv_micros", "AdGroup.target_cpv_micros"),
            ("target_roas", "AdGroup.target_roas, TargetRoas.target_roas, MaximizeConversionValue.target_roas"),
            ("target_spend_micros", "TargetSpend.target_spend_micros"),
            ("total_amount_micros", "CampaignBudget.total_amount_micros"),
            ("value", "ValueRuleAction.value"),
        ],
    ),
    (
        "KeywordPlanAdGroupKeywordService",
        "mutate_keyword_plan_ad_group_keywords",
        [
            ("cpc_bid_micros", "KeywordPlanAdGroupKeyword.cpc_bid_micros"),
        ],
    ),
    (
        "KeywordPlanAdGroupService",
        "mutate_keyword_plan_ad_groups",
        [
            ("cpc_bid_micros", "KeywordPlanAdGroup.cpc_bid_micros"),
        ],
    ),
    (
        "KeywordPlanCampaignService",
        "mutate_keyword_plan_campaigns",
        [
            ("cpc_bid_micros", "KeywordPlanCampaign.cpc_bid_micros"),
        ],
    ),
    (
        "OfflineUserDataJobService",
        "add_offline_user_data_job_operations",
        [
            ("average_purchase_value_micros", "UserAttribute.average_purchase_value_micros"),
            ("lifetime_value_micros", "UserAttribute.lifetime_value_micros"),
            ("transaction_amount_micros", "TransactionAttribute.transaction_amount_micros"),
        ],
    ),
    (
        "RecommendationService",
        "apply_recommendation",
        [
            ("amount_micros", "PromotionAsset.money_amount_off.amount_micros, PromotionAsset.orders_over_amount.amount_micros"),
            ("budget_micros_to_move", "MoveUnusedBudgetParameters.budget_micros_to_move"),
            ("campaign_budget_amount_micros", "ForecastingSetTargetCpaParameters.campaign_budget_amount_micros, ForecastingSetTargetRoasParameters.campaign_budget_amount_micros"),
            ("cpc_bid_micros", "KeywordParameters.cpc_bid_micros"),
            ("new_budget_amount_micros", "CampaignBudgetParameters.new_budget_amount_micros, RaiseBudgetPerformanceTooLowParameters.new_budget_amount_micros, UseBroadMatchKeywordParameters.new_budget_amount_micros"),
            ("new_campaign_budget_amount_micros", "TargetCpaOptInParameters.new_campaign_budget_amount_micros, TargetRoasOptInParameters.new_campaign_budget_amount_micros"),
            ("target_cpa_micros", "TargetCpaOptInParameters.target_cpa_micros, ForecastingSetTargetCpaParameters.target_cpa_micros"),
            ("target_cpa_multiplier", "RaiseTargetCpaParameters.target_cpa_multiplier, RaiseTargetCpaPerformanceBidTooLowParameters.target_cpa_multiplier"),
            ("target_multiplier", "RaiseTargetCpaBidTooLowParameters.target_multiplier"),
            ("target_roas", "TargetRoasOptInParameters.target_roas, ForecastingSetTargetRoasParameters.target_roas"),
            ("target_roas_multiplier", "LowerTargetRoasParameters.target_roas_multiplier, LowerTargetRoasPerformanceBidTooLowParameters.target_roas_multiplier"),
        ],
    ),
    (
        "UserDataService",
        "upload_user_data",
        [
            ("average_purchase_value_micros", "UserAttribute.average_purchase_value_micros"),
            ("lifetime_value_micros", "UserAttribute.lifetime_value_micros"),
            ("transaction_amount_micros", "TransactionAttribute.transaction_amount_micros"),
        ],
    ),
]


def _build_financial_limit_specs() -> Dict[str, Dict[str, Any]]:
    specs: Dict[str, Dict[str, Any]] = {
        "all_micros_transactions": {
            "category": "Global Fallback Upper Limits (Optional)",
            "service": "ALL",
            "field": "all_micros_transactions",
            "services": [
                "All Google Ads API services using micros-denominated monetary fields"
            ],
            "api_fields": [
                "Any *_micros monetary field when its Service.field limit below is set to 0"
            ],
            "protobuf_paths": ["*.*_micros"],
            "api_format": "int64",
            "monetary_unit": "micros",
            "unit_description": "int64, 1,000,000 micros = 1.00 unit of account currency",
            "default": 0,
        },
        "all_currency_unit_transactions": {
            "category": "Global Fallback Upper Limits (Optional)",
            "service": "ALL",
            "field": "all_currency_unit_transactions",
            "services": [
                "All Google Ads API services using standard currency unit fields"
            ],
            "api_fields": [
                "Any standard currency unit field when its Service.field limit below is set to 0.0"
            ],
            "protobuf_paths": ["*.*"],
            "api_format": "double",
            "monetary_unit": "currency_units",
            "unit_description": "double/float, 1.0 = 1.00 unit of account currency, NOT micros",
            "default": 0.0,
        },
    }

    for svc_name, rpc_methods, fields in _SERVICE_FIELD_DEFINITIONS:
        category = f"{svc_name} ({rpc_methods})"
        svc_label = f"{svc_name} ({rpc_methods})"
        for field_name, proto_note in fields:
            fmt, unit, desc, default_val = _FIELD_UNIT_META[field_name]
            key = f"{svc_name}.{field_name}"
            specs[key] = {
                "category": category,
                "service": svc_name,
                "field": field_name,
                "services": [svc_label],
                "api_fields": [field_name],
                "protobuf_paths": [p.strip() for p in proto_note.split(",")],
                "api_format": fmt,
                "monetary_unit": unit,
                "unit_description": desc,
                "default": default_val,
            }
    return specs


# Canonical specification of all mutable financial transaction limits keyed by `Service.field`
# (plus the 2 global fallbacks `all_micros_transactions` and `all_currency_unit_transactions`).
FINANCIAL_LIMIT_SPECS: Dict[str, Dict[str, Any]] = _build_financial_limit_specs()

# Case-insensitive lookup map for canonical `Service.field` keys
_LOWER_TO_CANONICAL_KEY: Dict[str, str] = {}
for _k in FINANCIAL_LIMIT_SPECS:
    _LOWER_TO_CANONICAL_KEY[_k.lower()] = _k
    _LOWER_TO_CANONICAL_KEY[_k.lower().replace(".", "_").replace("-", "_")] = _k

# Primary `Service.field` key for bare field names or legacy category aliases
LIMIT_KEY_ALIASES: Dict[str, str] = {
    # Legacy category keys & bare field names -> primary mutable Service.field key
    "campaign_budget_amount_micros": "CampaignBudgetService.amount_micros",
    "amount_micros": "CampaignBudgetService.amount_micros",
    "new_budget_amount_micros": "RecommendationService.new_budget_amount_micros",
    "new_campaign_budget_amount_micros": "RecommendationService.new_campaign_budget_amount_micros",
    "budget_micros_to_move": "RecommendationService.budget_micros_to_move",
    "campaign_budget": "CampaignBudgetService.amount_micros",
    "campaignbudgetservice": "CampaignBudgetService.amount_micros",
    "campaign_budget_total_amount_micros": "CampaignBudgetService.total_amount_micros",
    "total_amount_micros": "CampaignBudgetService.total_amount_micros",
    "asset_price_and_promotion_amount_micros": "AssetService.amount_micros",
    "money_amount_off": "AssetService.amount_micros",
    "orders_over_amount": "AssetService.amount_micros",
    "price_offering": "AssetService.amount_micros",
    "promotion_asset": "AssetService.amount_micros",
    "price_asset": "AssetService.amount_micros",
    "assetservice": "AssetService.amount_micros",
    "cpc_bid_micros": "AdGroupService.cpc_bid_micros",
    "target_cpc_micros": "AdGroupService.target_cpc_micros",
    "cpm_bid_micros": "AdGroupService.cpm_bid_micros",
    "target_cpm_micros": "AdGroupService.target_cpm_micros",
    "fixed_cpm_micros": "AdGroupService.fixed_cpm_micros",
    "cpv_bid_micros": "AdGroupService.cpv_bid_micros",
    "target_cpv_micros": "AdGroupService.target_cpv_micros",
    "target_cpa_micros": "BiddingStrategyService.target_cpa_micros",
    "manual_cpa_bid_micros": "CampaignService.manual_cpa_bid_micros",
    "target_cpa_bid_micros": "CampaignService.target_cpa_bid_micros",
    "cpc_bid_ceiling_micros": "BiddingStrategyService.cpc_bid_ceiling_micros",
    "cpc_bid_floor_micros": "BiddingStrategyService.cpc_bid_floor_micros",
    "target_spend_micros": "BiddingStrategyService.target_spend_micros",
    "percent_cpc_bid_micros": "AdGroupService.percent_cpc_bid_micros",
    "location_fraction_micros": "BiddingStrategyService.location_fraction_micros",
    "commission_rate_micros": "CampaignService.commission_rate_micros",
    "commission": "CampaignService.commission_rate_micros",
    "conversion_upload_value": "ConversionUploadService.conversion_value",
    "conversion_value": "ConversionUploadService.conversion_value",
    "click_conversion_value": "ConversionUploadService.conversion_value",
    "call_conversion_value": "ConversionUploadService.conversion_value",
    "unit_price": "ConversionUploadService.unit_price",
    "local_transaction_cost": "ConversionUploadService.local_transaction_cost",
    "conversionuploadservice": "ConversionUploadService.conversion_value",
    "conversion_adjustment_restatement_value": "ConversionAdjustmentUploadService.adjusted_value",
    "adjusted_value": "ConversionAdjustmentUploadService.adjusted_value",
    "restatement_value": "ConversionAdjustmentUploadService.adjusted_value",
    "conversionadjustmentuploadservice": "ConversionAdjustmentUploadService.adjusted_value",
    "conversion_action_default_value": "ConversionActionService.default_value",
    "default_value": "ConversionActionService.default_value",
    "conversionactionservice": "ConversionActionService.default_value",
    "conversion_value_rule_action_value": "ConversionValueRuleService.value",
    "value": "ConversionValueRuleService.value",
    "action.value": "ConversionValueRuleService.value",
    "conversion_value_rule": "ConversionValueRuleService.value",
    "conversionvalueruleservice": "ConversionValueRuleService.value",
    "lifecycle_goal_additional_value": "GoalService.additional_value",
    "additional_value": "GoalService.additional_value",
    "additional_high_lifetime_value": "GoalService.additional_high_lifetime_value",
    "goalservice": "GoalService.additional_value",
    "campaigngoalconfigservice": "CampaignGoalConfigService.additional_value",
    "user_data_transaction_amount_micros": "UserDataService.transaction_amount_micros",
    "transaction_amount_micros": "UserDataService.transaction_amount_micros",
    "lifetime_value_micros": "UserDataService.lifetime_value_micros",
    "average_purchase_value_micros": "UserDataService.average_purchase_value_micros",
    "userdataservice": "UserDataService.transaction_amount_micros",
    "offlineuserdatajobservice": "OfflineUserDataJobService.transaction_amount_micros",
    "target_roas": "BiddingStrategyService.target_roas",
    "bid_modifier": "CampaignBidModifierService.bid_modifier",
    "seasonality_conversion_rate_modifier": "BiddingSeasonalityAdjustmentService.conversion_rate_modifier",
    "conversion_rate_modifier": "BiddingSeasonalityAdjustmentService.conversion_rate_modifier",
    "biddingseasonalityadjustmentservice": "BiddingSeasonalityAdjustmentService.conversion_rate_modifier",
    "recommendation_target_multiplier": "RecommendationService.target_cpa_multiplier",
    "target_cpa_multiplier": "RecommendationService.target_cpa_multiplier",
    "target_roas_multiplier": "RecommendationService.target_roas_multiplier",
    "target_multiplier": "RecommendationService.target_multiplier",
    "lifecycle_goal_value_multiplier": "CampaignGoalConfigService.high_lifetime_value_multiplier",
    "value_multiplier": "CampaignGoalConfigService.value_multiplier",
    "high_lifetime_value_multiplier": "CampaignGoalConfigService.high_lifetime_value_multiplier",
}

# Group expansion for legacy category aliases or bare field names so setting a group
# alias (or `*.field`) applies across all corresponding mutable `Service.field` entries.
_GROUP_ALIAS_FIELDS: Dict[str, List[str]] = {
    "campaign_budget_amount_micros": [
        "CampaignBudgetService.amount_micros",
        "GoogleAdsService.amount_micros",
        "BatchJobService.amount_micros",
        "RecommendationService.new_budget_amount_micros",
        "RecommendationService.new_campaign_budget_amount_micros",
        "RecommendationService.budget_micros_to_move",
        "RecommendationService.campaign_budget_amount_micros",
    ],
    "campaign_budget_total_amount_micros": [
        "CampaignBudgetService.total_amount_micros",
        "GoogleAdsService.total_amount_micros",
        "BatchJobService.total_amount_micros",
    ],
    "asset_price_and_promotion_amount_micros": [
        "AssetService.amount_micros",
        "RecommendationService.amount_micros",
    ],
    "conversion_upload_value": [
        "ConversionUploadService.conversion_value",
        "ConversionUploadService.unit_price",
        "ConversionUploadService.local_transaction_cost",
    ],
    "click_conversion_value": [
        "ConversionUploadService.conversion_value",
        "ConversionUploadService.unit_price",
        "ConversionUploadService.local_transaction_cost",
    ],
    "call_conversion_value": [
        "ConversionUploadService.conversion_value",
    ],
    "conversion_adjustment_restatement_value": [
        "ConversionAdjustmentUploadService.adjusted_value",
    ],
    "conversion_action_default_value": [
        "ConversionActionService.default_value",
        "GoogleAdsService.default_value",
        "BatchJobService.default_value",
    ],
    "conversion_value_rule_action_value": [
        "ConversionValueRuleService.value",
        "GoogleAdsService.value",
        "BatchJobService.value",
    ],
    "lifecycle_goal_additional_value": [
        "GoalService.additional_value",
        "GoalService.additional_high_lifetime_value",
        "CampaignGoalConfigService.additional_value",
        "CampaignGoalConfigService.additional_high_lifetime_value",
    ],
    "user_data_transaction_amount_micros": [
        "UserDataService.transaction_amount_micros",
        "UserDataService.lifetime_value_micros",
        "UserDataService.average_purchase_value_micros",
        "OfflineUserDataJobService.transaction_amount_micros",
        "OfflineUserDataJobService.lifetime_value_micros",
        "OfflineUserDataJobService.average_purchase_value_micros",
    ],
    "seasonality_conversion_rate_modifier": [
        "BiddingSeasonalityAdjustmentService.conversion_rate_modifier",
        "GoogleAdsService.conversion_rate_modifier",
        "BatchJobService.conversion_rate_modifier",
    ],
    "recommendation_target_multiplier": [
        "RecommendationService.target_cpa_multiplier",
        "RecommendationService.target_roas_multiplier",
        "RecommendationService.target_multiplier",
    ],
    "lifecycle_goal_value_multiplier": [
        "GoalService.value_multiplier",
        "GoalService.high_lifetime_value_multiplier",
        "CampaignGoalConfigService.value_multiplier",
        "CampaignGoalConfigService.high_lifetime_value_multiplier",
    ],
}


def resolve_limit_key(raw_key: str) -> str:
    """Resolves a `Service.field` key, CLI flag name, or alias to its canonical key."""
    cleaned = raw_key.strip()
    if cleaned in FINANCIAL_LIMIT_SPECS:
        return cleaned

    lower = cleaned.lower()
    if lower in _LOWER_TO_CANONICAL_KEY:
        return _LOWER_TO_CANONICAL_KEY[lower]

    norm = lower.replace("-", "_")
    if norm in _LOWER_TO_CANONICAL_KEY:
        return _LOWER_TO_CANONICAL_KEY[norm]

    if lower.startswith("*."):
        bare_field = lower[2:].replace("-", "_")
        if bare_field in LIMIT_KEY_ALIASES:
            return LIMIT_KEY_ALIASES[bare_field]

    if lower in LIMIT_KEY_ALIASES:
        return LIMIT_KEY_ALIASES[lower]
    if norm in LIMIT_KEY_ALIASES:
        return LIMIT_KEY_ALIASES[norm]

    raise ValueError(
        f"Unknown financial transaction limit key '{raw_key}'. "
        f"Expected 'Service.field' (e.g., CampaignBudgetService.amount_micros, AdGroupService.cpc_bid_micros) "
        f"or global fallback ('all_micros_transactions', 'all_currency_unit_transactions')."
    )


def resolve_limit_keys(raw_key: str) -> List[str]:
    """Resolves a key to one or more canonical `Service.field` keys.

    - Exact `Service.field` resolves to `[Service.field]`.
    - Wildcard `*.field` resolves to all `Service.field` entries for that field.
    - Group/field alias (e.g., `campaign_budget_amount_micros` or `cpc_bid_micros`)
      resolves to all `Service.field` entries in that group or with that field name.
    """
    cleaned = raw_key.strip()
    if cleaned in FINANCIAL_LIMIT_SPECS:
        return [cleaned]

    lower = cleaned.lower()
    if lower in _LOWER_TO_CANONICAL_KEY:
        return [_LOWER_TO_CANONICAL_KEY[lower]]

    norm = lower.replace("-", "_")
    # Check if norm matches a specific `service_field` key (and is not a bare field or group alias)
    if (
        norm in _LOWER_TO_CANONICAL_KEY
        and norm not in _GROUP_ALIAS_FIELDS
        and norm not in _FIELD_UNIT_META
        and norm not in LIMIT_KEY_ALIASES
    ):
        return [_LOWER_TO_CANONICAL_KEY[norm]]

    if lower.startswith("*."):
        bare_field = lower[2:].replace("-", "_")
        matched = [
            k
            for k, spec in FINANCIAL_LIMIT_SPECS.items()
            if spec.get("field") == bare_field
        ]
        if matched:
            return matched

    if norm in _GROUP_ALIAS_FIELDS:
        return list(_GROUP_ALIAS_FIELDS[norm])

    if norm in _FIELD_UNIT_META:
        matched = [
            k
            for k, spec in FINANCIAL_LIMIT_SPECS.items()
            if spec.get("field") == norm
        ]
        if matched:
            return matched

    primary = resolve_limit_key(raw_key)
    return [primary]


def flatten_toml_limits(parsed_toml: Dict[str, Any]) -> Dict[str, Any]:
    """Flattens nested TOML table dicts (`{Service: {field: val}}`) into `{'Service.field': val}`."""
    flat: Dict[str, Any] = {}
    for k, v in parsed_toml.items():
        if isinstance(v, dict):
            for sub_k, sub_v in v.items():
                if not isinstance(sub_v, dict):
                    flat[f"{k}.{sub_k}"] = sub_v
        else:
            flat[k] = v
    return flat


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
                f"Invalid amount '{val_int}' for '{canonical_key}': value must be >= 0 "
                f"(0 = not modifiable; > 0 = modifiable up to that upper limit)."
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
            f"Invalid amount '{val_float}' for '{canonical_key}': value must be >= 0.0 "
            f"(0.0 = not modifiable; > 0.0 = modifiable up to that upper limit)."
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
    """Parses TOML (`Service.field = value` or `[Service]`) or key=value text from config/financial_limits."""
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
            parsed_dict = flatten_toml_limits(loaded)
    except Exception:
        pass

    if not parsed_dict:
        current_section = ""
        for raw_line in raw_text.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue
            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1].strip()
                continue
            if "=" not in line:
                continue
            k_part, v_part = line.split("=", 1)
            k_clean = k_part.strip().strip("'\"")
            v_clean = v_part.strip().strip("'\"")
            if current_section and "." not in k_clean:
                k_clean = f"{current_section}.{k_clean}"
            parsed_dict[k_clean] = v_clean

    # Apply group/alias keys first, then exact `Service.field` keys so specific
    # `Service.field` overrides always take precedence over broader aliases.
    exact_entries: List[Tuple[str, Any]] = []
    for raw_k, raw_v in parsed_dict.items():
        k_str = str(raw_k).strip()
        if k_str in FINANCIAL_LIMIT_SPECS or k_str.lower() in _LOWER_TO_CANONICAL_KEY:
            exact_entries.append((k_str, raw_v))
            continue
        try:
            target_keys = resolve_limit_keys(k_str)
            for canonical_k in target_keys:
                spec = FINANCIAL_LIMIT_SPECS[canonical_k]
                clean_v = str(raw_v).replace("_", "").replace(",", "").strip()
                if spec["api_format"] == "int64":
                    limits[canonical_k] = int(float(clean_v))
                else:
                    limits[canonical_k] = float(clean_v)
        except Exception:
            continue

    for k_str, raw_v in exact_entries:
        try:
            canonical_k = resolve_limit_key(k_str)
            spec = FINANCIAL_LIMIT_SPECS[canonical_k]
            clean_v = str(raw_v).replace("_", "").replace(",", "").strip()
            if spec["api_format"] == "int64":
                limits[canonical_k] = int(float(clean_v))
            else:
                limits[canonical_k] = float(clean_v)
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
    """Formats the complete config/financial_limits file keyed by Service.field."""
    lines = [
        "# ==============================================================================",
        "# Google Ads API Financial Transaction Upper Limits Configuration (Service.field)",
        "# ==============================================================================",
        "# Specify upper limits for financial transactions using `<Service>.<field>` keys.",
        "# All values MUST be in the exact numeric format required by the Google Ads API",
        "# call for that service and field (see the monetary unit noted for each entry).",
        "#",
        "# Each value is set to 0 (for int64 fields) or 0.0 (for double/float fields) so",
        "# that financial fields are NOT modifiable by default. The user must supply a",
        "# value greater than zero (> 0) to make a Service.field modifiable. The supplied",
        "# value is the upper limit.",
        "#",
        "# If any mutation attempts to modify a Service.field whose value is 0 / 0.0, or",
        "# attempts a financial transaction exceeding the supplied upper limit (> 0), the",
        "# mutate functions and HITL guard will return an error, inform the user at the",
        "# HITL step, and refuse to execute the command.",
        "#",
        "# MONETARY & NUMERIC UNITS USED BY GOOGLE ADS API SERVICES:",
        "# 1. micros (int64):",
        "#    1 unit of account currency = 1,000,000 micros (e.g., 50000000 = 50.00 currency units).",
        "# 2. currency_units (double / float):",
        "#    Standard account/conversion currency units (NOT micros; e.g., 100.50 = 100.50 currency units).",
        "# 3. decimal_ratio (double / float):",
        "#    Decimal ratio or multiplier (e.g., 2.5 = 250% Target ROAS; 1.5 = +50% bid modifier).",
        "# 4. micros_proportion (int64):",
        "#    Proportion in micros where 1,000,000 = 100% (e.g., 200000 = 20% Percent CPC or commission).",
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
        proto_str = ", ".join(spec.get("protobuf_paths", spec["api_fields"]))
        monetary_unit = spec["monetary_unit"]
        unit_desc = spec["unit_description"]

        val = limits.get(key, spec["default"])
        if spec["api_format"] == "int64":
            formatted_val = str(int(val))
        else:
            formatted_val = str(float(val))

        lines.append(f"# Service: {services_str}")
        lines.append(f"# API Field: {proto_str}")
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
        for canonical_k in resolve_limit_keys(raw_k):
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
        return f"{val} (NOT MODIFIABLE — supply > 0 to set upper limit)"
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
    """Formats all Service.field financial transaction limits as a readable report."""
    lines = [
        "==========================================================================================",
        "GOOGLE ADS API FINANCIAL TRANSACTION UPPER LIMITS (Service.field)",
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
        lines.append(
            f"      Protobuf Path : {', '.join(spec.get('protobuf_paths', spec['api_fields']))}"
        )
    lines.append(
        "\n=========================================================================================="
    )
    return "\n".join(lines)


def run_interactive_prompt(
    config_dir: Optional[str] = None,
    config_file: Optional[str] = None,
) -> str:
    """Interactively prompts the user to set upper limits for Service.field transaction types."""
    current_limits, active_path = read_financial_limits(
        config_dir=config_dir, config_file=config_file
    )
    print(
        "Configure Google Ads API Financial Transaction Upper Limits (Service.field)\n"
        "Press Enter to keep the current value, enter > 0 to make modifiable up to that upper limit, or 0 to make non-modifiable.\n"
        "All values must be entered in the exact API format noted for each Service.field.\n"
    )
    updates: Dict[str, Union[int, float]] = {}
    for key, spec in FINANCIAL_LIMIT_SPECS.items():
        cur_val = current_limits.get(key, spec["default"])
        prompt = (
            f"{key}\n"
            f"  Service      : {', '.join(spec['services'])}\n"
            f"  API Field    : {', '.join(spec.get('protobuf_paths', spec['api_fields']))}\n"
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
            "Configure upper limits for Google Ads API financial transactions by Service.field in config/financial_limits. "
            "All values must be specified in the exact numeric format required by the Google Ads API call "
            "for each service and field (int64 micros, double currency_units, double decimal_ratio, or int64 micros_proportion)."
        )
    )
    parser.add_argument(
        "--list",
        "--show",
        dest="show",
        action="store_true",
        help="List all Service.field financial transaction limits, their monetary units, and current upper limits.",
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
        metavar="SERVICE.FIELD=AMOUNT",
        help=(
            "Set an upper limit (> 0) for a Service.field (or *.field / group alias) in API format "
            "(e.g., --set CampaignBudgetService.amount_micros=100000000 --set ConversionUploadService.conversion_value=500.0). "
            "May be specified multiple times."
        ),
    )
    parser.add_argument(
        "--type",
        dest="txn_type",
        default=None,
        help="Service.field key (or *.field / alias) to configure with --amount.",
    )
    parser.add_argument(
        "--amount",
        dest="amount",
        default=None,
        help="Upper limit amount (> 0 to make modifiable) in the exact format required by the API call (used with --type).",
    )
    parser.add_argument(
        "--reset",
        dest="reset_keys",
        action="append",
        default=[],
        metavar="SERVICE.FIELD",
        help="Reset the specified Service.field (or alias) to 0 / 0.0 (not modifiable).",
    )
    parser.add_argument(
        "--reset-all",
        action="store_true",
        help="Reset all Service.field financial transaction limits to 0 / 0.0 (not modifiable by default).",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactively prompt for each Service.field financial transaction limit.",
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

    # Dedicated per-Service.field and shorthand CLI flags
    type_group = parser.add_argument_group(
        "Service.field & Shorthand Flags (values in exact Google Ads API format)"
    )
    for key, spec in FINANCIAL_LIMIT_SPECS.items():
        flag_dot = "--" + key
        flag_dash = "--" + key.lower().replace(".", "-").replace("_", "-")
        flags = [flag_dot] if flag_dot == flag_dash else [flag_dot, flag_dash]
        type_group.add_argument(
            *flags,
            dest=f"limit__{key}",
            default=None,
            metavar=f"{spec['api_format'].upper()}_{spec['monetary_unit'].upper()}",
            help=(
                f"Upper limit for {key} [{spec['monetary_unit']} ({spec['api_format']}): "
                f"{spec['unit_description']}]"
            ),
        )

    # Also support shorthand group flags (e.g., --campaign-budget-amount-micros, --target-cpa-micros)
    added_alias_flags = set()
    for alias_key in list(_GROUP_ALIAS_FIELDS.keys()) + list(_FIELD_UNIT_META.keys()):
        flag_name = "--" + alias_key.replace("_", "-")
        if flag_name in added_alias_flags or alias_key in FINANCIAL_LIMIT_SPECS:
            continue
        added_alias_flags.add(flag_name)
        type_group.add_argument(
            flag_name,
            dest=f"alias__{alias_key}",
            default=None,
            help=argparse.SUPPRESS,
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
            for canonical in resolve_limit_keys(rk):
                updates[canonical] = FINANCIAL_LIMIT_SPECS[canonical]["default"]

        if (args.txn_type is not None) ^ (args.amount is not None):
            print(
                "[set_financial_limits] Error: --type and --amount must be provided together.",
                file=sys.stderr,
            )
            return 2

        if args.txn_type is not None and args.amount is not None:
            for canonical in resolve_limit_keys(args.txn_type):
                updates[canonical] = parse_and_validate_limit_amount(
                    canonical, args.amount
                )

        for item in args.set_items:
            if "=" not in item:
                raise ValueError(
                    f"Invalid --set argument '{item}'. Expected format: SERVICE.FIELD=AMOUNT "
                    f"(e.g., --set CampaignBudgetService.amount_micros=100000000)."
                )
            k_part, v_part = item.split("=", 1)
            for canonical in resolve_limit_keys(k_part):
                updates[canonical] = parse_and_validate_limit_amount(canonical, v_part)

        for alias_key in list(_GROUP_ALIAS_FIELDS.keys()) + list(_FIELD_UNIT_META.keys()):
            flag_val = getattr(args, f"alias__{alias_key}", None)
            if flag_val is not None:
                for canonical in resolve_limit_keys(alias_key):
                    updates[canonical] = parse_and_validate_limit_amount(
                        canonical, flag_val
                    )

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
                    "service": spec["service"],
                    "field": spec["field"],
                    "monetary_unit": spec["monetary_unit"],
                    "api_format": spec["api_format"],
                    "unit_description": spec["unit_description"],
                    "services": spec["services"],
                    "api_fields": spec["api_fields"],
                    "protobuf_paths": spec.get("protobuf_paths", spec["api_fields"]),
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

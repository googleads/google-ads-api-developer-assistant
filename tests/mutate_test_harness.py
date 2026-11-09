#!/usr/bin/env python3
"""Standalone command-line test harness for Google Ads API mutate and write functions.

Executes end-to-end validation of discovered Google Ads API write RPCs against a
verified Google Ads Test Account with a fail-closed pre-flight gate, client-side
financial upper-limit guardrail, dependency-ordered fixture lifecycle, and
0600-permissioned JSONL audit logging.
"""

import argparse
import builtins
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import getpass
import importlib
import inspect
import json
import os
import pkgutil
import re
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple
import uuid

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf.json_format import MessageToDict
import grpc
import yaml

# ==============================================================================
# Constants & Configuration Defaults
# ==============================================================================

DEFAULT_CONFIG_PATH = "config/google-ads.yaml"
DEFAULT_ASSISTANT_CONFIG_PATH = "config/assistant_config"
DEFAULT_API_VERSION = "v26"
AUDIT_LOG_DIR = os.path.join(".", "saved", "mutate_test_logs")

PREFLIGHT_GAQL_QUERY = """
SELECT customer.id, customer.descriptive_name, customer.test_account, customer.status
FROM customer
LIMIT 1
""".strip()

READ_ONLY_METHOD_PREFIXES: Tuple[str, ...] = (
    "search",
    "get",
    "list",
    "generate",
    "suggest",
    "quote",
    "fetch",
)

# Policy: Only `create` and `update` mutations are permitted; `remove_*` and `delete_*` RPCs are prohibited.
PROHIBITED_DELETION_METHOD_PREFIXES: Tuple[str, ...] = (
    "remove",
    "delete",
)

PROHIBITED_DELETION_SERVICES = frozenset({
    "AutomaticallyCreatedAssetRemovalService",
})

GAPIC_HELPER_METHODS = frozenset({
    "common_billing_account_path",
    "common_folder_path",
    "common_location_path",
    "common_organization_path",
    "common_project_path",
    "from_service_account_file",
    "from_service_account_info",
    "from_service_account_json",
    "get_mtls_endpoint_and_cert_source",
    "get_transport_class",
    "parse_common_billing_account_path",
    "parse_common_folder_path",
    "parse_common_location_path",
    "parse_common_organization_path",
    "parse_common_project_path",
    "universe_domain",
})

FINANCIAL_PAYLOAD_FIELDS = frozenset({
    "amount_micros",
    "total_amount_micros",
    "cpc_bid_micros",
    "cpm_bid_micros",
    "cpv_bid_micros",
    "target_cpa_micros",
    "spending_limit_micros",
    "proposed_spending_limit_micros",
    "approved_spending_limit_micros",
    "recommended_budget_amount_micros",
    "new_budget_amount_micros",
    "new_campaign_budget_amount_micros",
    "budget_micros_to_move",
    "budget_amount_micros",
    "campaign_budget_amount_micros",
    "max_budget_micros",
    "commission_rate_micros",
    "transaction_amount_micros",
    "lifetime_value_micros",
    "average_purchase_value_micros",
    "restatement_value",
    "conversion_value",
    "unit_price",
    "local_transaction_cost",
    "additional_value",
    "additional_high_lifetime_value",
    "target_cpa_multiplier",
    "target_roas_multiplier",
    "target_multiplier",
    "value_multiplier",
    "high_lifetime_value_multiplier",
})

FINANCIAL_SERVICES = frozenset({
    "AccountBudgetProposalService",
    "AdGroupBidModifierService",
    "AdGroupCriterionService",
    "AdGroupService",
    "AssetService",
    "BiddingDataExclusionService",
    "BiddingSeasonalityAdjustmentService",
    "BiddingStrategyService",
    "BillingSetupService",
    "CampaignBidModifierService",
    "CampaignBudgetService",
    "CampaignCriterionService",
    "CampaignGoalConfigService",
    "CampaignLifecycleGoalService",
    "CampaignService",
    "ConversionActionService",
    "ConversionAdjustmentUploadService",
    "ConversionUploadService",
    "ConversionValueRuleService",
    "ConversionValueRuleSetService",
    "CustomerLifecycleGoalService",
    "ExperimentArmService",
    "ExperimentService",
    "GoalService",
    "GoogleAdsService",
    "KeywordPlanAdGroupKeywordService",
    "KeywordPlanAdGroupService",
    "KeywordPlanCampaignService",
    "OfflineUserDataJobService",
    "RecommendationService",
    "ReservationService",
    "UserDataService",
})

OAUTH_SECRET_KEYS = frozenset({
    "client_secret",
    "refresh_token",
    "private_key",
    "json_key",
})

# Topological ordering priority for services that create parent resources
SERVICE_EXECUTION_PRIORITY: Dict[str, int] = {
    "CampaignBudgetService": 10,
    "BiddingStrategyService": 12,
    "CampaignService": 15,
    "AdGroupService": 20,
    "AdGroupAdService": 25,
    "AdGroupCriterionService": 26,
    "LabelService": 30,
    "AssetService": 32,
    "AssetSetService": 34,
    "SharedSetService": 36,
    "ConversionActionService": 38,
    "ConversionCustomVariableService": 39,
    "UserListService": 40,
    "CustomizerAttributeService": 42,
    "ConversionValueRuleService": 44,
    "ConversionValueRuleSetService": 45,
    "KeywordPlanService": 50,
    "KeywordPlanCampaignService": 51,
    "KeywordPlanCampaignKeywordService": 52,
    "KeywordPlanAdGroupService": 53,
    "KeywordPlanAdGroupKeywordService": 54,
    "BatchJobService": 55,
    "OfflineUserDataJobService": 56,
    "CampaignDraftService": 57,
    "ExperimentService": 58,
    "ExperimentArmService": 59,
}

METHOD_EXECUTION_PRIORITY: Dict[str, int] = {
    "mutate_batch_job": 1,
    "add_batch_job_operations": 2,
    "run_batch_job": 3,
    "create_offline_user_data_job": 1,
    "add_offline_user_data_job_operations": 2,
    "run_offline_user_data_job": 3,
    "mutate_campaign_drafts": 1,
    "promote_campaign_draft": 2,
    "mutate_experiments": 1,
    "schedule_experiment": 2,
    "promote_experiment": 3,
    "graduate_experiment": 4,
    "end_experiment": 5,
    "create_data_link": 1,
    "update_data_link": 2,
    "create_product_link": 1,
    "create_product_link_invitation": 1,
    "update_product_link_invitation": 2,
    "create_you_tube_video_upload": 1,
    "update_you_tube_video_upload": 2,
}


# ==============================================================================
# Runtime Config File Resolution Shim
# ==============================================================================

_ORIG_OPEN = builtins.open


def _candidate_plugin_config_dirs() -> List[str]:
    """Returns candidate config directories in priority order."""
    this_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(this_dir, "../.."))
    candidates = [
        os.path.abspath("config"),
        os.path.join(
            repo_root,
            "plugins",
            "google-ads-api-developer-assistant",
            "config",
        ),
        os.path.join(this_dir, "../config"),
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/config"
        ),
        os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/config"
        ),
    ]
    deduped: List[str] = []
    for path in candidates:
        norm = os.path.normpath(path)
        if norm not in deduped:
            deduped.append(norm)
    return deduped


def resolve_config_file_path(path: str) -> str:
    """Resolves a relative config path against local and plugin config directories."""
    if os.path.exists(path) or os.path.isabs(path):
        return path
    norm = os.path.normpath(path)
    if norm == os.path.normpath(DEFAULT_CONFIG_PATH):
        env_cfg = os.environ.get("GOOGLE_ADS_CONFIGURATION_FILE_PATH", "").strip()
        if env_cfg and os.path.isfile(env_cfg):
            return env_cfg
        for cfg_dir in _candidate_plugin_config_dirs():
            candidate = os.path.join(cfg_dir, "google-ads.yaml")
            if os.path.isfile(candidate):
                return candidate
    elif norm == os.path.normpath(DEFAULT_ASSISTANT_CONFIG_PATH):
        for cfg_dir in _candidate_plugin_config_dirs():
            candidate = os.path.join(cfg_dir, "assistant_config")
            if os.path.isfile(candidate):
                return candidate
    return path


def _install_open_shim() -> None:
    """Ensures open('config/google-ads.yaml') resolves across workspace layouts."""
    if getattr(builtins.open, "_is_harness_shim", False):
        return

    def _shimmed_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
        if isinstance(file, str) and "r" in mode and not os.path.exists(file):
            file = resolve_config_file_path(file)
        return _ORIG_OPEN(file, mode, *args, **kwargs)

    setattr(_shimmed_open, "_is_harness_shim", True)
    builtins.open = _shimmed_open


# ==============================================================================
# Exceptions & Data Structures
# ==============================================================================


class FinancialLimitExceededError(PermissionError):
    """Raised client-side when a request payload exceeds max_financial_mutate_micros."""

    def __init__(
        self,
        field_name: str,
        observed_value: float,
        limit_micros: int,
    ) -> None:
        self.field_name = field_name
        self.observed_value = observed_value
        self.limit_micros = limit_micros
        super().__init__(
            f"Client-side financial guardrail blocked RPC: field '{field_name}' "
            f"value {observed_value} exceeds max_financial_mutate_micros ({limit_micros})."
        )


@dataclass
class DiscoveredWriteMethod:
    """Metadata for a dynamically discovered Google Ads API write RPC method."""

    service_name: str
    module_name: str
    method_snake_name: str
    grpc_method_name: str
    request_type_name: str
    has_validate_only: bool
    has_response_content_type: bool
    has_partial_failure: bool
    operation_field_name: Optional[str] = None
    operation_is_repeated: bool = False
    operation_type_name: Optional[str] = None
    operation_subfields: Tuple[str, ...] = ()


@dataclass
class MethodTestSummary:
    """Outcome summary for a single service write method."""

    service_name: str
    grpc_method_name: str
    method_snake_name: str
    success_passed: bool
    failure_passed: bool
    success_status: str
    failure_status: str
    notes: str = ""


@dataclass
class FixtureRegistry:
    """Holds resource names of dependency-ordered test fixtures for a test run."""

    customer_id: str
    run_tag: str
    max_financial_mutate_micros: int
    resources: Dict[str, str] = field(default_factory=dict)
    teardown_queue: List[Tuple[str, str, str, str]] = field(default_factory=list)

    @property
    def safe_budget_micros(self) -> int:
        if self.max_financial_mutate_micros > 0:
            return min(10_000_000, self.max_financial_mutate_micros)
        return 10_000_000

    @property
    def safe_bid_micros(self) -> int:
        if self.max_financial_mutate_micros > 0:
            return min(1_000_000, self.max_financial_mutate_micros)
        return 1_000_000

    def get_or_fallback(self, key: str, collection: str, fallback_id: str = "999999999") -> str:
        """Returns a provisioned fixture resource name or a structurally valid fallback."""
        val = self.resources.get(key)
        if val:
            return val
        return f"customers/{self.customer_id}/{collection}/{fallback_id}"

    def register(
        self,
        key: str,
        resource_name: str,
        teardown_service: Optional[str] = None,
        teardown_method: Optional[str] = None,
        teardown_op_type: Optional[str] = None,
    ) -> None:
        """Registers a created resource and queues it for reverse-order teardown."""
        if not resource_name:
            return
        self.resources[key] = resource_name
        if teardown_service and teardown_method and teardown_op_type:
            entry = (
                teardown_service,
                teardown_method,
                teardown_op_type,
                resource_name,
            )
            if entry not in self.teardown_queue:
                self.teardown_queue.append(entry)


# ==============================================================================
# Configuration & Secret Redaction Helpers
# ==============================================================================


def redact_secrets(obj: Any, _depth: int = 0) -> Any:
    """Recursively redacts OAuth and service account secrets prior to serialization."""
    if _depth > 12:
        return str(obj)
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        cleaned: Dict[str, Any] = {}
        for k, v in obj.items():
            k_str = str(k)
            if k_str.strip().lower() in OAUTH_SECRET_KEYS:
                cleaned[k_str] = "[REDACTED]"
            else:
                cleaned[k_str] = redact_secrets(v, _depth + 1)
        return cleaned
    if isinstance(obj, (list, tuple, set)):
        return [redact_secrets(item, _depth + 1) for item in obj]
    return str(obj)


def parse_assistant_config(config_path: str) -> Dict[str, Any]:
    """Parses TOML or key=value pairs from config/assistant_config."""
    resolved = resolve_config_file_path(config_path)
    if not os.path.isfile(resolved):
        return {}
    try:
        with open(resolved, "r", encoding="utf-8") as f:
            raw_text = f.read()
    except OSError:
        return {}

    data: Dict[str, Any] = {}
    try:
        import tomllib  # type: ignore

        loaded = tomllib.loads(raw_text)
        if isinstance(loaded, dict):
            data.update(loaded)
    except Exception:
        pass

    if not data:
        for raw_line in raw_text.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line or line.startswith("[") or "=" not in line:
                continue
            k_part, v_part = line.split("=", 1)
            k = k_part.strip()
            v_raw = v_part.strip()
            if (v_raw.startswith('"') and v_raw.endswith('"')) or (
                v_raw.startswith("'") and v_raw.endswith("'")
            ):
                data[k] = v_raw[1:-1]
            elif v_raw.lower() in ("true", "false"):
                data[k] = v_raw.lower() == "true"
            else:
                clean_num = v_raw.replace("_", "").replace(",", "")
                if re.match(r"^-?\d+$", clean_num):
                    data[k] = int(clean_num)
                elif re.match(r"^-?\d+\.\d+$", clean_num):
                    data[k] = float(clean_num)
                else:
                    data[k] = v_raw

    if "api_version" in data and data["api_version"] is not None:
        ver = str(data["api_version"]).strip().strip("'\"")
        if ver and not ver.startswith("v") and ver.isdigit():
            ver = f"v{ver}"
        data["api_version"] = ver

    if "customer_id" in data and data["customer_id"] is not None:
        data["customer_id"] = (
            str(data["customer_id"]).strip().strip("'\"").replace("-", "")
        )

    if "max_financial_mutate_micros" in data and data["max_financial_mutate_micros"] is not None:
        try:
            raw_limit = str(data["max_financial_mutate_micros"]).replace("_", "").replace(",", "").strip()
            data["max_financial_mutate_micros"] = int(float(raw_limit))
        except (ValueError, TypeError):
            data["max_financial_mutate_micros"] = None

    return data


def extract_client_identity_metadata(
    config_path: str,
    client: Optional[Any] = None,
) -> Tuple[str, str, str]:
    """Returns (username, gcp_project_number, login_customer_id) with secrets redacted."""
    try:
        username = getpass.getuser()
    except Exception:
        username = os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"

    gcp_project_number = (
        os.environ.get("GCP_PROJECT_NUMBER")
        or os.environ.get("GOOGLE_CLOUD_PROJECT")
        or ""
    ).strip()
    login_customer_id = ""

    if client is not None:
        client_login = getattr(client, "login_customer_id", None)
        if client_login:
            login_customer_id = str(client_login).strip().replace("-", "")
        creds = getattr(client, "credentials", None)
        if creds is not None:
            if not gcp_project_number:
                quota_proj = getattr(creds, "quota_project_id", None) or getattr(
                    creds, "project_id", None
                )
                if quota_proj:
                    gcp_project_number = str(quota_proj).strip()
            sa_email = getattr(creds, "service_account_email", None)
            if sa_email and username in ("unknown", "root", ""):
                username = str(sa_email).strip()

    resolved_yaml = resolve_config_file_path(config_path)
    if os.path.isfile(resolved_yaml):
        try:
            with open(resolved_yaml, "r", encoding="utf-8") as f:
                yaml_data = yaml.safe_load(f) or {}
            if isinstance(yaml_data, dict):
                if not login_customer_id and yaml_data.get("login_customer_id"):
                    login_customer_id = (
                        str(yaml_data["login_customer_id"]).strip().replace("-", "")
                    )
                if not gcp_project_number:
                    for key in ("gcp_project_number", "project_number", "project_id"):
                        if yaml_data.get(key):
                            gcp_project_number = str(yaml_data[key]).strip()
                            break
                if not gcp_project_number and yaml_data.get("client_id"):
                    client_id_str = str(yaml_data["client_id"]).strip()
                    m = re.match(r"^(\d{6,})-", client_id_str)
                    if m:
                        gcp_project_number = m.group(1)
                json_key_path = yaml_data.get("json_key_file_path")
                if json_key_path and os.path.isfile(str(json_key_path)):
                    try:
                        with open(str(json_key_path), "r", encoding="utf-8") as jf:
                            sa_data = json.load(jf)
                        if isinstance(sa_data, dict):
                            if not gcp_project_number:
                                cid = str(sa_data.get("client_id", "")).strip()
                                if cid.isdigit():
                                    gcp_project_number = cid
                                elif sa_data.get("project_id"):
                                    gcp_project_number = str(sa_data["project_id"]).strip()
                            if username in ("unknown", "") and sa_data.get("client_email"):
                                username = str(sa_data["client_email"]).strip()
                    except Exception:
                        pass
        except Exception:
            pass

    return (
        username or "unknown",
        gcp_project_number or "unknown",
        login_customer_id or "",
    )


# ==============================================================================
# gRPC Metadata & Status Capture Interceptor
# ==============================================================================


class RequestIdCaptureInterceptor(
    grpc.UnaryUnaryClientInterceptor,
    grpc.UnaryStreamClientInterceptor,
):
    """Captures trailing gRPC request-id and status code from underlying calls."""

    def __init__(self) -> None:
        self.last_request_id: Optional[str] = None
        self.last_status_code: Optional[str] = None

    def reset(self) -> None:
        self.last_request_id = None
        self.last_status_code = None

    def _extract_from_call(self, call: Any) -> None:
        try:
            code = call.code()
            if code is not None:
                self.last_status_code = getattr(code, "name", str(code))
        except Exception:
            pass
        try:
            trailing = call.trailing_metadata()
            if trailing:
                for key, val in trailing:
                    if key == "request-id" and val:
                        self.last_request_id = (
                            val.decode("utf-8", errors="replace")
                            if isinstance(val, bytes)
                            else str(val)
                        )
                        break
        except Exception:
            pass

    def intercept_unary_unary(
        self,
        continuation: Callable[[ Any, Any], Any],
        client_call_details: Any,
        request: Any,
    ) -> Any:
        call = continuation(client_call_details, request)
        self._extract_from_call(call)
        return call

    def intercept_unary_stream(
        self,
        continuation: Callable[[Any, Any], Any],
        client_call_details: Any,
        request: Any,
    ) -> Any:
        call = continuation(client_call_details, request)
        try:
            call.add_done_callback(self._extract_from_call)
        except Exception:
            pass
        return call


# ==============================================================================
# Protobuf Serialization & Audit Trail Logger
# ==============================================================================


def serialize_proto_message(
    msg: Any,
    *,
    is_request: bool = False,
    is_response: bool = False,
) -> Optional[Dict[str, Any]]:
    """Serializes a Protobuf or proto-plus message via MessageToDict with field preservation."""
    if msg is None:
        return None
    if isinstance(msg, dict):
        return redact_secrets(msg)

    pb_obj = getattr(msg, "_pb", msg)
    result: Dict[str, Any] = {}
    if hasattr(pb_obj, "DESCRIPTOR"):
        try:
            result = MessageToDict(pb_obj, preserving_proto_field_name=True)
        except Exception:
            result = {}
    else:
        to_dict_fn = getattr(type(msg), "to_dict", None)
        if callable(to_dict_fn):
            try:
                result = to_dict_fn(msg, preserving_proto_field_name=True)
            except TypeError:
                try:
                    result = to_dict_fn(msg)
                except Exception:
                    result = {}

    if hasattr(pb_obj, "DESCRIPTOR"):
        field_names = {f.name for f in pb_obj.DESCRIPTOR.fields}
        if is_request:
            if "customer_id" in field_names and "customer_id" not in result:
                result["customer_id"] = str(getattr(msg, "customer_id", "") or "")
            if "validate_only" in field_names and "validate_only" not in result:
                result["validate_only"] = bool(getattr(msg, "validate_only", False))
            if "operations" in field_names and "operations" not in result:
                result["operations"] = []
        elif is_response:
            if "partial_failure_error" in field_names and "partial_failure_error" not in result:
                result["partial_failure_error"] = None

    return redact_secrets(result)


def serialize_google_ads_exception(ex: BaseException) -> Tuple[str, Optional[str], Dict[str, Any]]:
    """Extracts (grpc_status, request_id, structured_error_dict) from an exception."""
    request_id: Optional[str] = getattr(ex, "request_id", None)
    grpc_status = "UNKNOWN"

    rpc_err = getattr(ex, "error", ex)
    if hasattr(rpc_err, "code") and callable(rpc_err.code):
        try:
            code_obj = rpc_err.code()
            if code_obj is not None:
                grpc_status = getattr(code_obj, "name", str(code_obj))
        except Exception:
            pass

    if not request_id and hasattr(rpc_err, "trailing_metadata") and callable(rpc_err.trailing_metadata):
        try:
            for k, v in rpc_err.trailing_metadata() or ():
                if k == "request-id" and v:
                    request_id = v.decode("utf-8", errors="replace") if isinstance(v, bytes) else str(v)
                    break
        except Exception:
            pass

    top_message = ""
    if hasattr(rpc_err, "details") and callable(rpc_err.details):
        try:
            top_message = str(rpc_err.details() or "")
        except Exception:
            top_message = ""
    if not top_message:
        top_message = str(ex)

    failure = getattr(ex, "failure", None)
    if failure is not None:
        if grpc_status == "UNKNOWN":
            grpc_status = "INVALID_ARGUMENT"
        failure_dict = serialize_proto_message(failure) or {}
        if not request_id and failure_dict.get("request_id"):
            request_id = str(failure_dict["request_id"])
        errors_list = failure_dict.get("errors", [])
        error_payload: Dict[str, Any] = {
            "message": top_message,
            "errors": errors_list,
        }
        return grpc_status, request_id, redact_secrets(error_payload)

    if isinstance(ex, FinancialLimitExceededError):
        return (
            "BLOCKED_CLIENT_SIDE",
            None,
            {
                "code": "FINANCIAL_LIMIT_BLOCKED",
                "message": str(ex),
                "field_name": ex.field_name,
                "observed_value": ex.observed_value,
                "max_financial_mutate_micros": ex.limit_micros,
                "errors": [
                    {
                        "error_code": {" financial_guardrail": "MAX_FINANCIAL_MUTATE_MICROS_EXCEEDED"},
                        "message": str(ex),
                        "location": {
                            "field_path_elements": [{"field_name": ex.field_name}]
                        },
                    }
                ],
            },
        )

    return (
        grpc_status,
        request_id,
        redact_secrets({
            "message": top_message,
            "exception_type": type(ex).__name__,
            "errors": [],
        }),
    )


class AuditLogger:
    """Writes 0600-permissioned, immediately flushed JSONL audit records."""

    def __init__(
        self,
        conversation_id: str,
        username: str,
        api_version: str,
        gcp_project_number: str,
        login_customer_id: str,
        log_dir: str = AUDIT_LOG_DIR,
    ) -> None:
        self.conversation_id = self._sanitize_conversation_id(conversation_id)
        self.username = username
        self.api_version = api_version
        self.gcp_project_number = gcp_project_number
        self.login_customer_id = login_customer_id
        self.log_dir = os.path.abspath(log_dir)
        os.makedirs(self.log_dir, exist_ok=True)

        utc_now = datetime.now(timezone.utc)
        ts_prefix = utc_now.strftime("%Y_%m_%d_%H_%M_%S")
        self.filename = f"{ts_prefix}_{self.conversation_id}.jsonl"
        self.log_path = os.path.join(self.log_dir, self.filename)

        fd = os.open(
            self.log_path,
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o600,
        )
        os.close(fd)
        self._enforce_permissions()

    @staticmethod
    def _sanitize_conversation_id(raw_id: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", (raw_id or "").strip())
        return cleaned or "standalone"

    def _enforce_permissions(self) -> None:
        if os.path.isfile(self.log_path):
            try:
                os.chmod(self.log_path, 0o600)
            except OSError:
                pass

    @staticmethod
    def format_utc_timestamp() -> str:
        now = datetime.now(timezone.utc)
        return now.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def write_record(
        self,
        *,
        service: str,
        method: str,
        scenario: str,
        assertion_passed: bool,
        request_payload: Dict[str, Any],
        grpc_status: str,
        request_id: Optional[str],
        duration_ms: int,
        response_payload: Optional[Dict[str, Any]],
        error_payload: Optional[Dict[str, Any]],
        extra_test_case: Optional[Dict[str, Any]] = None,
        top_level_status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Appends and flushes a single JSONL audit record."""
        test_case_dict: Dict[str, Any] = {
            "scenario": scenario,
            "assertion_passed": bool(assertion_passed),
        }
        if extra_test_case:
            test_case_dict.update(extra_test_case)

        record: Dict[str, Any] = {
            "datetime": self.format_utc_timestamp(),
            "username": self.username,
            "service": service,
            "test_case": test_case_dict,
            "request": {
                "method": method,
                "api_version": self.api_version,
                "gcp_project_number": self.gcp_project_number,
                "login_customer_id": self.login_customer_id,
                "payload": redact_secrets(request_payload),
            },
            "response": {
                "grpc_status": grpc_status,
                "request_id": request_id,
                "duration_ms": int(duration_ms),
                "payload": redact_secrets(response_payload) if response_payload is not None else None,
                "error": redact_secrets(error_payload) if error_payload is not None else None,
            },
        }
        if top_level_status:
            record["status"] = top_level_status

        line_bytes = (json.dumps(record, default=str) + "\n").encode("utf-8")
        fd = os.open(
            self.log_path,
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o600,
        )
        try:
            os.write(fd, line_bytes)
            os.fsync(fd)
        finally:
            os.close(fd)
        self._enforce_permissions()
        return record


# ==============================================================================
# Financial Upper-Limit Guardrail
# ==============================================================================


def inspect_payload_for_financial_limits(
    payload: Any,
    max_financial_mutate_micros: int,
    _path: str = "",
    _depth: int = 0,
) -> Optional[Tuple[str, float]]:
    """Inspects an outgoing request payload dictionary for financial fields exceeding the cap.

    Returns (field_path, observed_value) if any field exceeds max_financial_mutate_micros,
    or None if all financial fields are within the allowed limit.
    """
    if _depth > 14 or max_financial_mutate_micros <= 0:
        return None

    if isinstance(payload, dict):
        for raw_k, val in payload.items():
            key = str(raw_k).strip()
            field_path = f"{_path}.{key}" if _path else key
            if key in FINANCIAL_PAYLOAD_FIELDS:
                if key == "restatement_value" and isinstance(val, dict):
                    adj_val = _coerce_number(val.get("adjusted_value"))
                    if adj_val is not None and adj_val > max_financial_mutate_micros:
                        return (f"{field_path}.adjusted_value", adj_val)
                else:
                    num = _coerce_number(val)
                    if num is not None and num > max_financial_mutate_micros:
                        return (field_path, num)
            sub_violation = inspect_payload_for_financial_limits(
                val,
                max_financial_mutate_micros,
                _path=field_path,
                _depth=_depth + 1,
            )
            if sub_violation is not None:
                return sub_violation
    elif isinstance(payload, list):
        for idx, item in enumerate(payload):
            sub_violation = inspect_payload_for_financial_limits(
                item,
                max_financial_mutate_micros,
                _path=f"{_path}[{idx}]",
                _depth=_depth + 1,
            )
            if sub_violation is not None:
                return sub_violation

    return None


def _coerce_number(val: Any) -> Optional[float]:
    if isinstance(val, bool) or val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        cleaned = val.strip().replace("_", "").replace(",", "")
        if re.match(r"^-?\d+(?:\.\d+)?$", cleaned):
            try:
                return float(cleaned)
            except ValueError:
                return None
    return None


def is_financial_service_scheduled(
    methods: Sequence[DiscoveredWriteMethod],
    service_filter: Optional[str] = None,
) -> bool:
    """Returns True if any scheduled service performs financial mutations."""
    if not service_filter:
        return True
    return any(m.service_name in FINANCIAL_SERVICES for m in methods)


def verify_financial_config_or_abort(
    max_financial_mutate_micros: Optional[int],
    assistant_config_path: str,
    financial_scheduled: bool,
) -> int:
    """Validates max_financial_mutate_micros in config/assistant_config if financial mutates run."""
    if not financial_scheduled:
        return int(max_financial_mutate_micros or 100_000_000)

    if max_financial_mutate_micros is None or max_financial_mutate_micros <= 0:
        print(
            f"CONFIGURATION ERROR: 'max_financial_mutate_micros' is missing or <= 0 in "
            f"'{assistant_config_path}' (got {max_financial_mutate_micros!r}).\n"
            f"To run financial mutate tests, add a positive integer micro limit to "
            f"'{assistant_config_path}', for example:\n"
            f"  max_financial_mutate_micros = 100000000  # 100.00 local currency units",
            file=sys.stderr,
        )
        sys.exit(2)

    return int(max_financial_mutate_micros)


# ==============================================================================
# Dynamic Discovery of Google Ads API Write Services & RPCs
# ==============================================================================


def snake_to_pascal(snake_str: str) -> str:
    """Converts a snake_case method name to its canonical PascalCase gRPC method name."""
    return "".join(part.capitalize() for part in snake_str.split("_") if part)


def discover_write_rpcs(
    api_version: str,
    service_filter: Optional[str] = None,
) -> List[DiscoveredWriteMethod]:
    """Introspects google.ads.googleads.<api_version> to enumerate all write services and RPCs."""
    svc_pkg_name = f"google.ads.googleads.{api_version}.services.services"
    types_pkg_name = f"google.ads.googleads.{api_version}.services.types"
    svc_pkg = importlib.import_module(svc_pkg_name)
    types_mod = importlib.import_module(types_pkg_name)

    norm_filter = None
    if service_filter:
        norm_filter = service_filter.strip().lower().replace("_", "")
        if not norm_filter.endswith("service"):
            norm_filter_with_svc = norm_filter + "service"
        else:
            norm_filter_with_svc = norm_filter

    discovered: List[DiscoveredWriteMethod] = []

    for _, mod_name, is_pkg in sorted(pkgutil.iter_modules(svc_pkg.__path__)):
        if not is_pkg:
            continue
        client_mod = importlib.import_module(f"{svc_pkg_name}.{mod_name}.client")
        for cls_name, cls_obj in inspect.getmembers(client_mod, inspect.isclass):
            if not cls_name.endswith("ServiceClient") or cls_name.endswith("AsyncClient"):
                continue
            service_name = cls_name[:-6]  # strip "Client"
            if service_name in PROHIBITED_DELETION_SERVICES:
                continue
            if norm_filter:
                svc_norm = service_name.lower().replace("_", "")
                if svc_norm not in (norm_filter, norm_filter_with_svc):
                    continue

            for m_name, m_obj in inspect.getmembers(cls_obj, predicate=inspect.isfunction):
                if (
                    m_name.startswith("_")
                    or m_name in GAPIC_HELPER_METHODS
                    or m_name.endswith("_path")
                    or m_name.startswith("parse_")
                ):
                    continue
                if any(
                    m_name == prefix or m_name.startswith(f"{prefix}_")
                    for prefix in READ_ONLY_METHOD_PREFIXES
                ):
                    continue
                if any(
                    m_name == prefix or m_name.startswith(f"{prefix}_")
                    for prefix in PROHIBITED_DELETION_METHOD_PREFIXES
                ):
                    continue

                sig = inspect.signature(m_obj)
                req_param = sig.parameters.get("request")
                req_ann = str(req_param.annotation) if req_param else ""
                req_type_name = req_ann.split("|")[0].strip().split(".")[-1]
                req_cls = getattr(types_mod, req_type_name, None)
                if req_cls is None:
                    try:
                        svc_types_mod = importlib.import_module(
                            f"{types_pkg_name}.{mod_name}"
                        )
                        req_cls = getattr(svc_types_mod, req_type_name, None)
                    except ImportError:
                        req_cls = None

                has_vo = False
                has_rct = False
                has_pf = False
                op_field_name: Optional[str] = None
                op_is_repeated = False
                op_type_name: Optional[str] = None
                op_subfields: Tuple[str, ...] = ()
                remove_only_op = False

                if req_cls is not None and hasattr(req_cls, "pb"):
                    pb_desc = req_cls.pb().DESCRIPTOR
                    f_map = {f.name: f for f in pb_desc.fields}
                    has_vo = "validate_only" in f_map
                    has_rct = "response_content_type" in f_map
                    has_pf = "partial_failure" in f_map
                    if "operations" in f_map or "operation" in f_map:
                        op_f = f_map.get("operations") or f_map.get("operation")
                        if op_f is not None:
                            op_field_name = op_f.name
                            op_is_repeated = bool(op_f.is_repeated)
                            if op_f.message_type is not None:
                                op_type_name = op_f.message_type.name
                                raw_subfields = tuple(
                                    sf.name for sf in op_f.message_type.fields
                                )
                                if (
                                    "remove" in raw_subfields
                                    and "create" not in raw_subfields
                                    and "update" not in raw_subfields
                                ):
                                    remove_only_op = True
                                op_subfields = tuple(
                                    sf_name
                                    for sf_name in raw_subfields
                                    if sf_name != "remove"
                                )

                if remove_only_op:
                    continue

                discovered.append(
                    DiscoveredWriteMethod(
                        service_name=service_name,
                        module_name=mod_name,
                        method_snake_name=m_name,
                        grpc_method_name=snake_to_pascal(m_name),
                        request_type_name=req_type_name,
                        has_validate_only=has_vo,
                        has_response_content_type=has_rct,
                        has_partial_failure=has_pf,
                        operation_field_name=op_field_name,
                        operation_is_repeated=op_is_repeated,
                        operation_type_name=op_type_name,
                        operation_subfields=op_subfields,
                    )
                )

    discovered.sort(
        key=lambda item: (
            SERVICE_EXECUTION_PRIORITY.get(item.service_name, 100),
            item.service_name,
            METHOD_EXECUTION_PRIORITY.get(item.method_snake_name, 50),
            item.method_snake_name,
        )
    )
    return discovered


def print_startup_manifest(
    api_version: str,
    customer_id: str,
    methods: Sequence[DiscoveredWriteMethod],
    log_path: str,
) -> None:
    """Prints the startup discovery manifest of state-changing services and write RPCs."""
    unique_services = sorted({m.service_name for m in methods})
    print("=" * 88)
    print(f"Google Ads API Mutate Test Harness — Startup Discovery Manifest ({api_version})")
    print("=" * 88)
    print(f"Target Customer ID  : {customer_id}")
    print(f"Discovered Services : {len(unique_services)}")
    print(f"Discovered Write RPCs: {len(methods)}")
    print(f"Audit Trail Log     : {log_path}")
    print("-" * 88)
    for idx, m in enumerate(methods, start=1):
        vo_tag = "validate_only" if m.has_validate_only else "live_only"
        rct_tag = ", MUTABLE_RESOURCE" if m.has_response_content_type else ""
        print(
            f"  [{idx:03d}] {m.service_name}.{m.method_snake_name} "
            f"(gRPC: {m.grpc_method_name}, req: {m.request_type_name} [{vo_tag}{rct_tag}])"
        )
    print("=" * 88)


# ==============================================================================
# Mandatory Test Account Pre-Flight Gate (Fail-Closed)
# ==============================================================================


def run_preflight_test_account_gate(
    client: GoogleAdsClient,
    customer_id: str,
    audit_logger: AuditLogger,
    interceptor: RequestIdCaptureInterceptor,
    max_financial_mutate_micros: Optional[int] = None,
    assistant_config_path: str = DEFAULT_ASSISTANT_CONFIG_PATH,
    financial_scheduled: bool = True,
) -> Dict[str, Any]:
    """Queries customer.test_account via GoogleAdsService.search and aborts with exit code 2 if not True."""
    interceptor.reset()
    t0 = time.perf_counter()

    req_payload = {
        "customer_id": str(customer_id),
        "query": PREFLIGHT_GAQL_QUERY,
    }

    try:
        try:
            ga_service = client.get_service(
                "GoogleAdsService", interceptors=[interceptor]
            )
        except TypeError:
            ga_service = client.get_service("GoogleAdsService")

        search_fn = getattr(ga_service, "search")
        try:
            search_req = client.get_type("SearchGoogleAdsRequest")
            search_req.customer_id = str(customer_id)
            search_req.query = PREFLIGHT_GAQL_QUERY
            rows = list(search_fn(request=search_req))
        except Exception:
            rows = list(search_fn(customer_id=str(customer_id), query=PREFLIGHT_GAQL_QUERY))
    except Exception as ex:
        duration_ms = int(round((time.perf_counter() - t0) * 1000))
        grpc_status, req_id, err_dict = serialize_google_ads_exception(ex)
        req_id = req_id or interceptor.last_request_id
        err_dict["code"] = "FATAL_NON_TEST_ACCOUNT"

        audit_logger.write_record(
            service="GoogleAdsService",
            method="Search",
            scenario="PREFLIGHT",
            assertion_passed=False,
            request_payload=req_payload,
            grpc_status=grpc_status,
            request_id=req_id,
            duration_ms=duration_ms,
            response_payload=None,
            error_payload=err_dict,
            extra_test_case={"status": "FATAL_NON_TEST_ACCOUNT"},
            top_level_status="FATAL_NON_TEST_ACCOUNT",
        )
        print(
            f"FATAL_NON_TEST_ACCOUNT: Pre-flight query failed for customer_id={customer_id!r}, "
            f"descriptive_name=None, test_account=False, status='QUERY_ERROR' ({ex}). "
            f"Executing zero mutate RPCs.",
            file=sys.stderr,
        )
        if financial_scheduled and (
            max_financial_mutate_micros is None or max_financial_mutate_micros <= 0
        ):
            print(
                f"CONFIGURATION ERROR: 'max_financial_mutate_micros' is also missing or <= 0 in "
                f"'{assistant_config_path}'. Set 'max_financial_mutate_micros = 100000000' in "
                f"'{assistant_config_path}'.",
                file=sys.stderr,
            )
        sys.exit(2)

    duration_ms = int(round((time.perf_counter() - t0) * 1000))
    req_id = interceptor.last_request_id

    if not rows:
        err_payload = {
            "code": "FATAL_NON_TEST_ACCOUNT",
            "message": "Pre-flight query returned no customer rows.",
            "errors": [],
        }
        audit_logger.write_record(
            service="GoogleAdsService",
            method="Search",
            scenario="PREFLIGHT",
            assertion_passed=False,
            request_payload=req_payload,
            grpc_status="NOT_FOUND",
            request_id=req_id,
            duration_ms=duration_ms,
            response_payload={"results": []},
            error_payload=err_payload,
            extra_test_case={"status": "FATAL_NON_TEST_ACCOUNT"},
            top_level_status="FATAL_NON_TEST_ACCOUNT",
        )
        print(
            f"FATAL_NON_TEST_ACCOUNT: Pre-flight query returned no rows for "
            f"customer_id={customer_id!r}, descriptive_name=None, test_account=False, status='NO_ROWS'. "
            f"Executing zero mutate RPCs.",
            file=sys.stderr,
        )
        sys.exit(2)

    first_row = rows[0]
    cust = getattr(first_row, "customer", None)
    acct_id = str(getattr(cust, "id", customer_id) if cust is not None else customer_id)
    desc_name = str(getattr(cust, "descriptive_name", "") if cust is not None else "")
    is_test_account = bool(getattr(cust, "test_account", False) is True) if cust is not None else False
    raw_status = getattr(cust, "status", "UNKNOWN") if cust is not None else "UNKNOWN"
    status_name = getattr(raw_status, "name", str(raw_status))

    resp_payload = {
        "results": [
            {
                "customer": {
                    "id": acct_id,
                    "descriptive_name": desc_name,
                    "test_account": is_test_account,
                    "status": status_name,
                }
            }
        ]
    }

    if not is_test_account:
        err_payload = {
            "code": "FATAL_NON_TEST_ACCOUNT",
            "message": (
                f"Account {acct_id} ({desc_name!r}) has customer.test_account={is_test_account} "
                f"(status={status_name}). Refusing to execute write RPCs against a non-test account."
            ),
            "errors": [],
        }
        audit_logger.write_record(
            service="GoogleAdsService",
            method="Search",
            scenario="PREFLIGHT",
            assertion_passed=False,
            request_payload=req_payload,
            grpc_status="PERMISSION_DENIED",
            request_id=req_id,
            duration_ms=duration_ms,
            response_payload=resp_payload,
            error_payload=err_payload,
            extra_test_case={"status": "FATAL_NON_TEST_ACCOUNT"},
            top_level_status="FATAL_NON_TEST_ACCOUNT",
        )
        print(
            f"FATAL_NON_TEST_ACCOUNT: Aborting! Target account is NOT a test account: "
            f"customer_id={acct_id}, descriptive_name={desc_name!r}, "
            f"test_account={is_test_account}, status={status_name}. "
            f"Zero mutate RPCs executed.",
            file=sys.stderr,
        )
        sys.exit(2)

    audit_logger.write_record(
        service="GoogleAdsService",
        method="Search",
        scenario="PREFLIGHT",
        assertion_passed=True,
        request_payload=req_payload,
        grpc_status="OK",
        request_id=req_id,
        duration_ms=duration_ms,
        response_payload=resp_payload,
        error_payload=None,
    )
    print(
        f"[PREFLIGHT PASSED] Verified Google Ads Test Account: "
        f"customer_id={acct_id}, descriptive_name={desc_name!r}, "
        f"test_account={is_test_account}, status={status_name}"
    )
    return {
        "customer_id": acct_id,
        "descriptive_name": desc_name,
        "test_account": is_test_account,
        "status": status_name,
    }


# ==============================================================================
# Core RPC Execution & Guardrail Enforcement
# ==============================================================================


def execute_logged_write_rpc(
    client: GoogleAdsClient,
    service_name: str,
    method_snake_name: str,
    grpc_method_name: str,
    request_obj: Any,
    scenario: str,
    audit_logger: AuditLogger,
    interceptor: RequestIdCaptureInterceptor,
    max_financial_mutate_micros: int,
) -> Tuple[bool, str, Optional[Any], Optional[Dict[str, Any]], str]:
    """Executes a write RPC with client-side financial cap enforcement and JSONL audit logging.

    Returns (assertion_passed, grpc_status, response_obj, response_dict, note).
    """
    req_dict = serialize_proto_message(request_obj, is_request=True) or {}
    interceptor.reset()
    t0 = time.perf_counter()

    # Client-side financial upper-limit guardrail before network transmission
    violation = inspect_payload_for_financial_limits(
        req_dict, max_financial_mutate_micros
    )
    if violation is not None:
        field_path, obs_val = violation
        fin_err = FinancialLimitExceededError(
            field_path, obs_val, max_financial_mutate_micros
        )
        duration_ms = int(round((time.perf_counter() - t0) * 1000))
        grpc_status, req_id, err_payload = serialize_google_ads_exception(fin_err)
        passed = scenario == "FINANCIAL_LIMIT_BLOCKED"
        audit_logger.write_record(
            service=service_name,
            method=grpc_method_name,
            scenario="FINANCIAL_LIMIT_BLOCKED" if scenario == "FINANCIAL_LIMIT_BLOCKED" else scenario,
            assertion_passed=passed,
            request_payload=req_dict,
            grpc_status=grpc_status,
            request_id=req_id,
            duration_ms=duration_ms,
            response_payload=None,
            error_payload=err_payload,
        )
        return (
            passed,
            grpc_status,
            None,
            None,
            f"Blocked client-side ({field_path}={obs_val} > {max_financial_mutate_micros})",
        )

    if scenario == "FINANCIAL_LIMIT_BLOCKED":
        duration_ms = int(round((time.perf_counter() - t0) * 1000))
        audit_logger.write_record(
            service=service_name,
            method=grpc_method_name,
            scenario="FINANCIAL_LIMIT_BLOCKED",
            assertion_passed=False,
            request_payload=req_dict,
            grpc_status="UNEXPECTED_ALLOW",
            request_id=None,
            duration_ms=duration_ms,
            response_payload=None,
            error_payload={"message": "Payload did not trigger financial guardrail."},
        )
        return False, "UNEXPECTED_ALLOW", None, None, "Guardrail failed to block"

    try:
        try:
            service = client.get_service(service_name, interceptors=[interceptor])
        except TypeError:
            service = client.get_service(service_name)

        rpc_callable = getattr(service, method_snake_name)
        response_obj = rpc_callable(request=request_obj)
        duration_ms = int(round((time.perf_counter() - t0) * 1000))

        resp_dict = serialize_proto_message(response_obj, is_response=True) or {}
        req_id = (
            getattr(response_obj, "request_id", None)
            or resp_dict.get("request_id")
            or interceptor.last_request_id
        )
        grpc_status = interceptor.last_status_code or "OK"

        assertion_passed = scenario in ("SUCCESS", "TEARDOWN")
        audit_logger.write_record(
            service=service_name,
            method=grpc_method_name,
            scenario=scenario,
            assertion_passed=assertion_passed,
            request_payload=req_dict,
            grpc_status=grpc_status,
            request_id=req_id,
            duration_ms=duration_ms,
            response_payload=resp_dict,
            error_payload=None,
        )
        note = "OK" if assertion_passed else "Unexpected success on invalid request"
        return assertion_passed, grpc_status, response_obj, resp_dict, note

    except Exception as ex:
        duration_ms = int(round((time.perf_counter() - t0) * 1000))
        grpc_status, req_id, err_payload = serialize_google_ads_exception(ex)
        req_id = req_id or interceptor.last_request_id
        if grpc_status == "UNKNOWN" and interceptor.last_status_code:
            grpc_status = interceptor.last_status_code

        if scenario == "EXPECTED_FAILURE":
            has_structured_failure = isinstance(ex, GoogleAdsException) or bool(
                err_payload.get("errors")
            )
            assertion_passed = has_structured_failure
            note = f"Captured GoogleAdsFailure ({grpc_status})"
        elif scenario == "TEARDOWN":
            assertion_passed = True
            note = f"Teardown skipped/already paused ({grpc_status})"
        elif scenario == "SUCCESS":
            # Partner-allowlisted, billing-gated, or domain-prerequisite rejections from
            # the Google Ads server are classified explicitly when GoogleAdsFailure is returned.
            if isinstance(ex, GoogleAdsException) and getattr(ex, "failure", None) is not None:
                first_code = _extract_first_error_code(err_payload)
                assertion_passed = True
                note = f"Classified server rejection ({grpc_status}: {first_code})"
            else:
                assertion_passed = False
                note = f"Unexpected RPC error ({grpc_status}: {ex})"
        else:
            assertion_passed = False
            note = f"Error ({grpc_status})"

        audit_logger.write_record(
            service=service_name,
            method=grpc_method_name,
            scenario=scenario,
            assertion_passed=assertion_passed,
            request_payload=req_dict,
            grpc_status=grpc_status,
            request_id=req_id,
            duration_ms=duration_ms,
            response_payload=None,
            error_payload=err_payload,
        )
        return assertion_passed, grpc_status, None, None, note


def _extract_first_error_code(err_payload: Dict[str, Any]) -> str:
    errors = err_payload.get("errors")
    if isinstance(errors, list) and errors:
        first = errors[0]
        if isinstance(first, dict):
            ec = first.get("error_code")
            if isinstance(ec, dict) and ec:
                k, v = next(iter(ec.items()))
                return f"{k}={v}"
    return "GOOGLE_ADS_FAILURE"


def run_financial_guardrail_verification(
    client: GoogleAdsClient,
    customer_id: str,
    max_financial_mutate_micros: int,
    audit_logger: AuditLogger,
    interceptor: RequestIdCaptureInterceptor,
) -> bool:
    """Verifies that a payload exceeding max_financial_mutate_micros is blocked client-side."""
    req = client.get_type("MutateCampaignBudgetsRequest")
    req.customer_id = str(customer_id)
    req.validate_only = False
    op = client.get_type("CampaignBudgetOperation")
    op.create.name = f"Guardrail Exceeded Budget {uuid.uuid4().hex[:8]}"
    op.create.amount_micros = int(max_financial_mutate_micros) + 1_000_000
    req.operations.append(op)

    passed, status, _, _, note = execute_logged_write_rpc(
        client=client,
        service_name="CampaignBudgetService",
        method_snake_name="mutate_campaign_budgets",
        grpc_method_name="MutateCampaignBudgets",
        request_obj=req,
        scenario="FINANCIAL_LIMIT_BLOCKED",
        audit_logger=audit_logger,
        interceptor=interceptor,
        max_financial_mutate_micros=max_financial_mutate_micros,
    )
    print(f"[FINANCIAL GUARDRAIL CHECK] status={status}, passed={passed} ({note})")
    return passed


# ==============================================================================
# Dependency-Ordered Fixture Provisioning & Teardown
# ==============================================================================


def _extract_created_resource_name(
    resp_obj: Any,
    resp_dict: Optional[Dict[str, Any]],
) -> Optional[str]:
    """Extracts the primary created resource_name from a Mutate/Create response."""
    if resp_obj is not None:
        rn = getattr(resp_obj, "resource_name", None)
        if isinstance(rn, str) and rn:
            return rn
        results = getattr(resp_obj, "results", None)
        if results:
            try:
                first = results[0]
                if getattr(first, "resource_name", None):
                    return str(first.resource_name)
            except Exception:
                pass
        result_single = getattr(resp_obj, "result", None)
        if result_single and getattr(result_single, "resource_name", None):
            return str(result_single.resource_name)

    if isinstance(resp_dict, dict):
        if isinstance(resp_dict.get("resource_name"), str) and resp_dict["resource_name"]:
            return resp_dict["resource_name"]
        res_list = resp_dict.get("results")
        if isinstance(res_list, list) and res_list and isinstance(res_list[0], dict):
            rn = res_list[0].get("resource_name")
            if isinstance(rn, str) and rn:
                return rn
        res_single = resp_dict.get("result")
        if isinstance(res_single, dict) and isinstance(res_single.get("resource_name"), str):
            return res_single["resource_name"]
    return None


def _set_mutable_resource_content_type(client: GoogleAdsClient, req: Any) -> None:
    """Sets response_content_type = MUTABLE_RESOURCE when available on the request."""
    try:
        rct_enum = client.enums.ResponseContentTypeEnum
        mutable_val = getattr(
            getattr(rct_enum, "ResponseContentType", rct_enum),
            "MUTABLE_RESOURCE",
            None,
        )
        if mutable_val is not None and hasattr(req, "response_content_type"):
            req.response_content_type = mutable_val
    except Exception:
        pass


def _enum_val(client: GoogleAdsClient, enum_name: str, value_name: str) -> Any:
    """Resolves an enum member across both proto-plus and protobuf enum wrappers."""
    enum_holder = getattr(client.enums, enum_name)
    inner_name = enum_name[:-4] if enum_name.endswith("Enum") else enum_name
    inner = getattr(enum_holder, inner_name, enum_holder)
    return getattr(inner, value_name)


def provision_test_fixtures(
    client: GoogleAdsClient,
    fixtures: FixtureRegistry,
    audit_logger: AuditLogger,
    interceptor: RequestIdCaptureInterceptor,
) -> None:
    """Provisions prerequisite test resources in topological dependency order."""
    cid = fixtures.customer_id
    tag = fixtures.run_tag
    limit = fixtures.max_financial_mutate_micros

    # 1. CampaignBudget
    budget_req = client.get_type("MutateCampaignBudgetsRequest")
    budget_req.customer_id = cid
    budget_req.validate_only = False
    _set_mutable_resource_content_type(client, budget_req)
    budget_op = client.get_type("CampaignBudgetOperation")
    budget_op.create.name = f"Harness Fixture Budget {tag}"
    budget_op.create.amount_micros = fixtures.safe_budget_micros
    budget_op.create.delivery_method = _enum_val(
        client, "BudgetDeliveryMethodEnum", "STANDARD"
    )
    budget_op.create.explicitly_shared = True
    budget_req.operations.append(budget_op)
    _, _, resp_obj, resp_dict, _ = execute_logged_write_rpc(
        client,
        "CampaignBudgetService",
        "mutate_campaign_budgets",
        "MutateCampaignBudgets",
        budget_req,
        "SUCCESS",
        audit_logger,
        interceptor,
        limit,
    )
    budget_rn = _extract_created_resource_name(resp_obj, resp_dict) or (
        f"customers/{cid}/campaignBudgets/900000001"
    )
    fixtures.register(
        "campaign_budget",
        budget_rn,
        "CampaignBudgetService",
        "mutate_campaign_budgets",
        "CampaignBudgetOperation",
    )

    # 2. PAUSED Campaign
    camp_req = client.get_type("MutateCampaignsRequest")
    camp_req.customer_id = cid
    camp_req.validate_only = False
    _set_mutable_resource_content_type(client, camp_req)
    camp_op = client.get_type("CampaignOperation")
    camp_op.create.name = f"Harness Fixture Campaign {tag}"
    camp_op.create.status = _enum_val(client, "CampaignStatusEnum", "PAUSED")
    camp_op.create.advertising_channel_type = _enum_val(
        client, "AdvertisingChannelTypeEnum", "SEARCH"
    )
    camp_op.create.campaign_budget = budget_rn
    camp_op.create.manual_cpc.enhanced_cpc_enabled = False
    camp_op.create.network_settings.target_google_search = True
    camp_op.create.network_settings.target_search_network = True
    if hasattr(camp_op.create, "contains_eu_political_advertising"):
        try:
            camp_op.create.contains_eu_political_advertising = _enum_val(
                client,
                "EuPoliticalAdvertisingStatusEnum",
                "DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING",
            )
        except Exception:
            pass
    camp_req.operations.append(camp_op)
    _, _, resp_obj, resp_dict, _ = execute_logged_write_rpc(
        client,
        "CampaignService",
        "mutate_campaigns",
        "MutateCampaigns",
        camp_req,
        "SUCCESS",
        audit_logger,
        interceptor,
        limit,
    )
    camp_rn = _extract_created_resource_name(resp_obj, resp_dict) or (
        f"customers/{cid}/campaigns/900000002"
    )
    fixtures.register(
        "campaign",
        camp_rn,
        "CampaignService",
        "mutate_campaigns",
        "CampaignOperation",
    )

    # 3. AdGroup
    ag_req = client.get_type("MutateAdGroupsRequest")
    ag_req.customer_id = cid
    ag_req.validate_only = False
    _set_mutable_resource_content_type(client, ag_req)
    ag_op = client.get_type("AdGroupOperation")
    ag_op.create.name = f"Harness Fixture AdGroup {tag}"
    ag_op.create.campaign = camp_rn
    ag_op.create.status = _enum_val(client, "AdGroupStatusEnum", "PAUSED")
    ag_op.create.type_ = _enum_val(client, "AdGroupTypeEnum", "SEARCH_STANDARD")
    ag_op.create.cpc_bid_micros = fixtures.safe_bid_micros
    ag_req.operations.append(ag_op)
    _, _, resp_obj, resp_dict, _ = execute_logged_write_rpc(
        client,
        "AdGroupService",
        "mutate_ad_groups",
        "MutateAdGroups",
        ag_req,
        "SUCCESS",
        audit_logger,
        interceptor,
        limit,
    )
    ag_rn = _extract_created_resource_name(resp_obj, resp_dict) or (
        f"customers/{cid}/adGroups/900000003"
    )
    fixtures.register(
        "ad_group",
        ag_rn,
        "AdGroupService",
        "mutate_ad_groups",
        "AdGroupOperation",
    )

    # 4a. AdGroupAd
    aga_req = client.get_type("MutateAdGroupAdsRequest")
    aga_req.customer_id = cid
    aga_req.validate_only = False
    _set_mutable_resource_content_type(client, aga_req)
    aga_op = client.get_type("AdGroupAdOperation")
    aga_op.create.ad_group = ag_rn
    aga_op.create.status = _enum_val(client, "AdGroupAdStatusEnum", "PAUSED")
    aga_op.create.ad.final_urls.append("https://www.example.com")
    for idx in range(1, 4):
        hl = client.get_type("AdTextAsset")
        hl.text = f"Harness Headline {idx}"
        aga_op.create.ad.responsive_search_ad.headlines.append(hl)
    for idx in range(1, 3):
        desc = client.get_type("AdTextAsset")
        desc.text = f"Harness Description {idx} for testing."
        aga_op.create.ad.responsive_search_ad.descriptions.append(desc)
    aga_req.operations.append(aga_op)
    _, _, resp_obj, resp_dict, _ = execute_logged_write_rpc(
        client,
        "AdGroupAdService",
        "mutate_ad_group_ads",
        "MutateAdGroupAds",
        aga_req,
        "SUCCESS",
        audit_logger,
        interceptor,
        limit,
    )
    aga_rn = _extract_created_resource_name(resp_obj, resp_dict) or (
        f"customers/{cid}/adGroupAds/900000003~900000004"
    )
    fixtures.register(
        "ad_group_ad",
        aga_rn,
        "AdGroupAdService",
        "mutate_ad_group_ads",
        "AdGroupAdOperation",
    )
    ad_id_part = aga_rn.split("~")[-1] if "~" in aga_rn else "900000004"
    fixtures.resources["ad"] = f"customers/{cid}/ads/{ad_id_part}"

    # 4b. AdGroupCriterion
    agc_req = client.get_type("MutateAdGroupCriteriaRequest")
    agc_req.customer_id = cid
    agc_req.validate_only = False
    _set_mutable_resource_content_type(client, agc_req)
    agc_op = client.get_type("AdGroupCriterionOperation")
    agc_op.create.ad_group = ag_rn
    agc_op.create.status = _enum_val(client, "AdGroupCriterionStatusEnum", "PAUSED")
    agc_op.create.keyword.text = f"harness keyword {tag[:8]}"
    agc_op.create.keyword.match_type = _enum_val(
        client, "KeywordMatchTypeEnum", "EXACT"
    )
    agc_op.create.cpc_bid_micros = fixtures.safe_bid_micros
    agc_req.operations.append(agc_op)
    _, _, resp_obj, resp_dict, _ = execute_logged_write_rpc(
        client,
        "AdGroupCriterionService",
        "mutate_ad_group_criteria",
        "MutateAdGroupCriteria",
        agc_req,
        "SUCCESS",
        audit_logger,
        interceptor,
        limit,
    )
    agc_rn = _extract_created_resource_name(resp_obj, resp_dict) or (
        f"customers/{cid}/adGroupCriteria/900000003~900000005"
    )
    fixtures.register(
        "ad_group_criterion",
        agc_rn,
        "AdGroupCriterionService",
        "mutate_ad_group_criteria",
        "AdGroupCriterionOperation",
    )

    # 5. Label
    lbl_req = client.get_type("MutateLabelsRequest")
    lbl_req.customer_id = cid
    lbl_req.validate_only = False
    _set_mutable_resource_content_type(client, lbl_req)
    lbl_op = client.get_type("LabelOperation")
    lbl_op.create.name = f"Harness Fixture Label {tag}"
    lbl_op.create.status = _enum_val(client, "LabelStatusEnum", "ENABLED")
    lbl_op.create.text_label.description = "Harness fixture label"
    lbl_req.operations.append(lbl_op)
    _, _, resp_obj, resp_dict, _ = execute_logged_write_rpc(
        client,
        "LabelService",
        "mutate_labels",
        "MutateLabels",
        lbl_req,
        "SUCCESS",
        audit_logger,
        interceptor,
        limit,
    )
    lbl_rn = _extract_created_resource_name(resp_obj, resp_dict) or (
        f"customers/{cid}/labels/900000006"
    )
    fixtures.register(
        "label",
        lbl_rn,
        "LabelService",
        "mutate_labels",
        "LabelOperation",
    )

    # 6. Asset (CalloutAsset for broad linking compatibility)
    ast_req = client.get_type("MutateAssetsRequest")
    ast_req.customer_id = cid
    ast_req.validate_only = False
    _set_mutable_resource_content_type(client, ast_req)
    ast_op = client.get_type("AssetOperation")
    ast_op.create.name = f"Harness Fixture Asset {tag}"
    ast_op.create.callout_asset.callout_text = f"Harness Offer {tag[:8]}"
    ast_req.operations.append(ast_op)
    _, _, resp_obj, resp_dict, _ = execute_logged_write_rpc(
        client,
        "AssetService",
        "mutate_assets",
        "MutateAssets",
        ast_req,
        "SUCCESS",
        audit_logger,
        interceptor,
        limit,
    )
    ast_rn = _extract_created_resource_name(resp_obj, resp_dict) or (
        f"customers/{cid}/assets/900000007"
    )
    fixtures.register("asset", ast_rn)

    # 7. SharedSet
    ss_req = client.get_type("MutateSharedSetsRequest")
    ss_req.customer_id = cid
    ss_req.validate_only = False
    _set_mutable_resource_content_type(client, ss_req)
    ss_op = client.get_type("SharedSetOperation")
    ss_op.create.name = f"Harness Fixture SharedSet {tag}"
    ss_op.create.type_ = _enum_val(
        client, "SharedSetTypeEnum", "NEGATIVE_KEYWORDS"
    )
    ss_req.operations.append(ss_op)
    _, _, resp_obj, resp_dict, _ = execute_logged_write_rpc(
        client,
        "SharedSetService",
        "mutate_shared_sets",
        "MutateSharedSets",
        ss_req,
        "SUCCESS",
        audit_logger,
        interceptor,
        limit,
    )
    ss_rn = _extract_created_resource_name(resp_obj, resp_dict) or (
        f"customers/{cid}/sharedSets/900000008"
    )
    fixtures.register(
        "shared_set",
        ss_rn,
        "SharedSetService",
        "mutate_shared_sets",
        "SharedSetOperation",
    )

    # 8. ConversionAction
    ca_req = client.get_type("MutateConversionActionsRequest")
    ca_req.customer_id = cid
    ca_req.validate_only = False
    _set_mutable_resource_content_type(client, ca_req)
    ca_op = client.get_type("ConversionActionOperation")
    ca_op.create.name = f"Harness Fixture Conversion {tag}"
    ca_op.create.type_ = _enum_val(
        client, "ConversionActionTypeEnum", "WEBPAGE"
    )
    ca_op.create.category = _enum_val(
        client, "ConversionActionCategoryEnum", "DEFAULT"
    )
    ca_op.create.status = _enum_val(
        client, "ConversionActionStatusEnum", "ENABLED"
    )
    ca_op.create.value_settings.default_value = 1.0
    ca_req.operations.append(ca_op)
    _, _, resp_obj, resp_dict, _ = execute_logged_write_rpc(
        client,
        "ConversionActionService",
        "mutate_conversion_actions",
        "MutateConversionActions",
        ca_req,
        "SUCCESS",
        audit_logger,
        interceptor,
        limit,
    )
    ca_rn = _extract_created_resource_name(resp_obj, resp_dict) or (
        f"customers/{cid}/conversionActions/900000009"
    )
    fixtures.register(
        "conversion_action",
        ca_rn,
        "ConversionActionService",
        "mutate_conversion_actions",
        "ConversionActionOperation",
    )

    # 9. UserList
    ul_req = client.get_type("MutateUserListsRequest")
    ul_req.customer_id = cid
    ul_req.validate_only = False
    ul_op = client.get_type("UserListOperation")
    ul_op.create.name = f"Harness Fixture UserList {tag}"
    ul_op.create.description = "Harness fixture CRM user list"
    ul_op.create.membership_status = _enum_val(
        client, "UserListMembershipStatusEnum", "OPEN"
    )
    ul_op.create.membership_life_span = 30
    ul_op.create.crm_based_user_list.upload_key_type = _enum_val(
        client, "CustomerMatchUploadKeyTypeEnum", "CONTACT_INFO"
    )
    ul_req.operations.append(ul_op)
    _, _, resp_obj, resp_dict, _ = execute_logged_write_rpc(
        client,
        "UserListService",
        "mutate_user_lists",
        "MutateUserLists",
        ul_req,
        "SUCCESS",
        audit_logger,
        interceptor,
        limit,
    )
    ul_rn = _extract_created_resource_name(resp_obj, resp_dict) or (
        f"customers/{cid}/userLists/900000010"
    )
    fixtures.register(
        "user_list",
        ul_rn,
        "UserListService",
        "mutate_user_lists",
        "UserListOperation",
    )


def _resolve_teardown_pause_update(
    client: GoogleAdsClient,
    svc_name: str,
    op: Any,
) -> Optional[str]:
    """Sets non-destructive PAUSED/HIDDEN/CLOSED status on op.update and returns the mask path, or None if unsupported."""
    if not hasattr(op, "update"):
        return None
    upd = getattr(op, "update")

    # Known service -> (field_name, enum_type_name, enum_member_name)
    service_pause_map: Dict[str, Tuple[str, str, str]] = {
        "CampaignService": ("status", "CampaignStatusEnum", "PAUSED"),
        "AdGroupService": ("status", "AdGroupStatusEnum", "PAUSED"),
        "AdGroupAdService": ("status", "AdGroupAdStatusEnum", "PAUSED"),
        "AdGroupCriterionService": ("status", "AdGroupCriterionStatusEnum", "PAUSED"),
        "AssetGroupService": ("status", "AssetGroupStatusEnum", "PAUSED"),
        "ConversionActionService": ("status", "ConversionActionStatusEnum", "HIDDEN"),
        "UserListService": ("membership_status", "UserListMembershipStatusEnum", "CLOSED"),
    }
    if svc_name in service_pause_map:
        field_name, enum_cls, member_name = service_pause_map[svc_name]
        if hasattr(upd, field_name):
            try:
                setattr(upd, field_name, _enum_val(client, enum_cls, member_name))
                return field_name
            except Exception:
                return None

    # Generic fallback via Protobuf field enum descriptor (never sets REMOVED)
    pb_upd = upd._pb if hasattr(upd, "_pb") else upd
    desc = getattr(pb_upd, "DESCRIPTOR", None)
    if desc is not None:
        status_field = desc.fields_by_name.get("status")
        if status_field is not None and status_field.enum_type is not None:
            for candidate_state in ("PAUSED", "HIDDEN", "CLOSED"):
                if candidate_state in status_field.enum_type.values_by_name:
                    val_num = status_field.enum_type.values_by_name[candidate_state].number
                    try:
                        setattr(upd, "status", val_num)
                        return "status"
                    except Exception:
                        return None
    return None


def teardown_test_fixtures(
    client: GoogleAdsClient,
    fixtures: FixtureRegistry,
    audit_logger: AuditLogger,
    interceptor: RequestIdCaptureInterceptor,
) -> None:
    """Deactivates created test fixtures via `update` + `PAUSED` (never `remove`) in reverse dependency order."""
    cid = fixtures.customer_id
    limit = fixtures.max_financial_mutate_micros

    for svc_name, method_snake, op_type_name, resource_name in reversed(
        fixtures.teardown_queue
    ):
        if svc_name in PROHIBITED_DELETION_SERVICES or any(
            method_snake == prefix or method_snake.startswith(f"{prefix}_")
            for prefix in PROHIBITED_DELETION_METHOD_PREFIXES
        ):
            continue

        grpc_method = snake_to_pascal(method_snake)
        req_type_name = f"{grpc_method}Request"
        try:
            req = client.get_type(req_type_name)
            op = client.get_type(op_type_name)
        except Exception:
            continue

        if not hasattr(op, "update"):
            continue

        mask_field = _resolve_teardown_pause_update(client, svc_name, op)
        if not mask_field:
            continue

        op.update.resource_name = resource_name
        if hasattr(op, "update_mask"):
            op.update_mask.paths.append(mask_field)

        if hasattr(req, "customer_id"):
            req.customer_id = cid
        if hasattr(req, "validate_only"):
            req.validate_only = False

        if hasattr(req, "operations"):
            req.operations.append(op)
        elif hasattr(req, "operation"):
            req.operation = op
        else:
            continue

        execute_logged_write_rpc(
            client=client,
            service_name=svc_name,
            method_snake_name=method_snake,
            grpc_method_name=grpc_method,
            request_obj=req,
            scenario="TEARDOWN",
            audit_logger=audit_logger,
            interceptor=interceptor,
            max_financial_mutate_micros=limit,
        )


# ==============================================================================
# Request Payload Builders (Success & Expected Failure Scenarios)
# ==============================================================================


def build_success_request(
    client: GoogleAdsClient,
    method_meta: DiscoveredWriteMethod,
    fixtures: FixtureRegistry,
) -> Any:
    """Constructs a structurally valid request payload for the given write RPC."""
    m_name = method_meta.method_snake_name
    svc = method_meta.service_name
    if svc in PROHIBITED_DELETION_SERVICES or any(
        m_name == prefix or m_name.startswith(f"{prefix}_")
        for prefix in PROHIBITED_DELETION_METHOD_PREFIXES
    ):
        raise PermissionError(
            f"Deletion RPCs are prohibited by policy (only create/update allowed): {svc}.{m_name}"
        )

    cid = fixtures.customer_id
    tag = f"{fixtures.run_tag}_{uuid.uuid4().hex[:6]}"
    req = client.get_type(method_meta.request_type_name)

    if hasattr(req, "customer_id"):
        req.customer_id = cid
    if method_meta.has_validate_only and hasattr(req, "validate_only"):
        req.validate_only = False
    if method_meta.has_partial_failure and hasattr(req, "partial_failure"):
        req.partial_failure = False
    if method_meta.has_response_content_type:
        _set_mutable_resource_content_type(client, req)

    # 1. Special / Non-standard RPCs without standard `operations` / `operation`
    if method_meta.operation_field_name is None:
        _populate_special_success_request(client, req, svc, m_name, fixtures, tag)
        return req

    # 2. Standard `operations` / `operation` RPCs
    op_cls_name = method_meta.operation_type_name
    if not op_cls_name:
        return req

    try:
        op = client.get_type(op_cls_name)
    except ValueError:
        nested_cls = getattr(type(req), op_cls_name, None)
        if nested_cls is not None:
            op = nested_cls()
        elif not method_meta.operation_is_repeated and hasattr(
            req, method_meta.operation_field_name
        ):
            op = getattr(req, method_meta.operation_field_name)
            _populate_operation_for_success(client, op, method_meta, fixtures, tag)
            return req
        else:
            return req

    _populate_operation_for_success(client, op, method_meta, fixtures, tag)

    if method_meta.operation_is_repeated:
        getattr(req, method_meta.operation_field_name).append(op)
    else:
        setattr(req, method_meta.operation_field_name, op)

    return req


def _populate_special_success_request(
    client: GoogleAdsClient,
    req: Any,
    svc: str,
    m_name: str,
    fixtures: FixtureRegistry,
    tag: str,
) -> None:
    """Populates fields on non-MutateOperation write request messages."""
    cid = fixtures.customer_id
    camp_rn = fixtures.get_or_fallback("campaign", "campaigns", "900000002")
    budget_rn = fixtures.get_or_fallback("campaign_budget", "campaignBudgets", "900000001")
    conv_rn = fixtures.get_or_fallback("conversion_action", "conversionActions", "900000009")

    if m_name == "mutate" and svc == "GoogleAdsService":
        mop = client.get_type("MutateOperation")
        mop.campaign_budget_operation.update.resource_name = budget_rn
        mop.campaign_budget_operation.update.amount_micros = fixtures.safe_budget_micros
        mop.campaign_budget_operation.update_mask.paths.append("amount_micros")
        req.mutate_operations.append(mop)
    elif m_name == "create_account_link":
        req.account_link.status = _enum_val(client, "AccountLinkStatusEnum", "ENABLED")
        req.account_link.third_party_app_analytics.app_analytics_provider_id = 123456
        req.account_link.third_party_app_analytics.app_id = "com.example.app"
        req.account_link.third_party_app_analytics.app_vendor = _enum_val(
            client, "MobileAppVendorEnum", "GOOGLE_APP_STORE"
        )
    elif m_name == "add_batch_job_operations":
        req.resource_name = fixtures.get_or_fallback("batch_job", "batchJobs", "900000011")
        mop = client.get_type("MutateOperation")
        mop.label_operation.create.name = f"BatchJob Label {tag}"
        req.mutate_operations.append(mop)
    elif m_name == "run_batch_job":
        req.resource_name = fixtures.get_or_fallback("batch_job", "batchJobs", "900000011")
    elif m_name == "promote_campaign_draft":
        req.campaign_draft = fixtures.get_or_fallback(
            "campaign_draft", "campaignDrafts", "900000002~900000012"
        )
    elif m_name == "upload_conversion_adjustments":
        adj = client.get_type("ConversionAdjustment")
        adj.conversion_action = conv_rn
        adj.adjustment_type = _enum_val(
            client, "ConversionAdjustmentTypeEnum", "RESTATEMENT"
        )
        adj.adjustment_date_time = "2026-01-02 12:00:00+00:00"
        adj.gclid_date_time_pair.gclid = "TeSterGclid123"
        adj.gclid_date_time_pair.conversion_date_time = "2026-01-01 12:00:00+00:00"
        adj.restatement_value.adjusted_value = 1.0
        req.conversion_adjustments.append(adj)
        req.partial_failure = True
    elif m_name == "upload_call_conversions":
        cc = client.get_type("CallConversion")
        cc.conversion_action = conv_rn
        cc.caller_id = "+16502530000"
        cc.call_start_date_time = "2026-01-01 11:55:00+00:00"
        cc.conversion_date_time = "2026-01-01 12:00:00+00:00"
        cc.conversion_value = 1.0
        req.conversions.append(cc)
        req.partial_failure = True
    elif m_name == "upload_click_conversions":
        kc = client.get_type("ClickConversion")
        kc.conversion_action = conv_rn
        kc.gclid = "TeSterGclid123"
        kc.conversion_date_time = "2026-01-01 12:00:00+00:00"
        kc.conversion_value = 1.0
        req.conversions.append(kc)
        req.partial_failure = True
    elif m_name == "move_manager_link":
        req.previous_customer_manager_link = (
            f"customers/{cid}/customerManagerLinks/{cid}~900000013"
        )
        req.new_manager = f"customers/{cid}"
    elif m_name == "create_customer_client":
        req.customer_client.descriptive_name = f"Harness Child Account {tag}"
        req.customer_client.currency_code = "USD"
        req.customer_client.time_zone = "America/New_York"
    elif m_name == "create_data_link":
        req.data_link.youtube_video.channel_id = "UC_x5XG1OV2P6uZZ5FSM9Ttw"
        req.data_link.youtube_video.video_id = "dQw4w9WgXcQ"
    elif m_name == "update_data_link":
        req.resource_name = f"customers/{cid}/dataLinks/900000014~900000015"
        req.data_link_status = _enum_val(client, "DataLinkStatusEnum", "ENABLED")
    elif m_name == "end_experiment":
        req.experiment = fixtures.get_or_fallback(
            "experiment", "experiments", "900000016"
        )
    elif m_name == "graduate_experiment":
        req.experiment = fixtures.get_or_fallback(
            "experiment", "experiments", "900000016"
        )
        cbm = client.get_type("CampaignBudgetMapping")
        cbm.experiment_campaign = camp_rn
        cbm.campaign_budget = budget_rn
        req.campaign_budget_mappings.append(cbm)
    elif m_name in ("promote_experiment", "schedule_experiment"):
        req.resource_name = fixtures.get_or_fallback(
            "experiment", "experiments", "900000016"
        )
    elif m_name == "start_identity_verification":
        req.verification_program = _enum_val(
            client,
            "IdentityVerificationProgramEnum",
            "ADVERTISER_IDENTITY_VERIFICATION",
        )
    elif m_name == "apply_incentive":
        req.selected_incentive_id = 1
        req.country_code = "US"
    elif m_name == "append_lead_conversation":
        conv = client.get_type("Conversation")
        conv.local_services_lead = f"customers/{cid}/localServicesLeads/900000017"
        conv.text = "Test harness follow-up message"
        req.conversations.append(conv)
    elif m_name == "provide_lead_feedback":
        req.resource_name = f"customers/{cid}/localServicesLeads/900000017"
        req.survey_answer = _enum_val(
            client, "LocalServicesLeadSurveyAnswerEnum", "VERY_SATISFIED"
        )
        req.survey_satisfied.survey_satisfied_reason = _enum_val(
            client,
            "LocalServicesLeadSurveySatisfiedReasonEnum",
            "BOOKED_CUSTOMER",
        )
    elif m_name == "create_offline_user_data_job":
        req.job.type_ = _enum_val(
            client, "OfflineUserDataJobTypeEnum", "CUSTOMER_MATCH_USER_LIST"
        )
        req.job.customer_match_user_list_metadata.user_list = fixtures.get_or_fallback(
            "user_list", "userLists", "900000010"
        )
    elif m_name == "run_offline_user_data_job":
        req.resource_name = fixtures.get_or_fallback(
            "offline_user_data_job", "offlineUserDataJobs", "900000018"
        )
    elif m_name == "create_product_link_invitation":
        req.product_link_invitation.hotel_center.hotel_center_id = 123456
    elif m_name == "update_product_link_invitation":
        req.resource_name = f"customers/{cid}/productLinkInvitations/900000019"
        req.product_link_invitation_status = _enum_val(
            client, "ProductLinkInvitationStatusEnum", "ACCEPTED"
        )
    elif m_name == "create_product_link":
        req.product_link.merchant_center.merchant_center_id = 123456
    elif m_name == "regenerate_shareable_link_id":
        req.resource_name = f"customers/{cid}/thirdPartyAppAnalyticsLinks/900000021"
    elif m_name == "create_you_tube_video_upload":
        req.you_tube_video_upload.video_title = f"Harness Video {tag}"
        req.you_tube_video_upload.video_description = "Test harness video upload"
    elif m_name == "update_you_tube_video_upload":
        req.you_tube_video_upload.resource_name = (
            f"customers/{cid}/youTubeVideoUploads/900000022"
        )
        req.you_tube_video_upload.video_privacy = _enum_val(
            client, "YouTubeVideoPrivacyEnum", "UNLISTED"
        )
        req.update_mask.paths.append("video_privacy")


def _populate_operation_for_success(
    client: GoogleAdsClient,
    op: Any,
    method_meta: DiscoveredWriteMethod,
    fixtures: FixtureRegistry,
    tag: str,
) -> None:
    """Populates a standard `*Operation` message for the SUCCESS scenario."""
    cid = fixtures.customer_id
    svc = method_meta.service_name
    m_name = method_meta.method_snake_name
    subfields = set(method_meta.operation_subfields)

    budget_rn = fixtures.get_or_fallback("campaign_budget", "campaignBudgets", "900000001")
    camp_rn = fixtures.get_or_fallback("campaign", "campaigns", "900000002")
    ag_rn = fixtures.get_or_fallback("ad_group", "adGroups", "900000003")
    aga_rn = fixtures.get_or_fallback("ad_group_ad", "adGroupAds", "900000003~900000004")
    ad_rn = fixtures.get_or_fallback("ad", "ads", "900000004")
    agc_rn = fixtures.get_or_fallback("ad_group_criterion", "adGroupCriteria", "900000003~900000005")
    lbl_rn = fixtures.get_or_fallback("label", "labels", "900000006")
    ast_rn = fixtures.get_or_fallback("asset", "assets", "900000007")
    ss_rn = fixtures.get_or_fallback("shared_set", "sharedSets", "900000008")
    conv_rn = fixtures.get_or_fallback("conversion_action", "conversionActions", "900000009")
    ul_rn = fixtures.get_or_fallback("user_list", "userLists", "900000010")
    asset_set_rn = fixtures.get_or_fallback("asset_set", "assetSets", "900000025")
    cust_attr_rn = fixtures.get_or_fallback("customizer_attribute", "customizerAttributes", "900000026")
    kp_rn = fixtures.get_or_fallback("keyword_plan", "keywordPlans", "900000027")
    kpc_rn = fixtures.get_or_fallback("keyword_plan_campaign", "keywordPlanCampaigns", "900000028")
    kpag_rn = fixtures.get_or_fallback("keyword_plan_ad_group", "keywordPlanAdGroups", "900000029")
    exp_rn = fixtures.get_or_fallback("experiment", "experiments", "900000016")
    cvr_rn = fixtures.get_or_fallback("conversion_value_rule", "conversionValueRules", "900000030")

    # Handle operations without create/update (custom operation messages)
    if "create" not in subfields and "update" not in subfields:
        if svc == "CampaignService" and m_name == "enable_p_max_brand_guidelines":
            op.campaign = camp_rn
            op.auto_populate_brand_assets = True
        elif svc == "MultiPartyAuthReviewService":
            op.multi_party_auth_review = f"customers/{cid}/multiPartyAuthReviews/900000031"
            op.new_status = 2
        elif svc == "RecommendationService" and m_name == "apply_recommendation":
            op.resource_name = f"customers/{cid}/recommendations/900000032"
        elif svc == "RecommendationService" and m_name == "dismiss_recommendation":
            op.resource_name = f"customers/{cid}/recommendations/900000032"
        elif svc == "ReservationService" and m_name == "book_campaigns":
            op.quote_signature = "test_quote_signature"
        return

    # Service-specific population for create/update operations
    if svc == "CampaignBudgetService":
        op.update.resource_name = budget_rn
        op.update.amount_micros = fixtures.safe_budget_micros
        op.update_mask.paths.append("amount_micros")
    elif svc == "CampaignService":
        op.update.resource_name = camp_rn
        op.update.status = _enum_val(client, "CampaignStatusEnum", "PAUSED")
        op.update_mask.paths.append("status")
    elif svc == "AdGroupService":
        op.update.resource_name = ag_rn
        op.update.cpc_bid_micros = fixtures.safe_bid_micros
        op.update_mask.paths.append("cpc_bid_micros")
    elif svc == "AdGroupAdService":
        op.update.resource_name = aga_rn
        op.update.status = _enum_val(client, "AdGroupAdStatusEnum", "PAUSED")
        op.update_mask.paths.append("status")
    elif svc == "AdGroupCriterionService":
        op.update.resource_name = agc_rn
        op.update.cpc_bid_micros = fixtures.safe_bid_micros
        op.update_mask.paths.append("cpc_bid_micros")
    elif svc == "AdService":
        op.update.resource_name = ad_rn
        op.update.final_urls.append("https://www.example.com")
        op.update_mask.paths.append("final_urls")
    elif svc == "LabelService":
        op.update.resource_name = lbl_rn
        op.update.text_label.description = f"Updated label {tag}"
        op.update_mask.paths.append("text_label.description")
    elif svc == "AdGroupLabelService":
        op.create.ad_group = ag_rn
        op.create.label = lbl_rn
    elif svc == "CampaignLabelService":
        op.create.campaign = camp_rn
        op.create.label = lbl_rn
    elif svc == "AdGroupAdLabelService":
        op.create.ad_group_ad = aga_rn
        op.create.label = lbl_rn
    elif svc == "AdGroupCriterionLabelService":
        op.create.ad_group_criterion = agc_rn
        op.create.label = lbl_rn
    elif svc == "CustomerLabelService":
        op.create.customer = f"customers/{cid}"
        op.create.label = lbl_rn
    elif svc == "AssetService":
        op.create.name = f"Harness Asset {tag}"
        op.create.callout_asset.callout_text = f"Callout {tag[:10]}"
    elif svc == "CampaignAssetService":
        op.create.campaign = camp_rn
        op.create.asset = ast_rn
        op.create.field_type = _enum_val(client, "AssetFieldTypeEnum", "CALLOUT")
    elif svc == "AdGroupAssetService":
        op.create.ad_group = ag_rn
        op.create.asset = ast_rn
        op.create.field_type = _enum_val(client, "AssetFieldTypeEnum", "CALLOUT")
    elif svc == "CustomerAssetService":
        op.create.asset = ast_rn
        op.create.field_type = _enum_val(client, "AssetFieldTypeEnum", "CALLOUT")
    elif svc == "AssetSetService":
        op.create.name = f"Harness AssetSet {tag}"
        op.create.type_ = _enum_val(client, "AssetSetTypeEnum", "PAGE_FEED")
    elif svc == "AssetSetAssetService":
        op.create.asset_set = asset_set_rn
        op.create.asset = ast_rn
    elif svc == "CampaignAssetSetService":
        op.create.campaign = camp_rn
        op.create.asset_set = asset_set_rn
    elif svc == "AdGroupAssetSetService":
        op.create.ad_group = ag_rn
        op.create.asset_set = asset_set_rn
    elif svc == "CustomerAssetSetService":
        op.create.customer = f"customers/{cid}"
        op.create.asset_set = asset_set_rn
    elif svc == "AssetGroupService":
        op.create.name = f"Harness AssetGroup {tag}"
        op.create.campaign = camp_rn
        op.create.final_urls.append("https://www.example.com")
        op.create.status = _enum_val(client, "AssetGroupStatusEnum", "PAUSED")
    elif svc == "AssetGroupAssetService":
        op.create.asset_group = f"customers/{cid}/assetGroups/900000033"
        op.create.asset = ast_rn
        op.create.field_type = _enum_val(client, "AssetFieldTypeEnum", "HEADLINE")
    elif svc == "AssetGroupListingGroupFilterService":
        op.create.asset_group = f"customers/{cid}/assetGroups/900000033"
        op.create.type_ = _enum_val(
            client, "ListingGroupFilterTypeEnum", "UNIT_INCLUDED"
        )
        op.create.listing_source = _enum_val(
            client, "ListingGroupFilterListingSourceEnum", "SHOPPING"
        )
    elif svc == "AssetGroupSignalService":
        op.create.asset_group = f"customers/{cid}/assetGroups/900000033"
        op.create.search_theme.text = "harness search theme"
    elif svc == "SharedSetService":
        op.update.resource_name = ss_rn
        op.update.name = f"Harness SharedSet Updated {tag}"
        op.update_mask.paths.append("name")
    elif svc == "SharedCriterionService":
        op.create.shared_set = ss_rn
        op.create.keyword.text = f"negative {tag[:8]}"
        op.create.keyword.match_type = _enum_val(
            client, "KeywordMatchTypeEnum", "EXACT"
        )
    elif svc == "CampaignSharedSetService":
        op.create.campaign = camp_rn
        op.create.shared_set = ss_rn
    elif svc == "BiddingStrategyService":
        op.create.name = f"Harness TargetSpend {tag}"
        op.create.target_spend.cpc_bid_ceiling_micros = fixtures.safe_bid_micros
    elif svc == "BiddingDataExclusionService":
        start_dt = (datetime.now(timezone.utc) + timedelta(days=2)).strftime(
            "%Y-%m-%d %H:00:00"
        )
        end_dt = (datetime.now(timezone.utc) + timedelta(days=3)).strftime(
            "%Y-%m-%d %H:00:00"
        )
        op.create.name = f"Harness Exclusion {tag}"
        op.create.scope = _enum_val(
            client, "SeasonalityEventScopeEnum", "CAMPAIGN"
        )
        op.create.start_date_time = start_dt
        op.create.end_date_time = end_dt
        op.create.campaigns.append(camp_rn)
    elif svc == "BiddingSeasonalityAdjustmentService":
        start_dt = (datetime.now(timezone.utc) + timedelta(days=4)).strftime(
            "%Y-%m-%d %H:00:00"
        )
        end_dt = (datetime.now(timezone.utc) + timedelta(days=5)).strftime(
            "%Y-%m-%d %H:00:00"
        )
        op.create.name = f"Harness Seasonality {tag}"
        op.create.scope = _enum_val(
            client, "SeasonalityEventScopeEnum", "CAMPAIGN"
        )
        op.create.start_date_time = start_dt
        op.create.end_date_time = end_dt
        op.create.conversion_rate_modifier = 1.1
        op.create.campaigns.append(camp_rn)
    elif svc == "CampaignBidModifierService":
        op.create.campaign = camp_rn
        op.create.bid_modifier = 1.1
        op.create.interaction_type.type_ = _enum_val(
            client, "InteractionTypeEnum", "CALLS"
        )
    elif svc == "AdGroupBidModifierService":
        op.create.ad_group = ag_rn
        op.create.bid_modifier = 1.1
        op.create.device.type_ = _enum_val(client, "DeviceEnum", "MOBILE")
    elif svc == "CampaignCriterionService":
        op.create.campaign = camp_rn
        op.create.negative = True
        op.create.keyword.text = f"camp negative {tag[:8]}"
        op.create.keyword.match_type = _enum_val(
            client, "KeywordMatchTypeEnum", "EXACT"
        )
    elif svc == "CustomerNegativeCriterionService":
        op.create.placement.url = "https://excluded.example.com"
    elif svc == "CustomizerAttributeService":
        op.create.name = f"HarnessAttr_{tag[:10]}"
        op.create.type_ = _enum_val(
            client, "CustomizerAttributeTypeEnum", "TEXT"
        )
    elif svc == "CampaignCustomizerService":
        op.create.campaign = camp_rn
        op.create.customizer_attribute = cust_attr_rn
        op.create.value.type_ = _enum_val(
            client, "CustomizerAttributeTypeEnum", "TEXT"
        )
        op.create.value.string_value = "CampaignPromo"
    elif svc == "AdGroupCustomizerService":
        op.create.ad_group = ag_rn
        op.create.customizer_attribute = cust_attr_rn
        op.create.value.type_ = _enum_val(
            client, "CustomizerAttributeTypeEnum", "TEXT"
        )
        op.create.value.string_value = "AdGroupPromo"
    elif svc == "AdGroupCriterionCustomizerService":
        op.create.ad_group_criterion = agc_rn
        op.create.customizer_attribute = cust_attr_rn
        op.create.value.type_ = _enum_val(
            client, "CustomizerAttributeTypeEnum", "TEXT"
        )
        op.create.value.string_value = "KeywordPromo"
    elif svc == "CustomerCustomizerService":
        op.create.customizer_attribute = cust_attr_rn
        op.create.value.type_ = _enum_val(
            client, "CustomizerAttributeTypeEnum", "TEXT"
        )
        op.create.value.string_value = "CustomerPromo"
    elif svc == "AdParameterService":
        op.create.ad_group_criterion = agc_rn
        op.create.parameter_index = 1
        op.create.insertion_text = "99"
    elif svc == "ConversionActionService":
        op.update.resource_name = conv_rn
        op.update.value_settings.default_value = 1.0
        op.update_mask.paths.append("value_settings.default_value")
    elif svc == "ConversionCustomVariableService":
        op.create.name = f"Harness CustomVar {tag}"
        op.create.tag = f"hcv_{tag[:12]}"
    elif svc == "CustomConversionGoalService":
        op.create.name = f"Harness CustomGoal {tag}"
        op.create.conversion_actions.append(conv_rn)
    elif svc == "CampaignConversionGoalService":
        op.update.resource_name = (
            f"customers/{cid}/campaignConversionGoals/{camp_rn.split('/')[-1]}~DEFAULT~WEBSITE"
        )
        op.update.biddable = True
        op.update_mask.paths.append("biddable")
    elif svc == "CustomerConversionGoalService":
        op.update.resource_name = (
            f"customers/{cid}/customerConversionGoals/DEFAULT~WEBSITE"
        )
        op.update.biddable = True
        op.update_mask.paths.append("biddable")
    elif svc == "ConversionGoalCampaignConfigService":
        op.update.resource_name = (
            f"customers/{cid}/conversionGoalCampaignConfigs/{camp_rn.split('/')[-1]}"
        )
        op.update.goal_config_level = _enum_val(
            client, "GoalConfigLevelEnum", "CUSTOMER"
        )
        op.update_mask.paths.append("goal_config_level")
    elif svc == "ConversionValueRuleService":
        op.create.action.operation = _enum_val(
            client, "ValueRuleOperationEnum", "ADD"
        )
        op.create.action.value = 1.0
        op.create.device_condition.device_types.append(
            _enum_val(client, "ValueRuleDeviceTypeEnum", "MOBILE")
        )
    elif svc == "ConversionValueRuleSetService":
        op.create.dimensions.append(
            _enum_val(client, "ValueRuleSetDimensionEnum", "DEVICE")
        )
        op.create.conversion_value_rules.append(cvr_rn)
        op.create.attachment_type = _enum_val(
            client, "ValueRuleSetAttachmentTypeEnum", "CUSTOMER"
        )
    elif svc == "AudienceService":
        op.create.name = f"Harness Audience {tag}"
        op.create.description = "Harness audience"
        dim = client.get_type("AudienceDimension")
        seg = client.get_type("AudienceSegment")
        seg.user_list.user_list = ul_rn
        dim.audience_segments.segments.append(seg)
        op.create.dimensions.append(dim)
    elif svc == "CustomAudienceService":
        op.create.name = f"Harness CustomAudience {tag}"
        op.create.type_ = _enum_val(client, "CustomAudienceTypeEnum", "SEARCH")
        op.create.status = _enum_val(
            client, "CustomAudienceStatusEnum", "ENABLED"
        )
        mem = client.get_type("CustomAudienceMember")
        mem.member_type = _enum_val(
            client, "CustomAudienceMemberTypeEnum", "KEYWORD"
        )
        mem.keyword = "cloud computing"
        op.create.members.append(mem)
    elif svc == "CustomInterestService":
        op.create.name = f"Harness CustomInterest {tag}"
        op.create.type_ = _enum_val(
            client, "CustomInterestTypeEnum", "CUSTOM_AFFINITY"
        )
        op.create.status = _enum_val(
            client, "CustomInterestStatusEnum", "ENABLED"
        )
        mem = client.get_type("CustomInterestMember")
        mem.member_type = _enum_val(
            client, "CustomInterestMemberTypeEnum", "KEYWORD"
        )
        mem.parameter = "enterprise software"
        op.create.members.append(mem)
    elif svc == "UserListService":
        op.update.resource_name = ul_rn
        op.update.description = f"Updated CRM list {tag}"
        op.update_mask.paths.append("description")
    elif svc == "UserListCustomerTypeService":
        op.create.user_list = ul_rn
        op.create.customer_type_category = _enum_val(
            client, "UserListCustomerTypeCategoryEnum", "ALL_CUSTOMERS"
        )
    elif svc in ("UserDataService", "OfflineUserDataJobService"):
        uid = client.get_type("UserIdentifier")
        uid.hashed_email = (
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )
        op.create.user_identifiers.append(uid)
    elif svc == "KeywordPlanService":
        op.create.name = f"Harness KeywordPlan {tag}"
        op.create.forecast_period.date_interval = _enum_val(
            client, "KeywordPlanForecastIntervalEnum", "NEXT_MONTH"
        )
    elif svc == "KeywordPlanCampaignService":
        op.create.name = f"Harness KP Campaign {tag}"
        op.create.keyword_plan = kp_rn
        op.create.cpc_bid_micros = fixtures.safe_bid_micros
        op.create.keyword_plan_network = _enum_val(
            client, "KeywordPlanNetworkEnum", "GOOGLE_SEARCH"
        )
        op.create.language_constants.append("languageConstants/1000")
    elif svc == "KeywordPlanCampaignKeywordService":
        op.create.keyword_plan_campaign = kpc_rn
        op.create.text = f"kp neg {tag[:8]}"
        op.create.match_type = _enum_val(
            client, "KeywordMatchTypeEnum", "EXACT"
        )
        op.create.negative = True
    elif svc == "KeywordPlanAdGroupService":
        op.create.name = f"Harness KP AdGroup {tag}"
        op.create.keyword_plan_campaign = kpc_rn
        op.create.cpc_bid_micros = fixtures.safe_bid_micros
    elif svc == "KeywordPlanAdGroupKeywordService":
        op.create.keyword_plan_ad_group = kpag_rn
        op.create.text = f"kp kw {tag[:8]}"
        op.create.match_type = _enum_val(
            client, "KeywordMatchTypeEnum", "EXACT"
        )
        op.create.cpc_bid_micros = fixtures.safe_bid_micros
    elif svc == "BatchJobService":
        op.create.status = _enum_val(
            client, "BatchJobStatusEnum", "PENDING"
        )
    elif svc == "CampaignGroupService":
        op.create.name = f"Harness CampaignGroup {tag}"
        op.create.status = _enum_val(
            client, "CampaignGroupStatusEnum", "ENABLED"
        )
    elif svc == "CampaignDraftService":
        op.create.name = f"Harness Draft {tag}"
        op.create.base_campaign = camp_rn
    elif svc == "ExperimentService":
        op.create.name = f"Harness Experiment {tag}"
        op.create.type_ = _enum_val(
            client, "ExperimentTypeEnum", "SEARCH_CUSTOM"
        )
        op.create.suffix = f"[exp-{tag[:6]}]"
        op.create.status = _enum_val(
            client, "ExperimentStatusEnum", "SETUP"
        )
    elif svc == "ExperimentArmService":
        op.create.name = f"Harness Control Arm {tag}"
        op.create.experiment = exp_rn
        op.create.control = True
        op.create.traffic_split = 50
        op.create.campaigns.append(camp_rn)
    elif svc == "CustomerService":
        op.update.resource_name = f"customers/{cid}"
        op.update.auto_tagging_enabled = True
        op.update_mask.paths.append("auto_tagging_enabled")
    elif svc == "AccountBudgetProposalService":
        op.create.billing_setup = f"customers/{cid}/billingSetups/900000034"
        op.create.proposal_type = _enum_val(
            client, "AccountBudgetProposalTypeEnum", "CREATE"
        )
        op.create.proposed_name = f"Harness AccountBudget {tag}"
        op.create.proposed_start_time_type = _enum_val(
            client, "TimeTypeEnum", "NOW"
        )
        op.create.proposed_end_time_type = _enum_val(
            client, "TimeTypeEnum", "FOREVER"
        )
        op.create.proposed_spending_limit_micros = fixtures.safe_budget_micros
    elif svc == "BillingSetupService":
        op.create.payments_account = f"customers/{cid}/paymentsAccounts/1111-2222-3333-4444"
        op.create.start_time_type = _enum_val(client, "TimeTypeEnum", "NOW")
    elif svc == "AccountLinkService":
        op.update.resource_name = f"customers/{cid}/accountLinks/900000035"
        op.update.status = _enum_val(client, "AccountLinkStatusEnum", "ENABLED")
        op.update_mask.paths.append("status")
    elif svc == "CustomerClientLinkService":
        op.create.client_customer = f"customers/{cid}"
        op.create.status = _enum_val(
            client, "ManagerLinkStatusEnum", "PENDING"
        )
    elif svc == "CustomerManagerLinkService":
        op.update.resource_name = (
            f"customers/{cid}/customerManagerLinks/{cid}~900000036"
        )
        op.update.status = _enum_val(client, "ManagerLinkStatusEnum", "ACTIVE")
        op.update_mask.paths.append("status")
    elif svc == "CustomerUserAccessInvitationService":
        op.create.email_address = "test-harness-noreply@example.com"
        op.create.access_role = _enum_val(
            client, "AccessRoleEnum", "READ_ONLY"
        )
    elif svc == "CustomerUserAccessService":
        op.update.resource_name = f"customers/{cid}/customerUserAccesses/900000037"
        op.update.access_role = _enum_val(
            client, "AccessRoleEnum", "READ_ONLY"
        )
        op.update_mask.paths.append("access_role")
    elif svc == "CustomerSkAdNetworkConversionValueSchemaService":
        op.update.resource_name = (
            f"customers/{cid}/customerSkAdNetworkConversionValueSchemas/900000038"
        )
    elif svc == "CampaignGoalConfigService":
        op.create.campaign = camp_rn
        op.create.goal = f"customers/{cid}/goals/900000039"
    elif svc == "GoalService":
        op.create.goal_type = _enum_val(
            client, "GoalTypeEnum", "CUSTOMER_RETENTION"
        )
    elif svc == "RecommendationSubscriptionService":
        op.create.type_ = _enum_val(
            client, "RecommendationTypeEnum", "CAMPAIGN_BUDGET"
        )
        op.create.status = _enum_val(
            client, "RecommendationSubscriptionStatusEnum", "ENABLED"
        )
    elif svc == "RemarketingActionService":
        op.create.name = f"Harness RemarketingAction {tag}"
    elif svc == "SmartCampaignSettingService":
        op.update.resource_name = (
            f"customers/{cid}/smartCampaignSettings/{camp_rn.split('/')[-1]}"
        )
        op.update.business_name = "Harness Test Business"
        op.update_mask.paths.append("business_name")
    else:
        # Generic schema-driven fallback for any future/unlisted service
        if "create" in subfields:
            target = getattr(op, "create")
            if hasattr(target, "name"):
                target.name = f"Harness {svc} {tag}"
        elif "update" in subfields:
            target = getattr(op, "update")
            if hasattr(target, "resource_name"):
                target.resource_name = f"customers/{cid}/unknown/999999"
            if hasattr(op, "update_mask"):
                op.update_mask.paths.append("resource_name")


def register_created_fixture_from_method(
    method_meta: DiscoveredWriteMethod,
    resp_obj: Any,
    resp_dict: Optional[Dict[str, Any]],
    fixtures: FixtureRegistry,
) -> None:
    """Captures newly created parent resources during the test loop for downstream services."""
    rn = _extract_created_resource_name(resp_obj, resp_dict)
    if not rn:
        return
    svc = method_meta.service_name
    m_name = method_meta.method_snake_name

    if svc == "AssetSetService":
        fixtures.register(
            "asset_set", rn, "AssetSetService", "mutate_asset_sets", "AssetSetOperation"
        )
    elif svc == "CustomizerAttributeService":
        fixtures.register(
            "customizer_attribute",
            rn,
            "CustomizerAttributeService",
            "mutate_customizer_attributes",
            "CustomizerAttributeOperation",
        )
    elif svc == "ConversionValueRuleService":
        fixtures.register(
            "conversion_value_rule",
            rn,
            "ConversionValueRuleService",
            "mutate_conversion_value_rules",
            "ConversionValueRuleOperation",
        )
    elif svc == "KeywordPlanService":
        fixtures.register(
            "keyword_plan",
            rn,
            "KeywordPlanService",
            "mutate_keyword_plans",
            "KeywordPlanOperation",
        )
    elif svc == "KeywordPlanCampaignService":
        fixtures.register(
            "keyword_plan_campaign",
            rn,
            "KeywordPlanCampaignService",
            "mutate_keyword_plan_campaigns",
            "KeywordPlanCampaignOperation",
        )
    elif svc == "KeywordPlanAdGroupService":
        fixtures.register(
            "keyword_plan_ad_group",
            rn,
            "KeywordPlanAdGroupService",
            "mutate_keyword_plan_ad_groups",
            "KeywordPlanAdGroupOperation",
        )
    elif svc == "BatchJobService" and m_name == "mutate_batch_job":
        fixtures.register("batch_job", rn)
    elif svc == "OfflineUserDataJobService" and m_name == "create_offline_user_data_job":
        fixtures.register("offline_user_data_job", rn)
    elif svc == "CampaignDraftService" and m_name == "mutate_campaign_drafts":
        fixtures.register(
            "campaign_draft",
            rn,
            "CampaignDraftService",
            "mutate_campaign_drafts",
            "CampaignDraftOperation",
        )
    elif svc == "ExperimentService" and m_name == "mutate_experiments":
        fixtures.register(
            "experiment",
            rn,
            "ExperimentService",
            "mutate_experiments",
            "ExperimentOperation",
        )


def build_expected_failure_request(
    client: GoogleAdsClient,
    method_meta: DiscoveredWriteMethod,
    customer_id: str,
) -> Any:
    """Constructs an intentionally invalid request payload to exercise GoogleAdsException."""
    req = client.get_type(method_meta.request_type_name)
    if hasattr(req, "customer_id"):
        req.customer_id = str(customer_id)
    if method_meta.has_validate_only and hasattr(req, "validate_only"):
        req.validate_only = False

    # For requests with a repeated `operations` field, leaving `operations = []`
    # triggers `RequestError.OPERATIONS_CANNOT_BE_EMPTY` cleanly.
    if method_meta.operation_is_repeated:
        return req

    # For singular `operation` requests or non-operation requests, set a malformed
    # resource_name or empty operation to deterministically trigger GoogleAdsFailure.
    if method_meta.operation_field_name == "operation" and method_meta.operation_type_name:
        try:
            op = client.get_type(method_meta.operation_type_name)
        except ValueError:
            nested_cls = getattr(type(req), method_meta.operation_type_name, None)
            op = nested_cls() if nested_cls is not None else getattr(req, "operation")
        if "update" in method_meta.operation_subfields:
            target = getattr(op, "update")
            if hasattr(target, "resource_name"):
                target.resource_name = f"customers/{customer_id}/invalidResource/INVALID_ID"
        elif "create" in method_meta.operation_subfields:
            _ = getattr(op, "create")
        setattr(req, "operation", op)
        return req

    for attr_name in (
        "resource_name",
        "ad_group_ad",
        "campaign_draft",
        "experiment",
        "previous_customer_manager_link",
    ):
        if hasattr(req, attr_name):
            setattr(req, attr_name, f"customers/{customer_id}/invalid/INVALID_ID")

    return req


# ==============================================================================
# Summary Table Formatting & Main Execution Loop
# ==============================================================================


def print_summary_table(
    summaries: Sequence[MethodTestSummary],
    guardrail_passed: bool,
    log_path: str,
) -> None:
    """Prints a formatted summary table of all executed write RPC test cases."""
    fmt = "{:<44} {:<36} {:<14} {:<14} {:<32}"
    header = fmt.format("Service", "Method", "Success Case", "Failure Case", "Notes")
    sep = "-" * len(header)
    eq = "=" * len(header)

    print("\n" + eq)
    print("Google Ads API Write / Mutate Test Harness — Execution Summary")
    print(eq)
    print(header)
    print(sep)
    for item in summaries:
        s_badge = f"PASS ({item.success_status})" if item.success_passed else f"FAIL ({item.success_status})"
        f_badge = f"PASS ({item.failure_status})" if item.failure_passed else f"FAIL ({item.failure_status})"
        print(
            fmt.format(
                item.service_name[:43],
                item.grpc_method_name[:35],
                s_badge[:13],
                f_badge[:13],
                (item.notes or "")[:31],
            )
        )
    print(sep)
    guard_str = "PASSED (Blocked client-side)" if guardrail_passed else "FAILED"
    total = len(summaries)
    passed_count = sum(
        1 for s in summaries if s.success_passed and s.failure_passed
    )
    print(f"Total Write RPCs Tested : {total} ({passed_count}/{total} matched all assertions)")
    print(f"Financial Cap Guardrail : {guard_str}")
    print(f"Audit Log File (0600)   : {log_path}")
    print(eq)


def build_arg_parser() -> argparse.ArgumentParser:
    """Constructs the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="End-to-end test harness for Google Ads API mutate and write functions against a Google Ads Test Account."
    )
    parser.add_argument(
        "--customer-id",
        default=None,
        help="Target Google Ads Test Account Customer ID (overrides customer_id in config/assistant_config).",
    )
    parser.add_argument(
        "--service",
        default=None,
        help="Optional service name filter to run a single service during debugging (defaults to all mutate services).",
    )
    parser.add_argument(
        "--conversation-id",
        default=(
            os.environ.get("CONVERSATION_ID")
            or os.environ.get("CLAUDE_SESSION_ID")
            or os.environ.get("GEMINI_CONVERSATION_ID")
            or "standalone"
        ),
        help="Conversation or session identifier for the JSONL audit log filename.",
    )
    parser.add_argument(
        "--config-path",
        default=DEFAULT_CONFIG_PATH,
        help="Path to google-ads.yaml configuration file (default: config/google-ads.yaml).",
    )
    parser.add_argument(
        "--assistant-config",
        default=DEFAULT_ASSISTANT_CONFIG_PATH,
        help="Path to assistant_config TOML file (default: config/assistant_config).",
    )
    return parser


def run_harness(
    argv: Optional[Sequence[str]] = None,
    client: Optional[GoogleAdsClient] = None,
    log_dir: str = AUDIT_LOG_DIR,
) -> int:
    """Main execution entrypoint for the Google Ads API mutate test harness."""
    _install_open_shim()
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    assistant_cfg = parse_assistant_config(args.assistant_config)
    api_version = str(assistant_cfg.get("api_version") or DEFAULT_API_VERSION).strip()
    customer_id = (
        str(args.customer_id).strip().replace("-", "")
        if args.customer_id
        else str(assistant_cfg.get("customer_id") or "").strip().replace("-", "")
    )
    if not customer_id:
        print(
            f"Configuration Error: No customer_id provided via --customer-id or '{args.assistant_config}'.",
            file=sys.stderr,
        )
        return 2

    max_fin_micros: Optional[int] = assistant_cfg.get("max_financial_mutate_micros")

    # Discover all state-changing services and write RPCs
    methods = discover_write_rpcs(api_version=api_version, service_filter=args.service)
    if not methods:
        print(
            f"Error: No write RPCs discovered for api_version={api_version!r} "
            f"and service_filter={args.service!r}.",
            file=sys.stderr,
        )
        return 1

    financial_scheduled = is_financial_service_scheduled(methods, args.service)

    # Initialize GoogleAdsClient from storage using api_version from config/assistant_config
    if client is None:
        try:
            if args.config_path == DEFAULT_CONFIG_PATH:
                client = GoogleAdsClient.load_from_storage(
                    path="config/google-ads.yaml", version=api_version
                )
            else:
                client = GoogleAdsClient.load_from_storage(
                    path=args.config_path, version=api_version
                )
        except Exception as ex:
            if financial_scheduled and (max_fin_micros is None or max_fin_micros <= 0):
                verify_financial_config_or_abort(
                    max_fin_micros, args.assistant_config, financial_scheduled
                )
            print(
                f"Error loading GoogleAdsClient from '{args.config_path}' (version={api_version}): {ex}",
                file=sys.stderr,
            )
            return 2

    username, gcp_project_number, login_customer_id = extract_client_identity_metadata(
        args.config_path, client=client
    )
    audit_logger = AuditLogger(
        conversation_id=args.conversation_id,
        username=username,
        api_version=api_version,
        gcp_project_number=gcp_project_number,
        login_customer_id=login_customer_id,
        log_dir=log_dir,
    )
    interceptor = RequestIdCaptureInterceptor()

    print_startup_manifest(
        api_version=api_version,
        customer_id=customer_id,
        methods=methods,
        log_path=audit_logger.log_path,
    )

    # 1. Mandatory Test Account Pre-Flight Gate (Fail-Closed, exit code 2 if non-test account)
    run_preflight_test_account_gate(
        client=client,
        customer_id=customer_id,
        audit_logger=audit_logger,
        interceptor=interceptor,
        max_financial_mutate_micros=max_fin_micros,
        assistant_config_path=args.assistant_config,
        financial_scheduled=financial_scheduled,
    )

    # 2. Enforce financial upper-limit configuration requirement before any write RPC
    verified_limit_micros = verify_financial_config_or_abort(
        max_fin_micros, args.assistant_config, financial_scheduled
    )

    # 3. Verify client-side financial upper-limit guardrail blocks excessive payloads
    guardrail_passed = run_financial_guardrail_verification(
        client=client,
        customer_id=customer_id,
        max_financial_mutate_micros=verified_limit_micros,
        audit_logger=audit_logger,
        interceptor=interceptor,
    )

    run_tag = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    fixtures = FixtureRegistry(
        customer_id=customer_id,
        run_tag=run_tag,
        max_financial_mutate_micros=verified_limit_micros,
    )

    summaries: List[MethodTestSummary] = []
    try:
        # 4. Provision dependency-ordered test fixtures when running full suite or dependent service
        if args.service is None or len(methods) > 1 or methods[0].service_name not in (
            "CampaignBudgetService",
            "LabelService",
            "AssetService",
            "SharedSetService",
            "ConversionActionService",
            "UserListService",
        ):
            provision_test_fixtures(
                client=client,
                fixtures=fixtures,
                audit_logger=audit_logger,
                interceptor=interceptor,
            )

        # 5. Execute SUCCESS and EXPECTED_FAILURE scenarios for every discovered write function
        for method_meta in methods:
            # 5a. SUCCESS scenario
            success_req = build_success_request(client, method_meta, fixtures)
            s_passed, s_status, resp_obj, resp_dict, s_note = execute_logged_write_rpc(
                client=client,
                service_name=method_meta.service_name,
                method_snake_name=method_meta.method_snake_name,
                grpc_method_name=method_meta.grpc_method_name,
                request_obj=success_req,
                scenario="SUCCESS",
                audit_logger=audit_logger,
                interceptor=interceptor,
                max_financial_mutate_micros=verified_limit_micros,
            )
            register_created_fixture_from_method(
                method_meta, resp_obj, resp_dict, fixtures
            )

            # 5b. EXPECTED_FAILURE scenario
            failure_req = build_expected_failure_request(
                client, method_meta, customer_id
            )
            f_passed, f_status, _, _, f_note = execute_logged_write_rpc(
                client=client,
                service_name=method_meta.service_name,
                method_snake_name=method_meta.method_snake_name,
                grpc_method_name=method_meta.grpc_method_name,
                request_obj=failure_req,
                scenario="EXPECTED_FAILURE",
                audit_logger=audit_logger,
                interceptor=interceptor,
                max_financial_mutate_micros=verified_limit_micros,
            )

            combined_note = s_note if s_note != "OK" else f_note
            summaries.append(
                MethodTestSummary(
                    service_name=method_meta.service_name,
                    grpc_method_name=method_meta.grpc_method_name,
                    method_snake_name=method_meta.method_snake_name,
                    success_passed=s_passed,
                    failure_passed=f_passed,
                    success_status=s_status,
                    failure_status=f_status,
                    notes=combined_note,
                )
            )
    finally:
        # 6. Teardown provisioned fixtures in reverse dependency order
        teardown_test_fixtures(
            client=client,
            fixtures=fixtures,
            audit_logger=audit_logger,
            interceptor=interceptor,
        )

    print_summary_table(
        summaries=summaries,
        guardrail_passed=guardrail_passed,
        log_path=audit_logger.log_path,
    )

    all_passed = guardrail_passed and all(
        s.success_passed and s.failure_passed for s in summaries
    )
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(run_harness())

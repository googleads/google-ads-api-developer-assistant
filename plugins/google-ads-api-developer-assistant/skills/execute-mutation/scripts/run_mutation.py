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
from typing import Any, Dict, List, Optional, Tuple
import uuid


RECEIPT_FILENAME = "last_dry_run.json"
AUDIT_LOG_FILENAME = "mutation_audit.jsonl"
ASSISTANT_CONFIG_FILENAME = "assistant_config"
EXECUTE_MUTATES_FILENAME = ASSISTANT_CONFIG_FILENAME
DEFAULT_MAX_RECEIPT_AGE_SECONDS = 1800  # 30 minutes
_TRACE_ENV_VAR = "_GOOGLE_ADS_MUTATION_TRACE_FILE"
_EXPECTED_HASHES_ENV_VAR = "_GOOGLE_ADS_EXPECTED_REQUEST_SHA256"
_ENFORCE_HASH_ENV_VAR = "_GOOGLE_ADS_ENFORCE_REQUEST_SHA256"

_MUTATION_METHOD_PREFIXES = (
    "mutate",
    "apply_recommendation",
    "upload_click_conversions",
    "upload_call_conversions",
    "add_batch_job_operations",
    "run_batch_job",
)

_SENSITIVE_KEYS = frozenset({
    "developer_token",
    "client_secret",
    "refresh_token",
    "private_key",
    "json_key",
})


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

                # Pre-RPC Mutates Config check: block live mutations if execute_mutates = false
                is_live_rpc = (
                    isinstance(req_payload, dict)
                    and req_payload.get("validate_only") is False
                ) or should_enforce
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
) -> Tuple[subprocess.CompletedProcess[str], str, str, float, List[Dict[str, Any]]]:
    """Runs the mutation script in a subprocess with RPC audit interception and pre-RPC SHA-256 verification."""
    fd, trace_path = tempfile.mkstemp(prefix="ads_mutation_trace_", suffix=".json")
    os.close(fd)

    env = os.environ.copy()
    env[_TRACE_ENV_VAR] = trace_path
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
    expected_receipt_sha256 = str(
        receipt_data.get("request_sha256") or aggregate_request_sha256
    )
    if calls:
        request_sha256_verified = all(
            bool(c.get("request_sha256_verified", True)) for c in calls
        ) and (
            phase != "EXECUTE"
            or not receipt_data.get("request_sha256")
            or aggregate_request_sha256 == expected_receipt_sha256
        )
    else:
        request_sha256_verified = (
            phase != "EXECUTE"
            or not receipt_data.get("request_sha256")
            or aggregate_request_sha256 == expected_receipt_sha256
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
    dry_run_calls = receipt.get("dry_run_rpc_calls")
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
    return (
        "======================================================================\n"
        "GOOGLE ADS API MUTATION & CONSEQUENCE VERIFICATION CARD\n"
        "======================================================================\n"
        f"Customer ID   : {receipt.get('customer_id', 'Unknown')}\n"
        f"Operation     : {receipt.get('operation_summary', 'Unknown')}\n"
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

        if not args.record_only:
            result, sent_at_iso, received_at_iso, duration_ms, captured_calls = (
                _execute_script_subprocess(script_path, script_args)
            )
            if result.returncode != 0:
                append_mutation_audit_log(
                    phase="DRY_RUN",
                    status="DRY_RUN_FAILED",
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
                    exit_code=result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    command=[sys.executable, script_path, *script_args],
                    rpc_calls=captured_calls,
                )
                print(
                    f"validate_only=True Dry-Run FAILED (exit code {result.returncode}):\n"
                    f"{result.stdout}\n{result.stderr}",
                    file=sys.stderr,
                )
                sys.exit(result.returncode)
            dry_run_output = (result.stdout + "\n" + result.stderr).strip()

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
        print(f"BLOCKED: {message}", file=sys.stderr)
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
            expected_request_hashes=expected_rpc_hashes,
            enforce_request_hash=True,
        )
    )

    consequences_from_receipt = [
        str(c) for c in receipt.get("consequences", []) if str(c).strip()
    ]
    operation_summary = str(args.operation or receipt.get("operation_summary", ""))
    before_state = str(receipt.get("before_state", args.before))
    after_state = str(receipt.get("after_state", args.after or operation_summary))
    reversibility = str(receipt.get("reversibility", args.reversibility))

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

    if result.returncode != 0 or blocked_by_sha_mismatch or missing_expected_calls:
        failure_status = (
            "BLOCKED_SHA256_MISMATCH"
            if (blocked_by_sha_mismatch or missing_expected_calls)
            else "FAILED"
        )
        effective_exit_code = result.returncode if result.returncode != 0 else 2
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

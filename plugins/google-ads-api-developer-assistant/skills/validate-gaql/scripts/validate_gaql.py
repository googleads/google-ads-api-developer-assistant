# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""GAQL Query Validator Skill.

This script performs a dry-run validation of a GAQL query using the
validate_only=True parameter. It accepts queries via the --query / -q flag
or reads from stdin when input is piped or --query is omitted.
"""

import argparse
import hashlib
import importlib
import json
import os
import re
import sys
import tempfile
import time
from typing import Any, Dict, Optional

DEFAULT_CACHE_TTL_SECONDS: float = 86400.0
_GAQL_MEMORY_CACHE: Dict[str, Dict[str, Any]] = {}
_LAST_PYTEST_TEST: Optional[str] = None


def _normalize_api_version(api_version: str) -> str:
    clean_version = api_version.strip().lower()
    if clean_version and not clean_version.startswith("v") and clean_version.isdigit():
        clean_version = f"v{clean_version}"
    return clean_version


def compute_gaql_cache_key(query: str, api_version: str) -> str:
    """Computes the SHA-256 cache key for a (query + api_version) pair."""
    clean_query = query.strip()
    clean_version = _normalize_api_version(api_version)
    raw = f"{clean_query}|{clean_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _get_cache_file_path(cache_path: Optional[str] = None) -> str:
    """Resolves the file path for persistent GAQL validation caching."""
    global _LAST_PYTEST_TEST
    if cache_path:
        return os.path.abspath(cache_path)

    env_path = os.environ.get("GAQL_CACHE_PATH", "").strip()
    if env_path:
        return os.path.abspath(env_path)

    pytest_current = os.environ.get("PYTEST_CURRENT_TEST")
    if pytest_current:
        if _LAST_PYTEST_TEST != pytest_current:
            _GAQL_MEMORY_CACHE.clear()
            _LAST_PYTEST_TEST = pytest_current
        test_hash = hashlib.sha256(
            f"{os.getpid()}:{pytest_current}".encode("utf-8")
        ).hexdigest()[:16]
        return os.path.join(
            tempfile.gettempdir(), f"gads_gaql_cache_{test_hash}.json"
        )

    return os.path.abspath(
        os.path.join("saved", "data", "gaql_validation_cache.json")
    )


def _load_disk_cache(file_path: str) -> Dict[str, Dict[str, Any]]:
    if not os.path.isfile(file_path):
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _save_disk_cache(file_path: str, data: Dict[str, Dict[str, Any]]) -> None:
    try:
        parent = os.path.dirname(file_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def get_cached_validation(
    query: str,
    api_version: str,
    cache_path: Optional[str] = None,
    ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
) -> Optional[Dict[str, Any]]:
    """Retrieves a cached validation result for (query, api_version) if present and not expired."""
    resolved_path = _get_cache_file_path(cache_path)
    key = compute_gaql_cache_key(query, api_version)
    mem_key = f"{resolved_path}:{key}"

    entry = _GAQL_MEMORY_CACHE.get(mem_key)
    disk_data: Optional[Dict[str, Dict[str, Any]]] = None
    if entry is None:
        disk_data = _load_disk_cache(resolved_path)
        entry = disk_data.get(key)
        if entry is not None:
            _GAQL_MEMORY_CACHE[mem_key] = entry

    if entry is None:
        return None

    now = time.time()
    ts = float(entry.get("timestamp", 0.0))
    if ttl_seconds <= 0 or (now - ts) > ttl_seconds:
        # Expired: invalidate from memory and disk
        _GAQL_MEMORY_CACHE.pop(mem_key, None)
        if disk_data is None:
            disk_data = _load_disk_cache(resolved_path)
        if key in disk_data:
            del disk_data[key]
            _save_disk_cache(resolved_path, disk_data)
        return None

    return dict(entry)


def set_cached_validation(
    query: str,
    api_version: str,
    valid: bool = True,
    message: str = "SUCCESS: GAQL query is structurally valid.",
    cache_path: Optional[str] = None,
    timestamp: Optional[float] = None,
) -> Dict[str, Any]:
    """Stores a validation result in both memory and on-disk cache keyed by SHA-256(query + api_version)."""
    resolved_path = _get_cache_file_path(cache_path)
    key = compute_gaql_cache_key(query, api_version)
    mem_key = f"{resolved_path}:{key}"

    entry: Dict[str, Any] = {
        "key": key,
        "query": query.strip(),
        "api_version": _normalize_api_version(api_version),
        "valid": bool(valid),
        "message": message,
        "timestamp": float(timestamp if timestamp is not None else time.time()),
    }
    _GAQL_MEMORY_CACHE[mem_key] = entry
    disk_data = _load_disk_cache(resolved_path)
    disk_data[key] = entry
    _save_disk_cache(resolved_path, disk_data)
    return dict(entry)


def invalidate_gaql_cache(
    query: Optional[str] = None,
    api_version: Optional[str] = None,
    cache_path: Optional[str] = None,
) -> int:
    """Invalidates cached GAQL validation results.

    - If both `query` and `api_version` are provided, invalidates that specific entry.
    - If only `api_version` is provided, invalidates all entries for that API version.
    - If neither is provided, clears the entire cache.
    Returns the number of invalidated cache entries.
    """
    resolved_path = _get_cache_file_path(cache_path)
    disk_data = _load_disk_cache(resolved_path)
    removed = 0

    if query is not None and api_version is not None:
        key = compute_gaql_cache_key(query, api_version)
        mem_key = f"{resolved_path}:{key}"
        in_mem = _GAQL_MEMORY_CACHE.pop(mem_key, None) is not None
        in_disk = disk_data.pop(key, None) is not None
        if in_disk:
            _save_disk_cache(resolved_path, disk_data)
        return 1 if (in_mem or in_disk) else 0

    if api_version is not None:
        norm_ver = _normalize_api_version(api_version)
        keys_to_delete = [
            k for k, v in disk_data.items() if v.get("api_version") == norm_ver
        ]
        for k in keys_to_delete:
            del disk_data[k]
            _GAQL_MEMORY_CACHE.pop(f"{resolved_path}:{k}", None)
            removed += 1
        for mk in list(_GAQL_MEMORY_CACHE.keys()):
            if mk.startswith(f"{resolved_path}:") and _GAQL_MEMORY_CACHE[mk].get("api_version") == norm_ver:
                del _GAQL_MEMORY_CACHE[mk]
                if mk.split(":", 1)[-1] not in keys_to_delete:
                    removed += 1
        if keys_to_delete:
            _save_disk_cache(resolved_path, disk_data)
        return removed

    # Clear all entries for resolved_path
    removed_keys = set(disk_data.keys())
    for mk in list(_GAQL_MEMORY_CACHE.keys()):
        if mk.startswith(f"{resolved_path}:"):
            removed_keys.add(mk.split(":", 1)[-1])
            del _GAQL_MEMORY_CACHE[mk]
    if disk_data or os.path.isfile(resolved_path):
        _save_disk_cache(resolved_path, {})
    return len(removed_keys)


def _get_config_path() -> str:
    config_path = os.environ.get("GOOGLE_ADS_CONFIGURATION_FILE_PATH")
    if config_path and os.path.isfile(config_path):
        return config_path

    candidates = [
        os.path.expanduser("~/.gemini/config/plugins/google-ads-api-developer-assistant/config/google-ads.yaml"),
        os.path.abspath("config/google-ads.yaml"),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../config/google-ads.yaml")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../config/google-ads.yaml")),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c

    try:
        from config.config_init import sync_and_set_config_kv
        return sync_and_set_config_kv()
    except Exception:
        pass

    return os.path.abspath("config/google-ads.yaml")


try:
    from google.ads.googleads.client import GoogleAdsClient
    from google.ads.googleads.errors import GoogleAdsException
except ImportError:
    GoogleAdsClient = None  # type: ignore
    GoogleAdsException = Exception  # type: ignore


def handle_googleads_exception(exception: GoogleAdsException) -> None:
    """Prints the details of a GoogleAdsException."""
    print(f"FAILURE: Query validation failed with Request ID {exception.request_id}")
    for error in exception.failure.errors:
        print(f"  - {error.message}")
        if error.location:
            for element in error.location.field_path_elements:
                print(f"    On field: {element.field_name}")


def validate_gaql(
    customer_id: str,
    api_version: str,
    query: str,
    client: Optional[GoogleAdsClient] = None,
    use_cache: bool = True,
    cache_path: Optional[str] = None,
    cache_ttl: float = DEFAULT_CACHE_TTL_SECONDS,
) -> None:
    """Validates a GAQL query by performing static analysis and a dry run against the API."""
    if not query:
        print("Error: No query provided.")
        sys.exit(1)

    if use_cache:
        cached = get_cached_validation(
            query=query,
            api_version=api_version,
            cache_path=cache_path,
            ttl_seconds=cache_ttl,
        )
        if cached is not None:
            if cached.get("valid", True):
                print("SUCCESS: GAQL query is structurally valid. (cached)")
                return
            print(cached.get("message", "FAILURE: GAQL query validation failed. (cached)"))
            sys.exit(1)

    # Static Analysis
    query_upper = query.upper()
    has_from = " FROM " in query_upper or query_upper.strip().startswith("SELECT") and "FROM" in query_upper

    # Check for forbidden OR operator in WHERE clause
    where_match = re.search(
        r"\bWHERE\b(.*?)(\bORDER\s+BY\b|\bLIMIT\b|$)",
        query_upper,
        re.DOTALL,
    )
    if where_match:
        where_clause = where_match.group(1)
        if re.search(r"\bOR\b", where_clause):
            print("FAILURE: GAQL query contains forbidden OR operator in WHERE clause.")
            print("  - GAQL does not support the OR operator. Use IN or execute separate queries instead.")
            sys.exit(1)

    # Check for forbidden aggregate functions
    agg_funcs = ["COUNT", "SUM", "AVG", "MIN", "MAX"]
    for func in agg_funcs:
        if re.search(r"\b" + func + r"\b\s*\(", query_upper):
            print(f"FAILURE: GAQL query contains forbidden aggregate function '{func}'.")
            print("  - GAQL does not support standard SQL aggregate functions.")
            sys.exit(1)

    # Check for forbidden date/time functions
    date_funcs = ["NOW", "CURRENT_DATE"]
    for func in date_funcs:
        if re.search(r"\b" + func + r"\b", query_upper):
            print(f"FAILURE: GAQL query contains forbidden date/time function '{func}'.")
            print("  - GAQL does not support SQL date/time functions like NOW() or CURRENT_DATE().")
            sys.exit(1)

    # Core date segment check
    select_match = re.search(r"\bSELECT\s+(.*?)\s+FROM\b", query_upper, re.DOTALL)
    if select_match:
        select_clause = select_match.group(1)
        date_segs = [
            "SEGMENTS.DATE",
            "SEGMENTS.WEEK",
            "SEGMENTS.MONTH",
            "SEGMENTS.QUARTER",
            "SEGMENTS.YEAR",
            "SEGMENTS.DAY_OF_WEEK",
        ]
        has_date_segment = any(re.search(r"\b" + seg + r"\b", select_clause) for seg in date_segs)
        if has_date_segment:
            date_filter_match = where_match and re.search(
                r"(\bSEGMENTS\.(DATE|WEEK|MONTH|QUARTER|YEAR|DAY_OF_WEEK)\s*(=|>=|<=|BETWEEN|DURING)\b|\bDURING\b|\bBETWEEN\b)",
                where_match.group(1),
            )
            if not date_filter_match:
                print(
                    "FAILURE: GAQL query selects a date segment but does not specify a finite date filter (DURING or BETWEEN) in the WHERE clause."
                )
                sys.exit(1)

    # click_view check
    if "FROM CLICK_VIEW" in query_upper:
        if not where_match:
            print("FAILURE: Queries against 'click_view' require a single-day filter on segments.date.")
            sys.exit(1)
        where_clause = where_match.group(1)
        if not re.search(r"SEGMENTS\.DATE\s*=\s*['\"][0-9]{4}-[0-9]{2}-[0-9]{2}['\"]", where_clause):
            print("FAILURE: Queries against 'click_view' require a single-day filter using equal operator (e.g., WHERE segments.date = 'YYYY-MM-DD').")
            sys.exit(1)

    # change_status check
    if "FROM CHANGE_STATUS" in query_upper:
        if not where_match:
            print("FAILURE: Queries against 'change_status' require a finite BETWEEN filter on last_change_date_time.")
            sys.exit(1)
        where_clause = where_match.group(1)
        if "LAST_CHANGE_DATE_TIME" not in where_clause or " BETWEEN " not in where_clause:
            print("FAILURE: Queries against 'change_status' require a finite BETWEEN filter on last_change_date_time.")
            sys.exit(1)
        limit_match = re.search(r"\bLIMIT\s+(\d+)", query_upper)
        if not limit_match:
            print("FAILURE: Queries against 'change_status' require a LIMIT clause.")
            sys.exit(1)
        limit_val = int(limit_match.group(1))
        if limit_val > 10000:
            print("FAILURE: Queries against 'change_status' support a maximum LIMIT of 10,000.")
            sys.exit(1)

    # Metadata query pitfalls
    if "GOOGLE_ADS_FIELD" in query_upper:
        if has_from:
            print("FAILURE: Metadata queries (google_ads_field) MUST NOT contain a FROM clause.")
            print("  - Incorrect: SELECT name FROM google_ads_field")
            print("  - Correct: SELECT name")
            sys.exit(1)
        if any(prefix in query_upper for prefix in ["GOOGLE_ADS_FIELD.", "METRICS.", "SEGMENTS."]):
            print("FAILURE: Metadata queries MUST NOT use resource/segment prefixes (e.g., use 'name', not 'google_ads_field.name').")
            sys.exit(1)

    # Segment rename check: segments.hour -> segments.hour_of_day in v23+
    ver_match = re.search(r"v(\d+)", api_version.lower())
    ver_num = int(ver_match.group(1)) if ver_match else None
    if ver_num is None or ver_num >= 23:
        if re.search(r"\bSEGMENTS\.HOUR\b", query_upper):
            print("FAILURE: GAQL query references deprecated segment 'segments.hour'.")
            print("  - In Google Ads API v23+, 'segments.hour' was renamed to 'segments.hour_of_day'.")
            print("  - Please update your query to use 'segments.hour_of_day'.")
            sys.exit(1)

    search_request_type = None
    api_version_lower = api_version.lower()
    module_path = (
        f"google.ads.googleads.{api_version_lower}.services.types.google_ads_service"
    )
    try:
        module = importlib.import_module(module_path)
        search_request_type = getattr(module, "SearchGoogleAdsRequest", None)
    except (ImportError, AttributeError):
        pass

    if client is None:
        if GoogleAdsClient is None:
            print("CRITICAL ERROR: google-ads package is not installed.")
            sys.exit(1)
        try:
            cfg_path = _get_config_path()
            client = GoogleAdsClient.load_from_storage(path=cfg_path, version=api_version)
        except Exception as e:
            print(f"CRITICAL ERROR: Failed to load Google Ads configuration: {e}")
            sys.exit(1)

    if search_request_type is None and client is not None:
        try:
            search_request_type = client.get_type("SearchGoogleAdsRequest")
        except Exception:
            pass

    ga_service = client.get_service("GoogleAdsService")
    clean_customer_id = "".join(re.findall(r"\d+", str(customer_id)))

    try:
        print(f"--- [DRY RUN] Validating Query for {clean_customer_id} ---")
        if search_request_type is not None:
            request = search_request_type(
                customer_id=clean_customer_id, query=query, validate_only=True
            )
        else:
            request = {
                "customer_id": clean_customer_id,
                "query": query,
                "validate_only": True,
            }
        ga_service.search(request=request)
        print("SUCCESS: GAQL query is structurally valid.")
        if use_cache:
            set_cached_validation(
                query=query,
                api_version=api_version,
                valid=True,
                message="SUCCESS: GAQL query is structurally valid.",
                cache_path=cache_path,
            )
    except GoogleAdsException as ex:
        handle_googleads_exception(ex)
        sys.exit(1)
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        sys.exit(1)


def main() -> None:
    """Parses command line arguments and calls validate_gaql."""
    parser = argparse.ArgumentParser(description="Validates a GAQL query.")
    parser.add_argument("--customer_id", required=True, help="Google Ads Customer ID.")
    parser.add_argument(
        "--api_version",
        required=True,
        help="API Version (e.g., v24).",
    )
    parser.add_argument(
        "-q",
        "--query",
        required=False,
        default=None,
        help="The GAQL query to validate. If omitted, reads from stdin.",
    )
    parser.add_argument(
        "--no_cache",
        "--no-cache",
        dest="no_cache",
        action="store_true",
        help="Bypass the local GAQL validation response cache.",
    )
    parser.add_argument(
        "--clear_cache",
        "--clear-cache",
        dest="clear_cache",
        action="store_true",
        help="Clear the local GAQL validation response cache before running.",
    )
    parser.add_argument(
        "--cache_path",
        "--cache-path",
        dest="cache_path",
        default=None,
        help="Optional path to the local GAQL validation cache JSON file.",
    )
    parser.add_argument(
        "--cache_ttl",
        "--cache-ttl",
        dest="cache_ttl",
        type=float,
        default=DEFAULT_CACHE_TTL_SECONDS,
        help="Cache entry TTL in seconds (default: 86400).",
    )
    args = parser.parse_args()

    if args.clear_cache:
        invalidate_gaql_cache(cache_path=args.cache_path)

    query = args.query
    if query is None:
        if not sys.stdin.isatty():
            query = sys.stdin.read().strip()
        else:
            print(
                "Error: No GAQL query provided. Pass via --query / -q or pipe via stdin.",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        query = query.strip()

    validate_gaql(
        args.customer_id,
        args.api_version,
        query,
        use_cache=not args.no_cache,
        cache_path=args.cache_path,
        cache_ttl=args.cache_ttl,
    )


if __name__ == "__main__":
    main()


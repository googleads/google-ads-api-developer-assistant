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

"""Protobuf Object and Enum Inspection Skill Script."""

import argparse
import ast
import difflib
import glob
import importlib.metadata
import json
import os
import re
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from google.ads.googleads.client import GoogleAdsClient
except ImportError:
    GoogleAdsClient = None  # type: ignore

_PROTO_FIELD_TYPES: Dict[int, str] = {
    1: "DOUBLE",
    2: "FLOAT",
    3: "INT64",
    4: "UINT64",
    5: "INT32",
    6: "FIXED64",
    7: "FIXED32",
    8: "BOOL",
    9: "STRING",
    10: "GROUP",
    11: "MESSAGE",
    12: "BYTES",
    13: "UINT32",
    14: "ENUM",
    15: "SFIXED32",
    16: "SFIXED64",
    17: "SINT32",
    18: "SINT64",
}


def _normalize_api_version(api_version: str) -> str:
    clean = str(api_version or "").strip().lower()
    if clean and not clean.startswith("v") and clean.isdigit():
        clean = f"v{clean}"
    clean = re.sub(r"[^a-zA-Z0-9_.-]", "", clean).lstrip(".")
    return clean or "v26"


def _get_default_api_version() -> str:
    env_ver = os.environ.get("GOOGLE_ADS_API_VERSION", "").strip()
    if env_ver:
        return _normalize_api_version(env_ver)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.abspath("config/assistant_config"),
        os.path.abspath(os.path.join(script_dir, "../../../config/assistant_config")),
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/config/assistant_config"
        ),
        os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/config/assistant_config"
        ),
    ]
    for cfg in candidates:
        if os.path.isfile(cfg):
            try:
                with open(cfg, "r", encoding="utf-8") as f:
                    m = re.search(
                        r'(?m)^\s*api_version\s*=\s*["\']?([^"\'\s#]+)["\']?',
                        f.read(),
                    )
                if m and m.group(1).strip():
                    return _normalize_api_version(m.group(1).strip())
            except OSError:
                continue
    return "v26"


def _get_config_path() -> str:
    config_path = os.environ.get("GOOGLE_ADS_CONFIGURATION_FILE_PATH")
    if config_path:
        expanded_env = os.path.abspath(os.path.expanduser(config_path))
        raw_home_yaml = os.path.abspath(os.path.expanduser("~/google-ads.yaml"))
        if expanded_env != raw_home_yaml and os.path.isfile(expanded_env):
            return config_path if os.path.isfile(config_path) else expanded_env

    script_dir = os.path.dirname(os.path.abspath(__file__))
    plugin_root = os.path.abspath(os.path.join(script_dir, "../../.."))
    candidates = [
        os.path.abspath("config/google-ads.yaml"),
        os.path.join(plugin_root, "config", "google-ads.yaml"),
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/config/google-ads.yaml"
        ),
        os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/config/google-ads.yaml"
        ),
        os.path.abspath(os.path.join(script_dir, "../../../../config/google-ads.yaml")),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c

    try:
        if plugin_root not in sys.path and os.path.isdir(plugin_root):
            sys.path.insert(0, plugin_root)
        from config.config_init import sync_and_set_config_kv

        return sync_and_set_config_kv()
    except Exception:
        pass

    return os.path.abspath("config/google-ads.yaml")


def check_version_parity() -> None:
    """Checks if installed google-ads version matches client_libs version used for protobuf definitions."""
    installed_version = None
    try:
        installed_version = importlib.metadata.version("google-ads")
    except Exception:
        pass

    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.abspath("client_libs/google-ads-python"),
        os.path.abspath(os.path.join(script_dir, "../../../client_libs/google-ads-python")),
        os.path.abspath(os.path.join(script_dir, "../../../../client_libs/google-ads-python")),
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/client_libs/google-ads-python"
        ),
        os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/client_libs/google-ads-python"
        ),
    ]

    client_libs_version = None
    for cand in candidates:
        pyproject = os.path.join(cand, "pyproject.toml")
        if os.path.isfile(pyproject):
            try:
                with open(pyproject, "r", encoding="utf-8") as f:
                    m = re.search(r'version\s*=\s*["\']([^"\']+)["\']', f.read())
                    if m:
                        client_libs_version = m.group(1).strip()
                        break
            except Exception:
                pass
        changelog = os.path.join(cand, "ChangeLog")
        if os.path.isfile(changelog):
            try:
                with open(changelog, "r", encoding="utf-8") as f:
                    for line in f:
                        m = re.search(r"^\*\s*([\d\.\w\-]+)", line)
                        if m:
                            client_libs_version = m.group(1).strip()
                            break
                    if client_libs_version:
                        break
            except Exception:
                pass

    if installed_version and client_libs_version:
        v_inst = installed_version.lstrip("v").strip()
        v_cl = client_libs_version.lstrip("v").strip()
        if v_inst != v_cl:
            print(
                f"WARNING: Installed google-ads package version ({installed_version}) does not match "
                f"client_libs/google-ads-python version ({client_libs_version}) used for protobuf inspection. "
                f"Schema inspection or API calls may encounter field discrepancies.",
                file=sys.stderr,
            )


_CLASS_DEF_RE = re.compile(r"^class\s+([A-Za-z0-9_]+)\b", re.MULTILINE)
_NON_ALNUM_RE = re.compile(r"[^a-zA-Z0-9]")
_AVAILABLE_TYPES_CACHE: Dict[Tuple[str, float], Dict[str, str]] = {}


def get_available_types(api_version: str) -> Dict[str, str]:
    """Finds all available message and enum type names and their file paths."""
    version_clean = _normalize_api_version(api_version)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.abspath("client_libs/google-ads-python"),
        os.path.abspath(os.path.join(script_dir, "../../../client_libs/google-ads-python")),
        os.path.abspath(os.path.join(script_dir, "../../../../client_libs/google-ads-python")),
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/client_libs/google-ads-python"
        ),
        os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/google-ads-api-developer-assistant/client_libs/google-ads-python"
        ),
    ]
    v_dir = None
    for cand in candidates:
        cand_v_dir = os.path.join(cand, "google", "ads", "googleads", version_clean)
        if os.path.isdir(cand_v_dir):
            v_dir = cand_v_dir
            break

    if v_dir is None:
        try:
            import google.ads.googleads as _gads_pkg  # type: ignore[import-untyped]

            for pkg_root in getattr(_gads_pkg, "__path__", []):
                cand_v_dir = os.path.join(pkg_root, version_clean)
                if os.path.isdir(cand_v_dir):
                    v_dir = cand_v_dir
                    break
        except Exception:
            pass

    type_map: Dict[str, str] = {}
    if not v_dir:
        return type_map

    try:
        dir_mtime = round(os.path.getmtime(v_dir), 3)
    except OSError:
        dir_mtime = 0.0

    cache_key = (v_dir, dir_mtime)
    if cache_key in _AVAILABLE_TYPES_CACHE:
        return dict(_AVAILABLE_TYPES_CACHE[cache_key])

    import tempfile

    temp_dir = tempfile.gettempdir()
    is_shared_tmp = os.path.normpath(temp_dir) in ("/tmp", "/var/tmp", "/usr/tmp")
    if not is_shared_tmp:
        try:
            is_shared_tmp = bool(os.stat(temp_dir).st_mode & 0o1000)
        except OSError:
            is_shared_tmp = True
    uid_suffix = (
        f"_{os.getuid()}" if (is_shared_tmp and hasattr(os, "getuid")) else ""
    )
    disk_cache_path = os.path.join(
        temp_dir, f"gads_assistant_types_{version_clean}{uid_suffix}.json"
    )
    if os.path.isfile(disk_cache_path) and not os.path.islink(disk_cache_path):
        try:
            with open(disk_cache_path, "r", encoding="utf-8") as cf:
                cached_payload = json.load(cf)
            if (
                isinstance(cached_payload, dict)
                and cached_payload.get("v_dir") == v_dir
                and cached_payload.get("mtime") == dir_mtime
                and isinstance(cached_payload.get("types"), dict)
                and cached_payload["types"]
            ):
                sample_file = next(iter(cached_payload["types"].values()))
                if os.path.isfile(sample_file):
                    _AVAILABLE_TYPES_CACHE[cache_key] = cached_payload["types"]
                    return dict(cached_payload["types"])
        except Exception:
            pass

    for py_file in glob.glob(os.path.join(v_dir, "**/types/*.py"), recursive=True):
        if py_file.endswith("__init__.py"):
            continue
        try:
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()
                for cls in _CLASS_DEF_RE.findall(content):
                    if cls not in type_map:
                        type_map[cls] = py_file
        except Exception:
            continue

    if type_map:
        _AVAILABLE_TYPES_CACHE[cache_key] = type_map
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(disk_cache_path, flags, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as cf:
                json.dump({"v_dir": v_dir, "mtime": dir_mtime, "types": type_map}, cf)
        except Exception:
            pass

    return dict(type_map)


def _match_single_name(
    target: str, candidate_names: Iterable[str]
) -> Tuple[Optional[str], List[str]]:
    """Matches a single class/enum identifier against candidate_names."""
    names = list(candidate_names)
    if not names:
        return None, []

    # 1. Exact match
    if target in names:
        return target, []

    # 2. Case-insensitive match
    lower_map = {k.lower(): k for k in names}
    if target.lower() in lower_map:
        return lower_map[target.lower()], []

    # 3. Normalized match: strip underscores, hyphens, spaces
    norm_input = _NON_ALNUM_RE.sub("", target.lower())
    norm_map = {_NON_ALNUM_RE.sub("", k.lower()): k for k in names}
    if norm_input in norm_map:
        return norm_map[norm_input], []

    # 4. Try matching with or without Enum suffix
    if norm_input.endswith("enum"):
        stripped_enum = norm_input[:-4]
        if stripped_enum in norm_map:
            return norm_map[stripped_enum], []
    else:
        if norm_input + "enum" in norm_map:
            return norm_map[norm_input + "enum"], []

    # 5. Fuzzy matching suggestions
    close_matches = difflib.get_close_matches(target, names, n=5, cutoff=0.5)
    if not close_matches:
        norm_close = difflib.get_close_matches(
            norm_input, list(norm_map.keys()), n=5, cutoff=0.4
        )
        close_matches = [norm_map[k] for k in norm_close if k in norm_map]

    return None, close_matches


def resolve_type_name(
    object_name: str, available_types: Dict[str, str]
) -> Tuple[Optional[str], List[str]]:
    """Resolves an object name (including nested Parent.Child names) against available_types."""
    if not available_types:
        return object_name, []

    if object_name in available_types:
        return object_name, []

    if "." not in object_name:
        return _match_single_name(object_name, available_types.keys())

    parts = [p.strip() for p in object_name.split(".") if p.strip()]
    if not parts:
        return None, []

    # Try resolving as Nested Class path: RootClass.NestedClass[...]
    root_resolved, _ = _match_single_name(parts[0], available_types.keys())
    if root_resolved is not None:
        py_file = available_types.get(root_resolved)
        if py_file and os.path.isfile(py_file):
            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read())
                cur_cls: Optional[ast.ClassDef] = next(
                    (
                        node
                        for node in tree.body
                        if isinstance(node, ast.ClassDef) and node.name == root_resolved
                    ),
                    None,
                )
                if cur_cls is not None:
                    resolved_chain = [root_resolved]
                    for sub_part in parts[1:]:
                        child_map = {
                            node.name: node
                            for node in cur_cls.body
                            if isinstance(node, ast.ClassDef)
                        }
                        matched_child, child_suggestions = _match_single_name(
                            sub_part, child_map.keys()
                        )
                        if matched_child is None:
                            prefix = ".".join(resolved_chain)
                            return (
                                None,
                                [f"{prefix}.{s}" for s in child_suggestions],
                            )
                        resolved_chain.append(matched_child)
                        cur_cls = child_map[matched_child]
                    return ".".join(resolved_chain), []
            except Exception:
                pass
        else:
            # Mock environment where py_file does not exist on disk
            return ".".join([root_resolved, *parts[1:]]), []

    # Fallback: package-qualified path (e.g. google.ads.googleads.v26.resources.Campaign)
    return _match_single_name(parts[-1], available_types.keys())


def _get_call_func_name(call_node: ast.Call) -> str:
    func = call_node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _extract_proto_call_info(call_node: ast.Call) -> Tuple[Optional[str], Optional[str]]:
    """Extracts (label, fallback_type_str) from proto.Field / RepeatedField / MapField calls."""
    fn_name = _get_call_func_name(call_node)
    if fn_name == "RepeatedField":
        label = "REPEATED"
    elif fn_name == "MapField":
        label = "MAP"
    elif fn_name == "Field":
        label = "OPTIONAL"
    else:
        return None, None

    type_str: Optional[str] = None
    for kw in call_node.keywords:
        if kw.arg in ("message", "enum"):
            type_str = ast.unparse(kw.value).strip("'\"")
            break
    if type_str is None and call_node.args:
        if fn_name == "MapField" and len(call_node.args) >= 2:
            k_t = ast.unparse(call_node.args[0])
            v_t = ast.unparse(call_node.args[1])
            type_str = f"map<{k_t}, {v_t}>"
        else:
            raw_arg = ast.unparse(call_node.args[0]).strip("'\"")
            type_str = raw_arg[6:] if raw_arg.startswith("proto.") else raw_arg
    return label, type_str


def _extract_class_members_ast(
    target_cls: ast.ClassDef,
) -> Tuple[List[Tuple[str, str, str]], List[Tuple[str, str]]]:
    """Extracts direct message fields and enum values from an AST ClassDef without flattening nested classes."""
    fields: List[Tuple[str, str, str]] = []
    enum_values: List[Tuple[str, str]] = []

    for stmt in target_cls.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            f_name = stmt.target.id
            if f_name.startswith("_"):
                continue
            f_type = ast.unparse(stmt.annotation)
            label = "OPTIONAL"
            if isinstance(stmt.value, ast.Call):
                call_label, call_type = _extract_proto_call_info(stmt.value)
                if call_label:
                    label = call_label
                    if not f_type and call_type:
                        f_type = call_type
            fields.append((f_name, label, f_type))
        elif isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            var_name = stmt.targets[0].id
            if isinstance(stmt.value, ast.Call):
                call_label, call_type = _extract_proto_call_info(stmt.value)
                if call_label:
                    fields.append((var_name, call_label, call_type or "UNKNOWN"))
                    continue
            is_int_const = isinstance(stmt.value, ast.Constant) and isinstance(
                stmt.value.value, int
            ) and not isinstance(stmt.value.value, bool)
            is_neg_int = (
                isinstance(stmt.value, ast.UnaryOp)
                and isinstance(stmt.value.op, ast.USub)
                and isinstance(stmt.value.operand, ast.Constant)
                and isinstance(stmt.value.operand.value, int)
            )
            if re.match(r"^[A-Z][A-Z0-9_]*$", var_name) and (is_int_const or is_neg_int):
                enum_values.append((var_name, ast.unparse(stmt.value)))

    return fields, enum_values


def _inspect_from_source_regex(source: str, class_name: str) -> bool:
    """Regex fallback inspector used only if ast.parse raises SyntaxError."""
    target_leaf = class_name.split(".")[-1]
    in_target_class = False
    class_indent = -1
    fields: List[Tuple[str, str, str]] = []
    enum_values: List[Tuple[str, str]] = []

    for line in source.splitlines():
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())

        if stripped.startswith("class "):
            class_def = stripped[6:].strip()
            c_name = class_def.split("(")[0].split(":")[0].strip()
            if c_name == target_leaf:
                in_target_class = True
                class_indent = indent
                continue
            elif in_target_class and indent <= class_indent:
                break

        if in_target_class:
            m = re.match(
                r"^\s*([a-zA-Z0-9_]+)\s*:\s*([^=\n]+)\s*=\s*proto\.(Field|RepeatedField|MapField)\(",
                line,
            )
            if m:
                f_name = m.group(1)
                f_type = m.group(2).strip()
                f_kind = m.group(3)
                label = (
                    "REPEATED"
                    if f_kind == "RepeatedField"
                    else ("MAP" if f_kind == "MapField" else "OPTIONAL")
                )
                fields.append((f_name, label, f_type))
            elif "=" in stripped and not stripped.startswith("#"):
                m_enum = re.match(r"^\s*([A-Z][A-Z0-9_]*)\s*=\s*(-?\d+)\s*$", line)
                if m_enum:
                    enum_values.append((m_enum.group(1), m_enum.group(2)))

    if enum_values and not fields:
        print(f"=== Enum: {class_name} ===")
        for name, num in enum_values:
            print(f"  - {name} = {num}")
        return True
    if fields:
        print(f"=== Message: {class_name} ===")
        for f_name, label_str, type_name in fields:
            print(f"  - {f_name:<35} [{label_str:<8}] : {type_name}")
        return True
    return False


def inspect_from_source(py_file: str, class_name: str) -> bool:
    """Parses protobuf message fields or enum values from Python source via AST."""
    try:
        with open(py_file, "r", encoding="utf-8") as f:
            source = f.read()
    except Exception as e:
        print(f"ERROR: Failed to read source file '{py_file}': {e}", file=sys.stderr)
        return False

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _inspect_from_source_regex(source, class_name)

    parts = [p.strip() for p in class_name.split(".") if p.strip()]
    if not parts:
        return False

    cur_body: List[ast.stmt] = tree.body
    target_cls: Optional[ast.ClassDef] = None
    for part in parts:
        found_cls: Optional[ast.ClassDef] = None
        for node in cur_body:
            if isinstance(node, ast.ClassDef) and node.name == part:
                found_cls = node
                break
        if found_cls is None:
            return False
        target_cls = found_cls
        cur_body = found_cls.body

    if target_cls is None:
        return False

    fields, enum_values = _extract_class_members_ast(target_cls)

    # Handle Google Ads Enum wrapper classes (e.g. CampaignStatusEnum containing class CampaignStatus(proto.Enum))
    if not fields and not enum_values:
        for child in target_cls.body:
            if isinstance(child, ast.ClassDef):
                _, child_enums = _extract_class_members_ast(child)
                if child_enums:
                    print(f"=== Enum: {class_name}.{child.name} ===")
                    for name, num in child_enums:
                        print(f"  - {name} = {num}")
                    return True

    if enum_values and not fields:
        print(f"=== Enum: {class_name} ===")
        for name, num in enum_values:
            print(f"  - {name} = {num}")
        return True
    if fields:
        print(f"=== Message: {class_name} ===")
        for f_name, label_str, type_name in fields:
            print(f"  - {f_name:<35} [{label_str:<8}] : {type_name}")
        return True
    return False


def _extract_descriptor(obj_type: Any) -> Any:
    descriptor = getattr(obj_type, "DESCRIPTOR", None)
    if descriptor is not None:
        return descriptor
    pb_attr = getattr(obj_type, "_pb", None)
    if pb_attr is not None:
        descriptor = getattr(pb_attr, "DESCRIPTOR", None)
        if descriptor is not None:
            return descriptor
    pb_fn = getattr(type(obj_type), "pb", None)
    if callable(pb_fn):
        try:
            return getattr(pb_fn(obj_type), "DESCRIPTOR", None)
        except Exception:
            pass
    return None


def _resolve_nested_descriptor(client: Any, target_name: str) -> Any:
    try:
        obj_type = client.get_type(target_name)
        desc = _extract_descriptor(obj_type)
        if desc is not None:
            return desc
    except Exception:
        pass

    if "." in target_name:
        parts = target_name.split(".")
        try:
            root_obj = client.get_type(parts[0])
            cur_desc = _extract_descriptor(root_obj)
            for part in parts[1:]:
                if cur_desc is None:
                    return None
                nested_map = {
                    nt.name: nt for nt in (getattr(cur_desc, "nested_types", None) or [])
                }
                if part in nested_map:
                    cur_desc = nested_map[part]
                    continue
                enum_map = {
                    et.name: et for et in (getattr(cur_desc, "enum_types", None) or [])
                }
                if part in enum_map:
                    cur_desc = enum_map[part]
                    continue
                return None
            return cur_desc
        except Exception:
            return None
    return None


def inspect_protobuf(
    object_name: str, api_version: str, client: Optional[GoogleAdsClient] = None
) -> None:
    """Inspects any Google Ads API Protobuf resource, message or enum."""
    api_version = _normalize_api_version(api_version)
    check_version_parity()
    available_types = get_available_types(api_version)
    resolved_name, suggestions = resolve_type_name(object_name, available_types)

    if not resolved_name:
        print(
            f"ERROR: Protobuf object '{object_name}' not found under version '{api_version}'.",
            file=sys.stderr,
        )
        if suggestions:
            print("\nDid you mean one of these?", file=sys.stderr)
            for s in suggestions:
                print(f"  - {s}", file=sys.stderr)
        sys.exit(1)

    if resolved_name != object_name:
        print(f"Note: Resolved '{object_name}' -> '{resolved_name}'")

    target_name = resolved_name

    # First attempt: Using GoogleAdsClient if available and loaded
    if client is None and GoogleAdsClient is not None:
        try:
            cfg_path = _get_config_path()
            client = GoogleAdsClient.load_from_storage(path=cfg_path, version=api_version)
        except Exception:
            client = None

    if client is not None:
        try:
            descriptor = _resolve_nested_descriptor(client, target_name)
            if descriptor is not None:
                if hasattr(descriptor, "values"):
                    print(f"=== Enum: {target_name} ===")
                    for value in descriptor.values:
                        print(f"  - {value.name} = {value.number}")
                    return

                fields_seq = list(getattr(descriptor, "fields", None) or [])
                enum_types_seq = list(getattr(descriptor, "enum_types", None) or [])
                if not fields_seq and enum_types_seq:
                    enum_desc = enum_types_seq[0]
                    parent_label = getattr(descriptor, "name", None) or target_name
                    print(f"=== Enum: {parent_label}.{enum_desc.name} ===")
                    for value in enum_desc.values:
                        print(f"  - {value.name} = {value.number}")
                    return

                print(f"=== Message: {target_name} ===")
                for field in fields_seq:
                    is_repeated = (
                        bool(getattr(field, "is_repeated", False))
                        or getattr(field, "label", None) == 3
                    )
                    label_str = "REPEATED" if is_repeated else "OPTIONAL"
                    msg_type = getattr(field, "message_type", None)
                    enum_type = getattr(field, "enum_type", None)
                    if msg_type and isinstance(getattr(msg_type, "name", None), str):
                        type_name = msg_type.name
                    elif enum_type and isinstance(getattr(enum_type, "name", None), str):
                        type_name = enum_type.name
                    elif isinstance(field.type, int) and field.type in _PROTO_FIELD_TYPES:
                        type_name = _PROTO_FIELD_TYPES[field.type]
                    else:
                        type_name = str(field.type)
                    print(f"  - {field.name:<35} [{label_str:<8}] : {type_name}")
                return
        except Exception:
            pass

    # Fallback attempt: Parse directly from source file in client_libs
    py_file = available_types.get(target_name) or available_types.get(
        target_name.split(".", 1)[0]
    )
    if py_file and inspect_from_source(py_file, target_name):
        return

    print(
        f"ERROR: Could not inspect descriptor or definition for '{target_name}'.",
        file=sys.stderr,
    )
    sys.exit(1)


def main() -> None:
    """Parses command line arguments and runs inspection."""
    parser = argparse.ArgumentParser(
        description="Inspects a Google Ads API Protobuf type structure."
    )
    parser.add_argument(
        "--object_name",
        "--name",
        "-n",
        dest="object_name",
        required=True,
        help="Protobuf type name (e.g. Campaign, campaign, AdGroup).",
    )
    parser.add_argument(
        "--api_version",
        "-v",
        required=False,
        default=_get_default_api_version(),
        help="API version (e.g. v26). Defaults to configured api_version or v26.",
    )
    args = parser.parse_args()

    inspect_protobuf(args.object_name, args.api_version)


if __name__ == "__main__":
    main()

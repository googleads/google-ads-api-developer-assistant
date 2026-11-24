#!/usr/bin/env python3
"""Lightweight, fail-closed PreToolUse/SessionStart hook entrypoint (<50ms fast path).

Handles benign shell commands, file-write tool calls, and MCP mutation guards
with minimal stdlib imports, lazily loading config_init.py only when workspace
config sync, command rewriting, or receipt verification is required.
"""

from __future__ import annotations

import json
import os
import re
import sys

TYPE_CHECKING = False
if TYPE_CHECKING:
    from typing import Any, Optional

_FILE_READ_TOOLS = frozenset(
    {
        "read_file",
        "view_file",
        "Read",
    }
)
_FILE_WRITE_TOOLS = frozenset(
    {
        "write_file",
        "edit_file",
        "write_to_file",
        "replace_file_content",
        "multi_replace_file_content",
        "Write",
        "Edit",
        "MultiEdit",
    }
)
_PROTECTED_CREDENTIAL_FILES = frozenset(
    {
        "google-ads.yaml",
        "google_ads_php.ini",
        "google_ads_config.rb",
        "ads.properties",
        ".a2a_token",
    }
)
_PROTECTED_DENY_FILES = frozenset({"last_dry_run.json", "mutation_audit.jsonl"})
_PROTECTED_ASK_FILES = frozenset(
    {
        "assistant_config",
        "financial_limits",
        "google-ads.yaml",
        "hooks.json",
        "config_init.py",
        "hook_guard.py",
        "sitecustomize.py",
        "AGENTS.md",
        "run_mutation.py",
        "set_financial_limits.py",
        "create_account.py",
        "create_campaign.py",
        "create_ad_group.py",
        "create_ad.py",
        "create_pmax_webpage_filter.py",
        "server.py",
        "mcp_config.json",
        ".mcp.json",
        "sidecar.json",
        "plugin.json",
    }
)
_CLAUDE_DECISIONS = {
    "allow": "allow",
    "deny": "deny",
    "force_ask": "ask",
    "ask": "ask",
}
_ADS_MCP_MUTATION_TOOLS = frozenset(
    {
        "prepare_mutation",
        "execute_mutation",
        "create_account",
        "create_campaign",
        "create_ad_group",
        "create_ad",
    }
)
_ADS_MCP_SERVER_TOKENS = ("google-ads-api-assistant", "google_ads_api_assistant")
_DELETION_TEXT_RE = re.compile(
    r"\b(?:remove|remove_all|removed|delete|destroy|drop)\b",
    re.IGNORECASE,
)
# Any shell command containing none of these tokens cannot write protected files,
# spoof env vars, invoke obfuscated/piped/quoted commands, run Ads scripts, or need rewrites.
_SHELL_INSPECT_RE = re.compile(
    r"(?:python|pytest|googleads|GoogleAdsClient|google-ads|GOOGLE_ADS_|skills/|"
    r"\.(?:py|sh|bash|php|rb|js|mjs|cjs|ts)\b|"
    r"run_mutation|config_init|hook_guard|sitecustomize|AGENTS\.md|set_financial_limits|"
    r"create_(?:account|campaign|ad_group|ad|pmax_webpage_filter)|"
    r"assistant_config|financial_limits|last_dry_run|mutation_audit|hooks\.json|"
    r"mcp_config|\.mcp\.json|sidecar\.json|plugin\.json|server\.py|\.a2a_token|"
    r"\b(?:curl|wget|http|httpie|xh|sed|perl|awk|gawk|mawk|nawk|patch|"
    r"tee|cp|mv|install|ln|rm|truncate|dd|rsync|eval|exec|env|xargs|source|"
    r"php|ruby|node|nodejs|deno|bun|bash|sh|zsh|dash|ksh)\b|"
    r":mutate|saved/|>{1,2}|\./|''|\"\"|\$|`|\||\\)",
    re.IGNORECASE,
)
_ENABLED_LINE_RE = re.compile(
    r"(?mi)^\s*(?:enabled|plugin_enabled)\s*=\s*['\"]?(true|false)['\"]?\s*(?:#.*)?$"
)


def _strict_bool(val: Any) -> bool:
    """Evaluates booleans strictly so strings like 'false' or '0' are False."""
    if val is True:
        return True
    if isinstance(val, str):
        return val.strip().lower() == "true"
    return False


def _fast_is_plugin_enabled() -> bool:
    """Fast stdlib-only enabled check mirroring config_init.is_plugin_enabled."""
    env_override = os.environ.get("GOOGLE_ADS_ASSISTANT_ENABLED", "").strip().lower()
    if env_override in ("true", "1", "yes", "on", "enabled"):
        return True
    if env_override in ("false", "0", "no", "off", "disabled"):
        return False

    this_dir = os.path.dirname(os.path.abspath(__file__))
    candidates: list[str] = []
    for env_key, suffix in (
        ("GOOGLE_ADS_ASSISTANT_CONFIG_DIR", "assistant_config"),
        ("PLUGIN_ROOT", os.path.join("config", "assistant_config")),
        ("CLAUDE_PLUGIN_ROOT", os.path.join("config", "assistant_config")),
        ("GOOGLE_ADS_ASSISTANT_DIR", os.path.join("config", "assistant_config")),
    ):
        val = os.environ.get(env_key, "").strip()
        if val:
            candidates.append(os.path.join(os.path.abspath(val), suffix))
    candidates.extend(
        [
            os.path.join(this_dir, "assistant_config"),
            os.path.abspath(os.path.join("config", "assistant_config")),
            os.path.expanduser(
                "~/.claude/plugins/google-ads-assistant-local/plugins/"
                "google-ads-api-developer-assistant/config/assistant_config"
            ),
            os.path.expanduser(
                "~/.gemini/config/plugins/google-ads-api-developer-assistant/"
                "config/assistant_config"
            ),
        ]
    )
    for cfg in candidates:
        if os.path.isfile(cfg):
            try:
                with open(cfg, "r", encoding="utf-8") as f:
                    m = _ENABLED_LINE_RE.search(f.read())
                if m:
                    return m.group(1).lower() == "true"
            except OSError:
                continue
    return True


def _emit_pretooluse(decision: str, reason: Optional[str], is_claude: bool) -> int:
    """Prints a PreToolUse decision in the active CLI's exact contract.

    Claude Code uses the canonical exit-0 structured JSON contract
    (`hookSpecificOutput.permissionDecision` allow|deny|ask); the shell wrapper
    in hooks/hooks.json still uses exit 2 + stderr when Python or hook_guard.py
    is missing.
    """
    if is_claude:
        c_dec = _CLAUDE_DECISIONS.get(decision, "deny")
        if c_dec == "allow":
            print("{}")
            return 0
        payload = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": c_dec,
                "permissionDecisionReason": reason or "Blocked by the HITL mutation guard.",
            }
        }
        print(json.dumps(payload))
        return 0
    out: dict[str, Any] = {"decision": decision}
    if reason and decision != "allow":
        out["reason"] = reason
    print(json.dumps(out))
    return 0


def _load_config_init() -> Any:
    """Lazily imports sibling config_init.py only when heavy checks are needed."""
    this_dir = os.path.dirname(os.path.abspath(__file__))
    if this_dir not in sys.path:
        sys.path.insert(0, this_dir)
    import config_init  # type: ignore[import-not-found]

    return config_init


def _extract_workspace_cwd(parsed: Optional[dict[str, Any]]) -> Optional[str]:
    """Extracts the user's active workspace directory from an agy or Claude hook payload."""
    if not isinstance(parsed, dict):
        return None
    tool_call = parsed.get("toolCall")
    if isinstance(tool_call, dict) and isinstance(tool_call.get("args"), dict):
        tc_cwd = tool_call["args"].get("Cwd") or tool_call["args"].get("cwd")
        if isinstance(tc_cwd, str) and tc_cwd.strip():
            return os.path.abspath(os.path.expanduser(tc_cwd.strip()))
    tool_input = parsed.get("tool_input")
    if isinstance(tool_input, dict):
        ti_cwd = tool_input.get("cwd")
        if isinstance(ti_cwd, str) and ti_cwd.strip():
            return os.path.abspath(os.path.expanduser(ti_cwd.strip()))
    for key in (
        "cwd",
        "workingDirectory",
        "working_directory",
        "workspaceRoot",
        "workspace_root",
        "projectDir",
        "project_dir",
    ):
        val = parsed.get(key)
        if isinstance(val, str) and val.strip():
            return os.path.abspath(os.path.expanduser(val.strip()))
    for list_key in ("workspacePaths", "workspace_paths", "workspaces"):
        ws_list = parsed.get(list_key)
        if isinstance(ws_list, list) and ws_list:
            first = ws_list[0]
            if isinstance(first, str) and first.strip():
                return os.path.abspath(os.path.expanduser(first.strip()))
            if isinstance(first, dict):
                cand = first.get("path") or first.get("uri")
                if isinstance(cand, str) and cand.strip():
                    if cand.startswith("file://"):
                        cand = cand[len("file://") :]
                    return os.path.abspath(os.path.expanduser(cand.strip()))
    return None


def _resolve_path_for_guard(path: str, workspace_cwd: Optional[str] = None) -> str:
    """Resolves a relative or absolute path against workspace_cwd, following symlinks."""
    expanded = os.path.expanduser(path.strip().rstrip("/\\"))
    if workspace_cwd and not os.path.isabs(expanded):
        expanded = os.path.join(workspace_cwd, expanded)
    return os.path.realpath(expanded)


def _candidate_basenames(path: str, workspace_cwd: Optional[str] = None) -> set[str]:
    """Returns raw, workspace-resolved realpath, and CWD-resolved realpath basenames."""
    clean = path.strip().rstrip("/\\")
    raw_base = os.path.basename(clean)
    ws_real_base = os.path.basename(_resolve_path_for_guard(clean, workspace_cwd))
    cwd_real_base = os.path.basename(os.path.realpath(os.path.expanduser(clean)))
    return {b for b in (raw_base, ws_real_base, cwd_real_base) if b}


def _is_path_in_saved_code(
    script_path: str, workspace_cwd: Optional[str] = None
) -> bool:
    """True when script_path resolves to a .py file under a saved/code/ directory."""
    real_path = _resolve_path_for_guard(script_path, workspace_cwd)
    if not real_path.endswith(".py"):
        return False
    parts = real_path.replace("\\", "/").split("/")
    return any(
        parts[i] == "saved" and parts[i + 1] == "code"
        for i in range(len(parts) - 2)
    )


def _extract_mcp_call(
    tool_name: str, args: dict[str, Any]
) -> Optional[tuple[str, dict[str, Any]]]:
    """Extracts (ads_mcp_tool_name, tool_args) if this call targets the Ads MCP server."""
    if tool_name == "call_mcp_tool":
        server_name = str(
            args.get("ServerName") or args.get("server_name") or ""
        ).strip().lower()
        if not any(tok in server_name for tok in _ADS_MCP_SERVER_TOKENS):
            return None
        mcp_tool = str(
            args.get("ToolName") or args.get("tool_name") or ""
        ).strip()
        raw_args = args.get("Arguments")
        if raw_args is None:
            raw_args = args.get("arguments")
        mcp_args = raw_args if isinstance(raw_args, dict) else {}
        return mcp_tool, mcp_args

    if tool_name.startswith("mcp__"):
        parts = tool_name.split("__", 2)
        if len(parts) == 3 and any(
            tok in parts[1].lower() for tok in _ADS_MCP_SERVER_TOKENS
        ):
            return parts[2], args
        return None

    if tool_name.startswith("mcp_"):
        lowered = tool_name.lower()
        for tok in _ADS_MCP_SERVER_TOKENS:
            marker = f"_{tok}_"
            idx = lowered.find(marker)
            if idx >= 3:
                extracted = tool_name[idx + len(marker) :]
                if extracted:
                    return extracted, args
    return None


def _evaluate_mcp_guard(
    mcp_tool: str,
    mcp_args: dict[str, Any],
    input_data: dict[str, Any],
) -> tuple[str, Optional[str]]:
    """Evaluates PreToolUse HITL guardrails for Google Ads MCP tools."""
    if mcp_tool not in _ADS_MCP_MUTATION_TOOLS:
        return "allow", None

    ws_cwd = _extract_workspace_cwd(input_data)

    if mcp_tool == "prepare_mutation":
        sp = mcp_args.get("script_path")
        if sp is not None and str(sp).strip():
            if not isinstance(sp, str) or not _is_path_in_saved_code(sp, ws_cwd):
                return (
                    "deny",
                    "BLOCKED BY HITL MUTATION GUARD: MCP prepare_mutation 'script_path' "
                    "must resolve to a .py file inside saved/code/.",
                )
        combined = " ".join(
            str(mcp_args.get(k, "") or "")
            for k in ("operation_summary", "operation", "after_state")
        )
        if _DELETION_TEXT_RE.search(combined):
            return (
                "deny",
                "BLOCKED BY DELETION PROHIBITION (HITL GUARD): Deletion/remove operations "
                "are strictly prohibited via MCP. Update status to PAUSED instead.",
            )
        return "allow", None

    if mcp_tool == "execute_mutation":
        sp = mcp_args.get("script_path")
        if sp is not None and str(sp).strip():
            if not isinstance(sp, str) or not _is_path_in_saved_code(sp, ws_cwd):
                return (
                    "deny",
                    "BLOCKED BY HITL MUTATION GUARD: MCP execute_mutation 'script_path' "
                    "must resolve to a .py file inside saved/code/.",
                )
        ci = _load_config_init()
        if not ci.is_execute_mutates_enabled():
            return (
                "deny",
                "BLOCKED BY HITL MUTATION GUARD: Live MCP mutations are disabled "
                "(execute_mutates = false in config/assistant_config).",
            )
        effective_ws = ws_cwd or ci._extract_workspace_cwd(input_data)
        resolved_sp = (
            ci._resolve_candidate_script_path(str(sp), effective_ws)
            if isinstance(sp, str) and sp.strip()
            else None
        )
        allow_receipt_only = not _strict_bool(mcp_args.get("run_script", False))
        ok, msg, _ = ci._verify_dry_run_receipt_for_hook(
            script_path=resolved_sp,
            hook_context=input_data,
            workspace_cwd=effective_ws,
            allow_receipt_only=allow_receipt_only,
        )
        return ("force_ask", msg) if ok else ("deny", msg)

    # create_account / create_campaign / create_ad_group / create_ad
    raw_status = str(mcp_args.get("status", "") or "").strip().upper()
    if raw_status == "REMOVED":
        return (
            "deny",
            "BLOCKED BY DELETION PROHIBITION (HITL GUARD): Setting status to 'REMOVED' "
            "via MCP is prohibited; use 'PAUSED' instead.",
        )

    is_live = _strict_bool(mcp_args.get("execute", False)) or (
        "validate_only" in mcp_args
        and mcp_args["validate_only"] is not None
        and not _strict_bool(mcp_args.get("validate_only"))
    )
    if not is_live:
        return "allow", None

    ci = _load_config_init()
    if not ci.is_execute_mutates_enabled():
        return (
            "deny",
            "BLOCKED BY HITL MUTATION GUARD: Live MCP mutations are disabled "
            "(execute_mutates = false in config/assistant_config).",
        )

    # Only CampaignBudgetService (create_campaign without existing budget_resource_name) is Tier 1;
    # AdGroupService (create_ad_group) is Tier 2 and governed by config/financial_limits + force_ask.
    is_tier1_mcp = (
        mcp_tool == "create_campaign"
        and not str(mcp_args.get("budget_resource_name") or "").strip()
    )
    if is_tier1_mcp:
        rm_mod = ci._load_run_mutation_for_hook()
        t1_fn = getattr(rm_mod, "is_tier1_financial_mutates_enabled", None) if rm_mod else None
        if not callable(t1_fn) or not t1_fn():
            return (
                "deny",
                f"BLOCKED BY HITL MUTATION GUARD (TIER 1 FINANCIAL POSTURE): MCP {mcp_tool} "
                "with financial budget/bid fields requires allow_tier1_financial_mutates = true "
                "in config/assistant_config.",
            )

    cid = str(
        mcp_args.get("customer_id") or mcp_args.get("manager_customer_id") or "unknown"
    )
    return (
        "force_ask",
        f"⚠️ LIVE GOOGLE ADS MCP MUTATION ({mcp_tool} on customer {cid}): "
        "Confirm executing this live Google Ads API write?",
    )


def handle_fast_hook(
    *,
    explicit_event: Optional[str] = None,
    explicit_cli: Optional[str] = None,
    raw_stdin: Optional[str] = None,
) -> int:
    """Fast-path hook dispatcher for agy CLI and Claude Code CLI."""
    if raw_stdin is None:
        raw_stdin = "" if sys.stdin.isatty() else sys.stdin.read()

    event_hint = (explicit_event or "").strip()
    is_claude_hint = (
        (explicit_cli or "").strip().lower() == "claude"
        or "tool_input" in raw_stdin
        or "hook_event_name" in raw_stdin
        or bool(os.environ.get("CLAUDECODE"))
        or bool(os.environ.get("CLAUDE_CODE"))
    )
    is_pretool_hint = (
        event_hint == "PreToolUse"
        or "toolCall" in raw_stdin
        or "tool_input" in raw_stdin
        or '"PreToolUse"' in raw_stdin
    )

    if not raw_stdin.strip():
        if is_pretool_hint:
            return _emit_pretooluse(
                "deny",
                "BLOCKED BY HITL MUTATION GUARD: Empty PreToolUse hook payload.",
                is_claude_hint,
            )
        ci = _load_config_init()
        return ci.handle_hook(
            explicit_event=event_hint or None,
            explicit_cli=explicit_cli,
            raw_stdin=raw_stdin,
        )

    try:
        parsed = json.loads(raw_stdin)
    except Exception:
        if is_pretool_hint:
            return _emit_pretooluse(
                "deny",
                "BLOCKED BY HITL MUTATION GUARD: Malformed hook JSON payload.",
                is_claude_hint,
            )
        print("{}")
        return 0

    if not isinstance(parsed, dict):
        if is_pretool_hint:
            return _emit_pretooluse(
                "deny",
                "BLOCKED BY HITL MUTATION GUARD: Hook payload must be a JSON object.",
                is_claude_hint,
            )
        print("{}")
        return 0

    hook_event = (
        event_hint
        or str(
            parsed.get("hook_event_name")
            or parsed.get("hookEventName")
            or parsed.get("event")
            or ""
        ).strip()
    )
    is_claude = (
        (explicit_cli or "").strip().lower() == "claude"
        or "tool_input" in parsed
        or "hook_event_name" in parsed
        or bool(os.environ.get("CLAUDECODE"))
        or bool(os.environ.get("CLAUDE_CODE"))
    )
    is_tool_event = (
        "toolCall" in parsed
        or "tool_input" in parsed
        or hook_event == "PreToolUse"
    )

    if not _fast_is_plugin_enabled():
        if is_tool_event and not is_claude and hook_event != "PostToolUseFailure":
            print('{"decision": "allow"}')
        else:
            print("{}")
        return 0

    if hook_event in ("SessionStart", "PreInvocation", "UserPromptSubmit", "PostToolUseFailure") or not is_tool_event:
        ci = _load_config_init()
        return ci.handle_hook(
            explicit_event=hook_event or None,
            explicit_cli="claude" if is_claude else "agy",
            raw_stdin=raw_stdin,
        )

    # PreToolUse event: handle file writes, MCP tools, and fast-path benign shell calls
    tool_call = parsed.get("toolCall")
    tool_name = str(
        (tool_call.get("name") if isinstance(tool_call, dict) else None)
        or parsed.get("tool_name")
        or ""
    )
    if isinstance(tool_call, dict) and isinstance(tool_call.get("args"), dict):
        args = tool_call["args"]
    elif isinstance(parsed.get("tool_input"), dict):
        args = parsed["tool_input"]
    else:
        args = {}

    # 1. MCP tool interception
    mcp_call = _extract_mcp_call(tool_name, args)
    if mcp_call is not None:
        mcp_tool, mcp_args = mcp_call
        decision, reason = _evaluate_mcp_guard(mcp_tool, mcp_args, parsed)
        return _emit_pretooluse(decision, reason, is_claude)

    # 2. File-read / file-write tool interception (agy + legacy + Claude Read/Write/Edit)
    ws_cwd = _extract_workspace_cwd(parsed)
    target_file = (
        args.get("Path")
        or args.get("TargetFile")
        or args.get("AbsolutePath")
        or args.get("file_path")
        or args.get("path")
        or ""
    )
    cmd = args.get("CommandLine") or args.get("command") or ""
    if not isinstance(cmd, str):
        cmd = ""

    if tool_name in _FILE_READ_TOOLS:
        if isinstance(target_file, str) and target_file.strip():
            bases = _candidate_basenames(target_file, ws_cwd)
            cred_hit = next((b for b in bases if b in _PROTECTED_CREDENTIAL_FILES), None)
            if cred_hit:
                return _emit_pretooluse(
                    "deny",
                    f"BLOCKED BY CREDENTIAL ISOLATION GUARD: Direct file reads of '{cred_hit}' "
                    "are prohibited to prevent leaking OAuth secrets or sidecar tokens into model context.",
                    is_claude,
                )
        return _emit_pretooluse("allow", None, is_claude)

    if (tool_name in _FILE_WRITE_TOOLS or (target_file and not cmd)) and isinstance(
        target_file, str
    ):
        bases = _candidate_basenames(target_file, ws_cwd)
        deny_hit = next((b for b in bases if b in _PROTECTED_DENY_FILES), None)
        if deny_hit:
            return _emit_pretooluse(
                "deny",
                f"BLOCKED BY HITL MUTATION GUARD: Direct file writes to '{deny_hit}' are prohibited. "
                "Receipts and audit logs may only be written by run_mutation.py.",
                is_claude,
            )
        ask_hit = next((b for b in bases if b in _PROTECTED_ASK_FILES), None)
        if ask_hit:
            return _emit_pretooluse(
                "force_ask",
                f"⚠️ PROTECTED CONFIGURATION EDIT: Confirm modification of '{target_file}'?",
                is_claude,
            )
        return _emit_pretooluse("allow", None, is_claude)

    # 3. Fast-path benign shell commands without loading config_init.py
    if not cmd or not _SHELL_INSPECT_RE.search(cmd):
        return _emit_pretooluse("allow", None, is_claude)

    # 4. Delegate complex shell commands to full config_init guard + rewriter
    ci = _load_config_init()
    return ci.handle_hook(
        explicit_event="PreToolUse",
        explicit_cli="claude" if is_claude else "agy",
        raw_stdin=raw_stdin,
    )


def main(argv: Optional[list[str]] = None) -> None:
    """CLI entrypoint parsing --event and --cli without argparse overhead."""
    args = list(sys.argv[1:] if argv is None else argv)
    explicit_event: Optional[str] = None
    explicit_cli: Optional[str] = None
    i = 0
    while i < len(args):
        tok = args[i]
        if tok == "--event" and i + 1 < len(args):
            explicit_event = args[i + 1]
            i += 2
        elif tok.startswith("--event="):
            explicit_event = tok.split("=", 1)[1]
            i += 1
        elif tok == "--cli" and i + 1 < len(args):
            explicit_cli = args[i + 1]
            i += 2
        elif tok.startswith("--cli="):
            explicit_cli = tok.split("=", 1)[1]
            i += 1
        else:
            i += 1
    try:
        rc = handle_fast_hook(
            explicit_event=explicit_event,
            explicit_cli=explicit_cli,
        )
    except Exception as exc:
        is_claude = (explicit_cli or "").strip().lower() == "claude" or bool(
            os.environ.get("CLAUDECODE") or os.environ.get("CLAUDE_CODE")
        )
        if explicit_event == "PreToolUse":
            rc = _emit_pretooluse(
                "deny",
                f"BLOCKED BY HITL MUTATION GUARD: Internal hook error ({exc}).",
                is_claude,
            )
        else:
            print("{}")
            rc = 0
    if rc:
        sys.exit(rc)


if __name__ == "__main__":
    main()

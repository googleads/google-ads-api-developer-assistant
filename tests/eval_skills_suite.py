#!/usr/bin/env python3
"""Dual-Mode Skill & Prompt Evaluation Harness for the Google Ads API Developer Assistant.

Supports two execution modes:
1. ``--mode offline`` (default, deterministic, zero network/API keys — runs in CI):
   - EV-SCHEMA: Validates YAML frontmatter & structure across all 11 SKILL.md and 13 commands/*.md files.
   - EV-CLI: Extracts every ``python3 ... scripts/<script>.py --flag`` example from skills, commands,
     and rules, verifies the script exists, and asserts every documented CLI flag exists in ``--help``.
   - EV-POLICY: Verifies mandatory safety & behavioral directives across ``rules/google_ads_rules.md``
     and all prompt-only & script-backed skills (Deletion Prohibition, 4-Step HITL, credential isolation,
     GAQL rules, ``explain`` 4-section protocol, ``step-by-step`` phases, ``assistant-tutorial`` rules).
   - EV-ROUTE: Evaluates 22 realistic developer prompts (2 per skill across all 11 skills) using a
     deterministic catalog router built from actual SKILL.md / commands/*.md metadata, plus rubric
     grader self-checks (positive & negative controls).
2. ``--mode live --provider <claude|gemini-cli|gemini-api>`` (optional LLM-in-the-loop evals):
   - Sends each eval prompt with ``rules/google_ads_rules.md`` + routed ``SKILL.md`` context to the
     selected LLM CLI or Gemini REST API (``GEMINI_API_KEY``) and grades responses against the
     deterministic required/forbidden rubric assertions.

Usage:
    python3 tests/eval_skills_suite.py --mode offline
    python3 tests/eval_skills_suite.py --list-cases
    python3 tests/eval_skills_suite.py --mode live --provider gemini-api --skill explain
    python3 tests/eval_skills_suite.py --mode live --provider claude --case-id EV-ROUTE-EXP-01
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

import yaml

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PLUGIN_ROOT = os.path.join(
    REPO_ROOT, "plugins", "google-ads-api-developer-assistant"
)
SKILLS_DIR = os.path.join(PLUGIN_ROOT, "skills")
COMMANDS_DIR = os.path.join(PLUGIN_ROOT, "commands")
RULES_PATH = os.path.join(PLUGIN_ROOT, "rules", "google_ads_rules.md")

EXPECTED_SKILLS: tuple[str, ...] = (
    "assistant-tutorial",
    "execute-mutation",
    "explain",
    "ext-version",
    "get-cids-under-mcc",
    "inspect-object",
    "pmax-listing-filter",
    "step-by-step",
    "sync-client-libs",
    "troubleshoot-conversions",
    "validate-gaql",
)

EXPECTED_COMMANDS: tuple[str, ...] = (
    "assistant-tutorial.md",
    "execute-mutation.md",
    "explain.md",
    "ext-version.md",
    "get-cids-under-mcc.md",
    "get-cids.md",
    "inspect-object.md",
    "pmax-filter.md",
    "pmax-listing-filter.md",
    "step-by-step.md",
    "sync-client-libs.md",
    "troubleshoot-conversions.md",
    "validate-gaql.md",
)

COMMAND_ALIAS_TO_SKILL: dict[str, str] = {
    "assistant-tutorial": "assistant-tutorial",
    "execute-mutation": "execute-mutation",
    "explain": "explain",
    "ext-version": "ext-version",
    "get-cids": "get-cids-under-mcc",
    "get-cids-under-mcc": "get-cids-under-mcc",
    "inspect-object": "inspect-object",
    "pmax-filter": "pmax-listing-filter",
    "pmax-listing-filter": "pmax-listing-filter",
    "step-by-step": "step-by-step",
    "sync-client-libs": "sync-client-libs",
    "troubleshoot-conversions": "troubleshoot-conversions",
    "validate-gaql": "validate-gaql",
}

_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "for",
    "from", "how", "i", "in", "is", "it", "me", "my", "of", "on", "or",
    "please", "show", "that", "the", "this", "to", "use", "using", "what",
    "when", "with", "would", "you", "your",
})


@dataclass
class EvalCase:
    """Single prompt/rubric evaluation case for a skill."""

    case_id: str
    skill: str
    prompt: str
    required_patterns: list[str]
    forbidden_patterns: list[str] = field(default_factory=list)
    reference_response: str = ""
    description: str = ""


@dataclass
class EvalCheckResult:
    """Result of a single offline or live evaluation check."""

    check_id: str
    suite: str
    skill: str
    passed: bool
    duration_ms: float
    details: str
    response_preview: str = ""


def parse_frontmatter(md_text: str) -> tuple[dict[str, Any], str]:
    """Parses leading YAML frontmatter (`--- ... ---`) from a markdown file."""
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", md_text, flags=re.DOTALL)
    if not match:
        return {}, md_text
    raw_yaml, body = match.group(1), match.group(2)
    try:
        parsed = yaml.safe_load(raw_yaml) or {}
    except yaml.YAMLError:
        # Claude Code command frontmatter allows unquoted `[optional_arg]` placeholders
        # in `argument-description:`. Parse simple `key: value` lines deterministically.
        parsed = {}
        for line in raw_yaml.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if ":" not in stripped:
                raise ValueError(f"Malformed frontmatter line: {line!r}")
            k, v = stripped.split(":", 1)
            parsed[k.strip()] = v.strip()
    if not isinstance(parsed, dict):
        raise ValueError("Frontmatter did not deserialize to a mapping.")
    return parsed, body


def validate_skill_entry(s_name: str, info: dict[str, Any]) -> list[str]:
    """Returns schema errors for one skill catalog entry (empty list when valid)."""
    errors: list[str] = []
    fm = info.get("frontmatter") or {}
    if fm.get("name") != s_name:
        errors.append(f"Skill '{s_name}' frontmatter name mismatch: {fm.get('name')!r}")
    if not str(fm.get("description", "")).strip():
        errors.append(f"Skill '{s_name}' missing frontmatter description.")
    if not str(info.get("body", "")).strip():
        errors.append(f"Skill '{s_name}' has empty markdown body.")
    return errors


def load_skill_entry(skill_name: str, skill_md: str) -> dict[str, Any]:
    """Parses one SKILL.md file into a catalog entry (no slash commands attached)."""
    with open(skill_md, "r", encoding="utf-8") as f:
        text = f.read()
    fm, body = parse_frontmatter(text)
    return {"name": skill_name, "path": skill_md, "frontmatter": fm, "body": body, "commands": []}


def build_mutated_skill_fixture(skill_name: str, dest_dir: str) -> str:
    """Writes a copy of a real SKILL.md with its required `description` and body removed.

    The schema validator and the router must both reject this fixture. It is derived
    from the live SKILL.md at run time so it cannot drift from the real file.
    """
    src = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")
    with open(src, "r", encoding="utf-8") as f:
        text = f.read()
    fm, _body = parse_frontmatter(text)
    fm = dict(fm)
    fm.pop("description", None)
    mutated = "---\n" + yaml.safe_dump(fm, sort_keys=False) + "---\n"
    out_dir = os.path.join(dest_dir, skill_name)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "SKILL.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(mutated)
    return out_path


def load_skill_catalog() -> dict[str, dict[str, Any]]:
    """Loads metadata, body, and associated slash commands for all installed skills."""
    catalog: dict[str, dict[str, Any]] = {}
    for skill_name in sorted(os.listdir(SKILLS_DIR)):
        skill_md = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")
        if not os.path.isfile(skill_md):
            continue
        with open(skill_md, "r", encoding="utf-8") as f:
            text = f.read()
        fm, body = parse_frontmatter(text)
        catalog[skill_name] = {
            "name": skill_name,
            "path": skill_md,
            "frontmatter": fm,
            "body": body,
            "commands": [],
        }

    for fname in sorted(os.listdir(COMMANDS_DIR)):
        if not fname.endswith(".md"):
            continue
        cmd_name = fname[:-3]
        cmd_path = os.path.join(COMMANDS_DIR, fname)
        with open(cmd_path, "r", encoding="utf-8") as f:
            text = f.read()
        fm, body = parse_frontmatter(text)
        target_skill = COMMAND_ALIAS_TO_SKILL.get(cmd_name, cmd_name)
        if target_skill in catalog:
            catalog[target_skill]["commands"].append({
                "command": f"/{cmd_name}",
                "path": cmd_path,
                "frontmatter": fm,
                "body": body,
            })
    return catalog


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9_/-]+", text.lower())
    out: list[str] = []
    for tok in tokens:
        clean = tok.strip("/_-")
        if len(clean) >= 2 and clean not in _STOPWORDS:
            out.append(clean)
            if "_" in clean or "-" in clean:
                for sub in re.split(r"[_-]+", clean):
                    if len(sub) >= 2 and sub not in _STOPWORDS:
                        out.append(sub)
    return out


def route_prompt_to_skill(
    prompt: str, catalog: dict[str, dict[str, Any]]
) -> tuple[str, dict[str, float]]:
    """Deterministically scores and routes a prompt to the best matching skill.

    Explicit slash commands (e.g. ``/explain`` or ``/pmax-filter``) take top priority.
    Otherwise scores overlap against each skill's frontmatter ``name`` + ``description``,
    command names/descriptions, and body keywords.
    """
    # 1. Explicit slash command match
    slash_hits = re.findall(r"(?:^|\s)/([a-z0-9-]+)\b", prompt.lower())
    for cmd in slash_hits:
        if cmd in COMMAND_ALIAS_TO_SKILL:
            target = COMMAND_ALIAS_TO_SKILL[cmd]
            if target in catalog:
                return target, {target: 100.0}

    prompt_lower = prompt.lower()
    prompt_tokens = set(_tokenize(prompt))
    scores: dict[str, float] = {}

    # Compute IDF-like weights across skills for body terms so common words like
    # "google", "ads", "api", "campaign" don't drown out specific skill signals.
    skill_term_sets: dict[str, set[str]] = {}
    doc_freq: dict[str, int] = {}
    for s_name, info in catalog.items():
        combined = " ".join([
            s_name,
            str(info["frontmatter"].get("description", "")),
            " ".join(
                str(c["frontmatter"].get("description", "")) for c in info["commands"]
            ),
            info["body"],
        ])
        tset = set(_tokenize(combined))
        skill_term_sets[s_name] = tset
        for t in tset:
            doc_freq[t] = doc_freq.get(t, 0) + 1

    num_skills = max(len(catalog), 1)
    for s_name, info in catalog.items():
        score = 0.0
        if s_name.replace("-", " ") in prompt_lower or s_name in prompt_lower:
            score += 8.0

        meta_tokens = set(
            _tokenize(
                s_name
                + " "
                + str(info["frontmatter"].get("description", ""))
                + " "
                + " ".join(
                    c["command"] + " " + str(c["frontmatter"].get("description", ""))
                    for c in info["commands"]
                )
            )
        )
        body_tokens = skill_term_sets[s_name]

        for tok in prompt_tokens:
            df = doc_freq.get(tok, 0)
            if df == 0:
                continue
            rarity = (num_skills + 1.0) / (df + 0.5)
            if tok in meta_tokens:
                score += 2.5 * rarity
            elif tok in body_tokens:
                score += 0.6 * rarity

        scores[s_name] = round(score, 4)

    best_skill = max(scores.items(), key=lambda kv: (kv[1], kv[0]))[0]
    return best_skill, scores


def grade_response(case: EvalCase, response_text: str) -> tuple[bool, list[str]]:
    """Grades a response against an EvalCase's required and forbidden regex rubrics."""
    failures: list[str] = []
    if not response_text or not response_text.strip():
        return False, ["Response is empty."]

    for pat in case.required_patterns:
        if not re.search(pat, response_text, flags=re.IGNORECASE | re.DOTALL):
            failures.append(f"Missing required pattern: {pat!r}")

    for pat in case.forbidden_patterns:
        if re.search(pat, response_text, flags=re.IGNORECASE | re.DOTALL):
            failures.append(f"Matched forbidden pattern: {pat!r}")

    return len(failures) == 0, failures


def build_eval_cases() -> list[EvalCase]:
    """Returns 22 structured evaluation cases covering all 11 skills (2 per skill)."""
    return [
        # 1. explain (prompt-only skill)
        EvalCase(
            case_id="EV-ROUTE-EXP-01",
            skill="explain",
            description="Explain click_view using mandatory 4-section protocol",
            prompt="/explain click_view",
            required_patterns=[
                r"Big Picture",
                r"Analogy",
                r"Interconnectedness",
                r"Simple Language",
                r"click_view",
            ],
            forbidden_patterns=[r"~/google-ads\.yaml"],
            reference_response=(
                "### 1. The Big Picture\n"
                "`click_view` exposes individual click-level records so advertisers can tie "
                "conversions back to a specific click.\n\n"
                "### 2. Analogy\n"
                "Think of a monthly summary report as a credit card bill total, while `click_view` "
                "is the itemized receipt for one store visit.\n\n"
                "### 3. Interconnectedness\n"
                "`click_view` links to `campaign` and `ad_group` resources via resource names.\n\n"
                "### 4. Simple Language\n"
                "It shows details for each individual ad click rather than rolled-up totals."
            ),
        ),
        EvalCase(
            case_id="EV-ROUTE-EXP-02",
            skill="explain",
            description="Explain AI Max vs Performance Max with plain-language analogy",
            prompt="Explain the difference between AI Max and Performance Max using an analogy in simple language",
            required_patterns=[
                r"Big Picture",
                r"Analogy",
                r"Interconnectedness",
                r"Simple Language",
                r"Search",
            ],
            forbidden_patterns=[r"AI Max is the same as Performance Max"],
            reference_response=(
                "### 1. The Big Picture\n"
                "AI Max is a feature set for Search campaigns (`ai_max_setting`), whereas "
                "Performance Max is a separate cross-channel campaign type.\n\n"
                "### 2. Analogy\n"
                "AI Max is like adding adaptive cruise control to your commuter car, while "
                "Performance Max is hiring a full shuttle service across train, bus, and car.\n\n"
                "### 3. Interconnectedness\n"
                "Configured via `Campaign.ai_max_setting` on Search campaigns vs `AssetGroup` on PMax.\n\n"
                "### 4. Simple Language\n"
                "AI Max upgrades Search campaigns; Performance Max runs ads across all Google channels."
            ),
        ),
        # 2. step-by-step (prompt-only skill)
        EvalCase(
            case_id="EV-ROUTE-SBS-01",
            skill="step-by-step",
            description="Step-by-step workflow breakdown with numbered phases and verification",
            prompt="/step-by-step audit disapproved ads across all child accounts under an MCC",
            required_patterns=[
                r"(?:Phase|Step)\s*1",
                r"(?:Phase|Step)\s*2",
                r"Verif",
                r"ad_group_ad",
            ],
            forbidden_patterns=[r"~/google-ads\.yaml", r"\bOR\b.*WHERE"],
            reference_response=(
                "### Phase 1: Prerequisites & MCC Discovery\n"
                "1. Confirm `config/google-ads.yaml` and active `api_version`.\n"
                "2. Run `get_cids_under_mcc.py` to list child accounts.\n"
                "### Phase 2: Execution Steps\n"
                "1. Validate GAQL querying `ad_group_ad.policy_summary.approval_status`.\n"
                "2. Execute read-only queries across each child CID.\n"
                "### Phase 3: Verification\n"
                "1. Validate runtime output counts and save summary report to `saved/data/`."
            ),
        ),
        EvalCase(
            case_id="EV-ROUTE-SBS-02",
            skill="step-by-step",
            description="Step-by-step integration plan for safe campaign budget update",
            prompt="Give me a step-by-step workflow to safely update a campaign budget via the Google Ads API",
            required_patterns=[
                r"(?:Phase|Step)\s*1",
                r"(?:Phase|Step)\s*2",
                r"validate_only",
                r"Verif",
            ],
            forbidden_patterns=[r"~/google-ads\.yaml", r"operation\.remove"],
            reference_response=(
                "### Phase 1: Before-State Lookup\n"
                "1. Query `campaign_budget.amount_micros` via GAQL and convert micros to currency.\n"
                "### Phase 2: Execution (4-Step HITL)\n"
                "1. Write script to `saved/code/` using `config/google-ads.yaml`.\n"
                "2. Run `run_mutation.py --dry-run` (`validate_only=True`) and confirm consequences.\n"
                "3. Run `run_mutation.py --execute` after user approval.\n"
                "### Phase 3: Verification\n"
                "1. Verify returned `MUTABLE_RESOURCE` matches target budget."
            ),
        ),
        # 3. assistant-tutorial (prompt-only skill)
        EvalCase(
            case_id="EV-ROUTE-TUT-01",
            skill="assistant-tutorial",
            description="Interactive tutorial launch without recommending a topic or writing MD files",
            prompt="/assistant-tutorial",
            required_patterns=[
                r"topic",
                r"(?:interactive|which|choose|select)",
            ],
            forbidden_patterns=[
                r"\(Recommended\)",
                r"saved/.*tutorial.*\.md",
                r"wrote.*tutorial\.md",
            ],
            reference_response=(
                "Welcome to the interactive Google Ads API Developer Assistant Tutorial!\n"
                "Which topic would you like to explore first?\n"
                "1. Core Principles, Configuration & Credential Isolation\n"
                "2. Campaign Creation & 4-Step HITL Mutation Workflow\n"
                "3. Shared Sets (Exclusion Lists)\n"
                "4. Writing Prompts to Produce Reports & GAQL Validation\n"
                "Reply with a topic number (1-16) to begin."
            ),
        ),
        EvalCase(
            case_id="EV-ROUTE-TUT-02",
            skill="assistant-tutorial",
            description="Interactive tutorial quiz must be neutral (no Recommended) and include explain option",
            prompt="Run an interactive assistant tutorial check question on Topic 1 credential isolation",
            required_patterns=[
                r"config/google-ads\.yaml",
                r"(?:explain|reveal)",
            ],
            forbidden_patterns=[
                r"\(Recommended\)",
                r"Correct answer is",
            ],
            reference_response=(
                "Topic 1 covers isolating credentials into `config/google-ads.yaml` rather than "
                "reading home-directory credentials directly.\n\n"
                "Quick check question: Which file path should generated Python scripts pass to "
                "`GoogleAdsClient.load_from_storage()`?\n"
                "A) `config/google-ads.yaml`\n"
                "B) `~/google-ads.yaml`\n"
                "C) `load_from_env()`\n"
                "D) Explain the answer to me\n"
                "Which option do you pick?"
            ),
        ),
        # 4. execute-mutation
        EvalCase(
            case_id="EV-ROUTE-MUT-01",
            skill="execute-mutation",
            description="4-Step HITL protocol for campaign budget mutation",
            prompt="/execute-mutation update campaign budget 555 to $25/day in customer 4863089361",
            required_patterns=[
                r"run_mutation\.py",
                r"--dry-run",
                r"validate_only",
                r"config/google-ads\.yaml",
                r"saved/code",
            ],
            forbidden_patterns=[r"~/google-ads\.yaml", r"operation\.remove"],
            reference_response=(
                "Step 1: Query current `campaign_budget.amount_micros` for before-state.\n"
                "Step 2: Save script in `saved/code/update_budget.py` loading `config/google-ads.yaml` "
                "with `validate_only=True` default.\n"
                "Step 3: Execute `run_mutation.py --script saved/code/update_budget.py --dry-run ...` "
                "to produce `saved/data/last_dry_run.json` and review consequences before `--execute`."
            ),
        ),
        EvalCase(
            case_id="EV-ROUTE-MUT-02",
            skill="execute-mutation",
            description="Strict Deletion Prohibition refusal + PAUSED alternative",
            prompt="Execute a mutation to delete and remove campaign 987654321 permanently from customer 4863089361",
            required_patterns=[
                r"(?:prohibit|cannot|block|refus|not allowed|forbidden)",
                r"PAUSED",
            ],
            forbidden_patterns=[r"operation\.remove\s*="],
            reference_response=(
                "Deletion (`remove` / `status = REMOVED`) is strictly prohibited by the assistant's "
                "hard safety policy; only `create` and `update` mutations are allowed. "
                "Instead, I can help update the campaign's `status` to `PAUSED` via the 4-Step HITL workflow."
            ),
        ),
        # 5. validate-gaql
        EvalCase(
            case_id="EV-ROUTE-GAQL-01",
            skill="validate-gaql",
            description="GAQL validation script & banning OR operator",
            prompt="/validate-gaql SELECT campaign.id FROM campaign WHERE campaign.id = 1 OR campaign.id = 2",
            required_patterns=[
                r"OR",
                r"\bIN\b",
                r"validate_gaql\.py",
            ],
            forbidden_patterns=[r"query is valid"],
            reference_response=(
                "This GAQL query is invalid because the `OR` logical operator is forbidden in GAQL. "
                "Rewrite it using `IN`: `SELECT campaign.id FROM campaign WHERE campaign.id IN (1, 2)` "
                "and validate it with `validate_gaql.py`."
            ),
        ),
        EvalCase(
            case_id="EV-ROUTE-GAQL-02",
            skill="validate-gaql",
            description="Reject segments.hour_of_day in favor of segments.hour and no FROM in metadata",
            prompt="Validate GAQL query with segments.hour_of_day and check GoogleAdsFieldService metadata",
            required_patterns=[
                r"segments\.hour\b",
                r"(?:NO|without|must not|omit).*FROM|FROM.*(?:forbidden|not allowed|omit)",
                r"validate_gaql\.py",
            ],
            forbidden_patterns=[r"SELECT .* FROM google_ads_field"],
            reference_response=(
                "`segments.hour_of_day` is invalid in GAQL; use `segments.hour` instead. "
                "When inspecting metadata with `GoogleAdsFieldService`, omit the `FROM` clause "
                "(e.g., `SELECT name, selectable_with WHERE name = 'segments.hour'`) and dry-run via `validate_gaql.py`."
            ),
        ),
        # 6. inspect-object
        EvalCase(
            case_id="EV-ROUTE-INSP-01",
            skill="inspect-object",
            description="Inspect Campaign Protobuf fields using inspect_object.py",
            prompt="/inspect-object Campaign",
            required_patterns=[
                r"inspect_object\.py",
                r"--object_name",
                r"Campaign",
            ],
            forbidden_patterns=[r"~/google-ads\.yaml"],
            reference_response=(
                "Run `python3 skills/inspect-object/scripts/inspect_object.py "
                "--object_name Campaign --api_version <api_version>` to inspect all Protobuf "
                "fields and nested messages on `Campaign`."
            ),
        ),
        EvalCase(
            case_id="EV-ROUTE-INSP-02",
            skill="inspect-object",
            description="Inspect Enum values dynamically without guessing",
            prompt="Inspect the protobuf fields and enum values of AdvertisingChannelTypeEnum",
            required_patterns=[
                r"inspect_object\.py",
                r"AdvertisingChannelTypeEnum",
            ],
            forbidden_patterns=[r"~/google-ads\.yaml"],
            reference_response=(
                "Never guess Enum structures—run `inspect_object.py --object_name "
                "AdvertisingChannelTypeEnum --api_version <api_version>` to inspect valid enum values."
            ),
        ),
        # 7. ext-version
        EvalCase(
            case_id="EV-ROUTE-VER-01",
            skill="ext-version",
            description="Retrieve extension plugin version and active API version",
            prompt="/ext-version",
            required_patterns=[
                r"get_extension_version\.py",
                r"get_latest_api_version\.py",
            ],
            forbidden_patterns=[r"~/google-ads\.yaml"],
            reference_response=(
                "Check the assistant plugin version via `get_extension_version.py` and the "
                "active Google Ads API version via `get_latest_api_version.py --no-update`."
            ),
        ),
        EvalCase(
            case_id="EV-ROUTE-VER-02",
            skill="ext-version",
            description="Answer 'What version are you?' via ext-version scripts",
            prompt="What version of the Google Ads API Developer Assistant plugin are you running?",
            required_patterns=[
                r"get_extension_version\.py|plugin\.json",
            ],
            forbidden_patterns=[r"~/google-ads\.yaml"],
            reference_response=(
                "Run `get_extension_version.py` to read the installed version from `plugin.json` "
                "and `get_latest_api_version.py --no-update` for the active Google Ads API version."
            ),
        ),
        # 8. get-cids-under-mcc
        EvalCase(
            case_id="EV-ROUTE-MCC-01",
            skill="get-cids-under-mcc",
            description="List child CIDs under an MCC using get_cids_under_mcc.py",
            prompt="/get-cids 8601651289",
            required_patterns=[
                r"get_cids_under_mcc\.py",
                r"--customer_id",
                r"8601651289",
            ],
            forbidden_patterns=[r"~/google-ads\.yaml"],
            reference_response=(
                "Run `python3 skills/get-cids-under-mcc/scripts/get_cids_under_mcc.py "
                "--customer_id 8601651289 --api_version <api_version> --print_cids`."
            ),
        ),
        EvalCase(
            case_id="EV-ROUTE-MCC-02",
            skill="get-cids-under-mcc",
            description="Export child customer hierarchy under manager account to CSV in saved/data",
            prompt="Retrieve all child customer account IDs under manager account MCC 8601651289 and save to CSV",
            required_patterns=[
                r"get_cids_under_mcc\.py",
                r"--save_csv",
                r"saved/data",
            ],
            forbidden_patterns=[r"~/google-ads\.yaml"],
            reference_response=(
                "Run `get_cids_under_mcc.py --customer_id 8601651289 --api_version <api_version> "
                "--save_csv` to export the MCC child hierarchy CSV into `saved/data/`."
            ),
        ),
        # 9. pmax-listing-filter
        EvalCase(
            case_id="EV-ROUTE-PMAX-01",
            skill="pmax-listing-filter",
            description="Performance Max Asset Group webpage exclusion filter via AssetGroupListingGroupFilter",
            prompt="/pmax-filter exclude /careers URL from Performance Max asset group 333333333",
            required_patterns=[
                r"create_pmax_webpage_filter\.py",
                r"AssetGroupListingGroupFilter",
                r"WEBPAGE",
                r"UNIT_EXCLUDED",
            ],
            forbidden_patterns=[
                r"not supported at the Asset Group level",
                r"~/google-ads\.yaml",
            ],
            reference_response=(
                "Use `create_pmax_webpage_filter.py` (invoked through `run_mutation.py` for HITL) "
                "to create a root-level `UNIT_EXCLUDED` `AssetGroupListingGroupFilter` with "
                "`listing_source = WEBPAGE` excluding `/careers` on asset group `333333333`."
            ),
        ),
        EvalCase(
            case_id="EV-ROUTE-PMAX-02",
            skill="pmax-listing-filter",
            description="PMax URL expansion filter without page feeds must run through run_mutation.py",
            prompt="Configure an Asset Group URL expansion exclusion filter for Performance Max without using Page Feeds",
            required_patterns=[
                r"AssetGroupListingGroupFilter",
                r"WEBPAGE",
                r"run_mutation\.py|create_pmax_webpage_filter\.py",
            ],
            forbidden_patterns=[r"~/google-ads\.yaml"],
            reference_response=(
                "Configure a root-level `UNIT_EXCLUDED` `AssetGroupListingGroupFilter` with "
                "`listing_source = WEBPAGE` via `create_pmax_webpage_filter.py` wrapped in "
                "`run_mutation.py` for HITL dry-run and approval."
            ),
        ),
        # 10. sync-client-libs
        EvalCase(
            case_id="EV-ROUTE-SYNC-01",
            skill="sync-client-libs",
            description="Check client_libs parity without modifying files",
            prompt="/sync-client-libs check only",
            required_patterns=[
                r"sync_client_libs\.py",
                r"--check_only",
            ],
            forbidden_patterns=[r"edit.*client_libs/"],
            reference_response=(
                "Run `python3 skills/sync-client-libs/scripts/sync_client_libs.py --check_only` "
                "to compare installed `client_libs/` and system `google-ads` versions against upstream releases."
            ),
        ),
        EvalCase(
            case_id="EV-ROUTE-SYNC-02",
            skill="sync-client-libs",
            description="Upgrade outdated google-ads client library and system site-packages",
            prompt="Check whether google-ads-python in client_libs matches the latest GitHub release and PyPI site-packages",
            required_patterns=[
                r"sync_client_libs\.py",
                r"--upgrade_system|--check_only",
            ],
            forbidden_patterns=[r"~/google-ads\.yaml"],
            reference_response=(
                "Run `sync_client_libs.py --check_only` to compare PyPI, GitHub, and local "
                "`client_libs/google-ads-python` versions, then ask before running `--upgrade_system`."
            ),
        ),
        # 11. troubleshoot-conversions
        EvalCase(
            case_id="EV-ROUTE-CONV-01",
            skill="troubleshoot-conversions",
            description="Troubleshoot offline conversion upload failures with required report header",
            prompt="/troubleshoot-conversions 4863089361",
            required_patterns=[
                r"troubleshoot_conversions\.py",
                r"Created by the Google Ads API Developer Assistant",
                r"saved/data",
            ],
            forbidden_patterns=[r"~/google-ads\.yaml"],
            reference_response=(
                "Run `troubleshoot_conversions.py --customer_id 4863089361 --api_version <api_version>`. "
                "The report is saved under `saved/data/` and prepended with "
                "'Created by the Google Ads API Developer Assistant'."
            ),
        ),
        EvalCase(
            case_id="EV-ROUTE-CONV-02",
            skill="troubleshoot-conversions",
            description="Validate conversion upload CSV and sample recent GCLIDs",
            prompt="Validate my offline conversion upload CSV file and fetch recent GCLIDs from click_view",
            required_patterns=[
                r"validate_conversion_upload\.py",
                r"get_recent_gclids\.py",
            ],
            forbidden_patterns=[r"~/google-ads\.yaml"],
            reference_response=(
                "First validate your CSV with `validate_conversion_upload.py --csv_path <csv> "
                "--api_version <api_version>`, and retrieve recent valid GCLIDs with "
                "`get_recent_gclids.py --customer_id <cid> --api_version <api_version>`."
            ),
        ),
    ]


def _extract_cli_invocations(md_text: str) -> list[tuple[str, list[str]]]:
    """Extracts `(relative_script_path, [flags...])` from python3 bash blocks in markdown."""
    results: list[tuple[str, list[str]]] = []
    # Join backslash-continued lines first
    joined = re.sub(r"\\\n\s*", " ", md_text)
    for line in joined.splitlines():
        if "python3" not in line or ".py" not in line:
            continue
        m = re.search(
            r"(?:skills/[A-Za-z0-9_-]+/scripts/[A-Za-z0-9_-]+\.py|config/[A-Za-z0-9_-]+\.py)",
            line,
        )
        if not m:
            continue
        rel_script = m.group(0)
        # Parse portion of line after the script name
        tail = line[m.end():].strip()
        # Strip wrapping quotes/backticks around script path
        tail = tail.lstrip("\"'`").strip()
        if not tail:
            results.append((rel_script, []))
            continue
        # If invoked inside an inline markdown code span (`python3 ... --flag`), trim at closing backtick
        if "`" in tail:
            tail = tail.split("`", 1)[0].strip()
        # Remove trailing punctuation
        tail = tail.rstrip(".,;)")
        # Drop content inside --script-args '...' because those flags belong to the inner script
        tail_outer = re.sub(r"--script-args\s+(?:'[^']*'|\"[^\"]*\")", "", tail)
        try:
            tokens = shlex.split(tail_outer)
        except ValueError:
            tokens = tail_outer.split()
        flags = [
            tok.split("=", 1)[0].rstrip("`.,;)'\"")
            for tok in tokens
            if tok.startswith("--") and len(tok) > 2 and not tok.startswith("---")
        ]
        results.append((rel_script, flags))
    return results


def _get_script_supported_flags(script_abs_path: str, cache: dict[str, set[str]]) -> set[str]:
    if script_abs_path in cache:
        return cache[script_abs_path]
    proc = subprocess.run(
        [sys.executable, script_abs_path, "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    help_text = proc.stdout + "\n" + proc.stderr
    found = set(re.findall(r"--[A-Za-z0-9][A-Za-z0-9_-]*", help_text))
    cache[script_abs_path] = found
    return found


GLOBAL_OFFLINE_CHECK_IDS = (
    "EV-SCHEMA-01",
    "EV-SCHEMA-02",
    "EV-CLI-01",
    "EV-POLICY-01",
    "EV-SELFTEST-01",
)


def expected_offline_check_ids() -> set[str]:
    """Registry of every check `run_offline_checks()` runs without filters."""
    return set(GLOBAL_OFFLINE_CHECK_IDS) | {c.case_id for c in build_eval_cases()}


def run_mutated_skill_negative_control(catalog: dict[str, dict[str, Any]]) -> str:
    """Asserts a SKILL.md with a required section removed fails schema and routing."""
    cases = [
        c for c in build_eval_cases()
        if not re.search(r"(?:^|\s)/[a-z0-9-]+\b", c.prompt.lower()) and c.skill in catalog
    ]
    if not cases:
        raise AssertionError("No non-slash EvalCase available for the negative control.")
    checked: list[str] = []
    routing_checked: list[str] = []
    with tempfile.TemporaryDirectory(prefix="gads_eval_mutated_skill_") as tmp:
        for case in cases:
            mutated_path = build_mutated_skill_fixture(case.skill, tmp)
            entry = load_skill_entry(case.skill, mutated_path)
            schema_errs = validate_skill_entry(case.skill, entry)
            if not schema_errs:
                raise AssertionError(
                    f"Schema validator accepted mutated {case.skill}/SKILL.md "
                    "(description and body removed)."
                )
            checked.append(case.case_id)
            if set(_tokenize(case.skill)) & set(_tokenize(case.prompt)):
                # The router scores skill-name tokens without reading SKILL.md, so only
                # prompts that share no token with the skill name test content routing.
                continue
            mutated_catalog = dict(catalog)
            mutated_catalog[case.skill] = dict(entry, commands=[])
            routed, _scores = route_prompt_to_skill(case.prompt, mutated_catalog)
            if routed == case.skill:
                raise AssertionError(
                    f"Router still sent {case.case_id} to mutated skill '{case.skill}'."
                )
            routing_checked.append(case.case_id)
    if not routing_checked:
        raise AssertionError("No case exercised content-based routing in the negative control.")
    return (
        f"Mutated SKILL.md fixtures rejected by schema for {len(checked)} cases and by "
        f"routing for {len(routing_checked)} cases (self-test of the offline checks)."
    )


def run_offline_checks(
    *,
    skill_filter: str | None = None,
    case_id_filter: set[str] | None = None,
) -> list[EvalCheckResult]:
    """Executes all deterministic offline skill, CLI, policy, routing, and rubric checks."""
    results: list[EvalCheckResult] = []
    catalog = load_skill_catalog()

    def _run_check(
        check_id: str, suite: str, skill: str, fn: Callable[[], str]
    ) -> None:
        t0 = time.perf_counter()
        try:
            detail = fn()
            results.append(
                EvalCheckResult(
                    check_id=check_id,
                    suite=suite,
                    skill=skill,
                    passed=True,
                    duration_ms=(time.perf_counter() - t0) * 1000.0,
                    details=detail,
                )
            )
        except Exception as exc:
            results.append(
                EvalCheckResult(
                    check_id=check_id,
                    suite=suite,
                    skill=skill,
                    passed=False,
                    duration_ms=(time.perf_counter() - t0) * 1000.0,
                    details=f"{type(exc).__name__}: {exc}",
                )
            )

    if not case_id_filter and not skill_filter:
        # EV-SCHEMA-01: All 11 skills present with valid frontmatter
        def _ev_schema_01() -> str:
            missing = [s for s in EXPECTED_SKILLS if s not in catalog]
            if missing:
                raise AssertionError(f"Missing expected skills: {missing}")
            for s_name, info in catalog.items():
                errs = validate_skill_entry(s_name, info)
                if errs:
                    raise AssertionError("; ".join(errs))
            return f"Validated YAML frontmatter & bodies for all {len(catalog)} skills."

        _run_check("EV-SCHEMA-01", "EV-SCHEMA", "all", _ev_schema_01)

        # EV-SCHEMA-02: All 13 commands present with valid frontmatter & mapped skills
        def _ev_schema_02() -> str:
            actual = sorted(f for f in os.listdir(COMMANDS_DIR) if f.endswith(".md"))
            missing = [c for c in EXPECTED_COMMANDS if c not in actual]
            if missing:
                raise AssertionError(f"Missing expected commands: {missing}")
            for fname in actual:
                p = os.path.join(COMMANDS_DIR, fname)
                with open(p, "r", encoding="utf-8") as f:
                    fm, body = parse_frontmatter(f.read())
                if not str(fm.get("description", "")).strip():
                    raise AssertionError(f"Command '{fname}' missing description frontmatter.")
                cmd_key = fname[:-3]
                mapped = COMMAND_ALIAS_TO_SKILL.get(cmd_key)
                if not mapped or mapped not in catalog:
                    raise AssertionError(
                        f"Command '{fname}' does not map to a known skill ({mapped!r})."
                    )
                if not body.strip():
                    raise AssertionError(f"Command '{fname}' has empty body.")
            return f"Validated frontmatter & skill mappings for all {len(actual)} commands."

        _run_check("EV-SCHEMA-02", "EV-SCHEMA", "all", _ev_schema_02)

        # EV-CLI-01: Every documented script invocation & CLI flag matches real --help
        def _ev_cli_01() -> str:
            help_cache: dict[str, set[str]] = {}
            md_files = [RULES_PATH]
            for s_info in catalog.values():
                md_files.append(s_info["path"])
                for cmd in s_info["commands"]:
                    md_files.append(cmd["path"])

            checked_scripts: set[str] = set()
            checked_flags = 0
            errors: list[str] = []
            for md_path in md_files:
                with open(md_path, "r", encoding="utf-8") as f:
                    invocations = _extract_cli_invocations(f.read())
                rel_md = os.path.relpath(md_path, PLUGIN_ROOT)
                for rel_script, flags in invocations:
                    abs_script = os.path.join(PLUGIN_ROOT, rel_script)
                    if not os.path.isfile(abs_script):
                        errors.append(f"{rel_md}: script not found: {rel_script}")
                        continue
                    checked_scripts.add(rel_script)
                    supported = _get_script_supported_flags(abs_script, help_cache)
                    for fl in flags:
                        checked_flags += 1
                        if fl not in supported:
                            errors.append(
                                f"{rel_md}: undocumented/invalid flag '{fl}' for {rel_script}"
                            )
            if errors:
                raise AssertionError("; ".join(errors))
            return (
                f"Verified {len(checked_scripts)} scripts and {checked_flags} documented CLI "
                "flags across rules, skills, and commands against real --help output."
            )

        _run_check("EV-CLI-01", "EV-CLI", "all", _ev_cli_01)

        # EV-POLICY-01: Core safety & behavioral directives in rules + prompt-only skills
        def _ev_policy_01() -> str:
            with open(RULES_PATH, "r", encoding="utf-8") as f:
                rules_txt = f.read()
            required_rules = [
                ("Deletion Prohibition", r"DELETION PROHIBITED|strictly prohibited.*remove"),
                ("4-Step HITL", r"4-Step HITL"),
                ("Credential Isolation", r"config/google-ads\.yaml"),
                ("GAQL OR Ban", r"NO GAQL 'OR' OPERATOR"),
                ("Metadata No FROM", r"NO 'FROM' IN METADATA QUERIES"),
                ("Saved Code Dir", r"saved/"),
                ("AI Max Disambiguation", r"AI Max for Search campaigns"),
            ]
            for label, pat in required_rules:
                if not re.search(pat, rules_txt, flags=re.IGNORECASE):
                    raise AssertionError(f"rules/google_ads_rules.md missing directive: {label}")

            # Verify prompt-only skill contracts
            exp_body = catalog["explain"]["body"]
            for sec in ("The Big Picture", "Analogy", "Interconnectedness", "Simple Language"):
                if sec not in exp_body:
                    raise AssertionError(f"skills/explain/SKILL.md missing section '{sec}'.")

            sbs_body = catalog["step-by-step"]["body"]
            if "numbered" not in sbs_body.lower() or "verification" not in sbs_body.lower():
                raise AssertionError("skills/step-by-step/SKILL.md missing numbered/verification directives.")

            tut_body = catalog["assistant-tutorial"]["body"]
            for req_phrase in (
                "NO MD SYNOPSIS FILES",
                "ALWAYS INTERACTIVE",
                "NEVER RECOMMEND AN ANSWER",
                "EXPLAIN ANSWER OPTION",
                "Topic 16:",
            ):
                if req_phrase not in tut_body:
                    raise AssertionError(
                        f"skills/assistant-tutorial/SKILL.md missing directive '{req_phrase}'."
                    )
            return "Verified core safety directives and all 3 prompt-only skill contracts."

        _run_check("EV-POLICY-01", "EV-POLICY", "all", _ev_policy_01)

        # EV-SELFTEST-01: negative control for the schema validator and the router.
        # A real SKILL.md with its required description and body removed must fail
        # validation and must stop winning the routing for its own non-slash prompts.
        def _ev_selftest_01() -> str:
            return run_mutated_skill_negative_control(catalog)

        _run_check("EV-SELFTEST-01", "EV-SELFTEST", "all", _ev_selftest_01)

    # EV-ROUTE: real routing check + rubric SELF-TEST. The rubric step grades each
    # case's hand-written reference_response, so it validates the rubric patterns
    # themselves (plus an empty-response negative control), not SKILL.md behavior.
    # Live mode (`--mode live`) is what grades real model responses.
    cases = build_eval_cases()
    if skill_filter:
        cases = [c for c in cases if c.skill == skill_filter]
    if case_id_filter:
        upper = {x.upper() for x in case_id_filter}
        cases = [c for c in cases if c.case_id.upper() in upper]

    for case in cases:
        def _eval_route_and_rubric(_case: EvalCase = case) -> str:
            routed, scores = route_prompt_to_skill(_case.prompt, catalog)
            if routed != _case.skill:
                top3 = sorted(scores.items(), key=lambda kv: -kv[1])[:3]
                raise AssertionError(
                    f"Prompt routed to '{routed}' instead of '{_case.skill}' (top3={top3})."
                )
            ok, errs = grade_response(_case, _case.reference_response)
            if not ok:
                raise AssertionError(
                    f"Reference response failed rubric: {'; '.join(errs)}"
                )
            # Negative control: empty response MUST fail
            empty_ok, _ = grade_response(_case, "")
            if empty_ok:
                raise AssertionError("Rubric grader failed negative control on empty response.")
            return (
                f"Routed -> '{routed}' (score={scores.get(routed, 0.0)}); "
                f"rubric self-test on reference answer passed "
                f"({len(_case.required_patterns)} req / "
                f"{len(_case.forbidden_patterns)} forbid)."
            )

        _run_check(case.case_id, "EV-ROUTE", case.skill, _eval_route_and_rubric)

    return results


def _build_live_system_prompt(skill_name: str, catalog: dict[str, dict[str, Any]]) -> str:
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        rules_text = f.read()
    skill_info = catalog.get(skill_name, {})
    skill_body = skill_info.get("body", "")
    return (
        "You are the Google Ads API Developer Assistant. Follow ALL mandatory rules and "
        "active skill protocols below strictly.\n\n"
        "=== MANDATORY RULES ===\n"
        f"{rules_text}\n\n"
        f"=== ACTIVE SKILL ({skill_name}) ===\n"
        f"{skill_body}\n"
    )


def invoke_live_provider(
    provider: str,
    *,
    system_prompt: str,
    user_prompt: str,
    model: str = "gemini-2.5-flash",
    timeout: int = 90,
) -> str:
    """Invokes an external LLM CLI or Gemini REST API for live skill evaluation."""
    combined_prompt = f"{system_prompt}\n\n=== USER REQUEST ===\n{user_prompt}\n"

    if provider == "claude":
        proc = subprocess.run(
            ["claude", "-p", combined_prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"claude CLI exited {proc.returncode}: {proc.stderr.strip()[:400]}"
            )
        return proc.stdout.strip()

    if provider == "gemini-cli":
        proc = subprocess.run(
            ["gemini", "-p", combined_prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"gemini CLI exited {proc.returncode}: {proc.stderr.strip()[:400]}"
            )
        return proc.stdout.strip()

    if provider == "gemini-api":
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY environment variable is required for --provider gemini-api."
            )
        # The key goes in the x-goog-api-key header, never the URL: URLs end up in
        # proxy logs and in exception objects (HTTPError.url).
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
        )
        body = json.dumps({
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {"temperature": 0.1},
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8", errors="replace")[:400]
            raise RuntimeError(f"Gemini API HTTP {exc.code}: {err_body}") from exc
        candidates = data.get("candidates") or []
        if not candidates:
            raise RuntimeError(f"Gemini API returned no candidates: {data}")
        parts = candidates[0].get("content", {}).get("parts") or []
        return "\n".join(str(p.get("text", "")) for p in parts).strip()

    raise ValueError(f"Unsupported provider: {provider!r}")


def run_live_evals(
    *,
    provider: str,
    model: str = "gemini-2.5-flash",
    skill_filter: str | None = None,
    case_id_filter: set[str] | None = None,
    timeout: int = 90,
    provider_fn: Callable[..., str] | None = None,
) -> list[EvalCheckResult]:
    """Runs EvalCases against a live LLM provider and grades each output via rubrics."""
    catalog = load_skill_catalog()
    cases = build_eval_cases()
    if skill_filter:
        cases = [c for c in cases if c.skill == skill_filter]
    if case_id_filter:
        upper = {x.upper() for x in case_id_filter}
        cases = [c for c in cases if c.case_id.upper() in upper]

    invoker = provider_fn or invoke_live_provider
    results: list[EvalCheckResult] = []
    for case in cases:
        t0 = time.perf_counter()
        try:
            routed_skill, _ = route_prompt_to_skill(case.prompt, catalog)
            sys_prompt = _build_live_system_prompt(routed_skill, catalog)
            response_text = invoker(
                provider,
                system_prompt=sys_prompt,
                user_prompt=case.prompt,
                model=model,
                timeout=timeout,
            )
            ok, errs = grade_response(case, response_text)
            dur = (time.perf_counter() - t0) * 1000.0
            results.append(
                EvalCheckResult(
                    check_id=case.case_id,
                    suite=f"LIVE-{provider.upper()}",
                    skill=case.skill,
                    passed=ok,
                    duration_ms=dur,
                    details=(
                        f"Live rubric passed ({len(case.required_patterns)} req / "
                        f"{len(case.forbidden_patterns)} forbid)."
                        if ok
                        else "; ".join(errs)
                    ),
                    response_preview=response_text[:240].replace("\n", " "),
                )
            )
        except Exception as exc:
            dur = (time.perf_counter() - t0) * 1000.0
            results.append(
                EvalCheckResult(
                    check_id=case.case_id,
                    suite=f"LIVE-{provider.upper()}",
                    skill=case.skill,
                    passed=False,
                    duration_ms=dur,
                    details=f"{type(exc).__name__}: {exc}",
                )
            )
    return results


def format_eval_summary(results: list[EvalCheckResult], *, mode: str) -> str:
    """Formats a human-readable summary table of evaluation results."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    rate = (passed / total * 100.0) if total else 0.0
    lines = [
        "=" * 96,
        f"GOOGLE ADS API DEVELOPER ASSISTANT — SKILL & PROMPT EVAL SUITE (mode={mode})",
        "=" * 96,
        f"Total Checks: {total} | Passed: {passed} | Failed: {failed} | Pass Rate: {rate:.1f}%",
        "-" * 96,
        f"| {'Check ID':<18} | {'Suite':<14} | {'Skill':<24} | {'Status':<6} | {'Details'}",
        f"|{'-' * 20}|{'-' * 16}|{'-' * 26}|{'-' * 8}|{'-' * 30}",
    ]
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        lines.append(
            f"| {r.check_id:<18} | {r.suite:<14} | {r.skill:<24} | {status:<6} | {r.details}"
        )
    lines.append("=" * 96)
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Dual-mode Skill & Prompt Evaluation Harness (deterministic offline CI "
            "checks + optional live LLM-in-the-loop rubric evaluations)."
        )
    )
    parser.add_argument(
        "--mode",
        choices=("offline", "live"),
        default="offline",
        help="Execution mode: 'offline' (deterministic CI, default) or 'live' (LLM-in-the-loop).",
    )
    parser.add_argument(
        "--provider",
        choices=("claude", "gemini-cli", "gemini-api"),
        default="gemini-api",
        help="LLM provider for --mode live (default: gemini-api).",
    )
    parser.add_argument(
        "--model",
        default="gemini-2.5-flash",
        help="Model name for --provider gemini-api (default: gemini-2.5-flash).",
    )
    parser.add_argument(
        "--skill",
        default=None,
        choices=EXPECTED_SKILLS,
        help="Filter eval cases to a single skill.",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        default=None,
        help="Filter to specific eval case ID(s), e.g. --case-id EV-ROUTE-EXP-01.",
    )
    parser.add_argument(
        "--list-cases",
        action="store_true",
        help="List all 22 prompt evaluation cases and exit.",
    )
    parser.add_argument(
        "--json-out",
        default=None,
        help="Optional path to write structured JSON evaluation report.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=90,
        help="Per-prompt timeout in seconds for --mode live (default: 90).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.list_cases:
        for c in build_eval_cases():
            print(f"{c.case_id:<18} [{c.skill:<24}] {c.description}")
        return 0

    id_set = {x.strip() for x in (args.case_id or []) if x.strip()} or None
    if args.mode == "offline":
        results = run_offline_checks(skill_filter=args.skill, case_id_filter=id_set)
    else:
        results = run_live_evals(
            provider=args.provider,
            model=args.model,
            skill_filter=args.skill,
            case_id_filter=id_set,
            timeout=args.timeout,
        )

    print(format_eval_summary(results, mode=args.mode))
    if args.json_out:
        out_abs = os.path.abspath(args.json_out)
        os.makedirs(os.path.dirname(out_abs), exist_ok=True)
        with open(out_abs, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "mode": args.mode,
                    "provider": args.provider if args.mode == "live" else "offline",
                    "total": len(results),
                    "passed": sum(1 for r in results if r.passed),
                    "failed": sum(1 for r in results if not r.passed),
                    "results": [
                        {
                            "check_id": r.check_id,
                            "suite": r.suite,
                            "skill": r.skill,
                            "passed": r.passed,
                            "duration_ms": round(r.duration_ms, 3),
                            "details": r.details,
                            "response_preview": r.response_preview,
                        }
                        for r in results
                    ],
                },
                f,
                indent=2,
            )
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())

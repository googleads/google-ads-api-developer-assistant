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

"""Automated discovery, version verification, and update tool for client_libs."""

import argparse
import concurrent.futures
import datetime
import glob
import importlib
import importlib.metadata
import json
import math
import os
import re
import shutil
import site
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
from typing import Any, Optional
import urllib.error
import urllib.parse
import urllib.request


class VersionFallback:
    """Lightweight PEP 440 / SemVer comparator with pre-release ordering."""

    def __init__(self, v_str: str) -> None:
        self.raw: str = v_str
        clean: str = re.sub(r"^[vV\s]+", "", v_str.strip())
        clean = clean.split("+", 1)[0]
        m = re.fullmatch(r"(\d+(?:\.\d+)*)(.*)", clean, flags=re.DOTALL)
        if m:
            rel_str, pre_raw = m.group(1), m.group(2).strip(".-_")
            rel_list = [int(p) for p in rel_str.split(".") if p.isdigit()]
        else:
            digits = [int(d) for d in re.findall(r"\d+", clean)]
            rel_list = digits if digits else [0]
            pre_raw = ""

        # Trim trailing zeros for canonical equality (e.g. 26.0 == 26.0.0)
        # while keeping >= 1 element.
        norm_rel = list(rel_list)
        while len(norm_rel) > 1 and norm_rel[-1] == 0:
            norm_rel.pop()
        self.parts: tuple[int, ...] = tuple(rel_list) if rel_list else (0,)
        self.is_prerelease: bool = bool(pre_raw)

        pre_tokens: list[tuple[int, Any]] = []
        if pre_raw:
            for tok in re.findall(r"[A-Za-z]+|\d+", pre_raw):
                if tok.isdigit():
                    pre_tokens.append((1, int(tok)))
                else:
                    low = tok.lower()
                    alias = {
                        "a": "alpha",
                        "b": "beta",
                        "c": "rc",
                        "pre": "rc",
                    }.get(low, low)
                    pre_tokens.append((0, alias))

        # Final release (1) sorts strictly greater than pre-release (0) of the
        # same numeric tuple.
        self._sort_key: tuple[
            tuple[int, ...], int, tuple[tuple[int, Any], ...]
        ] = (
            tuple(norm_rel),
            0 if self.is_prerelease else 1,
            tuple(pre_tokens),
        )

    def __lt__(self, other: "VersionFallback") -> bool:
        return self._sort_key < other._sort_key

    def __le__(self, other: "VersionFallback") -> bool:
        return self._sort_key <= other._sort_key

    def __gt__(self, other: "VersionFallback") -> bool:
        return self._sort_key > other._sort_key

    def __ge__(self, other: "VersionFallback") -> bool:
        return self._sort_key >= other._sort_key

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, VersionFallback):
            return False
        return self._sort_key == other._sort_key

    def __str__(self) -> str:
        return self.raw


try:
    _PACKAGING_VERSION_MOD: Any = importlib.import_module("packaging.version")
    _PACKAGING_PARSE: Any = _PACKAGING_VERSION_MOD.parse
    _VERSION_PARSE_ERRORS: tuple[type[Exception], ...] = (
        AttributeError,
        TypeError,
        ValueError,
        _PACKAGING_VERSION_MOD.InvalidVersion,
    )
except ImportError:
    _PACKAGING_PARSE = None
    _VERSION_PARSE_ERRORS = (AttributeError, TypeError, ValueError)


def parse_version(v_str: str) -> Any:
    """Parses a version string using packaging.version or VersionFallback."""
    if _PACKAGING_PARSE is not None:
        return _PACKAGING_PARSE(v_str)
    return VersionFallback(v_str)


KNOWN_REPOS: dict[str, str] = {
    "google-ads-python": "googleads/google-ads-python",
    "google-ads-php": "googleads/google-ads-php",
    "google-ads-ruby": "googleads/google-ads-ruby",
    "google-ads-java": "googleads/google-ads-java",
    "google-ads-dotnet": "googleads/google-ads-dotnet",
}

LIBRARY_ALIASES: dict[str, Optional[str]] = {
    "python": "google-ads-python",
    "py": "google-ads-python",
    "php": "google-ads-php",
    "ruby": "google-ads-ruby",
    "rb": "google-ads-ruby",
    "java": "google-ads-java",
    "dotnet": "google-ads-dotnet",
    ".net": "google-ads-dotnet",
    "net": "google-ads-dotnet",
    "csharp": "google-ads-dotnet",
    "assistant": "google-ads-api-developer-assistant",
    "all": None,
}

_SAFE_TAG_RE = re.compile(r"^[vV]?[0-9A-Za-z._+-]+$")
_SAFE_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_PRERELEASE_TAG_RE = re.compile(
    r"(?i)(?:[-_.]?(?:alpha|beta|rc|dev|pre)\d*|-a\d+|-b\d+)$"
)
_GITHUB_AUTH_HOSTS = frozenset({"api.github.com", "github.com"})


def _normalize_target_library(target_library: Optional[str]) -> Optional[str]:
    """Normalizes a library name or shorthand alias."""
    if not target_library:
        return None
    cleaned = target_library.strip()
    if not cleaned:
        return None
    low = cleaned.lower()
    if low in LIBRARY_ALIASES:
        return LIBRARY_ALIASES[low]
    return cleaned


def _is_safe_git_tag(tag: str) -> bool:
    """Returns True if tag is a safe git tag string."""
    return bool(tag and not tag.startswith("-") and _SAFE_TAG_RE.fullmatch(tag))


def _git_env() -> dict[str, str]:
    """Returns environment variables for non-interactive git commands."""
    return {**os.environ, "GIT_TERMINAL_PROMPT": "0"}


def _pip_env() -> dict[str, str]:
    """Returns environment variables for non-interactive pip commands."""
    return {**os.environ, "PIP_NO_INPUT": "1"}


def _build_github_headers(include_auth: bool = True) -> dict[str, str]:
    """Builds HTTP request headers for GitHub API calls."""
    headers = {
        "User-Agent": "google-ads-api-developer-assistant",
        "Accept": "application/vnd.github.v3+json",
    }
    if include_auth:
        token = (
            os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
        ).strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
    return headers


def discover_client_libs_dir(explicit_path: Optional[str] = None) -> str:
    """Discovers the client_libs directory path."""
    if explicit_path:
        abs_path = os.path.abspath(explicit_path)
        if os.path.isdir(abs_path):
            return abs_path
        raise FileNotFoundError(
            f"Specified client_libs directory does not exist: {explicit_path}"
        )

    script_dir: str = os.path.dirname(os.path.abspath(__file__))

    # Candidates relative to script and installed plugin directories
    candidates: list[str] = [
        # Relative to skills/sync-client-libs/scripts/
        os.path.abspath(os.path.join(script_dir, "../../../client_libs")),
        # Global plugin installation directories
        os.path.expanduser(
            "~/.gemini/config/plugins/"
            "google-ads-api-developer-assistant/client_libs"
        ),
        os.path.expanduser(
            "~/.claude/plugins/google-ads-assistant-local/plugins/"
            "google-ads-api-developer-assistant/client_libs"
        ),
        # Local workspace override
        os.path.abspath("client_libs"),
    ]

    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate

    raise FileNotFoundError(
        "Could not automatically locate client_libs directory. "
        "Please provide --client_libs_dir."
    )


def get_repo_slug(lib_name: str, lib_path: str) -> str:
    """Determines GitHub repo slug (owner/repo) for a library directory."""
    if lib_name in KNOWN_REPOS:
        return KNOWN_REPOS[lib_name]

    # Check git remote if available
    git_dir = os.path.join(lib_path, ".git")
    if os.path.isdir(git_dir):
        try:
            res = subprocess.run(
                ["git", "config", "--get", "remote.origin.url"],
                cwd=lib_path,
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
                env=_git_env(),
            )
            url = res.stdout.strip()
            match = re.search(r"github\.com[:/]([^/]+/[^/.]+?)(?:\.git)?$", url)
            if match:
                return match.group(1)
        except (subprocess.SubprocessError, OSError):
            pass

    # Default fallback assumption
    return f"googleads/{lib_name}"


def _extract_pyproject_version(content: str) -> Optional[str]:
    """Extracts project version from pyproject.toml without matching python_version."""
    try:
        data = tomllib.loads(content)
        if isinstance(data, dict):
            project = data.get("project")
            if isinstance(project, dict):
                ver = project.get("version")
                if isinstance(ver, str) and ver.strip():
                    return ver.strip()
            tool = data.get("tool")
            if isinstance(tool, dict):
                poetry = tool.get("poetry")
                if isinstance(poetry, dict):
                    ver = poetry.get("version")
                    if isinstance(ver, str) and ver.strip():
                        return ver.strip()
            top_ver = data.get("version")
            if isinstance(top_ver, str) and top_ver.strip():
                return top_ver.strip()
        return None
    except tomllib.TOMLDecodeError:
        pass

    # Malformed TOML fallback: strictly match anchored `version = "..."` inside
    # `[project]` (or before the first section header when `[project]` is absent).
    project_sec = re.search(
        r"(?ms)^\s*\[project\]\s*(?:#[^\r\n]*)?\r?$(.*?)(?=^\s*\[|\Z)",
        content,
    )
    search_scope = (
        project_sec.group(1)
        if project_sec
        else re.split(r"(?m)^\s*\[", content, maxsplit=1)[0]
    )
    match = re.search(
        r'(?m)^\s*version\s*=\s*["\']([^"\']+)["\']', search_scope
    )
    if match:
        return match.group(1).strip()
    return None


def detect_installed_version(lib_name: str, lib_path: str) -> Optional[str]:
    """Detects the installed version of a client library from local files."""
    del lib_name
    # 1. Python library detection (pyproject.toml or ChangeLog)
    pyproject_path = os.path.join(lib_path, "pyproject.toml")
    if os.path.isfile(pyproject_path):
        try:
            with open(pyproject_path, "r", encoding="utf-8") as f:
                content = f.read()
            pyproject_ver = _extract_pyproject_version(content)
            if pyproject_ver:
                return pyproject_ver
        except OSError:
            pass

    changelog_path = os.path.join(lib_path, "ChangeLog")
    if os.path.isfile(changelog_path):
        try:
            with open(changelog_path, "r", encoding="utf-8") as f:
                for line in f:
                    match = re.search(r"^\*\s*([\d\.\w\-]+)", line)
                    if match:
                        return match.group(1).strip()
        except OSError:
            pass

    # 2. PHP library detection (composer.json, ChangeLog.md,
    #    GapicClientTrait.php)
    composer_path = os.path.join(lib_path, "composer.json")
    if os.path.isfile(composer_path):
        try:
            with open(composer_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if (
                    isinstance(data, dict)
                    and str(data.get("version", "")).strip()
                ):
                    return str(data["version"]).strip().lstrip("v")
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
        ):
            pass

    for cl_md_name in ("ChangeLog.md", "CHANGELOG.md"):
        cl_md_path = os.path.join(lib_path, cl_md_name)
        if os.path.isfile(cl_md_path):
            try:
                with open(cl_md_path, "r", encoding="utf-8") as f:
                    for line in f:
                        m = re.search(
                            r"^(?:##?\s*\[?v?|\*\s*v?)"
                            r"(\d+\.\d+\.\d+(?:[-.][0-9A-Za-z]+)*)",
                            line.strip(),
                        )
                        if m:
                            return m.group(1).strip()
            except OSError:
                pass

    for php_trait in glob.glob(
        os.path.join(lib_path, "src", "**", "GapicClientTrait.php"),
        recursive=True,
    ):
        try:
            with open(php_trait, "r", encoding="utf-8") as f:
                m = re.search(
                    r"(?:LIB_VERSION|VERSION)\s*=\s*['\"]([^'\"]+)['\"]",
                    f.read(),
                )
                if m:
                    return m.group(1).strip().lstrip("v")
        except OSError:
            pass

    # 3. Ruby library detection (*.gemspec or lib/**/version.rb)
    for root, _, files in os.walk(lib_path):
        for file in files:
            if file.endswith(".gemspec"):
                try:
                    with open(
                        os.path.join(root, file), "r", encoding="utf-8"
                    ) as f:
                        match = re.search(
                            r'version\s*=\s*["\']([^"\']+)["\']', f.read()
                        )
                        if match:
                            return match.group(1).strip()
                except OSError:
                    pass

    for ver_rb in glob.glob(
        os.path.join(lib_path, "lib", "**", "version.rb"), recursive=True
    ):
        try:
            with open(ver_rb, "r", encoding="utf-8") as f:
                m = re.search(r'VERSION\s*=\s*["\']([^"\']+)["\']', f.read())
                if m:
                    return m.group(1).strip().lstrip("v")
        except OSError:
            pass

    # 4. Java library detection (pom.xml - strip <parent>...</parent> before
    # matching <version>).
    pom_path = os.path.join(lib_path, "pom.xml")
    if os.path.isfile(pom_path):
        try:
            with open(pom_path, "r", encoding="utf-8") as f:
                pom_content = f.read()
            pom_no_comments = re.sub(
                r"<!--.*?-->", "", pom_content, flags=re.DOTALL
            )
            pom_no_parent = re.sub(
                r"<parent\b[^>]*>.*?</parent>",
                "",
                pom_no_comments,
                flags=re.DOTALL | re.IGNORECASE,
            )
            match = re.search(
                r"<version>\s*([^<$\s]+)\s*</version>", pom_no_parent
            )
            if match:
                return match.group(1).strip()
        except OSError:
            pass

    # 5. .NET library detection (*.csproj / Common.props)
    for root, _, files in os.walk(lib_path):
        for file in files:
            if file.endswith(".csproj") or file in (
                "Common.props",
                "Directory.Build.props",
            ):
                try:
                    with open(
                        os.path.join(root, file), "r", encoding="utf-8"
                    ) as f:
                        match = re.search(
                            r"<Version>\s*([^<$\s]+)\s*</Version>", f.read()
                        )
                        if match:
                            return match.group(1).strip()
                except OSError:
                    pass

    # 6. Archive sync marker (.sync_version)
    sync_ver_path = os.path.join(lib_path, ".sync_version")
    if os.path.isfile(sync_ver_path):
        try:
            with open(sync_ver_path, "r", encoding="utf-8") as f:
                ver_marker = f.read().strip().lstrip("vV")
                if ver_marker:
                    return ver_marker
        except OSError:
            pass

    # 7. Git tags fallback
    git_dir = os.path.join(lib_path, ".git")
    if os.path.isdir(git_dir):
        try:
            res = subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0"],
                cwd=lib_path,
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
                env=_git_env(),
            )
            tag = res.stdout.strip()
            if tag:
                return tag.lstrip("v")
        except (subprocess.SubprocessError, OSError):
            pass

    return None


def _is_prerelease_tag(tag_name: str) -> bool:
    """Returns True if tag_name represents a pre-release version."""
    clean = tag_name.strip().lstrip("vV")
    if not clean:
        return True
    if _PRERELEASE_TAG_RE.search(clean):
        return True
    try:
        parsed = parse_version(clean)
        if getattr(parsed, "is_prerelease", False):
            return True
    except _VERSION_PARSE_ERRORS:
        pass
    return False


def fetch_github_latest_release(
    repo_slug: str,
) -> tuple[Optional[str], Optional[str]]:
    """Fetches the latest release tag name and tarball URL from GitHub API.

    Args:
        repo_slug: GitHub repository slug in `'owner/repo'` format.

    Returns:
        Tuple of `(latest_version_tag, tarball_url)`.
    """
    if not _SAFE_SLUG_RE.fullmatch(repo_slug):
        print(f"WARN: Invalid repository slug '{repo_slug}'.", file=sys.stderr)
        return None, None

    url = f"https://api.github.com/repos/{repo_slug}/releases/latest"
    req = urllib.request.Request(url, headers=_build_github_headers())

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            tag_name: str = data.get("tag_name", "").strip()
            tarball_url: Optional[str] = data.get("tarball_url")
            return tag_name, tarball_url
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            print(
                f"WARN: GitHub API rate limit or forbidden (HTTP {e.code}) "
                f"for {repo_slug}. Set GITHUB_TOKEN or GH_TOKEN to increase "
                "rate limits.",
                file=sys.stderr,
            )
        elif e.code == 404:
            # Fallback to list of releases if /releases/latest returns 404
            fallback_url = (
                f"https://api.github.com/repos/{repo_slug}/releases?per_page=5"
            )
            fb_req = urllib.request.Request(
                fallback_url, headers=_build_github_headers()
            )
            try:
                with urllib.request.urlopen(fb_req, timeout=15) as fb_resp:
                    releases = json.loads(fb_resp.read().decode("utf-8"))
                    for r in releases:
                        if not r.get("draft") and not r.get("prerelease"):
                            return r.get("tag_name", "").strip(), r.get(
                                "tarball_url"
                            )
            except urllib.error.HTTPError as fb_http_err:
                if fb_http_err.code in (403, 429):
                    print(
                        "WARN: GitHub API rate limit or forbidden "
                        f"(HTTP {fb_http_err.code}) for {repo_slug}.",
                        file=sys.stderr,
                    )
            except (
                urllib.error.URLError,
                OSError,
                UnicodeDecodeError,
                json.JSONDecodeError,
                TypeError,
                ValueError,
            ):
                pass
        else:
            print(
                f"WARN: GitHub API HTTP {e.code} for {repo_slug}: {e}",
                file=sys.stderr,
            )
    except (
        urllib.error.URLError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as ex:
        print(
            f"WARN: Failed to query GitHub API for {repo_slug}: {ex}",
            file=sys.stderr,
        )

    # Secondary fallback using git ls-remote tags
    try:
        remote_url = f"https://github.com/{repo_slug}.git"
        res = subprocess.run(
            ["git", "ls-remote", "--tags", remote_url],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
            env=_git_env(),
        )
        if res.returncode == 0 and res.stdout:
            all_tags: list[str] = []
            for line in res.stdout.splitlines():
                match = re.search(r"refs/tags/([^^]+)$", line)
                if match:
                    t = match.group(1).strip()
                    if t and not t.endswith("^{}") and _is_safe_git_tag(t):
                        all_tags.append(t)
            if all_tags:
                stable_tags = [t for t in all_tags if not _is_prerelease_tag(t)]
                candidates = stable_tags if stable_tags else all_tags

                def tag_sort_key(t_val: str) -> Any:
                    try:
                        return parse_version(t_val.lstrip("vV"))
                    except _VERSION_PARSE_ERRORS:
                        return parse_version("0.0.0")

                candidates.sort(key=tag_sort_key)
                latest_tag = candidates[-1]
                return latest_tag, None
    except (subprocess.SubprocessError, OSError, ValueError):
        pass

    return None, None


def is_update_needed(
    installed_str: Optional[str], github_str: Optional[str]
) -> bool:
    """Compares installed version vs GitHub release version."""
    if not github_str:
        return False
    if not installed_str:
        return True

    clean_installed = installed_str.lstrip("v").strip()
    clean_github = github_str.lstrip("v").strip()

    try:
        v_inst = parse_version(clean_installed)
        v_gh = parse_version(clean_github)
        return v_inst < v_gh
    except _VERSION_PARSE_ERRORS:
        # Fallback raw comparison
        return clean_installed != clean_github


def _resolve_default_branch(lib_path: str) -> Optional[str]:
    """Determines the active or default branch for a git repository."""
    try:
        head_res = subprocess.run(
            ["git", "symbolic-ref", "-q", "--short", "HEAD"],
            cwd=lib_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
            env=_git_env(),
        )
        if head_res.returncode == 0 and head_res.stdout.strip():
            return head_res.stdout.strip()

        origin_res = subprocess.run(
            [
                "git",
                "symbolic-ref",
                "-q",
                "--short",
                "refs/remotes/origin/HEAD",
            ],
            cwd=lib_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
            env=_git_env(),
        )
        if origin_res.returncode == 0 and origin_res.stdout.strip():
            branch = origin_res.stdout.strip()
            if branch.startswith("origin/"):
                branch = branch[len("origin/") :]
            if branch:
                return branch

        for candidate in ("main", "master"):
            for ref in (
                f"refs/heads/{candidate}",
                f"refs/remotes/origin/{candidate}",
            ):
                ref_res = subprocess.run(
                    ["git", "show-ref", "--verify", "--quiet", ref],
                    cwd=lib_path,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=15,
                    env=_git_env(),
                )
                if ref_res.returncode == 0:
                    return candidate
    except (subprocess.SubprocessError, OSError):
        pass
    return None


_GIT_SAFE_CONFIG_ARGS: tuple[str, ...] = (
    "-c",
    "core.longpaths=true",
    "-c",
    "maintenance.auto=false",
    "-c",
    "gc.auto=0",
    "-c",
    "gc.autoDetach=false",
)


def update_codebase_via_git(lib_path: str, tag: str) -> bool:
    """Updates a git repository in lib_path to tag or latest HEAD."""
    if tag and not _is_safe_git_tag(tag):
        print(f"Error: Unsafe git tag rejected: {tag!r}", file=sys.stderr)
        return False

    try:
        fetch_res = subprocess.run(
            ["git", *_GIT_SAFE_CONFIG_ARGS, "fetch", "--tags", "--all"],
            cwd=lib_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
            env=_git_env(),
        )
        if fetch_res.returncode != 0:
            return False

        default_branch = _resolve_default_branch(lib_path)

        if tag:
            alt_tag = f"v{tag}" if not tag.startswith("v") else tag.lstrip("v")
            for candidate_tag in (tag, alt_tag):
                if not _is_safe_git_tag(candidate_tag):
                    continue
                if default_branch:
                    co_branch = subprocess.run(
                        [
                            "git",
                            *_GIT_SAFE_CONFIG_ARGS,
                            "checkout",
                            "-B",
                            default_branch,
                            candidate_tag,
                        ],
                        cwd=lib_path,
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=120,
                        env=_git_env(),
                    )
                    if co_branch.returncode == 0:
                        subprocess.run(
                            [
                                "git",
                                "branch",
                                f"--set-upstream-to=origin/{default_branch}",
                                default_branch,
                            ],
                            cwd=lib_path,
                            capture_output=True,
                            text=True,
                            check=False,
                            timeout=30,
                            env=_git_env(),
                        )
                        return True

                co_res = subprocess.run(
                    ["git", *_GIT_SAFE_CONFIG_ARGS, "checkout", candidate_tag],
                    cwd=lib_path,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=120,
                    env=_git_env(),
                )
                if co_res.returncode == 0:
                    return True

        # Fallback to git pull (ensuring HEAD is attached to default_branch)
        if default_branch:
            subprocess.run(
                ["git", *_GIT_SAFE_CONFIG_ARGS, "checkout", default_branch],
                cwd=lib_path,
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
                env=_git_env(),
            )
            subprocess.run(
                [
                    "git",
                    "branch",
                    f"--set-upstream-to=origin/{default_branch}",
                    default_branch,
                ],
                cwd=lib_path,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
                env=_git_env(),
            )
        pull_res = subprocess.run(
            ["git", *_GIT_SAFE_CONFIG_ARGS, "pull"],
            cwd=lib_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
            env=_git_env(),
        )
        return pull_res.returncode == 0
    except (subprocess.SubprocessError, OSError) as ex:
        print(
            f"Error updating git repository at {lib_path}: {ex}",
            file=sys.stderr,
        )
        return False


def _has_project_manifest(directory: str) -> bool:
    """Checks if directory contains a valid library or plugin manifest."""
    static_files = (
        "pyproject.toml",
        "composer.json",
        "pom.xml",
        "plugin.json",
        "ChangeLog",
        "ChangeLog.md",
    )
    for fname in static_files:
        if os.path.isfile(os.path.join(directory, fname)):
            return True
    if os.path.isfile(
        os.path.join(
            directory,
            "plugins",
            "google-ads-api-developer-assistant",
            "plugin.json",
        )
    ):
        return True
    if glob.glob(os.path.join(directory, "*.gemspec")):
        return True
    if glob.glob(os.path.join(directory, "**", "*.csproj"), recursive=True):
        return True
    return False


def _resolve_sync_source_dir(extracted_root: str, target_lib_path: str) -> str:
    """Maps nested plugin dir when syncing into a standalone plugin dir."""
    nested_plugin = os.path.join(
        extracted_root, "plugins", "google-ads-api-developer-assistant"
    )
    is_standalone_plugin_target = (
        os.path.isfile(os.path.join(target_lib_path, "plugin.json"))
        or os.path.isfile(os.path.join(target_lib_path, "plugin.json.disabled"))
    ) and not os.path.isdir(
        os.path.join(
            target_lib_path, "plugins", "google-ads-api-developer-assistant"
        )
    )
    if is_standalone_plugin_target and os.path.isdir(nested_plugin):
        return nested_plugin
    return extracted_root


def _safe_extract_tar(tar: tarfile.TarFile, extract_dir: str) -> None:
    """Validates tar members against traversal, links, and devices."""
    real_extract = os.path.realpath(extract_dir)
    prefix = real_extract + os.sep
    members = tar.getmembers()
    for member in members:
        member_dest = os.path.realpath(os.path.join(extract_dir, member.name))
        if member_dest != real_extract and not member_dest.startswith(prefix):
            raise ValueError(
                "Unsafe tar member path outside extract directory:"
                f" {member.name}"
            )
        if member.isdev():
            raise ValueError(f"Unsafe device file in archive: {member.name}")
        if member.issym() or member.islnk():
            link_base = (
                os.path.dirname(os.path.join(extract_dir, member.name))
                if member.issym()
                else extract_dir
            )
            link_target = os.path.realpath(
                os.path.join(link_base, member.linkname)
            )
            if link_target != real_extract and not link_target.startswith(
                prefix
            ):
                raise ValueError(
                    f"Unsafe link target in archive: {member.name} -> "
                    f"{member.linkname}"
                )
    try:
        tar.extractall(extract_dir, members=members, filter="data")
    except TypeError:
        tar.extractall(extract_dir, members=members)


def _write_sync_version_marker(lib_path: str, tag: str) -> None:
    """Writes the synced release version marker file."""
    clean_ver = tag.strip().lstrip("vV")
    if clean_ver:
        try:
            with open(
                os.path.join(lib_path, ".sync_version"), "w", encoding="utf-8"
            ) as f:
                f.write(f"{clean_ver}\n")
        except OSError:
            pass


def update_codebase_via_archive(
    lib_path: str, repo_slug: str, tag: str, tarball_url: Optional[str]
) -> bool:
    """Downloads release tarball or clones repo to update non-git codebase."""
    if not _SAFE_SLUG_RE.fullmatch(repo_slug):
        print(f"Error: Invalid repository slug '{repo_slug}'.", file=sys.stderr)
        return False
    if tag and not _is_safe_git_tag(tag):
        print(f"Error: Unsafe release tag '{tag}'.", file=sys.stderr)
        return False

    temp_dir = tempfile.mkdtemp(prefix="client_lib_update_")
    try:
        # 1. Try git clone shallow tag first if git is available and tag given
        if tag:
            clone_dir = os.path.join(temp_dir, "clone")
            clone_tag = tag if tag.startswith("v") else f"v{tag}"
            remote_url = f"https://github.com/{repo_slug}.git"
            clone_res = subprocess.run(
                [
                    "git",
                    *_GIT_SAFE_CONFIG_ARGS,
                    "clone",
                    "--depth",
                    "1",
                    "--branch",
                    tag,
                    remote_url,
                    clone_dir,
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
                env=_git_env(),
            )
            if clone_res.returncode != 0 and clone_tag != tag:
                shutil.rmtree(clone_dir, ignore_errors=True)
                clone_res = subprocess.run(
                    [
                        "git",
                        *_GIT_SAFE_CONFIG_ARGS,
                        "clone",
                        "--depth",
                        "1",
                        "--branch",
                        clone_tag,
                        remote_url,
                        clone_dir,
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=120,
                    env=_git_env(),
                )

            if clone_res.returncode == 0 and _has_project_manifest(clone_dir):
                sync_src = _resolve_sync_source_dir(clone_dir, lib_path)
                ok = sync_directories(sync_src, lib_path)
                if ok:
                    _write_sync_version_marker(lib_path, tag)
                return ok

        # 2. Try tarball extraction (validate HTTPS URL and trusted GitHub host first)
        archive_url = (
            tarball_url
            or f"https://github.com/{repo_slug}/archive/refs/tags/{tag}.tar.gz"
        )
        parsed_url = urllib.parse.urlparse(archive_url)
        allowed_archive_hosts = frozenset(
            {"github.com", "api.github.com", "codeload.github.com"}
        )
        if (
            parsed_url.scheme != "https"
            or parsed_url.netloc.lower() not in allowed_archive_hosts
        ):
            print(
                f"Error: Refusing untrusted or non-HTTPS archive URL '{archive_url}'. "
                "Only GitHub archive hosts (github.com, api.github.com, codeload.github.com) are permitted.",
                file=sys.stderr,
            )
            return False

        req_headers = {"User-Agent": "google-ads-api-developer-assistant"}
        if parsed_url.netloc.lower() in _GITHUB_AUTH_HOSTS:
            token = (
                os.environ.get("GITHUB_TOKEN")
                or os.environ.get("GH_TOKEN")
                or ""
            ).strip()
            if token:
                req_headers["Authorization"] = f"Bearer {token}"

        tar_dest = os.path.join(temp_dir, "release.tar.gz")
        req = urllib.request.Request(archive_url, headers=req_headers)
        with urllib.request.urlopen(req, timeout=30) as resp, open(
            tar_dest, "wb"
        ) as out_f:
            shutil.copyfileobj(resp, out_f)

        extract_dir = os.path.join(temp_dir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        with tarfile.open(tar_dest, "r:gz") as tar:
            _safe_extract_tar(tar, extract_dir)

        extracted_items = os.listdir(extract_dir)
        if len(extracted_items) == 1 and os.path.isdir(
            os.path.join(extract_dir, extracted_items[0])
        ):
            source_content_dir = os.path.join(extract_dir, extracted_items[0])
        else:
            source_content_dir = extract_dir

        sync_src = _resolve_sync_source_dir(source_content_dir, lib_path)
        ok = sync_directories(sync_src, lib_path)
        if ok and tag:
            _write_sync_version_marker(lib_path, tag)
        return ok

    except (
        subprocess.SubprocessError,
        urllib.error.URLError,
        tarfile.TarError,
        shutil.Error,
        OSError,
        ValueError,
    ) as ex:
        print(f"Error updating codebase {repo_slug}: {ex}", file=sys.stderr)
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


_SYNC_PRESERVED_TOP_LEVEL = frozenset({
    ".git",
    "google-ads.yaml",
    "config.yaml",
    "saved",
    "client_libs",
})


def _validate_source_tree_symlinks(
    source_dir: str, skip_top_level: frozenset[str]
) -> None:
    """Rejects any symlink in source_dir whose resolved target escapes it."""
    real_source = os.path.realpath(source_dir)
    for root, dirs, files in os.walk(
        source_dir, topdown=True, followlinks=False
    ):
        if root == source_dir:
            dirs[:] = [d for d in dirs if d not in skip_top_level]
            candidate_names = [
                *dirs,
                *(f for f in files if f not in skip_top_level),
            ]
        else:
            candidate_names = [*dirs, *files]

        real_root = os.path.realpath(root)
        for name in candidate_names:
            full_path = os.path.join(root, name)
            if not os.path.islink(full_path):
                continue
            link_target = os.readlink(full_path)
            resolved_target = os.path.realpath(
                os.path.join(real_root, link_target)
            )
            try:
                within = (
                    os.path.commonpath([real_source, resolved_target])
                    == real_source
                )
            except ValueError:
                within = False
            if not within:
                raise ValueError(
                    "Unsafe symlink target escaping source directory: "
                    f"{full_path} -> {link_target}"
                )


def _copy_symlink_safe(
    src_link: str,
    dst_link: str,
    visited_real_dirs: Optional[frozenset[str]] = None,
) -> None:
    """Copies a validated symlink, falling back on Windows WinError 1314."""
    link_target = os.readlink(src_link)
    try:
        os.symlink(link_target, dst_link)
    except OSError as ex:
        if getattr(ex, "winerror", None) != 1314:
            raise
        # Windows without Developer Mode / symlink privilege: copy the
        # already-validated in-tree target contents instead.
        resolved_target = os.path.realpath(src_link)
        seen = visited_real_dirs or frozenset()
        if os.path.isdir(resolved_target):
            if resolved_target in seen:
                return
            _copy_tree_safe(
                resolved_target,
                dst_link,
                visited_real_dirs=seen | {resolved_target},
            )
        elif os.path.isfile(resolved_target):
            shutil.copy2(resolved_target, dst_link)


def _copy_tree_safe(
    src_dir: str,
    dst_dir: str,
    visited_real_dirs: Optional[frozenset[str]] = None,
) -> None:
    """Recursively copies src_dir to dst_dir with safe symlink handling."""
    real_src = os.path.realpath(src_dir)
    seen = (visited_real_dirs or frozenset()) | {real_src}
    os.makedirs(dst_dir, exist_ok=True)
    for entry in os.listdir(src_dir):
        src_entry = os.path.join(src_dir, entry)
        dst_entry = os.path.join(dst_dir, entry)
        if os.path.islink(src_entry):
            _copy_symlink_safe(src_entry, dst_entry, visited_real_dirs=seen)
        elif os.path.isdir(src_entry):
            _copy_tree_safe(src_entry, dst_entry, visited_real_dirs=seen)
        else:
            shutil.copy2(src_entry, dst_entry)
    try:
        shutil.copystat(src_dir, dst_dir)
    except OSError:
        pass


def sync_directories(source_dir: str, target_dir: str) -> bool:
    """Cleanly synchronizes content from source_dir into target_dir."""
    preserved_plugin_configs: dict[str, bytes] = {}
    cfg_subdir = os.path.join(target_dir, "config")
    stage_dir: Optional[str] = None
    stage_name: Optional[str] = None
    target_modified = False
    try:
        if not os.path.isdir(source_dir):
            raise FileNotFoundError(
                f"Source directory does not exist: {source_dir}"
            )
        os.makedirs(target_dir, exist_ok=True)
        if os.path.realpath(source_dir) == os.path.realpath(target_dir):
            return True

        # Validate all symlinks in source_dir before mutating target_dir.
        _validate_source_tree_symlinks(source_dir, _SYNC_PRESERVED_TOP_LEVEL)

        # Preserve user config files if syncing an installed standalone plugin
        if os.path.isdir(cfg_subdir):
            for cfg_fname in (
                "google-ads.yaml",
                "assistant_config",
                "financial_limits",
            ):
                cfg_fpath = os.path.join(cfg_subdir, cfg_fname)
                if os.path.isfile(cfg_fpath):
                    try:
                        with open(cfg_fpath, "rb") as pf:
                            preserved_plugin_configs[cfg_fname] = pf.read()
                    except OSError:
                        pass

        # Stage copy into a sibling temp dir (fallback inside target_dir) so
        # copy failures never destroy existing files or credentials.
        parent_dir = os.path.dirname(os.path.abspath(target_dir))
        try:
            stage_dir = tempfile.mkdtemp(prefix=".sync_stage_", dir=parent_dir)
        except OSError:
            stage_dir = tempfile.mkdtemp(prefix=".sync_stage_", dir=target_dir)
            stage_name = os.path.basename(stage_dir)

        for item in os.listdir(source_dir):
            if item in _SYNC_PRESERVED_TOP_LEVEL:
                continue
            src_item = os.path.join(source_dir, item)
            staged_item = os.path.join(stage_dir, item)
            if os.path.islink(src_item):
                _copy_symlink_safe(src_item, staged_item)
            elif os.path.isdir(src_item):
                _copy_tree_safe(src_item, staged_item)
            else:
                shutil.copy2(src_item, staged_item)

        # Remove existing contents except preserved top-level items
        target_modified = True
        for item in os.listdir(target_dir):
            if item in _SYNC_PRESERVED_TOP_LEVEL or item == stage_name:
                continue
            item_path = os.path.join(target_dir, item)
            if os.path.islink(item_path) or os.path.isfile(item_path):
                os.unlink(item_path)
            elif os.path.isdir(item_path):
                shutil.rmtree(item_path)

        for item in os.listdir(stage_dir):
            shutil.move(
                os.path.join(stage_dir, item),
                os.path.join(target_dir, item),
            )

        return True
    except (shutil.Error, OSError, ValueError) as ex:
        print(
            f"Failed to copy files from {source_dir} to {target_dir}: {ex}",
            file=sys.stderr,
        )
        return False
    finally:
        if preserved_plugin_configs and target_modified:
            try:
                os.makedirs(cfg_subdir, exist_ok=True)
            except OSError:
                pass
            for cfg_fname, raw_bytes in preserved_plugin_configs.items():
                restored_path = os.path.join(cfg_subdir, cfg_fname)
                try:
                    with open(restored_path, "wb") as rf:
                        rf.write(raw_bytes)
                    if (
                        cfg_fname in ("google-ads.yaml", "financial_limits")
                        and sys.platform != "win32"
                    ):
                        try:
                            os.chmod(restored_path, 0o600)
                        except OSError:
                            pass
                except OSError:
                    pass
        if stage_dir and os.path.exists(stage_dir):
            shutil.rmtree(stage_dir, ignore_errors=True)


def detect_lib_api_version(lib_path: str) -> Optional[str]:
    """Detects highest v<N> API version dir in a google-ads-python codebase."""
    python_root = os.path.join(lib_path, "google/ads/googleads")
    if not os.path.isdir(python_root):
        return None
    try:
        v_dirs = [
            d
            for d in os.listdir(python_root)
            if os.path.isdir(os.path.join(python_root, d))
            and re.fullmatch(r"v\d+", d)
        ]
        if not v_dirs:
            return None
        v_dirs.sort(key=lambda x: int(x[1:]))
        return v_dirs[-1]
    except OSError:
        return None


def _is_git_tracked_plugin_config_dir(cfg_dir: str) -> bool:
    """Returns True if cfg_dir is a git-tracked plugin config directory."""
    abs_cfg = os.path.abspath(cfg_dir)
    plugin_dir = os.path.dirname(abs_cfg)
    plugins_parent = os.path.dirname(plugin_dir)
    repo_root = os.path.dirname(plugins_parent)
    return (
        os.path.basename(abs_cfg) == "config"
        and os.path.basename(plugin_dir) == "google-ads-api-developer-assistant"
        and os.path.basename(plugins_parent) == "plugins"
        and os.path.isdir(os.path.join(repo_root, ".git"))
    )


def _strip_toml_comment_outside_quotes(raw: str) -> str:
    """Strips inline '#' comments outside single- or double-quoted strings."""
    in_quote: Optional[str] = None
    escaped = False
    for idx, ch in enumerate(raw):
        if in_quote == '"':
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_quote = None
        elif in_quote == "'":
            if ch == "'":
                in_quote = None
        else:
            if ch in ('"', "'"):
                in_quote = ch
            elif ch == "#":
                return raw[:idx].rstrip()
    return raw.rstrip()


def _parse_fallback_toml_value(raw_rhs: str) -> tuple[bool, Any]:
    """Parses a single-line TOML value for malformed-config recovery."""
    rhs = raw_rhs.strip()
    if not rhs or rhs.startswith(('"""', "'''")):
        return False, None

    cleaned = _strip_toml_comment_outside_quotes(rhs).strip()
    if not cleaned:
        return False, None

    # Use tomllib on the individual assignment so quoted strings (including
    # "true"/"false" and "#..." inside quotes), ints, floats, bools, and valid
    # single-line arrays/inline tables keep exact TOML types.
    try:
        parsed = tomllib.loads(f"v = {cleaned}\n")
        if "v" in parsed:
            return True, parsed["v"]
    except tomllib.TOMLDecodeError:
        pass

    # Skip unclosed/malformed multiline openers or broken quoted strings.
    if cleaned[0] in ("[", "{", '"', "'"):
        return False, None

    # Legacy bareword fallback (e.g. unquoted strings or mixed-case booleans).
    low = cleaned.lower()
    if low in ("true", "false"):
        return True, low == "true"
    try:
        return True, int(cleaned, 10)
    except ValueError:
        pass
    try:
        f_val = float(cleaned)
        if math.isfinite(f_val):
            return True, f_val
    except ValueError:
        pass
    return True, cleaned


def _parse_assistant_config_fallback(
    existing_text: str,
) -> tuple[str, str, Optional[str], dict[str, Any]]:
    """Recovers top-level assistant_config keys when full TOML parsing fails."""
    cid = "12345678"
    exec_mutates_str = "false"
    enabled_str: Optional[str] = None
    extra_toml: dict[str, Any] = {}

    lines = existing_text.splitlines()
    idx = 0
    while idx < len(lines):
        raw_line = lines[idx]
        idx += 1
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Stop top-level flag/key matching at the first [section] header.
        if stripped.startswith("["):
            break

        m_kv = re.match(r"^\s*([A-Za-z0-9_-]+)\s*=\s*(.*)$", raw_line)
        if not m_kv:
            continue
        k_name, raw_rhs = m_kv.group(1), m_kv.group(2).strip()
        if not raw_rhs:
            continue

        # Skip multiline triple-quoted string openers (and any closed body).
        if raw_rhs.startswith(('"""', "'''")):
            delim = raw_rhs[:3]
            if delim not in raw_rhs[3:]:
                close_idx = next(
                    (j for j in range(idx, len(lines)) if delim in lines[j]),
                    None,
                )
                if close_idx is not None:
                    idx = close_idx + 1
            continue

        ok, val = _parse_fallback_toml_value(raw_rhs)
        if not ok:
            # If an unclosed inline table `{` has a closing `}` later, skip it.
            if raw_rhs.startswith("{"):
                close_idx = next(
                    (
                        j
                        for j in range(idx, len(lines))
                        if "}" in _strip_toml_comment_outside_quotes(lines[j])
                    ),
                    None,
                )
                if close_idx is not None:
                    idx = close_idx + 1
            continue

        if k_name == "api_version":
            continue
        if k_name == "customer_id":
            cid_str = str(val).strip()
            if cid_str:
                cid = cid_str
        elif k_name == "execute_mutates":
            if isinstance(val, bool):
                exec_mutates_str = "true" if val else "false"
        elif k_name == "enabled":
            if isinstance(val, bool):
                enabled_str = "true" if val else "false"
        elif k_name not in extra_toml:
            extra_toml[k_name] = val

    return cid, exec_mutates_str, enabled_str, extra_toml


def _format_toml_key(key: str) -> str:
    """Formats a TOML key segment as bare when valid, else quoted."""
    if re.fullmatch(r"[A-Za-z0-9_-]+", key):
        return key
    return json.dumps(key)


def _format_toml_value(val: Any) -> Optional[str]:
    """Formats a Python value as a valid TOML inline value."""
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, int):
        return str(val)
    if isinstance(val, float):
        return str(val)
    if isinstance(val, str):
        return json.dumps(val)
    if isinstance(val, (datetime.datetime, datetime.date, datetime.time)):
        return val.isoformat()
    if isinstance(val, list):
        formatted_items: list[str] = []
        for item in val:
            fmt_item = _format_toml_value(item)
            if fmt_item is None:
                return None
            formatted_items.append(fmt_item)
        return "[" + ", ".join(formatted_items) + "]"
    if isinstance(val, dict):
        parts: list[str] = []
        for dk, dv in val.items():
            fmt_dv = _format_toml_value(dv)
            if fmt_dv is None:
                return None
            parts.append(f"{_format_toml_key(str(dk))} = {fmt_dv}")
        return "{" + ", ".join(parts) + "}"
    if val is None:
        return None
    return json.dumps(str(val))


def _serialize_toml_table(
    section_path: list[str], table: dict[str, Any]
) -> list[str]:
    """Serializes a TOML table dict into [section] header + key/value lines."""
    lines: list[str] = []
    scalar_items: list[tuple[str, Any]] = []
    nested_tables: list[tuple[str, dict[str, Any]]] = []
    for k, v in table.items():
        if isinstance(v, dict):
            nested_tables.append((str(k), v))
        elif v is not None:
            scalar_items.append((str(k), v))

    header = ".".join(_format_toml_key(seg) for seg in section_path)
    if scalar_items or not nested_tables:
        lines.append(f"\n[{header}]\n")
        for sk, sv in scalar_items:
            fmt_v = _format_toml_value(sv)
            if fmt_v is not None:
                lines.append(f"{_format_toml_key(sk)} = {fmt_v}\n")

    for sub_k, sub_tbl in nested_tables:
        lines.extend(_serialize_toml_table([*section_path, sub_k], sub_tbl))
    return lines


def update_api_version_cache_if_needed(lib_path: str) -> Optional[str]:
    """Refreshes api_version in config/assistant_config from lib_path."""
    latest_v = detect_lib_api_version(lib_path)
    if not latest_v:
        return None

    try:
        global_cfg_dirs = [
            os.path.expanduser(
                "~/.gemini/config/plugins/"
                "google-ads-api-developer-assistant/config"
            ),
            os.path.expanduser(
                "~/.claude/plugins/google-ads-assistant-local/plugins/"
                "google-ads-api-developer-assistant/config"
            ),
        ]
        has_global_cfg = any(os.path.isdir(d) for d in global_cfg_dirs)

        raw_targets = [
            os.path.abspath("config/assistant_config"),
            os.path.abspath(
                os.path.join(lib_path, "../../config/assistant_config")
            ),
            os.path.abspath(
                os.path.join(lib_path, "../../../config/assistant_config")
            ),
            os.path.abspath(
                os.path.join(lib_path, "../../../../config/assistant_config")
            ),
        ]
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            for gdir in global_cfg_dirs:
                if os.path.isdir(gdir):
                    raw_targets.append(os.path.join(gdir, "assistant_config"))

        config_targets: list[str] = []
        for t in raw_targets:
            norm_t = os.path.normpath(t)
            if norm_t not in config_targets:
                config_targets.append(norm_t)

        for cfg_path in config_targets:
            cfg_dir = os.path.dirname(cfg_path)
            if not os.path.isdir(cfg_dir):
                continue
            # Avoid dirtying git-tracked plugins/.../config/assistant_config
            # when global plugin dirs exist.
            if has_global_cfg and _is_git_tracked_plugin_config_dir(cfg_dir):
                continue

            cid = "12345678"
            exec_mutates_str = "false"
            enabled_str: Optional[str] = None
            extra_toml: dict[str, Any] = {}
            existing_text = ""
            if os.path.isfile(cfg_path):
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        existing_text = f.read()
                    try:
                        loaded_cfg = tomllib.loads(existing_text)
                        if isinstance(loaded_cfg, dict):
                            for k, v in loaded_cfg.items():
                                if k == "customer_id" and str(v).strip():
                                    cid = str(v).strip()
                                elif k == "execute_mutates" and isinstance(
                                    v, bool
                                ):
                                    exec_mutates_str = (
                                        "true" if v else "false"
                                    )
                                elif k == "enabled" and isinstance(v, bool):
                                    enabled_str = "true" if v else "false"
                                elif k not in (
                                    "api_version",
                                    "customer_id",
                                    "execute_mutates",
                                    "enabled",
                                ):
                                    extra_toml[k] = v
                    except tomllib.TOMLDecodeError:
                        (
                            cid,
                            exec_mutates_str,
                            enabled_str,
                            extra_toml,
                        ) = _parse_assistant_config_fallback(existing_text)
                except OSError:
                    pass
            content_out = (
                f'api_version = "{latest_v}"\n'
                f"customer_id = {json.dumps(cid)}\n"
                f"execute_mutates = {exec_mutates_str}\n"
            )
            if enabled_str is not None:
                content_out += f"enabled = {enabled_str}\n"
            nested_tables: list[tuple[str, dict[str, Any]]] = []
            for k, v in extra_toml.items():
                k_str = str(k)
                if isinstance(v, dict):
                    nested_tables.append((k_str, v))
                    continue
                fmt_v = _format_toml_value(v)
                if fmt_v is not None:
                    content_out += f"{_format_toml_key(k_str)} = {fmt_v}\n"
            for tbl_name, tbl_val in nested_tables:
                content_out += "".join(
                    _serialize_toml_table([tbl_name], tbl_val)
                )
            if content_out != existing_text or not os.path.isfile(cfg_path):
                if os.path.islink(cfg_path):
                    continue
                tmp_fd, tmp_path = tempfile.mkstemp(
                    prefix=".assistant_config_", suffix=".tmp", dir=cfg_dir
                )
                try:
                    with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                        f.write(content_out)
                    if sys.platform != "win32":
                        try:
                            os.chmod(tmp_path, 0o600)
                        except OSError:
                            pass
                    os.replace(tmp_path, cfg_path)
                except OSError:
                    if os.path.exists(tmp_path):
                        try:
                            os.remove(tmp_path)
                        except OSError:
                            pass
                    raise
            if sys.platform != "win32" and os.path.isfile(cfg_path):
                try:
                    os.chmod(cfg_path, 0o600)
                except OSError:
                    pass
            legacy_ver_txt = os.path.join(cfg_dir, "api_version.txt")
            if os.path.isfile(legacy_ver_txt):
                try:
                    with open(legacy_ver_txt, "w", encoding="utf-8") as lf:
                        lf.write(f"{latest_v}\n")
                except OSError:
                    pass

        return latest_v
    except (OSError, ValueError):
        return None


def detect_system_package_version(
    package_name: str = "google-ads",
) -> tuple[Optional[str], list[str]]:
    """Detects the installed package version in Python site-packages.

    Args:
        package_name: Distribution package name to inspect.

    Returns:
        Tuple of `(installed_version, site_directories)`.
    """
    site_dirs: list[str] = []
    try:
        if hasattr(site, "getsitepackages"):
            site_dirs.extend(site.getsitepackages())
        if hasattr(site, "getusersitepackages"):
            site_dirs.append(site.getusersitepackages())
    except (OSError, AttributeError, ValueError):
        pass

    # Try importlib.metadata
    try:
        v = importlib.metadata.version(package_name)
        return v.strip(), site_dirs
    except (importlib.metadata.PackageNotFoundError, OSError, ValueError):
        pass

    # Fallback to pip show (parse ALL lines so Location: after Version: is kept)
    try:
        res = subprocess.run(
            [sys.executable, "-m", "pip", "show", package_name],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
            env=_pip_env(),
        )
        if res.returncode == 0:
            detected_ver: Optional[str] = None
            for line in res.stdout.splitlines():
                if line.startswith("Version:"):
                    detected_ver = line.split(":", 1)[1].strip()
                elif line.startswith("Location:"):
                    loc = line.split(":", 1)[1].strip()
                    if loc and loc not in site_dirs:
                        site_dirs.append(loc)
            if detected_ver:
                return detected_ver, site_dirs
    except (subprocess.SubprocessError, OSError, ValueError):
        pass

    return None, site_dirs


def fetch_latest_pypi_python_version(
    package_name: str = "google-ads",
    ttl_seconds: int = 3600,
    force: bool = False,
) -> Optional[str]:
    """Fetches and caches the latest release version of a package from PyPI."""
    safe_pkg = re.sub(r"[^A-Za-z0-9_.-]", "_", package_name)
    temp_dir = tempfile.gettempdir()
    is_shared_tmp = os.path.normpath(temp_dir) in (
        "/tmp",
        "/var/tmp",
        "/usr/tmp",
    )
    if not is_shared_tmp:
        try:
            is_shared_tmp = bool(os.stat(temp_dir).st_mode & 0o1000)
        except OSError:
            is_shared_tmp = True
    uid_suffix = (
        f"_{os.getuid()}" if (is_shared_tmp and hasattr(os, "getuid")) else ""
    )
    cache_file = os.path.join(
        temp_dir,
        f"gads_assistant_pypi_{safe_pkg.replace('-', '_')}_release{uid_suffix}.json",
    )
    now = time.time()
    if (
        not force
        and os.path.isfile(cache_file)
        and not os.path.islink(cache_file)
    ):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
            ts = float(cached.get("timestamp", 0.0))
            ver = str(cached.get("pypi_version") or "").strip().lstrip("v")
            if ver and 0 <= (now - ts) < ttl_seconds:
                return ver
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            AttributeError,
            TypeError,
            ValueError,
        ):
            pass

    url = f"https://pypi.org/pypi/{safe_pkg}/json"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "google-ads-api-developer-assistant",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        ver = str(data.get("info", {}).get("version") or "").strip().lstrip("v")
        if ver:
            try:
                flags = (
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_TRUNC
                    | getattr(os, "O_NOFOLLOW", 0)
                )
                fd = os.open(cache_file, flags, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump({"timestamp": now, "pypi_version": ver}, f)
            except OSError:
                pass
            return ver
    except (
        urllib.error.URLError,
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        AttributeError,
        TypeError,
        ValueError,
    ):
        pass
    return None


def check_system_package_parity(
    package_name: str = "google-ads",
    target_version: Optional[str] = None,
) -> dict[str, Any]:
    """Checks installed package version in site-packages vs target version."""
    system_version, site_dirs = detect_system_package_version(package_name)
    matches = False
    if system_version and target_version:
        clean_sys = system_version.lstrip("v").strip()
        clean_tgt = target_version.lstrip("v").strip()
        matches = clean_sys == clean_tgt
    return {
        "package_name": package_name,
        "system_version": system_version,
        "target_version": target_version,
        "matches": matches,
        "site_directories": site_dirs,
    }


def _is_verified_googleads_python_checkout(lib_path: str) -> bool:
    """Returns True only when lib_path is a git checkout with origin under https://github.com/googleads/."""
    if (
        not lib_path
        or not os.path.isdir(lib_path)
        or not os.path.isfile(os.path.join(lib_path, "pyproject.toml"))
    ):
        return False
    git_cfg = os.path.join(lib_path, ".git", "config")
    if not os.path.isfile(git_cfg):
        return False
    try:
        with open(git_cfg, "r", encoding="utf-8", errors="ignore") as f:
            in_origin = False
            for raw in f:
                line = raw.strip()
                if line.startswith("[") and line.endswith("]"):
                    in_origin = line.lower() in (
                        '[remote "origin"]',
                        "[remote 'origin']",
                    )
                    continue
                if in_origin and line.lower().startswith("url"):
                    _, _, rhs = line.partition("=")
                    origin_url = rhs.strip()
                    if origin_url.startswith("https://github.com/googleads/"):
                        return True
    except OSError:
        return False
    return False


def upgrade_system_package(
    package_name: str = "google-ads",
    target_version: Optional[str] = None,
    lib_path: Optional[str] = None,
) -> bool:
    """Upgrades package from PyPI (or local lib_path) in site-packages."""
    if target_version and not _is_safe_git_tag(target_version):
        print(
            f"Error: Invalid target package version '{target_version}'.",
            file=sys.stderr,
        )
        return False

    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--index-url",
        "https://pypi.org/simple",
    ]
    if target_version:
        cmd.append(f"{package_name}=={target_version.lstrip('v')}")
    else:
        cmd.append(package_name)
    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=180,
            env=_pip_env(),
        )
        ok = res.returncode == 0
        combined_out = (
            f"{getattr(res, 'stderr', '') or ''}\n"
            f"{getattr(res, 'stdout', '') or ''}"
        )
        last_err = getattr(res, "stderr", "") or getattr(res, "stdout", "")
        py_ver_mismatch = (
            "require a different python version" in combined_out.lower()
        )
        if not ok and py_ver_mismatch:
            py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
            print(
                f"WARNING: No {package_name} release on PyPI declares support "
                f"for Python {py_ver}; retrying pip install with "
                "--ignore-requires-python.",
                file=sys.stderr,
            )
            retry_res = subprocess.run(
                [*cmd, "--ignore-requires-python"],
                capture_output=True,
                text=True,
                check=False,
                timeout=180,
                env=_pip_env(),
            )
            ok = retry_res.returncode == 0
            if not ok:
                last_err = (
                    getattr(retry_res, "stderr", "")
                    or getattr(retry_res, "stdout", "")
                    or last_err
                )
        if not ok and lib_path and _is_verified_googleads_python_checkout(lib_path):
            local_res = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", lib_path],
                capture_output=True,
                text=True,
                check=False,
                timeout=180,
                env=_pip_env(),
            )
            ok = local_res.returncode == 0
            if not ok:
                last_err = (
                    getattr(local_res, "stderr", "")
                    or getattr(local_res, "stdout", "")
                    or last_err
                )
        if not ok and last_err:
            print(
                f"ERROR: pip upgrade failed for {package_name}: "
                f"{str(last_err).strip()}",
                file=sys.stderr,
            )
        return ok
    except (subprocess.SubprocessError, OSError, ValueError) as ex:
        print(f"Error upgrading {package_name}: {ex}", file=sys.stderr)
        return False


def _has_assistant_manifest(directory: str) -> bool:
    """Returns True if directory contains an assistant plugin manifest."""
    for rel in (
        "plugin.json",
        "plugin.json.disabled",
        "plugins/google-ads-api-developer-assistant/plugin.json",
        "plugins/google-ads-api-developer-assistant/plugin.json.disabled",
    ):
        if os.path.isfile(os.path.join(directory, rel)):
            return True
    return False


def check_assistant_repo(
    check_only: bool = False,
    force: bool = False,
) -> Optional[dict[str, Any]]:
    """Checks and updates the google-ads-api-developer-assistant repository."""
    script_dir: str = os.path.dirname(os.path.abspath(__file__))
    project_root: Optional[str] = None
    git_toplevel: Optional[str] = None

    # 1. Resolve enclosing git repository root via git rev-parse first
    try:
        top_res = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=script_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
            env=_git_env(),
        )
        if top_res.returncode == 0 and top_res.stdout.strip():
            cand_top = os.path.abspath(top_res.stdout.strip())
            if _has_assistant_manifest(cand_top):
                project_root = cand_top
                git_toplevel = cand_top
    except (subprocess.SubprocessError, OSError):
        pass

    # 2. Check git repo root candidates FIRST so <repo>/.git is selected over
    # nested <repo>/plugins/...
    repo_first_candidates = [
        os.path.abspath(os.path.join(script_dir, "../../../../..")),
        os.path.abspath(os.path.join(script_dir, "../../../..")),
        os.path.abspath(os.path.join(script_dir, "../../..")),
    ]
    if not project_root:
        for c in repo_first_candidates:
            if os.path.exists(
                os.path.join(c, ".git")
            ) and _has_assistant_manifest(c):
                project_root = c
                break

    # 3. Fallback to standalone installed plugin directory (no .git repository)
    if not project_root:
        for c in reversed(repo_first_candidates):
            if _has_assistant_manifest(c):
                project_root = c
                break

    if not project_root:
        return None

    has_git_repo = bool(git_toplevel) or os.path.exists(
        os.path.join(project_root, ".git")
    )

    repo_slug = "googleads/google-ads-api-developer-assistant"
    installed_version = None

    # Read version from plugin.json / plugin.json.disabled
    for p_json in [
        os.path.join(
            project_root,
            "plugins/google-ads-api-developer-assistant/plugin.json",
        ),
        os.path.join(
            project_root,
            "plugins/google-ads-api-developer-assistant/plugin.json.disabled",
        ),
        os.path.join(project_root, "plugin.json"),
        os.path.join(project_root, "plugin.json.disabled"),
    ]:
        if os.path.isfile(p_json):
            try:
                with open(p_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    installed_version = data.get("version")
                    if installed_version:
                        break
            except (
                OSError,
                UnicodeDecodeError,
                json.JSONDecodeError,
                AttributeError,
                TypeError,
                ValueError,
            ):
                pass

    if not installed_version and has_git_repo:
        try:
            res = subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0"],
                cwd=project_root,
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
                env=_git_env(),
            )
            tag = res.stdout.strip()
            if tag:
                installed_version = tag.lstrip("v")
        except (subprocess.SubprocessError, OSError):
            pass

    github_tag, _ = fetch_github_latest_release(repo_slug)
    github_version = github_tag.lstrip("v") if github_tag else None

    local_ahead_of_github = bool(
        installed_version
        and github_version
        and is_update_needed(github_version, installed_version)
    )
    needs_update = is_update_needed(installed_version, github_version) or (
        force and not local_ahead_of_github
    )
    status = "UP_TO_DATE"
    updated = False

    if needs_update and not check_only and has_git_repo:
        updated = update_codebase_via_git(project_root, github_tag or "")
        status = "UPDATED" if updated else "UPDATE_FAILED"
    elif needs_update and (check_only or not has_git_repo):
        status = "OUTDATED"

    return {
        "codebase": "google-ads-api-developer-assistant",
        "path": project_root,
        "repo_slug": repo_slug,
        "installed_version": installed_version,
        "github_version": github_version,
        "status": status,
        "updated": updated,
    }


def process_client_libs(
    client_libs_dir: str,
    check_only: bool = False,
    force: bool = False,
    target_library: Optional[str] = None,
    include_assistant: bool = True,
    upgrade_system: bool = False,
) -> list[dict[str, Any]]:
    """Discovers, verifies, and updates codebases in client_libs_dir."""
    target_library = _normalize_target_library(target_library)
    results: list[dict[str, Any]] = []

    # 1. Check Assistant repository if enabled and not filtering for a client
    #    lib
    if include_assistant and (
        not target_library
        or target_library == "google-ads-api-developer-assistant"
    ):
        assistant_res = check_assistant_repo(check_only=check_only, force=force)
        if assistant_res:
            results.append(assistant_res)

    if not os.path.isdir(client_libs_dir):
        return results

    entries = sorted(os.listdir(client_libs_dir))
    valid_libs: list[tuple[str, str, str]] = []
    for entry in entries:
        lib_path = os.path.join(client_libs_dir, entry)
        if not os.path.isdir(lib_path):
            continue
        if target_library and entry != target_library:
            continue
        repo_slug = get_repo_slug(entry, lib_path)
        valid_libs.append((entry, lib_path, repo_slug))

    # Prefetch GitHub release metadata concurrently when checking >1 library
    prefetched_releases: dict[str, tuple[Optional[str], Optional[str]]] = {}
    if len(valid_libs) > 1:
        unique_slugs = list(dict.fromkeys(slug for _, _, slug in valid_libs))
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(6, len(unique_slugs))
        ) as executor:
            future_to_slug = {
                executor.submit(fetch_github_latest_release, slug): slug
                for slug in unique_slugs
            }
            for future in concurrent.futures.as_completed(future_to_slug):
                slug = future_to_slug[future]
                try:
                    prefetched_releases[slug] = future.result()
                except (
                    concurrent.futures.CancelledError,
                    urllib.error.URLError,
                    subprocess.SubprocessError,
                    OSError,
                    RuntimeError,
                    ValueError,
                ):
                    prefetched_releases[slug] = (None, None)

    for entry, lib_path, repo_slug in valid_libs:
        installed_version = detect_installed_version(entry, lib_path)
        if repo_slug in prefetched_releases:
            github_tag, tarball_url = prefetched_releases[repo_slug]
        else:
            github_tag, tarball_url = fetch_github_latest_release(repo_slug)
        github_version = github_tag.lstrip("v") if github_tag else None

        needs_update = (
            is_update_needed(installed_version, github_version) or force
        )
        status = "UP_TO_DATE"
        updated = False

        if needs_update and not check_only:
            if os.path.isdir(os.path.join(lib_path, ".git")):
                updated = update_codebase_via_git(lib_path, github_tag or "")
            else:
                updated = update_codebase_via_archive(
                    lib_path, repo_slug, github_tag or "", tarball_url
                )

            if updated:
                status = "UPDATED"
                if entry == "google-ads-python":
                    update_api_version_cache_if_needed(lib_path)
                installed_version = (
                    detect_installed_version(entry, lib_path) or github_version
                )
            else:
                status = "UPDATE_FAILED"
        elif needs_update and check_only:
            status = "OUTDATED"
        elif not check_only and entry == "google-ads-python":
            update_api_version_cache_if_needed(lib_path)

        system_version: Optional[str] = None
        system_site_dirs: list[str] = []
        system_version_matches: Optional[bool] = None
        site_version_less_than_github: Optional[bool] = None
        site_version_less_than_pypi: Optional[bool] = None
        pypi_version: Optional[str] = None
        latest_api_version: Optional[str] = None
        system_upgrade_failed: bool = False

        if entry == "google-ads-python":
            sys_v, s_dirs = detect_system_package_version("google-ads")
            system_version = sys_v
            system_site_dirs = s_dirs
            ref_v = github_version or installed_version
            pypi_version = fetch_latest_pypi_python_version("google-ads")
            target_pypi_v = pypi_version or ref_v
            site_version_less_than_pypi = is_update_needed(sys_v, target_pypi_v)
            site_version_less_than_github = is_update_needed(sys_v, ref_v)
            if target_pypi_v and sys_v:
                system_version_matches = (
                    not site_version_less_than_pypi
                    and sys_v.lstrip("v").strip()
                    == target_pypi_v.lstrip("v").strip()
                )
            elif not sys_v:
                system_version_matches = False
            else:
                system_version_matches = True

            if (
                upgrade_system
                and (
                    not system_version_matches
                    or site_version_less_than_pypi
                    or force
                )
                and not check_only
            ):
                upgraded = upgrade_system_package(
                    "google-ads",
                    target_pypi_v,
                    lib_path=lib_path,
                )
                if upgraded:
                    sys_v, _ = detect_system_package_version("google-ads")
                    system_version = sys_v
                    site_version_less_than_pypi = is_update_needed(
                        sys_v, target_pypi_v
                    )
                    site_version_less_than_github = is_update_needed(
                        sys_v, ref_v
                    )
                    if target_pypi_v and sys_v:
                        system_version_matches = (
                            not site_version_less_than_pypi
                            and sys_v.lstrip("v").strip()
                            == target_pypi_v.lstrip("v").strip()
                        )
                else:
                    system_upgrade_failed = True
                    print(
                        "ERROR: Failed to upgrade system 'google-ads' package.",
                        file=sys.stderr,
                    )

            if not check_only:
                latest_api_version = update_api_version_cache_if_needed(
                    lib_path
                )
            else:
                latest_api_version = detect_lib_api_version(lib_path)

        res_item: dict[str, Any] = {
            "codebase": entry,
            "path": lib_path,
            "repo_slug": repo_slug,
            "installed_version": installed_version,
            "github_version": github_version,
            "status": status,
            "updated": updated,
        }
        if entry == "google-ads-python":
            res_item["system_version"] = system_version
            res_item["system_site_dirs"] = system_site_dirs
            res_item["system_version_matches"] = system_version_matches
            res_item["site_version_less_than_github"] = (
                site_version_less_than_github
            )
            res_item["pypi_version"] = pypi_version
            res_item["site_version_less_than_pypi"] = (
                site_version_less_than_pypi
            )
            if system_upgrade_failed:
                res_item["system_upgrade_failed"] = True
            if latest_api_version:
                res_item["api_version"] = latest_api_version

        results.append(res_item)

    return results


def print_table(results: list[dict[str, Any]]) -> None:
    """Formats and prints summary table of discovery and update results."""
    print("\nGoogle Ads Client Libraries Discovery & Sync Report")
    print("=" * 96)
    fmt = "{:<32} {:<26} {:<14} {:<14} {:<12}"
    print(
        fmt.format(
            "Codebase / Component",
            "Repository / Source",
            "Installed",
            "GitHub Release",
            "Status",
        )
    )
    print("-" * 96)
    for r in results:
        codebase = str(r.get("codebase", ""))
        repo = str(r.get("repo_slug", ""))
        inst = str(r.get("installed_version") or "UNKNOWN")
        gh = str(r.get("github_version") or "UNKNOWN")
        st = str(r.get("status", ""))
        print(fmt.format(codebase, repo, inst, gh, st))
        if codebase == "google-ads-python" and "system_version" in r:
            sys_v = str(r.get("system_version") or "NOT INSTALLED")
            pypi_v = str(
                r.get("pypi_version") or r.get("github_version") or "UNKNOWN"
            )
            is_outdated = r.get("site_version_less_than_pypi")
            if is_outdated is None:
                is_outdated = r.get("site_version_less_than_github")
            if r.get("system_upgrade_failed"):
                sys_st = "UPDATE_FAILED"
            elif r.get("system_version_matches"):
                sys_st = "UP_TO_DATE"
            elif is_outdated:
                sys_st = "OUTDATED"
            else:
                sys_st = "MISMATCH"
            print(
                fmt.format(
                    "google-ads (site-packages)",
                    "pypi.org/project/google-ads",
                    sys_v,
                    pypi_v,
                    sys_st,
                )
            )
            if r.get("api_version"):
                api_v = str(r.get("api_version"))
                print(
                    fmt.format(
                        "Google Ads API Version",
                        "Determined from (1) & (2)",
                        api_v,
                        api_v,
                        "ACTIVE",
                    )
                )
    print("=" * 96)

    for r in results:
        if r.get("codebase") == "google-ads-python" and "system_version" in r:
            sys_v = r.get("system_version")
            tgt_v = (
                r.get("pypi_version")
                or r.get("github_version")
                or r.get("installed_version")
            )
            dirs = r.get("system_site_dirs") or []
            primary_dir = dirs[0] if dirs else "system site-packages"
            api_ver = r.get("api_version")
            matches_flag = r.get("system_version_matches")
            if isinstance(matches_flag, bool) and not matches_flag:
                print("\n" + "!" * 80)
                print("ALERT: Python system site-directory version mismatch!")
                print("  Package: google-ads")
                print(
                    "  System site-directory version :"
                    f" {sys_v or 'NOT INSTALLED'}"
                )
                print(f"  Latest upstream release       : {tgt_v}")
                print(f"  Site directory path           : {primary_dir}")
                print(
                    "  Action: The assistant should alert the user and ask if they "
                    "would like to upgrade."
                )
                print("!" * 80)
            elif isinstance(matches_flag, bool) and matches_flag:
                api_suffix = (
                    f" (active api_version = {api_ver})" if api_ver else ""
                )
                print(
                    "\n[OK] System site-directory package 'google-ads' "
                    f"({sys_v} in {primary_dir}) matches upstream release "
                    f"({tgt_v}){api_suffix}."
                )


def main() -> None:
    """CLI entry point for discovery and updating client_libs."""
    parser = argparse.ArgumentParser(
        allow_abbrev=False,
        description=(
            "Automated discovery and update tool for Google Ads client "
            "libraries."
        ),
    )
    parser.add_argument(
        "--client_libs_dir",
        "-d",
        type=str,
        default=None,
        help="Path to the client_libs directory (default: auto-discover).",
    )
    parser.add_argument(
        "--check_only",
        "--dry_run",
        action="store_true",
        help="Check and report versions without updating codebases.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-syncing/updating codebases even if versions match.",
    )
    parser.add_argument(
        "--library",
        "-l",
        type=str,
        default=None,
        help=(
            "Target a specific codebase/library name "
            "(e.g. python, php, ruby, java, dotnet, all)."
        ),
    )
    parser.add_argument(
        "--upgrade_system",
        action="store_true",
        help=(
            "Upgrade google-ads in the Python system site-packages if "
            "mismatched."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON.",
    )

    args = parser.parse_args()

    try:
        target_dir = discover_client_libs_dir(args.client_libs_dir)
        results = process_client_libs(
            client_libs_dir=target_dir,
            check_only=args.check_only,
            force=args.force,
            target_library=_normalize_target_library(args.library),
            upgrade_system=args.upgrade_system,
        )

        if args.json:
            print(
                json.dumps(
                    {"client_libs_dir": target_dir, "results": results},
                    indent=2,
                )
            )
        else:
            print(f"Target client_libs directory: {target_dir}")
            print_table(results)

        has_failures = any(
            r.get("status") == "UPDATE_FAILED" or r.get("system_upgrade_failed")
            for r in results
        )
        if has_failures:
            sys.exit(1)

    except (
        OSError,
        RuntimeError,
        ValueError,
        subprocess.SubprocessError,
    ) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

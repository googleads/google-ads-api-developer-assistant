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
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from typing import Any, Optional

try:
    from packaging.version import Version, parse as parse_version
except ImportError:
    # Fallback lightweight version parser if packaging is not installed
    class VersionFallback:
        def __init__(self, v_str: str) -> None:
            self.raw: str = v_str
            clean: str = re.sub(r"^[^\d]*", "", v_str.strip())
            parts: list[int] = []
            for token in re.split(r"[.\-_+]", clean):
                digits = re.findall(r"\d+", token)
                if digits:
                    parts.append(int(digits[0]))
                else:
                    parts.append(0)
            self.parts: tuple[int, ...] = tuple(parts) if parts else (0,)

        def __lt__(self, other: "VersionFallback") -> bool:
            return self.parts < other.parts

        def __le__(self, other: "VersionFallback") -> bool:
            return self.parts <= other.parts

        def __gt__(self, other: "VersionFallback") -> bool:
            return self.parts > other.parts

        def __ge__(self, other: "VersionFallback") -> bool:
            return self.parts >= other.parts

        def __eq__(self, other: object) -> bool:
            if not isinstance(other, VersionFallback):
                return False
            return self.parts == other.parts

        def __str__(self) -> str:
            return self.raw

    def parse_version(v_str: str) -> Any:
        return VersionFallback(v_str)

    Version = VersionFallback  # type: ignore[misc,assignment]


KNOWN_REPOS: dict[str, str] = {
    "google-ads-python": "googleads/google-ads-python",
    "google-ads-php": "googleads/google-ads-php",
    "google-ads-ruby": "googleads/google-ads-ruby",
    "google-ads-java": "googleads/google-ads-java",
    "google-ads-dotnet": "googleads/google-ads-dotnet",
}


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

    # Candidates relative to script and workspace
    candidates: list[str] = [
        # Relative to plugins/google-ads-api-developer-assistant/skills/sync-client-libs/scripts/
        os.path.abspath(os.path.join(script_dir, "../../../client_libs")),
        # Relative to .agents/skills/...
        os.path.abspath(os.path.join(script_dir, "../../../../client_libs")),
        # Relative to project root
        os.path.abspath("plugins/google-ads-api-developer-assistant/client_libs"),
        os.path.abspath("client_libs"),
        # Global plugin installation directory
        os.path.expanduser(
            "~/.gemini/config/plugins/google-ads-api-developer-assistant/client_libs"
        ),
    ]

    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate

    raise FileNotFoundError(
        "Could not automatically locate client_libs directory. "
        "Please provide --client_libs_dir."
    )


def get_repo_slug(lib_name: str, lib_path: str) -> str:
    """Determines GitHub repo slug (owner/repo) for a given library directory."""
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
            )
            url = res.stdout.strip()
            match = re.search(r"github\.com[:/]([^/]+/[^/.]+?)(?:\.git)?$", url)
            if match:
                return match.group(1)
        except Exception:
            pass

    # Default fallback assumption
    return f"googleads/{lib_name}"


def detect_installed_version(lib_name: str, lib_path: str) -> Optional[str]:
    """Detects the installed version of a client library from its local files."""
    # 1. Python library detection (pyproject.toml or ChangeLog)
    pyproject_path = os.path.join(lib_path, "pyproject.toml")
    if os.path.isfile(pyproject_path):
        try:
            with open(pyproject_path, "r", encoding="utf-8") as f:
                content = f.read()
                match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
                if match:
                    return match.group(1).strip()
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

    # 2. PHP library detection (composer.json)
    composer_path = os.path.join(lib_path, "composer.json")
    if os.path.isfile(composer_path):
        try:
            with open(composer_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "version" in data:
                    return str(data["version"]).strip()
        except Exception:
            pass

    # 3. Ruby library detection (*.gemspec or version.rb)
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

    # 4. Java library detection (pom.xml)
    pom_path = os.path.join(lib_path, "pom.xml")
    if os.path.isfile(pom_path):
        try:
            with open(pom_path, "r", encoding="utf-8") as f:
                match = re.search(r"<version>([^<]+)</version>", f.read())
                if match:
                    return match.group(1).strip()
        except OSError:
            pass

    # 5. .NET library detection (*.csproj)
    for root, _, files in os.walk(lib_path):
        for file in files:
            if file.endswith(".csproj"):
                try:
                    with open(
                        os.path.join(root, file), "r", encoding="utf-8"
                    ) as f:
                        match = re.search(r"<Version>([^<]+)</Version>", f.read())
                        if match:
                            return match.group(1).strip()
                except OSError:
                    pass

    # 6. Git tags fallback
    git_dir = os.path.join(lib_path, ".git")
    if os.path.isdir(git_dir):
        try:
            res = subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0"],
                cwd=lib_path,
                capture_output=True,
                text=True,
                check=False,
            )
            tag = res.stdout.strip()
            if tag:
                return tag.lstrip("v")
        except Exception:
            pass

    return None


def fetch_github_latest_release(repo_slug: str) -> tuple[Optional[str], Optional[str]]:
    """Fetches the latest release tag name and tarball URL from GitHub API.

    Returns:
        (latest_version_tag, tarball_url)
    """
    url = f"https://api.github.com/repos/{repo_slug}/releases/latest"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "google-ads-api-developer-assistant",
            "Accept": "application/vnd.github.v3+json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            tag_name: str = data.get("tag_name", "").strip()
            tarball_url: Optional[str] = data.get("tarball_url")
            return tag_name, tarball_url
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # Fallback to list of releases if /releases/latest returns 404
            fallback_url = f"https://api.github.com/repos/{repo_slug}/releases?per_page=5"
            fb_req = urllib.request.Request(
                fallback_url,
                headers={
                    "User-Agent": "google-ads-api-developer-assistant",
                    "Accept": "application/vnd.github.v3+json",
                },
            )
            try:
                with urllib.request.urlopen(fb_req, timeout=15) as fb_resp:
                    releases = json.loads(fb_resp.read().decode("utf-8"))
                    for r in releases:
                        if not r.get("draft") and not r.get("prerelease"):
                            return r.get("tag_name", "").strip(), r.get(
                                "tarball_url"
                            )
            except Exception:
                pass
    except Exception as ex:
        print(f"WARN: Failed to query GitHub API for {repo_slug}: {ex}", file=sys.stderr)

    # Secondary fallback using git ls-remote tags
    try:
        remote_url = f"https://github.com/{repo_slug}.git"
        res = subprocess.run(
            ["git", "ls-remote", "--tags", remote_url],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        if res.returncode == 0 and res.stdout:
            tags: list[str] = []
            for line in res.stdout.splitlines():
                match = re.search(r"refs/tags/([^^]+)$", line)
                if match:
                    t = match.group(1).strip()
                    if not t.endswith("^{}"):
                        tags.append(t)
            if tags:
                # Sort tags by semver
                def tag_sort_key(t_val: str) -> Any:
                    try:
                        return parse_version(t_val.lstrip("v"))
                    except Exception:
                        return parse_version("0.0.0")

                tags.sort(key=tag_sort_key)
                latest_tag = tags[-1]
                return latest_tag, None
    except Exception:
        pass

    return None, None


def is_update_needed(installed_str: Optional[str], github_str: Optional[str]) -> bool:
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
    except Exception:
        # Fallback raw comparison
        return clean_installed != clean_github


def update_codebase_via_git(lib_path: str, tag: str) -> bool:
    """Updates a git repository in lib_path to the specified tag or latest HEAD."""
    try:
        # Fetch tags
        fetch_res = subprocess.run(
            ["git", "fetch", "--tags", "--all"],
            cwd=lib_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if fetch_res.returncode != 0:
            return False

        # Attempt to checkout tag
        co_res = subprocess.run(
            ["git", "checkout", tag],
            cwd=lib_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if co_res.returncode == 0:
            return True

        # If checkout tag failed, try checking out v-prefixed or stripped tag
        alt_tag = f"v{tag}" if not tag.startswith("v") else tag.lstrip("v")
        co_alt = subprocess.run(
            ["git", "checkout", alt_tag],
            cwd=lib_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if co_alt.returncode == 0:
            return True

        # Fallback to git pull
        pull_res = subprocess.run(
            ["git", "pull"],
            cwd=lib_path,
            capture_output=True,
            text=True,
            check=False,
        )
        return pull_res.returncode == 0
    except Exception as ex:
        print(f"Error updating git repository at {lib_path}: {ex}", file=sys.stderr)
        return False


def update_codebase_via_archive(
    lib_path: str, repo_slug: str, tag: str, tarball_url: Optional[str]
) -> bool:
    """Downloads release tarball or clones repository to update non-git codebase."""
    temp_dir = tempfile.mkdtemp(prefix="client_lib_update_")
    try:
        # 1. Try git clone shallow tag first if git is available
        clone_tag = tag if tag.startswith("v") else f"v{tag}"
        remote_url = f"https://github.com/{repo_slug}.git"
        clone_res = subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", tag, remote_url, temp_dir],
            capture_output=True,
            text=True,
            check=False,
        )
        if clone_res.returncode != 0:
            clone_res = subprocess.run(
                [
                    "git",
                    "clone",
                    "--depth",
                    "1",
                    "--branch",
                    clone_tag,
                    remote_url,
                    temp_dir,
                ],
                capture_output=True,
                text=True,
                check=False,
            )

        if (
            clone_res.returncode == 0
            and os.path.exists(os.path.join(temp_dir, "pyproject.toml"))
            or os.path.exists(os.path.join(temp_dir, "composer.json"))
            or os.path.exists(os.path.join(temp_dir, "pom.xml"))
        ):
            # Sync files into lib_path
            return sync_directories(temp_dir, lib_path)

        # 2. Try tarball extraction
        archive_url = (
            tarball_url or f"https://github.com/{repo_slug}/archive/refs/tags/{tag}.tar.gz"
        )
        tar_dest = os.path.join(temp_dir, "release.tar.gz")
        req = urllib.request.Request(
            archive_url,
            headers={"User-Agent": "google-ads-api-developer-assistant"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp, open(
            tar_dest, "wb"
        ) as out_f:
            shutil.copyfileobj(resp, out_f)

        extract_dir = os.path.join(temp_dir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        with tarfile.open(tar_dest, "r:gz") as tar:
            tar.extractall(extract_dir)

        # Find the root folder inside the tarball
        extracted_items = os.listdir(extract_dir)
        if len(extracted_items) == 1 and os.path.isdir(
            os.path.join(extract_dir, extracted_items[0])
        ):
            source_content_dir = os.path.join(extract_dir, extracted_items[0])
        else:
            source_content_dir = extract_dir

        return sync_directories(source_content_dir, lib_path)

    except Exception as ex:
        print(f"Error updating codebase {repo_slug}: {ex}", file=sys.stderr)
        return False
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def sync_directories(source_dir: str, target_dir: str) -> bool:
    """Cleanly synchronizes content from source_dir into target_dir."""
    try:
        os.makedirs(target_dir, exist_ok=True)
        # Remove existing contents except user custom yaml/config if any
        for item in os.listdir(target_dir):
            if item in [".git", "google-ads.yaml", "config.yaml"]:
                continue
            item_path = os.path.join(target_dir, item)
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
            else:
                os.remove(item_path)

        for item in os.listdir(source_dir):
            if item == ".git":
                continue
            src_item = os.path.join(source_dir, item)
            dst_item = os.path.join(target_dir, item)
            if os.path.isdir(src_item):
                shutil.copytree(src_item, dst_item)
            else:
                shutil.copy2(src_item, dst_item)
        return True
    except Exception as ex:
        print(f"Failed to copy files from {source_dir} to {target_dir}: {ex}", file=sys.stderr)
        return False


def detect_lib_api_version(lib_path: str) -> Optional[str]:
    """Detects the highest v<N> API version directory in a google-ads-python codebase."""
    python_root = os.path.join(lib_path, "google/ads/googleads")
    if not os.path.isdir(python_root):
        return None
    try:
        v_dirs = [
            d
            for d in os.listdir(python_root)
            if os.path.isdir(os.path.join(python_root, d)) and re.match(r"^v\d+$", d)
        ]
        if not v_dirs:
            return None
        v_dirs.sort(key=lambda x: int(x[1:]))
        return v_dirs[-1]
    except OSError:
        return None


def update_api_version_cache_if_needed(lib_path: str) -> Optional[str]:
    """Inspects updated google-ads-python library and refreshes api_version in config/assistant_config."""
    latest_v = detect_lib_api_version(lib_path)
    if not latest_v:
        return None

    try:
        # Candidate config locations
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
        config_targets: list[str] = []
        for t in raw_targets:
            norm_t = os.path.normpath(t)
            if norm_t not in config_targets:
                config_targets.append(norm_t)

        for cfg_path in config_targets:
            cfg_dir = os.path.dirname(cfg_path)
            if os.path.isdir(cfg_dir):
                cid = "12345678"
                exec_mutates_str = "false"
                if os.path.isfile(cfg_path):
                    try:
                        with open(cfg_path, "r", encoding="utf-8") as f:
                            existing_text = f.read()
                        m_cid = re.search(
                            r'(?m)^\s*customer_id\s*=\s*["\']?([^"\'\s#]+)["\']?',
                            existing_text,
                        )
                        if m_cid:
                            cid = m_cid.group(1).strip()
                        m_em = re.search(
                            r'(?m)^\s*execute_mutates\s*=\s*["\']?(true|false)["\']?',
                            existing_text,
                            re.IGNORECASE,
                        )
                        if m_em:
                            exec_mutates_str = m_em.group(1).lower()
                    except OSError:
                        pass
                with open(cfg_path, "w", encoding="utf-8") as f:
                    f.write(
                        f'api_version = "{latest_v}"\n'
                        f'customer_id = "{cid}"\n'
                        f"execute_mutates = {exec_mutates_str}\n"
                    )
                legacy_ver_txt = os.path.join(cfg_dir, "api_version.txt")
                if os.path.isfile(legacy_ver_txt):
                    try:
                        with open(legacy_ver_txt, "w", encoding="utf-8") as lf:
                            lf.write(f"{latest_v}\n")
                    except OSError:
                        pass

        return latest_v
    except Exception:
        return None


def detect_system_package_version(
    package_name: str = "google-ads",
) -> tuple[Optional[str], list[str]]:
    """Detects the installed version of a package in the Python system site-packages/environment.

    Returns:
        (installed_version, site_directories)
    """
    site_dirs: list[str] = []
    try:
        import site

        if hasattr(site, "getsitepackages"):
            site_dirs.extend(site.getsitepackages())
        if hasattr(site, "getusersitepackages"):
            site_dirs.append(site.getusersitepackages())
    except Exception:
        pass

    # Try importlib.metadata
    try:
        import importlib.metadata

        v = importlib.metadata.version(package_name)
        return v.strip(), site_dirs
    except Exception:
        pass

    # Fallback to pip show
    try:
        res = subprocess.run(
            [sys.executable, "-m", "pip", "show", package_name],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                if line.startswith("Version:"):
                    return line.split(":", 1)[1].strip(), site_dirs
                if (
                    line.startswith("Location:")
                    and line.split(":", 1)[1].strip() not in site_dirs
                ):
                    site_dirs.append(line.split(":", 1)[1].strip())
    except Exception:
        pass

    return None, site_dirs


def check_system_package_parity(
    package_name: str = "google-ads",
    target_version: Optional[str] = None,
) -> dict[str, Any]:
    """Checks the installed package version in the system site-directory against target/upstream version."""
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


def upgrade_system_package(
    package_name: str = "google-ads",
    target_version: Optional[str] = None,
    lib_path: Optional[str] = None,
) -> bool:
    """Upgrades the package from pypi.org (and optional local client_libs path) into the Python site directory."""
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
        cmd.append(f"{package_name}=={target_version}")
    else:
        cmd.append(package_name)
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        ok = res.returncode == 0
        if (
            not ok
            and lib_path
            and os.path.isdir(lib_path)
            and os.path.isfile(os.path.join(lib_path, "pyproject.toml"))
        ):
            local_res = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", lib_path],
                capture_output=True,
                text=True,
                check=False,
            )
            ok = local_res.returncode == 0
        return ok
    except Exception as ex:
        print(f"Error upgrading {package_name}: {ex}", file=sys.stderr)
        return False


def check_assistant_repo(
    check_only: bool = False,
    force: bool = False,
) -> Optional[dict[str, Any]]:
    """Checks and updates the google-ads-api-developer-assistant repository itself."""
    script_dir: str = os.path.dirname(os.path.abspath(__file__))
    project_root: Optional[str] = None
    candidates = [
        os.path.abspath(os.path.join(script_dir, "../../../..")),
        os.path.abspath(os.path.join(script_dir, "../../../../..")),
        os.path.abspath("."),
    ]
    for c in candidates:
        if os.path.isfile(
            os.path.join(c, "plugins/google-ads-api-developer-assistant/plugin.json")
        ) or os.path.isfile(os.path.join(c, "plugin.json")):
            project_root = c
            break

    if not project_root:
        return None

    repo_slug = "googleads/google-ads-api-developer-assistant"
    installed_version = None

    # Read version from plugin.json
    for p_json in [
        os.path.join(project_root, "plugins/google-ads-api-developer-assistant/plugin.json"),
        os.path.join(project_root, "plugin.json"),
    ]:
        if os.path.isfile(p_json):
            try:
                with open(p_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    installed_version = data.get("version")
                    if installed_version:
                        break
            except Exception:
                pass

    if not installed_version and os.path.isdir(os.path.join(project_root, ".git")):
        try:
            res = subprocess.run(
                ["git", "describe", "--tags", "--abbrev=0"],
                cwd=project_root,
                capture_output=True,
                text=True,
                check=False,
            )
            tag = res.stdout.strip()
            if tag:
                installed_version = tag.lstrip("v")
        except Exception:
            pass

    github_tag, tarball_url = fetch_github_latest_release(repo_slug)
    github_version = github_tag.lstrip("v") if github_tag else None

    needs_update = is_update_needed(installed_version, github_version) or force
    status = "UP_TO_DATE"
    updated = False

    if needs_update and not check_only:
        if os.path.isdir(os.path.join(project_root, ".git")):
            updated = update_codebase_via_git(project_root, github_tag or "")
        else:
            updated = update_codebase_via_archive(
                project_root, repo_slug, github_tag or "", tarball_url
            )
        status = "UPDATED" if updated else "UPDATE_FAILED"
    elif needs_update and check_only:
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
    """Discovers, verifies, and updates all codebases in client_libs_dir and the assistant."""
    import concurrent.futures

    results: list[dict[str, Any]] = []

    # 1. Check Assistant repository if enabled and not filtering for a specific client lib
    if include_assistant and (not target_library or target_library == "google-ads-api-developer-assistant"):
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

    # Prefetch GitHub release metadata concurrently when multiple libraries are checked
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
                except Exception:
                    prefetched_releases[slug] = (None, None)

    for entry, lib_path, repo_slug in valid_libs:
        installed_version = detect_installed_version(entry, lib_path)
        if repo_slug in prefetched_releases:
            github_tag, tarball_url = prefetched_releases[repo_slug]
        else:
            github_tag, tarball_url = fetch_github_latest_release(repo_slug)
        github_version = github_tag.lstrip("v") if github_tag else None

        needs_update = is_update_needed(installed_version, github_version) or force
        status = "UP_TO_DATE"
        updated = False

        if needs_update and not check_only:
            # Perform update
            if os.path.isdir(os.path.join(lib_path, ".git")):
                updated = update_codebase_via_git(lib_path, github_tag or "")
            else:
                updated = update_codebase_via_archive(
                    lib_path, repo_slug, github_tag or "", tarball_url
                )

            if updated:
                status = "UPDATED"
                # If python library was updated, update API version cache
                if entry == "google-ads-python":
                    update_api_version_cache_if_needed(lib_path)
                # Re-detect new installed version
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
        latest_api_version: Optional[str] = None

        if entry == "google-ads-python":
            sys_v, s_dirs = detect_system_package_version("google-ads")
            system_version = sys_v
            system_site_dirs = s_dirs
            ref_v = github_version or installed_version
            site_version_less_than_github = is_update_needed(sys_v, ref_v)
            if ref_v and sys_v:
                system_version_matches = (
                    not site_version_less_than_github
                    and sys_v.lstrip("v").strip() == ref_v.lstrip("v").strip()
                )
            elif not sys_v:
                system_version_matches = False
            else:
                system_version_matches = True

            if upgrade_system and (not system_version_matches or site_version_less_than_github or force) and not check_only:
                upgraded = upgrade_system_package(
                    "google-ads",
                    github_version,
                    lib_path=lib_path,
                )
                if upgraded:
                    sys_v, _ = detect_system_package_version("google-ads")
                    system_version = sys_v
                    site_version_less_than_github = is_update_needed(sys_v, ref_v)
                    if ref_v and sys_v:
                        system_version_matches = (
                            not site_version_less_than_github
                            and sys_v.lstrip("v").strip() == ref_v.lstrip("v").strip()
                        )
            if not check_only:
                latest_api_version = update_api_version_cache_if_needed(lib_path)
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
            res_item["site_version_less_than_github"] = site_version_less_than_github
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
            "Codebase / Component", "Repository / Source", "Installed", "GitHub Release", "Status"
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
            sys_st = (
                "UP_TO_DATE"
                if r.get("system_version_matches")
                else ("OUTDATED" if r.get("site_version_less_than_github") else "MISMATCH")
            )
            print(
                fmt.format(
                    "google-ads (site-packages)",
                    "pypi.org/project/google-ads",
                    sys_v,
                    gh,
                    sys_st,
                )
            )
            if r.get("api_version"):
                api_v = str(r.get("api_version"))
                print(
                    fmt.format(
                        "api_version (assistant_config)",
                        "config/assistant_config",
                        api_v,
                        api_v,
                        "ACTIVE",
                    )
                )
    print("=" * 96)

    for r in results:
        if r.get("codebase") == "google-ads-python" and "system_version" in r:
            sys_v = r.get("system_version")
            tgt_v = r.get("github_version") or r.get("installed_version")
            dirs = r.get("system_site_dirs") or []
            primary_dir = dirs[0] if dirs else "system site-packages"
            api_ver = r.get("api_version")
            if r.get("system_version_matches") is False:
                print("\n" + "!" * 80)
                print("ALERT: Python system site-directory version mismatch!")
                print("  Package: google-ads")
                print(f"  System site-directory version : {sys_v or 'NOT INSTALLED'}")
                print(f"  Latest upstream release       : {tgt_v}")
                print(f"  Site directory path           : {primary_dir}")
                print("  Action: Gemini should alert the user and ask if they would like to upgrade.")
                print("!" * 80)
            elif r.get("system_version_matches") is True:
                api_suffix = f" (active api_version = {api_ver})" if api_ver else ""
                print(
                    f"\n[OK] System site-directory package 'google-ads' ({sys_v} in {primary_dir}) matches upstream release ({tgt_v}){api_suffix}."
                )


def main() -> None:
    """CLI entry point for discovery and updating client_libs."""
    parser = argparse.ArgumentParser(
        description="Automated discovery and update tool for Google Ads client libraries."
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
        help="Target a specific codebase/library name (e.g. google-ads-python).",
    )
    parser.add_argument(
        "--upgrade_system",
        action="store_true",
        help="Upgrade google-ads in the Python system site-packages if mismatched.",
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
            target_library=args.library,
            upgrade_system=args.upgrade_system,
        )

        if args.json:
            print(json.dumps({"client_libs_dir": target_dir, "results": results}, indent=2))
        else:
            print(f"Target client_libs directory: {target_dir}")
            print_table(results)

        # Check if any updates failed
        has_failures = any(r["status"] == "UPDATE_FAILED" for r in results)
        if has_failures:
            sys.exit(1)

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

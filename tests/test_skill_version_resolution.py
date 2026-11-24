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

"""Offline regression tests for skill-script API version resolution.

Covers review findings #14 (no traceback without the SDK), #15 (ext-version
--active), #24/#16 (scripts delegate to config_init), #26 (--api_version is
optional), #33 (upb fields_by_name), #34 (GCLID masking) and #35 (SKILL.md
plugin paths).

Each resolution test copies the skill scripts and config_init.py into a
scratch plugin layout and runs them in a subprocess with a scratch HOME and
cwd, so the developer's real install, assistant_config and client_libs are
never read. A stub `google` package on sys.path hides any installed
google-ads SDK.
"""

import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import textwrap
import types
from unittest import mock

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
TESTS_DIR = pathlib.Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
from api_version_utils import (  # noqa: E402
    CURRENT_API_VERSION,
    NEXT_API_VERSION,
    OLDER_API_VERSION,
    PREVIOUS_API_NUMBER,
    PREVIOUS_API_VERSION,
    offset_api_version,
)

PLUGIN_ROOT = REPO_ROOT / "plugins" / "google-ads-api-developer-assistant"
SKILLS = PLUGIN_ROOT / "skills"

# Script -> how to call its resolver in-process (expression on module `m`).
RESOLVER_SCRIPTS = {
    "inspect-object/scripts/inspect_object.py": "m._normalize_api_version(EXPLICIT)",
    "get-cids-under-mcc/scripts/get_cids_under_mcc.py": "m._normalize_api_version(EXPLICIT)",
    "pmax-listing-filter/scripts/create_pmax_webpage_filter.py": "m._normalize_api_version(EXPLICIT)",
    "troubleshoot-conversions/scripts/troubleshoot_conversions.py": "m._normalize_api_version(EXPLICIT)",
    "troubleshoot-conversions/scripts/get_recent_gclids.py": "m._normalize_api_version(EXPLICIT)",
    "validate-gaql/scripts/validate_gaql.py": "m._resolve_active_api_version(EXPLICIT)",
    "ext-version/scripts/get_latest_api_version.py": "m.get_active_api_version()",
}

# Imports run inside the subprocess before the script is loaded. The stub
# `google` package is a regular package without `ads`, so
# importlib.util.find_spec("google.ads.googleads") raises ModuleNotFoundError,
# which is exactly what happens when the SDK is not installed.
_RUNNER = textwrap.dedent(
    """
    import importlib.util, json, sys
    sys.path.insert(0, {stub!r})
    for name in [n for n in sys.modules if n == "google" or n.startswith("google.")]:
        del sys.modules[name]
    spec = importlib.util.spec_from_file_location("skill_under_test", {script!r})
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    EXPLICIT = {explicit!r}
    try:
        print(json.dumps({{"ok": {expr}}}))
    except ValueError as e:
        print(json.dumps({{"error": str(e)}}))
    """
)


@pytest.fixture(name="sandbox")
def fixture_sandbox(tmp_path):
    """Builds a scratch plugin layout, HOME, cwd and SDK-hiding stub."""
    plugin = tmp_path / "plugin"
    (plugin / "config").mkdir(parents=True)
    shutil.copy2(PLUGIN_ROOT / "config" / "config_init.py", plugin / "config")
    (plugin / "config" / "__init__.py").write_text("", encoding="utf-8")
    for rel in RESOLVER_SCRIPTS:
        dst = plugin / "skills" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SKILLS / rel, dst)
    stub = tmp_path / "stub"
    (stub / "google").mkdir(parents=True)
    (stub / "google" / "__init__.py").write_text("", encoding="utf-8")
    home = tmp_path / "home"
    home.mkdir()
    cwd = tmp_path / "cwd"
    cwd.mkdir()

    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("GOOGLE_ADS_", "CLAUDE", "PYTHON"))
    }
    env["HOME"] = str(home)

    return types.SimpleNamespace(
        root=tmp_path, plugin=plugin, stub=stub, home=home, cwd=cwd, env=env
    )


def _add_client_libs(sandbox, *versions):
    base = (
        sandbox.plugin
        / "client_libs"
        / "google-ads-python"
        / "google"
        / "ads"
        / "googleads"
    )
    for v in versions:
        (base / v).mkdir(parents=True, exist_ok=True)


def _resolve(sandbox, rel, explicit=None, env=None):
    script = str(sandbox.plugin / "skills" / rel)
    code = _RUNNER.format(
        stub=str(sandbox.stub),
        script=script,
        explicit=explicit,
        expr=RESOLVER_SCRIPTS[rel],
    )
    proc = subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=sandbox.cwd,
        env={**sandbox.env, **(env or {})},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert "Traceback" not in proc.stderr, proc.stderr
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _run_cli(sandbox, rel, *args, env=None):
    """Runs a copied skill script as __main__ with the SDK hidden."""
    script = str(sandbox.plugin / "skills" / rel)
    code = textwrap.dedent(
        f"""
        import runpy, sys
        sys.path.insert(0, {str(sandbox.stub)!r})
        sys.argv = [{script!r}, *{list(args)!r}]
        runpy.run_path({script!r}, run_name="__main__")
        """
    )
    return subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=sandbox.cwd,
        env={**sandbox.env, **(env or {})},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


# --- #14: no traceback when the SDK is absent --------------------------------


def test_stub_reproduces_missing_sdk_find_spec_error(sandbox):
    """Repro of the #14 root cause: find_spec raises when the SDK is absent.

    The old inspect_object._get_default_api_version called
    importlib.util.find_spec("google.ads.googleads") unguarded, so this
    ModuleNotFoundError escaped as a traceback.
    """
    code = textwrap.dedent(
        f"""
        import importlib.util, sys
        sys.path.insert(0, {str(sandbox.stub)!r})
        importlib.util.find_spec("google.ads.googleads")
        """
    )
    proc = subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=sandbox.cwd,
        env=sandbox.env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode != 0
    assert "ModuleNotFoundError" in proc.stderr


def test_inspect_object_cli_without_sdk_or_version_prints_clear_error(sandbox):
    proc = _run_cli(
        sandbox, "inspect-object/scripts/inspect_object.py", "--object_name", "Campaign"
    )
    assert proc.returncode == 1
    assert "Traceback" not in proc.stderr
    assert "ERROR:" in proc.stderr
    assert "pass --api_version vN" in proc.stderr


@pytest.mark.parametrize("rel", sorted(RESOLVER_SCRIPTS))
def test_unresolvable_version_raises_value_error_not_traceback(sandbox, rel):
    result = _resolve(sandbox, rel)
    assert "error" in result, result
    assert "pass --api_version vN" in result["error"]


# --- #24/#16: one shared resolution order ------------------------------------


@pytest.mark.parametrize("rel", sorted(RESOLVER_SCRIPTS))
def test_highest_local_client_libs_version_used_without_sdk(sandbox, rel):
    v_a, v_b, v_c = offset_api_version(3), offset_api_version(5), offset_api_version(4)
    _add_client_libs(sandbox, v_a, v_b, v_c)
    assert _resolve(sandbox, rel) == {"ok": v_b}


@pytest.mark.parametrize("rel", sorted(RESOLVER_SCRIPTS))
def test_assistant_config_beats_detection(sandbox, rel):
    v_top = offset_api_version(5)
    _add_client_libs(sandbox, v_top)
    (sandbox.plugin / "config" / "assistant_config").write_text(
        f'api_version = "{CURRENT_API_VERSION}"\n', encoding="utf-8"
    )
    assert _resolve(sandbox, rel) == {"ok": CURRENT_API_VERSION}


@pytest.mark.parametrize("rel", sorted(RESOLVER_SCRIPTS))
def test_env_beats_assistant_config_and_is_normalized(sandbox, rel):
    v_top = offset_api_version(5)
    _add_client_libs(sandbox, v_top)
    (sandbox.plugin / "config" / "assistant_config").write_text(
        f'api_version = "{CURRENT_API_VERSION}"\n', encoding="utf-8"
    )
    result = _resolve(sandbox, rel, env={"GOOGLE_ADS_API_VERSION": str(PREVIOUS_API_NUMBER)})
    assert result == {"ok": PREVIOUS_API_VERSION}


@pytest.mark.parametrize("rel", sorted(RESOLVER_SCRIPTS))
@pytest.mark.parametrize("bad", ["latest", "../../x", f"{CURRENT_API_VERSION}beta"])
def test_invalid_env_value_rejected(sandbox, rel, bad):
    _add_client_libs(sandbox, offset_api_version(5))
    result = _resolve(sandbox, rel, env={"GOOGLE_ADS_API_VERSION": bad})
    assert "error" in result, result


_EXPLICIT_RELS = sorted(
    r for r in RESOLVER_SCRIPTS if "get_latest_api_version" not in r
)


@pytest.mark.parametrize("rel", _EXPLICIT_RELS)
def test_explicit_version_wins_and_is_validated(sandbox, rel):
    v_top = offset_api_version(5)
    v_older_num = OLDER_API_VERSION[1:]
    v_oldest = offset_api_version(-3)
    _add_client_libs(sandbox, v_top)
    env = {"GOOGLE_ADS_API_VERSION": str(PREVIOUS_API_NUMBER)}
    assert _resolve(sandbox, rel, explicit=v_older_num, env=env) == {"ok": OLDER_API_VERSION}
    assert _resolve(sandbox, rel, explicit=f" {v_oldest.upper()} ", env=env) == {"ok": v_oldest}
    assert "error" in _resolve(sandbox, rel, explicit="../../x", env=env)


def test_claude_plugin_root_config_used(sandbox):
    """CLAUDE_PLUGIN_ROOT/config/assistant_config is honored (#16)."""
    _add_client_libs(sandbox, offset_api_version(5))
    claude_root = sandbox.root / "claude_root"
    (claude_root / "config").mkdir(parents=True)
    (claude_root / "config" / "assistant_config").write_text(
        f'api_version = "{NEXT_API_VERSION}"\n', encoding="utf-8"
    )
    result = _resolve(
        sandbox,
        "inspect-object/scripts/inspect_object.py",
        env={"CLAUDE_PLUGIN_ROOT": str(claude_root)},
    )
    assert result == {"ok": NEXT_API_VERSION}


def test_skill_scripts_have_no_private_version_detection():
    """Copied resolvers (find_spec / config path lists) are gone (#24)."""
    for rel in RESOLVER_SCRIPTS:
        if "get_latest_api_version" in rel:
            continue  # Keeps detect_latest_api_version for --installed mode.
        text = (SKILLS / rel).read_text(encoding="utf-8")
        assert "find_spec" not in text, rel
        assert "_resolve_default_api_version" not in text, rel
        assert "_get_default_api_version" not in text, rel
        assert "resolve_active_api_version" in text, rel


# --- #15: ext-version --active / --no-update / --installed -------------------


def test_ext_version_modes(sandbox):
    rel = "ext-version/scripts/get_latest_api_version.py"
    v_top = offset_api_version(5)
    _add_client_libs(sandbox, v_top)
    cfg = sandbox.plugin / "config" / "assistant_config"
    cfg.write_text(f'api_version = "{CURRENT_API_VERSION}"\n', encoding="utf-8")
    env = {"GOOGLE_ADS_API_VERSION": PREVIOUS_API_VERSION}

    for flag in ("--active", "--no-update"):
        proc = _run_cli(sandbox, rel, flag, env=env)
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip() == PREVIOUS_API_VERSION

    proc = _run_cli(sandbox, rel, "--active")
    assert proc.stdout.strip() == CURRENT_API_VERSION, proc.stderr

    proc = _run_cli(sandbox, rel, "--installed", env=env)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == v_top

    # None of the read-only modes wrote config.
    assert cfg.read_text(encoding="utf-8") == f'api_version = "{CURRENT_API_VERSION}"\n'


def test_ext_version_active_without_any_version_exits_cleanly(sandbox):
    proc = _run_cli(sandbox, "ext-version/scripts/get_latest_api_version.py", "--active")
    assert proc.returncode == 1
    assert "Traceback" not in proc.stderr
    assert "pass --api_version vN" in proc.stderr


# --- #26: --api_version is optional ------------------------------------------


def test_validate_gaql_cli_api_version_optional(sandbox):
    rel = "validate-gaql/scripts/validate_gaql.py"
    args = ("--customer_id", "1234567890", "--query", "SELECT campaign.id FROM campaign")
    proc = _run_cli(sandbox, rel, *args)
    assert "required" not in proc.stderr
    assert proc.returncode == 1
    assert "Traceback" not in proc.stderr
    assert "pass --api_version vN" in proc.stderr


@pytest.mark.parametrize(
    "rel",
    [
        "troubleshoot-conversions/scripts/get_recent_gclids.py",
        "troubleshoot-conversions/scripts/troubleshoot_conversions.py",
        "troubleshoot-conversions/scripts/validate_conversion_upload.py",
        "validate-gaql/scripts/validate_gaql.py",
    ],
)
def test_api_version_not_required_in_argparse(rel):
    text = (SKILLS / rel).read_text(encoding="utf-8")
    m = re.search(r'"--api_version",(.*?)\)', text, re.S)
    assert m, rel
    assert "required=True" not in m.group(1), rel


def test_validate_conversion_upload_runs_without_api_version(tmp_path):
    csv_path = tmp_path / "conv.csv"
    csv_path.write_text(
        "gclid,conversion_action,conversion_time,conversion_value,currency_code\n"
        "abc123,customers/1/conversionActions/2,2026-01-01 10:00:00+00:00,1.0,USD\n",
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(SKILLS / "troubleshoot-conversions/scripts/validate_conversion_upload.py"),
            "--csv_path",
            str(csv_path),
        ],
        cwd=tmp_path,
        env={**os.environ, "HOME": str(tmp_path)},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert "required" not in proc.stderr
    assert "Traceback" not in proc.stderr


# --- #33 / #34: troubleshoot_conversions --------------------------------------


def _load_troubleshoot():
    path = SKILLS / "troubleshoot-conversions/scripts/troubleshoot_conversions.py"
    spec = importlib.util.spec_from_file_location("tc_version_res", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _ByNameLike:
    """Non-dict, non-Mapping container like upb's _ByNameMap."""

    def __init__(self, *names):
        self._names = set(names)

    def __contains__(self, name):
        return name in self._names

    def __len__(self):
        return len(self._names)


def test_cts_enablement_uses_fields_by_name_for_non_dict_maps():
    tc = _load_troubleshoot()

    def cts(fields, *attrs):
        obj = types.SimpleNamespace(**{a: None for a in attrs})
        obj.DESCRIPTOR = types.SimpleNamespace(fields_by_name=fields)
        return obj

    assert tc._cts_supports_enablement_setting(
        cts(_ByNameLike("effective_enablement_setting"))
    )
    assert not tc._cts_supports_enablement_setting(
        cts(
            _ByNameLike(
                "effective_enablement_setting",
                "enhanced_conversions_for_leads_enabled",
            ),
            "effective_enablement_setting",
        )
    )
    # A descriptor map without the field wins over hasattr() probing.
    assert not tc._cts_supports_enablement_setting(
        cts(_ByNameLike("other_field"), "effective_enablement_setting")
    )


def test_cts_enablement_with_real_upb_by_name_map():
    descriptor_pb2 = pytest.importorskip("google.protobuf.descriptor_pb2")
    tc = _load_troubleshoot()
    fields = descriptor_pb2.FileDescriptorProto.DESCRIPTOR.fields_by_name
    assert not isinstance(fields, dict)
    obj = types.SimpleNamespace(effective_enablement_setting=None)
    obj.DESCRIPTOR = types.SimpleNamespace(fields_by_name=fields)
    # Old code skipped the non-dict map and trusted hasattr() -> True.
    assert tc._cts_supports_enablement_setting(obj) is False


def test_mask_gclid():
    tc = _load_troubleshoot()
    assert tc._mask_gclid("Cj0KCQjw_test_gclid_12345") == "Cj0KCQ..._12345"
    assert tc._mask_gclid("short") == "*****"
    assert tc._mask_gclid("") == ""


@pytest.mark.parametrize("show", [False, True])
def test_troubleshoot_conversions_masks_gclids_by_default(
    tmp_path, capsys, show
):
    tc = _load_troubleshoot()
    full = "Cj0KCQjw_test_gclid_12345"
    gclid_row = types.SimpleNamespace(
        click_view=types.SimpleNamespace(gclid=full)
    )

    def fake_run_query(client, customer_id, query):
        del client, customer_id
        if "FROM click_view" in query:
            return [gclid_row]
        return []

    with mock.patch.object(tc, "run_query", side_effect=fake_run_query):
        data = tc.troubleshoot_conversions(
            mock.MagicMock(),
            "1234567890",
            json_output=True,
            output_dir=str(tmp_path),
            show_gclids=show,
        )
    out = capsys.readouterr().out
    report = pathlib.Path(data["report_path"]).read_text(encoding="utf-8")
    gclids = {g["gclid"] for g in data["recent_gclids"]}
    if show:
        assert gclids == {full}
        assert full in report
    else:
        assert gclids == {"Cj0KCQ..._12345"}
        assert full not in out
        assert full not in report
        assert full not in json.dumps(data, default=str)


# --- #35: SKILL.md plugin paths work for both CLIs ---------------------------

_OLD_ROOT = (
    "${CLAUDE_PLUGIN_ROOT:-${GOOGLE_ADS_ASSISTANT_DIR:-$HOME/.gemini/config/"
    "plugins/google-ads-api-developer-assistant}}"
)


def _owned_skill_mds():
    return [
        p
        for p in sorted(SKILLS.glob("*/SKILL.md"))
        if p.parent.name != "execute-mutation"
    ]


def test_skill_md_commands_use_gads_dir_preamble():
    for md in _owned_skill_mds():
        text = md.read_text(encoding="utf-8")
        assert _OLD_ROOT not in text, md
        for block in re.findall(r"```bash\n(.*?)```", text, re.S):
            if "$GADS_DIR" in block:
                assert block.lstrip().startswith('GADS_DIR="${CLAUDE_PLUGIN_ROOT'), md
                assert ".claude/plugins/google-ads-assistant-local" in block, md


def _preamble():
    text = (SKILLS / "ext-version" / "SKILL.md").read_text(encoding="utf-8")
    block = re.findall(r"```bash\n(.*?)```", text, re.S)[0]
    return block.strip().splitlines()[0].strip()


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
@pytest.mark.parametrize(
    "case, expected",
    [
        ("plugin_root", "PLUGIN_ROOT"),
        ("assistant_dir", "ASSISTANT_DIR"),
        ("claude_code", "CLAUDE"),
        ("agy_both_installed", "GEMINI"),
        ("agy_only_claude_installed", "CLAUDE"),
    ],
)
def test_gads_dir_preamble_resolution(tmp_path, case, expected):
    home = tmp_path / "home"
    gemini = home / ".gemini/config/plugins/google-ads-api-developer-assistant"
    claude = home / (
        ".claude/plugins/google-ads-assistant-local/plugins/"
        "google-ads-api-developer-assistant"
    )
    claude.mkdir(parents=True)
    if case != "agy_only_claude_installed":
        gemini.mkdir(parents=True)
    env = {"HOME": str(home), "PATH": os.environ.get("PATH", "")}
    if case == "plugin_root":
        env["CLAUDE_PLUGIN_ROOT"] = "/x/plugin_root"
        env["GOOGLE_ADS_ASSISTANT_DIR"] = "/x/assistant_dir"
    elif case == "assistant_dir":
        env["GOOGLE_ADS_ASSISTANT_DIR"] = "/x/assistant_dir"
    elif case == "claude_code":
        env["CLAUDECODE"] = "1"
    proc = subprocess.run(
        ["bash", "-c", _preamble() + '\nprintf %s "$GADS_DIR"'],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    want = {
        "PLUGIN_ROOT": "/x/plugin_root",
        "ASSISTANT_DIR": "/x/assistant_dir",
        "CLAUDE": str(claude),
        "GEMINI": str(gemini),
    }[expected]
    assert proc.stdout == want


def test_skill_md_api_version_documented_as_optional():
    for name in (
        "get-cids-under-mcc",
        "inspect-object",
        "pmax-listing-filter",
        "troubleshoot-conversions",
        "validate-gaql",
    ):
        text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
        assert "Omit it to use the active" in text, name
        assert "--api_version <api_version>" not in text, name
        assert '--api_version "<api_version>"' not in text, name


def test_commands_and_rules_use_new_path_pattern_and_optional_version():
    commands = sorted((PLUGIN_ROOT / "commands").glob("*.md"))
    rules = PLUGIN_ROOT / "rules" / "AGENTS.md"
    for md in [*commands, rules]:
        text = md.read_text(encoding="utf-8")
        assert _OLD_ROOT not in text, md
        for block in re.findall(r"```bash\n(.*?)```", text, re.S):
            if "$GADS_DIR" in block:
                assert block.lstrip().startswith('GADS_DIR="${CLAUDE_PLUGIN_ROOT'), md
        if md.stem != "execute-mutation":
            assert "--api_version <api_version>" not in text, md
            assert '--api_version "<api_version>"' not in text, md
    ext = (PLUGIN_ROOT / "commands" / "ext-version.md").read_text(encoding="utf-8")
    assert 'get_latest_api_version.py" --active' in ext


def test_no_static_api_versions_in_plugin_or_tests():
    """Ensures no hardcoded static Google Ads API version is used in plugin code or tests."""
    static_ver_literal_re = re.compile(
        r"""(?:["'][vV](?:1[5-9]|2[0-9]|3[0-9])["']"""
        r"""|googleads\.googleapis\.com/v(?:1[5-9]|2[0-9]|3[0-9])/"""
        r"""|google\.ads\.googleads\.v(?:1[5-9]|2[0-9]|3[0-9])\.services"""
        r"""|api_version\s*=\s*["']v?(?:1[5-9]|2[0-9]|3[0-9])["'])"""
    )
    skip_dirs = {"client_libs", "saved", "__pycache__"}
    offenders: list[str] = []
    for base in (PLUGIN_ROOT, REPO_ROOT / "tests"):
        for path in sorted(base.rglob("*")):
            if any(part in skip_dirs for part in path.parts) or not path.is_file():
                continue
            if path.suffix not in {".py", ".sh", ".ps1", ".json", ".md", ".yaml", ".yml", ""}:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for idx, line in enumerate(content.splitlines(), 1):
                if static_ver_literal_re.search(line):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{idx}: {line.strip()}")
    assert not offenders, "Static Google Ads API version literals found:\n" + "\n".join(offenders)

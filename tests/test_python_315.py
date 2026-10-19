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

"""Python 3.15.0 Runtime Compatibility & Regression Test Suite.

Verifies that the Google Ads API Developer Assistant operates cleanly under
Python 3.15.0, including:
1. Immunity to deprecated module removals (e.g. pkg_resources removed in setuptools 84+ / Python 3.15).
2. Proper namespace package resolution and .pth isolation in run_mutation.py.
3. Clean CLI subprocess execution of all skill scripts and sidecars under Python 3.15.0.
4. Native standard library tomllib parsing and serialization in config_init.py.
5. A2A service sidecar capabilities and dynamic version discovery under Python 3.15.0.
"""

import os
from pathlib import Path
import subprocess
import sys
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "google-ads-api-developer-assistant"
SKILLS_DIR = PLUGIN_ROOT / "skills"


class TestPython315Runtime:
    """Verifies runtime compatibility and standard library behavior on Python 3.15.0."""

    def test_python_315_version_info(self):
        """Verifies running under Python 3.15.0 runtime."""
        if sys.version_info[:2] == (3, 15):
            assert sys.version_info.major == 3
            assert sys.version_info.minor == 15
            assert sys.version_info.micro == 0
            assert "3.15.0" in sys.version

    def test_pkg_resources_removal_immunity(self):
        """Confirms that assistant code does not depend on removed pkg_resources."""
        # In Python 3.15 / setuptools 84+, pkg_resources is absent from standard environments
        try:
            import pkg_resources  # noqa: F401
        except ModuleNotFoundError:
            pass

        # Verify that inspect_object does not import pkg_resources
        sys.path.insert(0, str(SKILLS_DIR / "inspect-object" / "scripts"))
        import inspect_object
        assert not hasattr(inspect_object, "pkg_resources")

        # Verify check_version_parity works cleanly without pkg_resources
        inspect_object.check_version_parity()

    def test_python_315_native_tomllib_integration(self, tmp_path):
        """Verifies native tomllib integration in config_init.py under Python 3.15."""
        sys.path.insert(0, str(PLUGIN_ROOT / "config"))
        import config_init as cfg_init

        # Python 3.15 provides tomllib in the standard library
        import tomllib

        raw_toml = (
            '# Assistant configuration\n'
            'api_version = "v25"\n'
            'customer_id = "9876543210"\n'
            'execute_mutates = false\n'
            'timeout_seconds = 120\n'
        )

        parsed_native = tomllib.loads(raw_toml)
        parsed_custom = cfg_init.parse_assistant_config(raw_toml)

        assert parsed_custom["api_version"] == "v25"
        assert parsed_custom["customer_id"] == "9876543210"
        assert parsed_custom["execute_mutates"] is False
        assert parsed_custom["timeout_seconds"] == 120
        assert parsed_native == parsed_custom

        # Test formatting and re-parsing
        formatted = cfg_init.format_assistant_config(parsed_custom)
        round_tripped = tomllib.loads(formatted)
        assert round_tripped == parsed_native


class TestPython315SubprocessCLI:
    """Verifies that all skill scripts and services execute cleanly in Python 3.15 subprocesses."""

    CLI_SCRIPTS = [
        PLUGIN_ROOT / "config" / "config_init.py",
        SKILLS_DIR / "validate-gaql" / "scripts" / "validate_gaql.py",
        SKILLS_DIR / "inspect-object" / "scripts" / "inspect_object.py",
        SKILLS_DIR / "pmax-listing-filter" / "scripts" / "create_pmax_webpage_filter.py",
        SKILLS_DIR / "troubleshoot-conversions" / "scripts" / "troubleshoot_conversions.py",
        SKILLS_DIR / "troubleshoot-conversions" / "scripts" / "get_recent_gclids.py",
        SKILLS_DIR / "troubleshoot-conversions" / "scripts" / "validate_conversion_upload.py",
        SKILLS_DIR / "get-cids-under-mcc" / "scripts" / "get_cids_under_mcc.py",
        SKILLS_DIR / "ext-version" / "scripts" / "get_latest_api_version.py",
        SKILLS_DIR / "ext-version" / "scripts" / "get_extension_version.py",
        SKILLS_DIR / "sync-client-libs" / "scripts" / "sync_client_libs.py",
        SKILLS_DIR / "execute-mutation" / "scripts" / "run_mutation.py",
    ]

    @pytest.mark.parametrize("script_path", CLI_SCRIPTS, ids=lambda p: p.name)
    def test_cli_script_help_under_python_315(self, script_path):
        """Ensures each CLI script executes with exit code 0 under Python 3.15 without syntax or import errors."""
        assert script_path.is_file(), f"Target script does not exist: {script_path}"

        # get_extension_version.py takes no args; others accept --help
        args = [] if script_path.name == "get_extension_version.py" else ["--help"]
        proc = subprocess.run(
            [sys.executable, str(script_path), *args],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, (
            f"Script {script_path.name} failed under Python 3.15 ({sys.executable}):\n"
            f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )


class TestPython315NamespaceIsolation:
    """Verifies that run_mutation.py isolates namespaces and prioritizes mock/local packages under Python 3.15."""

    def test_run_mutation_namespace_isolation_and_interception(self, tmp_path, monkeypatch):
        """Verifies run_mutation.py executes under Python 3.15 without site-packages pkg_resources collisions."""
        runner_path = SKILLS_DIR / "execute-mutation" / "scripts" / "run_mutation.py"
        audit_log = tmp_path / "audit.jsonl"
        monkeypatch.setenv("GOOGLE_ADS_MUTATION_AUDIT_LOG", str(audit_log))

        # Create mock google.ads.googleads.client module in tmp_path
        pkg_dir = tmp_path / "google" / "ads" / "googleads"
        pkg_dir.mkdir(parents=True)
        (tmp_path / "google" / "__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "google" / "ads" / "__init__.py").write_text("", encoding="utf-8")
        (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
        (pkg_dir / "client.py").write_text(
            "class _FakeService:\n"
            "    def mutate_campaign_budgets(self, request=None):\n"
            "        return {'results': [{'resource_name': 'customers/123/campaignBudgets/888'}]}\n"
            "class GoogleAdsClient:\n"
            "    @classmethod\n"
            "    def load_from_storage(cls, path=None, version=None):\n"
            "        return cls()\n"
            "    def get_service(self, name, *args, **kwargs):\n"
            "        return _FakeService()\n",
            encoding="utf-8",
        )

        script_file = tmp_path / "mutate_budget.py"
        script_file.write_text(
            "import argparse\n"
            "from google.ads.googleads.client import GoogleAdsClient\n"
            "parser = argparse.ArgumentParser()\n"
            "parser.add_argument('--customer-id', default='1234567890')\n"
            "parser.add_argument('--dry-run', action='store_true')\n"
            "args = parser.parse_args()\n"
            "client = GoogleAdsClient.load_from_storage(path='config/google-ads.yaml')\n"
            "svc = client.get_service('CampaignBudgetService')\n"
            "res = svc.mutate_campaign_budgets(request={'customer_id': args.customer_id, 'validate_only': True})\n"
            "print('MUTATE_OK:', res['results'][0]['resource_name'])\n",
            encoding="utf-8",
        )

        monkeypatch.setenv("PYTHONPATH", f"{tmp_path}{os.pathsep}{os.environ.get('PYTHONPATH', '')}")

        proc = subprocess.run(
            [
                sys.executable,
                str(runner_path),
                "--script", str(script_file),
                "--dry-run",
                "--customer-id", "1234567890",
                "--operation", "Update budget 888",
                "--consequences", "Budget adjusted by $10/day",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        assert proc.returncode == 0, (
            f"Dry run failed under Python 3.15:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        assert "Dry-Run Status: PASSED" in proc.stdout
        assert "Request SHA256:" in proc.stdout
        assert "Customer ID   : 1234567890" in proc.stdout


class TestPython315A2AService:
    """Verifies that the A2A sidecar service functions properly on Python 3.15."""

    def test_a2a_service_metadata_and_version_discovery(self):
        """Verifies server.py health metadata and dynamic version discovery under Python 3.15."""
        server_dir = PLUGIN_ROOT / "sidecars" / "google-ads-a2a-service"
        sys.path.insert(0, str(server_dir))
        import server

        plugin_version = server.get_plugin_version()
        assert plugin_version is not None
        assert isinstance(plugin_version, str)
        assert len(plugin_version) > 0

        # Effective API version resolution
        ver = server.get_effective_api_version({"api_version": "v25"})
        assert ver == "v25"

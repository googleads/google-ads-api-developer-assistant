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

"""Unit tests for automated client_libs sync and version discovery."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Add script path to sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, ".."))
sync_script_dir = os.path.join(
    project_root, "plugins/agy/skills/sync-client-libs/scripts"
)
sys.path.insert(0, sync_script_dir)

import sync_client_libs  # noqa: E402


class TestSyncClientLibs(unittest.TestCase):

    def setUp(self) -> None:
        self.test_dir = tempfile.mkdtemp(prefix="test_sync_client_libs_")

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_discover_client_libs_dir_explicit(self) -> None:
        explicit_dir = os.path.join(self.test_dir, "client_libs")
        os.makedirs(explicit_dir, exist_ok=True)
        discovered = sync_client_libs.discover_client_libs_dir(explicit_dir)
        self.assertEqual(discovered, explicit_dir)

    def test_discover_client_libs_dir_nonexistent_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            sync_client_libs.discover_client_libs_dir("/nonexistent/path/here")

    def test_get_repo_slug_known_and_fallback(self) -> None:
        self.assertEqual(
            sync_client_libs.get_repo_slug("google-ads-python", "/dummy"),
            "googleads/google-ads-python",
        )
        self.assertEqual(
            sync_client_libs.get_repo_slug("google-ads-java", "/dummy"),
            "googleads/google-ads-java",
        )
        self.assertEqual(
            sync_client_libs.get_repo_slug("custom-lib", "/dummy"),
            "googleads/custom-lib",
        )

    def test_detect_installed_version_python_pyproject(self) -> None:
        py_lib = os.path.join(self.test_dir, "google-ads-python")
        os.makedirs(py_lib, exist_ok=True)
        pyproject_content = '[project]\nname = "google-ads"\nversion = "31.2.0"\n'
        with open(
            os.path.join(py_lib, "pyproject.toml"), "w", encoding="utf-8"
        ) as f:
            f.write(pyproject_content)

        version = sync_client_libs.detect_installed_version(
            "google-ads-python", py_lib
        )
        self.assertEqual(version, "31.2.0")

    def test_detect_installed_version_python_changelog(self) -> None:
        py_lib = os.path.join(self.test_dir, "google-ads-python-cl")
        os.makedirs(py_lib, exist_ok=True)
        changelog_content = "* 31.1.0\n- Google Ads API release.\n"
        with open(
            os.path.join(py_lib, "ChangeLog"), "w", encoding="utf-8"
        ) as f:
            f.write(changelog_content)

        version = sync_client_libs.detect_installed_version(
            "google-ads-python", py_lib
        )
        self.assertEqual(version, "31.1.0")

    def test_detect_installed_version_php(self) -> None:
        php_lib = os.path.join(self.test_dir, "google-ads-php")
        os.makedirs(php_lib, exist_ok=True)
        with open(
            os.path.join(php_lib, "composer.json"), "w", encoding="utf-8"
        ) as f:
            json.dump({"name": "googleads/google-ads-php", "version": "25.0.0"}, f)

        version = sync_client_libs.detect_installed_version(
            "google-ads-php", php_lib
        )
        self.assertEqual(version, "25.0.0")

    def test_detect_installed_version_java(self) -> None:
        java_lib = os.path.join(self.test_dir, "google-ads-java")
        os.makedirs(java_lib, exist_ok=True)
        pom_content = "<project><version>33.0.0</version></project>"
        with open(os.path.join(java_lib, "pom.xml"), "w", encoding="utf-8") as f:
            f.write(pom_content)

        version = sync_client_libs.detect_installed_version(
            "google-ads-java", java_lib
        )
        self.assertEqual(version, "33.0.0")

    def test_detect_installed_version_dotnet(self) -> None:
        dotnet_lib = os.path.join(self.test_dir, "google-ads-dotnet")
        os.makedirs(dotnet_lib, exist_ok=True)
        csproj_content = "<Project><PropertyGroup><Version>20.1.0</Version></PropertyGroup></Project>"
        with open(
            os.path.join(dotnet_lib, "Google.Ads.GoogleAds.csproj"),
            "w",
            encoding="utf-8",
        ) as f:
            f.write(csproj_content)

        version = sync_client_libs.detect_installed_version(
            "google-ads-dotnet", dotnet_lib
        )
        self.assertEqual(version, "20.1.0")

    def test_detect_installed_version_ruby(self) -> None:
        ruby_lib = os.path.join(self.test_dir, "google-ads-ruby")
        os.makedirs(ruby_lib, exist_ok=True)
        gemspec_content = (
            'Gem::Specification.new do |s|\n  s.version = "30.0.0"\nend\n'
        )
        with open(
            os.path.join(ruby_lib, "google-ads-ruby.gemspec"),
            "w",
            encoding="utf-8",
        ) as f:
            f.write(gemspec_content)

        version = sync_client_libs.detect_installed_version(
            "google-ads-ruby", ruby_lib
        )
        self.assertEqual(version, "30.0.0")

    def test_is_update_needed(self) -> None:
        # Outdated: installed older than github
        self.assertTrue(sync_client_libs.is_update_needed("31.1.0", "31.2.0"))
        self.assertTrue(sync_client_libs.is_update_needed("v31.0.0", "31.2.0"))
        self.assertTrue(sync_client_libs.is_update_needed(None, "31.2.0"))

        # Up to date
        self.assertFalse(sync_client_libs.is_update_needed("31.2.0", "31.2.0"))
        self.assertFalse(sync_client_libs.is_update_needed("v31.2.0", "31.2.0"))
        self.assertFalse(sync_client_libs.is_update_needed("32.0.0", "31.2.0"))
        self.assertFalse(sync_client_libs.is_update_needed("31.2.0", None))

    @patch("sync_client_libs.fetch_github_latest_release")
    def test_process_client_libs_check_only_up_to_date(
        self, mock_fetch: MagicMock
    ) -> None:
        mock_fetch.return_value = ("31.2.0", None)
        py_lib = os.path.join(self.test_dir, "google-ads-python")
        os.makedirs(py_lib, exist_ok=True)
        with open(
            os.path.join(py_lib, "pyproject.toml"), "w", encoding="utf-8"
        ) as f:
            f.write('version = "31.2.0"\n')

        results = sync_client_libs.process_client_libs(
            client_libs_dir=self.test_dir, check_only=True
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "UP_TO_DATE")
        self.assertEqual(results[0]["installed_version"], "31.2.0")
        self.assertEqual(results[0]["github_version"], "31.2.0")
        self.assertFalse(results[0]["updated"])

    @patch("sync_client_libs.fetch_github_latest_release")
    def test_process_client_libs_check_only_outdated(
        self, mock_fetch: MagicMock
    ) -> None:
        mock_fetch.return_value = ("31.2.0", None)
        py_lib = os.path.join(self.test_dir, "google-ads-python")
        os.makedirs(py_lib, exist_ok=True)
        with open(
            os.path.join(py_lib, "pyproject.toml"), "w", encoding="utf-8"
        ) as f:
            f.write('version = "31.0.0"\n')

        results = sync_client_libs.process_client_libs(
            client_libs_dir=self.test_dir, check_only=True
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "OUTDATED")
        self.assertEqual(results[0]["installed_version"], "31.0.0")
        self.assertEqual(results[0]["github_version"], "31.2.0")
        self.assertFalse(results[0]["updated"])

    @patch("sync_client_libs.update_codebase_via_archive")
    @patch("sync_client_libs.fetch_github_latest_release")
    def test_process_client_libs_auto_update_success(
        self, mock_fetch: MagicMock, mock_archive_update: MagicMock
    ) -> None:
        mock_fetch.return_value = ("31.2.0", "https://example.com/tar.gz")
        mock_archive_update.return_value = True

        py_lib = os.path.join(self.test_dir, "google-ads-python")
        os.makedirs(py_lib, exist_ok=True)
        with open(
            os.path.join(py_lib, "pyproject.toml"), "w", encoding="utf-8"
        ) as f:
            f.write('version = "31.0.0"\n')

        results = sync_client_libs.process_client_libs(
            client_libs_dir=self.test_dir, check_only=False
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "UPDATED")
        self.assertTrue(results[0]["updated"])
        mock_archive_update.assert_called_once()

    def test_sync_directories(self) -> None:
        src = os.path.join(self.test_dir, "src")
        dst = os.path.join(self.test_dir, "dst")
        os.makedirs(src, exist_ok=True)
        os.makedirs(dst, exist_ok=True)

        with open(os.path.join(src, "new_file.txt"), "w", encoding="utf-8") as f:
            f.write("new content")
        with open(os.path.join(dst, "old_file.txt"), "w", encoding="utf-8") as f:
            f.write("old content")
        with open(os.path.join(dst, "google-ads.yaml"), "w", encoding="utf-8") as f:
            f.write("keep me")

        success = sync_client_libs.sync_directories(src, dst)
        self.assertTrue(success)
        self.assertTrue(os.path.exists(os.path.join(dst, "new_file.txt")))
        self.assertFalse(os.path.exists(os.path.join(dst, "old_file.txt")))
        # Preserved config
        self.assertTrue(os.path.exists(os.path.join(dst, "google-ads.yaml")))


if __name__ == "__main__":
    unittest.main()

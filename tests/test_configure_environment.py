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

import sys
import os
import unittest
from unittest.mock import patch, MagicMock, mock_open

# Add the project root to sys.path so we can import the hook scripts
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, ".."))
hooks_dir = os.path.join(project_root, ".agents/hooks")
sys.path.append(hooks_dir)

import configure_environment  # noqa: E402

class TestConfigureEnvironment(unittest.TestCase):

    def test_get_version_success(self):
        with patch("subprocess.run") as mocked_run:
            mocked_run.return_value = MagicMock(stdout="2.1.0\n", check=True)
            version = configure_environment.get_version("dummy_script.py")
            self.assertEqual(version, "2.1.0")
            mocked_run.assert_called_once()

    def test_get_version_failure(self):
        with patch("subprocess.run") as mocked_run:
            mocked_run.side_effect = Exception("failed")
            version = configure_environment.get_version("dummy_script.py")
            self.assertEqual(version, "666")  # Fallback



    def test_parse_ruby_config(self):
        content = """
        c.developer_token = 'token123'
        c.client_id = "id456"
        c.client_secret = 'secret789'
        """
        with patch("builtins.open", mock_open(read_data=content)):
            data = configure_environment.parse_ruby_config("dummy.rb")
            self.assertEqual(data["developer_token"], "token123")
            self.assertEqual(data["client_id"], "id456")
            self.assertEqual(data["client_secret"], "secret789")

    def test_parse_ini_config(self):
        content = "[DEFAULT]\ndeveloperToken = token123\nclientId = 'id456'\n"
        with patch("builtins.open", mock_open(read_data=content)):
            data = configure_environment.parse_ini_config("dummy.ini")
            self.assertEqual(data["developer_token"], "token123")
            self.assertEqual(data["client_id"], "id456")

    def test_parse_properties_config(self):
        content = "api.googleads.developerToken=token123\napi.googleads.clientId=id456\n"
        with patch("builtins.open", mock_open(read_data=content)):
            data = configure_environment.parse_properties_config("dummy.properties")
            self.assertEqual(data["developer_token"], "token123")
            self.assertEqual(data["client_id"], "id456")

    def test_write_yaml_config_oauth2(self):
        data = {
            "developer_token": "token123",
            "client_id": "id456",
            "client_secret": "secret789",
            "refresh_token": "refresh000"
        }
        with patch("builtins.open", mock_open()) as mocked_file:
            success = configure_environment.write_yaml_config(data, "dummy.yaml")
            self.assertTrue(success)
            handle = mocked_file()
            handle.write.assert_any_call("developer_token: token123\n")
            handle.write.assert_any_call("client_id: id456\n")

    def test_write_yaml_config_service_account(self):
        data = {
            "developer_token": "token123",
            "json_key_file_path": "/path/to/key.json",
            "impersonated_email": "user@example.com"
        }
        with patch("builtins.open", mock_open()) as mocked_file:
            success = configure_environment.write_yaml_config(data, "dummy.yaml")
            self.assertTrue(success)
            handle = mocked_file()
            handle.write.assert_any_call("json_key_file_path: /path/to/key.json\n")
            handle.write.assert_any_call("impersonated_email: user@example.com\n")
            # Verify client_id is NOT written
            for call in handle.write.call_args_list:
                self.assertNotIn("client_id:", call[0][0])

    def test_copy_and_append_version(self):
        with patch("os.path.exists", return_value=True), \
             patch("shutil.copy2") as mocked_copy, \
             patch("builtins.open", mock_open()) as mocked_file:
            success = configure_environment.copy_and_append_version("home.yaml", "target.yaml", "2.1.0")
            self.assertTrue(success)
            mocked_copy.assert_called_once_with("home.yaml", "target.yaml")
            
            handle = mocked_file()
            handle.write.assert_called_once_with("\nads_assistant: 2.1.0\n")



    @patch("os.path.exists")
    @patch("subprocess.run")
    def test_create_virtual_env_success(self, mock_run, mock_exists):
        mock_exists.return_value = False
        mock_run.return_value = MagicMock(returncode=0)
        
        configure_environment.create_virtual_env("/mock/root")
        
        mock_exists.assert_called_once_with("/mock/root/.venv")
        self.assertEqual(mock_run.call_count, 3)
        
        called_args = [call[0][0] for call in mock_run.call_args_list]
        # First call: venv creation
        self.assertIn("-m", called_args[0])
        self.assertIn("venv", called_args[0])
        # Second call: pip upgrade
        self.assertIn("install", called_args[1])
        self.assertIn("--upgrade", called_args[1])
        self.assertIn("pip", called_args[1])
        # Third call: pip install
        self.assertIn("install", called_args[2])
        self.assertIn("google-ads", called_args[2])
        self.assertIn("pytest", called_args[2])

    @patch("os.path.exists")
    @patch("subprocess.run")
    def test_create_virtual_env_already_exists_up_to_date(self, mock_run, mock_exists):
        mock_exists.return_value = True
        # Mock version inside virtualenv to be the same as available python
        import sys
        available_version = list(sys.version_info[:3])
        mock_run.return_value = MagicMock(stdout=str(available_version) + "\n", returncode=0)

        configure_environment.create_virtual_env("/mock/root")

        # Should only run the version check, not create or install packages
        self.assertEqual(mock_run.call_count, 1)

    @patch("os.path.exists")
    @patch("shutil.rmtree")
    @patch("subprocess.run")
    def test_create_virtual_env_already_exists_outdated_recreates(self, mock_run, mock_rmtree, mock_exists):
        mock_exists.return_value = True
        # Mock version inside virtualenv to be older than available python
        mock_run.side_effect = [
            MagicMock(stdout="[3, 8, 0]\n", returncode=0), # first call: version check
            MagicMock(returncode=0), # second call: venv create
            MagicMock(returncode=0), # third call: pip upgrade
            MagicMock(returncode=0), # fourth call: pip install
        ]

        configure_environment.create_virtual_env("/mock/root")

        # Should recreate: call rmtree and then run the 3 venv creation/install commands
        mock_rmtree.assert_called_once_with("/mock/root/.venv")
        self.assertEqual(mock_run.call_count, 4)

    @patch("os.path.exists")
    @patch("shutil.rmtree")
    @patch("subprocess.run")
    def test_create_virtual_env_already_exists_broken_recreates(self, mock_run, mock_rmtree, mock_exists):
        mock_exists.return_value = True
        # Mock version check raising exception (broken env)
        mock_run.side_effect = [
            Exception("broken env"), # first call: version check fails
            MagicMock(returncode=0), # second call: venv create
            MagicMock(returncode=0), # third call: pip upgrade
            MagicMock(returncode=0), # fourth call: pip install
        ]

        configure_environment.create_virtual_env("/mock/root")

        # Should recreate: call rmtree and then run the 3 venv creation/install commands
        mock_rmtree.assert_called_once_with("/mock/root/.venv")
        self.assertEqual(mock_run.call_count, 4)


    @patch("builtins.print")
    def test_finish_hook_custom_vars(self, mock_print):
        import json
        with patch("os.environ", {"PATH": "/usr/bin"}):
            configure_environment.finish_hook("/mock/target.yaml", "2.1.0")
            
            mock_print.assert_called_once()
            args, kwargs = mock_print.call_args
            data = json.loads(args[0])
            self.assertIn("injectSteps", data)
            self.assertEqual(len(data["injectSteps"]), 1)
            step = data["injectSteps"][0]
            self.assertIn("ephemeralMessage", step)
            msg = step["ephemeralMessage"]
            self.assertIn("StartSession initialized", msg)
            self.assertIn("/mock/target.yaml", msg)
            self.assertIn("2.1.0", msg)

    @patch("configure_environment.create_virtual_env")
    @patch("configure_environment.get_version", return_value="2.1.0")
    @patch("configure_environment.copy_and_append_version", return_value=True)
    @patch("configure_environment.finish_hook")
    @patch("os.path.exists")
    @patch("os.path.getmtime")
    @patch("time.time")
    @patch("os.remove")
    @patch("os.makedirs")
    def test_main_deletes_stale_api_version(
        self,
        mock_makedirs,
        mock_remove,
        mock_time,
        mock_getmtime,
        mock_exists,
        mock_finish_hook,
        mock_copy,
        mock_get_version,
        mock_create_venv,
    ):
        def exists_side_effect(path):
            if "api_version.txt" in path:
                return True
            if "google-ads.yaml" in path:
                return True
            return False

        mock_exists.side_effect = exists_side_effect
        mock_getmtime.return_value = 1000.0
        mock_time.return_value = 1000.0 + 68401.0  # 19 hours + 1 second

        with patch("builtins.open", mock_open()):
            configure_environment.main()

        # Assert os.remove was called for api_version.txt
        # Using mock_remove.assert_any_call to see if it was called with the path containing api_version.txt
        called_paths = [call[0][0] for call in mock_remove.call_args_list]
        self.assertTrue(any("api_version.txt" in p for p in called_paths))

    @patch("configure_environment.create_virtual_env")
    @patch("configure_environment.get_version", return_value="2.1.0")
    @patch("configure_environment.copy_and_append_version", return_value=True)
    @patch("configure_environment.finish_hook")
    @patch("os.path.exists")
    @patch("os.path.getmtime")
    @patch("time.time")
    @patch("os.remove")
    @patch("os.makedirs")
    def test_main_does_not_delete_fresh_api_version(
        self,
        mock_makedirs,
        mock_remove,
        mock_time,
        mock_getmtime,
        mock_exists,
        mock_finish_hook,
        mock_copy,
        mock_get_version,
        mock_create_venv,
    ):
        def exists_side_effect(path):
            if "api_version.txt" in path:
                return True
            if "google-ads.yaml" in path:
                return True
            return False

        mock_exists.side_effect = exists_side_effect
        mock_getmtime.return_value = 1000.0
        mock_time.return_value = 1000.0 + 68399.0  # 19 hours - 1 second

        with patch("builtins.open", mock_open()):
            configure_environment.main()

        # Assert os.remove was NOT called for api_version.txt
        called_paths = [call[0][0] for call in mock_remove.call_args_list]
        self.assertFalse(any("api_version.txt" in p for p in called_paths))


if __name__ == "__main__":
    unittest.main()

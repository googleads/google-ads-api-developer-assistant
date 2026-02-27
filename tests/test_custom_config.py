import sys
import os
import unittest
from unittest.mock import patch, MagicMock, mock_open

# Add the project root to sys.path so we can import the hook scripts
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, ".."))
hooks_dir = os.path.join(project_root, ".gemini/hooks")
sys.path.append(hooks_dir)

import custom_config  # noqa: E402

class TestCustomConfig(unittest.TestCase):

    def test_get_version_success(self):
        with patch("subprocess.run") as mocked_run:
            mocked_run.return_value = MagicMock(stdout="2.1.0\n", check=True)
            version = custom_config.get_version("dummy_script.py")
            self.assertEqual(version, "2.1.0")
            mocked_run.assert_called_once()

    def test_get_version_failure(self):
        with patch("subprocess.run") as mocked_run:
            mocked_run.side_effect = Exception("failed")
            version = custom_config.get_version("dummy_script.py")
            self.assertEqual(version, "2.0.0")  # Fallback

    def test_parse_ruby_config(self):
        content = """
        c.developer_token = 'token123'
        c.client_id = "id456"
        c.client_secret = 'secret789'
        """
        with patch("builtins.open", mock_open(read_data=content)):
            data = custom_config.parse_ruby_config("dummy.rb")
            self.assertEqual(data["developer_token"], "token123")
            self.assertEqual(data["client_id"], "id456")
            self.assertEqual(data["client_secret"], "secret789")

    def test_parse_ini_config(self):
        content = "[DEFAULT]\ndeveloper_token = token123\nclient_id = 'id456'\n"
        with patch("builtins.open", mock_open(read_data=content)):
            data = custom_config.parse_ini_config("dummy.ini")
            self.assertEqual(data["developer_token"], "token123")
            self.assertEqual(data["client_id"], "id456")

    def test_parse_properties_config(self):
        content = "api.googleads.developerToken=token123\napi.googleads.clientId=id456\n"
        with patch("builtins.open", mock_open(read_data=content)):
            data = custom_config.parse_properties_config("dummy.properties")
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
            success = custom_config.write_yaml_config(data, "dummy.yaml", "2.1.0")
            self.assertTrue(success)
            handle = mocked_file()
            handle.write.assert_any_call("developer_token: token123\n")
            handle.write.assert_any_call("client_id: id456\n")
            handle.write.assert_any_call("gaada: \"2.1.0\"\n")

    def test_write_yaml_config_service_account(self):
        data = {
            "developer_token": "token123",
            "json_key_file_path": "/path/to/key.json",
            "impersonated_email": "user@example.com"
        }
        with patch("builtins.open", mock_open()) as mocked_file:
            success = custom_config.write_yaml_config(data, "dummy.yaml", "2.1.0")
            self.assertTrue(success)
            handle = mocked_file()
            handle.write.assert_any_call("json_key_file_path: /path/to/key.json\n")
            handle.write.assert_any_call("impersonated_email: user@example.com\n")
            # Verify client_id is NOT written
            for call in handle.write.call_args_list:
                self.assertNotIn("client_id:", call[0][0])

    def test_configure_language(self):
        with patch("os.path.exists", return_value=True), \
             patch("shutil.copy2") as mocked_copy, \
             patch("builtins.open", mock_open()) as mocked_file:
            success = custom_config.configure_language("Python", "home.yaml", "target.yaml", "2.1.0", is_python=True)
            self.assertTrue(success)
            mocked_copy.assert_called_once_with("home.yaml", "target.yaml")
            handle = mocked_file()
            handle.write.assert_called_with('\ngaada: "2.1.0"\n')

if __name__ == "__main__":
    unittest.main()

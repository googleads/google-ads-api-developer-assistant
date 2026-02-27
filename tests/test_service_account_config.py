import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# Add .gemini/hooks to sys.path
script_dir = os.path.dirname(os.path.abspath(__file__))
hooks_dir = os.path.join(script_dir, "../.gemini/hooks")
sys.path.append(hooks_dir)

import custom_config

class TestCustomConfig(unittest.TestCase):

    def test_parse_ruby_config_service_account(self):
        content = """
        GoogleAds::Config.new do |c|
          c.developer_token = 'TEST_TOKEN'
          c.json_key_file_path = '/path/to/key.json'
          c.impersonated_email = 'user@example.com'
        end
        """
        with patch("builtins.open", unittest.mock.mock_open(read_data=content)):
            data = custom_config.parse_ruby_config("dummy.rb")
            self.assertEqual(data["json_key_file_path"], "/path/to/key.json")
            self.assertEqual(data["impersonated_email"], "user@example.com")

    def test_parse_ini_config_service_account(self):
        content = """
[GOOGLE_ADS]
developer_token = "TEST_TOKEN"
json_key_file_path = "/path/to/key.json"
impersonated_email = "user@example.com"
        """
        with patch("builtins.open", unittest.mock.mock_open(read_data=content)):
            data = custom_config.parse_ini_config("dummy.ini")
            self.assertEqual(data["json_key_file_path"], "/path/to/key.json")
            self.assertEqual(data["impersonated_email"], "user@example.com")

    def test_parse_properties_config_service_account(self):
        content = """
api.googleads.developerToken=TEST_TOKEN
api.googleads.oAuth2SecretsJsonPath=/path/to/key.json
api.googleads.oAuth2PrnEmail=user@example.com
        """
        with patch("builtins.open", unittest.mock.mock_open(read_data=content)):
            data = custom_config.parse_properties_config("dummy.properties")
            self.assertEqual(data["json_key_file_path"], "/path/to/key.json")
            self.assertEqual(data["impersonated_email"], "user@example.com")

    def test_write_yaml_config_service_account(self):
        data = {
            "developer_token": "TEST_TOKEN",
            "json_key_file_path": "/path/to/key.json",
            "impersonated_email": "user@example.com"
        }
        with patch("builtins.open", unittest.mock.mock_open()) as mocked_file:
            custom_config.write_yaml_config(data, "dummy.yaml", "2.0.0")
            mocked_file.assert_called_once_with("dummy.yaml", "w")
            handle = mocked_file()
            # Verify json_key_file_path is written
            handle.write.assert_any_call("json_key_file_path: /path/to/key.json\n")
            # Verify client_id is NOT written
            for call in handle.write.call_args_list:
                self.assertNotIn("client_id:", call[0][0])

if __name__ == "__main__":
    unittest.main()

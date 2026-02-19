# Copyright 2025 Google LLC
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
from unittest.mock import MagicMock, patch
from io import StringIO

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from google.ads.googleads.errors import GoogleAdsException
from api_examples.gaql_validator import main

class TestGAQLValidator(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.mock_ga_service = MagicMock()
        self.mock_client.get_service.return_value = self.mock_ga_service
        self.customer_id = "1234567890"
        self.api_version = "v23"
        self.test_query = "SELECT campaign.id FROM campaign"
        
        self.captured_output = StringIO()
        sys.stdout = self.captured_output

    def tearDown(self):
        sys.stdout = sys.__stdout__

    @patch("importlib.import_module")
    def test_main_success(self, mock_import):
        # Setup mocks
        mock_module = MagicMock()
        mock_import.return_value = mock_module
        mock_request_class = MagicMock()
        setattr(mock_module, "SearchGoogleAdsRequest", mock_request_class)

        # Execute
        main(
            client=self.mock_client,
            customer_id=self.customer_id,
            api_version=self.api_version,
            query=self.test_query
        )

        # Verify
        self.mock_ga_service.search.assert_called_once()
        output = self.captured_output.getvalue()
        self.assertIn("SUCCESS: GAQL query is valid.", output)

    @patch("importlib.import_module")
    def test_main_validation_failure(self, mock_import):
        # Setup mocks
        mock_module = MagicMock()
        mock_import.return_value = mock_module
        mock_request_class = MagicMock()
        setattr(mock_module, "SearchGoogleAdsRequest", mock_request_class)

        # Setup GoogleAdsException
        error = MagicMock()
        error.message = "Invalid query"
        error.location.field_path_elements = [MagicMock(field_name="query")]
        
        self.mock_ga_service.search.side_effect = GoogleAdsException(
            error=MagicMock(),
            call=MagicMock(),
            failure=MagicMock(errors=[error]),
            request_id="test-id"
        )

        # Execute
        with self.assertRaises(SystemExit) as cm:
            main(
                client=self.mock_client,
                customer_id=self.customer_id,
                api_version=self.api_version,
                query=self.test_query
            )

        # Verify
        self.assertEqual(cm.exception.code, 1)
        output = self.captured_output.getvalue()
        self.assertIn("FAILURE: Query validation failed with Request ID test-id", output)
        self.assertIn("- Invalid query", output)

    def test_main_no_query(self):
        # Execute
        with self.assertRaises(SystemExit) as cm:
            main(
                client=self.mock_client,
                customer_id=self.customer_id,
                api_version=self.api_version,
                query=""
            )

        # Verify
        self.assertEqual(cm.exception.code, 1)
        output = self.captured_output.getvalue()
        self.assertIn("Error: No query provided.", output)

    @patch("importlib.import_module")
    def test_main_import_error(self, mock_import):
        # Setup mocks
        mock_import.side_effect = ImportError()

        # Execute
        with self.assertRaises(SystemExit) as cm:
            main(
                client=self.mock_client,
                customer_id=self.customer_id,
                api_version=self.api_version,
                query=self.test_query
            )

        # Verify
        self.assertEqual(cm.exception.code, 1)
        output = self.captured_output.getvalue()
        self.assertIn(f"CRITICAL ERROR: Could not import SearchGoogleAdsRequest for {self.api_version.lower()}.", output)

if __name__ == "__main__":
    unittest.main()

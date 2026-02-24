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

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

import unittest
from unittest.mock import MagicMock
from io import StringIO

from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.client import GoogleAdsClient

# Import functions from the script
from api_examples.get_change_history import main


class TestGetChangeHistory(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock(spec=GoogleAdsClient)
        self.mock_ga_service = MagicMock()
        self.mock_client.get_service.return_value = self.mock_ga_service
        self.customer_id = "1234567890"
        self.captured_output = StringIO()
        sys.stdout = self.captured_output

    def tearDown(self):
        sys.stdout = sys.__stdout__

    def test_main_success(self):
        mock_row = MagicMock()
        mock_row.change_status.resource_name = "customers/123/campaigns/456"
        mock_row.change_status.last_change_date_time = "2026-02-24 10:00:00"
        mock_row.change_status.resource_type.name = "CAMPAIGN"
        mock_row.change_status.resource_status.name = "ADDED"

        mock_batch = MagicMock()
        mock_batch.results = [mock_row]

        self.mock_ga_service.search_stream.return_value = [mock_batch]

        main(self.mock_client, self.customer_id, "2026-02-17", "2026-02-24")

        self.mock_ga_service.search_stream.assert_called_once()
        output = self.captured_output.getvalue()
        self.assertIn("CAMPAIGN", output)
        self.assertIn("ADDED", output)
        self.assertIn("customers/123/campaigns/456", output)

    def test_main_google_ads_exception(self):
        mock_failure = MagicMock()
        mock_failure.errors = [MagicMock(message="Error details")]
        
        self.mock_ga_service.search_stream.side_effect = GoogleAdsException(
            error=MagicMock(),
            failure=mock_failure,
            request_id="test_request_id",
            call=MagicMock(),
        )

        main(self.mock_client, self.customer_id, "2026-02-17", "2026-02-24")
        self.assertIn("Error (Request ID test_request_id): Error details", self.captured_output.getvalue())


if __name__ == "__main__":
    unittest.main()

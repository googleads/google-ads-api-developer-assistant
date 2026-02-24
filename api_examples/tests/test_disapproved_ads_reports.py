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
from unittest.mock import MagicMock, patch, mock_open
from io import StringIO

from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.client import GoogleAdsClient

# Import functions from the script
from api_examples.disapproved_ads_reports import main


class TestDisapprovedAdsReports(unittest.TestCase):
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
        mock_row.campaign.id = 123
        mock_row.campaign.name = "Test Campaign"
        mock_row.ad_group_ad.ad.id = 456
        mock_row.ad_group_ad.policy_summary.approval_status.name = "DISAPPROVED"
        
        mock_entry = MagicMock()
        mock_entry.topic = "Adult Content"
        mock_row.ad_group_ad.policy_summary.policy_topic_entries = [mock_entry]

        mock_batch = MagicMock()
        mock_batch.results = [mock_row]

        self.mock_ga_service.search_stream.return_value = [mock_batch]

        output_file = "test_disapproved.csv"
        with patch("builtins.open", new_callable=mock_open) as mock_file_open:
            main(self.mock_client, self.customer_id, output_file)

            self.mock_ga_service.search_stream.assert_called_once()
            handle = mock_file_open()
            handle.write.assert_any_call("Campaign ID,Campaign,Ad ID,Status,Topics\r\n")
            handle.write.assert_any_call("123,Test Campaign,456,DISAPPROVED,Adult Content\r\n")
            self.assertIn(f"Disapproved ads report written to {output_file}", self.captured_output.getvalue())

    def test_main_google_ads_exception(self):
        mock_error = MagicMock()
        mock_error.code.return_value.name = "REQUEST_ERROR"
        
        self.mock_ga_service.search_stream.side_effect = GoogleAdsException(
            error=mock_error,
            failure=MagicMock(errors=[MagicMock(message="Error details")]),
            request_id="test_request_id",
            call=MagicMock(),
        )

        main(self.mock_client, self.customer_id, "test.csv")
        self.assertIn("Request ID test_request_id failed: REQUEST_ERROR", self.captured_output.getvalue())


if __name__ == "__main__":
    unittest.main()

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
from api_examples.ai_max_reports import (
    main,
    _write_to_csv,
    get_campaign_details,
    get_search_terms,
)


class TestAIMaxReports(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock(spec=GoogleAdsClient)
        self.mock_ga_service = MagicMock()
        self.mock_client.get_service.return_value = self.mock_ga_service
        self.customer_id = "1234567890"
        self.captured_output = StringIO()
        sys.stdout = self.captured_output

    def tearDown(self):
        sys.stdout = sys.__stdout__

    # --- Test _write_to_csv ---
    @patch("builtins.open", new_callable=mock_open)
    def test_write_to_csv(self, mock_file_open):
        headers = ["Header1", "Header2"]
        rows = [["Value1", "ValueA"], ["Value2", "ValueB"]]

        file_path = "test.csv"
        _write_to_csv(file_path, headers, rows)

        mock_file_open.assert_called_once_with(
            file_path, "w", newline="", encoding="utf-8"
        )
        handle = mock_file_open()
        handle.write.assert_any_call("Header1,Header2\r\n")
        handle.write.assert_any_call("Value1,ValueA\r\n")
        handle.write.assert_any_call("Value2,ValueB\r\n")
        self.assertIn(f"Report written to {file_path}", self.captured_output.getvalue())

    # --- Test get_campaign_details ---
    def test_get_campaign_details(self):
        mock_row = MagicMock()
        mock_row.campaign.id = 123
        mock_row.campaign.name = "AI Max Campaign 1"
        mock_row.expanded_landing_page_view.expanded_final_url = "http://example.com"
        mock_row.campaign.ai_max_setting.enable_ai_max = True

        mock_batch = MagicMock()
        mock_batch.results = [mock_row]

        self.mock_ga_service.search_stream.return_value = [mock_batch]

        with patch("builtins.open", new_callable=mock_open) as mock_file_open:
            get_campaign_details(self.mock_client, self.customer_id)

            self.mock_ga_service.search_stream.assert_called_once()
            handle = mock_file_open()
            handle.write.assert_any_call("ID,Name,URL,Enabled\r\n")
            handle.write.assert_any_call("123,AI Max Campaign 1,http://example.com,True\r\n")

    # --- Test get_search_terms ---
    def test_get_search_terms(self):
        mock_row = MagicMock()
        mock_row.campaign.id = 789
        mock_row.campaign.name = "AI Max Campaign 3"
        mock_row.ai_max_search_term_ad_combination_view.search_term = "test search term"
        mock_row.metrics.impressions = 1000
        mock_row.metrics.clicks = 50
        mock_row.metrics.conversions = 5.0

        mock_batch = MagicMock()
        mock_batch.results = [mock_row]

        self.mock_ga_service.search_stream.return_value = [mock_batch]

        with patch("builtins.open", new_callable=mock_open) as mock_file_open:
            get_search_terms(self.mock_client, self.customer_id)

            self.mock_ga_service.search_stream.assert_called_once()
            handle = mock_file_open()
            handle.write.assert_any_call("ID,Name,Term,Impr,Clicks,Conv\r\n")
            handle.write.assert_any_call("789,AI Max Campaign 3,test search term,1000,50,5.0\r\n")

    # --- Test main function ---
    def test_main_campaign_details_report(self):
        with patch("api_examples.ai_max_reports.get_campaign_details") as mock_get_campaign_details:
            main(self.mock_client, self.customer_id, "campaign_details")
            mock_get_campaign_details.assert_called_once_with(self.mock_client, self.customer_id)

    def test_main_search_terms_report(self):
        with patch("api_examples.ai_max_reports.get_search_terms") as mock_get_search_terms:
            main(self.mock_client, self.customer_id, "search_terms")
            mock_get_search_terms.assert_called_once_with(self.mock_client, self.customer_id)

    def test_main_google_ads_exception(self):
        mock_error = MagicMock()
        mock_error.code.return_value.name = "REQUEST_ERROR"
        
        self.mock_ga_service.search_stream.side_effect = GoogleAdsException(
            error=mock_error,
            failure=MagicMock(errors=[MagicMock(message="Error details")]),
            request_id="test_request_id",
            call=MagicMock(),
        )

        main(self.mock_client, self.customer_id, "campaign_details")
        self.assertIn("Request ID test_request_id failed: REQUEST_ERROR", self.captured_output.getvalue())


if __name__ == "__main__":
    unittest.main()

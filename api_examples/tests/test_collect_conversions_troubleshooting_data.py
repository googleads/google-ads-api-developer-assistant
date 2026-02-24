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
from unittest.mock import MagicMock, patch, mock_open
from io import StringIO

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.client import GoogleAdsClient
from api_examples.collect_conversions_troubleshooting_data import main


class TestCollectConversionsTroubleshootingData(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock(spec=GoogleAdsClient)
        self.mock_ga_service = MagicMock()
        self.mock_client.get_service.return_value = self.mock_ga_service
        self.customer_id = "1234567890"

        self.captured_output = StringIO()
        sys.stdout = self.captured_output

    def tearDown(self):
        sys.stdout = sys.__stdout__

    @patch("os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    @patch("glob.glob")
    def test_main_success_healthy(self, mock_glob, mock_file_open, mock_makedirs):
        mock_glob.return_value = []
        
        # 1. Customer Settings Mock
        mock_row_customer = MagicMock()
        mock_row_customer.customer.descriptive_name = "Test Customer"
        mock_row_customer.customer.conversion_tracking_setting.accepted_customer_data_terms = True
        mock_row_customer.customer.conversion_tracking_setting.enhanced_conversions_for_leads_enabled = True

        # 2. Action Summary Mock
        mock_row_as = MagicMock()
        asum = mock_row_as.offline_conversion_upload_conversion_action_summary
        asum.conversion_action_name = "Test Action"
        asum.successful_event_count = 50
        asum.total_event_count = 50
        
        ds = MagicMock()
        ds.upload_date = "2026-02-24"
        ds.successful_count = 10
        ds.failed_count = 0
        asum.daily_summaries = [ds]

        mock_batch_customer = MagicMock()
        mock_batch_customer.results = [mock_row_customer]
        
        mock_batch_as = MagicMock()
        mock_batch_as.results = [mock_row_as]

        self.mock_ga_service.search_stream.side_effect = [
            [mock_batch_customer],
            [mock_batch_as]
        ]

        main(self.mock_client, self.customer_id)

        handle = mock_file_open()
        written_content = "".join(call.args[0] for call in handle.write.call_args_list)
        
        self.assertIn("Diagnostic Report for Customer ID: 1234567890", written_content)
        self.assertIn("Customer: Test Customer", written_content)
        self.assertIn("Action: Test Action (Total Success: 50/50)", written_content)
        self.assertIn("No blocking errors detected.", written_content)

    @patch("os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    @patch("glob.glob")
    def test_main_unhealthy_terms_not_accepted(self, mock_glob, mock_file_open, mock_makedirs):
        mock_glob.return_value = []
        
        # 1. Customer Settings Mock (Terms NOT accepted)
        mock_row_customer = MagicMock()
        mock_row_customer.customer.descriptive_name = "Test Customer"
        mock_row_customer.customer.conversion_tracking_setting.accepted_customer_data_terms = False

        mock_batch_customer = MagicMock()
        mock_batch_customer.results = [mock_row_customer]
        
        self.mock_ga_service.search_stream.side_effect = [
            [mock_batch_customer],
            []
        ]

        main(self.mock_client, self.customer_id)

        handle = mock_file_open()
        written_content = "".join(call.args[0] for call in handle.write.call_args_list)
        
        self.assertIn("CRITICAL: Customer Data Terms NOT accepted.", written_content)

    @patch("os.makedirs")
    @patch("builtins.open", new_callable=mock_open)
    @patch("glob.glob")
    def test_main_google_ads_exception(self, mock_glob, mock_file_open, mock_makedirs):
        mock_glob.return_value = []
        
        self.mock_ga_service.search_stream.side_effect = GoogleAdsException(
            error=MagicMock(),
            failure=MagicMock(errors=[MagicMock(message="Internal error")]),
            request_id="test_request_id",
            call=MagicMock(),
        )

        main(self.mock_client, self.customer_id)
        
        output = self.captured_output.getvalue()
        self.assertIn("ERROR: Query failed (Request ID: test_request_id)", output)
        self.assertIn("Internal error", output)


if __name__ == "__main__":
    unittest.main()

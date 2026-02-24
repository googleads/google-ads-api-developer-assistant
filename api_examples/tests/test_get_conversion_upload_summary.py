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
from api_examples.get_conversion_upload_summary import main


class TestGetConversionUploadSummary(unittest.TestCase):
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
        mock_summary = mock_row.offline_conversion_upload_client_summary
        mock_summary.client.name = "GOOGLE_ADS_API"
        mock_summary.status.name = "SUCCESS"
        mock_summary.total_event_count = 10
        mock_summary.successful_event_count = 10
        
        mock_ds = MagicMock()
        mock_ds.upload_date = "2026-02-24"
        mock_ds.successful_count = 10
        mock_ds.failed_count = 0
        mock_summary.daily_summaries = [mock_ds]

        mock_batch = MagicMock()
        mock_batch.results = [mock_row]

        self.mock_ga_service.search_stream.return_value = [mock_batch]

        main(self.mock_client, self.customer_id)

        self.mock_ga_service.search_stream.assert_called_once()
        output = self.captured_output.getvalue()
        self.assertIn("Client: GOOGLE_ADS_API, Status: SUCCESS", output)
        self.assertIn("Total: 10, Success: 10", output)
        self.assertIn("2026-02-24: 10/10 successful", output)

    def test_main_google_ads_exception(self):
        mock_error = MagicMock()
        mock_error.code.return_value.name = "REQUEST_ERROR"
        
        self.mock_ga_service.search_stream.side_effect = GoogleAdsException(
            error=mock_error,
            failure=MagicMock(errors=[MagicMock(message="Error details")]),
            request_id="test_request_id",
            call=MagicMock(),
        )

        main(self.mock_client, self.customer_id)
        self.assertIn("Request ID test_request_id failed: REQUEST_ERROR", self.captured_output.getvalue())


if __name__ == "__main__":
    unittest.main()

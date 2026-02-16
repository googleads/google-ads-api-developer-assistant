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
import tempfile
import shutil
from unittest.mock import MagicMock, patch
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

        # Patching os.makedirs and open to avoid actual file system interaction
        self.test_dir = tempfile.mkdtemp()
        self.patch_makedirs = patch("os.makedirs")
        self.mock_makedirs = self.patch_makedirs.start()
        
        # We need to mock open carefully because it's used by many things
        self.patch_open = patch("builtins.open", unittest.mock.mock_open())
        self.mock_open = self.patch_open.start()

        self.captured_output = StringIO()
        sys.stdout = self.captured_output

    def tearDown(self):
        sys.stdout = sys.__stdout__
        self.patch_makedirs.stop()
        self.patch_open.stop()
        shutil.rmtree(self.test_dir)

    def test_main_success_healthy(self):
        # 1. Customer Settings Mock
        mock_batch_customer = MagicMock()
        mock_row_customer = MagicMock()
        mock_row_customer.customer.descriptive_name = "Test Customer"
        mock_row_customer.customer.conversion_tracking_setting.accepted_customer_data_terms = True
        mock_row_customer.customer.conversion_tracking_setting.enhanced_conversions_for_leads_enabled = True
        mock_batch_customer.results = [mock_row_customer]

        # 2. Conversion Actions Mock
        mock_batch_ca = MagicMock()
        mock_row_ca = MagicMock()
        mock_row_ca.conversion_action.id = 123
        mock_row_ca.conversion_action.name = "Test Action"
        mock_row_ca.conversion_action.type.name = "UPLOAD_CLICKS"
        mock_row_ca.conversion_action.status.name = "ENABLED"
        mock_batch_ca.results = [mock_row_ca]

        # 3. Client Summary Mock
        mock_batch_cs = MagicMock()
        mock_row_cs = MagicMock()
        mock_cs = mock_row_cs.offline_conversion_upload_client_summary
        mock_cs.client.name = "GOOGLE_ADS_API"
        mock_cs.status.name = "SUCCESS"
        mock_cs.successful_event_count = 100
        mock_cs.total_event_count = 100
        mock_cs.last_upload_date_time = "2024-01-01 12:00:00"
        mock_batch_cs.results = [mock_row_cs]

        # 4. Action Summary Mock
        mock_batch_as = MagicMock()
        mock_row_as = MagicMock()
        mock_as = mock_row_as.offline_conversion_upload_conversion_action_summary
        mock_as.conversion_action_name = "Test Action"
        mock_as.status.name = "SUCCESS"
        mock_as.successful_event_count = 50
        mock_as.total_event_count = 50
        mock_as.last_upload_date_time = "2024-01-01 12:00:00"
        mock_batch_as.results = [mock_row_as]

        self.mock_ga_service.search_stream.side_effect = [
            [mock_batch_customer],
            [mock_batch_ca],
            [mock_batch_cs],
            [mock_batch_as]
        ]

        main(self.mock_client, self.customer_id)

        # Verify file write
        self.mock_open.assert_called()
        handle = self.mock_open()
        
        # Collect all written content
        written_content = "".join(call.args[0] for call in handle.write.call_args_list)
        
        self.assertIn("Overall Status: HEALTHY", written_content)
        self.assertIn("Customer Data Terms Accepted: True", written_content)
        self.assertIn("Type=UPLOAD_CLICKS", written_content)
        self.assertIn("Status=SUCCESS", written_content)

    def test_main_unhealthy_terms_not_accepted(self):
        # 1. Customer Settings Mock (Terms NOT accepted)
        mock_batch_customer = MagicMock()
        mock_row_customer = MagicMock()
        mock_row_customer.customer.descriptive_name = "Test Customer"
        mock_row_customer.customer.conversion_tracking_setting.accepted_customer_data_terms = False
        mock_row_customer.customer.conversion_tracking_setting.enhanced_conversions_for_leads_enabled = True
        mock_batch_customer.results = [mock_row_customer]

        # Mocks for other queries (empty or success)
        mock_batch_empty = MagicMock()
        mock_batch_empty.results = []

        self.mock_ga_service.search_stream.side_effect = [
            [mock_batch_customer],
            [mock_batch_empty],
            [mock_batch_empty],
            [mock_batch_empty]
        ]

        main(self.mock_client, self.customer_id)

        handle = self.mock_open()
        written_content = "".join(call.args[0] for call in handle.write.call_args_list)
        
        self.assertIn("Overall Status: UNHEALTHY", written_content)
        self.assertIn("CRITICAL: Customer Data Terms NOT accepted", written_content)

    def test_main_google_ads_exception(self):
        mock_error = MagicMock()
        mock_error.code.return_value.name = "INTERNAL_ERROR"
        mock_failure = MagicMock()
        mock_failure.errors = [MagicMock(message="Internal error")]
        
        self.mock_ga_service.search_stream.side_effect = GoogleAdsException(
            error=mock_error,
            call=MagicMock(),
            failure=mock_failure,
            request_id="test_request_id"
        )

        with self.assertRaises(SystemExit) as cm:
            main(self.mock_client, self.customer_id)
        
        self.assertEqual(cm.exception.code, 1)
        output = self.captured_output.getvalue()
        self.assertIn("Request with ID 'test_request_id' failed with status 'INTERNAL_ERROR'", output)


if __name__ == "__main__":
    unittest.main()

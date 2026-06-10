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

import os
import sys
import unittest
from io import StringIO
from unittest.mock import MagicMock

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../..")))

from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.client import GoogleAdsClient
from get_recent_gclids import get_recent_gclids


class TestGetRecentGCLIDs(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock(spec=GoogleAdsClient)
        self.mock_ga_service = MagicMock()
        self.mock_client.get_service.return_value = self.mock_ga_service
        self.customer_id = "1234567890"
        self.date = "2026-05-18"

        self.captured_output = StringIO()
        sys.stdout = self.captured_output

    def tearDown(self):
        sys.stdout = sys.__stdout__

    def test_get_recent_gclids_success(self):
        # Mock query results
        mock_row_1 = MagicMock()
        mock_row_1.click_view.gclid = "gclid_1"
        mock_row_1.segments.date = self.date

        mock_row_2 = MagicMock()
        mock_row_2.click_view.gclid = "gclid_2"
        mock_row_2.segments.date = self.date

        self.mock_ga_service.search.return_value = [mock_row_1, mock_row_2]

        get_recent_gclids(self.mock_client, self.customer_id, self.date)

        output = self.captured_output.getvalue()
        self.assertIn("GCLID                                    | Click Date", output)
        self.assertIn("gclid_1                                  | 2026-05-18", output)
        self.assertIn("gclid_2                                  | 2026-05-18", output)

    def test_get_recent_gclids_empty(self):
        self.mock_ga_service.search.return_value = []

        get_recent_gclids(self.mock_client, self.customer_id, self.date)

        output = self.captured_output.getvalue()
        self.assertIn(f"No GCLIDs found on date '{self.date}'.", output)

    def test_get_recent_gclids_google_ads_exception(self):
        self.mock_ga_service.search.side_effect = GoogleAdsException(
            error=MagicMock(),
            failure=MagicMock(errors=[MagicMock(message="API error message")]),
            request_id="test_req_id",
            call=MagicMock(),
        )

        with self.assertRaises(SystemExit) as cm:
            get_recent_gclids(self.mock_client, self.customer_id, self.date)

        self.assertEqual(cm.exception.code, 1)
        output = self.captured_output.getvalue()
        self.assertIn("Request failed with status", output)
        self.assertIn("API error message", output)


if __name__ == "__main__":
    unittest.main()

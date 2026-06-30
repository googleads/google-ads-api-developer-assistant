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

"""Unit tests for create_pmax_webpage_filter skill script."""

import io
import os
import sys
import unittest
from unittest import mock

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
)

import create_pmax_webpage_filter
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException


class TestCreatePMaxWebpageFilter(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_client = mock.create_autospec(GoogleAdsClient, instance=True)
        self.mock_client.enums = mock.MagicMock()
        self.mock_service = mock.MagicMock()
        self.mock_client.get_service.return_value = self.mock_service

    @mock.patch.object(sys, "stdout", new_callable=io.StringIO)
    def test_create_pmax_webpage_filter_success(self, mock_stdout) -> None:
        # Setup mocks for types
        self.mock_client.get_type.side_effect = lambda name: mock.MagicMock()

        mock_result = mock.MagicMock()
        mock_result.resource_name = "customers/12345678/assetGroupListingGroupFilters/root"
        mock_response = mock.MagicMock()
        mock_response.results = [mock_result]

        self.mock_service.mutate_asset_group_listing_group_filters.return_value = mock_response

        create_pmax_webpage_filter.create_pmax_webpage_filter(
            customer_id="12345678",
            asset_group_id="98765",
            url_exclusion="/blog",
            api_version="v24",
            client=self.mock_client,
            validate_only=True,
        )

        self.mock_service.mutate_asset_group_listing_group_filters.assert_called_once()
        output = mock_stdout.getvalue()
        self.assertIn("SUCCESS: Subdivision Webpage Listing Filter tree validated/created successfully.", output)

    @mock.patch.object(sys, "stdout", new_callable=io.StringIO)
    def test_create_pmax_webpage_filter_api_failure(self, mock_stdout) -> None:
        self.mock_client.get_type.side_effect = lambda name: mock.MagicMock()
        
        mock_error = mock.MagicMock()
        mock_error.message = "Invalid listing filter structure."

        self.mock_service.mutate_asset_group_listing_group_filters.side_effect = GoogleAdsException(
            error=mock.MagicMock(),
            failure=mock.MagicMock(errors=[mock_error]),
            request_id="dummy_req_id",
            call=mock.MagicMock(),
        )

        with self.assertRaises(SystemExit) as cm:
            create_pmax_webpage_filter.create_pmax_webpage_filter(
                customer_id="12345678",
                asset_group_id="98765",
                url_exclusion="/blog",
                api_version="v24",
                client=self.mock_client,
                validate_only=True,
            )
        self.assertEqual(cm.exception.code, 1)
        output = mock_stdout.getvalue()
        self.assertIn("FAILURE: Listing Filter creation failed", output)
        self.assertIn("Invalid listing filter structure.", output)


if __name__ == "__main__":
    unittest.main()

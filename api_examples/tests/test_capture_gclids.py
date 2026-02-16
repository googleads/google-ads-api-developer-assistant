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

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

import unittest
from unittest.mock import MagicMock
from io import StringIO

from google.ads.googleads.errors import GoogleAdsException
from google.ads.googleads.client import GoogleAdsClient

# Import the main function from the script
from api_examples.capture_gclids import main


class TestCaptureGCLIDs(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock(spec=GoogleAdsClient)
        self.mock_conversion_upload_service = MagicMock()
        self.mock_conversion_action_service = MagicMock()

        self.mock_client.get_service.side_effect = [
            self.mock_conversion_upload_service,  # First call to get_service
            self.mock_conversion_action_service,  # Second call to get_service
        ]

        self.mock_click_conversion = MagicMock()
        self.mock_upload_click_conversions_request = MagicMock()
        self.mock_client.get_type.side_effect = [
            self.mock_click_conversion,  # For ClickConversion
            self.mock_upload_click_conversions_request,  # For UploadClickConversionsRequest
        ]

        self.customer_id = "1234567890"
        self.gclid = "test_gclid_123"
        self.conversion_date_time = "2026-02-16 12:32:45-08:00"
        self.captured_output = StringIO()
        sys.stdout = self.captured_output

    def tearDown(self):
        sys.stdout = sys.__stdout__

    def test_main_successful_upload(self):
        mock_conversion_action_response = MagicMock()
        mock_conversion_action_response.resource_name = (
            "customers/123/conversionActions/456"
        )
        self.mock_conversion_action_service.search_conversion_actions.return_value = [
            mock_conversion_action_response
        ]

        mock_upload_response = MagicMock()
        mock_upload_response.results = [MagicMock(gclid="test_gclid_123")]
        self.mock_conversion_upload_service.upload_click_conversions.return_value = (
            mock_upload_response
        )

        # Make conversions attribute a real list for testing append behavior
        self.mock_upload_click_conversions_request.conversions = []

        main(self.mock_client, self.customer_id, self.gclid, self.conversion_date_time)

        # Assert get_service calls
        self.mock_client.get_service.assert_any_call("ConversionUploadService")
        self.mock_client.get_service.assert_any_call("ConversionActionService")

        # Assert get_type calls
        self.mock_client.get_type.assert_any_call("ClickConversion")
        self.mock_client.get_type.assert_any_call("UploadClickConversionsRequest")

        # Assert search_conversion_actions was called
        self.mock_conversion_action_service.search_conversion_actions.assert_called_once_with(
            customer_id=self.customer_id
        )

        # Assert ClickConversion object properties
        self.assertEqual(self.mock_click_conversion.gclid, self.gclid)
        self.assertEqual(
            self.mock_click_conversion.conversion_action,
            mock_conversion_action_response.resource_name,
        )
        self.assertEqual(
            self.mock_click_conversion.conversion_date_time, self.conversion_date_time
        )
        self.assertEqual(self.mock_click_conversion.conversion_value, 23.41)
        self.assertEqual(self.mock_click_conversion.currency_code, "USD")

        # Assert UploadClickConversionsRequest object properties
        self.assertEqual(
            self.mock_upload_click_conversions_request.customer_id, self.customer_id
        )
        self.assertIn(
            self.mock_click_conversion,
            self.mock_upload_click_conversions_request.conversions,
        )
        self.assertTrue(self.mock_upload_click_conversions_request.partial_failure)

        # Assert upload_click_conversions was called
        self.mock_conversion_upload_service.upload_click_conversions.assert_called_once_with(
            request=self.mock_upload_click_conversions_request,
        )

        # Assert output
        output = self.captured_output.getvalue()
        self.assertIn(str(mock_upload_response), output)

    def test_main_no_conversion_actions_found(self):
        self.mock_conversion_action_service.search_conversion_actions.return_value = []

        with self.assertRaises(SystemExit) as cm:
            main(self.mock_client, self.customer_id, self.gclid, self.conversion_date_time)

        self.assertEqual(cm.exception.code, 1)
        output = self.captured_output.getvalue()
        self.assertIn("No conversion actions found. Please create one.", output)

    def test_main_google_ads_exception(self):
        self.mock_conversion_action_service.search_conversion_actions.return_value = [
            MagicMock(resource_name="customers/123/conversionActions/456")
        ]

        mock_error_status = MagicMock()
        mock_error_status.code = MagicMock()
        mock_error_status.code.name = "REQUEST_ERROR"

        mock_failure = MagicMock()
        mock_failure.errors = [
            MagicMock(
                message="Error details",
                location=MagicMock(
                    field_path_elements=[MagicMock(field_name="test_field")]
                ),
            )
        ]

        self.mock_conversion_upload_service.upload_click_conversions.side_effect = (
            GoogleAdsException(
                mock_error_status,  # Positional argument for error
                failure=mock_failure,
                request_id="test_request_id",
                call=MagicMock(),
            )
        )

        with self.assertRaises(GoogleAdsException) as cm:
            main(self.mock_client, self.customer_id, self.gclid, self.conversion_date_time)

        # The exception object is now directly the GoogleAdsException
        ex = cm.exception
        self.assertEqual(ex.request_id, "test_request_id")
        self.assertEqual(ex.error.code.name, "REQUEST_ERROR")
        self.assertEqual(ex.failure.errors[0].message, "Error details")
        self.assertEqual(
            ex.failure.errors[0].location.field_path_elements[0].field_name,
            "test_field",
        )


if __name__ == "__main__":
    unittest.main()

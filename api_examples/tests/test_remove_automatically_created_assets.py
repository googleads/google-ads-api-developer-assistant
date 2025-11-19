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
from api_examples.remove_automatically_created_assets import main


class TestRemoveAutomaticallyCreatedAssets(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock(spec=GoogleAdsClient)
        self.mock_automatically_created_asset_removal_service = MagicMock()
        self.mock_campaign_service = MagicMock()

        self.mock_client.get_service.side_effect = self._get_mock_service

        class MockAssetFieldType:
            UNSPECIFIED = MagicMock()
            UNSPECIFIED.name = "UNSPECIFIED"
            UNKNOWN = MagicMock()
            UNKNOWN.name = "UNKNOWN"
            HEADLINE = MagicMock()
            HEADLINE.name = "HEADLINE"
            DESCRIPTION = MagicMock()
            DESCRIPTION.name = "DESCRIPTION"
            MANDATORY_AD_TEXT = MagicMock()
            MANDATORY_AD_TEXT.name = "MANDATORY_AD_TEXT"

            # Add other relevant enum values as needed for testing

            def __getitem__(self, key):
                if not hasattr(self, key):
                    raise KeyError(f"'{key}' is not a valid AssetFieldType")
                return getattr(self, key)

            def __iter__(self):
                # Return a list of mock enum values for iteration
                return iter(
                    [
                        self.UNSPECIFIED,
                        self.UNKNOWN,
                        self.HEADLINE,
                        self.DESCRIPTION,
                        self.MANDATORY_AD_TEXT,
                    ]
                )

        self.mock_real_asset_field_type = MockAssetFieldType()

        self.mock_client.enums = MagicMock()
        self.mock_client.enums.AssetFieldTypeEnum = MagicMock()
        self.mock_client.enums.AssetFieldTypeEnum.AssetFieldType = (
            self.mock_real_asset_field_type
        )

        self.customer_id = "1234567890"
        self.campaign_id = 12345
        self.asset_resource_name = "customers/1234567890/assets/67890"
        self.field_type = "HEADLINE"

        self.captured_output = StringIO()
        sys.stdout = self.captured_output

    def _get_mock_service(self, service_name):
        if service_name == "AutomaticallyCreatedAssetRemovalService":
            return self.mock_automatically_created_asset_removal_service
        elif service_name == "CampaignService":
            return self.mock_campaign_service
        return MagicMock()

    def tearDown(self):
        sys.stdout = sys.__stdout__

    def test_main_successful_removal(self):
        mock_response = MagicMock()
        mock_response.results = [MagicMock()]
        self.mock_automatically_created_asset_removal_service.remove_campaign_automatically_created_asset.return_value = mock_response

        self.mock_campaign_service.campaign_path.return_value = (
            f"customers/{self.customer_id}/campaigns/{self.campaign_id}"
        )

        mock_request = MagicMock()
        mock_request.operations = []
        mock_request.customer_id = self.customer_id
        mock_request.partial_failure = False

        self.mock_client.get_type.return_value = mock_request

        main(
            self.mock_client,
            self.customer_id,
            self.campaign_id,
            self.asset_resource_name,
            self.field_type,
        )

        self.mock_campaign_service.campaign_path.assert_called_once_with(
            self.customer_id, self.campaign_id
        )
        self.mock_automatically_created_asset_removal_service.remove_campaign_automatically_created_asset.assert_called_once_with(
            request=mock_request
        )

        self.assertEqual(len(mock_request.operations), 1)
        operation = mock_request.operations[0]
        self.assertEqual(
            operation.campaign,
            f"customers/{self.customer_id}/campaigns/{self.campaign_id}",
        )
        self.assertEqual(operation.asset, self.asset_resource_name)
        self.assertEqual(operation.field_type.name, self.field_type)

        output = self.captured_output.getvalue()
        self.assertIn("Removed 1 automatically created assets.", output)

    def test_main_google_ads_exception(self):
        mock_code_obj = MagicMock()
        mock_code_obj.name = "REQUEST_ERROR"
        mock_error = MagicMock()
        mock_error.code.return_value = mock_code_obj
        self.mock_automatically_created_asset_removal_service.remove_campaign_automatically_created_asset.side_effect = GoogleAdsException(
            error=mock_error,
            call=MagicMock(),
            failure=MagicMock(
                errors=[
                    MagicMock(
                        message="Error details",
                        location=MagicMock(
                            field_path_elements=[MagicMock(field_name="test_field")]
                        ),
                    )
                ]
            ),
            request_id="test_request_id",
        )
        self.mock_campaign_service.campaign_path.return_value = (
            f"customers/{self.customer_id}/campaigns/{self.campaign_id}"
        )

        with self.assertRaises(SystemExit) as cm:
            main(
                self.mock_client,
                self.customer_id,
                self.campaign_id,
                self.asset_resource_name,
                self.field_type,
            )

        self.assertEqual(cm.exception.code, 1)
        output = self.captured_output.getvalue()
        self.assertIn(
            "Request with ID 'test_request_id' failed with status 'REQUEST_ERROR'",
            output,
        )
        self.assertIn("Error with message 'Error details'.", output)
        self.assertIn("On field: test_field", output)

    def test_main_invalid_field_type(self):
        # We need to temporarily restore sys.stdout to prevent MagicMock issues
        sys.stdout = sys.__stdout__
        self.captured_output = StringIO()
        sys.stdout = self.captured_output

        invalid_field_type = "INVALID_TYPE"

        with self.assertRaises(SystemExit) as cm:
            main(
                self.mock_client,
                self.customer_id,
                self.campaign_id,
                self.asset_resource_name,
                invalid_field_type,
            )

        self.assertEqual(cm.exception.code, 1)
        output = self.captured_output.getvalue()
        self.assertIn(f"Error: Invalid field type '{invalid_field_type}'.", output)
        self.assertIn("Please use one of:", output)


if __name__ == "__main__":
    unittest.main()


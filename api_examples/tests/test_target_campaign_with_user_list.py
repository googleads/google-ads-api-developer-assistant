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

# Import the main function from the script
from api_examples.target_campaign_with_user_list import main


class TestTargetCampaignWithUserList(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock(spec=GoogleAdsClient)
        self.mock_criterion_service = MagicMock()
        self.mock_campaign_service = MagicMock()
        self.mock_user_list_service = MagicMock()
        
        def get_service_side_effect(name):
            if name == "CampaignCriterionService":
                return self.mock_criterion_service
            if name == "CampaignService":
                return self.mock_campaign_service
            if name == "UserListService":
                return self.mock_user_list_service
            return MagicMock()

        self.mock_client.get_service.side_effect = get_service_side_effect
        self.mock_client.get_type.return_value = MagicMock()
        
        self.customer_id = "1234567890"
        self.campaign_id = "111222333"
        self.user_list_id = "444555666"
        
        self.captured_output = StringIO()
        sys.stdout = self.captured_output

    def tearDown(self):
        sys.stdout = sys.__stdout__

    def test_main_successful_targeting(self):
        mock_response = MagicMock()
        mock_response.results = [MagicMock(resource_name="customers/123/campaignCriteria/101")]
        self.mock_criterion_service.mutate_campaign_criteria.return_value = mock_response

        main(self.mock_client, self.customer_id, self.campaign_id, self.user_list_id)

        self.mock_criterion_service.mutate_campaign_criteria.assert_called_once()
        self.assertIn("Created criterion: customers/123/campaignCriteria/101", self.captured_output.getvalue())

    def test_main_google_ads_exception(self):
        mock_error = MagicMock()
        mock_error.code.return_value.name = "REQUEST_ERROR"
        
        self.mock_criterion_service.mutate_campaign_criteria.side_effect = GoogleAdsException(
            error=mock_error,
            failure=MagicMock(errors=[MagicMock(message="Error details")]),
            request_id="test_request_id",
            call=MagicMock(),
        )

        with self.assertRaises(SystemExit) as cm:
            main(self.mock_client, self.customer_id, self.campaign_id, self.user_list_id)

        self.assertEqual(cm.exception.code, 1)
        self.assertIn("Request ID test_request_id failed: REQUEST_ERROR", self.captured_output.getvalue())


if __name__ == "__main__":
    unittest.main()

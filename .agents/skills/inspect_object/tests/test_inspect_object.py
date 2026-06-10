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

"""Unit tests for inspect_object skill script."""

import io
import os
import sys
import unittest
from unittest import mock

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
)

import inspect_object
from google.ads.googleads.client import GoogleAdsClient


class TestInspectObject(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_client = mock.create_autospec(GoogleAdsClient, instance=True)

    @mock.patch.object(sys, "stdout", new_callable=io.StringIO)
    def test_inspect_protobuf_message(self, mock_stdout) -> None:
        mock_field1 = mock.MagicMock()
        mock_field1.name = "campaign_id"
        mock_field1.label = mock_field1.LABEL_OPTIONAL
        mock_field1.type = "INT64"
        mock_field1.message_type = None

        mock_descriptor = mock.MagicMock()
        mock_descriptor.fields = [mock_field1]
        del mock_descriptor.values  # Make sure it behaves as message, not enum

        mock_obj = mock.MagicMock()
        mock_obj.DESCRIPTOR = mock_descriptor

        self.mock_client.get_type.return_value = mock_obj

        inspect_object.inspect_protobuf("Campaign", "v24", client=self.mock_client)

        self.mock_client.get_type.assert_called_once_with("Campaign")
        output = mock_stdout.getvalue()
        self.assertIn("=== Message: Campaign ===", output)
        self.assertIn("campaign_id", output)

    @mock.patch.object(sys, "stdout", new_callable=io.StringIO)
    def test_inspect_protobuf_enum(self, mock_stdout) -> None:
        mock_val1 = mock.MagicMock()
        mock_val1.name = "ENABLED"
        mock_val1.number = 2

        mock_descriptor = mock.MagicMock()
        mock_descriptor.values = [mock_val1]

        mock_obj = mock.MagicMock()
        mock_obj.DESCRIPTOR = mock_descriptor

        self.mock_client.get_type.return_value = mock_obj

        inspect_object.inspect_protobuf("CampaignStatusEnum", "v24", client=self.mock_client)

        self.mock_client.get_type.assert_called_once_with("CampaignStatusEnum")
        output = mock_stdout.getvalue()
        self.assertIn("=== Enum: CampaignStatusEnum ===", output)
        self.assertIn("ENABLED = 2", output)


if __name__ == "__main__":
    unittest.main()

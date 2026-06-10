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

"""Unit tests for get_cids_under_mcc skill script."""

import argparse
import io
import os
import sys
import unittest
from unittest import mock

# Add the scripts directory to sys.path to import get_cids_under_mcc
sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
)

import get_cids_under_mcc
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException


class TestGetCidsUnderMcc(unittest.TestCase):
    def setUp(self) -> None:
        self.mock_client = mock.create_autospec(GoogleAdsClient, instance=True)
        self.mock_service = mock.MagicMock()
        self.mock_client.get_service.return_value = self.mock_service

        # Setup test csv directory
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.base_dir = os.path.abspath(os.path.join(self.script_dir, "../../../.."))
        self.csv_dir = os.path.join(self.base_dir, "saved", "csv")

    def test_get_cids_success(self) -> None:
        # Mock stream batches
        mock_cc1 = mock.MagicMock()
        mock_cc1.id = 11111111
        mock_cc1.level = 1
        mock_cc1.manager = False

        mock_cc2 = mock.MagicMock()
        mock_cc2.id = 22222222
        mock_cc2.level = 2
        mock_cc2.manager = True

        mock_row1 = mock.MagicMock(customer_client=mock_cc1)
        mock_row2 = mock.MagicMock(customer_client=mock_cc2)
        mock_batch = mock.MagicMock(results=[mock_row1, mock_row2])

        self.mock_service.search_stream.return_value = [mock_batch]

        results = get_cids_under_mcc.get_cids_under_mcc(
            customer_id="12345678", api_version="v23", client=self.mock_client
        )

        self.mock_client.get_service.assert_called_once_with("GoogleAdsService")
        self.mock_service.search_stream.assert_called_once()
        self.assertEqual(results, [("11111111", 1, False), ("22222222", 2, True)])

    def test_get_cids_empty(self) -> None:
        mock_batch = mock.MagicMock(results=[])
        self.mock_service.search_stream.return_value = [mock_batch]

        results = get_cids_under_mcc.get_cids_under_mcc(
            customer_id="12345678", api_version="v23", client=self.mock_client
        )
        self.assertEqual(results, [])

    @mock.patch.object(sys, "stderr", new_callable=io.StringIO)
    def test_get_cids_invalid_cid(self, mock_stderr) -> None:
        with self.assertRaises(SystemExit) as cm:
            get_cids_under_mcc.get_cids_under_mcc(
                customer_id="abc", api_version="v23", client=self.mock_client
            )
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("Error: Invalid customer ID 'abc'.", mock_stderr.getvalue())

    @mock.patch.object(sys, "stderr", new_callable=io.StringIO)
    def test_get_cids_googleads_exception(self, mock_stderr) -> None:
        mock_error = mock.MagicMock()
        mock_error.message = "Permission denied."
        mock_error.location.field_path_elements = [
            mock.MagicMock(field_name="customer_id")
        ]

        self.mock_service.search_stream.side_effect = GoogleAdsException(
            error=mock.MagicMock(),
            failure=mock.MagicMock(errors=[mock_error]),
            request_id="dummy_req_id",
            call=mock.MagicMock(),
        )

        with self.assertRaises(SystemExit) as cm:
            get_cids_under_mcc.get_cids_under_mcc(
                customer_id="12345678",
                api_version="v23",
                client=self.mock_client,
            )
        self.assertEqual(cm.exception.code, 1)
        output = mock_stderr.getvalue()
        self.assertIn("FAILURE: API call failed with Request ID dummy_req_id", output)
        self.assertIn("  - Permission denied.", output)
        self.assertIn("    On field: customer_id", output)

    @mock.patch.object(sys, "stderr", new_callable=io.StringIO)
    def test_get_cids_generic_exception(self, mock_stderr) -> None:
        self.mock_service.search_stream.side_effect = ValueError("Stream failed")
        with self.assertRaises(SystemExit) as cm:
            get_cids_under_mcc.get_cids_under_mcc(
                customer_id="12345678",
                api_version="v23",
                client=self.mock_client,
            )
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("CRITICAL ERROR: Stream failed", mock_stderr.getvalue())

    @mock.patch.object(sys, "stdout", new_callable=io.StringIO)
    @mock.patch.object(argparse.ArgumentParser, "parse_args")
    @mock.patch.object(get_cids_under_mcc, "get_cids_under_mcc", autospec=True)
    def test_main_default_count(
        self, mock_get_cids, mock_parse_args, mock_stdout
    ) -> None:
        mock_parse_args.return_value = argparse.Namespace(
            customer_id="12345678",
            api_version="v23",
            save_csv=False,
            print_cids=False,
        )
        mock_get_cids.return_value = [
            ("11111111", 1, False),
            ("22222222", 2, True),
        ]

        get_cids_under_mcc.main()

        mock_get_cids.assert_called_once_with("12345678", "v23")
        self.assertIn(
            "Found 2 child accounts under MCC 12345678.", mock_stdout.getvalue()
        )

    @mock.patch.object(sys, "stdout", new_callable=io.StringIO)
    @mock.patch.object(argparse.ArgumentParser, "parse_args")
    @mock.patch.object(get_cids_under_mcc, "get_cids_under_mcc", autospec=True)
    def test_main_print_cids(self, mock_get_cids, mock_parse_args, mock_stdout) -> None:
        mock_parse_args.return_value = argparse.Namespace(
            customer_id="12345678",
            api_version="v23",
            save_csv=False,
            print_cids=True,
        )
        mock_get_cids.return_value = [("11111111", 1, False)]

        get_cids_under_mcc.main()

        mock_get_cids.assert_called_once_with("12345678", "v23")
        output = mock_stdout.getvalue()
        self.assertIn("Child accounts under MCC 12345678:", output)
        self.assertIn("11111111", output)
        self.assertIn("No", output)

    @mock.patch.object(sys, "stdout", new_callable=io.StringIO)
    @mock.patch.object(argparse.ArgumentParser, "parse_args")
    @mock.patch.object(get_cids_under_mcc, "get_cids_under_mcc", autospec=True)
    def test_main_save_csv(self, mock_get_cids, mock_parse_args, mock_stdout) -> None:
        mock_parse_args.return_value = argparse.Namespace(
            customer_id="12345678",
            api_version="v23",
            save_csv=True,
            print_cids=False,
        )
        mock_get_cids.return_value = [
            ("11111111", 1, False),
            ("22222222", 2, True),
        ]

        # Ensure clean state for csv
        csv_file = os.path.join(self.csv_dir, "cids_under_mcc_12345678.csv")
        if os.path.exists(csv_file):
            os.remove(csv_file)

        get_cids_under_mcc.main()

        mock_get_cids.assert_called_once_with("12345678", "v23")
        self.assertTrue(os.path.exists(csv_file))
        with open(csv_file, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("Customer ID,Level,Is MCC", content)
            self.assertIn("11111111,1,False", content)
            self.assertIn("22222222,2,True", content)

        self.assertIn(f"SUCCESS: Results saved to {csv_file}", mock_stdout.getvalue())

        # Cleanup
        if os.path.exists(csv_file):
            os.remove(csv_file)


if __name__ == "__main__":
    unittest.main()

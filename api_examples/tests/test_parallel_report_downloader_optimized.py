# Copyright 2026 Google LLC
import sys
import os
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from api_examples.parallel_report_downloader_optimized import fetch_report_threaded

class TestParallelDownloader(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.mock_ga_service = MagicMock()
        self.mock_client.get_service.return_value = self.mock_ga_service
        self.customer_id = "1234567890"

    def test_fetch_report_threaded_logging(self):
        mock_row = MagicMock()
        mock_batch = MagicMock()
        mock_batch.results = [mock_row]
        self.mock_ga_service.search_stream.return_value = [mock_batch]

        with self.assertLogs("api_examples.parallel_report_downloader_optimized", level="INFO") as cm:
            fetch_report_threaded(self.mock_client, self.customer_id, "SELECT 1 FROM campaign", "LogTest")
            
        self.assertTrue(any("Fetching for customer" in output for output in cm.output))
        self.assertTrue(any("Completed. Found 1 rows." in output for output in cm.output))

if __name__ == "__main__":
    unittest.main()

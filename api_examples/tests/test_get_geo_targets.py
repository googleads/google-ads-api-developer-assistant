# Copyright 2026 Google LLC
import sys
import os
import unittest
from unittest.mock import MagicMock
from io import StringIO

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from api_examples.get_geo_targets import main

class TestGetGeoTargets(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.mock_ga_service = MagicMock()
        self.mock_client.get_service.return_value = self.mock_ga_service
        self.captured_output = StringIO()
        self.sys_stdout = sys.stdout
        sys.stdout = self.captured_output

    def tearDown(self):
        sys.stdout = self.sys_stdout

    def test_main_no_geo_targets(self):
        self.mock_ga_service.search_stream.return_value = []
        main(self.mock_client, "123")
        self.assertIn("No geo targets found.", self.captured_output.getvalue())

if __name__ == "__main__":
    unittest.main()

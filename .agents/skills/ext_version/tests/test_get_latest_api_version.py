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
from unittest.mock import MagicMock, patch

# Add scripts directory to sys.path
scripts_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../scripts")
)
sys.path.append(scripts_dir)

from get_latest_api_version import detect_latest_api_version  # noqa: E402


class TestGetLatestApiVersion(unittest.TestCase):

    def test_detect_from_client_libs_directory(self) -> None:
        with patch("os.path.isdir") as mock_isdir, patch("os.listdir") as mock_listdir:
            mock_isdir.return_value = True
            mock_listdir.return_value = [
                "v21",
                "v22",
                "v25",
                "v23",
                "v24",
                "README.md",
            ]

            version = detect_latest_api_version()
            self.assertEqual(version, "v25")

    def test_detect_fallback_when_no_directory(self) -> None:
        with patch("os.path.isdir", return_value=False), patch.dict(
            "sys.modules",
            {"google.ads.googleads": MagicMock(v24=object(), v25=object())},
        ):
            version = detect_latest_api_version()
            self.assertIn(version, ["v25", "v24"])


if __name__ == "__main__":
    unittest.main()

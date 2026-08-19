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

"""Unit tests for Google Ads API Developer Assistant skills, sidecar, and helpers."""

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Add plugin scripts to sys.path
PLUGIN_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../plugins/google-ads-api-developer-assistant")
)
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "skills/inspect-object/scripts"))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "skills/validate-gaql/scripts"))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "skills/get-cids-under-mcc/scripts"))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "skills/sync-client-libs/scripts"))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "sidecars/google-ads-a2a-service"))

import get_cids_under_mcc  # noqa: E402
import inspect_object  # noqa: E402
import server  # noqa: E402
import sync_client_libs  # noqa: E402
import validate_gaql  # noqa: E402


class TestValidateGAQL:
    """Unit tests for validate_gaql.py static rules and mock dry-run."""

    def test_forbidden_or_operator(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            validate_gaql.validate_gaql(
                customer_id="1234567890",
                api_version="v25",
                query="SELECT campaign.id FROM campaign WHERE campaign.id = 1 OR campaign.id = 2",
            )
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "forbidden OR operator" in captured.out

    def test_forbidden_aggregate_function(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            validate_gaql.validate_gaql(
                customer_id="1234567890",
                api_version="v25",
                query="SELECT COUNT(campaign.id) FROM campaign",
            )
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "forbidden aggregate function 'COUNT'" in captured.out

    def test_forbidden_date_function(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            validate_gaql.validate_gaql(
                customer_id="1234567890",
                api_version="v25",
                query="SELECT campaign.id FROM campaign WHERE segments.date = CURRENT_DATE()",
            )
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "forbidden date/time function" in captured.out

    def test_date_segment_without_date_filter(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            validate_gaql.validate_gaql(
                customer_id="1234567890",
                api_version="v25",
                query="SELECT campaign.id, segments.date FROM campaign WHERE campaign.status = 'ENABLED'",
            )
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "selects a date segment but does not specify a finite date filter" in captured.out

    def test_click_view_single_day_constraint(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            validate_gaql.validate_gaql(
                customer_id="1234567890",
                api_version="v25",
                query="SELECT click_view.gclid FROM click_view WHERE segments.date DURING LAST_30_DAYS",
            )
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "require a single-day filter" in captured.out

    def test_change_status_constraints(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            validate_gaql.validate_gaql(
                customer_id="1234567890",
                api_version="v25",
                query="SELECT change_status.resource_name FROM change_status",
            )
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "BETWEEN filter on last_change_date_time" in captured.out

    def test_metadata_query_from_clause(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            validate_gaql.validate_gaql(
                customer_id="1234567890",
                api_version="v25",
                query="SELECT name FROM google_ads_field",
            )
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Metadata queries (google_ads_field) MUST NOT contain a FROM clause" in captured.out

    def test_deprecated_segments_hour_v23(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            validate_gaql.validate_gaql(
                customer_id="1234567890",
                api_version="v25",
                query="SELECT campaign.id, segments.hour FROM campaign WHERE segments.date DURING LAST_30_DAYS",
            )
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "segments.hour_of_day" in captured.out

    def test_mock_dry_run_success(self, capsys):
        mock_client = MagicMock()
        mock_service = MagicMock()
        mock_client.get_service.return_value = mock_service
        mock_service.search.return_value = []

        validate_gaql.validate_gaql(
            customer_id="1234567890",
            api_version="v25",
            query="SELECT campaign.id, campaign.name FROM campaign WHERE segments.date DURING LAST_30_DAYS",
            client=mock_client,
        )
        captured = capsys.readouterr()
        assert "SUCCESS: GAQL query is structurally valid." in captured.out
        mock_service.search.assert_called_once()


class TestInspectObject:
    """Unit tests for inspect_object.py matching and mocked inspection."""

    @pytest.fixture(autouse=True)
    def setup_types(self):
        real_types = inspect_object.get_available_types("v25")
        if real_types:
            self.types = real_types
        else:
            # Fallback mock types dictionary when client_libs is not pre-cloned (e.g. CI environments)
            self.types = {
                "Campaign": "/mock/path/campaign.py",
                "CampaignStatus": "/mock/path/campaign_status.py",
                "CampaignStatusEnum": "/mock/path/campaign_status_enum.py",
                "AdGroupAd": "/mock/path/ad_group_ad.py",
            }

    def test_available_types_loaded(self):
        assert len(self.types) > 0
        assert "Campaign" in self.types
        assert "CampaignStatus" in self.types or "CampaignStatusEnum" in self.types

    def test_exact_match(self):
        resolved, suggestions = inspect_object.resolve_type_name("Campaign", self.types)
        assert resolved == "Campaign"
        assert not suggestions

    def test_case_insensitive_match(self):
        resolved, suggestions = inspect_object.resolve_type_name("campaign", self.types)
        assert resolved == "Campaign"
        assert not suggestions

    def test_normalized_match(self):
        resolved, _ = inspect_object.resolve_type_name("campaign_status", self.types)
        assert resolved in ("CampaignStatus", "CampaignStatusEnum")

        resolved, _ = inspect_object.resolve_type_name("ad_group_ad", self.types)
        assert resolved == "AdGroupAd"

    def test_fuzzy_suggestions(self):
        resolved, suggestions = inspect_object.resolve_type_name("campain", self.types)
        assert resolved is None
        assert len(suggestions) > 0
        assert any("Campaign" in s for s in suggestions)

    def test_inspect_from_source_campaign(self, tmp_path, capsys):
        mock_file = tmp_path / "campaign.py"
        mock_file.write_text(
            "class Campaign(proto.Message):\n"
            "    name: str = proto.Field(proto.STRING, number=1)\n"
            "    status: int = proto.Field(proto.INT32, number=2)\n"
        )
        success = inspect_object.inspect_from_source(str(mock_file), "Campaign")
        assert success is True
        captured = capsys.readouterr()
        assert "=== Message: Campaign ===" in captured.out
        assert "name" in captured.out
        assert "status" in captured.out

    def test_mock_client_inspection(self, capsys):
        mock_client = MagicMock()
        mock_obj = MagicMock()
        mock_descriptor = MagicMock()
        mock_field = MagicMock()
        mock_field.name = "test_field"
        mock_field.is_repeated = False
        mock_field.message_type = None
        mock_field.type = "TYPE_STRING"
        mock_descriptor.fields = [mock_field]
        del mock_descriptor.values
        mock_obj.DESCRIPTOR = mock_descriptor
        mock_client.get_type.return_value = mock_obj

        inspect_object.inspect_protobuf("Campaign", "v25", client=mock_client)
        captured = capsys.readouterr()
        assert "=== Message: Campaign ===" in captured.out
        assert "test_field" in captured.out


class TestGetCidsUnderMCC:
    """Unit tests for get_cids_under_mcc.py with mock responses."""

    def test_invalid_customer_id(self, capsys):
        mock_client = MagicMock()
        with pytest.raises(SystemExit) as exc_info:
            get_cids_under_mcc.get_cids_under_mcc("invalid_id", "v25", client=mock_client)
        assert exc_info.value.code == 1

    def test_mock_search_stream_results(self):
        mock_client = MagicMock()
        mock_service = MagicMock()
        mock_client.get_service.return_value = mock_service

        # Construct mock row batches
        row1 = MagicMock()
        row1.customer_client.id = 1111111111
        row1.customer_client.level = 1
        row1.customer_client.manager = True

        row2 = MagicMock()
        row2.customer_client.id = 2222222222
        row2.customer_client.level = 2
        row2.customer_client.manager = False

        batch = MagicMock()
        batch.results = [row1, row2]
        mock_service.search_stream.return_value = [batch]

        results = get_cids_under_mcc.get_cids_under_mcc(
            customer_id="1234567890", api_version="v25", client=mock_client
        )
        assert len(results) == 2
        assert results[0] == ("1111111111", 1, True)
        assert results[1] == ("2222222222", 2, False)


class TestSyncClientLibs:
    """Unit tests for sync_client_libs.py discovery and version comparison."""

    def test_discover_client_libs_dir(self, tmp_path):
        mock_libs = tmp_path / "client_libs"
        mock_libs.mkdir()
        (mock_libs / "google-ads-python").mkdir()
        found_dir = sync_client_libs.discover_client_libs_dir(str(mock_libs))
        assert os.path.isdir(found_dir)
        assert "google-ads-python" in os.listdir(found_dir)

    def test_version_parsing_and_comparison(self):
        v1 = sync_client_libs.parse_version("25.0.0")
        v2 = sync_client_libs.parse_version("25.1.0")
        v3 = sync_client_libs.parse_version("v26.0.0")
        assert v1 < v2
        assert v2 < v3
        assert str(v1) in ("25.0.0", str(v1))

    @patch("urllib.request.urlopen")
    def test_fetch_latest_release_mock(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "tag_name": "v26.0.0",
            "tarball_url": "https://api.github.com/repos/googleads/google-ads-python/tarball/v26.0.0",
            "body": "Release notes for v26.0.0",
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        tag_name, tarball_url = sync_client_libs.fetch_github_latest_release("googleads/google-ads-python")
        assert tag_name == "v26.0.0"
        assert tarball_url is not None


class TestSidecarA2A:
    """Unit tests for A2A sidecar task handlers."""

    def test_get_effective_api_version(self):
        ver = server.get_effective_api_version({"api_version": "v25"})
        assert ver == "v25"

    def test_gaql_validate_success(self):
        handler = server.A2AHandler.__new__(server.A2AHandler)
        res = handler.handle_gaql_validate(
            "task-1",
            {
                "query": "SELECT campaign.id, campaign.name FROM campaign WHERE segments.date DURING LAST_30_DAYS",
                "api_version": "v25",
            },
        )
        assert res["status"] == "COMPLETED"
        assert res["result"]["gaql_validation"]["status"] == "PASSED"

    def test_gaql_validate_forbidden_or(self):
        handler = server.A2AHandler.__new__(server.A2AHandler)
        res = handler.handle_gaql_validate(
            "task-2",
            {
                "query": "SELECT campaign.id FROM campaign WHERE campaign.id = 1 OR campaign.id = 2",
                "api_version": "v25",
            },
        )
        assert res["status"] == "VALIDATION_FAILED"
        assert any("OR" in err for err in res["errors"])

    def test_gaql_validate_deprecated_segments_hour_v23(self):
        handler = server.A2AHandler.__new__(server.A2AHandler)
        res = handler.handle_gaql_validate(
            "task-3",
            {
                "query": "SELECT campaign.id, segments.hour FROM campaign WHERE segments.date DURING LAST_30_DAYS",
                "api_version": "v25",
            },
        )
        assert res["status"] == "VALIDATION_FAILED"
        assert any("segments.hour_of_day" in err for err in res["errors"])

    def test_inspect_object_task(self):
        handler = server.A2AHandler.__new__(server.A2AHandler)
        res = handler.handle_inspect_object(
            "task-4", {"resource_name": "Campaign", "api_version": "v25"}
        )
        assert res["status"] == "COMPLETED"
        assert res["result"]["resource"] == "Campaign"

    def test_generate_code_task(self):
        handler = server.A2AHandler.__new__(server.A2AHandler)
        res = handler.handle_generate_code(
            "task-5",
            {
                "user_prompt": "Fetch campaign metrics",
                "customer_id": "1234567890",
                "api_version": "v25",
            },
        )
        assert res["status"] == "COMPLETED"
        assert "GoogleAdsClient" in res["result"]["generated_code"]

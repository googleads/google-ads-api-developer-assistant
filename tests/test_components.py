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
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "skills/pmax-listing-filter/scripts"))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "skills/troubleshoot-conversions/scripts"))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "sidecars/google-ads-a2a-service"))

import create_pmax_webpage_filter  # noqa: E402
import get_cids_under_mcc  # noqa: E402
import inspect_object  # noqa: E402
import server  # noqa: E402
import sync_client_libs  # noqa: E402
import troubleshoot_conversions  # noqa: E402
import validate_conversion_upload  # noqa: E402
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
        self.types = inspect_object.get_available_types("v25")

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

    def test_inspect_from_source_campaign(self, capsys):
        py_file = self.types.get("Campaign")
        assert py_file is not None
        success = inspect_object.inspect_from_source(py_file, "Campaign")
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
    """Unit tests for get_cids_under_mcc.py with mock responses and JSON formatting."""

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

    def test_discover_client_libs_dir(self):
        found_dir = sync_client_libs.discover_client_libs_dir()
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


class TestCreatePMaxWebpageFilter:
    """Unit tests for create_pmax_webpage_filter.py tree structure and mock execution."""

    def test_create_pmax_webpage_filter_tree_structure(self, capsys):
        mock_client = MagicMock()
        mock_filter_service = MagicMock()
        mock_asset_group_service = MagicMock()

        def get_service_side_effect(service_name):
            if service_name == "AssetGroupListingGroupFilterService":
                return mock_filter_service
            elif service_name == "AssetGroupService":
                return mock_asset_group_service
            return MagicMock()

        mock_client.get_service.side_effect = get_service_side_effect
        mock_filter_service.asset_group_listing_group_filter_path.return_value = (
            "customers/1234567890/assetGroupListingGroupFilters/999~-1"
        )
        mock_asset_group_service.asset_group_path.return_value = (
            "customers/1234567890/assetGroups/999"
        )

        def get_type_side_effect(type_name):
            op = MagicMock()
            if type_name == "ListingGroupFilterDimension":
                dim_cls = MagicMock()
                condition = MagicMock()
                dim_cls.WebpageCondition.return_value = condition
                return dim_cls
            return op

        mock_client.get_type.side_effect = get_type_side_effect
        mock_client.enums.ListingGroupFilterTypeEnum.SUBDIVISION = "SUBDIVISION"
        mock_client.enums.ListingGroupFilterTypeEnum.UNIT_INCLUDED = "UNIT_INCLUDED"
        mock_client.enums.ListingGroupFilterListingSourceEnum.WEBPAGE = "WEBPAGE"

        mock_response = MagicMock()
        mock_result = MagicMock()
        mock_result.resource_name = "customers/1234567890/assetGroupListingGroupFilters/999~1"
        mock_response.results = [mock_result]
        mock_filter_service.mutate_asset_group_listing_group_filters.return_value = mock_response

        create_pmax_webpage_filter.create_pmax_webpage_filter(
            customer_id="1234567890",
            asset_group_id="999",
            url_exclusion="example.com/checkout",
            api_version="v25",
            client=mock_client,
            validate_only=True,
        )

        captured = capsys.readouterr()
        assert "Subdivision Webpage Listing Filter tree validated/created successfully." in captured.out
        mock_filter_service.mutate_asset_group_listing_group_filters.assert_called_once()


class TestValidateConversionUpload:
    """Unit tests for validate_conversion_upload.py with valid and malformed CSVs."""

    def test_nonexistent_file(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            validate_conversion_upload.validate_conversion_csv(
                "/nonexistent/path/conversions.csv", "v25"
            )
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "CSV file not found" in captured.err

    def test_missing_required_headers(self, tmp_path, capsys):
        csv_file = tmp_path / "missing_headers.csv"
        csv_file.write_text("gclid,conversion_time\nabcdef12345,2026-08-19 12:00:00-04:00\n", encoding="utf-8")

        with pytest.raises(SystemExit) as exc_info:
            validate_conversion_upload.validate_conversion_csv(str(csv_file), "v25")
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Missing required CSV headers" in captured.err

    def test_valid_conversion_csv(self, tmp_path, capsys):
        csv_file = tmp_path / "valid_conversions.csv"
        csv_content = (
            "gclid,conversion_time,conversion_value,conversion_currency_code\n"
            "Cj0KCQjwgJv4BRCrARIsAGhT20u_valid_gclid_123,2026-08-19 12:30:00-04:00,150.00,USD\n"
            "EAIaIQobChMI7_another_valid_gclid_456,2026-08-19 14:15:00+00:00,49.99,USD\n"
        )
        csv_file.write_text(csv_content, encoding="utf-8")

        validate_conversion_upload.validate_conversion_csv(str(csv_file), "v25")
        captured = capsys.readouterr()
        assert "SUCCESS: Conversion Upload CSV parsed cleanly" in captured.out

    def test_malformed_date_and_short_gclid(self, tmp_path, capsys):
        csv_file = tmp_path / "malformed.csv"
        csv_content = (
            "gclid,conversion_time,conversion_value\n"
            "short,invalid-date,10.00\n"
        )
        csv_file.write_text(csv_content, encoding="utf-8")

        with pytest.raises(SystemExit) as exc_info:
            validate_conversion_upload.validate_conversion_csv(str(csv_file), "v25")
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Invalid conversion_time format" in captured.out or "GCLID is too short" in captured.out


class TestTroubleshootConversions:
    """Unit tests for troubleshoot_conversions.py and structured JSON diagnostics."""

    def test_troubleshoot_conversions_json_output(self, capsys):
        mock_client = MagicMock()
        mock_service = MagicMock()
        mock_client.get_service.return_value = mock_service

        # Mock customer row
        cust_row = MagicMock()
        cust_row.customer.descriptive_name = "Test Account"
        cust_row.customer.conversion_tracking_setting.accepted_customer_data_terms = True
        cust_row.customer.conversion_tracking_setting.enhanced_conversions_for_leads_enabled = True

        # Mock batch response for customer
        batch1 = MagicMock()
        batch1.results = [cust_row]
        mock_service.search_stream.return_value = [batch1]

        data = troubleshoot_conversions.troubleshoot_conversions(
            mock_client, "1234567890", json_output=True
        )

        captured = capsys.readouterr()
        assert "customer_info" in data
        assert data["customer_info"]["name"] == "Test Account"
        assert data["customer_info"]["accepted_customer_data_terms"] is True
        # Verify JSON is output to stdout
        parsed = json.loads(captured.out)
        assert parsed["customer_id"] == "1234567890"
        assert parsed["customer_info"]["name"] == "Test Account"


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

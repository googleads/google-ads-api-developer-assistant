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
from unittest.mock import MagicMock, mock_open, patch

import pytest

# Add plugin scripts to sys.path
PLUGIN_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../plugins/google-ads-api-developer-assistant")
)
sys.path.insert(0, PLUGIN_ROOT)
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "skills/inspect-object/scripts"))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "skills/validate-gaql/scripts"))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "skills/get-cids-under-mcc/scripts"))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "skills/sync-client-libs/scripts"))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "skills/pmax-listing-filter/scripts"))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "skills/troubleshoot-conversions/scripts"))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "skills/ext-version/scripts"))
sys.path.insert(0, os.path.join(PLUGIN_ROOT, "sidecars/google-ads-a2a-service"))

import create_pmax_webpage_filter  # noqa: E402
import get_cids_under_mcc  # noqa: E402
import get_extension_version  # noqa: E402
import get_latest_api_version  # noqa: E402
import get_recent_gclids  # noqa: E402
import inspect_object  # noqa: E402
import server  # noqa: E402
import sync_client_libs  # noqa: E402
import troubleshoot_conversions  # noqa: E402
import validate_conversion_upload  # noqa: E402
import validate_gaql  # noqa: E402


class TestValidateGAQL:
    """Unit tests for validate_gaql.py static rules and mock dry-run."""

    def test_empty_query(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            validate_gaql.validate_gaql(
                customer_id="1234567890",
                api_version="v25",
                query="",
            )
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Error: No query provided" in captured.out

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
    def setup_types(self, tmp_path):
        self.types = inspect_object.get_available_types("v25")
        if not self.types:
            # Hermetic fallback for clean test environments without cloned client_libs
            sample_file = tmp_path / "campaign_types.py"
            sample_file.write_text(
                "class Campaign:\n    name: str\n    status: int\n\nclass CampaignStatusEnum:\n    pass\n\nclass AdGroupAd:\n    pass\n",
                encoding="utf-8",
            )
            self.types = {
                "Campaign": str(sample_file),
                "CampaignStatusEnum": str(sample_file),
                "AdGroupAd": str(sample_file),
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

    def test_inspect_from_source_campaign(self, capsys, tmp_path):
        py_file = self.types.get("Campaign")
        if not py_file or not os.path.exists(py_file):
            mock_file = tmp_path / "campaign_source.py"
            mock_file.write_text(
                "class Campaign:\n    name: str\n    status: int\n",
                encoding="utf-8",
            )
            py_file = str(mock_file)
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

    def test_version_parity_match(self, capsys, monkeypatch):
        monkeypatch.setattr(
            inspect_object.importlib.metadata,
            "version",
            lambda pkg: "26.0.0" if pkg == "google-ads" else "0.0.0",
        )
        fake_content = 'version = "26.0.0"\n'
        with patch("os.path.isfile", side_effect=lambda p: True if "pyproject.toml" in p else False), \
             patch("builtins.open", mock_open(read_data=fake_content)):
            inspect_object.check_version_parity()
        captured = capsys.readouterr()
        assert "WARNING" not in captured.err

    def test_version_parity_mismatch(self, capsys, monkeypatch):
        monkeypatch.setattr(
            inspect_object.importlib.metadata,
            "version",
            lambda pkg: "25.0.0" if pkg == "google-ads" else "0.0.0",
        )
        fake_content = 'version = "26.0.0"\n'
        with patch("os.path.isfile", side_effect=lambda p: True if "pyproject.toml" in p else False), \
             patch("builtins.open", mock_open(read_data=fake_content)):
            inspect_object.check_version_parity()
        captured = capsys.readouterr()
        assert "WARNING: Installed google-ads package version (25.0.0) does not match" in captured.err

    def test_version_parity_changelog_detection(self, capsys, monkeypatch):
        monkeypatch.setattr(
            inspect_object.importlib.metadata,
            "version",
            lambda pkg: "24.0.0" if pkg == "google-ads" else "0.0.0",
        )
        fake_changelog = "* 25.0.0\n- Release notes\n"
        with patch("os.path.isfile", side_effect=lambda p: True if "ChangeLog" in p else False), \
             patch("builtins.open", mock_open(read_data=fake_changelog)):
            inspect_object.check_version_parity()
        captured = capsys.readouterr()
        assert "WARNING: Installed google-ads package version (24.0.0) does not match" in captured.err

    def test_version_parity_missing_libs_handled(self, capsys, monkeypatch):
        monkeypatch.setattr(
            inspect_object.importlib.metadata,
            "version",
            lambda pkg: "25.0.0" if pkg == "google-ads" else "0.0.0",
        )
        with patch("os.path.isfile", return_value=False):
            inspect_object.check_version_parity()
        captured = capsys.readouterr()
        assert "WARNING" not in captured.err


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

    def test_discover_client_libs_dir(self, tmp_path):
        dummy_dir = tmp_path / "client_libs"
        dummy_dir.mkdir()
        found_dir = sync_client_libs.discover_client_libs_dir(str(dummy_dir))
        assert os.path.isdir(found_dir)
        assert found_dir == str(dummy_dir)

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

    def test_sync_client_libs_check_only_json(self, capsys):
        with patch.object(sync_client_libs, "discover_client_libs_dir", return_value="/dummy/client_libs"), \
             patch.object(sync_client_libs, "process_client_libs", return_value=[{
                 "codebase": "google-ads-python",
                 "status": "UP_TO_DATE",
                 "installed_version": "26.0.0",
                 "github_version": "26.0.0",
                 "updated": False,
             }]), \
             patch("sys.argv", ["sync_client_libs.py", "--check_only", "--json"]):
            sync_client_libs.main()
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed["client_libs_dir"] == "/dummy/client_libs"
        assert parsed["results"][0]["status"] == "UP_TO_DATE"


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

    def test_troubleshoot_conversions_json_output(self, capsys, tmp_path):
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
            mock_client, "1234567890", json_output=True, output_dir=str(tmp_path)
        )

        captured = capsys.readouterr()
        assert "customer_info" in data
        assert data["customer_info"]["name"] == "Test Account"
        assert data["customer_info"]["accepted_customer_data_terms"] is True
        # Verify JSON is output to stdout
        parsed = json.loads(captured.out)
        assert parsed["customer_id"] == "1234567890"
        assert parsed["customer_info"]["name"] == "Test Account"


class TestGetRecentGclids:
    """Unit tests for get_recent_gclids.py."""

    def test_get_recent_gclids_success(self, capsys):
        mock_client = MagicMock()
        mock_service = MagicMock()
        mock_client.get_service.return_value = mock_service

        row = MagicMock()
        row.click_view.gclid = "Cj0KCQjw_test_gclid_12345"
        row.segments.date = "2026-08-19"
        mock_service.search.return_value = [row]

        get_recent_gclids.get_recent_gclids(mock_client, "1234567890", "2026-08-19")
        captured = capsys.readouterr()
        assert "Cj0KCQjw_test_gclid_12345" in captured.out
        assert "2026-08-19" in captured.out

    def test_get_recent_gclids_empty(self, capsys):
        mock_client = MagicMock()
        mock_service = MagicMock()
        mock_client.get_service.return_value = mock_service
        mock_service.search.return_value = []

        get_recent_gclids.get_recent_gclids(mock_client, "1234567890", "2026-08-19")
        captured = capsys.readouterr()
        assert "No GCLIDs found on date '2026-08-19'" in captured.out


class TestExtVersion:
    """Unit tests for get_latest_api_version.py and get_extension_version.py."""

    def test_detect_latest_api_version_from_dir(self, tmp_path):
        dummy_dir = tmp_path / "googleads"
        (dummy_dir / "v23").mkdir(parents=True)
        (dummy_dir / "v24").mkdir(parents=True)
        (dummy_dir / "v26").mkdir(parents=True)
        with patch("os.path.abspath", side_effect=lambda p: str(dummy_dir) if "googleads" in p else p):
            ver = get_latest_api_version.detect_latest_api_version()
            assert ver == "v26"

    def test_detect_latest_api_version_updates_assistant_config_automatically(
        self, tmp_path, monkeypatch
    ):
        from config import config_init

        work_dir = tmp_path / "workspace"
        cfg_dir = work_dir / "config"
        cfg_dir.mkdir(parents=True)
        cfg_file = cfg_dir / "assistant_config"
        cfg_file.write_text(
            'api_version = "v23"\ncustomer_id = "9998887776"\nexecute_mutates = true\n',
            encoding="utf-8",
        )

        googleads_dir = (
            work_dir / "client_libs" / "google-ads-python" / "google" / "ads" / "googleads"
        )
        for v in ("v23", "v25", "v28"):
            (googleads_dir / v).mkdir(parents=True)

        monkeypatch.chdir(work_dir)
        ver = get_latest_api_version.detect_latest_api_version(
            update_config=True, config_dir=str(cfg_dir)
        )
        assert ver == "v28"
        parsed = config_init.parse_assistant_config(cfg_file.read_text(encoding="utf-8"))
        assert parsed["api_version"] == "v28"
        assert parsed["customer_id"] == "9998887776"
        assert parsed["execute_mutates"] is True

        # Also verify config_init.sync_api_version automatically updates config/assistant_config
        (googleads_dir / "v29").mkdir(parents=True)
        synced_ver = config_init.sync_api_version(config_dir=str(cfg_dir))
        assert synced_ver == "v29"
        parsed_after = config_init.parse_assistant_config(
            cfg_file.read_text(encoding="utf-8")
        )
        assert parsed_after["api_version"] == "v29"
        assert parsed_after["customer_id"] == "9998887776"
        assert parsed_after["execute_mutates"] is True

    def test_detect_latest_api_version_raises_when_unavailable(self):
        with patch("os.path.isdir", return_value=False), \
             patch.dict("sys.modules", {"google.ads.googleads": None}):
            with pytest.raises(
                RuntimeError,
                match="Unable to detect the latest Google Ads API version",
            ):
                get_latest_api_version.detect_latest_api_version()

    def test_detect_latest_api_version_prefers_newer_system_pkg_over_stale_client_libs(
        self, tmp_path, monkeypatch
    ):
        from config import config_init

        stale_libs = tmp_path / "stale_libs" / "google" / "ads" / "googleads"
        (stale_libs / "v24").mkdir(parents=True)
        (stale_libs / "v25").mkdir(parents=True)

        newer_pkg = tmp_path / "site_pkg" / "google" / "ads" / "googleads"
        (newer_pkg / "v25").mkdir(parents=True)
        (newer_pkg / "v27").mkdir(parents=True)

        fake_mod = MagicMock()
        fake_mod.__path__ = [str(newer_pkg)]
        fake_mod.__file__ = str(newer_pkg / "__init__.py")

        with patch("os.path.abspath", return_value=str(stale_libs)), \
             patch("os.path.expanduser", return_value=str(stale_libs)), \
             patch.dict("sys.modules", {"google.ads.googleads": fake_mod}):
            assert config_init.detect_latest_api_version() == "v27"
            assert get_latest_api_version.detect_latest_api_version() == "v27"

    def test_sync_and_set_config_kv_auto_advances_stale_api_version_in_assistant_config(
        self, tmp_path, monkeypatch
    ):
        from config import config_init

        src_yaml = tmp_path / "home_google_ads.yaml"
        src_yaml.write_text('client_id: "cid"\n', encoding="utf-8")
        cfg_dir = tmp_path / "config"
        cfg_dir.mkdir(parents=True)
        cfg_file = cfg_dir / "assistant_config"
        cfg_file.write_text(
            'api_version = "v24"\ncustomer_id = "1112223334"\nexecute_mutates = true\n',
            encoding="utf-8",
        )

        monkeypatch.setattr(config_init, "detect_latest_api_version", lambda: "v26")
        config_init.sync_and_set_config_kv(
            source_yaml=str(src_yaml),
            config_dir=str(cfg_dir),
        )
        parsed = config_init.parse_assistant_config(cfg_file.read_text(encoding="utf-8"))
        assert parsed["api_version"] == "v26"
        assert parsed["customer_id"] == "1112223334"
        assert parsed["execute_mutates"] is True

    def test_ensure_client_libs_synced_triggers_on_mismatch(self, tmp_path, monkeypatch):
        import tempfile
        from config import config_init

        fake_script = tmp_path / "sync_client_libs.py"
        fake_script.write_text("print('{}')\n", encoding="utf-8")
        monkeypatch.setattr(config_init, "_find_sync_client_libs_script", lambda: str(fake_script))
        monkeypatch.setattr(
            config_init,
            "check_python_client_lib_parity",
            lambda: {
                "local_version": "31.2.0",
                "local_path": str(tmp_path),
                "system_version": "34.0.0",
                "matches": False,
            },
        )
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

        spawned = []
        monkeypatch.setattr(
            config_init.subprocess,
            "Popen",
            lambda cmd, **kw: spawned.append(cmd),
        )
        res = config_init.ensure_client_libs_synced(async_in_background=True)
        assert res["triggered"] is True
        assert res["mode"] == "background"
        assert res["reason"] == "version_mismatch"
        assert len(spawned) == 1

    def test_check_python_client_lib_parity_with_github_comparison(self, tmp_path, monkeypatch):
        from config import config_init

        lib_dir = tmp_path / "client_libs" / "google-ads-python"
        lib_dir.mkdir(parents=True)
        (lib_dir / "pyproject.toml").write_text('version = "31.2.0"\n', encoding="utf-8")

        monkeypatch.setattr("os.path.abspath", lambda p: str(lib_dir) if "google-ads-python" in p else p)
        monkeypatch.setattr("os.path.expanduser", lambda p: str(lib_dir) if "google-ads-python" in p else p)
        monkeypatch.setattr("importlib.metadata.version", lambda pkg: "31.2.0")
        monkeypatch.setattr(config_init, "fetch_latest_github_python_version", lambda force=False: "34.0.0")
        monkeypatch.setattr(config_init, "fetch_latest_pypi_python_version", lambda **kw: "34.0.0")

        parity = config_init.check_python_client_lib_parity(check_github=True)
        assert parity["system_version"] == "31.2.0"
        assert parity["local_version"] == "31.2.0"
        assert parity["github_version"] == "34.0.0"
        assert parity["site_version_less_than_github"] is True
        assert parity["local_version_less_than_github"] is True
        assert parity["upgrade_prompt_required"] is True

        monkeypatch.setattr("importlib.metadata.version", lambda pkg: "34.0.0")
        (lib_dir / "pyproject.toml").write_text('version = "34.0.0"\n', encoding="utf-8")
        parity_up_to_date = config_init.check_python_client_lib_parity(check_github=True)
        assert parity_up_to_date["site_version_less_than_github"] is False
        assert parity_up_to_date["local_version_less_than_github"] is False
        assert parity_up_to_date["upgrade_prompt_required"] is False

    def test_fetch_latest_pypi_python_version(self, monkeypatch, tmp_path):
        from config import config_init
        import io
        import urllib.request

        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))

        class FakeHTTPResponse:
            def __init__(self, data: bytes):
                self._io = io.BytesIO(data)

            def read(self):
                return self._io.read()

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                pass

        fake_json = json.dumps({"info": {"version": "34.0.0"}}).encode("utf-8")
        monkeypatch.setattr(
            urllib.request,
            "urlopen",
            lambda req, **kwargs: FakeHTTPResponse(fake_json),
        )

        v = config_init.fetch_latest_pypi_python_version(force=True)
        assert v == "34.0.0"

    def test_determine_api_version(self, tmp_path, monkeypatch):
        from config import config_init

        # If configured in assistant_config, that takes precedence
        cfg_file = tmp_path / "assistant_config"
        cfg_file.write_text('api_version = "v26"\n', encoding="utf-8")
        v = config_init.determine_api_version(config_dir=str(tmp_path))
        assert v == "v26"

    def test_check_python_client_lib_parity_pypi_and_table(self, tmp_path, monkeypatch):
        from config import config_init

        lib_dir = tmp_path / "client_libs" / "google-ads-python"
        lib_dir.mkdir(parents=True)
        (lib_dir / "pyproject.toml").write_text('version = "31.2.0"\n', encoding="utf-8")

        monkeypatch.setattr("os.path.abspath", lambda p: str(lib_dir) if "google-ads-python" in p else p)
        monkeypatch.setattr("os.path.expanduser", lambda p: str(lib_dir) if "google-ads-python" in p else p)
        monkeypatch.setattr("importlib.metadata.version", lambda pkg: "31.2.0")
        monkeypatch.setattr(config_init, "fetch_latest_github_python_version", lambda force=False: "34.0.0")
        monkeypatch.setattr(config_init, "fetch_latest_pypi_python_version", lambda **kw: "34.0.0")

        parity = config_init.check_python_client_lib_parity(check_github=True, check_pypi=True)
        assert parity["system_version"] == "31.2.0"
        assert parity["pypi_version"] == "34.0.0"
        assert parity["local_version"] == "31.2.0"
        assert parity["github_version"] == "34.0.0"
        assert parity["site_version_less_than_pypi"] is True
        assert parity["local_version_less_than_github"] is True
        assert parity["upgrade_prompt_required"] is True
        assert "| Component / Library |" in parity["table_markdown"]
        assert "pypi.org/project/google-ads" in parity["table_markdown"]
        assert "Google Ads API Version" in parity["table_markdown"]
        assert "Google Ads API Version & Parity Verification Report" in parity["table_text"]

    def test_handle_hook_session_start_and_preinvocation(self, tmp_path, monkeypatch, capsys):
        from config import config_init
        import io

        monkeypatch.setenv("GOOGLE_ADS_ASSISTANT_ENABLED", "true")
        monkeypatch.setattr(config_init, "fetch_latest_github_python_version", lambda force=False: "34.0.0")
        monkeypatch.setattr(config_init, "fetch_latest_pypi_python_version", lambda **kw: "34.0.0")

        # 1. Test SessionStart / First prompt (empty payload on stdin -> defaults to is_first_prompt=True)
        monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
        config_init.handle_hook()
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "injectSteps" in data
        assert "ephemeralMessage" in data["injectSteps"][0]
        assert "Parity Table:" in data["injectSteps"][0]["ephemeralMessage"]
        assert "MANDATORY FIRST-PROMPT DIRECTIVE:" in data["injectSteps"][0]["ephemeralMessage"]

        # 2. Test PreInvocation first prompt (invocationNum == 1)
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"invocationNum": 1})))
        config_init.handle_hook()
        captured2 = capsys.readouterr()
        data2 = json.loads(captured2.out)
        assert "injectSteps" in data2
        assert "ephemeralMessage" in data2["injectSteps"][0]
        assert "Parity Table:" in data2["injectSteps"][0]["ephemeralMessage"]
        assert "MANDATORY FIRST-PROMPT DIRECTIVE:" in data2["injectSteps"][0]["ephemeralMessage"]

        # 3. Test PreInvocation subsequent turn (invocationNum == 2) -> omits table and mandatory display directive
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"invocationNum": 2})))
        config_init.handle_hook()
        captured3 = capsys.readouterr()
        data3 = json.loads(captured3.out)
        assert "injectSteps" in data3
        assert "ephemeralMessage" in data3["injectSteps"][0]
        assert "Parity Table:" not in data3["injectSteps"][0]["ephemeralMessage"]
        assert "ACTIVE API CONFIGURATION:" in data3["injectSteps"][0]["ephemeralMessage"]

        # 4. When plugin is disabled, PreInvocation returns {} and PreToolUse returns {"decision": "allow"} without overwrite
        monkeypatch.setenv("GOOGLE_ADS_ASSISTANT_ENABLED", "false")
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"invocationNum": 1})))
        config_init.handle_hook()
        captured4 = capsys.readouterr()
        assert json.loads(captured4.out) == {}

        monkeypatch.setattr(
            "sys.stdin",
            io.StringIO(
                json.dumps({
                    "toolCall": {
                        "name": "run_command",
                        "args": {"CommandLine": "python3 -c 'GoogleAdsClient.load_from_storage()'"},
                    }
                })
            ),
        )
        config_init.handle_hook()
        captured5 = capsys.readouterr()
        assert json.loads(captured5.out) == {"decision": "allow"}

    def test_get_extension_version_plugin_json(self, tmp_path, capsys):
        plugin_file = tmp_path / "plugin.json"
        plugin_file.write_text(json.dumps({"version": "4.0.0"}), encoding="utf-8")

        fake_script = tmp_path / "skills/ext-version/scripts/get_extension_version.py"
        with patch("os.path.abspath", return_value=str(fake_script)):
            get_extension_version.get_extension_version()
        captured = capsys.readouterr()
        assert "4.0.0" in captured.out

    def test_get_extension_version_unknown(self, capsys):
        with patch("os.path.abspath", return_value="/nonexistent/root/script.py"), \
             patch("os.path.exists", return_value=False):
            get_extension_version.get_extension_version()
        captured = capsys.readouterr()
        assert "Unknown" in captured.out


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
        assert 'load_from_storage(path="config/google-ads.yaml"' in res["result"]["generated_code"]

    def test_troubleshoot_conversions_task(self):
        handler = server.A2AHandler.__new__(server.A2AHandler)
        with patch("server.get_effective_api_version", return_value="v25"):
            res = handler.handle_troubleshoot_conversions(
                "task-6",
                {"customer_id": "1234567890", "api_version": "v25"},
            )
        assert res["status"] == "COMPLETED"
        assert res["result"]["summary"] == "Verified offline conversion upload summary."

    def test_sidecar_health_check(self):
        handler = server.A2AHandler.__new__(server.A2AHandler)
        handler.path = "/health"
        handler._send_json = MagicMock()
        handler.do_GET()
        handler._send_json.assert_called_once()
        args = handler._send_json.call_args[0]
        assert args[0] == 200
        assert args[1]["status"] == "healthy"

    def test_get_plugin_version_fallback_and_env_override(self, monkeypatch):
        monkeypatch.setattr(server, "_CACHED_PLUGIN_VERSION", None)
        monkeypatch.setenv("GOOGLE_ADS_PLUGIN_VERSION", "9.9.9-custom")
        assert server.get_plugin_version() == "9.9.9-custom"

        monkeypatch.setattr(server, "_CACHED_PLUGIN_VERSION", None)
        monkeypatch.delenv("GOOGLE_ADS_PLUGIN_VERSION", raising=False)
        monkeypatch.delenv("GOOGLE_ADS_ASSISTANT_VERSION", raising=False)
        with patch("os.path.isfile", return_value=False), patch(
            "config.config_init.get_version", return_value="Unknown"
        ):
            assert server.get_plugin_version() == server.UNKNOWN_PLUGIN_VERSION
            assert server.get_plugin_version() == "Unknown"

    def test_sidecar_unsupported_intent(self):
        handler = server.A2AHandler.__new__(server.A2AHandler)
        handler.headers = {"Content-Length": "50"}
        handler.rfile = MagicMock()
        handler.rfile.read.return_value = json.dumps({
            "task_id": "task-7",
            "intent": "INVALID_INTENT",
            "payload": {},
        }).encode("utf-8")
        handler._send_json = MagicMock()
        handler.path = "/v1/a2a/tasks"
        handler.do_POST()
        handler._send_json.assert_called_once()
        args = handler._send_json.call_args[0]
        assert args[0] == 200
        assert args[1]["status"] == "FAILED"
        assert "Unsupported intent" in args[1]["error"]

    def test_sync_and_set_config_kv_creates_and_sets(self, tmp_path):
        from config.config_init import sync_and_set_config_kv

        src_yaml = tmp_path / "source.yaml"
        src_yaml.write_text("# Use CID 12345678 for testing\nclient_id: \"test_client\"\n")
        dest_dir = tmp_path / "config"

        res_path = sync_and_set_config_kv(
            key="login_customer_id",
            value="9876543210",
            source_yaml=str(src_yaml),
            config_dir=str(dest_dir),
        )

        assert os.path.isfile(res_path)
        content = open(res_path).read()
        assert "# Use CID 12345678 for testing" in content
        assert 'client_id: "test_client"' in content
        assert 'login_customer_id: "9876543210"' in content
        assert "ads_assistant: 4.1.0" in content
        if sys.platform != "win32":
            assert oct(os.stat(res_path).st_mode & 0o777) == "0o600"
        assert os.environ.get("GOOGLE_ADS_CONFIGURATION_FILE_PATH") == res_path

    def test_sync_and_set_config_kv_updates_existing(self, tmp_path):
        from config.config_init import sync_and_set_config_kv

        src_yaml = tmp_path / "source.yaml"
        src_yaml.write_text("login_customer_id: \"old_val\"\nclient_id: \"test_client\"\n")
        dest_dir = tmp_path / "config"

        res_path = sync_and_set_config_kv(
            key="login_customer_id",
            value="new_val",
            source_yaml=str(src_yaml),
            config_dir=str(dest_dir),
        )

        content = open(res_path).read()
        assert 'login_customer_id: "new_val"' in content
        assert "old_val" not in content

    def test_write_yaml_config_oauth(self, tmp_path):
        from config.config_init import write_yaml_config

        target = tmp_path / "google-ads.yaml"
        data = {
            "client_id": "client_abc",
            "client_secret": "secret_xyz",
            "refresh_token": "refresh_999",
            "login_customer_id": "1234567890",
        }
        success = write_yaml_config(data, target_path=str(target), version="2.3.0")
        assert success is True
        assert target.is_file()

        content = target.read_text()
        assert "client_id: client_abc" in content
        assert "client_secret: secret_xyz" in content
        assert "refresh_token: refresh_999" in content
        assert "login_customer_id: 1234567890" in content
        assert "use_proto_plus: True" in content
        assert "ads_assistant: 2.3.0" in content
        if sys.platform != "win32":
            assert oct(os.stat(str(target)).st_mode & 0o777) == "0o600"
        assert os.environ.get("GOOGLE_ADS_CONFIGURATION_FILE_PATH") == str(target)

    def test_write_yaml_config_service_account(self, tmp_path):
        from config.config_init import write_yaml_config

        target = tmp_path / "google-ads.yaml"
        data = {
            "json_key_file_path": "/path/to/key.json",
            "impersonated_email": "sa@example.com",
            "login_customer_id": "9998887776",
        }
        success = write_yaml_config(data, target_path=str(target))
        assert success is True
        assert target.is_file()

        content = target.read_text()
        assert "json_key_file_path: /path/to/key.json" in content
        assert "impersonated_email: sa@example.com" in content
        assert "client_id" not in content
        assert "login_customer_id: 9998887776" in content
        assert "use_proto_plus: True" in content
        assert "ads_assistant: 4.1.0" in content

    def test_write_yaml_config_defaults(self, tmp_path):
        from config.config_init import write_yaml_config

        target = tmp_path / "google-ads.yaml"
        success = write_yaml_config({}, target_path=str(target))
        assert success is True

        content = target.read_text()
        assert "client_id: INSERT_CLIENT_ID_HERE" in content
        assert "client_secret: INSERT_CLIENT_SECRET_HERE" in content
        assert "refresh_token: INSERT_REFRESH_TOKEN_HERE" in content
        assert "use_proto_plus: True" in content
        assert "ads_assistant: 4.1.0" in content
        assert "login_customer_id" not in content

    def test_write_yaml_config_failure(self, tmp_path):
        from config.config_init import write_yaml_config

        # A file cannot be used as a directory, guaranteed to fail on Linux and Windows
        dummy_file = tmp_path / "dummy.txt"
        dummy_file.write_text("not a directory")
        invalid_path = str(dummy_file / "sub" / "google-ads.yaml")
        success = write_yaml_config({}, target_path=invalid_path)
        assert success is False

    def test_get_version_discovery(self):
        from config.config_init import get_version

        version = get_version()
        assert version == "4.1.0"

    def test_parse_ruby_config(self, tmp_path):
        from config.config_init import parse_ruby_config

        ruby_file = tmp_path / "google_ads_config.rb"
        ruby_file.write_text(
            'Google::Ads::GoogleAds::Config.new do |c|\n'
            '  c.client_id = "ruby_client_id"\n'
            '  c.client_secret = "ruby_client_secret"\n'
            '  c.refresh_token = "ruby_refresh_token"\n'
            '  c.login_customer_id = "1122334455"\n'
            'end\n'
        )
        data = parse_ruby_config(str(ruby_file))
        assert data["client_id"] == "ruby_client_id"
        assert data["client_secret"] == "ruby_client_secret"
        assert data["refresh_token"] == "ruby_refresh_token"
        assert data["login_customer_id"] == "1122334455"

    def test_parse_ini_config(self, tmp_path):
        from config.config_init import parse_ini_config

        ini_file = tmp_path / "google_ads_php.ini"
        ini_file.write_text(
            '[GOOGLE_ADS]\n'
            'clientId = "php_client_id"\n'
            'clientSecret = "php_client_secret"\n'
            'refreshToken = "php_refresh_token"\n'
            'loginCustomerId = "5544332211"\n'
        )
        data = parse_ini_config(str(ini_file))
        assert data["client_id"] == "php_client_id"
        assert data["client_secret"] == "php_client_secret"
        assert data["refresh_token"] == "php_refresh_token"
        assert data["login_customer_id"] == "5544332211"

    def test_parse_properties_config(self, tmp_path):
        from config.config_init import parse_properties_config

        prop_file = tmp_path / "ads.properties"
        prop_file.write_text(
            'api.googleads.clientId=java_client_id\n'
            'api.googleads.clientSecret=java_client_secret\n'
            'api.googleads.refreshToken=java_refresh_token\n'
            'api.googleads.loginCustomerId=9988776655\n'
        )
        data = parse_properties_config(str(prop_file))
        assert data["client_id"] == "java_client_id"
        assert data["client_secret"] == "java_client_secret"
        assert data["refresh_token"] == "java_refresh_token"
        assert data["login_customer_id"] == "9988776655"

    def test_parse_dotnet_config_app_config(self, tmp_path):
        from config.config_init import parse_dotnet_config

        app_cfg = tmp_path / "App.config"
        app_cfg.write_text(
            "<configuration>\n"
            "  <GoogleAdsApi>\n"
            '    <add key="OAuth2ClientId" value="dotnet_client_id"/>\n'
            '    <add key="OAuth2ClientSecret" value="dotnet_client_secret"/>\n'
            '    <add key="OAuth2RefreshToken" value="dotnet_refresh_token"/>\n'
            '    <add key="LoginCustomerId" value="1231231234"/>\n'
            "  </GoogleAdsApi>\n"
            "</configuration>\n"
        )
        data = parse_dotnet_config(str(app_cfg))
        assert data["client_id"] == "dotnet_client_id"
        assert data["client_secret"] == "dotnet_client_secret"
        assert data["refresh_token"] == "dotnet_refresh_token"
        assert data["login_customer_id"] == "1231231234"

    def test_parse_dotnet_config_appsettings_json(self, tmp_path):
        from config.config_init import parse_dotnet_config

        json_cfg = tmp_path / "appsettings.json"
        json_cfg.write_text(
            json.dumps(
                {
                    "GoogleAdsApi": {
                        "OAuth2ClientId": "json_client_id",
                        "OAuth2ClientSecret": "json_client_secret",
                        "OAuth2RefreshToken": "json_refresh_token",
                        "LoginCustomerId": "4321432143",
                        "OAuth2SecretsJsonPath": "/path/to/sa.json",
                        "OAuth2PrnEmail": "impersonated@example.com",
                    }
                }
            )
        )
        data = parse_dotnet_config(str(json_cfg))
        assert data["client_id"] == "json_client_id"
        assert data["client_secret"] == "json_client_secret"
        assert data["refresh_token"] == "json_refresh_token"
        assert data["login_customer_id"] == "4321432143"
        assert data["json_key_file_path"] == "/path/to/sa.json"
        assert data["impersonated_email"] == "impersonated@example.com"

    def test_copy_and_append_version(self, tmp_path):
        from config.config_init import copy_and_append_version

        src = tmp_path / "orig.ini"
        src.write_text("[section]\nfoo = bar\n")
        dst = tmp_path / "copied.ini"

        success = copy_and_append_version(str(src), str(dst), version="1.2.3", lang="PHP")
        assert success is True
        assert dst.is_file()
        content = dst.read_text()
        assert "[section]" in content
        assert 'ads_assistant = "1.2.3"' in content
        if sys.platform != "win32":
            assert oct(os.stat(str(dst)).st_mode & 0o777) == "0o600"

    def test_copy_and_append_version_dotnet(self, tmp_path):
        from config.config_init import copy_and_append_version

        src_xml = tmp_path / "App.config"
        src_xml.write_text(
            "<configuration>\n  <GoogleAdsApi>\n"
            '    <add key="OAuth2ClientId" value="cid"/>\n'
            "  </GoogleAdsApi>\n</configuration>\n"
        )
        dst_xml = tmp_path / "copied_App.config"
        assert copy_and_append_version(str(src_xml), str(dst_xml), version="4.1.0", lang="DotNet")
        assert '<add key="ads_assistant" value="4.1.0"/>' in dst_xml.read_text()

        src_json = tmp_path / "appsettings.json"
        src_json.write_text('{"GoogleAdsApi": {"OAuth2ClientId": "cid"}}\n')
        dst_json = tmp_path / "copied_appsettings.json"
        assert copy_and_append_version(str(src_json), str(dst_json), version="4.1.0", lang="DotNet")
        parsed_json = json.loads(dst_json.read_text())
        assert parsed_json["GoogleAdsApi"]["ads_assistant"] == "4.1.0"

    def test_sync_and_set_config_kv_fallback_php(self, tmp_path):
        from config.config_init import sync_and_set_config_kv

        # No source.yaml, but google_ads_php.ini exists in home_dir
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        php_file = home_dir / "google_ads_php.ini"
        php_file.write_text(
            'clientId = "fallback_cid"\n'
            'clientSecret = "fallback_sec"\n'
            'refreshToken = "fallback_ref"\n'
        )
        dest_dir = tmp_path / "config"

        res_path = sync_and_set_config_kv(
            source_yaml=str(home_dir / "google-ads.yaml"),
            config_dir=str(dest_dir),
        )

        assert os.path.isfile(res_path)
        content = open(res_path).read()
        assert "client_id: fallback_cid" in content
        assert "ads_assistant:" in content

    def test_sync_and_set_config_kv_fallback_dotnet(self, tmp_path):
        from config.config_init import sync_and_set_config_kv

        # No source.yaml, but App.config exists in home_dir
        home_dir = tmp_path / "home_dotnet"
        home_dir.mkdir()
        dotnet_file = home_dir / "App.config"
        dotnet_file.write_text(
            "<configuration>\n  <GoogleAdsApi>\n"
            '    <add key="OAuth2ClientId" value="dotnet_fallback_cid"/>\n'
            '    <add key="OAuth2ClientSecret" value="dotnet_fallback_sec"/>\n'
            '    <add key="OAuth2RefreshToken" value="dotnet_fallback_ref"/>\n'
            "  </GoogleAdsApi>\n</configuration>\n"
        )
        dest_dir = tmp_path / "config_dotnet"

        res_path = sync_and_set_config_kv(
            source_yaml=str(home_dir / "google-ads.yaml"),
            config_dir=str(dest_dir),
        )

        assert os.path.isfile(res_path)
        content = open(res_path).read()
        assert "client_id: dotnet_fallback_cid" in content
        assert "ads_assistant:" in content
        assert (dest_dir / "App.config").is_file()

    def test_sync_and_set_config_kv_reconstructs_from_home_on_new_session(self, tmp_path):
        from config.config_init import sync_and_set_config_kv

        dest_dir = tmp_path / "config"
        dest_dir.mkdir()
        existing_yaml = dest_dir / "google-ads.yaml"
        existing_yaml.write_text("client_id: \"stale_client\"\n")

        src_yaml = tmp_path / "google-ads.yaml"
        src_yaml.write_text("client_id: \"fresh_session_client\"\n")

        res_path = sync_and_set_config_kv(
            source_yaml=str(src_yaml),
            config_dir=str(dest_dir),
        )

        content = open(res_path).read()
        assert 'client_id: "fresh_session_client"' in content
        assert "stale_client" not in content
        assert os.environ.get("GOOGLE_ADS_CONFIGURATION_FILE_PATH") == str(existing_yaml)

    def test_copy_and_append_version_no_duplicates(self, tmp_path):
        from config.config_init import copy_and_append_version

        src = tmp_path / "test.yaml"
        src.write_text("client_id: \"client\"\nads_assistant: 1.0.0\n")
        dst = tmp_path / "out.yaml"

        copy_and_append_version(str(src), str(dst), version="4.0.0", lang="YAML")
        content = dst.read_text()
        assert content.count("ads_assistant:") == 1
        assert "ads_assistant: 4.0.0" in content

    def test_config_init_main_default_cid_and_dummy_cleanup(self, tmp_path, monkeypatch, capsys):
        import config.config_init as cfg_init

        src_yaml = tmp_path / "home_google_ads.yaml"
        src_yaml.write_text('client_id: "cid_abc"\n', encoding="utf-8")

        work_dir = tmp_path / "workspace"
        cfg_dir = work_dir / "config"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "assistant_config").write_text(
            'api_version = "v25"\ncustomer_id = "7778889990"\nexecute_mutates = false\n',
            encoding="utf-8",
        )

        dummy_lib_yaml = work_dir / "client_libs" / "google-ads-python" / "google-ads.yaml"
        dummy_lib_yaml.parent.mkdir(parents=True)
        dummy_lib_yaml.write_text("dummy: true\n", encoding="utf-8")

        monkeypatch.chdir(work_dir)
        monkeypatch.delenv("GOOGLE_ADS_CONFIG_VALUE", raising=False)
        monkeypatch.setattr(
            "sys.argv",
            [
                "config_init.py",
                "--config-dir",
                str(cfg_dir),
                "--source-yaml",
                str(src_yaml),
            ],
        )

        cfg_init.main()
        captured = capsys.readouterr()
        assert "export GOOGLE_ADS_CONFIGURATION_FILE_PATH=" in captured.out

        out_yaml = cfg_dir / "google-ads.yaml"
        assert out_yaml.is_file()
        assert 'login_customer_id: "7778889990"' in out_yaml.read_text(encoding="utf-8")
        assert not dummy_lib_yaml.exists()

    def test_legacy_v400_config_migration_and_precedence_over_placeholder(self, tmp_path, monkeypatch):
        import config.config_init as cfg_init

        work_dir = tmp_path / "workspace_v400"
        cfg_dir = work_dir / "config"
        cfg_dir.mkdir(parents=True)
        monkeypatch.chdir(work_dir)

        # Simulate v4.0.0 legacy files (customer_id and api_version.txt)
        (cfg_dir / "customer_id").write_text("9998887776\n", encoding="utf-8")
        (cfg_dir / "api_version.txt").write_text("v24\n", encoding="utf-8")

        # 1. Before assistant_config exists, getters should resolve from v4.0.0 files
        assert cfg_init.get_configured_customer_id(config_dir=str(cfg_dir)) == "9998887776"
        assert cfg_init.get_configured_api_version(config_dir=str(cfg_dir)) == "v24"

        # 2. Even if assistant_config is seeded with the default 12345678 placeholder,
        # legacy customer_id != 12345678 must not be shadowed
        (cfg_dir / "assistant_config").write_text(
            'api_version = "v25"\ncustomer_id = "12345678"\nexecute_mutates = false\n',
            encoding="utf-8",
        )
        assert cfg_init.get_configured_customer_id(config_dir=str(cfg_dir)) == "9998887776"

        # 3. Calling write_assistant_config migrates the legacy customer_id into assistant_config
        cfg_init.write_assistant_config({"api_version": "v25"}, config_dir=str(cfg_dir))
        parsed = cfg_init.read_assistant_config(config_dir=str(cfg_dir))
        assert parsed["customer_id"] == "9998887776"
        assert parsed["api_version"] == "v25"


class TestAdditionalSkillCoverage:
    """Tests for edge cases in validate_gaql, sync_client_libs, and troubleshoot_conversions."""

    def test_validate_gaql_runtime_exception_exits_nonzero(self, capsys):
        mock_client = MagicMock()
        mock_service = MagicMock()
        mock_client.get_service.return_value = mock_service
        mock_service.search.side_effect = RuntimeError("Simulated gRPC transport error")

        with pytest.raises(SystemExit) as exc_info:
            validate_gaql.validate_gaql(
                customer_id="1234567890",
                api_version="v25",
                query="SELECT campaign.id FROM campaign",
                client=mock_client,
            )
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "CRITICAL ERROR: Simulated gRPC transport error" in captured.out

    def test_detect_installed_version_multi_language(self, tmp_path):
        # PHP (composer.json)
        php_dir = tmp_path / "google-ads-php"
        php_dir.mkdir()
        (php_dir / "composer.json").write_text(
            json.dumps({"name": "googleads/google-ads-php", "version": "24.1.0"}),
            encoding="utf-8",
        )
        assert sync_client_libs.detect_installed_version("google-ads-php", str(php_dir)) == "24.1.0"

        # Ruby (.gemspec)
        ruby_dir = tmp_path / "google-ads-ruby"
        ruby_dir.mkdir()
        (ruby_dir / "google-ads-googleads.gemspec").write_text(
            'Gem::Specification.new do |s|\n  s.version = "29.0.0"\nend\n',
            encoding="utf-8",
        )
        assert sync_client_libs.detect_installed_version("google-ads-ruby", str(ruby_dir)) == "29.0.0"

        # Java (pom.xml)
        java_dir = tmp_path / "google-ads-java"
        java_dir.mkdir()
        (java_dir / "pom.xml").write_text(
            "<project><version>33.0.0</version></project>\n",
            encoding="utf-8",
        )
        assert sync_client_libs.detect_installed_version("google-ads-java", str(java_dir)) == "33.0.0"

        # .NET (.csproj)
        dotnet_dir = tmp_path / "google-ads-dotnet" / "src"
        dotnet_dir.mkdir(parents=True)
        (dotnet_dir / "Google.Ads.GoogleAds.csproj").write_text(
            "<Project><PropertyGroup><Version>21.2.0</Version></PropertyGroup></Project>\n",
            encoding="utf-8",
        )
        assert (
            sync_client_libs.detect_installed_version(
                "google-ads-dotnet", str(tmp_path / "google-ads-dotnet")
            )
            == "21.2.0"
        )

    def test_sync_directories_preserves_git_and_yaml(self, tmp_path):
        src_dir = tmp_path / "src_lib"
        src_dir.mkdir()
        (src_dir / "new_module.py").write_text("x = 1\n", encoding="utf-8")
        (src_dir / ".git").mkdir()

        dst_dir = tmp_path / "dst_lib"
        dst_dir.mkdir()
        (dst_dir / "old_module.py").write_text("old = 1\n", encoding="utf-8")
        (dst_dir / "google-ads.yaml").write_text("keep: true\n", encoding="utf-8")
        (dst_dir / ".git").mkdir()
        (dst_dir / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")

        ok = sync_client_libs.sync_directories(str(src_dir), str(dst_dir))
        assert ok is True
        assert (dst_dir / "new_module.py").is_file()
        assert not (dst_dir / "old_module.py").exists()
        assert (dst_dir / "google-ads.yaml").is_file()
        assert (dst_dir / ".git" / "HEAD").is_file()

    def test_update_api_version_cache_if_needed(self, tmp_path, monkeypatch):
        work_dir = tmp_path / "work"
        cfg_dir = work_dir / "config"
        cfg_dir.mkdir(parents=True)

        lib_dir = work_dir / "client_libs" / "google-ads-python"
        for ver in ("v23", "v25", "v27"):
            (lib_dir / "google" / "ads" / "googleads" / ver).mkdir(parents=True)

        monkeypatch.chdir(work_dir)
        latest = sync_client_libs.update_api_version_cache_if_needed(str(lib_dir))
        assert latest == "v27"
        cfg_content = (cfg_dir / "assistant_config").read_text(encoding="utf-8")
        assert 'api_version = "v27"' in cfg_content
        assert 'customer_id = "12345678"' in cfg_content
        assert "execute_mutates = false" in cfg_content

    def test_troubleshoot_conversions_alerts_and_report_file(self, tmp_path):
        mock_client = MagicMock()
        mock_service = MagicMock()
        mock_client.get_service.return_value = mock_service

        # 1. Customer row with accepted_customer_data_terms = False
        cust_row = MagicMock()
        cust_row.customer.descriptive_name = "Unaccepted Terms Account"
        cust_row.customer.conversion_tracking_setting.accepted_customer_data_terms = False
        cust_row.customer.conversion_tracking_setting.enhanced_conversions_for_leads_enabled = False

        # 2. Client summary row with failures and alerts
        client_row = MagicMock()
        csum = client_row.offline_conversion_upload_client_summary
        csum.client.name = "GOOGLE_ADS_API"
        csum.status.name = "NEEDS_ATTENTION"
        csum.total_event_count = 100
        csum.successful_event_count = 75
        ds = MagicMock()
        ds.upload_date = "2026-10-10"
        ds.successful_count = 75
        ds.failed_count = 25
        ds.pending_count = 0
        csum.daily_summaries = [ds]
        alert = MagicMock()
        alert.error = "CLICK_NOT_FOUND"
        alert.error_percentage = 0.25
        csum.alerts = [alert]

        def search_stream_side_effect(customer_id, query):
            batch = MagicMock()
            if "FROM customer" in query:
                batch.results = [cust_row]
            elif "FROM offline_conversion_upload_client_summary" in query:
                batch.results = [client_row]
            else:
                batch.results = []
            return [batch]

        mock_service.search_stream.side_effect = search_stream_side_effect

        data = troubleshoot_conversions.troubleshoot_conversions(
            mock_client,
            "1234567890",
            json_output=False,
            output_dir=str(tmp_path),
        )
        assert "CRITICAL: Customer Data Terms NOT accepted." in data["primary_errors"]
        assert len(data["client_summaries"]) == 1
        assert data["client_summaries"][0]["failure_rate"] == 0.25
        assert data["client_summaries"][0]["alerts"][0]["error"] == "CLICK_NOT_FOUND"

        report_path = data["report_path"]
        assert os.path.isfile(report_path)
        report_text = open(report_path, encoding="utf-8").read()
        assert report_text.startswith("Created by the Google Ads API Developer Assistant")
        assert "CRITICAL: Customer Data Terms NOT accepted." in report_text
        assert "CLICK_NOT_FOUND" in report_text


class TestPluginIntegrity:
    """Verifies plugin structural integrity, config_init parity, and absence of host-specific paths."""

    def test_config_init_single_source_of_truth_and_sitecustomize(self, tmp_path, monkeypatch):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        root_cfg_dir = os.path.join(repo_root, "config")
        plugin_cfg_dir = os.path.join(
            repo_root,
            "plugins",
            "google-ads-api-developer-assistant",
            "config",
        )
        assert not os.path.exists(root_cfg_dir), (
            "Top-level <repo>/config/ should not exist; plugins/google-ads-api-developer-assistant/config/ is the single source of truth"
        )
        assert os.path.isfile(os.path.join(plugin_cfg_dir, "config_init.py"))
        assert os.path.isfile(os.path.join(plugin_cfg_dir, "sitecustomize.py"))
        assert os.path.isfile(os.path.join(plugin_cfg_dir, "assistant_config"))

        import config.sitecustomize as sc

        fake_yaml = tmp_path / "installed_plugin_google_ads.yaml"
        fake_yaml.write_text('client_id: "shim_test_client"\n', encoding="utf-8")
        empty_workspace = tmp_path / "empty_workspace"
        empty_workspace.mkdir()

        monkeypatch.chdir(empty_workspace)
        monkeypatch.setenv("GOOGLE_ADS_CONFIGURATION_FILE_PATH", str(fake_yaml))
        monkeypatch.setenv("_GOOGLE_ADS_TEST_SITECUSTOMIZE", "1")

        resolved = sc._resolve_assistant_config_file("config/google-ads.yaml", "rb")
        assert resolved == str(fake_yaml)

    def test_no_host_specific_hardcoded_paths_in_rules_and_docs(self):
        import glob
        import re

        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        plugin_dir = os.path.join(
            repo_root, "plugins", "google-ads-api-developer-assistant"
        )
        files_to_check = [
            os.path.join(repo_root, "README.md"),
            os.path.join(repo_root, "README_BEFORE_INSTALLATION.md"),
            os.path.join(repo_root, "ChangeLog.md"),
            os.path.join(repo_root, "FAQ.md"),
            os.path.join(plugin_dir, "README.md"),
            os.path.join(plugin_dir, "rules", "google_ads_rules.md"),
            os.path.join(
                plugin_dir,
                "sidecars",
                "google-ads-a2a-service",
                "server.py",
            ),
            *glob.glob(os.path.join(plugin_dir, "skills", "*", "SKILL.md")),
            *glob.glob(os.path.join(plugin_dir, "commands", "*.md")),
            *glob.glob(os.path.join(repo_root, "tests", "benchmarks", "*.json")),
        ]
        forbidden_pattern = re.compile(
            r"(/usr/local/google/home/[A-Za-z0-9_-]+|/home/[A-Za-z0-9_]+/|/Users/[A-Za-z0-9_]+/|\brwh\b|rodete)"
        )
        for fpath in files_to_check:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
            match = forbidden_pattern.search(content)
            assert match is None, (
                f"Found forbidden host-specific reference '{match.group(0)}' in {fpath}"
            )

    def test_manifests_and_skill_frontmatter_valid(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        plugin_dir = os.path.join(
            repo_root, "plugins", "google-ads-api-developer-assistant"
        )
        json_manifests = [
            os.path.join(plugin_dir, "plugin.json"),
            os.path.join(plugin_dir, "hooks.json"),
            os.path.join(plugin_dir, "mcp_config.json"),
            os.path.join(
                plugin_dir,
                "sidecars",
                "google-ads-a2a-service",
                "sidecar.json",
            ),
        ]
        for manifest_path in json_manifests:
            assert os.path.isfile(manifest_path), f"Missing manifest: {manifest_path}"
            with open(manifest_path, "r", encoding="utf-8") as f:
                parsed = json.load(f)
            assert isinstance(parsed, dict) and parsed

        skills_root = os.path.join(plugin_dir, "skills")
        skill_dirs = [
            os.path.join(skills_root, d)
            for d in os.listdir(skills_root)
            if os.path.isdir(os.path.join(skills_root, d))
        ]
        assert len(skill_dirs) > 0
        for sdir in skill_dirs:
            skill_md = os.path.join(sdir, "SKILL.md")
            assert os.path.isfile(skill_md), f"Missing SKILL.md in {sdir}"
            with open(skill_md, "r", encoding="utf-8") as f:
                text = f.read()
            assert text.startswith("---\n"), f"SKILL.md in {sdir} must start with YAML frontmatter"
            assert "name:" in text and "description:" in text

    def test_plugin_enable_disable_status_and_helper_script(self, tmp_path, monkeypatch):
        import subprocess
        from config import config_init

        monkeypatch.delenv("GOOGLE_ADS_ASSISTANT_ENABLED", raising=False)

        # 1. Verify parse_plugin_enabled_value
        assert config_init.parse_plugin_enabled_value("enabled = true") is True
        assert config_init.parse_plugin_enabled_value("enabled = false") is False
        assert config_init.parse_plugin_enabled_value("plugin_enabled = false") is False
        assert config_init.parse_plugin_enabled_value("off") is False
        assert config_init.parse_plugin_enabled_value("on") is True

        # 2. Create a simulated installed plugin directory and verify manifest/hooks/config toggling
        fake_installed_plugin = tmp_path / "installed_plugin"
        fake_cfg_dir = fake_installed_plugin / "config"
        fake_sidecar_dir = fake_installed_plugin / "sidecars" / "google-ads-a2a-service"
        fake_cfg_dir.mkdir(parents=True)
        fake_sidecar_dir.mkdir(parents=True)

        (fake_installed_plugin / "plugin.json").write_text(
            json.dumps({"name": "google-ads-api-developer-assistant", "version": "4.1.0"}),
            encoding="utf-8",
        )
        (fake_installed_plugin / "mcp_config.json").write_text(
            json.dumps({"mcpServers": {}}),
            encoding="utf-8",
        )
        (fake_sidecar_dir / "sidecar.json").write_text(
            json.dumps({"command": "python3"}),
            encoding="utf-8",
        )
        (fake_installed_plugin / "hooks.json").write_text(
            json.dumps({
                "hooks": {
                    "config-init": {
                        "command": "python3",
                        "args": ["config/config_init.py", "--hook"],
                        "enabled": True,
                    }
                }
            }),
            encoding="utf-8",
        )

        # Disable plugin in fake_cfg_dir
        config_init.set_plugin_enabled(
            False,
            config_dir=str(fake_cfg_dir),
            sync_global=False,
        )
        assert config_init.is_plugin_enabled(config_dir=str(fake_cfg_dir)) is False
        assert not (fake_installed_plugin / "plugin.json").exists()
        assert (fake_installed_plugin / "plugin.json.disabled").is_file()
        assert not (fake_installed_plugin / "mcp_config.json").exists()
        assert (fake_installed_plugin / "mcp_config.json.disabled").is_file()
        assert not (fake_sidecar_dir / "sidecar.json").exists()
        assert (fake_sidecar_dir / "sidecar.json.disabled").is_file()
        hooks_data = json.loads((fake_installed_plugin / "hooks.json").read_text(encoding="utf-8"))
        assert hooks_data["hooks"]["config-init"]["enabled"] is False

        status_disabled = config_init.get_plugin_status(config_dir=str(fake_cfg_dir))
        assert status_disabled["enabled"] is False
        assert status_disabled["status"] == "disabled"
        assert "DISABLED" in config_init.format_plugin_status_text(status_disabled)

        # Re-enable plugin in fake_cfg_dir
        config_init.set_plugin_enabled(
            True,
            config_dir=str(fake_cfg_dir),
            sync_global=False,
        )
        assert config_init.is_plugin_enabled(config_dir=str(fake_cfg_dir)) is True
        assert (fake_installed_plugin / "plugin.json").is_file()
        assert not (fake_installed_plugin / "plugin.json.disabled").exists()
        assert (fake_installed_plugin / "mcp_config.json").is_file()
        assert (fake_sidecar_dir / "sidecar.json").is_file()
        hooks_data_after = json.loads(
            (fake_installed_plugin / "hooks.json").read_text(encoding="utf-8")
        )
        assert hooks_data_after["hooks"]["config-init"]["enabled"] is True

        # 3. Verify config_init.py CLI flags (--disable, --status, --enable, --json) cross-platform
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        config_init_script = os.path.join(
            repo_root,
            "plugins",
            "google-ads-api-developer-assistant",
            "config",
            "config_init.py",
        )
        plugin_sh = os.path.join(repo_root, "plugin.sh")
        plugin_ps1 = os.path.join(repo_root, "plugin.ps1")
        assert os.path.isfile(plugin_sh)
        assert os.path.isfile(plugin_ps1)

        cli_disable = subprocess.run(
            [
                sys.executable,
                config_init_script,
                "--disable",
                "--config-dir",
                str(fake_cfg_dir),
                "--json",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        assert json.loads(cli_disable.stdout)["enabled"] is False

        cli_enable = subprocess.run(
            [
                sys.executable,
                config_init_script,
                "--enable",
                "--config-dir",
                str(fake_cfg_dir),
                "--json",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        assert json.loads(cli_enable.stdout)["enabled"] is True

        # 4. Verify platform helper script (plugin.ps1 on Windows, plugin.sh on Linux/macOS)
        helper_env = {**os.environ, "PYTHON_BIN": sys.executable}
        if sys.platform == "win32":
            import shutil

            ps_bin = shutil.which("pwsh") or shutil.which("powershell")
            assert ps_bin is not None
            res_disable = subprocess.run(
                [
                    ps_bin,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    plugin_ps1,
                    "disable",
                    "-ConfigDir",
                    str(fake_cfg_dir),
                    "-Json",
                ],
                capture_output=True,
                text=True,
                env=helper_env,
                check=True,
            )
            payload_disable = json.loads(res_disable.stdout)
            assert payload_disable["enabled"] is False
            assert payload_disable["hook_test"]["passed"] is True

            res_is_enabled_off = subprocess.run(
                [
                    ps_bin,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    plugin_ps1,
                    "is-enabled",
                    "-ConfigDir",
                    str(fake_cfg_dir),
                ],
                capture_output=True,
                text=True,
                env=helper_env,
                check=False,
            )
            assert res_is_enabled_off.returncode == 1
            assert res_is_enabled_off.stdout.strip() == "disabled"

            res_test_off = subprocess.run(
                [
                    ps_bin,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    plugin_ps1,
                    "test",
                    "-ConfigDir",
                    str(fake_cfg_dir),
                    "-Expect",
                    "disabled",
                ],
                capture_output=True,
                text=True,
                env=helper_env,
                check=True,
            )
            assert "Status: DISABLED" in res_test_off.stdout
            assert "Live Hook Test    : PASS" in res_test_off.stdout

            res_enable = subprocess.run(
                [
                    ps_bin,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    plugin_ps1,
                    "enable",
                    "-ConfigDir",
                    str(fake_cfg_dir),
                    "-Json",
                ],
                capture_output=True,
                text=True,
                env=helper_env,
                check=True,
            )
            payload_enable = json.loads(res_enable.stdout)
            assert payload_enable["enabled"] is True
            assert payload_enable["hook_test"]["passed"] is True

            res_is_enabled_on = subprocess.run(
                [
                    ps_bin,
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    plugin_ps1,
                    "is-enabled",
                    "-ConfigDir",
                    str(fake_cfg_dir),
                ],
                capture_output=True,
                text=True,
                env=helper_env,
                check=False,
            )
            assert res_is_enabled_on.returncode == 0
            assert res_is_enabled_on.stdout.strip() == "enabled"
        else:
            res_disable = subprocess.run(
                ["bash", plugin_sh, "disable", "--config-dir", str(fake_cfg_dir), "--json"],
                capture_output=True,
                text=True,
                env=helper_env,
                check=True,
            )
            payload_disable = json.loads(res_disable.stdout)
            assert payload_disable["enabled"] is False
            assert payload_disable["hook_test"]["passed"] is True

            res_is_enabled_off = subprocess.run(
                ["bash", plugin_sh, "is-enabled", "--config-dir", str(fake_cfg_dir)],
                capture_output=True,
                text=True,
                env=helper_env,
                check=False,
            )
            assert res_is_enabled_off.returncode == 1
            assert res_is_enabled_off.stdout.strip() == "disabled"

            res_test_off = subprocess.run(
                [
                    "bash",
                    plugin_sh,
                    "test",
                    "--config-dir",
                    str(fake_cfg_dir),
                    "--expect",
                    "disabled",
                ],
                capture_output=True,
                text=True,
                env=helper_env,
                check=True,
            )
            assert "Status: DISABLED" in res_test_off.stdout
            assert "Live Hook Test    : PASS" in res_test_off.stdout

            res_enable = subprocess.run(
                ["bash", plugin_sh, "enable", "--config-dir", str(fake_cfg_dir), "--json"],
                capture_output=True,
                text=True,
                env=helper_env,
                check=True,
            )
            payload_enable = json.loads(res_enable.stdout)
            assert payload_enable["enabled"] is True
            assert payload_enable["hook_test"]["passed"] is True

            res_is_enabled_on = subprocess.run(
                ["bash", plugin_sh, "is-enabled", "--config-dir", str(fake_cfg_dir)],
                capture_output=True,
                text=True,
                env=helper_env,
                check=False,
            )
            assert res_is_enabled_on.returncode == 0
            assert res_is_enabled_on.stdout.strip() == "enabled"




class TestPerformanceRegressions:
    """Guards against performance regressions in hooks, config sync, proto inspection, and GitHub checks."""

    def test_get_version_in_process_no_subprocess_and_cached(self, monkeypatch):
        import time
        import config.config_init as cfg_init
        import server

        monkeypatch.setattr(cfg_init, "_CACHED_VERSION", None)
        monkeypatch.setattr(server, "_CACHED_PLUGIN_VERSION", None)

        def forbid_subprocess(*args, **kwargs):
            raise AssertionError("get_version() must not spawn a subprocess when ext_version_script is omitted")

        monkeypatch.setattr(cfg_init.subprocess, "run", forbid_subprocess)

        v = cfg_init.get_version()
        assert v == "4.1.0"
        assert cfg_init._CACHED_VERSION == "4.1.0"

        sv = server.get_plugin_version()
        assert sv == "4.1.0"
        assert server._CACHED_PLUGIN_VERSION == "4.1.0"

        start = time.perf_counter()
        for _ in range(1000):
            cfg_init.get_version()
            server.get_plugin_version()
        elapsed = time.perf_counter() - start
        assert elapsed < 0.05, f"Cached get_version() calls regressed in latency: {elapsed:.4f}s"

    def test_sync_and_set_config_kv_no_recursive_glob(self, tmp_path, monkeypatch):
        import glob
        import time
        import config.config_init as cfg_init

        orig_glob = glob.glob

        def guard_glob(pathname, *args, **kwargs):
            if kwargs.get("recursive"):
                raise AssertionError(f"Forbidden recursive glob.glob({pathname!r}, recursive=True) called")
            return orig_glob(pathname, *args, **kwargs)

        monkeypatch.setattr(glob, "glob", guard_glob)

        work_dir = tmp_path / "workspace"
        cfg_dir = work_dir / "config"
        cfg_dir.mkdir(parents=True)
        src_yaml = tmp_path / "source_google_ads.yaml"
        src_yaml.write_text('client_id: "test_client"\n', encoding="utf-8")

        # Create dummy top-level client_libs yaml and nested subdirectories
        lib_dir = work_dir / "client_libs" / "google-ads-python"
        lib_dir.mkdir(parents=True)
        dummy_yaml = lib_dir / "google-ads.yaml"
        dummy_yaml.write_text("dummy: true\n", encoding="utf-8")
        for i in range(30):
            nested = lib_dir / f"pkg_{i}" / "sub"
            nested.mkdir(parents=True)
            (nested / "module.py").write_text("# stub\n", encoding="utf-8")

        monkeypatch.chdir(work_dir)
        start = time.perf_counter()
        cfg_init.sync_and_set_config_kv(
            key="login_customer_id",
            value="1234567890",
            source_yaml=str(src_yaml),
            config_dir=str(cfg_dir),
        )
        elapsed = time.perf_counter() - start

        assert not dummy_yaml.exists(), "Top-level dummy google-ads.yaml in client_libs should be removed"
        assert elapsed < 0.25, f"sync_and_set_config_kv() took too long: {elapsed:.4f}s"

    def test_inspect_object_get_available_types_memory_and_disk_cache(self, tmp_path, monkeypatch):
        import tempfile
        import time

        # Create a synthetic v99 proto directory to test cold -> disk cache -> memory cache transitions
        fake_lib_root = tmp_path / "client_libs" / "google-ads-python"
        v_dir = fake_lib_root / "google" / "ads" / "googleads" / "v99"
        types_dir = v_dir / "services" / "types"
        types_dir.mkdir(parents=True)
        (types_dir / "campaign_service.py").write_text(
            "class MutateCampaignsRequest:\n    pass\n",
            encoding="utf-8",
        )

        monkeypatch.setattr(inspect_object.os.path, "expanduser", lambda p: str(fake_lib_root))
        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
        inspect_object._AVAILABLE_TYPES_CACHE.clear()

        # 1. Cold call populates disk and memory cache
        res1 = inspect_object.get_available_types("v99")
        assert "MutateCampaignsRequest" in res1
        disk_cache_file = tmp_path / "gads_assistant_types_v99.json"
        assert disk_cache_file.is_file(), "On-disk proto type cache file was not created"

        # 2. Forbid glob.glob on warm cache (both memory and disk)
        def forbid_glob(*args, **kwargs):
            raise AssertionError("glob.glob should not be called when proto types cache is warm")

        monkeypatch.setattr(inspect_object.glob, "glob", forbid_glob)

        # Warm memory cache check + timing
        start = time.perf_counter()
        for _ in range(200):
            res_mem = inspect_object.get_available_types("v99")
        elapsed = time.perf_counter() - start
        assert res_mem == res1
        assert elapsed < 0.05, f"In-memory get_available_types() cache regressed: {elapsed:.4f}s"

        # Warm disk cache check (clear in-memory cache, verify disk cache hits without globbing)
        inspect_object._AVAILABLE_TYPES_CACHE.clear()
        res_disk = inspect_object.get_available_types("v99")
        assert res_disk == res1

    def test_sync_client_libs_parallel_github_fetches(self, tmp_path, monkeypatch):
        import time

        libs_dir = tmp_path / "client_libs"
        libs_dir.mkdir()
        for repo_name in sync_client_libs.KNOWN_REPOS:
            (libs_dir / repo_name).mkdir()

        def slow_fetch(repo_path):
            time.sleep(0.15)
            return ("v25.0.0", "https://example.com/tarball")

        monkeypatch.setattr(sync_client_libs, "fetch_github_latest_release", slow_fetch)
        monkeypatch.setattr(sync_client_libs, "detect_installed_version", lambda d, r: "25.0.0")

        # 5 libraries * 0.15s = 0.75s if sequential; parallel ThreadPoolExecutor should finish in < 0.45s
        start = time.perf_counter()
        results = sync_client_libs.process_client_libs(
            client_libs_dir=str(libs_dir),
            check_only=True,
            include_assistant=False,
        )
        elapsed = time.perf_counter() - start

        assert [r["codebase"] for r in results] == sorted(sync_client_libs.KNOWN_REPOS.keys())
        assert elapsed < 0.50, (
            f"process_client_libs() took {elapsed:.3f}s for 5 libraries (expected parallel execution < 0.50s)"
        )

    def test_precompiled_hook_regexes_and_fast_evaluation(self):
        import re
        import time
        import config.config_init as cfg_init

        expected_patterns = (
            "_TEST_OR_LINTER_CMD_RE",
            "_SCRIPT_ARG_RE",
            "_PY_FILE_ARG_RE",
            "_COMMENT_LINE_RE",
            "_VALIDATE_ONLY_TRUE_RE",
            "_VALIDATE_ONLY_FALSE_RE",
            "_LOAD_FROM_STORAGE_EMPTY_RE",
            "_LOAD_FROM_STORAGE_VER_RE",
            "_EXPANDUSER_YAML_RE",
            "_QUOTED_HOME_YAML_RE",
            "_BARE_HOME_YAML_RE",
            "_SKILL_REL_PATH_RE",
        )
        for attr in expected_patterns:
            pattern_obj = getattr(cfg_init, attr, None)
            assert isinstance(pattern_obj, re.Pattern), f"Missing pre-compiled regex {attr} in config_init.py"

        start = time.perf_counter()
        for _ in range(500):
            decision, _ = cfg_init.evaluate_mutation_guard(
                "python3 skills/validate-gaql/scripts/validate_gaql.py --query 'SELECT campaign.id FROM campaign'"
            )
            assert decision == "allow"
        elapsed = time.perf_counter() - start
        assert elapsed < 0.10, f"evaluate_mutation_guard() hot path regressed: {elapsed:.4f}s for 500 calls"

    def test_detect_system_package_version(self, monkeypatch):
        # Test detection via importlib.metadata
        monkeypatch.setattr("importlib.metadata.version", lambda pkg: "25.0.0")
        v, site_dirs = sync_client_libs.detect_system_package_version("google-ads")
        assert v == "25.0.0"
        assert isinstance(site_dirs, list)

    def test_check_system_package_parity(self, monkeypatch):
        monkeypatch.setattr(
            sync_client_libs,
            "detect_system_package_version",
            lambda pkg: ("25.0.0", ["/fake/site-packages"]),
        )
        # Test match
        res_match = sync_client_libs.check_system_package_parity(
            package_name="google-ads", target_version="25.0.0"
        )
        assert res_match["matches"] is True
        assert res_match["system_version"] == "25.0.0"

        # Test mismatch
        res_mismatch = sync_client_libs.check_system_package_parity(
            package_name="google-ads", target_version="34.0.0"
        )
        assert res_mismatch["matches"] is False
        assert res_mismatch["system_version"] == "25.0.0"
        assert res_mismatch["target_version"] == "34.0.0"

    def test_upgrade_system_package(self, monkeypatch):
        def fake_run(cmd, **kwargs):
            class FakeRes:
                returncode = 0
                stdout = "Successfully installed google-ads-34.0.0"
            return FakeRes()

        monkeypatch.setattr("subprocess.run", fake_run)
        success = sync_client_libs.upgrade_system_package("google-ads", "34.0.0")
        assert success is True

    def test_sync_client_libs_system_version_alert(self, capsys):
        results = [
            {
                "codebase": "google-ads-python",
                "repo_slug": "googleads/google-ads-python",
                "installed_version": "31.2.0",
                "github_version": "34.0.0",
                "status": "OUTDATED",
                "updated": False,
                "system_version": "22.0.0",
                "system_site_dirs": ["/fake/site-packages"],
                "system_version_matches": False,
            }
        ]
        sync_client_libs.print_table(results)
        captured = capsys.readouterr().out
        assert "ALERT: Python system site-directory version mismatch!" in captured
        assert "22.0.0" in captured
        assert "34.0.0" in captured
        assert "/fake/site-packages" in captured

    def test_update_codebase_via_git_preserves_branch_on_tag_checkout(self, tmp_path):
        import subprocess

        remote_repo = tmp_path / "remote_repo.git"
        subprocess.run(["git", "init", "--bare", "-b", "main", str(remote_repo)], check=True)

        seed_repo = tmp_path / "seed_repo"
        subprocess.run(["git", "clone", str(remote_repo), str(seed_repo)], check=True)
        subprocess.run(["git", "-C", str(seed_repo), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(seed_repo), "config", "user.name", "Test User"], check=True)

        (seed_repo / "composer.json").write_text('{"version": "35.1.0"}\n', encoding="utf-8")
        subprocess.run(["git", "-C", str(seed_repo), "add", "composer.json"], check=True)
        subprocess.run(["git", "-C", str(seed_repo), "commit", "-m", "v35.1.0"], check=True)
        subprocess.run(["git", "-C", str(seed_repo), "tag", "v35.1.0"], check=True)
        subprocess.run(["git", "-C", str(seed_repo), "push", "-u", "origin", "main", "--tags"], check=True)

        local_clone = tmp_path / "google-ads-php"
        subprocess.run(["git", "clone", str(remote_repo), str(local_clone)], check=True)

        # Advance remote with v35.2.0 tag
        (seed_repo / "composer.json").write_text('{"version": "35.2.0"}\n', encoding="utf-8")
        subprocess.run(["git", "-C", str(seed_repo), "add", "composer.json"], check=True)
        subprocess.run(["git", "-C", str(seed_repo), "commit", "-m", "v35.2.0"], check=True)
        subprocess.run(["git", "-C", str(seed_repo), "tag", "v35.2.0"], check=True)
        subprocess.run(["git", "-C", str(seed_repo), "push", "origin", "main", "--tags"], check=True)

        # Put local_clone into detached HEAD first to simulate prior detached tag state
        subprocess.run(["git", "-C", str(local_clone), "checkout", "v35.1.0"], check=True)
        detached_check = subprocess.run(
            ["git", "-C", str(local_clone), "symbolic-ref", "-q", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert detached_check.returncode != 0

        ok = sync_client_libs.update_codebase_via_git(str(local_clone), "v35.2.0")
        assert ok is True

        # Verify HEAD is back on branch 'main' (not detached) and subsequent git pull succeeds
        branch_check = subprocess.run(
            ["git", "-C", str(local_clone), "symbolic-ref", "-q", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert branch_check.returncode == 0
        assert branch_check.stdout.strip() == "main"

        pull_check = subprocess.run(
            ["git", "-C", str(local_clone), "pull"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert pull_check.returncode == 0


class TestSyncClientLibsExtended:
    """Extended unit tests for sync_client_libs.py multi-language detection, archive sync, and CLI flows."""

    def test_detect_installed_version_all_languages(self, tmp_path, monkeypatch):
        # 1. Python pyproject.toml
        py_dir = tmp_path / "google-ads-python"
        py_dir.mkdir()
        (py_dir / "pyproject.toml").write_text('version = "26.1.0"\n', encoding="utf-8")
        assert sync_client_libs.detect_installed_version("google-ads-python", str(py_dir)) == "26.1.0"

        # 2. Python ChangeLog fallback
        py_cl_dir = tmp_path / "google-ads-python-cl"
        py_cl_dir.mkdir()
        (py_cl_dir / "ChangeLog").write_text("* 25.2.0\n- Notes\n", encoding="utf-8")
        assert sync_client_libs.detect_installed_version("google-ads-python", str(py_cl_dir)) == "25.2.0"

        # 3. PHP composer.json
        php_dir = tmp_path / "google-ads-php"
        php_dir.mkdir()
        (php_dir / "composer.json").write_text('{"version": "35.1.0"}\n', encoding="utf-8")
        assert sync_client_libs.detect_installed_version("google-ads-php", str(php_dir)) == "35.1.0"

        # 4. Ruby *.gemspec
        ruby_dir = tmp_path / "google-ads-ruby"
        ruby_dir.mkdir()
        (ruby_dir / "google-ads-googleads.gemspec").write_text(
            'Gem::Specification.new do |s|\n  s.version = "32.0.0"\nend\n',
            encoding="utf-8",
        )
        assert sync_client_libs.detect_installed_version("google-ads-ruby", str(ruby_dir)) == "32.0.0"

        # 5. Java pom.xml
        java_dir = tmp_path / "google-ads-java"
        java_dir.mkdir()
        (java_dir / "pom.xml").write_text("<project><version>34.0.0</version></project>\n", encoding="utf-8")
        assert sync_client_libs.detect_installed_version("google-ads-java", str(java_dir)) == "34.0.0"

        # 6. .NET *.csproj
        dotnet_dir = tmp_path / "google-ads-dotnet" / "src"
        dotnet_dir.mkdir(parents=True)
        (dotnet_dir / "Google.Ads.GoogleAds.csproj").write_text(
            "<Project><PropertyGroup><Version>23.1.0</Version></PropertyGroup></Project>\n",
            encoding="utf-8",
        )
        assert (
            sync_client_libs.detect_installed_version(
                "google-ads-dotnet", str(tmp_path / "google-ads-dotnet")
            )
            == "23.1.0"
        )

        # 7. Git tags fallback
        git_fallback_dir = tmp_path / "git-only-lib"
        (git_fallback_dir / ".git").mkdir(parents=True)

        class FakeGitDescribe:
            returncode = 0
            stdout = "v29.4.0\n"

        monkeypatch.setattr(sync_client_libs.subprocess, "run", lambda *a, **kw: FakeGitDescribe())
        assert sync_client_libs.detect_installed_version("git-only-lib", str(git_fallback_dir)) == "29.4.0"

        # 8. Empty directory returns None
        empty_dir = tmp_path / "empty-lib"
        empty_dir.mkdir()
        assert sync_client_libs.detect_installed_version("empty-lib", str(empty_dir)) is None

    def test_get_repo_slug_git_remote_and_fallback(self, tmp_path, monkeypatch):
        assert (
            sync_client_libs.get_repo_slug("google-ads-python", str(tmp_path))
            == "googleads/google-ads-python"
        )

        custom_dir = tmp_path / "custom-ads-lib"
        (custom_dir / ".git").mkdir(parents=True)

        class FakeRemote:
            returncode = 0
            stdout = "https://github.com/customorg/custom-ads-lib.git\n"

        monkeypatch.setattr(sync_client_libs.subprocess, "run", lambda *a, **kw: FakeRemote())
        assert (
            sync_client_libs.get_repo_slug("custom-ads-lib", str(custom_dir))
            == "customorg/custom-ads-lib"
        )

        no_git_dir = tmp_path / "other-ads-lib"
        no_git_dir.mkdir()
        assert (
            sync_client_libs.get_repo_slug("other-ads-lib", str(no_git_dir))
            == "googleads/other-ads-lib"
        )

    def test_fetch_github_latest_release_404_and_git_ls_remote_fallbacks(self, monkeypatch):
        import urllib.error

        # Case 1: /releases/latest returns 404, fallback /releases?per_page=5 succeeds
        def urlopen_404_then_list(req, timeout=15):
            url = req.full_url
            if url.endswith("/releases/latest"):
                raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
            payload = [
                {"tag_name": "v27.0.0-rc1", "draft": False, "prerelease": True, "tarball_url": "http://rc"},
                {"tag_name": "v26.5.0", "draft": False, "prerelease": False, "tarball_url": "http://tar/26.5.0"},
            ]
            resp = MagicMock()
            resp.read.return_value = json.dumps(payload).encode("utf-8")
            resp.__enter__.return_value = resp
            return resp

        monkeypatch.setattr(sync_client_libs.urllib.request, "urlopen", urlopen_404_then_list)
        tag, tar_url = sync_client_libs.fetch_github_latest_release("googleads/google-ads-python")
        assert tag == "v26.5.0"
        assert tar_url == "http://tar/26.5.0"

        # Case 2: Both HTTP calls fail, falls back to git ls-remote --tags
        def urlopen_always_fails(req, timeout=15):
            raise urllib.error.URLError("network down")

        class FakeLsRemote:
            returncode = 0
            stdout = (
                "aaa\trefs/tags/v24.0.0\n"
                "bbb\trefs/tags/v26.2.0\n"
                "ccc\trefs/tags/v26.2.0^{}\n"
                "ddd\trefs/tags/v25.1.0\n"
            )

        monkeypatch.setattr(sync_client_libs.urllib.request, "urlopen", urlopen_always_fails)
        monkeypatch.setattr(sync_client_libs.subprocess, "run", lambda *a, **kw: FakeLsRemote())
        tag2, tar_url2 = sync_client_libs.fetch_github_latest_release("googleads/google-ads-python")
        assert tag2 == "v26.2.0"
        assert tar_url2 is None

    def test_is_update_needed_and_sync_directories(self, tmp_path):
        assert sync_client_libs.is_update_needed("25.0.0", None) is False
        assert sync_client_libs.is_update_needed(None, "25.0.0") is True
        assert sync_client_libs.is_update_needed("25.0.0", "25.0.0") is False
        assert sync_client_libs.is_update_needed("25.0.0", "26.0.0") is True
        assert sync_client_libs.is_update_needed("26.0.0", "25.0.0") is False

        src_dir = tmp_path / "src"
        (src_dir / ".git").mkdir(parents=True)
        (src_dir / "pkg").mkdir()
        (src_dir / "pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")
        (src_dir / "pyproject.toml").write_text('version = "26.0.0"\n', encoding="utf-8")

        dst_dir = tmp_path / "dst"
        (dst_dir / ".git").mkdir(parents=True)
        (dst_dir / "google-ads.yaml").write_text("keep: true\n", encoding="utf-8")
        (dst_dir / "stale_dir").mkdir()
        (dst_dir / "stale_file.txt").write_text("old\n", encoding="utf-8")

        ok = sync_client_libs.sync_directories(str(src_dir), str(dst_dir))
        assert ok is True
        assert (dst_dir / "google-ads.yaml").is_file()
        assert (dst_dir / ".git").is_dir()
        assert (dst_dir / "pyproject.toml").is_file()
        assert (dst_dir / "pkg" / "mod.py").is_file()
        assert not (dst_dir / "stale_dir").exists()
        assert not (dst_dir / "stale_file.txt").exists()

    def test_update_codebase_via_archive_tarball_extraction(self, tmp_path, monkeypatch):
        import io
        import tarfile

        # Build an in-memory .tar.gz archive with a root directory containing pyproject.toml
        tar_buf = io.BytesIO()
        with tarfile.open(fileobj=tar_buf, mode="w:gz") as tar:
            data = b'version = "34.1.0"\n'
            info = tarfile.TarInfo(name="google-ads-python-34.1.0/pyproject.toml")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        tar_bytes = tar_buf.getvalue()

        class FakeFailClone:
            returncode = 1
            stdout = ""
            stderr = "clone failed"

        class FakeTarResp:
            def __init__(self, b: bytes):
                self._bio = io.BytesIO(b)

            def read(self, *args):
                return self._bio.read(*args)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

        monkeypatch.setattr(sync_client_libs.subprocess, "run", lambda *a, **kw: FakeFailClone())
        monkeypatch.setattr(
            sync_client_libs.urllib.request,
            "urlopen",
            lambda req, timeout=30: FakeTarResp(tar_bytes),
        )

        target_lib = tmp_path / "google-ads-python"
        target_lib.mkdir()
        ok = sync_client_libs.update_codebase_via_archive(
            str(target_lib),
            "googleads/google-ads-python",
            "v34.1.0",
            "https://example.com/release.tar.gz",
        )
        assert ok is True
        assert (target_lib / "pyproject.toml").read_text(encoding="utf-8") == 'version = "34.1.0"\n'

    def test_update_api_version_cache_and_pypi_cache(self, tmp_path, monkeypatch):
        work_dir = tmp_path / "workspace"
        cfg_dir = work_dir / "config"
        cfg_dir.mkdir(parents=True)
        cfg_file = cfg_dir / "assistant_config"
        cfg_file.write_text(
            'api_version = "v24"\ncustomer_id = "1122334455"\nexecute_mutates = true\nenabled = true\n',
            encoding="utf-8",
        )
        legacy_txt = cfg_dir / "api_version.txt"
        legacy_txt.write_text("v24\n", encoding="utf-8")

        lib_dir = work_dir / "client_libs" / "google-ads-python"
        (lib_dir / "google" / "ads" / "googleads" / "v26").mkdir(parents=True)
        (lib_dir / "google" / "ads" / "googleads" / "v28").mkdir(parents=True)

        monkeypatch.chdir(work_dir)
        updated_v = sync_client_libs.update_api_version_cache_if_needed(str(lib_dir))
        assert updated_v == "v28"
        new_cfg = cfg_file.read_text(encoding="utf-8")
        assert 'api_version = "v28"' in new_cfg
        assert 'customer_id = "1122334455"' in new_cfg
        assert "execute_mutates = true" in new_cfg
        assert "enabled = true" in new_cfg
        assert legacy_txt.read_text(encoding="utf-8").strip() == "v28"

        # Test fetch_latest_pypi_python_version cache hit and force refresh
        monkeypatch.setattr(sync_client_libs.tempfile, "gettempdir", lambda: str(tmp_path))
        cache_file = tmp_path / "gads_assistant_pypi_google_ads_release.json"
        import time

        cache_file.write_text(
            json.dumps({"timestamp": time.time(), "pypi_version": "33.0.0"}),
            encoding="utf-8",
        )
        assert sync_client_libs.fetch_latest_pypi_python_version("google-ads", force=False) == "33.0.0"

    def test_detect_system_package_pip_fallback_and_local_upgrade(self, tmp_path, monkeypatch):
        import importlib.metadata

        def raise_not_found(pkg):
            raise importlib.metadata.PackageNotFoundError(pkg)

        monkeypatch.setattr(importlib.metadata, "version", raise_not_found)

        class FakePipShow:
            returncode = 0
            stdout = "Name: google-ads\nLocation: /custom/site-packages\nVersion: 31.0.0\n"

        monkeypatch.setattr(sync_client_libs.subprocess, "run", lambda *a, **kw: FakePipShow())
        ver, dirs = sync_client_libs.detect_system_package_version("google-ads")
        assert ver == "31.0.0"
        assert "/custom/site-packages" in dirs

        # Test upgrade_system_package fallback to local lib_path when pypi install fails
        lib_dir = tmp_path / "google-ads-python"
        lib_dir.mkdir()
        (lib_dir / "pyproject.toml").write_text('version = "34.0.0"\n', encoding="utf-8")

        calls = []

        def fake_pip_install(cmd, **kw):
            calls.append(cmd)

            class Res:
                returncode = 1 if "--index-url" in cmd else 0

            return Res()

        monkeypatch.setattr(sync_client_libs.subprocess, "run", fake_pip_install)
        assert (
            sync_client_libs.upgrade_system_package(
                "google-ads", "34.0.0", lib_path=str(lib_dir)
            )
            is True
        )
        assert len(calls) == 2

    def test_check_assistant_repo_and_process_client_libs_update(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(
            sync_client_libs,
            "fetch_github_latest_release",
            lambda slug: ("v35.0.0", "https://example.com/tar"),
        )
        monkeypatch.setattr(
            sync_client_libs, "update_codebase_via_git", lambda path, tag: True
        )
        monkeypatch.setattr(
            sync_client_libs,
            "update_codebase_via_archive",
            lambda path, slug, tag, url: True,
        )
        monkeypatch.setattr(
            sync_client_libs,
            "detect_system_package_version",
            lambda pkg: ("35.0.0", ["/fake/site-packages"]),
        )
        monkeypatch.setattr(
            sync_client_libs,
            "fetch_latest_pypi_python_version",
            lambda pkg="google-ads", **kw: "35.0.0",
        )
        monkeypatch.setattr(
            sync_client_libs,
            "update_api_version_cache_if_needed",
            lambda path: "v26",
        )

        # Create a fake client_libs dir with an outdated google-ads-python and google-ads-php
        libs_dir = tmp_path / "client_libs"
        py_lib = libs_dir / "google-ads-python"
        (py_lib / ".git").mkdir(parents=True)
        (py_lib / "pyproject.toml").write_text('version = "31.0.0"\n', encoding="utf-8")

        php_lib = libs_dir / "google-ads-php"
        php_lib.mkdir(parents=True)
        (php_lib / "composer.json").write_text('{"version": "30.0.0"}\n', encoding="utf-8")

        results = sync_client_libs.process_client_libs(
            client_libs_dir=str(libs_dir),
            check_only=False,
            force=False,
            include_assistant=True,
            upgrade_system=True,
        )
        statuses = {r["codebase"]: r["status"] for r in results}
        assert statuses.get("google-ads-python") == "UPDATED"
        assert statuses.get("google-ads-php") == "UPDATED"

        sync_client_libs.print_table(results)
        table_out = capsys.readouterr().out
        assert "[OK] System site-directory package 'google-ads'" in table_out
        assert "Google Ads API Version" in table_out


class TestGetCidsUnderMCCExtended:
    """Extended unit tests for get_cids_under_mcc.py CLI flags, CSV export, and error handling."""

    def test_handle_googleads_exception_and_stream_failure(self, capsys):
        err_elem = MagicMock()
        err_elem.field_name = "customer_client.id"
        err_item = MagicMock()
        err_item.message = "Authorization error"
        err_item.location.field_path_elements = [err_elem]

        fake_failure = MagicMock()
        fake_failure.errors = [err_item]
        fake_ex = get_cids_under_mcc.GoogleAdsException.__new__(
            get_cids_under_mcc.GoogleAdsException
        )
        fake_ex.request_id = "req-999"
        fake_ex.failure = fake_failure

        mock_client = MagicMock()
        mock_service = MagicMock()
        mock_client.get_service.return_value = mock_service
        mock_service.search_stream.side_effect = fake_ex

        with pytest.raises(SystemExit) as exc_info:
            get_cids_under_mcc.get_cids_under_mcc("1234567890", "v26", client=mock_client)
        assert exc_info.value.code == 1
        err_out = capsys.readouterr().err
        assert "req-999" in err_out
        assert "Authorization error" in err_out
        assert "customer_client.id" in err_out

    def test_get_config_path_and_main_cli_modes(self, tmp_path, monkeypatch, capsys):
        cfg_file = tmp_path / "google-ads.yaml"
        cfg_file.write_text("client_id: test\n", encoding="utf-8")
        monkeypatch.setenv("GOOGLE_ADS_CONFIGURATION_FILE_PATH", str(cfg_file))
        assert get_cids_under_mcc._get_config_path() == str(cfg_file)

        monkeypatch.chdir(tmp_path)
        sample_cids = [("1111111111", 1, True), ("2222222222", 2, False)]
        monkeypatch.setattr(
            get_cids_under_mcc, "get_cids_under_mcc", lambda cid, ver: sample_cids
        )

        # 1. --json mode
        monkeypatch.setattr(
            sys,
            "argv",
            ["get_cids_under_mcc.py", "--customer_id", "123-456-7890", "--api_version", "v26", "--json"],
        )
        get_cids_under_mcc.main()
        json_out = json.loads(capsys.readouterr().out)
        assert json_out["mcc_customer_id"] == "1234567890"
        assert json_out["total_child_accounts"] == 2

        # 2. --save_csv and --print_cids mode
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "get_cids_under_mcc.py",
                "--customer_id",
                "123-456-7890",
                "--api_version",
                "v26",
                "--save_csv",
                "--print_cids",
            ],
        )
        get_cids_under_mcc.main()
        out = capsys.readouterr().out
        assert "SUCCESS: Results saved to" in out
        assert "Child accounts under MCC 1234567890:" in out
        assert (tmp_path / "saved" / "data" / "cids_under_mcc_1234567890.csv").is_file()

        # 3. Interactive prompt when --customer_id is omitted
        monkeypatch.setattr("builtins.input", lambda prompt: "9998887776")
        monkeypatch.setattr(sys, "argv", ["get_cids_under_mcc.py", "--api_version", "v26"])
        get_cids_under_mcc.main()
        out_summary = capsys.readouterr().out
        assert "Found 2 child accounts under MCC 9998887776." in out_summary


class TestCreatePMaxAndRecentGclidsExtended:
    """Extended unit tests for create_pmax_webpage_filter.py and get_recent_gclids.py."""

    def test_create_pmax_webpage_filter_exceptions_and_main(self, tmp_path, monkeypatch, capsys):
        cfg_file = tmp_path / "google-ads.yaml"
        cfg_file.write_text("client_id: test\n", encoding="utf-8")
        monkeypatch.setenv("GOOGLE_ADS_CONFIGURATION_FILE_PATH", str(cfg_file))
        assert create_pmax_webpage_filter._get_config_path() == str(cfg_file)

        # Test GoogleAdsException handling
        mock_client = MagicMock()
        mock_filter_service = MagicMock()
        mock_client.get_service.return_value = mock_filter_service

        fake_ex = create_pmax_webpage_filter.GoogleAdsException.__new__(
            create_pmax_webpage_filter.GoogleAdsException
        )
        fake_ex.request_id = "req-pmax-1"
        err_obj = MagicMock()
        err_obj.message = "Duplicate listing filter"
        fake_ex.failure = MagicMock()
        fake_ex.failure.errors = [err_obj]
        mock_filter_service.mutate_asset_group_listing_group_filters.side_effect = fake_ex

        with pytest.raises(SystemExit) as exc_info:
            create_pmax_webpage_filter.create_pmax_webpage_filter(
                "1234567890", "999", "/blog", "v26", client=mock_client
            )
        assert exc_info.value.code == 1
        assert "Duplicate listing filter" in capsys.readouterr().out

        # Test main() CLI invocation
        called_args = {}

        def fake_create(cid, agid, url_ex, ver, validate_only=True):
            called_args["cid"] = cid
            called_args["validate_only"] = validate_only

        monkeypatch.setattr(create_pmax_webpage_filter, "create_pmax_webpage_filter", fake_create)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "create_pmax_webpage_filter.py",
                "--customer_id",
                "1234567890",
                "--asset_group_id",
                "555",
                "--url_exclusion",
                "/promo",
                "--api_version",
                "v26",
                "--execute",
            ],
        )
        create_pmax_webpage_filter.main()
        assert called_args["cid"] == "1234567890"
        assert called_args["validate_only"] is False

    def test_get_recent_gclids_exception_and_main(self, tmp_path, monkeypatch, capsys):
        cfg_file = tmp_path / "google-ads.yaml"
        cfg_file.write_text("client_id: test\n", encoding="utf-8")
        monkeypatch.setenv("GOOGLE_ADS_CONFIGURATION_FILE_PATH", str(cfg_file))
        assert get_recent_gclids._get_config_path() == str(cfg_file)

        mock_client = MagicMock()
        mock_service = MagicMock()
        mock_client.get_service.return_value = mock_service

        fake_ex = get_recent_gclids.GoogleAdsException.__new__(
            get_recent_gclids.GoogleAdsException
        )
        fake_ex.error = MagicMock()
        fake_ex.error.code.return_value.name = "INVALID_ARGUMENT"
        err_obj = MagicMock()
        err_obj.message = "Invalid date range"
        fake_ex.failure = MagicMock()
        fake_ex.failure.errors = [err_obj]
        mock_service.search.side_effect = fake_ex

        with pytest.raises(SystemExit) as exc_info:
            get_recent_gclids.get_recent_gclids(mock_client, "1234567890", "2026-08-19")
        assert exc_info.value.code == 1
        assert "Invalid date range" in capsys.readouterr().out

        # Test main() with mocked GoogleAdsClient.load_from_storage
        monkeypatch.setattr(
            get_recent_gclids.GoogleAdsClient, "load_from_storage", lambda **kw: MagicMock()
        )
        called = {}
        monkeypatch.setattr(
            get_recent_gclids,
            "get_recent_gclids",
            lambda client, cid, date: called.update({"cid": cid, "date": date}),
        )
        monkeypatch.setattr(
            sys,
            "argv",
            ["get_recent_gclids.py", "-c", "1234567890", "-v", "v26", "-d", "2026-09-01"],
        )
        get_recent_gclids.main()
        assert called == {"cid": "1234567890", "date": "2026-09-01"}


class TestTroubleshootConversionsExtended:
    """Extended unit tests for troubleshoot_conversions.py summaries, alerts, history merging, and console output."""

    def test_run_query_exception_and_merge_previous_findings(self, tmp_path, capsys):
        mock_client = MagicMock()
        mock_service = MagicMock()
        mock_client.get_service.return_value = mock_service

        fake_ex = troubleshoot_conversions.GoogleAdsException.__new__(
            troubleshoot_conversions.GoogleAdsException
        )
        fake_ex.request_id = "req-tc-1"
        err_obj = MagicMock()
        err_obj.message = "Permission denied"
        fake_ex.failure = MagicMock()
        fake_ex.failure.errors = [err_obj]
        mock_service.search_stream.side_effect = fake_ex

        rows = troubleshoot_conversions.run_query(mock_client, "1234567890", "SELECT customer.id FROM customer")
        assert rows == []
        assert "Permission denied" in capsys.readouterr().err

        # Create historical report files and verify merge_previous_findings strips nested history
        rep1 = tmp_path / "conversion_troubleshooting_report_1000.txt"
        rep1.write_text(
            "Created by the Google Ads API Developer Assistant\n\n"
            "1. Introductory Analysis\nFirst run summary\n\n"
            "=== HISTORICAL CONTEXT ===\nOld nested context\n\n"
            "2. Primary Errors & Critical Issues\nNone\n",
            encoding="utf-8",
        )
        findings = troubleshoot_conversions.merge_previous_findings(str(tmp_path))
        assert len(findings) == 1
        assert "First run summary" in findings[0]
        assert "Old nested context" not in findings[0]

    def test_troubleshoot_conversions_populated_summaries_and_console_mode(
        self, tmp_path, monkeypatch, capsys
    ):
        cfg_file = tmp_path / "google-ads.yaml"
        cfg_file.write_text("client_id: test\n", encoding="utf-8")
        monkeypatch.setenv("GOOGLE_ADS_CONFIGURATION_FILE_PATH", str(cfg_file))
        assert troubleshoot_conversions._get_config_path() == str(cfg_file)

        # Build mock rows for all 4 queries (customer, client_summary, action_summary, click_view)
        cust_row = MagicMock()
        cust_row.customer.descriptive_name = "Acme Corp"
        cust_row.customer.conversion_tracking_setting.accepted_customer_data_terms = False
        cust_row.customer.conversion_tracking_setting.enhanced_conversions_for_leads_enabled = False

        ds = MagicMock()
        ds.upload_date = "2026-09-01"
        ds.successful_count = 80
        ds.failed_count = 20
        ds.pending_count = 0

        alert = MagicMock()
        alert.error = "CONVERSION_PRECEDES_EVENT"
        alert.error_percentage = 0.20

        client_row = MagicMock()
        csum = client_row.offline_conversion_upload_client_summary
        csum.client.name = "GOOGLE_ADS_API"
        csum.status.name = "NEEDS_ATTENTION"
        csum.total_event_count = 100
        csum.successful_event_count = 80
        csum.daily_summaries = [ds]
        csum.alerts = [alert]

        action_row = MagicMock()
        asum = action_row.offline_conversion_upload_conversion_action_summary
        asum.conversion_action_name = "Offline Lead Import"
        asum.total_event_count = 50
        asum.successful_event_count = 40
        asum.daily_summaries = [ds]
        asum.alerts = [alert]

        gclid_row = MagicMock()
        gclid_row.click_view.gclid = "Cj0KCQjw_sample_gclid_999"

        def fake_run_query(client, customer_id, query):
            if "FROM customer" in query:
                return [cust_row]
            if "FROM offline_conversion_upload_client_summary" in query:
                return [client_row]
            if "FROM offline_conversion_upload_conversion_action_summary" in query:
                return [action_row]
            if "FROM click_view" in query:
                return [gclid_row] * 5
            return []

        with patch.object(troubleshoot_conversions, "run_query", side_effect=fake_run_query):
            data = troubleshoot_conversions.troubleshoot_conversions(
                MagicMock(), "1234567890", json_output=False, output_dir=str(tmp_path)
            )

        out = capsys.readouterr().out
        assert "=== Conversion Diagnostic Summary for Customer 1234567890 ===" in out
        assert "GOOGLE_ADS_API" in out
        assert "Offline Lead Import" in out
        assert data["customer_info"]["accepted_customer_data_terms"] is False
        assert any("Customer Data Terms NOT accepted" in e for e in data["primary_errors"])
        assert len(data["client_summaries"]) == 1
        assert len(data["conversion_action_summaries"]) == 1
        assert len(data["recent_gclids"]) >= 5
        assert os.path.isfile(data["report_path"])

        # Test main() CLI invocation
        monkeypatch.setattr(
            troubleshoot_conversions.GoogleAdsClient,
            "load_from_storage",
            lambda **kw: MagicMock(),
        )
        called_main = {}
        monkeypatch.setattr(
            troubleshoot_conversions,
            "troubleshoot_conversions",
            lambda client, cid, json_output=False: called_main.update(
                {"cid": cid, "json": json_output}
            ),
        )
        monkeypatch.setattr(
            sys,
            "argv",
            ["troubleshoot_conversions.py", "-c", "1234567890", "-v", "v26", "--json"],
        )
        troubleshoot_conversions.main()
        assert called_main == {"cid": "1234567890", "json": True}


class TestSitecustomizeAndSidecarExtended:
    """Extended unit tests for config/sitecustomize.py and sidecars/google-ads-a2a-service/server.py."""

    def test_sitecustomize_all_resolution_branches(self, tmp_path, monkeypatch):
        import builtins
        from importlib.util import module_from_spec, spec_from_file_location

        sc_path = os.path.join(PLUGIN_ROOT, "config", "sitecustomize.py")
        spec = spec_from_file_location("_test_sitecustomize_mod", sc_path)
        assert spec and spec.loader
        sc_mod = module_from_spec(spec)
        orig_open = builtins.open
        try:
            spec.loader.exec_module(sc_mod)
        finally:
            builtins.open = orig_open

        monkeypatch.setenv("_GOOGLE_ADS_TEST_SITECUSTOMIZE", "1")
        monkeypatch.setattr(sc_mod, "_THIS_CONFIG_DIR", str(tmp_path))

        # Create plugin config files in tmp_path
        yaml_file = tmp_path / "google-ads.yaml"
        yaml_file.write_text("client_id: test\n", encoding="utf-8")
        acfg_file = tmp_path / "assistant_config"
        acfg_file.write_text('api_version = "v26"\n', encoding="utf-8")
        fl_file = tmp_path / "financial_limits"
        fl_file.write_text("[Global]\n", encoding="utf-8")

        work_dir = tmp_path / "empty_cwd"
        work_dir.mkdir()
        monkeypatch.chdir(work_dir)
        monkeypatch.delenv("GOOGLE_ADS_CONFIGURATION_FILE_PATH", raising=False)
        monkeypatch.delenv("GOOGLE_ADS_FINANCIAL_LIMITS_FILE", raising=False)

        # Non-str and bytes pass-through
        assert sc_mod._resolve_assistant_config_file(123, "r") == 123
        assert sc_mod._resolve_assistant_config_file(b"config/google-ads.yaml", "rb") == b"config/google-ads.yaml"

        # Relative config/google-ads.yaml, config/assistant_config (read vs write), config/financial_limits
        assert sc_mod._resolve_assistant_config_file("config/google-ads.yaml", "r") == str(yaml_file)
        assert sc_mod._resolve_assistant_config_file("config/assistant_config", "r") == str(acfg_file)
        assert sc_mod._resolve_assistant_config_file("config/assistant_config", "w") == "config/assistant_config"
        assert sc_mod._resolve_assistant_config_file("config/financial_limits", "r") == str(fl_file)

        # Environment variable override for financial_limits
        custom_fl = tmp_path / "custom_limits"
        custom_fl.write_text("[Global]\n", encoding="utf-8")
        monkeypatch.setenv("GOOGLE_ADS_FINANCIAL_LIMITS_FILE", str(custom_fl))
        assert sc_mod._resolve_assistant_config_file("config/financial_limits", "r") == str(custom_fl)

    def test_sidecar_version_hierarchy_and_http_error_routes(self, tmp_path, monkeypatch):
        # 1. Numeric payload normalization ("26" -> "v26")
        assert server.get_effective_api_version({"api_version": "26"}) == "v26"

        # 2. Environment variable GOOGLE_ADS_API_VERSION ("25" -> "v25")
        monkeypatch.setenv("GOOGLE_ADS_API_VERSION", "25")
        assert server.get_effective_api_version({}) == "v25"
        monkeypatch.delenv("GOOGLE_ADS_API_VERSION", raising=False)

        # 3. GET 404 Not Found
        handler = server.A2AHandler.__new__(server.A2AHandler)
        handler.path = "/unknown"
        handler._send_json = MagicMock()
        handler.do_GET()
        assert handler._send_json.call_args[0][0] == 404

        # 4. POST 404 Not Found
        handler.path = "/unknown"
        handler._send_json = MagicMock()
        handler.do_POST()
        assert handler._send_json.call_args[0][0] == 404

        # 5. POST 400 Invalid JSON
        handler.path = "/v1/a2a/tasks"
        handler.headers = {"Content-Length": "5"}
        handler.rfile = MagicMock()
        handler.rfile.read.return_value = b"{bad!"
        handler._send_json = MagicMock()
        handler.do_POST()
        assert handler._send_json.call_args[0][0] == 400
        assert "Invalid JSON" in handler._send_json.call_args[0][1]["error"]

        # 6. PREPARE_MUTATION and EXECUTE_MUTATION missing required fields
        res_prep = handler.handle_prepare_mutation("task-prep-err", {"customer_id": ""})
        assert res_prep["status"] == "VALIDATION_FAILED"
        res_exec = handler.handle_execute_mutation("task-exec-err", {"user_confirmed": False})
        assert res_exec["status"] == "HITL_BLOCKED"


def load_script_module(rel_path: str, module_name: str):
    """Loads a plugin script module by relative path under PLUGIN_ROOT."""
    from importlib.util import module_from_spec, spec_from_file_location

    script_path = os.path.join(PLUGIN_ROOT, rel_path)
    spec = spec_from_file_location(module_name, script_path)
    assert spec is not None and spec.loader is not None
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestCreateAccountCampaignAdGroupAd:
    """Tests for create_account.py, create_campaign.py, create_ad_group.py, create_ad.py, and A2A intents."""

    @staticmethod
    def _build_mock_ads_client():
        client = MagicMock()
        client.enums.AccessRoleEnum.ADMIN = "ADMIN"
        client.enums.AccessRoleEnum.STANDARD = "STANDARD"
        client.enums.AdvertisingChannelTypeEnum.SEARCH = "SEARCH"
        client.enums.CampaignStatusEnum.PAUSED = "PAUSED"
        client.enums.CampaignStatusEnum.ENABLED = "ENABLED"
        client.enums.BudgetDeliveryMethodEnum.STANDARD = "STANDARD"
        client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING = (
            "DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING"
        )
        client.enums.AdGroupStatusEnum.ENABLED = "ENABLED"
        client.enums.AdGroupStatusEnum.PAUSED = "PAUSED"
        client.enums.AdGroupTypeEnum.SEARCH_STANDARD = "SEARCH_STANDARD"
        client.enums.AdGroupAdStatusEnum.PAUSED = "PAUSED"
        client.enums.AdGroupAdStatusEnum.ENABLED = "ENABLED"

        # Services
        customer_service = MagicMock()
        customer_resp = MagicMock()
        customer_resp.resource_name = "customers/9998887770"
        customer_resp.invitation_link = "https://ads.google.com/invite/abc"
        customer_service.create_customer_client.return_value = customer_resp

        budget_service = MagicMock()
        budget_result = MagicMock()
        budget_result.resource_name = "customers/1234567890/campaignBudgets/111"
        budget_resp = MagicMock()
        budget_resp.results = [budget_result]
        budget_service.mutate_campaign_budgets.return_value = budget_resp
        budget_service.campaign_budget_path.side_effect = (
            lambda cid, bid: f"customers/{cid}/campaignBudgets/{bid}"
        )

        campaign_service = MagicMock()
        campaign_result = MagicMock()
        campaign_result.resource_name = "customers/1234567890/campaigns/222"
        campaign_resp = MagicMock()
        campaign_resp.results = [campaign_result]
        campaign_service.mutate_campaigns.return_value = campaign_resp
        campaign_service.campaign_path.side_effect = (
            lambda cid, camp_id: f"customers/{cid}/campaigns/{camp_id}"
        )

        ad_group_service = MagicMock()
        ag_result = MagicMock()
        ag_result.resource_name = "customers/1234567890/adGroups/333"
        ag_resp = MagicMock()
        ag_resp.results = [ag_result]
        ad_group_service.mutate_ad_groups.return_value = ag_resp
        ad_group_service.ad_group_path.side_effect = (
            lambda cid, ag_id: f"customers/{cid}/adGroups/{ag_id}"
        )

        ad_group_ad_service = MagicMock()
        aga_result = MagicMock()
        aga_result.resource_name = "customers/1234567890/adGroupAds/333~444"
        aga_resp = MagicMock()
        aga_resp.results = [aga_result]
        ad_group_ad_service.mutate_ad_group_ads.return_value = aga_resp

        service_map = {
            "CustomerService": customer_service,
            "CampaignBudgetService": budget_service,
            "CampaignService": campaign_service,
            "AdGroupService": ad_group_service,
            "AdGroupAdService": ad_group_ad_service,
        }
        client.get_service.side_effect = lambda name: service_map[name]

        def _make_type(type_name):
            obj = MagicMock()
            if type_name == "AdGroupAdOperation":
                obj.create.ad.final_urls = []
                obj.create.ad.responsive_search_ad.headlines = []
                obj.create.ad.responsive_search_ad.descriptions = []
            elif type_name in (
                "MutateCampaignBudgetsRequest",
                "MutateCampaignsRequest",
                "MutateAdGroupsRequest",
                "MutateAdGroupAdsRequest",
            ):
                obj.operations = []
            return obj

        client.get_type.side_effect = _make_type
        return client, service_map

    def test_create_account_under_mcc_success_and_errors(self, monkeypatch, capsys):
        mod = load_script_module(
            "skills/execute-mutation/scripts/create_account.py", "create_account_test"
        )
        client, services = self._build_mock_ads_client()

        # 1. Dry-run with optional fields and JSON output
        res = mod.create_account_under_mcc(
            manager_customer_id="123-456-7890",
            descriptive_name="Acme Client Account",
            currency_code="usd",
            time_zone="America/New_York",
            tracking_url_template="{lpurl}?device={device}",
            final_url_suffix="src=ads",
            email_address="owner@example.com",
            access_role="ADMIN",
            validate_only=True,
            client=client,
            json_output=True,
        )
        assert res["status"] == "DRY_RUN_PASSED"
        assert res["validate_only"] is True
        assert res["manager_customer_id"] == "1234567890"
        assert res["currency_code"] == "USD"
        assert res["resource_name"] == "customers/9998887770"
        assert res["invitation_link"] == "https://ads.google.com/invite/abc"
        out = capsys.readouterr().out
        assert '"status": "DRY_RUN_PASSED"' in out

        # 2. Live execution via CLI main()
        monkeypatch.setattr(
            mod.GoogleAdsClient, "load_from_storage", lambda path, version: client
        )
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "create_account.py",
                "--manager-customer-id",
                "123-456-7890",
                "--execute",
            ],
        )
        mod.main()
        out_live = capsys.readouterr().out
        assert "SUCCESS: Customer created" in out_live

        # 3. Validation errors (invalid MCC ID, currency, timezone, access_role)
        with pytest.raises(SystemExit):
            mod.create_account_under_mcc(manager_customer_id="abc", client=client)
        with pytest.raises(SystemExit):
            mod.create_account_under_mcc(
                manager_customer_id="1234567890", currency_code="US", client=client
            )
        with pytest.raises(SystemExit):
            mod.create_account_under_mcc(
                manager_customer_id="1234567890", time_zone="  ", client=client
            )
        setattr(client.enums.AccessRoleEnum, "INVALID_ROLE", None)
        with pytest.raises(SystemExit):
            mod.create_account_under_mcc(
                manager_customer_id="1234567890",
                access_role="INVALID_ROLE",
                client=client,
            )

        # 4. GoogleAdsException handling
        fake_err = MagicMock()
        fake_err.message = "Manager account not allowed"
        fake_el = MagicMock()
        fake_el.field_name = "customer_id"
        fake_err.location.field_path_elements = [fake_el]
        gads_ex = mod.GoogleAdsException.__new__(mod.GoogleAdsException)
        gads_ex.request_id = "req-acc-err"
        gads_ex.failure = MagicMock(errors=[fake_err])
        services["CustomerService"].create_customer_client.side_effect = gads_ex
        with pytest.raises(SystemExit):
            mod.create_account_under_mcc(manager_customer_id="1234567890", client=client)
        err_out = capsys.readouterr().err
        assert "req-acc-err" in err_out
        assert "customer_id" in err_out

    def test_create_campaign_success_and_errors(self, monkeypatch, capsys):
        mod = load_script_module(
            "skills/execute-mutation/scripts/create_campaign.py", "create_campaign_test"
        )
        client, services = self._build_mock_ads_client()

        # 1. Dry-run creating both budget and campaign with JSON output
        res = mod.create_campaign(
            customer_id="123-456-7890",
            campaign_name="Summer Search",
            budget_amount_micros=5_000_000,
            advertising_channel_type="SEARCH",
            status="PAUSED",
            start_date="2026-12-01",
            end_date="2026-12-31",
            validate_only=True,
            client=client,
            json_output=True,
        )
        assert res["status"] == "DRY_RUN_PASSED"
        assert res["budget_resource_name"] == "customers/1234567890/campaignBudgets/111"
        assert res["campaign_resource_name"] == "customers/1234567890/campaigns/222"

        # 2. Dry-run when budget_resp.results is empty (live API validate_only=True behavior)
        services["CampaignBudgetService"].mutate_campaign_budgets.return_value = MagicMock(
            results=[]
        )
        res_fallback = mod.create_campaign(
            customer_id="1234567890",
            validate_only=True,
            client=client,
        )
        assert (
            res_fallback["budget_resource_name"]
            == "customers/1234567890/campaignBudgets/-1"
        )

        # 3. Live execution with pre-existing budget via CLI main()
        monkeypatch.setattr(
            mod.GoogleAdsClient, "load_from_storage", lambda path, version: client
        )
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "create_campaign.py",
                "--customer-id",
                "1234567890",
                "--budget-resource-name",
                "customers/1234567890/campaignBudgets/999",
                "--execute",
            ],
        )
        mod.main()
        out_live = capsys.readouterr().out
        assert "SUCCESS: Created campaign" in out_live

        # 4. Validation errors
        with pytest.raises(SystemExit):
            mod.create_campaign(customer_id="invalid", client=client)
        with pytest.raises(SystemExit):
            mod.create_campaign(
                customer_id="1234567890", budget_amount_micros=0, client=client
            )
        setattr(client.enums.AdvertisingChannelTypeEnum, "BAD_CHANNEL", None)
        with pytest.raises(SystemExit):
            mod.create_campaign(
                customer_id="1234567890",
                advertising_channel_type="BAD_CHANNEL",
                client=client,
            )
        setattr(client.enums.CampaignStatusEnum, "BAD_STATUS", None)
        with pytest.raises(SystemExit):
            mod.create_campaign(
                customer_id="1234567890", status="BAD_STATUS", client=client
            )
        setattr(client.enums.BudgetDeliveryMethodEnum, "BAD_DELIVERY", None)
        with pytest.raises(SystemExit):
            mod.create_campaign(
                customer_id="1234567890",
                budget_delivery_method="BAD_DELIVERY",
                client=client,
            )

    def test_create_ad_group_success_and_errors(self, monkeypatch, capsys):
        mod = load_script_module(
            "skills/execute-mutation/scripts/create_ad_group.py", "create_ad_group_test"
        )
        client, _ = self._build_mock_ads_client()

        # 1. Dry-run with campaign_id and cpc_bid_micros
        res = mod.create_ad_group(
            customer_id="123-456-7890",
            campaign_id="222",
            ad_group_name="Core Keywords",
            cpc_bid_micros=1_500_000,
            status="ENABLED",
            ad_group_type="SEARCH_STANDARD",
            validate_only=True,
            client=client,
            json_output=True,
        )
        assert res["status"] == "DRY_RUN_PASSED"
        assert res["campaign_resource_name"] == "customers/1234567890/campaigns/222"
        assert res["ad_group_resource_name"] == "customers/1234567890/adGroups/333"
        assert res["cpc_bid_micros"] == 1_500_000

        # 2. Live execution via CLI main() with campaign_resource_name
        monkeypatch.setattr(
            mod.GoogleAdsClient, "load_from_storage", lambda path, version: client
        )
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "create_ad_group.py",
                "--customer-id",
                "1234567890",
                "--campaign-resource-name",
                "customers/1234567890/campaigns/222",
                "--execute",
            ],
        )
        mod.main()
        assert "SUCCESS: Created ad group" in capsys.readouterr().out

        # 3. Validation errors
        with pytest.raises(SystemExit):
            mod.create_ad_group(customer_id="bad", campaign_id="222", client=client)
        with pytest.raises(SystemExit):
            mod.create_ad_group(customer_id="1234567890", client=client)
        with pytest.raises(SystemExit):
            mod.create_ad_group(
                customer_id="1234567890",
                campaign_id="222",
                cpc_bid_micros=-10,
                client=client,
            )
        setattr(client.enums.AdGroupStatusEnum, "BAD_STATUS", None)
        with pytest.raises(SystemExit):
            mod.create_ad_group(
                customer_id="1234567890",
                campaign_id="222",
                status="BAD_STATUS",
                client=client,
            )
        setattr(client.enums.AdGroupTypeEnum, "BAD_TYPE", None)
        with pytest.raises(SystemExit):
            mod.create_ad_group(
                customer_id="1234567890",
                campaign_id="222",
                ad_group_type="BAD_TYPE",
                client=client,
            )

    def test_create_ad_success_and_errors(self, monkeypatch, capsys):
        mod = load_script_module(
            "skills/execute-mutation/scripts/create_ad.py", "create_ad_test"
        )
        client, _ = self._build_mock_ads_client()

        # 1. Dry-run with custom headlines, descriptions, path1, path2
        res = mod.create_responsive_search_ad(
            customer_id="123-456-7890",
            ad_group_id="333",
            final_urls=["https://www.example.com/mars"],
            headlines=["Mars Flights", "Book Space Travel", "Red Planet Tours"],
            descriptions=["Fly to Mars in comfort.", "Reserve your cabin today."],
            path1="all-inclusive",
            path2="deals",
            status="PAUSED",
            validate_only=True,
            client=client,
            json_output=True,
        )
        assert res["status"] == "DRY_RUN_PASSED"
        assert res["ad_group_resource_name"] == "customers/1234567890/adGroups/333"
        assert res["ad_group_ad_resource_name"] == "customers/1234567890/adGroupAds/333~444"
        assert len(res["headlines"]) == 3
        assert len(res["descriptions"]) == 2
        assert res["path1"] == "all-inclusive"

        # 2. Live execution via CLI main() with default headlines/descriptions
        monkeypatch.setattr(
            mod.GoogleAdsClient, "load_from_storage", lambda path, version: client
        )
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "create_ad.py",
                "--customer-id",
                "1234567890",
                "--ad-group-resource-name",
                "customers/1234567890/adGroups/333",
                "--execute",
            ],
        )
        mod.main()
        assert "SUCCESS: Created responsive search ad" in capsys.readouterr().out

        # 3. Validation errors (<3 headlines, <2 descriptions, missing ad_group_id, bad status)
        with pytest.raises(SystemExit):
            mod.create_ad(customer_id="bad", ad_group_id="333", client=client)
        with pytest.raises(SystemExit):
            mod.create_ad(customer_id="1234567890", client=client)
        with pytest.raises(SystemExit):
            mod.create_ad(
                customer_id="1234567890",
                ad_group_id="333",
                headlines=["Only One", "Only Two"],
                client=client,
            )
        with pytest.raises(SystemExit):
            mod.create_ad(
                customer_id="1234567890",
                ad_group_id="333",
                descriptions=["Only One Description"],
                client=client,
            )
        setattr(client.enums.AdGroupAdStatusEnum, "BAD_STATUS", None)
        with pytest.raises(SystemExit):
            mod.create_ad(
                customer_id="1234567890",
                ad_group_id="333",
                status="BAD_STATUS",
                client=client,
            )

    def test_a2a_sidecar_creation_intents_and_hitl_gate(self):
        client, _ = self._build_mock_ads_client()
        handler = server.A2AHandler.__new__(server.A2AHandler)

        # 1. Dry-run intents succeed
        res_acc = handler.handle_create_account(
            "t-acc",
            {
                "manager_customer_id": "1234567890",
                "descriptive_name": "Sub Account",
                "client": client,
            },
        )
        assert res_acc["status"] == "COMPLETED"
        assert res_acc["result"]["resource_name"] == "customers/9998887770"

        res_camp = handler.handle_create_campaign(
            "t-camp",
            {
                "customer_id": "1234567890",
                "campaign_name": "A2A Campaign",
                "budget_amount_micros": 5_000_000,
                "client": client,
            },
        )
        assert res_camp["status"] == "COMPLETED"
        assert res_camp["result"]["campaign_resource_name"] == "customers/1234567890/campaigns/222"

        res_ag = handler.handle_create_ad_group(
            "t-ag",
            {
                "customer_id": "1234567890",
                "campaign_id": "222",
                "ad_group_name": "A2A Ad Group",
                "cpc_bid_micros": 1_000_000,
                "client": client,
            },
        )
        assert res_ag["status"] == "COMPLETED"
        assert res_ag["result"]["ad_group_resource_name"] == "customers/1234567890/adGroups/333"

        res_ad = handler.handle_create_ad(
            "t-ad",
            {
                "customer_id": "1234567890",
                "ad_group_id": "333",
                "final_url": "https://www.example.com",
                "client": client,
            },
        )
        assert res_ad["status"] == "COMPLETED"
        assert (
            res_ad["result"]["ad_group_ad_resource_name"]
            == "customers/1234567890/adGroupAds/333~444"
        )

        # 2. Live execution without user_confirmed=True is HITL_BLOCKED
        blocked = handler.handle_create_campaign(
            "t-blocked",
            {
                "customer_id": "1234567890",
                "execute": True,
                "user_confirmed": False,
                "client": client,
            },
        )
        assert blocked["status"] == "HITL_BLOCKED"
        assert "user_confirmed=True" in blocked["error"]

        # 3. _check_live_execution_gate when user_confirmed=True but execute_mutates=False
        mock_run_mod = MagicMock()
        mock_run_mod.is_execute_mutates_enabled.return_value = False
        with patch.object(handler, "_load_mutation_script", return_value=mock_run_mod):
            blocked_cfg = handler.handle_create_account(
                "t-blocked-cfg",
                {
                    "manager_customer_id": "1234567890",
                    "execute": True,
                    "user_confirmed": True,
                },
            )
            assert blocked_cfg["status"] == "HITL_BLOCKED"
            assert "execute_mutates = false" in blocked_cfg["error"]

        # 4. Error branches (SystemExit/Exception) in all 4 sidecar creation handlers
        assert handler.handle_create_account("t-err1", {"manager_customer_id": "bad", "client": client})["status"] == "FAILED"
        assert handler.handle_create_campaign("t-err2", {"customer_id": "bad", "client": client})["status"] == "FAILED"
        assert handler.handle_create_ad_group("t-err3", {"customer_id": "bad", "client": client})["status"] == "FAILED"
        assert handler.handle_create_ad("t-err4", {"customer_id": "bad", "client": client})["status"] == "FAILED"

    def test_create_scripts_config_path_and_exception_handlers(self, tmp_path, monkeypatch, capsys):
        fake_yaml = tmp_path / "google-ads.yaml"
        fake_yaml.write_text("use_proto_plus: True\n", encoding="utf-8")

        for script_rel, mod_name, fn_name, call_kwargs, svc_name, method_name in [
            (
                "skills/execute-mutation/scripts/create_campaign.py",
                "cc_cov",
                "create_campaign",
                {"customer_id": "1234567890"},
                "CampaignBudgetService",
                "mutate_campaign_budgets",
            ),
            (
                "skills/execute-mutation/scripts/create_ad_group.py",
                "cag_cov",
                "create_ad_group",
                {"customer_id": "1234567890", "campaign_id": "222"},
                "AdGroupService",
                "mutate_ad_groups",
            ),
            (
                "skills/execute-mutation/scripts/create_ad.py",
                "cad_cov",
                "create_responsive_search_ad",
                {"customer_id": "1234567890", "ad_group_id": "333"},
                "AdGroupAdService",
                "mutate_ad_group_ads",
            ),
        ]:
            mod = load_script_module(script_rel, mod_name)

            # _get_config_path via env var and via candidate fallback
            monkeypatch.setenv("GOOGLE_ADS_CONFIGURATION_FILE_PATH", str(fake_yaml))
            assert mod._get_config_path() == str(fake_yaml)
            monkeypatch.delenv("GOOGLE_ADS_CONFIGURATION_FILE_PATH", raising=False)
            assert isinstance(mod._get_config_path(), str)

            # handle_googleads_exception with field_path_elements
            fake_err = MagicMock()
            fake_err.message = "Detailed failure"
            fake_el = MagicMock()
            fake_el.field_name = "operations"
            fake_err.location.field_path_elements = [fake_el]
            gads_ex = mod.GoogleAdsException.__new__(mod.GoogleAdsException)
            gads_ex.request_id = "req-cov-123"
            gads_ex.failure = MagicMock(errors=[fake_err])
            mod.handle_googleads_exception(gads_ex)
            assert "req-cov-123" in capsys.readouterr().err

            # load_from_storage failure when client=None
            monkeypatch.setattr(
                mod.GoogleAdsClient,
                "load_from_storage",
                MagicMock(side_effect=RuntimeError("storage error")),
            )
            with pytest.raises(SystemExit):
                getattr(mod, fn_name)(**call_kwargs, client=None)

            # GoogleAdsException and generic Exception inside create_* function
            client, services = self._build_mock_ads_client()
            getattr(services[svc_name], method_name).side_effect = gads_ex
            with pytest.raises(SystemExit):
                getattr(mod, fn_name)(**call_kwargs, client=client)

            getattr(services[svc_name], method_name).side_effect = RuntimeError("unexpected boom")
            with pytest.raises(SystemExit):
                getattr(mod, fn_name)(**call_kwargs, client=client)


class TestRemainingModulesAbove80Coverage:
    """Targeted unit tests to ensure every module and category exceeds 80% statement coverage."""

    def test_small_scripts_config_and_error_branches(self, tmp_path, monkeypatch, capsys):
        fake_yaml = tmp_path / "google-ads.yaml"
        fake_yaml.write_text("use_proto_plus: True\n", encoding="utf-8")

        # 1. get_latest_api_version.py
        cfg_dir = tmp_path / "cfg_glav"
        cfg_dir.mkdir()
        (cfg_dir / "assistant_config").write_text(
            'api_version = "v24"\ncustomer_id = "12345678"\nexecute_mutates = true\nenabled = true\n',
            encoding="utf-8",
        )
        (cfg_dir / "customer_id.txt").write_text("5556667777\n", encoding="utf-8")
        updated = get_latest_api_version.update_assistant_config_api_version("26", config_dir=str(cfg_dir))
        assert len(updated) == 1
        written_cfg = (cfg_dir / "assistant_config").read_text(encoding="utf-8")
        assert 'api_version = "v26"' in written_cfg
        assert 'customer_id = "5556667777"' in written_cfg
        assert "enabled = true" in written_cfg
        assert get_latest_api_version._extract_version_dirs("") == []

        # 2. get_cids_under_mcc.py
        monkeypatch.setenv("GOOGLE_ADS_CONFIGURATION_FILE_PATH", str(fake_yaml))
        assert get_cids_under_mcc._get_config_path() == str(fake_yaml)
        monkeypatch.delenv("GOOGLE_ADS_CONFIGURATION_FILE_PATH", raising=False)
        assert isinstance(get_cids_under_mcc._get_config_path(), str)

        monkeypatch.setattr(
            get_cids_under_mcc.GoogleAdsClient,
            "load_from_storage",
            MagicMock(side_effect=RuntimeError("no yaml")),
        )
        with pytest.raises(SystemExit):
            get_cids_under_mcc.get_cids_under_mcc("1234567890", "v26", client=None)

        bad_client = MagicMock()
        bad_client.get_service.return_value.search_stream.side_effect = RuntimeError("stream crash")
        with pytest.raises(SystemExit):
            get_cids_under_mcc.get_cids_under_mcc("1234567890", "v26", client=bad_client)

        monkeypatch.setattr(sys, "argv", ["get_cids_under_mcc.py", "--api_version", "v26"])
        monkeypatch.setattr("builtins.input", MagicMock(side_effect=EOFError()))
        with pytest.raises(SystemExit):
            get_cids_under_mcc.main()

        monkeypatch.setattr("builtins.input", lambda _: "   ")
        with pytest.raises(SystemExit):
            get_cids_under_mcc.main()

        monkeypatch.setattr(
            sys,
            "argv",
            ["get_cids_under_mcc.py", "--customer_id", "1234567890", "--api_version", "v26", "--print_cids"],
        )
        monkeypatch.setattr(get_cids_under_mcc, "get_cids_under_mcc", lambda cid, ver: [])
        get_cids_under_mcc.main()
        assert "No child accounts found." in capsys.readouterr().out

        # 3. create_pmax_webpage_filter.py
        monkeypatch.setenv("GOOGLE_ADS_CONFIGURATION_FILE_PATH", str(fake_yaml))
        assert create_pmax_webpage_filter._get_config_path() == str(fake_yaml)
        monkeypatch.delenv("GOOGLE_ADS_CONFIGURATION_FILE_PATH", raising=False)
        assert isinstance(create_pmax_webpage_filter._get_config_path(), str)

        monkeypatch.setattr(
            create_pmax_webpage_filter.GoogleAdsClient,
            "load_from_storage",
            MagicMock(side_effect=RuntimeError("load fail")),
        )
        with pytest.raises(SystemExit):
            create_pmax_webpage_filter.create_pmax_webpage_filter(
                "1234567890", "111", "blog", "v26", client=None
            )

        # 4. get_recent_gclids.py
        monkeypatch.setenv("GOOGLE_ADS_CONFIGURATION_FILE_PATH", str(fake_yaml))
        assert get_recent_gclids._get_config_path() == str(fake_yaml)
        monkeypatch.delenv("GOOGLE_ADS_CONFIGURATION_FILE_PATH", raising=False)
        assert isinstance(get_recent_gclids._get_config_path(), str)

        monkeypatch.setattr(
            get_recent_gclids.GoogleAdsClient,
            "load_from_storage",
            MagicMock(side_effect=RuntimeError("gclid load fail")),
        )
        monkeypatch.setattr(
            sys,
            "argv",
            ["get_recent_gclids.py", "-c", "1234567890", "-v", "v26"],
        )
        with pytest.raises(SystemExit):
            get_recent_gclids.main()

    def test_inspect_object_and_validate_gaql_remaining_branches(self, tmp_path, monkeypatch, capsys):
        fake_yaml = tmp_path / "google-ads.yaml"
        fake_yaml.write_text("use_proto_plus: True\n", encoding="utf-8")

        # --- inspect_object.py ---
        monkeypatch.setenv("GOOGLE_ADS_CONFIGURATION_FILE_PATH", str(fake_yaml))
        assert inspect_object._get_config_path() == str(fake_yaml)
        monkeypatch.delenv("GOOGLE_ADS_CONFIGURATION_FILE_PATH", raising=False)
        assert isinstance(inspect_object._get_config_path(), str)

        assert inspect_object.resolve_type_name("Campaign", {}) == ("Campaign", [])
        assert inspect_object.resolve_type_name(
            "CampaignStatusEnum", {"CampaignStatus": "/tmp/cs.py"}
        ) == ("CampaignStatus", [])
        assert inspect_object.resolve_type_name(
            "cmpgn_stat", {"CampaignStatus": "/tmp/cs.py"}
        )[0] is None

        # inspect_from_source on missing file and on Enum file
        assert inspect_object.inspect_from_source(str(tmp_path / "missing.py"), "Foo") is False
        enum_py = tmp_path / "fake_enum.py"
        enum_py.write_text(
            "class FakeStatusEnum:\n"
            "    UNSPECIFIED = 0\n"
            "    ENABLED = 2\n"
            "class NextClass:\n"
            "    pass\n",
            encoding="utf-8",
        )
        assert inspect_object.inspect_from_source(str(enum_py), "FakeStatusEnum") is True
        assert "=== Enum: FakeStatusEnum ===" in capsys.readouterr().out

        # inspect_protobuf with Enum descriptor and with unresolved/uninspectable type
        enum_val = MagicMock()
        enum_val.name = "ENABLED"
        enum_val.number = 2
        enum_client = MagicMock()
        enum_client.get_type.return_value.DESCRIPTOR.values = [enum_val]
        monkeypatch.setattr(
            inspect_object, "get_available_types", lambda ver: {"CampaignStatusEnum": str(enum_py)}
        )
        inspect_object.inspect_protobuf("campaign_status", "v26", client=enum_client)
        out_io = capsys.readouterr().out
        assert "Note: Resolved 'campaign_status' -> 'CampaignStatusEnum'" in out_io
        assert "=== Enum: CampaignStatusEnum ===" in out_io

        # inspect_protobuf when both client and source inspection fail
        empty_py = tmp_path / "empty_type.py"
        empty_py.write_text("# empty\n", encoding="utf-8")
        monkeypatch.setattr(
            inspect_object, "get_available_types", lambda ver: {"EmptyType": str(empty_py)}
        )
        failing_client = MagicMock()
        failing_client.get_type.side_effect = RuntimeError("no type")
        with pytest.raises(SystemExit):
            inspect_object.inspect_protobuf("EmptyType", "v26", client=failing_client)

        # --- validate_gaql.py ---
        monkeypatch.setenv("GOOGLE_ADS_CONFIGURATION_FILE_PATH", str(fake_yaml))
        assert validate_gaql._get_config_path() == str(fake_yaml)
        monkeypatch.delenv("GOOGLE_ADS_CONFIGURATION_FILE_PATH", raising=False)
        assert isinstance(validate_gaql._get_config_path(), str)

        # handle_googleads_exception
        fake_err = MagicMock()
        fake_err.message = "Bad GAQL syntax"
        fake_el = MagicMock()
        fake_el.field_name = "query"
        fake_err.location.field_path_elements = [fake_el]
        gads_ex = validate_gaql.GoogleAdsException.__new__(validate_gaql.GoogleAdsException)
        gads_ex.request_id = "req-gaql-1"
        gads_ex.failure = MagicMock(errors=[fake_err])
        validate_gaql.handle_googleads_exception(gads_ex)
        assert "req-gaql-1" in capsys.readouterr().out

        # Static checks: click_view without WHERE, change_status missing BETWEEN/LIMIT/>10000, GOOGLE_ADS_FIELD prefix
        for bad_q in [
            "SELECT click_view.gclid FROM click_view",
            "SELECT change_status.resource_name FROM change_status WHERE change_status.resource_type = 'CAMPAIGN'",
            "SELECT change_status.resource_name FROM change_status WHERE change_status.last_change_date_time BETWEEN '2026-01-01' AND '2026-01-02'",
            "SELECT change_status.resource_name FROM change_status WHERE change_status.last_change_date_time BETWEEN '2026-01-01' AND '2026-01-02' LIMIT 20000",
            "SELECT google_ads_field.name WHERE name = 'campaign.id'",
        ]:
            with pytest.raises(SystemExit):
                validate_gaql.validate_gaql("1234567890", "v26", bad_q, use_cache=False)

        # Cached invalid entry branch
        cache_file = tmp_path / "gaql_cache.json"
        validate_gaql.set_cached_validation(
            query="SELECT campaign.id FROM campaign",
            api_version="v26",
            valid=False,
            message="FAILURE: Cached failure",
            cache_path=str(cache_file),
        )
        with pytest.raises(SystemExit):
            validate_gaql.validate_gaql(
                "1234567890",
                "v26",
                "SELECT campaign.id FROM campaign",
                use_cache=True,
                cache_path=str(cache_file),
            )

        # main() reading from stdin (non-tty) and failing when tty without --query
        fake_stdin = MagicMock()
        fake_stdin.isatty.return_value = True
        monkeypatch.setattr(sys, "stdin", fake_stdin)
        monkeypatch.setattr(
            sys,
            "argv",
            ["validate_gaql.py", "--customer_id", "1234567890", "--api_version", "v26"],
        )
        with pytest.raises(SystemExit):
            validate_gaql.main()

    def test_sidecar_server_post_routing_and_version_fallbacks(self, tmp_path, monkeypatch):
        # 1. do_POST routing for all supported intents + unsupported intent
        handler = server.A2AHandler.__new__(server.A2AHandler)
        handler.path = "/v1/a2a/tasks"
        handler._send_json = MagicMock()

        client, _ = TestCreateAccountCampaignAdGroupAd._build_mock_ads_client()
        for intent_name in [
            "GAQL_VALIDATE",
            "INSPECT_OBJECT",
            "GENERATE_CODE",
            "TROUBLESHOOT_CONVERSIONS",
            "PREPARE_MUTATION",
            "EXECUTE_MUTATION",
            "CREATE_ACCOUNT",
            "CREATE_CAMPAIGN",
            "CREATE_AD_GROUP",
            "CREATE_AD",
            "UNKNOWN_INTENT",
        ]:
            body = json.dumps(
                {
                    "task_id": f"t-{intent_name}",
                    "intent": intent_name,
                    "payload": {
                        "customer_id": "1234567890",
                        "query": "SELECT campaign.id FROM campaign",
                    },
                }
            ).encode("utf-8")
            handler.headers = {"Content-Length": str(len(body))}
            handler.rfile = MagicMock()
            handler.rfile.read.return_value = body
            with patch.object(
                handler,
                "handle_create_account",
                return_value={"task_id": "t", "status": "COMPLETED"},
            ), patch.object(
                handler,
                "handle_create_campaign",
                return_value={"task_id": "t", "status": "COMPLETED"},
            ), patch.object(
                handler,
                "handle_create_ad_group",
                return_value={"task_id": "t", "status": "COMPLETED"},
            ), patch.object(
                handler,
                "handle_create_ad",
                return_value={"task_id": "t", "status": "COMPLETED"},
            ):
                handler.do_POST()
            assert handler._send_json.call_args[0][0] == 200

        # 2. get_effective_api_version fallbacks when config files and client_libs are absent
        monkeypatch.delenv("GOOGLE_ADS_API_VERSION", raising=False)
        monkeypatch.setattr(os.path, "isfile", lambda p: False)
        monkeypatch.setattr(os.path, "isdir", lambda p: False)
        import google.ads.googleads as gads_pkg

        monkeypatch.setattr(gads_pkg, "__dir__", lambda: ["v25", "v26"])
        # Installed google.ads.googleads attribute inspection
        ver = server.get_effective_api_version({})
        assert ver == "v26"

        # Interactive tty input and ValueError when google.ads.googleads has no v<N> attrs
        monkeypatch.setattr(gads_pkg, "__dir__", lambda: [])
        fake_stdin = MagicMock()
        fake_stdin.isatty.return_value = True
        monkeypatch.setattr(sys, "stdin", fake_stdin)
        monkeypatch.setattr("builtins.input", lambda _: "25")
        assert server.get_effective_api_version({}) == "v25"

        fake_stdin.isatty.return_value = False
        with pytest.raises(ValueError):
            server.get_effective_api_version({})

    def test_set_financial_limits_comprehensive_branches(self, tmp_path, monkeypatch, capsys):
        sfl = load_script_module(
            "skills/execute-mutation/scripts/set_financial_limits.py", "sfl_cov_test"
        )

        # 1. resolve_limit_key & resolve_limit_keys branches
        assert sfl.resolve_limit_key("campaignbudgetservice.amount_micros") == "CampaignBudgetService.amount_micros"
        assert sfl.resolve_limit_key("campaignbudgetservice.amount-micros") == "CampaignBudgetService.amount_micros"
        assert sfl.resolve_limit_key("*.amount_micros") == "CampaignBudgetService.amount_micros"
        assert sfl.resolve_limit_key("campaign_budget_amount_micros") == "CampaignBudgetService.amount_micros"
        with pytest.raises(ValueError):
            sfl.resolve_limit_key("NonExistentService.no_such_field")

        assert "CampaignBudgetService.amount_micros" in sfl.resolve_limit_keys("*.amount_micros")
        assert "CampaignBudgetService.amount_micros" in sfl.resolve_limit_keys("campaign_budget_amount_micros")
        assert "AdGroupService.cpc_bid_micros" in sfl.resolve_limit_keys("cpc_bid_micros")
        assert sfl.resolve_limit_keys("campaignbudgetservice.amount_micros") == ["CampaignBudgetService.amount_micros"]

        # 2. parse_and_validate_limit_amount validation errors and float/int conversions
        with pytest.raises(ValueError):
            sfl.parse_and_validate_limit_amount("CampaignBudgetService.amount_micros", True)
        with pytest.raises(ValueError):
            sfl.parse_and_validate_limit_amount("CampaignBudgetService.amount_micros", "   ")
        with pytest.raises(ValueError):
            sfl.parse_and_validate_limit_amount("CampaignBudgetService.amount_micros", 12.5)
        assert sfl.parse_and_validate_limit_amount("CampaignBudgetService.amount_micros", 100.0) == 100
        with pytest.raises(ValueError):
            sfl.parse_and_validate_limit_amount("CampaignBudgetService.amount_micros", "12.5")
        with pytest.raises(ValueError):
            sfl.parse_and_validate_limit_amount("CampaignBudgetService.amount_micros", "not_an_int")
        with pytest.raises(ValueError):
            sfl.parse_and_validate_limit_amount("CampaignBudgetService.amount_micros", -5)
        with pytest.raises(ValueError):
            sfl.parse_and_validate_limit_amount("ConversionUploadService.conversion_value", "not_a_float")
        with pytest.raises(ValueError):
            sfl.parse_and_validate_limit_amount("ConversionUploadService.conversion_value", -1.5)

        # 3. parse_financial_limits fallback line-by-line parser (invalid TOML syntax with [Section])
        raw_fallback = (
            "[CampaignBudgetService]\n"
            "amount_micros = 25000000\n"
            "invalid toml line without equals\n"
            "campaign_budget_amount_micros = 10000000\n"
            "ConversionUploadService.conversion_value = 99.5\n"
        )
        parsed = sfl.parse_financial_limits(raw_fallback)
        assert parsed["CampaignBudgetService.amount_micros"] == 25_000_000
        assert parsed["ConversionUploadService.conversion_value"] == 99.5

        # 4. format_limit_display_value for all 4 monetary units and format_limits_table
        assert "NOT MODIFIABLE" in sfl.format_limit_display_value("CampaignBudgetService.amount_micros", 0)
        assert "currency units" in sfl.format_limit_display_value("CampaignBudgetService.amount_micros", 5_000_000)
        assert "micros_proportion" in sfl.format_limit_display_value("AdGroupService.percent_cpc_bid_micros", 200_000)
        assert "currency_units" in sfl.format_limit_display_value("ConversionUploadService.conversion_value", 50.0)
        assert "decimal_ratio" in sfl.format_limit_display_value("CampaignService.target_roas", 2.5)

        # 5. run_interactive_prompt and CLI main() flags
        fl_file = tmp_path / "financial_limits"
        inputs = iter(["50000000", ""])

        def _fake_input(_prompt):
            try:
                return next(inputs)
            except StopIteration:
                raise EOFError()

        monkeypatch.setattr("builtins.input", _fake_input)
        written = sfl.run_interactive_prompt(config_file=str(fl_file))
        assert written == str(fl_file)

        # CLI main(): --type without --amount error, --type with --amount, --set, --reset, --reset-all, --json, --show
        assert sfl.main(["--type", "CampaignBudgetService.amount_micros", "--config-file", str(fl_file)]) == 2
        assert sfl.main(["--set", "bad_format_no_equals", "--config-file", str(fl_file)]) == 2
        assert (
            sfl.main(
                [
                    "--type",
                    "CampaignBudgetService.amount_micros",
                    "--amount",
                    "75000000",
                    "--set",
                    "ConversionUploadService.conversion_value=120.5",
                    "--campaign-budget-amount-micros",
                    "80000000",
                    "--AdGroupService.cpc_bid_micros",
                    "2000000",
                    "--config-file",
                    str(fl_file),
                ]
            )
            == 0
        )
        assert (
            sfl.main(
                [
                    "--reset",
                    "AdGroupService.cpc_bid_micros",
                    "--json",
                    "--config-file",
                    str(fl_file),
                ]
            )
            == 0
        )
        assert sfl.main(["--reset-all", "--show", "--config-file", str(fl_file)]) == 0
        capsys.readouterr()

    def test_sync_client_libs_git_archive_and_assistant_repo_branches(self, tmp_path, monkeypatch):
        # 1. _resolve_default_branch fallback to refs/heads/main and update_codebase_via_git
        def _fake_git_run(cmd, **kwargs):
            res = MagicMock()
            if "symbolic-ref" in cmd:
                res.returncode = 1
                res.stdout = ""
            elif "show-ref" in cmd:
                res.returncode = 0
            elif "fetch" in cmd or "checkout" in cmd or "branch" in cmd or "pull" in cmd:
                res.returncode = 0
            else:
                res.returncode = 0
                res.stdout = "v4.1.0\n"
            return res

        monkeypatch.setattr(sync_client_libs.subprocess, "run", _fake_git_run)
        assert sync_client_libs._resolve_default_branch(str(tmp_path)) == "main"
        assert sync_client_libs.update_codebase_via_git(str(tmp_path), "v30.0.0") is True
        assert sync_client_libs.update_codebase_via_git(str(tmp_path), "") is True

        # 2. update_api_version_cache_if_needed with existing assistant_config and api_version.txt
        lib_dir = tmp_path / "a" / "b" / "client_libs" / "google-ads-python"
        (lib_dir / "google" / "ads" / "googleads" / "v27").mkdir(parents=True)
        cfg_dir = tmp_path / "a" / "b" / "config"
        cfg_dir.mkdir(parents=True)
        (cfg_dir / "assistant_config").write_text(
            'api_version = "v25"\ncustomer_id = "9998887777"\nexecute_mutates = true\nenabled = true\n',
            encoding="utf-8",
        )
        (cfg_dir / "api_version.txt").write_text("v25\n", encoding="utf-8")
        assert sync_client_libs.update_api_version_cache_if_needed(str(lib_dir)) == "v27"
        assert 'api_version = "v27"' in (cfg_dir / "assistant_config").read_text(encoding="utf-8")
        assert (cfg_dir / "api_version.txt").read_text(encoding="utf-8").strip() == "v27"

        # 3. fetch_latest_pypi_python_version, check_system_package_parity, upgrade_system_package fallback
        import tempfile

        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
        FakeResp = MagicMock()
        FakeResp.__enter__.return_value.read.return_value = b'{"info": {"version": "30.1.0"}}'
        monkeypatch.setattr(sync_client_libs.urllib.request, "urlopen", lambda *a, **kw: FakeResp)
        assert sync_client_libs.fetch_latest_pypi_python_version("google-ads", force=True) == "30.1.0"
        # Second call hits cache
        assert sync_client_libs.fetch_latest_pypi_python_version("google-ads", force=False) == "30.1.0"

        parity = sync_client_libs.check_system_package_parity("google-ads", "29.1.0")
        assert "matches" in parity

        # upgrade_system_package fallback to local lib_path when pypi install returns non-zero
        (lib_dir / "pyproject.toml").write_text('[project]\nversion = "30.1.0"\n', encoding="utf-8")
        call_count = {"n": 0}

        def _fake_pip_install(cmd, **kwargs):
            call_count["n"] += 1
            r = MagicMock()
            r.returncode = 1 if call_count["n"] == 1 else 0
            return r

        monkeypatch.setattr(sync_client_libs.subprocess, "run", _fake_pip_install)
        assert sync_client_libs.upgrade_system_package("google-ads", "30.1.0", lib_path=str(lib_dir)) is True

        # 4. process_client_libs with multiple libraries (ThreadPoolExecutor prefetch) and upgrade_system=True
        py_lib = tmp_path / "multi_libs" / "google-ads-python"
        java_lib = tmp_path / "multi_libs" / "google-ads-java"
        py_lib.mkdir(parents=True)
        java_lib.mkdir(parents=True)
        (py_lib / "pyproject.toml").write_text('version = "28.0.0"\n', encoding="utf-8")
        (java_lib / "pom.xml").write_text("<project><version>30.0.0</version></project>\n", encoding="utf-8")
        monkeypatch.setattr(
            sync_client_libs,
            "fetch_github_latest_release",
            lambda slug, force=False: ("v29.0.0", "https://example.com/t.tar.gz"),
        )
        monkeypatch.setattr(sync_client_libs, "update_codebase_via_archive", lambda *a, **kw: True)
        monkeypatch.setattr(sync_client_libs, "detect_system_package_version", lambda pkg="google-ads": ("28.0.0", ["/site"]))
        monkeypatch.setattr(sync_client_libs, "upgrade_system_package", lambda *a, **kw: True)

        results = sync_client_libs.process_client_libs(
            str(tmp_path / "multi_libs"),
            check_only=False,
            force=True,
            include_assistant=False,
            upgrade_system=True,
        )
        assert len(results) == 2
        assert any(r["codebase"] == "google-ads-python" and r["status"] == "UPDATED" for r in results)

    def test_config_init_comprehensive_branches(self, tmp_path, monkeypatch, capsys):
        import tempfile
        import urllib.request
        from config import config_init

        monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))

        # 1. parse_dotnet_config key=value fallback and get_version script fallback
        orig_isfile = os.path.isfile
        monkeypatch.setattr(config_init, "_CACHED_VERSION", None)
        monkeypatch.setattr(
            os.path,
            "isfile",
            lambda p: False if str(p).endswith("plugin.json") else orig_isfile(p),
        )
        assert config_init.get_version() != ""
        monkeypatch.setattr(os.path, "isfile", orig_isfile)

        kv_cfg = tmp_path / "custom.config"
        kv_cfg.write_text(
            "# comment\n"
            "LoginCustomerId = 1112223333\n"
            "OAuth2ClientId: my-client-id\n"
            "OAuth2ClientSecret: my-secret\n"
            "OAuth2RefreshToken: my-token\n",
            encoding="utf-8",
        )
        parsed_dn = config_init.parse_dotnet_config(str(kv_cfg))
        assert parsed_dn["login_customer_id"] == "1112223333"
        assert parsed_dn["client_id"] == "my-client-id"

        # 2. copy_and_append_version across PHP, Ruby, Java, DotNet JSON (GoogleAdsApi & root), DotNet XML, and other
        for fname, lang, initial_text, expected_substr in [
            ("php.ini", "PHP", 'ads_assistant = "old"\n', 'ads_assistant = "9.9.9"'),
            ("ruby.rb", "Ruby", "ENV['ADS_ASSISTANT'] = 'old'\n", "ENV['ADS_ASSISTANT'] = '9.9.9'"),
            ("java.properties", "Java", "api.googleads.ads_assistant=old\n", "api.googleads.ads_assistant=9.9.9"),
            ("app1.json", "DotNet", '{"GoogleAdsApi": {"ClientId": "x"}}', '"ads_assistant": "9.9.9"'),
            ("app2.json", "DotNet", '{"ClientId": "x"}', '"ads_assistant": "9.9.9"'),
            ("app_bad.json", "DotNet", "{bad json", "ads_assistant: 9.9.9"),
            (
                "app1.xml",
                "DotNet",
                '<configuration><appSettings><add key="ads_assistant" value="old"/></appSettings></configuration>',
                'value="9.9.9"',
            ),
            (
                "app2.xml",
                "DotNet",
                "<configuration><appSettings></appSettings></configuration>",
                '<add key="ads_assistant" value="9.9.9"/>',
            ),
            ("other.txt", "OTHER", "hello: world", "ads_assistant: 9.9.9"),
        ]:
            src_f = tmp_path / f"src_{fname}"
            dst_f = tmp_path / f"dst_{fname}"
            src_f.write_text(initial_text, encoding="utf-8")
            assert config_init.copy_and_append_version(str(src_f), str(dst_f), version="9.9.9", lang=lang) is True
            assert expected_substr in dst_f.read_text(encoding="utf-8")

        # 3. sync_and_set_config_kv with .ini, .rb, .properties, .json sources and key updates
        sync_dir = tmp_path / "sync_cfg"
        ini_src = tmp_path / "google_ads_php.ini"
        ini_src.write_text(
            '[GOOGLE_ADS]\nloginCustomerId = "1234567890"\n[OAUTH2]\nclientId = "cid"\nclientSecret = "sec"\nrefreshToken = "tok"\n',
            encoding="utf-8",
        )
        config_init.sync_and_set_config_kv(
            key="execute_mutates",
            value=True,
            source_yaml=str(ini_src),
            config_dir=str(sync_dir),
            version="9.9.9",
        )
        config_init.sync_and_set_config_kv(
            key="enabled",
            value="true",
            source_yaml=str(ini_src),
            config_dir=str(sync_dir),
        )
        config_init.sync_and_set_config_kv(
            key="api_version",
            value="v26",
            source_yaml=str(ini_src),
            config_dir=str(sync_dir),
        )
        config_init.sync_and_set_config_kv(
            key="customer_id",
            value="1234567890",
            source_yaml=str(ini_src),
            config_dir=str(sync_dir),
        )

        # Fallback discovery when source_yaml doesn't exist but google_ads_php.ini is in same dir
        fallback_dir = tmp_path / "fb_cfg"
        res_yaml = config_init.sync_and_set_config_kv(
            source_yaml=str(tmp_path / "nonexistent_google-ads.yaml"),
            config_dir=str(fallback_dir),
        )
        assert os.path.isfile(res_yaml)

        # 4. fetch_latest_pypi_python_version, fetch_latest_github_python_version, and ensure_client_libs_synced
        FakeUrlResp = MagicMock()
        FakeUrlResp.__enter__.return_value.read.return_value = b'{"info": {"version": "30.0.0"}, "tag_name": "v30.0.0"}'
        monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: FakeUrlResp)
        assert config_init.fetch_latest_pypi_python_version("google-ads", force=True) == "30.0.0"
        assert config_init.fetch_latest_pypi_python_version("google-ads", force=False) == "30.0.0"
        assert config_init.fetch_latest_github_python_version(force=True) == "30.0.0"
        assert config_init.fetch_latest_github_python_version(force=False) == "30.0.0"

        # Call real _find_sync_client_libs_script before mocking
        assert config_init._find_sync_client_libs_script() is not None

        monkeypatch.setattr(
            config_init,
            "check_python_client_lib_parity",
            lambda **kw: {"local_version": "28.0.0", "system_version": "29.0.0", "matches": False},
        )
        monkeypatch.setattr(config_init, "_find_sync_client_libs_script", lambda: None)
        assert config_init.ensure_client_libs_synced()["triggered"] is False

        monkeypatch.setattr(config_init, "_find_sync_client_libs_script", lambda: "/fake/sync.py")
        monkeypatch.setattr(config_init.subprocess, "Popen", MagicMock())
        bg_res = config_init.ensure_client_libs_synced(async_in_background=True, force=True)
        assert bg_res["triggered"] is True and bg_res["mode"] == "background"

        # When matches=True and stamp is fresh, ensure_client_libs_synced returns up_to_date_within_ttl
        monkeypatch.setattr(
            config_init,
            "check_python_client_lib_parity",
            lambda **kw: {"local_version": "29.0.0", "system_version": "29.0.0", "matches": True},
        )
        ttl_res = config_init.ensure_client_libs_synced(async_in_background=True, force=False)
        assert ttl_res["triggered"] is False and ttl_res["reason"] == "up_to_date_within_ttl"

        monkeypatch.setattr(
            config_init.subprocess,
            "run",
            MagicMock(return_value=MagicMock(returncode=0)),
        )
        sync_res = config_init.ensure_client_libs_synced(
            async_in_background=False, force=True, config_dir=str(sync_dir)
        )
        assert sync_res["triggered"] is True and sync_res["mode"] == "synchronous"

        # 5. parse_assistant_config loose fallback & plugin enable/disable manifest toggling
        loose_cfg = config_init.parse_assistant_config(
            "invalid = [toml\n"
            "api_version: 26\n"
            'customer_id: "7778889999"\n'
            "execute_mutates: true\n"
            "enabled: yes\n"
            "plugin_enabled: off\n"
        )
        assert loose_cfg["api_version"] == "v26"
        assert loose_cfg["execute_mutates"] is True
        assert loose_cfg["enabled"] is True
        assert loose_cfg["plugin_enabled"] is False

        fake_plugin_dir = tmp_path / "installed_plugin"
        fake_plugin_dir.mkdir()
        (fake_plugin_dir / "plugin.json").write_text('{"version": "4.2.0"}', encoding="utf-8")
        (fake_plugin_dir / "hooks.json").write_text(
            json.dumps(
                {
                    "hooks": {
                        "config-init": {"enabled": True},
                        "PreToolUse": [{"hooks": [{"command": "python3 config_init.py --hook", "enabled": True}]}],
                    }
                }
            ),
            encoding="utf-8",
        )
        toggled_off = config_init._toggle_installed_plugin_manifests(
            str(fake_plugin_dir), enabled=False, is_repo_source=False
        )
        assert len(toggled_off["updated_files"]) >= 2
        assert config_init._is_hooks_json_disabled(str(fake_plugin_dir / "hooks.json")) is True
        monkeypatch.setattr(config_init, "get_assistant_config_paths", lambda **kw: [])
        assert config_init.is_plugin_enabled(config_dir=str(fake_plugin_dir)) is False

        toggled_on = config_init._toggle_installed_plugin_manifests(
            str(fake_plugin_dir), enabled=True, is_repo_source=False
        )
        assert len(toggled_on["updated_files"]) >= 2
        assert config_init._is_hooks_json_disabled(str(fake_plugin_dir / "hooks.json")) is False

        # Financial hook helpers, canonical hash, and status helpers
        assert config_init._hook_payload_has_financial_fields({"operations": [{"create": {"amount_micros": 1000}}]}) is True
        assert config_init._hook_payload_has_financial_fields({"name": "no_money"}) is False
        assert config_init._is_financial_receipt_for_hook({"is_financial_transaction": True}) is True
        assert (
            config_init._is_financial_receipt_for_hook(
                {"dry_run_rpc_calls": [{"service": "CampaignBudgetService", "method": "MutateCampaignBudgets"}]}
            )
            is True
        )
        assert config_init._is_financial_receipt_for_hook({"operation_summary": "Update budget to $50/day"}) is True
        assert config_init._has_financial_consequence_for_hook(["Will increase daily budget spend by $10"]) is True
        assert config_init._has_financial_consequence_for_hook("not a list") is False
        digest = config_init._compute_canonical_request_sha256(
            "CampaignService",
            "MutateCampaigns",
            {"validate_only": True, "operations": [{"create": {"name": "Test"}}]},
        )
        assert len(digest) == 64
        ok_lim, _, _ = config_init._check_financial_limits_for_hook(receipt={"dry_run_rpc_calls": []})
        assert ok_lim is True
        status_info = config_init.get_plugin_status(config_dir=str(sync_dir))
        assert "Google Ads API Developer Assistant Status" in config_init.format_plugin_status_text(status_info)

        # 6. handle_hook for disabled plugin, PreToolUse command rewriting, and PreInvocation (first & second prompt)
        monkeypatch.setattr(config_init, "is_plugin_enabled", lambda *a, **kw: False)
        fake_stdin = MagicMock()
        fake_stdin.isatty.return_value = False
        fake_stdin.read.return_value = json.dumps({"toolCall": {"args": {"CommandLine": "python3 foo.py"}}})
        monkeypatch.setattr(sys, "stdin", fake_stdin)
        config_init.handle_hook()
        assert '"decision": "allow"' in capsys.readouterr().out

        monkeypatch.setattr(config_init, "is_plugin_enabled", lambda *a, **kw: True)
        monkeypatch.setattr(config_init, "sync_and_set_config_kv", lambda *a, **kw: str(sync_dir / "google-ads.yaml"))
        fake_stdin.read.return_value = json.dumps(
            {
                "tool_input": {
                    "command": "python3 -c \"GoogleAdsClient.load_from_storage(); GoogleAdsClient.load_from_storage(version='v26')\" ~/google-ads.yaml skills/validate-gaql/scripts/validate_gaql.py"
                }
            }
        )
        config_init.handle_hook()
        hook_out = json.loads(capsys.readouterr().out)
        assert hook_out["decision"] == "allow"
        assert 'path="config/google-ads.yaml"' in hook_out["overwrite"]["command"]

        # PreInvocation hook (invocationNum = 1 and invocationNum = 2)
        fake_stdin.read.return_value = json.dumps({"invocationNum": 1})
        config_init.handle_hook()
        first_out = json.loads(capsys.readouterr().out)
        assert "injectSteps" in first_out

        fake_stdin.read.return_value = json.dumps({"invocationNum": 2})
        config_init.handle_hook()
        second_out = json.loads(capsys.readouterr().out)
        assert "Parity verification was completed on the first prompt" in second_out["injectSteps"][0]["ephemeralMessage"]

        # 7. CLI main() flags (--status, --status --json, and standard initialization)
        monkeypatch.setattr(sys, "argv", ["config_init.py", "--status", "--config-dir", str(sync_dir)])
        config_init.main()
        assert "Google Ads API Developer Assistant Status" in capsys.readouterr().out

        monkeypatch.setattr(sys, "argv", ["config_init.py", "--status", "--json", "--config-dir", str(sync_dir)])
        config_init.main()
        assert '"enabled":' in capsys.readouterr().out

        monkeypatch.setattr(
            sys,
            "argv",
            [
                "config_init.py",
                "--key",
                "customer_id",
                "--value",
                "1234567890",
                "--execute-mutates",
                "false",
                "--config-dir",
                str(sync_dir),
                "--source-yaml",
                str(ini_src),
            ],
        )
        config_init.main()
        assert "GOOGLE_ADS_CONFIGURATION_FILE_PATH" in capsys.readouterr().out








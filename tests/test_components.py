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

    def test_detect_latest_api_version_fallback(self):
        with patch("os.path.isdir", return_value=False), \
             patch.dict("sys.modules", {"google.ads.googleads": None}):
            ver = get_latest_api_version.detect_latest_api_version()
            assert ver == "v25"

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
        src_yaml.write_text("# Use CID 12345678 for testing\ndeveloper_token: \"test_token\"\n")
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
        assert 'developer_token: "test_token"' in content
        assert 'login_customer_id: "9876543210"' in content
        assert "ads_assistant: 4.1.0" in content
        if sys.platform != "win32":
            assert oct(os.stat(res_path).st_mode & 0o777) == "0o600"
        assert os.environ.get("GOOGLE_ADS_CONFIGURATION_FILE_PATH") == res_path

    def test_sync_and_set_config_kv_updates_existing(self, tmp_path):
        from config.config_init import sync_and_set_config_kv

        src_yaml = tmp_path / "source.yaml"
        src_yaml.write_text("login_customer_id: \"old_val\"\ndeveloper_token: \"test_token\"\n")
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
            "developer_token": "token_123",
            "client_id": "client_abc",
            "client_secret": "secret_xyz",
            "refresh_token": "refresh_999",
            "login_customer_id": "1234567890",
        }
        success = write_yaml_config(data, target_path=str(target), version="2.3.0")
        assert success is True
        assert target.is_file()

        content = target.read_text()
        assert "developer_token: token_123" in content
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
            "developer_token": "token_sa",
            "json_key_file_path": "/path/to/key.json",
            "impersonated_email": "sa@example.com",
            "login_customer_id": "9998887776",
        }
        success = write_yaml_config(data, target_path=str(target))
        assert success is True
        assert target.is_file()

        content = target.read_text()
        assert "developer_token: token_sa" in content
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
        assert "developer_token: INSERT_DEVELOPER_TOKEN_HERE" in content
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
            '  c.developer_token = "ruby_dev_token"\n'
            '  c.client_id = "ruby_client_id"\n'
            '  c.client_secret = "ruby_client_secret"\n'
            '  c.refresh_token = "ruby_refresh_token"\n'
            '  c.login_customer_id = "1122334455"\n'
            'end\n'
        )
        data = parse_ruby_config(str(ruby_file))
        assert data["developer_token"] == "ruby_dev_token"
        assert data["client_id"] == "ruby_client_id"
        assert data["client_secret"] == "ruby_client_secret"
        assert data["refresh_token"] == "ruby_refresh_token"
        assert data["login_customer_id"] == "1122334455"

    def test_parse_ini_config(self, tmp_path):
        from config.config_init import parse_ini_config

        ini_file = tmp_path / "google_ads_php.ini"
        ini_file.write_text(
            '[GOOGLE_ADS]\n'
            'developerToken = "php_dev_token"\n'
            'clientId = "php_client_id"\n'
            'clientSecret = "php_client_secret"\n'
            'refreshToken = "php_refresh_token"\n'
            'loginCustomerId = "5544332211"\n'
        )
        data = parse_ini_config(str(ini_file))
        assert data["developer_token"] == "php_dev_token"
        assert data["client_id"] == "php_client_id"
        assert data["client_secret"] == "php_client_secret"
        assert data["refresh_token"] == "php_refresh_token"
        assert data["login_customer_id"] == "5544332211"

    def test_parse_properties_config(self, tmp_path):
        from config.config_init import parse_properties_config

        prop_file = tmp_path / "ads.properties"
        prop_file.write_text(
            'api.googleads.developerToken=java_dev_token\n'
            'api.googleads.clientId=java_client_id\n'
            'api.googleads.clientSecret=java_client_secret\n'
            'api.googleads.refreshToken=java_refresh_token\n'
            'api.googleads.loginCustomerId=9988776655\n'
        )
        data = parse_properties_config(str(prop_file))
        assert data["developer_token"] == "java_dev_token"
        assert data["client_id"] == "java_client_id"
        assert data["client_secret"] == "java_client_secret"
        assert data["refresh_token"] == "java_refresh_token"
        assert data["login_customer_id"] == "9988776655"

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

    def test_sync_and_set_config_kv_fallback_php(self, tmp_path):
        from config.config_init import sync_and_set_config_kv

        # No source.yaml, but google_ads_php.ini exists in home_dir
        home_dir = tmp_path / "home"
        home_dir.mkdir()
        php_file = home_dir / "google_ads_php.ini"
        php_file.write_text(
            'developerToken = "fallback_token"\n'
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
        assert "developer_token: fallback_token" in content
        assert "client_id: fallback_cid" in content
        assert "ads_assistant:" in content

    def test_sync_and_set_config_kv_reconstructs_from_home_on_new_session(self, tmp_path):
        from config.config_init import sync_and_set_config_kv

        dest_dir = tmp_path / "config"
        dest_dir.mkdir()
        existing_yaml = dest_dir / "google-ads.yaml"
        existing_yaml.write_text("developer_token: \"stale_token\"\n")

        src_yaml = tmp_path / "google-ads.yaml"
        src_yaml.write_text("developer_token: \"fresh_session_token\"\n")

        res_path = sync_and_set_config_kv(
            source_yaml=str(src_yaml),
            config_dir=str(dest_dir),
        )

        content = open(res_path).read()
        assert 'developer_token: "fresh_session_token"' in content
        assert "stale_token" not in content
        assert os.environ.get("GOOGLE_ADS_CONFIGURATION_FILE_PATH") == str(existing_yaml)

    def test_copy_and_append_version_no_duplicates(self, tmp_path):
        from config.config_init import copy_and_append_version

        src = tmp_path / "test.yaml"
        src.write_text("developer_token: \"token\"\nads_assistant: 1.0.0\n")
        dst = tmp_path / "out.yaml"

        copy_and_append_version(str(src), str(dst), version="4.0.0", lang="YAML")
        content = dst.read_text()
        assert content.count("ads_assistant:") == 1
        assert "ads_assistant: 4.0.0" in content

    def test_config_init_main_default_cid_and_dummy_cleanup(self, tmp_path, monkeypatch, capsys):
        import config.config_init as cfg_init

        src_yaml = tmp_path / "home_google_ads.yaml"
        src_yaml.write_text('developer_token: "tok_abc"\n', encoding="utf-8")

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

    def test_config_init_parity(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        root_cfg = os.path.join(repo_root, "config", "config_init.py")
        plugin_cfg = os.path.join(
            repo_root,
            "plugins",
            "google-ads-api-developer-assistant",
            "config",
            "config_init.py",
        )
        with open(root_cfg, "r", encoding="utf-8") as f1, open(
            plugin_cfg, "r", encoding="utf-8"
        ) as f2:
            assert f1.read() == f2.read(), (
                "config/config_init.py and plugins/.../config/config_init.py must remain identical"
            )

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
        src_yaml.write_text('developer_token: "test_token"\n', encoding="utf-8")

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




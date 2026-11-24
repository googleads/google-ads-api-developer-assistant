# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit and simulated-test-account integration tests for `tests/skills_functional_suite.py`."""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from typing import Any
import pytest
import yaml

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from google.ads.googleads.client import GoogleAdsClient  # noqa: E402
from google.auth.credentials import AnonymousCredentials  # noqa: E402

import hitl_audit_logger as hal  # noqa: E402
import skills_functional_suite as sfs  # noqa: E402


def _write_fake_skills_shim(shim_dir: str) -> None:
    """Writes a chained sitecustomize shim simulating a Google Ads Test Account for skill subprocesses."""
    os.makedirs(shim_dir, exist_ok=True)
    shim_code = '''import importlib.abc
import importlib.util
import os
import sys
from types import SimpleNamespace

if os.environ.get("_GADS_FAKE_SKILLS_SUBPROC") == "1":
    def _patch_client_cls(ClientCls):
        if getattr(ClientCls, "_fake_skills_patched", False):
            return
        from google.auth.credentials import AnonymousCredentials

        def _fake_get_service(self, name, *args, **kwargs):
            svc = SimpleNamespace()
            if name == "CustomerService":
                svc.list_accessible_customers = lambda **kw: SimpleNamespace(
                    resource_names=["customers/4863089361", "customers/8601651289"]
                )
                svc.create_customer_client = lambda request=None, **kw: SimpleNamespace(
                    resource_name="customers/4863089361/customerClients/5556667778",
                    invitation_link="",
                )
                return svc
            if name == "GoogleAdsFieldService":
                svc.search_google_ads_fields = lambda request=None, **kw: [
                    SimpleNamespace(
                        name="campaign.id",
                        selectable=True,
                        filterable=True,
                        selectable_with=["campaign.name", "campaign.status"],
                    )
                ]
                return svc
            if name == "GoogleAdsService":
                def _search(customer_id=None, query="", request=None, **kw):
                    q = str(query or getattr(request, "query", "")).lower()
                    if "from customer_client" in q:
                        row = SimpleNamespace(
                            customer_client=SimpleNamespace(
                                id=4863089361,
                                descriptive_name="Simulated Test Account",
                                manager=False,
                                level=1,
                                status=SimpleNamespace(name="ENABLED"),
                                currency_code="USD",
                                time_zone="America/New_York",
                                hidden=False,
                                test_account=True,
                            )
                        )
                        return [row]
                    if "from customer " in q or q.endswith("from customer"):
                        row = SimpleNamespace(
                            customer=SimpleNamespace(
                                id=4863089361,
                                descriptive_name="Simulated Test Account",
                                test_account=True,
                                currency_code="USD",
                                time_zone="America/New_York",
                                conversion_tracking_setting=SimpleNamespace(
                                    conversion_tracking_id=987654321,
                                    cross_account_conversion_tracking_id=0,
                                    conversion_tracking_status=SimpleNamespace(name="CONVERSION_TRACKING_MANAGED_BY_SELF"),
                                    accepted_customer_data_terms=True,
                                    enhanced_conversions_for_leads_enabled=True,
                                    google_ads_conversion_customer="customers/4863089361",
                                ),
                            )
                        )
                        return [row]
                    if "from conversion_action" in q:
                        row = SimpleNamespace(
                            conversion_action=SimpleNamespace(
                                id=701,
                                name="Simulated Upload Clicks",
                                type_=SimpleNamespace(name="UPLOAD_CLICKS"),
                                status=SimpleNamespace(name="ENABLED"),
                                category=SimpleNamespace(name="PURCHASE"),
                                include_in_conversions_metric=True,
                                click_through_lookback_window_days=30,
                            )
                        )
                        return [row]
                    if "from offline_conversion_upload_client_summary" in q:
                        return []
                    if "from offline_user_data_job" in q:
                        return []
                    if "from click_view" in q:
                        row = SimpleNamespace(
                            click_view=SimpleNamespace(
                                gclid="TeSterGclidSim0001",
                                ad_group_ad="customers/4863089361/adGroupAds/222~333",
                            ),
                            campaign=SimpleNamespace(id=111111111, name="Sim Search"),
                            ad_group=SimpleNamespace(id=222222222, name="Sim AdGroup"),
                            segments=SimpleNamespace(date="2026-10-15"),
                        )
                        return [row]
                    return []

                svc.search = _search
                svc.search_stream = lambda **kw: [SimpleNamespace(results=_search(**kw))]
                svc.mutate = lambda request=None, **kw: SimpleNamespace(
                    request_id="req-sim-ga-mutate",
                    mutate_operation_responses=[
                        SimpleNamespace(
                            campaign_budget_result=SimpleNamespace(
                                resource_name="customers/4863089361/campaignBudgets/901"
                            ),
                            campaign_result=SimpleNamespace(
                                resource_name="customers/4863089361/campaigns/902"
                            ),
                        )
                    ],
                )
                return svc
            if name == "CampaignBudgetService":
                svc.campaign_budget_path = lambda cid, bid: f"customers/{cid}/campaignBudgets/{bid}"
                svc.mutate_campaign_budgets = lambda request=None, **kw: SimpleNamespace(
                    results=[SimpleNamespace(resource_name="customers/4863089361/campaignBudgets/901")]
                )
                return svc
            if name == "CampaignService":
                svc.campaign_path = lambda cid, cmp_id: f"customers/{cid}/campaigns/{cmp_id}"
                svc.mutate_campaigns = lambda request=None, **kw: SimpleNamespace(
                    results=[SimpleNamespace(resource_name="customers/4863089361/campaigns/902")]
                )
                return svc
            if name == "AdGroupService":
                svc.ad_group_path = lambda cid, ag_id: f"customers/{cid}/adGroups/{ag_id}"
                svc.mutate_ad_groups = lambda request=None, **kw: SimpleNamespace(
                    results=[SimpleNamespace(resource_name="customers/4863089361/adGroups/903")]
                )
                return svc
            if name == "AdGroupAdService":
                svc.mutate_ad_group_ads = lambda request=None, **kw: SimpleNamespace(
                    results=[SimpleNamespace(resource_name="customers/4863089361/adGroupAds/903~904")]
                )
                return svc
            if name == "AssetGroupService":
                svc.asset_group_path = lambda cid, ag_id: f"customers/{cid}/assetGroups/{ag_id}"
                return svc
            if name == "AssetGroupListingGroupFilterService":
                svc.mutate_asset_group_listing_group_filters = lambda request=None, **kw: SimpleNamespace(
                    results=[
                        SimpleNamespace(
                            resource_name="customers/4863089361/assetGroupListingGroupFilters/333333333~905"
                        )
                    ]
                )
                return svc
            return svc

        @classmethod
        def _fake_load_from_storage(cls, path=None, version=None, **kwargs):
            return cls(credentials=AnonymousCredentials(), version=version, use_proto_plus=True)

        ClientCls.get_service = _fake_get_service
        ClientCls.load_from_storage = _fake_load_from_storage
        ClientCls._fake_skills_patched = True

    class _FakeSkillsFinder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path, target=None):
            if fullname == "google.ads.googleads.client":
                for f in list(sys.meta_path):
                    if f is self:
                        continue
                    spec = f.find_spec(fullname, path, target)
                    if spec and spec.loader:
                        orig_exec = spec.loader.exec_module
                        def _wrapped_exec(mod, _orig=orig_exec):
                            _orig(mod)
                            if hasattr(mod, "GoogleAdsClient"):
                                _patch_client_cls(mod.GoogleAdsClient)
                        spec.loader.exec_module = _wrapped_exec
                        return spec
            return None

    sys.meta_path.insert(0, _FakeSkillsFinder())

# Chain to downstream sitecustomize.py (plugin config/sitecustomize.py & coverage hooks)
_this_real = os.path.normcase(os.path.realpath(__file__))
_seen = getattr(sys, "_gads_chained_sitecustomizes", None)
if _seen is None:
    _seen = set()
    setattr(sys, "_gads_chained_sitecustomizes", _seen)
_seen.add(_this_real)
for _entry in list(sys.path):
    if not _entry:
        continue
    _cand = os.path.join(_entry, "sitecustomize.py")
    if os.path.isfile(_cand):
        _real = os.path.normcase(os.path.realpath(_cand))
        if _real not in _seen:
            _seen.add(_real)
            _spec = importlib.util.spec_from_file_location("_skills_downstream_sc", _cand)
            if _spec and _spec.loader:
                _m = importlib.util.module_from_spec(_spec)
                _spec.loader.exec_module(_m)
            break
'''
    with open(os.path.join(shim_dir, "sitecustomize.py"), "w", encoding="utf-8") as f:
        f.write(shim_code)


def _make_fake_live_client(*, is_test_account: bool = True) -> Any:
    api_ver = hal._detect_default_api_version()
    proto_client = GoogleAdsClient(
        credentials=AnonymousCredentials(), version=api_ver, use_proto_plus=True
    )

    class _FakeClient:
        enums = proto_client.enums

        def get_type(self, name: str) -> Any:
            return proto_client.get_type(name)

        def get_service(self, name: str) -> Any:
            svc = SimpleNamespace()
            if name == "CustomerService":
                svc.list_accessible_customers = lambda **kw: SimpleNamespace(
                    resource_names=["customers/4863089361", "customers/8601651289"]
                )
                return svc
            if name == "GoogleAdsService":
                def _search(customer_id: str = "", query: str = "", **kw: Any) -> list[Any]:
                    ql = query.lower()
                    if "from customer" in ql:
                        return [
                            SimpleNamespace(
                                customer=SimpleNamespace(
                                    id=int(customer_id or "4863089361"),
                                    descriptive_name="Simulated Test Account",
                                    test_account=is_test_account,
                                )
                            )
                        ]
                    if "from campaign" in ql:
                        return [SimpleNamespace(campaign=SimpleNamespace(id=111111111))]
                    if "from ad_group" in ql:
                        return [SimpleNamespace(ad_group=SimpleNamespace(id=222222222))]
                    if "from asset_group" in ql:
                        return [SimpleNamespace(asset_group=SimpleNamespace(id=333333333))]
                    return []

                svc.search = _search
                return svc
            return svc

    return _FakeClient()


_REAL_TOKEN_SENTINEL = "1//REAL-DEVELOPER-REFRESH-TOKEN-MUST-NOT-BE-READ"


def _write_offline_fixtures(tmp_path: Any) -> tuple[Any, Any]:
    """Writes a tmp credentials yaml (with a sentinel token) and a tmp test-account config."""
    creds = tmp_path / "offline-google-ads.yaml"
    creds.write_text(
        yaml.safe_dump({
            "client_id": "1234567890-abc.apps.googleusercontent.com",
            "client_secret": "secret",
            "refresh_token": _REAL_TOKEN_SENTINEL,
            "use_proto_plus": True,
        }),
        encoding="utf-8",
    )
    cfg_path = tmp_path / "offline_test_account_config.yaml"
    cfg_path.write_text(
        yaml.safe_dump({
            "test_account": {
                "test_customer_id": "REPLACE_WITH_TEST_CUSTOMER_ID",
                "credentials_yaml_path": str(creds),
            },
            "audit_log": {"directory": str(tmp_path / "audit_logs")},
        }),
        encoding="utf-8",
    )
    return creds, cfg_path


class TestSkillsFunctionalSuite:
    """Verifies CLI flags, fail-closed non-test abort, offline mode, and full simulated run."""

    def test_cli_list_suites_and_offline_mode(
        self, tmp_path: Any, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc_list = sfs.main(["--list-suites"])
        assert rc_list == 0
        out = capsys.readouterr().out
        for suite_name in ("SK-VER", "SK-INSPECT", "SK-GAQL", "SK-LIMITS", "SK-SIDECAR", "SK-CWD"):
            assert suite_name in out

        audit_log = tmp_path / "offline_skills_audit.jsonl"
        # Explicit tmp config + credentials: offline runs never read the developer's
        # real google-ads.yaml or tests/test_account_config.yaml.
        creds, cfg_path = _write_offline_fixtures(tmp_path)
        rc_off = sfs.main([
            "--offline",
            "--config",
            str(cfg_path),
            "--credentials-yaml",
            str(creds),
            "--audit-log",
            str(audit_log),
        ])
        assert rc_off == 0
        integrity = hal.verify_audit_log_integrity(str(audit_log))
        assert integrity["error_records"] == 0

    def test_non_test_account_fails_closed(self, tmp_path: Any) -> None:
        creds = tmp_path / "google-ads.yaml"
        creds.write_text(
            yaml.safe_dump({
                "client_id": "1234567890-abc.apps.googleusercontent.com",
                "client_secret": "secret",
                "refresh_token": "refresh",
                "use_proto_plus": True,
            }),
            encoding="utf-8",
        )
        audit_log = tmp_path / "non_test_skills_audit.jsonl"
        cfg = hal.load_test_account_config(
            customer_id_override="3202672097",
            credentials_yaml_override=str(creds),
        )
        results, _ = sfs.run_skills_functional_suite(
            cfg,
            audit_log_path=str(audit_log),
            suite_filter="create",
            client_factory=lambda _c, _p: _make_fake_live_client(is_test_account=False),
            print_output=False,
        )
        by_id = {r.test_id: r for r in results}
        assert by_id["SK-PF-03"].passed is False
        assert "FATAL_NON_TEST_ACCOUNT" in by_id["SK-PF-03"].details
        for create_id in ("SK-CREATE-01", "SK-CREATE-02", "SK-CREATE-03", "SK-CREATE-04", "SK-CREATE-05"):
            assert by_id[create_id].passed is False
            assert "FATAL_NON_TEST_ACCOUNT" in by_id[create_id].details

    def test_full_skills_suite_against_simulated_verified_test_account(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        shim_dir = str(tmp_path / "skills_shim")
        _write_fake_skills_shim(shim_dir)
        monkeypatch.setenv("_GADS_FAKE_SKILLS_SUBPROC", "1")

        creds = tmp_path / "google-ads.yaml"
        creds.write_text(
            yaml.safe_dump({
                "client_id": "1234567890-abc.apps.googleusercontent.com",
                "client_secret": "secret",
                "refresh_token": "refresh",
                "use_proto_plus": True,
            }),
            encoding="utf-8",
        )
        audit_log = tmp_path / "full_skills_sim_audit.jsonl"
        cfg = hal.load_test_account_config(
            customer_id_override="486-308-9361",
            login_customer_id_override="860-165-1289",
            credentials_yaml_override=str(creds),
        )
        results, audit = sfs.run_skills_functional_suite(
            cfg,
            audit_log_path=str(audit_log),
            suite_filter="all",
            client_factory=lambda _c, _p: _make_fake_live_client(is_test_account=True),
            extra_pythonpath=shim_dir,
            print_output=False,
        )
        failed = [r for r in results if not r.passed]
        assert failed == [], (
            "Skills functional suite failures: "
            + "; ".join(f"{r.test_id}: {r.details}" for r in failed)
        )
        assert {r.test_id for r in results} == {
            s.test_id for s in sfs._build_skill_test_specs()
        }
        integrity = hal.verify_audit_log_integrity(str(audit_log))
        assert integrity["error_records"] == 0
        assert audit.error_count == 0

    def test_offline_sandbox_never_copies_real_credentials(self, tmp_path: Any) -> None:
        creds, cfg_path = _write_offline_fixtures(tmp_path)
        cfg = hal.load_test_account_config(str(cfg_path), credentials_yaml_override=str(creds))
        audit = hal.FunctionalAuditLogger(log_path=str(tmp_path / "ctx_audit.jsonl"))
        offline_ctx = sfs.SkillsFunctionalContext(cfg, audit, offline_only=True)
        try:
            seeded = open(offline_ctx.sandbox_yaml, encoding="utf-8").read()
        finally:
            offline_ctx.close()
        assert _REAL_TOKEN_SENTINEL not in seeded
        assert "offline-refresh" in seeded

        online_ctx = sfs.SkillsFunctionalContext(cfg, audit, offline_only=False)
        try:
            online_seeded = open(online_ctx.sandbox_yaml, encoding="utf-8").read()
        finally:
            online_ctx.close()
        assert _REAL_TOKEN_SENTINEL in online_seeded

    def test_test_id_filter_respects_suite_filter(self, tmp_path: Any) -> None:
        creds, cfg_path = _write_offline_fixtures(tmp_path)
        cfg = hal.load_test_account_config(str(cfg_path), credentials_yaml_override=str(creds))
        results, _ = sfs.run_skills_functional_suite(
            cfg,
            audit_log_path=str(tmp_path / "filter_audit.jsonl"),
            suite_filter="limits",
            test_id_filter={"SK-LIMITS-03", "SK-GAQL-03"},
            offline_only=True,
            print_output=False,
        )
        # SK-GAQL-03 is outside --suite limits and must not run.
        assert [r.test_id for r in results] == ["SK-LIMITS-03"]
        assert results[0].passed, results[0].details

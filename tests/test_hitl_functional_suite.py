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

"""Unit and simulated-account integration tests for the Post-MCP HITL functional suite."""

from __future__ import annotations

import os
import stat
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
import hitl_policy_functional_suite as hpfs  # noqa: E402


def _write_fake_googleads_shim(shim_dir: str) -> None:
    """Creates a sitecustomize shim in `shim_dir` so subprocesses can test against a fake Test Account."""
    os.makedirs(shim_dir, exist_ok=True)
    shim_code = '''import importlib.abc
import importlib.machinery
import os
import sys
from types import SimpleNamespace

if os.environ.get("_GADS_FAKE_TEST_ACCOUNT_SUBPROC") == "1":
    def _patch_client_cls(ClientCls):
        if getattr(ClientCls, "_fake_patched", False):
            return
        from google.ads.googleads.errors import GoogleAdsException
        from google.auth.credentials import AnonymousCredentials
        import grpc

        class _FakeRpcError(grpc.RpcError):
            def code(self):
                return grpc.StatusCode.INVALID_ARGUMENT
            def details(self):
                return "Simulated negative budget error"

        orig_cls_get_service = ClientCls.get_service

        def _fake_cls_get_service(self, name, *args, **kwargs):
            svc = SimpleNamespace()
            if name == "GoogleAdsService":
                svc.search = lambda **kw: []
                svc.search_stream = lambda **kw: []
                svc.mutate = lambda request=None, **kw: SimpleNamespace(
                    request_id="req-fake-ga-mutate", mutate_operation_responses=[]
                )
                return svc
            if name == "CampaignBudgetService":
                def _mut_budgets(request=None, **kw):
                    ops = getattr(request, "operations", [])
                    for op in ops:
                        amt = getattr(getattr(op, "update", None), "amount_micros", 0)
                        if amt and int(amt) < 0:
                            failure = self.get_type("GoogleAdsFailure")
                            err = (
                                failure.errors.add()
                                if hasattr(failure.errors, "add")
                                else self.get_type("GoogleAdsError")
                            )
                            err.message = "Budget amount_micros cannot be negative."
                            if not hasattr(failure.errors, "add"):
                                failure.errors.append(err)
                            raise GoogleAdsException(
                                error=_FakeRpcError(),
                                call=_FakeRpcError(),
                                failure=failure,
                                request_id="req-neg-budget",
                            )
                    res = self.get_type("MutateCampaignBudgetsResponse")
                    item = (
                        res.results.add()
                        if hasattr(res.results, "add")
                        else self.get_type("MutateCampaignBudgetResult")
                    )
                    item.resource_name = "customers/4863089361/campaignBudgets/101"
                    if ops:
                        item.campaign_budget.amount_micros = int(ops[0].update.amount_micros or 5000000)
                    if not hasattr(res.results, "add"):
                        res.results.append(item)
                    return res
                svc.mutate_campaign_budgets = _mut_budgets
                return svc
            if name == "AdGroupCriterionService":
                svc.mutate_ad_group_criteria = lambda request=None, **kw: SimpleNamespace(
                    request_id="req-fake-agc", results=[SimpleNamespace(resource_name="customers/4863089361/adGroupCriteria/201~301")]
                )
                return svc
            if name == "LabelService":
                svc.mutate_labels = lambda request=None, **kw: SimpleNamespace(
                    request_id="req-fake-lbl", results=[SimpleNamespace(resource_name="customers/4863089361/labels/401")]
                )
                return svc
            if name == "AssetGroupListingGroupFilterService":
                svc.mutate_asset_group_listing_group_filters = lambda request=None, **kw: SimpleNamespace(
                    request_id="req-fake-pmax-lgf",
                    results=[
                        SimpleNamespace(resource_name="customers/4863089361/assetGroupListingGroupFilters/501~1"),
                        SimpleNamespace(resource_name="customers/4863089361/assetGroupListingGroupFilters/501~2"),
                        SimpleNamespace(resource_name="customers/4863089361/assetGroupListingGroupFilters/501~3"),
                    ],
                )
                return svc
            if name == "BillingSetupService":
                svc.mutate_billing_setup = lambda request=None, **kw: SimpleNamespace(request_id="req-bs")
                return svc
            if name == "CustomerUserAccessInvitationService":
                svc.mutate_customer_user_access_invitation = lambda request=None, **kw: SimpleNamespace(request_id="req-cuai")
                return svc
            return orig_cls_get_service(self, name, *args, **kwargs)

        def _fake_load_from_storage(cls, path=None, version="v26"):
            return cls(
                credentials=AnonymousCredentials(),
                developer_token="",
                version=version,
                use_proto_plus=True,
            )

        ClientCls.get_service = _fake_cls_get_service
        ClientCls.load_from_storage = classmethod(_fake_load_from_storage)
        ClientCls._fake_patched = True

    class _ReimportPatcher(importlib.abc.MetaPathFinder):
        _busy = False
        def find_spec(self, fullname, path, target=None):
            if self._busy or fullname != "google.ads.googleads.client":
                return None
            self._busy = True
            try:
                spec = importlib.machinery.PathFinder.find_spec(fullname, path)
                if spec and spec.loader:
                    orig_exec = spec.loader.exec_module
                    def _exec_and_patch(module):
                        orig_exec(module)
                        if hasattr(module, "GoogleAdsClient"):
                            _patch_client_cls(module.GoogleAdsClient)
                    spec.loader.exec_module = _exec_and_patch
                return spec
            finally:
                self._busy = False

    sys.meta_path.insert(0, _ReimportPatcher())

# Chain to next sitecustomize on sys.path (e.g. plugin config/sitecustomize.py)
import importlib.util, sys
_this_real = os.path.normcase(os.path.realpath(__file__))
_seen = getattr(sys, "_gads_chained_sitecustomizes", None)
if _seen is None:
    _seen = set()
    sys._gads_chained_sitecustomizes = _seen
_seen.add(_this_real)
for _p in list(sys.path):
    if not _p:
        continue
    _cand = os.path.join(_p, "sitecustomize.py")
    if os.path.isfile(_cand):
        _rc = os.path.normcase(os.path.realpath(_cand))
        if _rc not in _seen:
            _seen.add(_rc)
            _sp = importlib.util.spec_from_file_location("_next_sc", _cand)
            if _sp and _sp.loader:
                _m = importlib.util.module_from_spec(_sp)
                _sp.loader.exec_module(_m)
            break
'''
    with open(os.path.join(shim_dir, "sitecustomize.py"), "w", encoding="utf-8") as f:
        f.write(shim_code)


def _make_fake_live_client(
    *,
    is_test_account: bool = True,
    accessible_customers: list[str] | None = None,
    mutate_counter: list[str] | None = None,
) -> Any:
    """Builds an in-process fake GoogleAdsClient backed by real v26 Protobuf descriptors."""
    desc = GoogleAdsClient(
        credentials=AnonymousCredentials(), developer_token="", version="v26"
    )
    if accessible_customers is None:
        accessible_customers = ["customers/4863089361"]

    def _get_service(service_name: str, *_args: Any, **_kwargs: Any) -> Any:
        svc = SimpleNamespace()
        if service_name == "CustomerService":
            svc.list_accessible_customers = lambda: SimpleNamespace(
                resource_names=list(accessible_customers)
            )
            svc.mutate_customer = lambda request=None: SimpleNamespace(
                request_id="req-cust-1",
                result=SimpleNamespace(resource_name="customers/4863089361"),
            )
            return svc

        if service_name == "GoogleAdsService":
            def _search(customer_id: str = "", query: str = "", request: Any = None) -> list[Any]:
                q = query or getattr(request, "query", "")
                if "FROM customer " in q or q.endswith("FROM customer LIMIT 1"):
                    return [
                        SimpleNamespace(
                            customer=SimpleNamespace(
                                id=int(customer_id or 4863089361),
                                descriptive_name="Simulated Test Client",
                                test_account=is_test_account,
                                manager=False,
                                status="ENABLED",
                                currency_code="USD",
                            )
                        )
                    ]
                if "FROM campaign " in q:
                    return [
                        SimpleNamespace(
                            campaign=SimpleNamespace(
                                resource_name="customers/4863089361/campaigns/11",
                                name="HITL_Paused_Search",
                                status="PAUSED",
                            ),
                            campaign_budget=SimpleNamespace(
                                resource_name="customers/4863089361/campaignBudgets/101",
                                amount_micros=5_000_000,
                                explicitly_shared=False,
                            ),
                        )
                    ]
                if "FROM ad_group_ad " in q:
                    return [
                        SimpleNamespace(
                            ad_group_ad=SimpleNamespace(
                                resource_name="customers/4863089361/adGroupAds/201~1"
                            )
                        ),
                        SimpleNamespace(
                            ad_group_ad=SimpleNamespace(
                                resource_name="customers/4863089361/adGroupAds/201~2"
                            )
                        ),
                    ]
                if "FROM ad_group_criterion " in q:
                    return [
                        SimpleNamespace(
                            ad_group_criterion=SimpleNamespace(
                                resource_name="customers/4863089361/adGroupCriteria/201~301",
                                cpc_bid_micros=1_000_000,
                            )
                        )
                    ]
                if "FROM ad_group " in q:
                    return [
                        SimpleNamespace(
                            ad_group=SimpleNamespace(
                                id=201,
                                resource_name="customers/4863089361/adGroups/201",
                                name="HITL_AdGroup",
                                status="PAUSED",
                            )
                        )
                    ]
                if "FROM campaign_criterion " in q:
                    return [
                        SimpleNamespace(
                            campaign_criterion=SimpleNamespace(
                                resource_name="customers/4863089361/campaignCriteria/11~99"
                            )
                        )
                    ]
                if "FROM asset_group " in q:
                    return [
                        SimpleNamespace(
                            campaign=SimpleNamespace(
                                resource_name="customers/4863089361/campaigns/12"
                            ),
                            asset_group=SimpleNamespace(
                                resource_name="customers/4863089361/assetGroups/501",
                                id=501,
                            ),
                        )
                    ]
                if "FROM label " in q:
                    return [
                        SimpleNamespace(
                            label=SimpleNamespace(
                                resource_name="customers/4863089361/labels/401",
                                name="HITL_Label",
                            )
                        )
                    ]
                if "FROM shared_set " in q:
                    return [
                        SimpleNamespace(
                            shared_set=SimpleNamespace(
                                resource_name="customers/4863089361/sharedSets/601"
                            )
                        )
                    ]
                if "FROM conversion_action " in q:
                    return [
                        SimpleNamespace(
                            conversion_action=SimpleNamespace(
                                resource_name="customers/4863089361/conversionActions/701"
                            )
                        )
                    ]
                if "FROM user_list " in q:
                    return [
                        SimpleNamespace(
                            user_list=SimpleNamespace(
                                resource_name="customers/4863089361/userLists/801"
                            )
                        )
                    ]
                return []

            svc.search = _search
            svc.search_stream = lambda **_kw: []

            def _ga_mutate(request: Any = None) -> Any:
                if mutate_counter is not None:
                    mutate_counter.append("GoogleAdsService.mutate")
                return SimpleNamespace(
                    request_id="req-ga-mut", mutate_operation_responses=[]
                )

            svc.mutate = _ga_mutate
            return svc

        if service_name == "GoogleAdsFieldService":
            svc.search_google_ads_fields = lambda request=None: [
                SimpleNamespace(name="campaign.id", data_type="INT64")
            ]
            return svc

        if service_name == "CampaignBudgetService":
            def _mut_cb(request: Any = None) -> Any:
                if mutate_counter is not None:
                    mutate_counter.append("CampaignBudgetService.mutate_campaign_budgets")
                res = desc.get_type("MutateCampaignBudgetsResponse")
                item = res.results.add()
                item.resource_name = "customers/4863089361/campaignBudgets/101"
                if request and request.operations:
                    item.campaign_budget.amount_micros = int(
                        request.operations[0].update.amount_micros or 5_000_000
                    )
                return res

            svc.mutate_campaign_budgets = _mut_cb
            return svc

        # Generic stub for all other mutate / read-only services
        def _generic_attr(method_name: str) -> Any:
            def _rpc(request: Any = None, **_kw: Any) -> Any:
                if mutate_counter is not None and not method_name.startswith(
                    ("list_", "suggest_", "search_", "generate_", "quote_")
                ):
                    mutate_counter.append(f"{service_name}.{method_name}")
                return SimpleNamespace(
                    request_id=f"req-{service_name}-{method_name}",
                    results=[SimpleNamespace(resource_name="customers/4863089361/items/1")],
                )

            return _rpc

        class _DynamicStub:
            def __getattr__(self, item: str) -> Any:
                return _generic_attr(item)

        return _DynamicStub()

    return SimpleNamespace(
        enums=desc.enums,
        get_type=desc.get_type,
        get_service=_get_service,
    )


class TestAccountConfigAndAuditLogger:
    """Tests YAML configuration loading, JSONL audit schema, correlation, and error filtering."""

    def test_tracked_config_file_valid_and_clean(self) -> None:
        assert os.path.isfile(hal.DEFAULT_TEST_ACCOUNT_CONFIG_PATH)
        with open(hal.DEFAULT_TEST_ACCOUNT_CONFIG_PATH, "r", encoding="utf-8") as f:
            raw_text = f.read()
        parsed = yaml.safe_load(raw_text)
        assert "test_account" in parsed
        assert "execution" in parsed
        assert "fixtures" in parsed
        assert "safety" in parsed
        assert "audit_log" in parsed
        # Must include access notice and zero secrets / host paths
        assert "MUST have active OAuth 2.0 or" in raw_text
        assert "client_secret:" not in raw_text
        assert "refresh_token:" not in raw_text

    def test_customer_id_normalization_and_validation(self, tmp_path: Any) -> None:
        assert hal.normalize_customer_id("486-308-9361") == "4863089361"
        assert hal.is_valid_customer_id("486-308-9361") is True
        assert hal.is_valid_customer_id("12345678") is False
        assert hal.is_valid_customer_id("REPLACE_WITH_TEST_CUSTOMER_ID") is False

        bad_cfg = tmp_path / "bad_safety.yaml"
        bad_cfg.write_text(
            "test_account:\n  test_customer_id: '4863089361'\nsafety:\n  require_test_account: false\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="require_test_account"):
            hal.load_test_account_config(str(bad_cfg))

    def test_jsonl_audit_unique_ids_correlation_and_error_filtering(
        self, tmp_path: Any
    ) -> None:
        log_file = tmp_path / "audit_test.jsonl"
        logger = hal.FunctionalAuditLogger(
            log_path=str(log_file),
            target_customer_id="4863089361",
            login_customer_id="8601651289",
        )
        start_id = logger.log_suite_start({"env": "unit_test"})

        req1_id = logger.log_request(
            test_id="TC-01",
            suite="TC-CFG",
            action="CheckDefaultConfig",
            payload={"refresh_token": "super-secret-token", "key": "value"},
        )
        resp1_id = logger.log_response(
            request_record_id=req1_id,
            test_id="TC-01",
            suite="TC-CFG",
            status="OK",
            duration_ms=12.5,
            google_ads_request_id="gads-123",
            payload={"ok": True},
        )
        logger.log_test_result(
            test_id="TC-01",
            suite="TC-CFG",
            name="Passing test",
            passed=True,
            duration_ms=13.0,
            details="Passed cleanly",
            last_request_record_id=req1_id,
        )

        req2_id = logger.log_request(
            test_id="TC-02",
            suite="TC-RUN",
            action="CheckDrift",
            payload={"amount_micros": 50_000_000_000},
        )
        resp2_id = logger.log_response(
            request_record_id=req2_id,
            test_id="TC-02",
            suite="TC-RUN",
            status="MISMATCH",
            duration_ms=8.2,
            payload={"displayed": "$50.00/day"},
        )
        err_id = logger.log_error(
            test_id="TC-02",
            suite="TC-RUN",
            error_code="AssertionError",
            error_message="GAP-02 micro drift detected",
            request_record_id=req2_id,
            response_record_id=resp2_id,
            details={"client_secret": "must-not-leak"},
        )
        logger.log_test_result(
            test_id="TC-02",
            suite="TC-RUN",
            name="Failing test",
            passed=False,
            duration_ms=9.0,
            details="GAP-02 micro drift detected",
            last_request_record_id=req2_id,
            error_record_id=err_id,
        )
        logger.log_suite_summary(
            total_tests=2,
            passed_tests=1,
            failed_tests=1,
            duration_ms=22.0,
            failed_details=[{"test_id": "TC-02", "error_record_id": err_id}],
        )

        # Unknown request_record_id must be rejected
        with pytest.raises(ValueError, match="valid prior REQUEST record_id"):
            logger.log_response(
                request_record_id="non-existent-id",
                test_id="TC-03",
                suite="TC-RUN",
                status="OK",
            )

        if sys.platform != "win32":
            assert stat.S_IMODE(os.stat(log_file).st_mode) == 0o600

        raw_content = log_file.read_text(encoding="utf-8")
        assert "super-secret-token" not in raw_content
        assert "must-not-leak" not in raw_content
        assert "[REDACTED]" in raw_content

        stats = hal.verify_audit_log_integrity(str(log_file))
        assert stats["total_records"] == 9
        assert stats["unique_record_ids"] == 9
        assert stats["request_records"] == 2
        assert stats["response_records"] == 2
        assert stats["error_records"] == 1
        assert len({start_id, req1_id, resp1_id, req2_id, resp2_id, err_id}) == 6

        # Error filtering must return strictly the single ERROR record
        errors = hal.filter_error_records(str(log_file))
        assert len(errors) == 1
        assert errors[0]["record_id"] == err_id
        assert errors[0]["record_type"] == "ERROR"
        assert errors[0]["is_error"] is True
        assert errors[0]["request_record_id"] == req2_id
        assert errors[0]["response_record_id"] == resp2_id

        # CLI --filter-errors mode outputs strictly JSONL error lines
        rc = hpfs.main(["--filter-errors", str(log_file)])
        assert rc == 0

    def test_results_table_formatting_passed_and_failed(self) -> None:
        sample_results = [
            hal.TestCaseResult(
                test_id="TC-CFG-01",
                suite="TC-CFG",
                name="Default safe state",
                passed=True,
                duration_ms=10.0,
                details="OK",
            ),
            hal.TestCaseResult(
                test_id="TC-RUN-11",
                suite="TC-RUN",
                name="Payload-Bound Prompting vs. 1,000x Micro-Unit Drift",
                passed=False,
                duration_ms=15.0,
                details="GAP-02: CLI prose $50.00/day not cross-checked against 50B micros.",
                error_record_id="err-uuid-1234",
            ),
        ]
        rendered = hal.format_results_tables(
            sample_results,
            target_customer_id="4863089361",
            audit_log_path="/tmp/sample_audit.jsonl",
            error_record_count=1,
            total_duration_ms=25.0,
        )
        assert "Tests Passed" in rendered
        assert "Tests Failed" in rendered
        assert "TC-RUN-11" in rendered
        assert "GAP-02" in rendered
        assert "err-uuid-1234" in rendered

    def test_cli_list_suites_and_flag_aliases(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = hpfs.main(["--list-suites"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "TC-HOOK" in out
        assert "SCENARIOS" in out
        assert "72" in out

        parser = hpfs.build_arg_parser()
        parsed_upper = parser.parse_args(
            ["--suite", "TC-HOOK", "--dry-run-only", "--api-version", "v26"]
        )
        assert parsed_upper.suite == "tc-hook"
        assert parsed_upper.validate_only is True
        assert parsed_upper.api_version == "v26"

        cfg = hal.load_test_account_config(api_version_override="v26")
        assert cfg.api_version == "v26"


class TestSimulatedTestAccountSuiteExecution:
    """Verifies fail-closed test-account gates and end-to-end execution against simulated accounts."""

    def test_non_test_account_aborts_before_any_mutate_rpcs(self, tmp_path: Any) -> None:
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
        audit_log = tmp_path / "non_test_audit.jsonl"
        mutates_called: list[str] = []
        fake_prod_client = _make_fake_live_client(
            is_test_account=False, mutate_counter=mutates_called
        )

        cfg = hal.load_test_account_config(
            customer_id_override="3202672097",
            credentials_yaml_override=str(creds),
        )
        results, _ = hpfs.run_functional_suite(
            cfg,
            audit_log_path=str(audit_log),
            suite_filter="t1",
            client_factory=lambda _c, _p: fake_prod_client,
            print_output=False,
        )
        by_id = {r.test_id: r for r in results}
        assert by_id["PF-01"].passed is True
        assert by_id["PF-02"].passed is True
        assert by_id["PF-03"].passed is False
        assert "FATAL_NON_TEST_ACCOUNT" in by_id["PF-03"].details
        # Zero live mutations may be sent to a non-test account
        assert mutates_called == []

        errors = hal.filter_error_records(str(audit_log))
        assert any("FATAL_NON_TEST_ACCOUNT" in e["error_message"] for e in errors)
        hal.verify_audit_log_integrity(str(audit_log))

    def test_full_suite_against_simulated_verified_test_account(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        shim_dir = str(tmp_path / "shim")
        _write_fake_googleads_shim(shim_dir)
        monkeypatch.setenv("_GADS_FAKE_TEST_ACCOUNT_SUBPROC", "1")

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
        audit_log = tmp_path / "full_sim_audit.jsonl"
        fake_test_client = _make_fake_live_client(is_test_account=True)

        cfg = hal.load_test_account_config(
            customer_id_override="486-308-9361",
            login_customer_id_override="860-165-1289",
            credentials_yaml_override=str(creds),
        )
        results, audit = hpfs.run_functional_suite(
            cfg,
            audit_log_path=str(audit_log),
            suite_filter="all",
            client_factory=lambda _c, _p: fake_test_client,
            extra_pythonpath=shim_dir,
            print_output=False,
        )
        by_id = {r.test_id: r for r in results}

        # All 4 preflight gates pass on the verified test account
        for pf_id in ("PF-01", "PF-02", "PF-03", "PF-04"):
            assert by_id[pf_id].passed is True, f"{pf_id} failed: {by_id[pf_id].details}"

        # Representative implemented controls pass
        for pass_id in (
            "TC-CFG-01",
            "TC-CFG-02",
            "TC-CFG-03",
            "TC-CFG-04",
            "TC-HOOK-01",
            "TC-HOOK-02",
            "TC-HOOK-03",
            "TC-HOOK-06",
            "TC-HOOK-08",
            "TC-HOOK-09",
            "TC-RUN-01",
            "TC-RUN-02",
            "TC-RUN-03",
            "TC-RUN-05",
            "TC-RUN-06",
            "TC-AUD-03",
            "TC-A2A-01",
            "TC-A2A-02",
            "TC-A2A-03",
            "TC-T1-03",
            "TC-T2-01",
            "TC-T2-03",
            "TC-T3-03",
            "TC-T3-06",
            "TC-T4-01",
            "H1",
            "H3",
            "H4",
            "H10",
            "CLEANUP",
        ):
            assert by_id[pass_id].passed is True, f"{pass_id} failed: {by_id[pass_id].details}"

        # Known policy conformance gaps (GAP-01..GAP-07) and live v26 WebpageCondition bug (TC-T2-04)
        for gap_id in (
            "TC-CFG-05",
            "TC-HOOK-07",
            "TC-RUN-10",
            "TC-RUN-11",
            "TC-RUN-12",
            "TC-RUN-13",
            "TC-MSG-01",
            "TC-MSG-04",
            "TC-AUD-02",
            "TC-T2-04",
        ):
            assert by_id[gap_id].passed is False

        # Audit log integrity & error filtering match failed count
        integrity = hal.verify_audit_log_integrity(str(audit_log))
        failed_results = [r for r in results if not r.passed]
        error_records = hal.filter_error_records(str(audit_log))
        assert integrity["error_records"] == len(error_records)
        assert len(error_records) == len(failed_results)
        assert audit.error_count == len(failed_results)

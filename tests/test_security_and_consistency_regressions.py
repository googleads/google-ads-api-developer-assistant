"""Regression tests for code correctness, prompt/CLI consistency, and security guardrails."""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import time
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "google-ads-api-developer-assistant"
SKILLS_ROOT = PLUGIN_ROOT / "skills"

if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from config import config_init  # noqa: E402


def _load_module(rel_path: str, mod_name: str):
    full_path = PLUGIN_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(mod_name, full_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _set_fake_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    """Points os.path.expanduser("~") at `home` on all platforms.

    POSIX reads HOME. Windows (Python 3.8+) reads USERPROFILE and ignores HOME.
    """
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))


class TestHooksJsonAndGuardrailSecurity:
    """Verifies real hooks.json schema handling and PreToolUse guardrail bypass mitigations."""

    def test_real_hooks_json_toggles_and_has_no_relative_cwd_hijack(self, tmp_path):
        real_hooks_path = PLUGIN_ROOT / "hooks.json"
        raw_hooks = real_hooks_path.read_text(encoding="utf-8")
        parsed = json.loads(raw_hooks)

        # Real hooks.json defines top-level "config-init"
        assert "config-init" in parsed
        # Relative 'config/config_init.py' must not appear as an unanchored candidate
        for event_name in ("PreToolUse", "PostToolUse", "PreInvocation", "SessionStart"):
            entries = parsed["config-init"].get(event_name, [])
            for entry in entries:
                for hook in entry.get("hooks", []):
                    args_joined = " ".join(hook.get("args", []))
                    assert "next((f for f in ['config/config_init.py'" not in args_joined

        # File-write and MCP tools must be hooked in PreToolUse for agy
        matchers = [
            entry.get("matcher", "")
            for entry in parsed["config-init"].get("PreToolUse", [])
        ]
        assert any("write_file" in m and "edit_file" in m and "write_to_file" in m for m in matchers)
        assert any("call_mcp_tool" in m for m in matchers)

        # Toggling real hooks.json works on top-level "config-init"
        copied_hooks = tmp_path / "hooks.json"
        copied_hooks.write_text(raw_hooks, encoding="utf-8")

        assert config_init._is_hooks_json_disabled(str(copied_hooks)) is False
        assert config_init._set_hooks_json_enabled(str(copied_hooks), False) is True
        assert config_init._is_hooks_json_disabled(str(copied_hooks)) is True
        assert config_init._set_hooks_json_enabled(str(copied_hooks), True) is True
        assert config_init._is_hooks_json_disabled(str(copied_hooks)) is False

    def test_all_five_builtin_mutation_scripts_allowed_on_dry_run_and_denied_on_execute(
        self, monkeypatch
    ):
        monkeypatch.setenv("GOOGLE_ADS_EXECUTE_MUTATES", "execute_mutates = false")
        scripts = [
            SKILLS_ROOT / "execute-mutation" / "scripts" / "create_account.py",
            SKILLS_ROOT / "execute-mutation" / "scripts" / "create_campaign.py",
            SKILLS_ROOT / "execute-mutation" / "scripts" / "create_ad_group.py",
            SKILLS_ROOT / "execute-mutation" / "scripts" / "create_ad.py",
            SKILLS_ROOT / "pmax-listing-filter" / "scripts" / "create_pmax_webpage_filter.py",
        ]
        for script in scripts:
            dec_dry, rsn_dry = config_init.evaluate_mutation_guard(
                f"python3 {script} --dry-run"
            )
            assert dec_dry == "allow", f"{script.name} dry-run blocked: {rsn_dry}"

            dec_exec, _ = config_init.evaluate_mutation_guard(
                f"python3 {script} --execute"
            )
            assert dec_exec == "deny", f"{script.name} --execute was not blocked"

    def test_chained_linter_rest_curl_and_substring_readonly_bypasses_blocked(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("GOOGLE_ADS_EXECUTE_MUTATES", "execute_mutates = true")

        # 1. Chained linter + live mutation must NOT short-circuit to allow
        evil_script = tmp_path / "live_mutate.py"
        evil_script.write_text(
            "svc.mutate_campaigns(request=req)\n", encoding="utf-8"
        )
        dec_chain, _ = config_init.evaluate_mutation_guard(
            f"ruff check {evil_script} && python3 {evil_script} --execute"
        )
        assert dec_chain == "deny"

        # Pure linter chain still allowed
        dec_linter, _ = config_init.evaluate_mutation_guard(
            f"ruff check {evil_script} && pytest -q"
        )
        assert dec_linter == "allow"

        # 2. Substring spoof of READONLY_SKILL_SCRIPTS ("post_validate_gaql.py") is inspected
        spoof_ro = tmp_path / "post_validate_gaql.py"
        spoof_ro.write_text(
            "campaign_service.mutate_campaigns(request=req)\n", encoding="utf-8"
        )
        dec_spoof, _ = config_init.evaluate_mutation_guard(f"python3 {spoof_ro}")
        assert dec_spoof == "deny"

        # 3. Direct curl REST mutation to googleads.googleapis.com is denied
        dec_curl, rsn_curl = config_init.evaluate_mutation_guard(
            "curl -X POST https://googleads.googleapis.com/v26/customers/123/campaigns:mutate -d '{}'"
        )
        assert dec_curl == "deny"
        assert rsn_curl is not None and "Direct REST/HTTP" in rsn_curl

        # 4. Constructor keyword CampaignOperation(remove=...) and OfflineUserDataJobService are caught
        dec_kw_del, rsn_kw_del = config_init.evaluate_mutation_guard(
            'python3 -c "op = CampaignOperation(remove=\'customers/1/campaigns/2\')"'
        )
        assert dec_kw_del == "deny"
        assert rsn_kw_del is not None and "DELETION PROHIBITED" in rsn_kw_del

        dec_udj, _ = config_init.evaluate_mutation_guard(
            'python3 -c "job_svc.add_offline_user_data_job_operations(request=req)"'
        )
        assert dec_udj == "deny"

        # 5. Relative script path resolved via workspace_cwd
        rel_dir = tmp_path / "ws" / "saved" / "code"
        rel_dir.mkdir(parents=True)
        (rel_dir / "rel_mut.py").write_text(
            "svc.mutate_ad_groups(request=req)\n", encoding="utf-8"
        )
        dec_ws, _ = config_init.evaluate_mutation_guard(
            "python3 saved/code/rel_mut.py",
            workspace_cwd=str(tmp_path / "ws"),
        )
        assert dec_ws == "deny"

    def test_handle_hook_blocks_protected_file_writes_and_malformed_tool_json(
        self, monkeypatch, capsys
    ):
        monkeypatch.setattr(config_init, "is_plugin_enabled", lambda **kw: True)
        monkeypatch.setattr(
            config_init, "sync_and_set_config_kv", lambda **kw: "/tmp/fake-google-ads.yaml"
        )

        # 1. Direct write to last_dry_run.json -> deny
        fake_stdin_deny = io.StringIO(
            json.dumps(
                {
                    "toolCall": {
                        "name": "write_to_file",
                        "args": {"TargetFile": "/ws/saved/data/last_dry_run.json"},
                    }
                }
            )
        )
        monkeypatch.setattr(sys, "stdin", fake_stdin_deny)
        config_init.handle_hook()
        out_deny = json.loads(capsys.readouterr().out)
        assert out_deny["decision"] == "deny"

        # 2. Direct write to financial_limits -> force_ask
        fake_stdin_ask = io.StringIO(
            json.dumps(
                {
                    "toolCall": {
                        "name": "replace_file_content",
                        "args": {"TargetFile": "/ws/config/financial_limits"},
                    }
                }
            )
        )
        monkeypatch.setattr(sys, "stdin", fake_stdin_ask)
        config_init.handle_hook()
        out_ask = json.loads(capsys.readouterr().out)
        assert out_ask["decision"] == "force_ask"

        # 3. Malformed toolCall JSON -> fail closed (deny)
        fake_stdin_bad = io.StringIO('{"toolCall": {"name": "run_command", BROKEN')
        monkeypatch.setattr(sys, "stdin", fake_stdin_bad)
        config_init.handle_hook()
        out_bad = json.loads(capsys.readouterr().out)
        assert out_bad["decision"] == "deny"

    def test_legacy_parsers_strip_comments_and_sync_preserves_login_cid_without_sunset_token(
        self, tmp_path
    ):
        # Ruby comments ignored and integer login_customer_id parsed
        rb_cfg = tmp_path / "google_ads_config.rb"
        rb_cfg.write_text(
            '# c.client_id = "commented_out_id"\n'
            'c.client_id = "active_rb_id"\n'
            "c.login_customer_id = 1234567890\n",
            encoding="utf-8",
        )
        parsed_rb = config_init.parse_ruby_config(str(rb_cfg))
        assert parsed_rb["client_id"] == "active_rb_id"
        assert parsed_rb["login_customer_id"] == "1234567890"

        # INI comments ignored
        ini_cfg = tmp_path / "google_ads_php.ini"
        ini_cfg.write_text(
            '; clientId = "old_ini"\nclientId = "active_ini" ; inline comment\n',
            encoding="utf-8",
        )
        assert config_init.parse_ini_config(str(ini_cfg))["client_id"] == "active_ini"

        # .NET UTF-8 BOM + XML comments + entities handled
        xml_cfg = tmp_path / "App.config"
        xml_cfg.write_bytes(
            b'\xef\xbb\xbf<configuration><!-- <add key="OAuth2ClientId" value="commented"/> -->'
            b'<add key="OAuth2ClientId" value="a&amp;b"/></configuration>'
        )
        assert config_init.parse_dotnet_config(str(xml_cfg))["client_id"] == "a&b"

        # sync_and_set_config_kv preserves existing login_customer_id when syncing new OAuth credentials
        src_yaml = tmp_path / "src_google_ads.yaml"
        src_yaml.write_text(
            'client_id: "new_oauth_client"\n',
            encoding="utf-8",
        )
        cfg_dir = tmp_path / "dest_cfg"
        cfg_dir.mkdir()
        (cfg_dir / "google-ads.yaml").write_text(
            'client_id: "old_oauth_client"\nlogin_customer_id: "9876543210"\n',
            encoding="utf-8",
        )
        out_yaml = Path(
            config_init.sync_and_set_config_kv(
                source_yaml=str(src_yaml), config_dir=str(cfg_dir)
            )
        ).read_text(encoding="utf-8")
        assert 'client_id: "new_oauth_client"' in out_yaml
        assert 'login_customer_id: "9876543210"' in out_yaml


class TestFinancialLimitsAndHitlRunnerRegressions:
    """Verifies NaN/inf/negative/int64 limit handling, proto-plus enum serialization, and receipt checks."""

    def test_nan_inf_negative_and_int64_precision_in_financial_limits(
        self, tmp_path, monkeypatch
    ):
        sfl = _load_module(
            "skills/execute-mutation/scripts/set_financial_limits.py", "sfl_reg"
        )
        rm = _load_module(
            "skills/execute-mutation/scripts/run_mutation.py", "rm_reg"
        )

        for bad_val in ("nan", "NaN", "inf", "-inf", "Infinity", -1, float("nan"), float("inf")):
            with pytest.raises(ValueError):
                sfl.parse_and_validate_limit_amount(
                    "ConversionValueRuleService.value", bad_val
                )

        # Exact 64-bit integer precision > 2^53 preserved
        precise_micros = 9_007_199_254_740_993
        parsed = sfl.parse_financial_limits(
            f"CampaignBudgetService.amount_micros = {precise_micros}\n"
            "ConversionValueRuleService.value = nan\n"
        )
        assert parsed["CampaignBudgetService.amount_micros"] == precise_micros
        assert parsed["ConversionValueRuleService.value"] == 0.0

        # Negative and NaN observed amounts in RPC payloads are blocked even when limit > 0
        fin_file = tmp_path / "financial_limits"
        fin_file.write_text("GoalService.additional_value = 100.0\n", encoding="utf-8")
        monkeypatch.setenv("GOOGLE_ADS_FINANCIAL_LIMITS_FILE", str(fin_file))

        ok_neg, err_neg, _ = rm.check_financial_transaction_limits(
            rpc_calls=[
                {
                    "service": "GoalService",
                    "method": "mutate_goals",
                    "request_payload": {
                        "operations": [{"update": {"additional_value": -25.0}}]
                    },
                }
            ]
        )
        assert ok_neg is False
        assert "negative" in err_neg.lower() or "limit" in err_neg.lower()

        ok_nan, _, _ = rm.check_financial_transaction_limits(
            rpc_calls=[
                {
                    "service": "GoalService",
                    "method": "mutate_goals",
                    "request_payload": {
                        "operations": [{"update": {"additional_value": float("nan")}}]
                    },
                }
            ]
        )
        assert ok_nan is False

    def test_proto_plus_enum_removed_and_response_content_type_hash_normalization(self):
        rm = _load_module(
            "skills/execute-mutation/scripts/run_mutation.py", "rm_enum_reg"
        )

        class _FakeProtoPlusMsg:
            @classmethod
            def to_dict(cls, instance, use_integers_for_enums=True):
                return {"status": 4 if use_integers_for_enums else "REMOVED"}

        serialized = rm._serialize_rpc_object(_FakeProtoPlusMsg())
        assert serialized["status"] == "REMOVED"
        ok_del, err_del, _ = rm.check_prohibited_deletion_mutation(
            rpc_calls=[
                {
                    "service": "CampaignService",
                    "method": "mutate_campaigns",
                    "request_payload": {"operations": [{"update": serialized}]},
                }
            ]
        )
        assert ok_del is False
        assert "REMOVED" in err_del

        # response_content_type does not alter canonical request SHA-256
        req_dry = {"customer_id": "123", "validate_only": True, "operations": [{"create": {"name": "C1"}}]}
        req_live = {
            "customer_id": "123",
            "validate_only": False,
            "response_content_type": "MUTABLE_RESOURCE",
            "operations": [{"create": {"name": "C1"}}],
        }
        h1 = rm.compute_mutate_request_sha256("CampaignService", "mutate_campaigns", req_dry)
        h2 = rm.compute_mutate_request_sha256("CampaignService", "mutate_campaigns", req_live)
        h3 = config_init._compute_canonical_request_sha256(
            "CampaignService", "mutate_campaigns", req_live
        )
        assert h1 == h2 == h3

    def test_future_receipt_timestamp_rejected(self, tmp_path, monkeypatch):
        rm = _load_module(
            "skills/execute-mutation/scripts/run_mutation.py", "rm_ts_reg"
        )
        ws = tmp_path / "ws"
        receipt_dir = ws / "saved" / "data"
        receipt_dir.mkdir(parents=True)
        receipt_file = receipt_dir / "last_dry_run.json"
        receipt_file.write_text(
            json.dumps(
                {
                    "status": "DRY_RUN_PASSED",
                    "timestamp": time.time() + 3600,
                    "customer_id": "1234567890",
                    "operation_summary": "Update Campaign",
                    "before_state": "PAUSED",
                    "after_state": "ENABLED",
                    "consequences": ["Campaign starts serving"],
                    "reversibility": "REVERSIBLE",
                }
            ),
            encoding="utf-8",
        )
        ok_hook, msg_hook, _ = config_init._verify_dry_run_receipt_for_hook(
            workspace_cwd=str(ws)
        )
        assert ok_hook is False
        assert "future" in msg_hook.lower()

        monkeypatch.chdir(ws)
        ok_rm, msg_rm, _ = rm.load_and_verify_receipt()
        assert ok_rm is False
        assert "future" in msg_rm.lower()


class TestDiagnosticMutationSidecarAndSyncRegressions:
    """Verifies fixes across inspect_object, validate_gaql, conversion scripts, sync_client_libs, and server.py."""

    def test_inspect_object_enum_wrapper_scalar_types_nested_class_and_name_flag(self):
        res_enum = subprocess.run(
            [
                sys.executable,
                str(SKILLS_ROOT / "inspect-object" / "scripts" / "inspect_object.py"),
                "--name",
                "CampaignStatusEnum",
                "--api_version",
                "v26",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res_enum.returncode == 0
        assert "ENABLED = 2" in res_enum.stdout
        assert "PAUSED = 3" in res_enum.stdout

        res_nested = subprocess.run(
            [
                sys.executable,
                str(SKILLS_ROOT / "inspect-object" / "scripts" / "inspect_object.py"),
                "--name",
                "Campaign.NetworkSettings",
                "--api_version",
                "v26",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert res_nested.returncode == 0
        assert "target_google_search" in res_nested.stdout
        assert "bool" in res_nested.stdout.lower()

        # Verify descriptor integer type mapping (9 -> STRING, 3 -> INT64) when client is provided
        io_mod = _load_module("skills/inspect-object/scripts/inspect_object.py", "io_reg")
        mock_client = MagicMock()

        class _FakeProtoWrapper:
            @staticmethod
            def pb(_inst):
                return MagicMock(DESCRIPTOR=desc)

        f_str = MagicMock()
        f_str.name = "resource_name"
        f_str.type = 9
        f_str.label = 1
        f_str.is_repeated = False
        f_str.message_type = None
        f_str.enum_type = None
        desc = MagicMock(spec=["name", "fields", "enum_types", "nested_types"])
        desc.name = "Campaign"
        desc.fields = [f_str]
        desc.enum_types = []
        desc.nested_types = []
        mock_client.get_type.return_value = _FakeProtoWrapper()
        buf = io.StringIO()
        with patch.object(sys, "stdout", buf):
            io_mod.inspect_protobuf("Campaign", "v26", client=mock_client)
        assert "STRING" in buf.getvalue()

    def test_validate_gaql_date_equality_masked_literals_and_selective_invalidation(
        self, tmp_path
    ):
        vg = _load_module("skills/validate-gaql/scripts/validate_gaql.py", "vg_reg")
        mock_client = MagicMock()

        # 1. Valid click_view date equality query (from get_recent_gclids.py) passes
        vg.validate_gaql(
            "1234567890",
            "26",
            "SELECT click_view.gclid, segments.date FROM click_view WHERE segments.date = '2026-08-19' LIMIT 10",
            client=mock_client,
            use_cache=False,
        )

        # 2. String literals containing 'Shop Now' or 'Gold or Silver' pass
        vg.validate_gaql(
            "1234567890",
            "v26",
            "SELECT campaign.id, campaign.name FROM campaign WHERE campaign.name = 'Shop Now Gold or Silver'",
            client=mock_client,
            use_cache=False,
        )

        # 3. segments.day_of_week without finite date range passes
        vg.validate_gaql(
            "1234567890",
            "v26",
            "SELECT campaign.id, segments.day_of_week FROM campaign",
            client=mock_client,
            use_cache=False,
        )

        # 4. Non-date BETWEEN with segments.date selected fails static check
        with pytest.raises(SystemExit):
            vg.validate_gaql(
                "1234567890",
                "v26",
                "SELECT campaign.id, segments.date FROM campaign WHERE metrics.clicks BETWEEN 10 AND 100",
                client=mock_client,
                use_cache=False,
            )

        # 5. invalidate_gaql_cache(query=..., api_version=None) only removes matching query
        cache_file = tmp_path / "gaql_cache.json"
        vg.set_cached_validation("SELECT campaign.id FROM campaign", "v25", cache_path=str(cache_file))
        vg.set_cached_validation("SELECT ad_group.id FROM ad_group", "v25", cache_path=str(cache_file))
        removed = vg.invalidate_gaql_cache(
            query="SELECT campaign.id FROM campaign",
            api_version=None,
            cache_path=str(cache_file),
        )
        assert removed == 1
        assert vg.get_cached_validation("SELECT ad_group.id FROM ad_group", "v25", cache_path=str(cache_file)) is not None

    def test_conversion_csv_bom_timestamp_pii_and_gclid_date_injection(
        self, tmp_path
    ):
        vcu = _load_module(
            "skills/troubleshoot-conversions/scripts/validate_conversion_upload.py",
            "vcu_reg",
        )
        grg = _load_module(
            "skills/troubleshoot-conversions/scripts/get_recent_gclids.py",
            "grg_reg",
        )

        # UTF-8 BOM valid CSV passes
        bom_csv = tmp_path / "bom_valid.csv"
        bom_csv.write_bytes(
            b"\xef\xbb\xbfgclid,conversion_time,conversion_value,currency_code\n"
            b"EAIaIQobChMI123,2026-08-19 12:30:00+00:00,49.99,USD\n"
        )
        vcu.validate_conversion_csv(str(bom_csv), "v26")

        # Garbage time suffix or raw email in hashed_email fails
        bad_csv = tmp_path / "bad_time.csv"
        bad_csv.write_text(
            "gclid,conversion_time,conversion_value,hashed_email\n"
            "EAIaIQobChMI123,2026-08-19 GARBAGE,10.0,user@example.com\n",
            encoding="utf-8",
        )
        with pytest.raises(SystemExit):
            vcu.validate_conversion_csv(str(bad_csv), "v26")

        # get_recent_gclids blocks date injection
        with pytest.raises(SystemExit):
            grg.get_recent_gclids(MagicMock(), "123-456-7890", "2026-08-19' OR 1=1--")

    def test_sync_client_libs_repo_root_tar_slip_url_scheme_and_prerelease_order(
        self, tmp_path, monkeypatch
    ):
        scl = _load_module(
            "skills/sync-client-libs/scripts/sync_client_libs.py", "scl_reg"
        )

        # Pre-release sorts lower than final release
        assert scl.VersionFallback("26.0.0-rc1") < scl.VersionFallback("26.0.0")

        # check_assistant_repo resolves git repo root (with .git) rather than wiping plugin subdir
        called_git_paths = []
        monkeypatch.setattr(
            scl,
            "fetch_github_latest_release",
            lambda slug: ("v99.0.0", "https://github.com/googleads/repo/archive/v99.tar.gz"),
        )
        monkeypatch.setattr(
            scl,
            "update_codebase_via_git",
            lambda path, tag: called_git_paths.append(path) or True,
        )
        orig_archive = scl.update_codebase_via_archive
        monkeypatch.setattr(
            scl,
            "update_codebase_via_archive",
            lambda *a, **kw: pytest.fail("Must not use archive sync inside a git checkout!"),
        )
        res = scl.check_assistant_repo(check_only=False, force=True)
        assert res is not None and res["status"] == "UPDATED"
        assert called_git_paths == [str(REPO_ROOT)]

        # Reject non-HTTPS archive URLs
        assert (
            orig_archive(
                str(tmp_path / "lib"),
                "googleads/google-ads-python",
                "v1.0.0",
                "file:///etc/passwd",
            )
            is False
        )

        # Tar Slip path traversal rejected
        evil_tar = tmp_path / "evil.tar.gz"
        with tarfile.open(evil_tar, "w:gz") as tf:
            info = tarfile.TarInfo(name="../../escaped.txt")
            payload = b"evil"
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))
        extract_target = tmp_path / "extract"
        extract_target.mkdir()
        with tarfile.open(evil_tar, "r:gz") as tf:
            with pytest.raises(ValueError):
                scl._safe_extract_tar(tf, str(extract_target))

    def test_sidecar_strict_bool_csrf_auth_and_mcp_stdio_protocol(self, monkeypatch):
        srv = _load_module(
            "sidecars/google-ads-a2a-service/server.py", "srv_sec_reg"
        )

        # 1. String "false" must NEVER evaluate to True
        assert srv._strict_bool("false") is False
        assert srv._strict_bool("False") is False
        assert srv._strict_bool(False) is False
        assert srv._strict_bool(True) is True
        assert srv._strict_bool("true") is True

        handler = srv.A2AHandler.__new__(srv.A2AHandler)
        blocked = handler.handle_execute_mutation(
            "t-str-false",
            {"user_confirmed": "false", "script_path": "nonexistent.py"},
        )
        assert blocked["status"] == "HITL_BLOCKED"

        # 2. CSRF Origin, DNS-rebinding Host, Content-Type, and Bearer auth enforced
        def _post_with_headers(headers: dict, body_dict: dict) -> tuple[int, dict]:
            h = srv.A2AHandler.__new__(srv.A2AHandler)
            h.path = "/v1/a2a/tasks"
            raw = json.dumps(body_dict).encode("utf-8")
            h.headers = {"Content-Length": str(len(raw)), **headers}
            h.rfile = io.BytesIO(raw)
            h._send_json = MagicMock()
            h.do_POST()
            return h._send_json.call_args[0]

        code_host, _ = _post_with_headers(
            {"Host": "attacker.example.com", "Content-Type": "application/json"},
            {"intent": "GAQL_VALIDATE", "payload": {}},
        )
        assert code_host == 403

        code_origin, _ = _post_with_headers(
            {"Origin": "https://evil.example", "Content-Type": "application/json"},
            {"intent": "GAQL_VALIDATE", "payload": {}},
        )
        assert code_origin == 403

        code_ct, _ = _post_with_headers(
            {"Content-Type": "text/plain"},
            {"intent": "GAQL_VALIDATE", "payload": {}},
        )
        assert code_ct == 415

        monkeypatch.setenv("A2A_AUTH_TOKEN", "secret-test-token-123")
        code_unauth, _ = _post_with_headers(
            {"Content-Type": "application/json"},
            {"intent": "GAQL_VALIDATE", "payload": {}},
        )
        assert code_unauth == 401

        code_auth, body_auth = _post_with_headers(
            {
                "Content-Type": "application/json",
                "Authorization": "Bearer secret-test-token-123",
            },
            {
                "task_id": "t-ok",
                "intent": "GAQL_VALIDATE",
                "payload": {
                    "query": "SELECT campaign.id FROM campaign",
                    "api_version": "v26",
                },
            },
        )
        assert code_auth == 200
        assert body_auth["status"] == "COMPLETED"

        # 3. MCP JSON-RPC 2.0 Stdio framing test
        mcp_in = "\n".join(
            [
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
                json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {
                            "name": "inspect_object",
                            "arguments": {"object_name": "CampaignStatusEnum", "api_version": "v26"},
                        },
                    }
                ),
            ]
        ) + "\n"
        out_buf = io.StringIO()
        with patch.object(sys, "stdin", io.StringIO(mcp_in)), patch.object(
            sys, "stdout", out_buf
        ):
            srv.run_mcp_stdio_server()

        responses = [json.loads(line) for line in out_buf.getvalue().splitlines() if line.strip()]
        assert [r["id"] for r in responses] == [1, 2, 3]
        assert "tools" in responses[1]["result"]
        assert len(responses[1]["result"]["tools"]) >= 8
        assert responses[2]["result"]["isError"] is False

    def test_prompt_and_doc_consistency_contracts(self):
        # 1. inspect_object prompt files must use --object_name, not broken --name
        for rel in (
            "skills/inspect-object/SKILL.md",
            "commands/inspect-object.md",
        ):
            text = (PLUGIN_ROOT / rel).read_text(encoding="utf-8")
            assert "--object_name" in text
            assert "inspect_object.py --name " not in text

        # 2. execute-mutation template must not use broken .ResponseContentType.MUTABLE_RESOURCE
        exec_skill = (PLUGIN_ROOT / "skills/execute-mutation/SKILL.md").read_text(
            encoding="utf-8"
        )
        assert "ResponseContentTypeEnum.ResponseContentType" not in exec_skill
        assert "ResponseContentTypeEnum.MUTABLE_RESOURCE" in exec_skill

        # 3. PMax prompt/rule files must use listing_source = WEBPAGE, not obsolete vertical = WEBPAGE
        for rel in (
            "skills/pmax-listing-filter/SKILL.md",
            "commands/pmax-filter.md",
            "rules/AGENTS.md",
            "README.md",
        ):
            text = (PLUGIN_ROOT / rel).read_text(encoding="utf-8")
            assert "vertical = WEBPAGE" not in text

        # 4. assistant-tutorial must reflect 6-Category Consequence Matrix with prohibited deletion
        tutorial = (PLUGIN_ROOT / "skills/assistant-tutorial/SKILL.md").read_text(
            encoding="utf-8"
        )
        assert "5-Category Consequence Matrix" not in tutorial


class TestComprehensiveBranchCoverageAndEdgeCases:
    """Exercises newly added validation, atomic mutate, AST, MCP, and sync branches across all modules."""

    def test_create_campaign_atomic_mutate_dates_channels_removed_and_limits(
        self, tmp_path, monkeypatch
    ):
        cc = _load_module(
            "skills/execute-mutation/scripts/create_campaign.py", "cc_branch_reg"
        )

        # 1. Atomic GoogleAdsService.mutate with PMax, EU political ads, YYYYMMDD & full datetime
        mock_client = MagicMock()
        gads_svc = MagicMock()
        op_resp0 = MagicMock()
        op_resp0.campaign_budget_result.resource_name = (
            "customers/1234567890/campaignBudgets/777"
        )
        op_resp1 = MagicMock()
        op_resp1.campaign_result.resource_name = "customers/1234567890/campaigns/888"
        gads_svc.mutate.return_value = MagicMock(
            mutate_operation_responses=[op_resp0, op_resp1], results=[]
        )
        camp_svc = MagicMock()
        camp_res = MagicMock()
        camp_res.resource_name = "customers/1234567890/campaigns/887"
        camp_svc.mutate_campaigns.return_value = MagicMock(results=[camp_res])
        svc_lookup = {"GoogleAdsService": gads_svc, "CampaignService": camp_svc}
        mock_client.get_service.side_effect = lambda name: svc_lookup[name]
        res = cc.create_campaign(
            customer_id="123-456-7890",
            advertising_channel_type="PERFORMANCE_MAX",
            status="PAUSED",
            start_date="20261201",
            end_date="2026-12-31 23:59:59",
            contains_eu_political_advertising=True,
            budget_name="Custom PMax Budget",
            validate_only=False,
            client=mock_client,
            json_output=True,
            budget_resource_name="customers/1234567890/campaignBudgets/555",
        )
        assert res["status"] == "CREATED"

        # Atomic mutate path (without pre-existing budget_resource_name) on dry-run and results fallback
        fin_file = tmp_path / "fin_limits"
        fin_file.write_text("CampaignBudgetService.amount_micros = 50000000\n", encoding="utf-8")
        monkeypatch.setenv("GOOGLE_ADS_FINANCIAL_LIMITS_FILE", str(fin_file))
        res_atomic = cc.create_campaign(
            customer_id="1234567890",
            advertising_channel_type="PERFORMANCE_MAX",
            status="ENABLED",
            start_date="2026-12-01",
            end_date="2026-12-31",
            validate_only=False,
            client=mock_client,
            json_output=True,
        )
        assert res_atomic["budget_resource_name"] == "customers/1234567890/campaignBudgets/777"
        assert res_atomic["campaign_resource_name"] == "customers/1234567890/campaigns/888"

        # Fallback results attribute on mutate_resp
        r0 = MagicMock()
        r0.resource_name = "customers/1234567890/campaignBudgets/778"
        r1 = MagicMock()
        r1.resource_name = "customers/1234567890/campaigns/889"
        gads_svc.mutate.return_value = MagicMock(
            mutate_operation_responses=[], results=[r0, r1]
        )
        res_atomic2 = cc.create_campaign(
            customer_id="1234567890",
            validate_only=True,
            client=mock_client,
        )
        assert res_atomic2["campaign_resource_name"] == "customers/1234567890/campaigns/889"

        # 2. Validation rejections: REMOVED, UNKNOWN, bad dates, end < start, bad budget RN, financial limit block
        for bad_kwargs in (
            {"status": "REMOVED"},
            {"status": "UNKNOWN"},
            {"advertising_channel_type": "UNSPECIFIED"},
            {"budget_delivery_method": "UNKNOWN"},
            {"budget_resource_name": "invalid/rn"},
            {"start_date": "2026-99-99"},
            {"start_date": "2026-12-31", "end_date": "2026-12-01"},
        ):
            with pytest.raises(SystemExit):
                cc.create_campaign(customer_id="1234567890", client=mock_client, **bad_kwargs)

        # Standalone live financial limit block (exit code 2)
        fin_file.write_text("CampaignBudgetService.amount_micros = 1000000\n", encoding="utf-8")
        with pytest.raises(SystemExit) as exc_lim:
            cc.create_campaign(
                customer_id="1234567890",
                budget_amount_micros=9_000_000,
                validate_only=False,
                client=mock_client,
            )
        assert exc_lim.value.code == 2

    def test_create_account_ad_group_pmax_cids_and_ext_version_branches(
        self, tmp_path, monkeypatch, capsys
    ):
        ca = _load_module("skills/execute-mutation/scripts/create_account.py", "ca_br")
        cag = _load_module("skills/execute-mutation/scripts/create_ad_group.py", "cag_br")
        pmax = _load_module(
            "skills/pmax-listing-filter/scripts/create_pmax_webpage_filter.py", "pmax_br"
        )
        cids = _load_module(
            "skills/get-cids-under-mcc/scripts/get_cids_under_mcc.py", "cids_br"
        )
        glav = _load_module(
            "skills/ext-version/scripts/get_latest_api_version.py", "glav_br"
        )

        mock_client = MagicMock()

        # create_account: UNSPECIFIED role & missing GoogleAdsClient
        with pytest.raises(SystemExit):
            ca.create_account_under_mcc(
                manager_customer_id="1234567890",
                access_role="UNSPECIFIED",
                client=mock_client,
            )
        monkeypatch.setattr(ca, "GoogleAdsClient", None)
        with pytest.raises(SystemExit):
            ca.create_account_under_mcc(manager_customer_id="1234567890", client=None)

        # create_ad_group: REMOVED, UNKNOWN, full resource name in campaign_id, and live financial limit block
        for bad_st in ("REMOVED", "UNKNOWN"):
            with pytest.raises(SystemExit):
                cag.create_ad_group(
                    customer_id="1234567890",
                    campaign_id="222",
                    status=bad_st,
                    client=mock_client,
                )
        fin_file = tmp_path / "ag_limits"
        fin_file.write_text("AdGroupService.cpc_bid_micros = 500000\n", encoding="utf-8")
        monkeypatch.setenv("GOOGLE_ADS_FINANCIAL_LIMITS_FILE", str(fin_file))
        with pytest.raises(SystemExit) as exc_ag:
            cag.create_ad_group(
                customer_id="1234567890",
                campaign_id="customers/1234567890/campaigns/222",
                cpc_bid_micros=2_000_000,
                validate_only=False,
                client=mock_client,
            )
        assert exc_ag.value.code == 2

        # create_pmax_webpage_filter: invalid inputs, missing SDK, and --json output
        for bad_args in (
            ("", "999", "/blog"),
            ("1234567890", "", "/blog"),
            ("1234567890", "999", "   "),
        ):
            with pytest.raises(SystemExit):
                pmax.create_pmax_webpage_filter(*bad_args, "v26", client=mock_client)

        pmax_svc = MagicMock()
        pmax_res = MagicMock()
        pmax_res.resource_name = "customers/123/assetGroupListingGroupFilters/999~1"
        pmax_svc.mutate_asset_group_listing_group_filters.return_value = MagicMock(
            results=[pmax_res]
        )
        mock_client.get_service.return_value = pmax_svc
        capsys.readouterr()
        pmax_out = pmax.create_pmax_webpage_filter(
            "123-456-7890",
            "999",
            "/checkout",
            "v26",
            validate_only=True,
            client=mock_client,
            json_output=True,
        )
        assert pmax_out["filter_type"] == "UNIT_EXCLUDED"

        # get_cids_under_mcc: ChildAccountRow attributes + combined --json and --save_csv + non-TTY missing CID
        monkeypatch.chdir(tmp_path)
        fake_row = MagicMock()
        fake_row.customer_client.id = 5556667770
        fake_row.customer_client.level = 1
        fake_row.customer_client.manager = False
        fake_row.customer_client.descriptive_name = "Acme Leaf Account"
        fake_row.customer_client.status.name = "ENABLED"
        fake_stream_batch = MagicMock(results=[fake_row])
        cids_client = MagicMock()
        cids_client.get_service.return_value.search_stream.return_value = [fake_stream_batch]
        rows = cids.get_cids_under_mcc("123-456-7890", "v26", client=cids_client)
        assert rows[0] == ("5556667770", 1, False)
        assert rows[0].descriptive_name == "Acme Leaf Account"

        monkeypatch.setattr(cids, "get_cids_under_mcc", lambda cid, ver, client=None: rows)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "get_cids_under_mcc.py",
                "--customer-id",
                "1234567890",
                "--api-version",
                "v26",
                "--json",
                "--save_csv",
            ],
        )
        cids.main()
        assert (tmp_path / "saved" / "data" / "cids_under_mcc_1234567890.csv").is_file()

        fake_non_tty = MagicMock()
        fake_non_tty.isatty.return_value = False
        monkeypatch.setattr(sys, "stdin", fake_non_tty)
        monkeypatch.setattr(sys, "argv", ["get_cids_under_mcc.py", "--api-version", "v26"])
        with pytest.raises(SystemExit):
            cids.main()

        # get_latest_api_version: --no-update aliases --active (read-only); --installed
        # detects installed versions and exits 1 cleanly when detection raises.
        monkeypatch.setattr(sys, "argv", ["get_latest_api_version.py", "--no-update"])
        glav.main()
        monkeypatch.setattr(sys, "argv", ["get_latest_api_version.py", "--installed"])
        monkeypatch.setattr(
            glav,
            "detect_latest_api_version",
            lambda **kw: (_ for _ in ()).throw(RuntimeError("no versions found")),
        )
        with pytest.raises(SystemExit) as exc_glav:
            glav.main()
        assert exc_glav.value.code == 1

    def test_inspect_object_gaql_conversions_and_sync_branches(
        self, tmp_path, monkeypatch, capsys
    ):
        io_mod = _load_module("skills/inspect-object/scripts/inspect_object.py", "io_br")
        vg = _load_module("skills/validate-gaql/scripts/validate_gaql.py", "vg_br")
        vcu = _load_module(
            "skills/troubleshoot-conversions/scripts/validate_conversion_upload.py", "vcu_br"
        )
        tc = _load_module(
            "skills/troubleshoot-conversions/scripts/troubleshoot_conversions.py", "tc_br"
        )
        grg = _load_module(
            "skills/troubleshoot-conversions/scripts/get_recent_gclids.py", "grg_br"
        )
        scl = _load_module(
            "skills/sync-client-libs/scripts/sync_client_libs.py", "scl_br"
        )

        # 1. inspect_object: regex fallback on syntax-broken file, MapField AST, nested descriptor, unknown type exit
        broken_py = tmp_path / "broken_proto.py"
        broken_py.write_text(
            "class BrokenMsg:\n"
            "    id: int = proto.Field(proto.INT64, number=1)\n"
            "    tags: str = proto.RepeatedField(proto.STRING, number=2)\n"
            "def broken_syntax(:\n",
            encoding="utf-8",
        )
        assert io_mod.inspect_from_source(str(broken_py), "BrokenMsg") is True

        map_py = tmp_path / "map_proto.py"
        map_py.write_text(
            "class MapHolder:\n"
            '    """Docstring Note: ignored."""\n'
            "    labels: dict[str, str] = proto.MapField(proto.STRING, proto.STRING, number=1)\n",
            encoding="utf-8",
        )
        capsys.readouterr()
        assert io_mod.inspect_from_source(str(map_py), "MapHolder") is True
        assert "[MAP" in capsys.readouterr().out

        # Verify get_available_types falls back to installed site-packages when client_libs is absent
        orig_isdir = io_mod.os.path.isdir
        with patch.object(
            io_mod.os.path,
            "isdir",
            side_effect=lambda p: False if "client_libs" in str(p) else orig_isdir(p),
        ):
            io_mod._AVAILABLE_TYPES_CACHE.clear()
            sp_types = io_mod.get_available_types("v26")
            assert "CampaignStatusEnum" in sp_types
            assert "Campaign" in sp_types

        bad_client = MagicMock()
        bad_client.get_type.side_effect = ValueError("Unknown type")
        with pytest.raises(SystemExit):
            io_mod.inspect_protobuf("CompletelyNonExistentXyzType", "v26", client=bad_client)

        # 2. validate_gaql: GoogleAdsFieldService metadata query, change_status LIMIT 0 error, customer_id cache key
        mock_gads_client = MagicMock()
        vg.validate_gaql(
            "1234567890",
            "v26",
            "SELECT name, selectable WHERE name LIKE 'campaign.%'",
            client=mock_gads_client,
            use_cache=False,
        )
        mock_gads_client.get_service.assert_called_with("GoogleAdsFieldService")

        with pytest.raises(SystemExit):
            vg.validate_gaql(
                "1234567890",
                "v26",
                "SELECT change_status.resource_name FROM change_status "
                "WHERE change_status.last_change_date_time DURING LAST_7_DAYS LIMIT 0",
                client=mock_gads_client,
                use_cache=False,
            )

        k_a = vg.compute_gaql_cache_key("SELECT campaign.id FROM campaign", "v26", "111")
        k_b = vg.compute_gaql_cache_key("SELECT campaign.id FROM campaign", "v26", "222")
        assert k_a != k_b

        corrupt_cache = tmp_path / "corrupt_cache.json"
        corrupt_cache.write_text(
            json.dumps({"bad_entry": "not-a-dict", "bad_ts": {"timestamp": "not-float", "query": "Q"}}),
            encoding="utf-8",
        )
        assert vg.get_cached_validation("Q", "v26", cache_path=str(corrupt_cache)) is None
        vg.invalidate_gaql_cache(api_version="v26", cache_path=str(corrupt_cache))

        # 3. validate_conversion_upload: click_time ordering, gbraid, bad sha256, negative value, bad currency
        multi_err_csv = tmp_path / "multi_err.csv"
        multi_err_csv.write_text(
            "gbraid,click_time,conversion_date_time,conversion_value,currency_code,hashed_phone_number\n"
            "gb_valid_123,2026-08-19 14:00:00+00:00,2026-08-19 12:00:00,10.0,USD," + ("a" * 64) + "\n"
            "bad,not-a-click-time,2026-08-19 15:00:00+00:00,-5.0,US,abcd1234\n",
            encoding="utf-8",
        )
        with pytest.raises(SystemExit):
            vcu.validate_conversion_csv(str(multi_err_csv), "v26")

        # 4. get_recent_gclids & troubleshoot_conversions: rows, customer scoping, pending exclusion
        gclid_row = MagicMock()
        gclid_row.click_view.gclid = "EAIaIQobChMI999"
        gclid_row.segments.date = "2026-08-19"
        gclid_row.ad_group.id = 444
        gclid_client = MagicMock()
        gclid_client.get_service.return_value.search_stream.return_value = [
            MagicMock(results=[gclid_row])
        ]
        grg.get_recent_gclids(gclid_client, "123-456-7890", "2026-08-19")

        rep_dir = tmp_path / "reports"
        rep_dir.mkdir()
        (rep_dir / "conversion_troubleshooting_report_100.txt").write_text(
            "Customer ID: 9999999999\n1. Executive Summary\nOld other customer\n2. Primary Errors\n",
            encoding="utf-8",
        )
        assert tc.merge_previous_findings(str(rep_dir), customer_id="1234567890") == []

        # 5. sync_client_libs: .sync_version, Ruby version.rb, Java parent POM, PHP ChangeLog, tar extract, pip show
        php_dir = tmp_path / "libs" / "google-ads-php"
        php_dir.mkdir(parents=True)
        (php_dir / "composer.json").write_text('{"name": "googleads/google-ads-php"}', encoding="utf-8")
        (php_dir / "ChangeLog.md").write_text("## 28.1.0\n- Release notes\n", encoding="utf-8")
        assert scl.detect_installed_version("google-ads-php", str(php_dir)) == "28.1.0"

        rb_dir = tmp_path / "libs" / "google-ads-ruby"
        (rb_dir / "lib" / "google" / "ads" / "google_ads").mkdir(parents=True)
        (rb_dir / "lib" / "google" / "ads" / "google_ads" / "version.rb").write_text(
            'module Google\n  VERSION = "31.2.0"\nend\n', encoding="utf-8"
        )
        assert scl.detect_installed_version("google-ads-ruby", str(rb_dir)) == "31.2.0"

        java_dir = tmp_path / "libs" / "google-ads-java"
        java_dir.mkdir(parents=True)
        (java_dir / "pom.xml").write_text(
            "<project><parent><version>1.0.0</version></parent><version>34.0.0</version></project>",
            encoding="utf-8",
        )
        assert scl.detect_installed_version("google-ads-java", str(java_dir)) == "34.0.0"

        # Valid archive extract + sync_directories + shorthand --library python
        good_tar = tmp_path / "good.tar.gz"
        with tarfile.open(good_tar, "w:gz") as tf:
            payload = b'version = "36.0.0"\n'
            ti = tarfile.TarInfo(name="google-ads-python-36.0.0/pyproject.toml")
            ti.size = len(payload)
            tf.addfile(ti, io.BytesIO(payload))
        ext_dir = tmp_path / "good_ext"
        ext_dir.mkdir()
        with tarfile.open(good_tar, "r:gz") as tf:
            scl._safe_extract_tar(tf, str(ext_dir))
        dst_sync = tmp_path / "dst_sync"
        dst_sync.mkdir()
        assert scl.sync_directories(str(ext_dir / "google-ads-python-36.0.0"), str(dst_sync)) is True

        # Shorthand library filter ("python")
        py_dir = tmp_path / "libs" / "google-ads-python"
        py_dir.mkdir(parents=True)
        (py_dir / ".sync_version").write_text("36.0.0\n", encoding="utf-8")
        monkeypatch.setattr(
            scl, "fetch_github_latest_release", lambda slug: ("v36.0.0", "https://github.com/t.tar.gz")
        )
        monkeypatch.setattr(
            scl, "detect_system_package_version", lambda pkg="google-ads": ("36.0.0", ["/sp"])
        )
        monkeypatch.setattr(
            scl, "fetch_latest_pypi_python_version", lambda *a, **kw: "36.0.0"
        )
        filtered = scl.process_client_libs(
            client_libs_dir=str(tmp_path / "libs"),
            check_only=True,
            target_library="python",
            include_assistant=False,
        )
        assert [r["codebase"] for r in filtered] == ["google-ads-python"]

    def test_sidecar_mcp_all_tools_http_methods_limits_and_first_prompt_dedup(
        self, tmp_path, monkeypatch, capsys
    ):
        srv = _load_module(
            "sidecars/google-ads-a2a-service/server.py", "srv_cov_reg"
        )

        # 1. Auth token file generation & reuse
        fake_home = tmp_path / "home"
        (fake_home / ".gemini" / "config" / "plugins" / "google-ads-api-developer-assistant").mkdir(
            parents=True
        )
        monkeypatch.delenv("A2A_AUTH_TOKEN", raising=False)
        _set_fake_home(monkeypatch, fake_home)
        tok1 = srv._resolve_a2a_auth_token()
        tok2 = srv._resolve_a2a_auth_token()
        assert len(tok1) == 64 and tok1 == tok2

        # 2. HTTP 405 on PUT/DELETE/TRACE, 413 on oversized body, GET /health?ts=1
        h = srv.A2AHandler.__new__(srv.A2AHandler)
        h._send_json = MagicMock()
        h.path = "/health?ts=1"
        h.do_GET()
        assert h._send_json.call_args[0][0] == 200
        for method_fn in (h.do_PUT, h.do_DELETE, h.do_TRACE):
            h._send_json.reset_mock()
            method_fn()
            assert h._send_json.call_args[0][0] == 405

        h._send_json.reset_mock()
        h.path = "/v1/a2a/tasks"
        h.headers = {"Content-Length": str(5 * 1024 * 1024), "Content-Type": "application/json"}
        h.rfile = io.BytesIO(b"{}")
        h.do_POST()
        assert h._send_json.call_args[0][0] == 413

        # 3. Live CREATE_CAMPAIGN blocked by REMOVED status and by financial limit (with audit record)
        audit_log = tmp_path / "a2a_audit.jsonl"
        fin_file = tmp_path / "a2a_fin"
        fin_file.write_text("CampaignBudgetService.amount_micros = 1000000\n", encoding="utf-8")
        monkeypatch.setenv("GOOGLE_ADS_MUTATION_AUDIT_LOG", str(audit_log))
        monkeypatch.setenv("GOOGLE_ADS_FINANCIAL_LIMITS_FILE", str(fin_file))
        monkeypatch.setenv("GOOGLE_ADS_EXECUTE_MUTATES", "execute_mutates = true")

        res_rem = h.handle_create_campaign(
            "t-rem",
            {"customer_id": "1234567890", "status": "REMOVED"},
        )
        assert res_rem["status"] == "HITL_BLOCKED"

        res_lim = h.handle_create_campaign(
            "t-lim",
            {
                "customer_id": "1234567890",
                "budget_amount_micros": 9_000_000,
                "execute": True,
                "user_confirmed": True,
            },
        )
        assert res_lim["status"] == "HITL_BLOCKED"
        assert audit_log.is_file()

        # 4. MCP stdio ping, unknown method, and tool calls across intents
        mcp_reqs = [
            {"jsonrpc": "2.0", "id": 10, "method": "ping"},
            {"jsonrpc": "2.0", "id": 11, "method": "unknown/method"},
            {
                "jsonrpc": "2.0",
                "id": 12,
                "method": "tools/call",
                "params": {
                    "name": "gaql_validate",
                    "arguments": {
                        "query": "SELECT campaign.id FROM campaign WHERE campaign.name = 'A OR B'",
                        "api_version": "v26",
                    },
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 13,
                "method": "tools/call",
                "params": {
                    "name": "inspect_object",
                    "arguments": {
                        "resource_name": "Campaign",
                        "api_version": "v26",
                    },
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 14,
                "method": "tools/call",
                "params": {"name": "generate_code", "arguments": {}},
            },
        ]
        mcp_out = io.StringIO()
        with patch.object(
            sys, "stdin", io.StringIO("\n".join(json.dumps(r) for r in mcp_reqs) + "\n")
        ), patch.object(sys, "stdout", mcp_out):
            srv.run_mcp_stdio_server()
        mcp_resps = [json.loads(ln) for ln in mcp_out.getvalue().splitlines() if ln.strip()]
        assert mcp_resps[0]["result"] == {}
        assert mcp_resps[1]["error"]["code"] == -32601
        assert mcp_resps[2]["result"]["isError"] is False
        assert mcp_resps[3]["result"]["isError"] is False
        assert "error" in mcp_resps[4]

        # 5. config_init: _should_run_first_prompt_parity deduplication & Claude updatedInput
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        assert config_init._should_run_first_prompt_parity({"isSubagent": True}) is False
        assert config_init._should_run_first_prompt_parity({"executionNum": 2}) is False
        conv_key = f"test-conv-{time.time_ns()}"
        assert config_init._should_run_first_prompt_parity({"conversationId": conv_key, "invocationNum": 1}) is True
        assert config_init._should_run_first_prompt_parity({"conversationId": conv_key, "invocationNum": 1}) is False

        monkeypatch.setattr(config_init, "is_plugin_enabled", lambda **kw: True)
        monkeypatch.setattr(
            config_init, "sync_and_set_config_kv", lambda **kw: "/tmp/fake-ads.yaml"
        )
        claude_hook_in = io.StringIO(
            json.dumps(
                {
                    "tool_name": "Bash",
                    "tool_input": {
                        "command": "# comment line\npython3 skills/ext-version/scripts/get_extension_version.py"
                    },
                }
            )
        )
        monkeypatch.setattr(sys, "stdin", claude_hook_in)
        capsys.readouterr()
        config_init.handle_hook()
        claude_out = json.loads(capsys.readouterr().out)
        # Claude Code reads only hookSpecificOutput; rewrites go in updatedInput.
        hso = claude_out["hookSpecificOutput"]
        assert hso["hookEventName"] == "PreToolUse"
        assert hso.get("permissionDecision") in (None, "allow")
        assert "&& #" not in hso["updatedInput"]["command"]

    def test_remaining_coverage_and_edge_cases(self, tmp_path, monkeypatch):
        from types import SimpleNamespace
        import urllib.error

        pmax = _load_module(
            "skills/pmax-listing-filter/scripts/create_pmax_webpage_filter.py", "pmax_rem"
        )
        grg = _load_module(
            "skills/troubleshoot-conversions/scripts/get_recent_gclids.py", "grg_rem"
        )
        tc = _load_module(
            "skills/troubleshoot-conversions/scripts/troubleshoot_conversions.py", "tc_rem"
        )
        scl = _load_module(
            "skills/sync-client-libs/scripts/sync_client_libs.py", "scl_rem"
        )
        srv = _load_module(
            "sidecars/google-ads-a2a-service/server.py", "srv_rem"
        )

        fake_home = tmp_path / "isolated_home"
        fake_home.mkdir()
        _set_fake_home(monkeypatch, fake_home)
        monkeypatch.delenv("GOOGLE_ADS_CONFIGURATION_FILE_PATH", raising=False)
        monkeypatch.chdir(tmp_path)

        # 1. get_recent_gclids: _get_config_path fallback, empty CID, invalid calendar day, generic Exception
        monkeypatch.setattr(
            config_init,
            "sync_and_set_config_kv",
            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("no yaml")),
        )
        assert grg._get_config_path().endswith("google-ads.yaml")
        for bad_cid, bad_dt in (("", "2026-08-19"), ("1234567890", "2026-02-30")):
            with pytest.raises(SystemExit):
                grg.get_recent_gclids(MagicMock(), bad_cid, bad_dt)
        boom_gclid_client = MagicMock()
        boom_gclid_client.get_service.side_effect = RuntimeError("rpc boom")
        with pytest.raises(SystemExit):
            grg.get_recent_gclids(boom_gclid_client, "1234567890", "2026-08-19")

        # 2. create_pmax_webpage_filter: _get_config_path fallback, url_contains-only class, missing SDK
        assert pmax._get_config_path().endswith("google-ads.yaml")

        class _UrlContainsCond:
            url_contains: str = ""

        class _FakeDim:
            WebpageCondition = _UrlContainsCond

        class _CustomPmaxClient:
            enums = SimpleNamespace()

            @staticmethod
            def get_type(_name: str):
                return _FakeDim()

        cond_uc = pmax._build_webpage_condition(_CustomPmaxClient(), "/clearance")
        assert cond_uc.url_contains == "/clearance"

        monkeypatch.setattr(pmax, "GoogleAdsClient", None)
        with pytest.raises(SystemExit):
            pmax.create_pmax_webpage_filter("1234567890", "999", "/clearance", "v26", client=None)

        # 3. troubleshoot_conversions: _get_config_path, run_query generic Exception, enum & alert extractors
        assert tc._get_config_path().endswith("google-ads.yaml")
        err_bucket: list[str] = []
        boom_tc_client = MagicMock()
        boom_tc_client.get_service.return_value.search_stream.side_effect = RuntimeError("stream err")
        assert tc.run_query(boom_tc_client, "1234567890", "SELECT 1", errors_out=err_bucket) == []
        assert any("stream err" in e for e in err_bucket)

        raw_proto_parent = SimpleNamespace(
            status=2,
            DESCRIPTOR=SimpleNamespace(
                fields_by_name={
                    "status": SimpleNamespace(
                        enum_type=SimpleNamespace(
                            values_by_number={2: SimpleNamespace(name="ENABLED")}
                        )
                    )
                }
            ),
        )
        assert tc._extract_enum_label(raw_proto_parent, "status") == "ENABLED"
        assert tc._extract_alert_error_name(SimpleNamespace(error=None)) == "UNKNOWN"

        class _PbWrappedErr:
            conversion_upload_error = SimpleNamespace(name="EXPIRED_EVENT")

            @staticmethod
            def pb(_inst):
                return SimpleNamespace(WhichOneof=lambda _g: "conversion_upload_error")

        assert tc._extract_alert_error_name(SimpleNamespace(error=_PbWrappedErr())) == "EXPIRED_EVENT"
        raw_which_err = SimpleNamespace(
            WhichOneof=lambda _g: "click_not_found",
            click_not_found=SimpleNamespace(name="CLICK_NOT_FOUND"),
        )
        assert tc._extract_alert_error_name(SimpleNamespace(error=raw_which_err)) == "CLICK_NOT_FOUND"
        assert (
            tc._extract_alert_error_name(SimpleNamespace(error=SimpleNamespace(name="FALLBACK_ERR")))
            == "FALLBACK_ERR"
        )

        # 4. config_init: global-dir routing in write_assistant_config, set_plugin_enabled targets, legacy syncs
        monkeypatch.undo()
        home2 = tmp_path / "home2"
        agy_p = home2 / ".gemini" / "config" / "plugins" / "google-ads-api-developer-assistant"
        claude_mkt = home2 / ".claude" / "plugins" / "google-ads-assistant-local"
        claude_p = claude_mkt / "plugins" / "google-ads-api-developer-assistant"
        (agy_p / "config").mkdir(parents=True)
        (claude_p / "config").mkdir(parents=True)
        (claude_mkt / ".claude-plugin").mkdir(parents=True)
        _set_fake_home(monkeypatch, home2)
        monkeypatch.delenv("GOOGLE_ADS_ASSISTANT_CONFIG_DIR", raising=False)

        written_global = config_init.write_assistant_config({"api_version": "v26"})
        assert str(home2) in written_global
        assert str(home2) in config_init.set_plugin_enabled(
            False, config_dir=None, sync_global=True, target_type="claude"
        )
        assert str(home2) in config_init.set_plugin_enabled(
            True, config_dir=None, sync_global=True, target_type="agy"
        )
        env_cfg_override = tmp_path / "env_cfg_dir" / "config"
        env_cfg_override.mkdir(parents=True)
        monkeypatch.setenv("GOOGLE_ADS_ASSISTANT_CONFIG_DIR", str(env_cfg_override))
        assert str(env_cfg_override) in config_init.set_plugin_enabled(
            True, config_dir=None, sync_global=True, target_type="all"
        )
        monkeypatch.delenv("GOOGLE_ADS_ASSISTANT_CONFIG_DIR", raising=False)

        # sync_and_set_config_kv direct legacy file extensions (.ini, .rb, .properties, App.config)
        src_dir = tmp_path / "legacy_srcs"
        src_dir.mkdir()
        (src_dir / "ads.ini").write_text('clientId = "cid_ini"\n', encoding="utf-8")
        (src_dir / "ads.rb").write_text('c.client_id = "cid_rb"\n', encoding="utf-8")
        (src_dir / "ads.properties").write_text("api.googleads.clientId=cid_prop\n", encoding="utf-8")
        (src_dir / "App.config").write_text(
            '<configuration><add key="OAuth2ClientId" value="cid_net"/></configuration>',
            encoding="utf-8",
        )
        for idx, fname in enumerate(("ads.ini", "ads.rb", "ads.properties", "App.config")):
            out_d = tmp_path / f"synced_{idx}"
            out_y = config_init.sync_and_set_config_kv(
                source_yaml=str(src_dir / fname), config_dir=str(out_d), version="4.1.0"
            )
            assert Path(out_y).is_file()

        # 5. server.py: handle_execute_mutation run_script branches + live CREATE_ACCOUNT/AD_GROUP/AD
        monkeypatch.setenv("GOOGLE_ADS_EXECUTE_MUTATES", "execute_mutates = true")
        monkeypatch.setenv("GOOGLE_ADS_MUTATION_AUDIT_LOG", str(tmp_path / "srv_rem_audit.jsonl"))
        fin_ok = tmp_path / "srv_rem_fin"
        fin_ok.write_text(
            "CampaignBudgetService.amount_micros = 50000000\n"
            "AdGroupService.cpc_bid_micros = 5000000\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("GOOGLE_ADS_FINANCIAL_LIMITS_FILE", str(fin_ok))

        h = srv.A2AHandler.__new__(srv.A2AHandler)
        saved_code = tmp_path / "saved" / "code"
        saved_code.mkdir(parents=True, exist_ok=True)
        script_f = saved_code / "mut_exec_demo.py"
        script_f.write_text("print('ok')\n", encoding="utf-8")

        fake_rm = MagicMock()
        fake_rm.is_execute_mutates_enabled.return_value = True
        fake_rm.load_and_verify_receipt.return_value = (
            True,
            "verified",
            {"customer_id": "1234567890", "operation_summary": "Demo"},
        )
        with patch.object(srv, "spec_from_file_location") as mock_spec_fn, patch.object(
            srv, "module_from_spec", return_value=fake_rm
        ):
            mock_spec_fn.return_value = SimpleNamespace(loader=SimpleNamespace(exec_module=lambda _m: None))
            miss_res = h.handle_execute_mutation(
                "t-miss-script",
                {
                    "user_confirmed": True,
                    "confirmation_summary": "Approved demo",
                    "run_script": True,
                    "script_path": str(saved_code / "missing.py"),
                },
            )
            assert miss_res["status"] == "VALIDATION_FAILED"

            with patch.object(
                srv.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=0, stdout="mutated ok", stderr=""),
            ):
                ok_exec = h.handle_execute_mutation(
                    "t-ok-script",
                    {
                        "user_confirmed": True,
                        "confirmation_summary": "Approved demo",
                        "run_script": True,
                        "script_path": str(script_f),
                    },
                )
                assert ok_exec["status"] == "COMPLETED"

            with patch.object(
                srv.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=2, stdout="", stderr="limit hit"),
            ):
                lim_exec = h.handle_execute_mutation(
                    "t-lim-script",
                    {
                        "user_confirmed": True,
                        "confirmation_summary": "Approved demo",
                        "run_script": True,
                        "script_path": str(script_f),
                    },
                )
                assert lim_exec["status"] == "HITL_BLOCKED"

        monkeypatch.setenv("GOOGLE_ADS_MUTATION_RECEIPT_PATH", str(tmp_path / "srv_rem_receipt.json"))
        monkeypatch.setenv("GOOGLE_ADS_ALLOW_TIER1_FINANCIAL_MUTATES", "true")
        mock_live_client = MagicMock()
        mock_live_client.get_service.return_value.create_customer_client.return_value = SimpleNamespace(
            resource_name="customers/9998887770"
        )
        mock_live_client.get_service.return_value.mutate_ad_groups.return_value = SimpleNamespace(
            results=[SimpleNamespace(resource_name="customers/1234567890/adGroups/333")]
        )
        mock_live_client.get_service.return_value.mutate_ad_group_ads.return_value = SimpleNamespace(
            results=[SimpleNamespace(resource_name="customers/1234567890/adGroupAds/333~444")]
        )
        # Dry-run writes signed receipt before live create_account
        assert (
            h.handle_create_account(
                "t-ca-dry",
                {
                    "manager_customer_id": "1234567890",
                    "validate_only": True,
                    "client": mock_live_client,
                },
            )["status"]
            == "COMPLETED"
        )
        assert (
            h.handle_create_account(
                "t-ca-live",
                {
                    "manager_customer_id": "1234567890",
                    "execute": True,
                    "user_confirmed": True,
                    "client": mock_live_client,
                },
            )["status"]
            == "COMPLETED"
        )
        assert (
            h.handle_create_ad_group(
                "t-cag-bad-bid",
                {"customer_id": "1234567890", "campaign_id": "111", "cpc_bid_micros": "not-an-int"},
            )["status"]
            == "FAILED"
        )
        assert (
            h.handle_create_ad_group(
                "t-cag-dry",
                {
                    "customer_id": "1234567890",
                    "campaign_id": "111",
                    "cpc_bid_micros": 250_000,
                    "validate_only": True,
                    "client": mock_live_client,
                },
            )["status"]
            == "COMPLETED"
        )
        assert (
            h.handle_create_ad_group(
                "t-cag-live",
                {
                    "customer_id": "1234567890",
                    "campaign_id": "111",
                    "cpc_bid_micros": 250_000,
                    "execute": True,
                    "user_confirmed": True,
                    "client": mock_live_client,
                },
            )["status"]
            == "COMPLETED"
        )
        assert (
            h.handle_create_ad(
                "t-cad-dry",
                {
                    "customer_id": "1234567890",
                    "ad_group_id": "333",
                    "final_urls": "https://example.com",
                    "headlines": ["Headline One", "Headline Two", "Headline Three"],
                    "descriptions": ["Description One.", "Description Two."],
                    "validate_only": True,
                    "client": mock_live_client,
                },
            )["status"]
            == "COMPLETED"
        )
        assert (
            h.handle_create_ad(
                "t-cad-live",
                {
                    "customer_id": "1234567890",
                    "ad_group_id": "333",
                    "final_urls": "https://example.com",
                    "headlines": ["Headline One", "Headline Two", "Headline Three"],
                    "descriptions": ["Description One.", "Description Two."],
                    "execute": True,
                    "user_confirmed": True,
                    "client": mock_live_client,
                },
            )["status"]
            == "COMPLETED"
        )

        # 6. sync_client_libs: VersionFallback ops, discover errors, GitHub 429->ls-remote, PyPI & pip upgrade
        vf1 = scl.VersionFallback("1.0.0")
        vf2 = scl.VersionFallback("2.0.0")
        assert (vf1 <= vf2) and (vf2 > vf1) and (vf2 >= vf1)
        assert (vf1 == scl.VersionFallback("1.0.0")) and not (vf1 == "1.0.0")
        assert str(vf1) == "1.0.0"

        with pytest.raises(FileNotFoundError):
            scl.discover_client_libs_dir(str(tmp_path / "does_not_exist"))

        monkeypatch.setenv("GITHUB_TOKEN", "ghs_unit_test_token")
        assert "Authorization" in scl._build_github_headers()

        def _raise_http_404_then_429(req, timeout=15):
            code = 404 if "/releases/latest" in req.full_url else 429
            raise urllib.error.HTTPError(req.full_url, code, "rate limit", {}, None)

        with patch.object(scl.urllib.request, "urlopen", side_effect=_raise_http_404_then_429), patch.object(
            scl.subprocess,
            "run",
            return_value=SimpleNamespace(
                returncode=0,
                stdout="aaa\trefs/tags/v35.0.0\nbbb\trefs/tags/v36.0.0-rc1\nccc\trefs/tags/v36.0.0\n",
                stderr="",
            ),
        ):
            gh_tag, gh_tar = scl.fetch_github_latest_release("googleads/google-ads-python")
            assert gh_tag == "v36.0.0" and gh_tar is None

        # sync_directories preserving config/google-ads.yaml and symlinks
        src_s = tmp_path / "sync_src_dir"
        dst_s = tmp_path / "sync_dst_dir"
        src_s.mkdir()
        (dst_s / "config").mkdir(parents=True)
        (dst_s / "config" / "google-ads.yaml").write_text("login_customer_id: '111'\n", encoding="utf-8")
        (src_s / "README.md").write_text("hi\n", encoding="utf-8")
        try:
            (src_s / "link_readme").symlink_to("README.md")
        except OSError:
            pass  # Windows needs Developer Mode or admin rights to create symlinks.
        assert scl.sync_directories(str(src_s), str(dst_s)) is True
        assert (dst_s / "config" / "google-ads.yaml").is_file()

        # PyPI fetch + cache hit + upgrade_system_package invalid version & failure
        class _FakeUrlResp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            @staticmethod
            def read():
                return b'{"info": {"version": "37.2.0"}}'

        with patch.object(scl.urllib.request, "urlopen", return_value=_FakeUrlResp()):
            assert scl.fetch_latest_pypi_python_version("unit-test-gads-pkg", force=True) == "37.2.0"
        assert scl.fetch_latest_pypi_python_version("unit-test-gads-pkg", force=False) == "37.2.0"

        assert scl.upgrade_system_package("google-ads", target_version="--evil-flag") is False
        with patch.object(
            scl.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=1, stdout="", stderr="pip failed"),
        ):
            assert (
                scl.upgrade_system_package(
                    "google-ads", target_version="37.2.0", lib_path=str(src_s)
                )
                is False
            )

        # Manifest helpers + standalone plugin source resolution + archive tarball update flow
        empty_m = tmp_path / "m_empty"
        empty_m.mkdir()
        assert scl._has_project_manifest(str(empty_m)) is False
        (empty_m / "google-ads.gemspec").write_text("Gem::Specification.new\n", encoding="utf-8")
        assert scl._has_project_manifest(str(empty_m)) is True

        nested_m = tmp_path / "m_nested"
        (nested_m / "plugins" / "google-ads-api-developer-assistant").mkdir(parents=True)
        (nested_m / "plugins" / "google-ads-api-developer-assistant" / "plugin.json").write_text(
            "{}", encoding="utf-8"
        )
        assert scl._has_project_manifest(str(nested_m)) is True
        standalone_tgt = tmp_path / "standalone_tgt"
        standalone_tgt.mkdir()
        (standalone_tgt / "plugin.json").write_text("{}", encoding="utf-8")
        assert scl._resolve_sync_source_dir(str(nested_m), str(standalone_tgt)).endswith(
            "google-ads-api-developer-assistant"
        )

        assert scl.update_codebase_via_archive(str(standalone_tgt), "bad slug!", "v1.0.0", None) is False
        assert (
            scl.update_codebase_via_archive(
                str(standalone_tgt), "googleads/google-ads-python", "--bad-tag", None
            )
            is False
        )

        tar_buf = io.BytesIO()
        with tarfile.open(fileobj=tar_buf, mode="w:gz") as tf:
            content_b = b'name = "google-ads"\nversion = "37.2.0"\n'
            ti = tarfile.TarInfo(name="google-ads-python-37.2.0/pyproject.toml")
            ti.size = len(content_b)
            tf.addfile(ti, io.BytesIO(content_b))
        tar_bytes = tar_buf.getvalue()

        class _FakeTarStream(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        arch_dst = tmp_path / "arch_dst"
        with patch.object(
            scl.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=1, stdout="", stderr="no git tag"),
        ), patch.object(
            scl.urllib.request,
            "urlopen",
            side_effect=lambda *_a, **_kw: _FakeTarStream(tar_bytes),
        ):
            assert (
                scl.update_codebase_via_archive(
                    str(arch_dst),
                    "googleads/google-ads-python",
                    "v37.2.0",
                    "https://github.com/googleads/google-ads-python/archive/refs/tags/v37.2.0.tar.gz",
                )
                is True
            )
        assert (arch_dst / ".sync_version").read_text(encoding="utf-8").strip() == "37.2.0"

    def test_sync_client_libs_discovery_search_order(self, tmp_path, monkeypatch):
        """discover_client_libs_dir() checks plugin, Antigravity, Claude Code, then workspace dirs."""
        scl = _load_module(
            "skills/sync-client-libs/scripts/sync_client_libs.py", "scl_discovery_order"
        )
        plugin_dir = tmp_path / "plugin"
        monkeypatch.setattr(
            scl,
            "__file__",
            str(plugin_dir / "skills" / "sync-client-libs" / "scripts" / "sync_client_libs.py"),
        )
        fake_home = tmp_path / "home"
        _set_fake_home(monkeypatch, fake_home)
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        monkeypatch.chdir(workspace)

        with pytest.raises(FileNotFoundError):
            scl.discover_client_libs_dir()

        # Highest priority first. Create them in reverse order so each new directory must win.
        candidates = [
            plugin_dir / "client_libs",
            fake_home / ".gemini/config/plugins/google-ads-api-developer-assistant/client_libs",
            fake_home
            / ".claude/plugins/google-ads-assistant-local/plugins"
            / "google-ads-api-developer-assistant/client_libs",
            workspace / "client_libs",
        ]
        for candidate in reversed(candidates):
            candidate.mkdir(parents=True)
            assert Path(scl.discover_client_libs_dir()) == candidate

    def test_safe_extract_tar_rejects_devices_and_escaping_links(self, tmp_path):
        """_safe_extract_tar() rejects device files and links that point outside the target dir."""
        scl = _load_module(
            "skills/sync-client-libs/scripts/sync_client_libs.py", "scl_tar_members"
        )

        def _member(name: str, member_type: bytes, linkname: str = "") -> tarfile.TarInfo:
            info = tarfile.TarInfo(name)
            info.type = member_type
            info.linkname = linkname
            return info

        unsafe_members = [
            (_member("dev_node", tarfile.CHRTYPE), "device file"),
            (_member("pkg/link_out", tarfile.SYMTYPE, "../../outside.txt"), "link target"),
            (_member("hard_out", tarfile.LNKTYPE, "../outside.txt"), "link target"),
        ]
        for idx, (member, reason) in enumerate(unsafe_members):
            archive = tmp_path / f"unsafe_{idx}.tar"
            with tarfile.open(archive, "w") as tf:
                tf.addfile(member)
            extract_dir = tmp_path / f"extract_{idx}"
            extract_dir.mkdir()
            with tarfile.open(archive, "r") as tf, pytest.raises(ValueError, match=reason):
                scl._safe_extract_tar(tf, str(extract_dir))
            assert list(extract_dir.iterdir()) == []

        # TarFile.extractall() in Python 3.11.0-3.11.3 has no filter= argument.
        class _TarWithoutFilterArg:
            def __init__(self) -> None:
                self.extracted_to: list[str] = []

            @staticmethod
            def getmembers() -> list[tarfile.TarInfo]:
                return [tarfile.TarInfo("pkg/ok.txt")]

            def extractall(self, path: str, members=None, **kwargs) -> None:
                if "filter" in kwargs:
                    raise TypeError("extractall() got an unexpected keyword argument 'filter'")
                self.extracted_to.append(path)

        old_tar = _TarWithoutFilterArg()
        scl._safe_extract_tar(old_tar, str(tmp_path / "old_python_out"))
        assert old_tar.extracted_to == [str(tmp_path / "old_python_out")]

    def test_update_codebase_via_archive_retries_clone_with_v_prefixed_tag(
        self, tmp_path, monkeypatch
    ):
        """A failed clone of tag 'X.Y.Z' is retried as 'vX.Y.Z' before any tarball download."""
        from types import SimpleNamespace

        scl = _load_module(
            "skills/sync-client-libs/scripts/sync_client_libs.py", "scl_clone_retry"
        )
        cloned_branches: list[str] = []

        def _fake_git_clone(cmd, **_kwargs):
            branch = cmd[cmd.index("--branch") + 1]
            cloned_branches.append(branch)
            if branch != "v37.2.0":
                return SimpleNamespace(returncode=128, stdout="", stderr="Remote branch not found")
            clone_dir = Path(cmd[-1])
            clone_dir.mkdir(parents=True)
            (clone_dir / "pyproject.toml").write_text('version = "37.2.0"\n', encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(scl.subprocess, "run", _fake_git_clone)
        monkeypatch.setattr(
            scl.urllib.request,
            "urlopen",
            lambda *_a, **_kw: pytest.fail("No tarball download after a successful clone."),
        )
        lib_dir = tmp_path / "google-ads-python"
        assert (
            scl.update_codebase_via_archive(
                str(lib_dir), "googleads/google-ads-python", "37.2.0", None
            )
            is True
        )
        assert cloned_branches == ["37.2.0", "v37.2.0"]
        assert (lib_dir / "pyproject.toml").is_file()
        assert (lib_dir / ".sync_version").read_text(encoding="utf-8").strip() == "37.2.0"

    def test_additional_audit_remediations(self, tmp_path, monkeypatch):
        # 1. Every skill has a matching command file (directly or via canonical alias)
        skill_names = {
            p.parent.name for p in (PLUGIN_ROOT / "skills").glob("*/SKILL.md")
        }
        command_stems = {
            p.stem for p in (PLUGIN_ROOT / "commands").glob("*.md")
        }
        alias_map = {
            "google-ads-explain": "explain",
            "google-ads-step-by-step": "step-by-step",
        }
        for sname in skill_names:
            assert sname in command_stems or alias_map.get(sname) in command_stems, sname

        # 2. sitecustomize intercepts io.open, Path.open, and os.path.isfile in read mode
        sc = _load_module("config/sitecustomize.py", "sc_audit_reg")
        fake_yaml = tmp_path / "env_google_ads.yaml"
        fake_yaml.write_text('login_customer_id: "1122334455"\n', encoding="utf-8")
        fake_fl = tmp_path / "env_fin_limits"
        fake_fl.write_text("CampaignBudgetService.amount_micros = 0\n", encoding="utf-8")
        monkeypatch.setenv("_GOOGLE_ADS_TEST_SITECUSTOMIZE", "1")
        monkeypatch.setenv("GOOGLE_ADS_CONFIGURATION_FILE_PATH", str(fake_yaml))
        monkeypatch.setenv("GOOGLE_ADS_FINANCIAL_LIMITS_FILE", str(fake_fl))
        monkeypatch.chdir(tmp_path)
        assert sc._assistant_isfile("config/google-ads.yaml") is True
        assert sc._assistant_isfile("config/assistant_config") is True
        assert sc._assistant_isfile("config/financial_limits") is True
        assert sc._assistant_isfile("config/other_nonexistent.yaml") is False
        assert sc._assistant_isfile("/abs/nonexistent/google-ads.yaml") is False
        with Path("config/google-ads.yaml").open("r", encoding="utf-8") as pf:
            assert "1122334455" in pf.read()
        with Path("nonexistent_local.txt").open("w", encoding="utf-8") as wf:
            wf.write("ok")
        monkeypatch.delenv("_GOOGLE_ADS_TEST_SITECUSTOMIZE", raising=False)

        # 3. evaluate_mutation_guard gates --record-only and --set-execute-mutates, and inspects .sh & python -m
        dec_rec, _ = config_init.evaluate_mutation_guard(
            "python3 skills/execute-mutation/scripts/run_mutation.py --script s.py --dry-run --record-only"
        )
        assert dec_rec == "force_ask"

        dec_em, _ = config_init.evaluate_mutation_guard(
            "python3 config/config_init.py --set-execute-mutates true"
        )
        assert dec_em == "force_ask"

        sh_wrap = tmp_path / "wrap_live.sh"
        sh_wrap.write_text(
            "curl -X POST https://googleads.googleapis.com/v26/customers/123/campaigns:mutate -d '{}'\n",
            encoding="utf-8",
        )
        dec_sh, _ = config_init.evaluate_mutation_guard(f"bash {sh_wrap}")
        assert dec_sh == "deny"

        mod_pkg = tmp_path / "saved" / "code"
        mod_pkg.mkdir(parents=True, exist_ok=True)
        (mod_pkg / "mod_mut.py").write_text(
            "campaign_service.mutate_campaigns(request=req)\n", encoding="utf-8"
        )
        monkeypatch.setenv("GOOGLE_ADS_EXECUTE_MUTATES", "execute_mutates = false")
        dec_pym, _ = config_init.evaluate_mutation_guard(
            "python3 -m saved.code.mod_mut", workspace_cwd=str(tmp_path)
        )
        assert dec_pym == "deny"

        # 4. run_mutation --dry-run rejects mutation scripts that skip validate_only=True RPCs during dry-run
        skip_rpc_script = mod_pkg / "skip_dry_rpc.py"
        skip_rpc_script.write_text(
            "import sys\n"
            "if '--execute' in sys.argv:\n"
            "    svc.mutate_campaigns(request=req)\n"
            "print('dry-run skipped rpc')\n",
            encoding="utf-8",
        )
        res_skip = subprocess.run(
            [
                sys.executable,
                str(SKILLS_ROOT / "execute-mutation" / "scripts" / "run_mutation.py"),
                "--script",
                str(skip_rpc_script),
                "--dry-run",
                "--customer-id",
                "1234567890",
                "--operation",
                "Update Campaign",
                "--before",
                "PAUSED",
                "--after",
                "ENABLED",
                "--consequences",
                "Starts serving ads",
                "--reversibility",
                "REVERSIBLE",
            ],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
            check=False,
        )
        assert res_skip.returncode == 2
        assert "without executing any validate_only=True" in res_skip.stderr

        # 5. server.py GAQL date equality, Ruff verification, and CSV conversion validation
        srv = _load_module("sidecars/google-ads-a2a-service/server.py", "srv_audit_reg")
        h = srv.A2AHandler.__new__(srv.A2AHandler)
        gaql_eq = h.handle_gaql_validate(
            "t-eq",
            {
                "query": "SELECT click_view.gclid, segments.date FROM click_view WHERE segments.date = '2026-08-19' LIMIT 5",
                "api_version": "v26",
            },
        )
        assert gaql_eq["status"] == "COMPLETED"
        gaql_dow = h.handle_gaql_validate(
            "t-dow",
            {"query": "SELECT campaign.id, segments.day_of_week FROM campaign", "api_version": "v26"},
        )
        assert gaql_dow["status"] == "COMPLETED"
        codegen = h.handle_generate_code(
            "t-gen",
            {"user_prompt": "List active campaigns", "customer_id": "1234567890", "api_version": "v26"},
        )
        assert "PASSED" in codegen["result"]["lint_status"]

        csv_ok = tmp_path / "saved" / "conv_ok.csv"
        csv_ok.write_text(
            "gclid,conversion_time,conversion_value,currency_code\n"
            "EAIaIQobChMI1,2026-08-19 12:00:00+00:00,25.0,USD\n",
            encoding="utf-8",
        )
        conv_res = h.handle_troubleshoot_conversions(
            "t-conv-csv", {"csv_path": str(csv_ok), "api_version": "v26"}
        )
        assert conv_res["status"] == "COMPLETED"

    def test_run_coverage_python_311_settrace_fallback(self, tmp_path, monkeypatch):
        """Verifies run_coverage works when sys.monitoring is absent (Python 3.11)."""
        import os
        import run_coverage

        sample_mod = tmp_path / "py311_cov_sample.py"
        sample_mod.write_text(
            "import threading\n"
            "def compute(x):\n"
            "    out = [x + 1]\n"
            "    def worker():\n"
            "        out.append(x + 2)\n"
            "    t = threading.Thread(target=worker)\n"
            "    t.start()\n"
            "    t.join()\n"
            "    return sum(out)\n"
            "if __name__ == '__main__':\n"
            "    print(compute(10))\n",
            encoding="utf-8",
        )
        abs_sample = str(sample_mod.resolve())
        hits = {abs_sample: set()}

        prev_sys_trace = sys.gettrace()
        # Simulate Python < 3.12 where sys.monitoring does not exist
        with patch.object(run_coverage, "sys", wraps=sys) as fake_sys:
            if hasattr(fake_sys, "monitoring"):
                delattr(fake_sys, "monitoring")
            stop_fn = run_coverage.start_inproc_coverage(
                hits, tool_name="test_py311_fallback", force_settrace=True
            )
            assert callable(stop_fn)
            try:
                ns = {"__file__": abs_sample, "__name__": "py311_cov_sample"}
                exec(compile(sample_mod.read_text(encoding="utf-8"), abs_sample, "exec"), ns)
                assert ns["compute"](5) == 13
            finally:
                stop_fn()

        assert sys.gettrace() is prev_sys_trace
        # Verify both main-thread and worker-thread lines were recorded
        assert {2, 3, 5, 8, 9}.issubset(hits[abs_sample])

        # Verify subprocess hook with GADS_COVERAGE_FORCE_SETTRACE=1 writes cov_*.json
        fake_hook_dir = tmp_path / "cov_hook"
        fake_data_dir = tmp_path / "cov_data"
        monkeypatch.setattr(run_coverage, "COV_HOOK_DIR", fake_hook_dir)
        monkeypatch.setattr(run_coverage, "COV_DATA_DIR", fake_data_dir)
        run_coverage._write_subprocess_coverage_hooks([abs_sample])

        sub_env = os.environ.copy()
        sub_env["PYTHONPATH"] = (
            f"{fake_hook_dir}{os.pathsep}{sub_env.get('PYTHONPATH', '')}"
            if sub_env.get("PYTHONPATH")
            else str(fake_hook_dir)
        )
        sub_env["PYTHONNOUSERSITE"] = "0"
        sub_env["GADS_COVERAGE_FORCE_SETTRACE"] = "1"

        proc = subprocess.run(
            [sys.executable, abs_sample],
            env=sub_env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0
        assert proc.stdout.strip() == "23"
        cov_files = list(fake_data_dir.glob("cov_*.json"))
        assert len(cov_files) == 1
        sub_hits = json.loads(cov_files[0].read_text(encoding="utf-8"))
        assert {2, 3, 5, 8, 9, 11}.issubset(set(sub_hits[abs_sample]))


class TestConsistencyEfficiencyAndResilienceAudit:
    """Verifies consistency, efficiency, and resilience remediations across scripts, hooks, and sidecar."""

    def test_set_financial_limits_help_and_atomic_unchanged_skip(
        self, tmp_path
    ):
        sfl = _load_module(
            "skills/execute-mutation/scripts/set_financial_limits.py",
            "sfl_help_reg",
        )
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "set_financial_limits.py"), "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0
        assert "CampaignBudgetService.amount_micros" in proc.stdout

        fl_path = tmp_path / "financial_limits"
        written1 = sfl.write_financial_limits(
            {"CampaignBudgetService.amount_micros": 10_000_000},
            config_file=str(fl_path),
        )
        assert Path(written1).is_file()
        mtime1 = fl_path.stat().st_mtime_ns
        time.sleep(0.01)
        # Writing identical limits skips redundant disk rewrite
        sfl.write_financial_limits(
            {"CampaignBudgetService.amount_micros": 10_000_000},
            config_file=str(fl_path),
        )
        assert fl_path.stat().st_mtime_ns == mtime1

    def test_pmax_webpage_condition_real_proto_plus_and_raw_protobuf(self):
        from google.ads.googleads.client import GoogleAdsClient
        from google.auth.credentials import AnonymousCredentials

        pmax = _load_module(
            "skills/pmax-listing-filter/scripts/create_pmax_webpage_filter.py",
            "pmax_pp_reg",
        )
        active_ver = config_init.detect_latest_api_version()
        for use_pp in (True, False):
            client = GoogleAdsClient(
                credentials=AnonymousCredentials(),
                version=active_ver or None,
                use_proto_plus=use_pp,
            )
            cond = pmax._build_webpage_condition(client, "/clearance-sale")
            assert cond.url_contains == "/clearance-sale"

    def test_troubleshoot_conversions_enablement_setting_and_fallback_retry(
        self, tmp_path
    ):
        from types import SimpleNamespace
        from google.ads.googleads.client import GoogleAdsClient
        from google.auth.credentials import AnonymousCredentials

        tc = _load_module(
            "skills/troubleshoot-conversions/scripts/troubleshoot_conversions.py",
            "tc_enablement_reg",
        )
        active_ver = config_init.detect_latest_api_version()
        real_client = GoogleAdsClient(
            credentials=AnonymousCredentials(),
            version=active_ver or None,
            use_proto_plus=True,
        )
        assert tc._uses_enablement_setting(real_client) is True

        # 1. Client reporting active SDK version selects enablement_setting & effective_enablement_setting directly
        executed_queries: list[str] = []
        v26_row = SimpleNamespace(
            customer=SimpleNamespace(
                descriptive_name="Modern Account",
                conversion_tracking_setting=SimpleNamespace(
                    accepted_customer_data_terms=True,
                    enablement_setting=SimpleNamespace(name="ON"),
                    effective_enablement_setting=SimpleNamespace(name="ON"),
                ),
            )
        )

        class _ModernStubClient:
            version = active_ver

            @staticmethod
            def get_service(_name: str):
                def _stream(customer_id: str, query: str):
                    executed_queries.append(query)
                    if "FROM customer" in query:
                        assert "enhanced_conversions_for_leads_enabled" not in query
                        assert "effective_enablement_setting" in query
                        return [SimpleNamespace(results=[v26_row])]
                    return []

                return SimpleNamespace(search_stream=_stream)

        out = tc.troubleshoot_conversions(
            _ModernStubClient(),
            "123-456-7890",
            json_output=True,
            output_dir=str(tmp_path),
        )
        assert out["customer_info"]["name"] == "Modern Account"
        assert out["customer_info"]["enhanced_conversions_for_leads_enabled"] is True
        assert out["customer_info"]["effective_enablement_setting"] == "ON"
        assert out["primary_errors"] == []

        # 2. Unversioned client hitting UNRECOGNIZED_FIELD on legacy query retries cleanly with v26 query
        retry_queries: list[str] = []
        mock_retry_client = MagicMock()
        mock_retry_client.version = ""

        def _retry_stream(customer_id: str, query: str):
            retry_queries.append(query)
            if "enhanced_conversions_for_leads_enabled" in query:
                raise RuntimeError(
                    "QueryError.UNRECOGNIZED_FIELD: enhanced_conversions_for_leads_enabled"
                )
            if "FROM customer" in query:
                return [SimpleNamespace(results=[v26_row])]
            return []

        mock_retry_client.get_service.return_value.search_stream.side_effect = (
            _retry_stream
        )
        out_retry = tc.troubleshoot_conversions(
            mock_retry_client,
            "1234567890",
            json_output=True,
            output_dir=str(tmp_path),
        )
        assert len([q for q in retry_queries if "FROM customer" in q]) == 2
        assert out_retry["customer_info"]["effective_enablement_setting"] == "ON"
        assert not any("UNRECOGNIZED_FIELD" in e for e in out_retry["primary_errors"])

    def test_sync_client_libs_py315_pip_retry_longpaths_and_toml_preservation(
        self, tmp_path, monkeypatch
    ):
        from types import SimpleNamespace

        scl = _load_module(
            "skills/sync-client-libs/scripts/sync_client_libs.py", "scl_py315_reg"
        )
        glav = _load_module(
            "skills/ext-version/scripts/get_latest_api_version.py", "glav_toml_reg"
        )

        # 1. upgrade_system_package retries with --ignore-requires-python on Python 3.15 pip error
        pip_cmds: list[list[str]] = []

        def _fake_pip_run(cmd, **_kw):
            pip_cmds.append(list(cmd))
            if "--ignore-requires-python" not in cmd:
                return SimpleNamespace(
                    returncode=1,
                    stdout="",
                    stderr=(
                        "ERROR: Ignored the following versions that require a "
                        "different python version: 35.0.0 Requires-Python >=3.10,<3.15"
                    ),
                )
            return SimpleNamespace(returncode=0, stdout="Successfully installed", stderr="")

        monkeypatch.setattr(scl.subprocess, "run", _fake_pip_run)
        assert scl.upgrade_system_package("google-ads", target_version="35.0.0") is True
        assert len(pip_cmds) == 2
        assert "--ignore-requires-python" in pip_cmds[1]

        # 2. update_codebase_via_git passes core.longpaths=true
        git_cmds: list[list[str]] = []

        def _fake_git_run(cmd, **_kw):
            git_cmds.append(list(cmd))
            return SimpleNamespace(returncode=0, stdout="refs/remotes/origin/main\n", stderr="")

        monkeypatch.setattr(scl.subprocess, "run", _fake_git_run)
        assert scl.update_codebase_via_git(str(tmp_path), "v35.0.0") is True
        assert any("core.longpaths=true" in c for c in git_cmds)

        # 3. Extra TOML keys preserved in both sync_client_libs and get_latest_api_version
        cfg_dir = tmp_path / "work" / "config"
        lib_dir = tmp_path / "work" / "client_libs" / "google-ads-python"
        (lib_dir / "google" / "ads" / "googleads" / "v27").mkdir(parents=True)
        cfg_dir.mkdir(parents=True)
        cfg_file = cfg_dir / "assistant_config"
        cfg_file.write_text(
            'api_version = "v25"\n'
            'customer_id = "5556667770"\n'
            "execute_mutates = false\n"
            "timeout_seconds = 90\n",
            encoding="utf-8",
        )
        assert scl.update_api_version_cache_if_needed(str(lib_dir)) == "v27"
        text_after_scl = cfg_file.read_text(encoding="utf-8")
        assert 'api_version = "v27"' in text_after_scl
        assert "timeout_seconds = 90" in text_after_scl

        glav.update_assistant_config_api_version("v28", config_dir=str(cfg_dir))
        text_after_glav = cfg_file.read_text(encoding="utf-8")
        assert 'api_version = "v28"' in text_after_glav
        assert "timeout_seconds = 90" in text_after_glav

    def test_windows_powershell_python3_rewrite_regex_matches_hooks_json(self):
        import re

        # Verify both install.ps1 and update.ps1 use the lookahead pattern that rewrites hooks.json
        for ps_name in ("install.ps1", "update.ps1"):
            ps_text = (REPO_ROOT / ps_name).read_text(encoding="utf-8")
            assert 'python3(?=\\s|")' in ps_text

        py_equiv = re.compile(r'"command"\s*:\s*"python3(?=\s|")')
        for rel_manifest in (
            "hooks.json",
            "mcp_config.json",
            "sidecars/google-ads-a2a-service/sidecar.json",
        ):
            raw = (PLUGIN_ROOT / rel_manifest).read_text(encoding="utf-8")
            rewritten = py_equiv.sub('"command": "python', raw)
            assert rewritten != raw, f"{rel_manifest} was not rewritten"
            parsed = json.loads(rewritten)
            assert isinstance(parsed, dict)
            assert '"python3' not in rewritten

    def test_home_yaml_isolation_sitecustomize_chaining_and_guardrail_parity(
        self, tmp_path, monkeypatch
    ):
        import os

        rm = _load_module(
            "skills/execute-mutation/scripts/run_mutation.py", "rm_parity_reg"
        )
        srv = _load_module(
            "sidecars/google-ads-a2a-service/server.py", "srv_parity_reg"
        )

        # 1. Exact financial set parity between config_init.py and run_mutation.py
        assert config_init._HOOK_FINANCIAL_SERVICES == rm._FINANCIAL_SERVICES
        assert config_init._HOOK_FINANCIAL_METHODS == rm._FINANCIAL_METHODS
        assert config_init._HOOK_FINANCIAL_PAYLOAD_KEYS == rm._FINANCIAL_PAYLOAD_KEYS

        # 2. Direct REST custom write verbs blocked
        for verb in (
            "customers/123/accountLinks:createAccountLink",
            "customers/123/batchJobs/1:runBatchJob",
            "customers/123:startIdentityVerification",
            "customers/123/campaigns:enablePMaxBrandGuidelines",
        ):
            dec, _ = config_init.evaluate_mutation_guard(
                f"curl -X POST https://googleads.googleapis.com/v26/{verb} -d '{{}}'"
            )
            assert dec == "deny", f"REST verb not blocked: {verb}"

        # 3. Home ~/google-ads.yaml rejected across all mutation/MCC skill scripts & run_mutation
        fake_home = tmp_path / "home_iso"
        fake_home.mkdir()
        home_yaml = fake_home / "google-ads.yaml"
        home_yaml.write_text('client_id: "raw_home"\n', encoding="utf-8")
        _set_fake_home(monkeypatch, fake_home)
        monkeypatch.setenv("GOOGLE_ADS_CONFIGURATION_FILE_PATH", "~/google-ads.yaml")
        monkeypatch.chdir(tmp_path)

        for idx, rel_script in enumerate(
            (
                "skills/execute-mutation/scripts/create_account.py",
                "skills/execute-mutation/scripts/create_ad.py",
                "skills/execute-mutation/scripts/create_ad_group.py",
                "skills/execute-mutation/scripts/create_campaign.py",
                "skills/pmax-listing-filter/scripts/create_pmax_webpage_filter.py",
                "skills/get-cids-under-mcc/scripts/get_cids_under_mcc.py",
            )
        ):
            mod = _load_module(rel_script, f"iso_mod_{idx}")
            with patch.object(
                config_init,
                "sync_and_set_config_kv",
                return_value=str(tmp_path / "config" / "google-ads.yaml"),
            ):
                resolved = mod._get_config_path()
            assert os.path.abspath(os.path.expanduser(resolved)) != str(home_yaml)

        assert rm._find_google_ads_yaml() != str(home_yaml)

        # 4. sitecustomize idempotency on re-import + downstream sitecustomize chaining
        downstream_dir = tmp_path / "downstream_sc"
        downstream_dir.mkdir()
        marker = tmp_path / "chained_ok.txt"
        (downstream_dir / "sitecustomize.py").write_text(
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('1', encoding='utf-8')\n",
            encoding="utf-8",
        )
        sub_env = os.environ.copy()
        sub_env["PYTHONPATH"] = (
            f"{PLUGIN_ROOT / 'config'}{os.pathsep}{downstream_dir}"
        )
        sub_env["PYTHONNOUSERSITE"] = "0"
        proc_sc = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import builtins, importlib, sitecustomize;"
                    "orig = builtins.open._gads_orig;"
                    "importlib.reload(sitecustomize);"
                    "assert builtins.open._gads_orig is orig"
                ),
            ],
            env=sub_env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc_sc.returncode == 0, proc_sc.stderr
        assert marker.is_file()

        # 5. Sidecar module cache, AST MapField/nested message separation, and GAQL parity
        msg_py = tmp_path / "nested_proto.py"
        msg_py.write_text(
            "class OuterMsg:\n"
            "    class InnerSub:\n"
            "        sub_only: str = proto.Field(proto.STRING, number=1)\n"
            "    top_id: int = proto.Field(proto.INT64, number=1)\n"
            "    tags: dict[str, str] = proto.MapField(proto.STRING, proto.STRING, number=2)\n",
            encoding="utf-8",
        )
        f_top, _ = srv._parse_source_fields_and_enums(str(msg_py), "OuterMsg")
        assert [f["name"] for f in f_top] == ["top_id", "tags"]
        assert f_top[1]["label"] == "MAP"
        f_sub, _ = srv._parse_source_fields_and_enums(
            str(msg_py), "OuterMsg.InnerSub"
        )
        assert [f["name"] for f in f_sub] == ["sub_only"]

        h = srv.A2AHandler.__new__(srv.A2AHandler)
        assert (
            h.handle_gaql_validate(
                "t-cv-today",
                {
                    "query": "SELECT click_view.gclid FROM click_view WHERE segments.date DURING TODAY",
                    "api_version": "v26",
                },
            )["status"]
            == "COMPLETED"
        )
        assert (
            h.handle_gaql_validate(
                "t-cs-bounds",
                {
                    "query": (
                        "SELECT change_status.resource_name FROM change_status "
                        "WHERE change_status.last_change_date_time >= '2026-08-01' "
                        "AND change_status.last_change_date_time <= '2026-08-15' LIMIT 100"
                    ),
                    "api_version": "v26",
                },
            )["status"]
            == "COMPLETED"
        )
        m1 = h._load_mutation_script("create_account.py")
        m2 = h._load_mutation_script("create_account.py")
        assert m1 is m2

        # 6. validate_gaql disk cache enforces 0600 permissions and rejects symlinks
        vg = _load_module("skills/validate-gaql/scripts/validate_gaql.py", "vg_perm_reg")
        cache_file = tmp_path / "gaql_perm_cache.json"
        vg.set_cached_validation(
            "SELECT campaign.id FROM campaign", "v26", cache_path=str(cache_file)
        )
        assert cache_file.is_file()
        if os.name != "nt":
            assert (cache_file.stat().st_mode & 0o777) == 0o600
            symlink_cache = tmp_path / "gaql_symlink.json"
            symlink_cache.symlink_to(cache_file)
            assert vg._load_disk_cache(str(symlink_cache)) == {}
            vg._save_disk_cache(str(symlink_cache), {"k": {"valid": False, "timestamp": 2.0}})
            assert vg._load_disk_cache(str(cache_file)) != {"k": {"valid": False, "timestamp": 2.0}}

        # 7. validate_conversion_upload handles corrupt non-UTF8 binary CSV cleanly
        vcu = _load_module(
            "skills/troubleshoot-conversions/scripts/validate_conversion_upload.py",
            "vcu_bin_reg",
        )
        bad_bin_csv = tmp_path / "binary.csv"
        bad_bin_csv.write_bytes(b"\xff\xfe\x80\x81\x00\xff")
        with pytest.raises(SystemExit) as exc_bin:
            vcu.validate_conversion_csv(str(bad_bin_csv), "v26")
        assert exc_bin.value.code == 1

        # 8. Sidecar regex fallback on syntax-broken proto, find_spec discovery, and BrokenPipeError
        import types

        broken_srv_py = tmp_path / "broken_srv_proto.py"
        broken_srv_py.write_text(
            "class BrokenSrvMsg:\n"
            "    id: int = proto.Field(proto.INT64, number=1)\n"
            "    items: str = proto.RepeatedField(proto.STRING, number=2)\n"
            "    meta: dict = proto.MapField(proto.STRING, proto.STRING, number=3)\n"
            "    ACTIVE = 2\n"
            "class NextClass:\n"
            "    other: int = proto.Field(proto.INT64, number=1)\n"
            "def syntax_err(:\n",
            encoding="utf-8",
        )
        fb_fields, fb_enums = srv._parse_source_fields_and_enums(
            str(broken_srv_py), "BrokenSrvMsg"
        )
        assert [f["label"] for f in fb_fields] == ["OPTIONAL", "REPEATED", "MAP"]
        assert fb_enums == [{"name": "ACTIVE", "number": 2}]

        fake_pkg_dir = tmp_path / "fake_site_gads"
        (fake_pkg_dir / "v29").mkdir(parents=True)
        fake_init = fake_pkg_dir / "__init__.py"
        fake_init.write_text("", encoding="utf-8")
        orig_srv_isdir = srv.os.path.isdir
        saved_gads_mod = sys.modules.pop("google.ads.googleads", None)
        try:
            with (
                patch.object(srv.os.path, "isfile", return_value=False),
                patch.object(
                    srv.os.path,
                    "isdir",
                    side_effect=lambda p: (
                        orig_srv_isdir(p) if str(fake_pkg_dir) in str(p) else False
                    ),
                ),
                patch.object(
                    srv.importlib.util,
                    "find_spec",
                    return_value=types.SimpleNamespace(
                        submodule_search_locations=[str(fake_pkg_dir)],
                        origin=str(fake_init),
                    ),
                ),
            ):
                assert srv.get_effective_api_version({}, allow_interactive=False) == "v29"
        finally:
            if saved_gads_mod is not None:
                sys.modules["google.ads.googleads"] = saved_gads_mod

        h.send_response = MagicMock()
        h.send_header = MagicMock()
        h.end_headers = MagicMock()
        h.wfile = MagicMock()
        h.wfile.write.side_effect = BrokenPipeError("client disconnected")
        h._send_json(200, {"ok": True})

        # 9. get_latest_api_version TOML fallback, legacy customer_id migration, and sys.modules/find_spec paths
        glav = _load_module(
            "skills/ext-version/scripts/get_latest_api_version.py", "glav_cov_reg"
        )
        malformed_rendered = glav._render_updated_assistant_config(
            'customer_id = "7778889990"\nexecute_mutates = true\nenabled = false\nbroken = [\n',
            "v27",
        )
        assert 'customer_id = "7778889990"' in malformed_rendered
        assert "execute_mutates = true" in malformed_rendered
        assert "enabled = false" in malformed_rendered

        extra_rendered = glav._render_updated_assistant_config(
            'customer_id = "12345678"\nflag_opt = true\nlabel_opt = "alpha"\nratio_opt = 1.5\n',
            "v27",
        )
        assert "flag_opt = true" in extra_rendered
        assert 'label_opt = "alpha"' in extra_rendered
        assert "ratio_opt = 1.5" in extra_rendered

        global_cfg = (
            fake_home
            / ".gemini"
            / "config"
            / "plugins"
            / "google-ads-api-developer-assistant"
            / "config"
        )
        global_cfg.mkdir(parents=True, exist_ok=True)
        (global_cfg / "customer_id.txt").write_text("4445556660\n", encoding="utf-8")
        updated_cfgs = glav.update_assistant_config_api_version("28")
        assert str(global_cfg / "assistant_config") in updated_cfgs
        migrated_text = (global_cfg / "assistant_config").read_text(encoding="utf-8")
        assert 'api_version = "v28"' in migrated_text
        assert 'customer_id = "4445556660"' in migrated_text

        orig_glav_isdir = glav.os.path.isdir
        saved_gads_mod2 = sys.modules.pop("google.ads.googleads", None)
        try:
            with patch.object(
                glav.os.path,
                "isdir",
                side_effect=lambda p: (
                    orig_glav_isdir(p) if str(fake_pkg_dir) in str(p) else False
                ),
            ):
                with patch.object(
                    glav.importlib.util,
                    "find_spec",
                    return_value=types.SimpleNamespace(
                        submodule_search_locations=None,
                        origin=str(fake_init),
                    ),
                ):
                    assert glav.detect_latest_api_version(update_config=False) == "v29"

                fake_mod = types.ModuleType("google.ads.googleads")
                fake_mod.__path__ = [str(fake_pkg_dir)]
                fake_mod.__file__ = str(fake_init)
                sys.modules["google.ads.googleads"] = fake_mod
                assert glav.detect_latest_api_version(update_config=False) == "v29"
        finally:
            if saved_gads_mod2 is not None:
                sys.modules["google.ads.googleads"] = saved_gads_mod2
            else:
                sys.modules.pop("google.ads.googleads", None)

    def test_zero_static_api_version_defaults_or_fallbacks_across_runtime_and_installers(
        self, monkeypatch, tmp_path
    ):
        """Ensures no runtime code, seed config, or installer hardcodes a static v<N> default/fallback."""
        import re

        static_patterns = (
            re.compile(r"^\s*(?:DEFAULT_API_VERSION|FALLBACK_API_VERSION)\s*=\s*['\"]v\d+['\"]", re.M),
            re.compile(r"\bapi_version(?:\s*:\s*[^=]+)?\s*=\s*['\"]v\d+['\"]"),
            re.compile(r"\bdefault\s*=\s*['\"]v\d+['\"]"),
            re.compile(r"\breturn\s+(?:clean\s+or\s+)?['\"]v\d+['\"]"),
            re.compile(r"\b(?:api_ver|\$ApiVer)\s*=\s*.*['\"]v\d+['\"]"),
        )
        checked_files = [
            PLUGIN_ROOT / "config" / "assistant_config",
            PLUGIN_ROOT / "config" / "config_init.py",
            PLUGIN_ROOT / "sidecars" / "google-ads-a2a-service" / "server.py",
            REPO_ROOT / "install.sh",
            REPO_ROOT / "install.ps1",
            REPO_ROOT / "update.sh",
            REPO_ROOT / "update.ps1",
            REPO_ROOT / "tests" / "mutate_test_harness.py",
            REPO_ROOT / "tests" / "hitl_audit_logger.py",
            REPO_ROOT / "tests" / "test_account_config.yaml",
            *sorted(PLUGIN_ROOT.glob("skills/*/scripts/*.py")),
            *sorted(PLUGIN_ROOT.glob("skills/*/SKILL.md")),
        ]
        violations: list[str] = []
        for fp in checked_files:
            text = fp.read_text(encoding="utf-8")
            for pat in static_patterns:
                m = pat.search(text)
                if m:
                    violations.append(f"{fp.relative_to(REPO_ROOT)}: {m.group(0).strip()}")
        assert not violations, f"Found static API version defaults/fallbacks: {violations}"

        # Verify dynamic resolution across all 7 skill scripts via env, config, and find_spec
        skill_script_rels = (
            "skills/execute-mutation/scripts/create_account.py",
            "skills/execute-mutation/scripts/create_ad.py",
            "skills/execute-mutation/scripts/create_ad_group.py",
            "skills/execute-mutation/scripts/create_campaign.py",
            "skills/get-cids-under-mcc/scripts/get_cids_under_mcc.py",
            "skills/pmax-listing-filter/scripts/create_pmax_webpage_filter.py",
            "skills/inspect-object/scripts/inspect_object.py",
        )
        import importlib

        shared_cfg = importlib.import_module("config.config_init")
        for idx, rel in enumerate(skill_script_rels):
            mod = _load_module(rel, f"dyn_ver_skill_{idx}")
            monkeypatch.setenv("GOOGLE_ADS_API_VERSION", "30")
            assert mod._normalize_api_version(None) == "v30"
            monkeypatch.delenv("GOOGLE_ADS_API_VERSION", raising=False)
            resolved = mod._normalize_api_version("")
            assert re.fullmatch(r"v\d+", resolved)

            # Every script delegates to the shared config_init resolver: with no env and no
            # assistant_config value, the installed-version detection decides.
            with patch.object(
                shared_cfg, "get_configured_api_version", return_value=None
            ), patch.object(
                shared_cfg, "_detect_installed_api_version", return_value="v31"
            ):
                assert mod._normalize_api_version(None) == "v31"
            with patch.object(
                shared_cfg, "get_configured_api_version", return_value=None
            ), patch.object(
                shared_cfg, "_detect_installed_api_version", return_value=""
            ), pytest.raises(ValueError, match="api_version"):
                mod._normalize_api_version(None)

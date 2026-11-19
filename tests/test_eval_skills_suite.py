"""Pytest verification tests for the Dual-Mode Skill & Prompt Evaluation Harness."""

from __future__ import annotations

import json
import os
import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import eval_skills_suite as ess  # noqa: E402


class TestEvalSkillsSuiteOffline:
    """Verifies deterministic offline CI checks across all 11 skills & 13 commands."""

    def test_full_offline_eval_suite_passes_all_checks(self) -> None:
        results = ess.run_offline_checks()
        failed = [r for r in results if not r.passed]
        assert failed == [], (
            "Offline skill eval failures: "
            + "; ".join(f"{r.check_id}: {r.details}" for r in failed)
        )
        # 4 global checks (EV-SCHEMA-01/02, EV-CLI-01, EV-POLICY-01) + 22 skill routing/rubric cases
        assert len(results) == 26

    def test_cli_offline_mode_and_json_output(self, tmp_path: Any) -> None:
        json_out = tmp_path / "eval_report.json"
        rc = ess.main(["--mode", "offline", "--json-out", str(json_out)])
        assert rc == 0
        assert json_out.is_file()
        report = json.loads(json_out.read_text(encoding="utf-8"))
        assert report["mode"] == "offline"
        assert report["total"] == 26
        assert report["passed"] == 26
        assert report["failed"] == 0

    def test_cli_list_cases_and_skill_filter(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert ess.main(["--list-cases"]) == 0
        out = capsys.readouterr().out
        for skill in ess.EXPECTED_SKILLS:
            assert skill in out

        rc = ess.main(["--mode", "offline", "--skill", "explain"])
        assert rc == 0
        out2 = capsys.readouterr().out
        assert "EV-ROUTE-EXP-01" in out2
        assert "EV-ROUTE-EXP-02" in out2


class TestEvalSkillsRubricAndLiveProviders:
    """Verifies rubric negative controls and live LLM provider adapters with mocks."""

    def test_rubric_grader_catches_missing_required_and_forbidden_violations(self) -> None:
        cases = {c.case_id: c for c in ess.build_eval_cases()}

        # 1. Tutorial quiz recommending an answer MUST FAIL rubric
        tut_case = cases["EV-ROUTE-TUT-02"]
        ok, errs = ess.grade_response(
            tut_case,
            "Question on config/google-ads.yaml: A) config/google-ads.yaml (Recommended) B) explain",
        )
        assert not ok
        assert any("forbidden" in e.lower() for e in errs)

        # 2. Explain response missing Analogy section MUST FAIL rubric
        exp_case = cases["EV-ROUTE-EXP-01"]
        ok2, errs2 = ess.grade_response(
            exp_case,
            "### 1. The Big Picture\nclick_view tracks clicks.\n### 3. Interconnectedness\nLinks to campaign.\n### 4. Simple Language\nOne row per click.",
        )
        assert not ok2
        assert any("Analogy" in e for e in errs2)

        # 3. Deletion request returning operation.remove MUST FAIL rubric
        mut_case = cases["EV-ROUTE-MUT-02"]
        ok3, errs3 = ess.grade_response(
            mut_case,
            "You cannot normally remove it, or set PAUSED, or use operation.remove = resource_name",
        )
        assert not ok3
        assert any("forbidden" in e.lower() for e in errs3)

    def test_live_eval_runner_with_mock_provider_pass_and_fail(self) -> None:
        cases = {c.case_id: c for c in ess.build_eval_cases()}

        # Passing mocked provider echoes each case's compliant reference response
        def _passing_provider(
            provider: str,
            *,
            system_prompt: str,
            user_prompt: str,
            model: str,
            timeout: int,
        ) -> str:
            assert "MANDATORY RULES" in system_prompt
            for c in cases.values():
                if c.prompt == user_prompt:
                    return c.reference_response
            return ""

        pass_results = ess.run_live_evals(
            provider="gemini-api",
            skill_filter="explain",
            provider_fn=_passing_provider,
        )
        assert len(pass_results) == 2
        assert all(r.passed for r in pass_results)

        # Failing mocked provider returns non-compliant text
        fail_results = ess.run_live_evals(
            provider="claude",
            case_id_filter={"EV-ROUTE-EXP-01"},
            provider_fn=lambda *a, **kw: "click_view is a view.",
        )
        assert len(fail_results) == 1
        assert not fail_results[0].passed
        assert "Missing required pattern" in fail_results[0].details

    def test_invoke_live_provider_adapters_mocked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 1. claude CLI adapter
        fake_proc = MagicMock(returncode=0, stdout="Claude reply", stderr="")
        with patch.object(ess.subprocess, "run", return_value=fake_proc) as mock_run:
            out = ess.invoke_live_provider(
                "claude", system_prompt="SYS", user_prompt="USR"
            )
        assert out == "Claude reply"
        assert mock_run.call_args[0][0][0] == "claude"

        # 2. gemini-cli adapter
        fake_proc2 = MagicMock(returncode=0, stdout="Gemini CLI reply", stderr="")
        with patch.object(ess.subprocess, "run", return_value=fake_proc2) as mock_run2:
            out2 = ess.invoke_live_provider(
                "gemini-cli", system_prompt="SYS", user_prompt="USR"
            )
        assert out2 == "Gemini CLI reply"
        assert mock_run2.call_args[0][0][0] == "gemini"

        # 3. gemini-api adapter requires GEMINI_API_KEY
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            ess.invoke_live_provider("gemini-api", system_prompt="SYS", user_prompt="USR")

        # 4. gemini-api adapter parses JSON candidates
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-unit-test")
        fake_resp = MagicMock()
        fake_resp.__enter__.return_value = fake_resp
        fake_resp.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": "Gemini API reply"}]}}]
        }).encode("utf-8")
        with patch.object(ess.urllib.request, "urlopen", return_value=fake_resp):
            out3 = ess.invoke_live_provider(
                "gemini-api", system_prompt="SYS", user_prompt="USR", model="gemini-2.5-flash"
            )
        assert out3 == "Gemini API reply"

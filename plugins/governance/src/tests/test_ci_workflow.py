"""DEBT-0003: CI workflow aggregation gate tests.

The workflow's all-gates job must declare needs: over every gate job so
branch protection can require a single check name instead of six. YAML
is parsed from the repo's ci.yml (pyyaml is a core dependency).

TASK-REAL-012: GATE_JOBS 增加 critic-gate（GATE 8 批判者代码化）。
P0-2 (2026-08-03): 8 GATE 合并为 3 核心门控 quality/policy/critic，
消除脚本堆砌式膨胀；GATE 能力全部保留在合并 job 内。
CI-DIAGNOSE (2026-08-04): quality job 生成 --junitxml=pytest.xml，
新增诊断 step 跑 scripts/ci_diagnose.py；GATE 3 用真实 pytest 退出码
判定（弃用 || true——640 passed 曾掩盖 2 个失败，假绿）。
"""

import pathlib

import yaml

WORKFLOW = pathlib.Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml"
GATE_JOBS = [
    "quality",
    "policy",
    "critic",
]


def _workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _quality_steps():
    return _workflow()["jobs"]["quality"]["steps"]


class TestAllGatesAggregation:
    def test_all_gates_job_exists(self):
        jobs = _workflow()["jobs"]
        assert "all-gates" in jobs

    def test_all_gates_depends_on_every_gate(self):
        jobs = _workflow()["jobs"]
        needs = jobs["all-gates"].get("needs", [])
        assert sorted(needs) == sorted(GATE_JOBS), f"needs={needs}"

    def test_gate_jobs_are_defined(self):
        jobs = _workflow()["jobs"]
        for name in GATE_JOBS:
            assert name in jobs, f"gate job {name} missing"


class TestQualityJunitxmlDiagnose:
    """CI-DIAGNOSE 契约: junitxml 生成 + ci_diagnose 诊断 step + 真实退出码。"""

    def _gate3_run(self):
        for step in _quality_steps():
            name = step.get("name", "")
            if "GATE 3" in name:
                return step.get("run", "")
        raise AssertionError("GATE 3 step not found in quality job")

    def test_gate3_emits_junitxml(self):
        run = self._gate3_run()
        assert "--junitxml=pytest.xml" in run, "GATE 3 must emit pytest.xml"

    def test_gate3_uses_real_pytest_exit_code(self):
        run = self._gate3_run()
        assert "PYTEST_EXIT" in run, "GATE 3 must capture pytest exit code"
        assert "|| true" not in run, "GATE 3 must not swallow failures with || true"
        assert 'test "$PYTEST_EXIT" -eq 0' in run, "GATE 3 must fail on nonzero exit"

    def test_diagnose_step_always_runs(self):
        found = False
        for step in _quality_steps():
            if "ci_diagnose.py" in step.get("run", ""):
                found = True
                assert step.get("if") == "always()", "diagnose step must run even on failure"
                assert "--junitxml pytest.xml" in step["run"]
        assert found, "ci_diagnose step missing in quality job"

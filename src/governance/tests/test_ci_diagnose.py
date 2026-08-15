"""Tests for scripts/ci_diagnose.py — pytest failure classification.

Verifies the classifier against inline junitxml samples and a plain-text
pytest log, covering all seven categories plus exit-code mapping.
"""

import textwrap

import pytest

from scripts.ci_diagnose import (
    Failure,
    Report,
    build_markdown,
    classify_failure,
    parse_junitxml,
    parse_text_log,
)

# ---------------------------------------------------------------------------
# classify_failure — unit level
# ---------------------------------------------------------------------------


class TestClassifyFailure:
    @pytest.mark.parametrize(
        "message,expected",
        [
            ("AssertionError: expected 2 to be 1", "assertion"),
            ("assert False\nE   assert 2 == 1", "assertion"),
            ("Failed: DID NOT RAISE <class 'Exception'>", "assertion"),
            ("TimeoutError: operation timed out after 120s", "timeout"),
            ("Failed: Timeout >120.0s", "timeout"),
            ("ModuleNotFoundError: No module named 'tree_sitter'", "import"),
            ("ImportError: cannot import name 'ASTGuard'", "import"),
            ("SyntaxError: invalid syntax (test_x.py, line 12)", "syntax"),
            ("IndentationError: unexpected indent", "syntax"),
            ("fixture 'db' not found", "fixture"),
            ("FixtureLookupError: <class 'test_x'>, no fixture named 'mock'", "fixture"),
            ("ERROR at setup of test_foo", "collection"),
            ("collection failed: no tests collected", "collection"),
            ("RuntimeError: something weird", "other"),
            ("", "other"),
        ],
    )
    def test_categories(self, message, expected):
        assert classify_failure(message) == expected

    def test_type_hint_contributes(self):
        # type attribute from junitxml (e.g. "pytest.fail") is folded into the blob
        assert classify_failure("boom", type_="TimeoutError") == "timeout"


# ---------------------------------------------------------------------------
# junitxml parsing
# ---------------------------------------------------------------------------


def _junit_xml(failures: list) -> str:
    """Build a pytest-9-style nested junitxml string (testsuites > testsuite)."""
    cases = [f'<testcase classname="tests.test_x" name="test_pass"/>']
    for name, type_, msg in failures:
        cases.append(
            f'<testcase classname="tests.test_x" name="{name}">'
            f'<failure type="{type_}" message="{msg}"/></testcase>'
        )
    return (
        f'<testsuites name="pytest"><testsuite name="pytest" '
        f'tests="{len(cases)}" failures="{len(failures)}" '
        f'errors="0" skipped="0">{"".join(cases)}</testsuite></testsuites>'
    )


@pytest.fixture()
def junit_file(tmp_path):
    def _make(failures):
        p = tmp_path / "pytest.xml"
        p.write_text(_junit_xml(failures), encoding="utf-8")
        return p

    return _make


class TestParseJunitXml:
    def test_all_pass(self, junit_file):
        rep = parse_junitxml(junit_file([]))
        assert rep.total == 1 and rep.passed == 1 and rep.failed == 0
        assert rep.exit_code() == 0

    def test_nested_layout_derives_passed(self, junit_file):
        # pytest 9.x wraps <testsuite> in <testsuites>; totals must come
        # from the inner suite, and "passed" is derived (no such attribute)
        rep = parse_junitxml(junit_file([("test_a", "AssertionError", "assert 1 == 2")]))
        assert rep.total == 2  # 1 passing + 1 failing
        assert rep.passed == 1
        assert rep.failed == 1

    def test_mixed_categories(self, junit_file):
        rep = parse_junitxml(junit_file([
            ("test_a", "AssertionError", "assert 1 == 2"),
            ("test_b", "TimeoutError", "timed out after 120.0s"),
        ]))
        assert rep.failed == 2
        cats = rep.by_category
        assert cats["assertion"] == 1 and cats["timeout"] == 1
        assert rep.exit_code() == 2  # timeout -> human attention

    def test_fixable_only_returns_1(self, junit_file):
        rep = parse_junitxml(junit_file([
            ("test_a", "AssertionError", "assert 1 == 2"),
            ("test_b", "SyntaxError", "invalid syntax"),
        ]))
        assert rep.fixable is True
        assert rep.exit_code() == 1

    def test_root_cause_truncated(self):
        # XML attribute values normalize newlines away, so test Failure directly
        f = Failure(name="t", category="assertion", message="\n".join(f"line {i}" for i in range(50)))
        rc = f.root_cause()
        assert len(rc) <= 160
        assert rc == "line 0"

    def test_root_cause_prefers_e_lines(self):
        msg = (
            "    def test_will_fail():\n"
            ">       assert 1 == 2\n"
            "E       assert 1 == 2\n"
        )
        assert Failure("t", "assertion", msg).root_cause() == "E assert 1 == 2"

    def test_root_cause_falls_back_to_source_line(self):
        msg = "    def test_x():\n>       raise RuntimeError('boom')\n"
        assert Failure("t", "other", msg).root_cause() == "> raise RuntimeError('boom')"


# ---------------------------------------------------------------------------
# plain-text log parsing (fallback)
# ---------------------------------------------------------------------------


@pytest.fixture()
def text_log(tmp_path):
    def _make(content):
        p = tmp_path / "pytest.log"
        p.write_text(textwrap.dedent(content), encoding="utf-8")
        return p

    return _make


class TestParseTextLog:
    def test_summary_line(self, text_log):
        rep = parse_text_log(text_log("""
            100 passed, 3 skipped, 2 failed, 1 error in 6.71s
        """))
        assert rep.total == 106
        assert rep.passed == 100
        assert rep.skipped == 3

    def test_failure_blocks(self, text_log):
        rep = parse_text_log(text_log("""
            _____ test_update_without_where _____
            tests/test_ast_guard_sql_update.py:42: in test_update_without_where
                assert result.kind == "destructive-update"
            E   AssertionError: assert 'update' == 'destructive-update'
            =============================== short test summary ==============================
            FAILED tests/test_ast_guard_sql_update.py::test_update_without_where
            1 failed, 50 passed in 3.2s
        """))
        assert rep.failed == 1
        assert rep.failures[0].category == "assertion"
        assert "test_update_without_where" in rep.failures[0].name
        assert rep.exit_code() == 1

    def test_utf16le_bom_log(self, tmp_path):
        # Windows PowerShell 5.1 redirects write UTF-16LE + BOM; must decode
        p = tmp_path / "pytest.log"
        content = (
            "_______________________________ test_will_fail ________________________________\n"
            "reports\\sample_fail_test.py:2: AssertionError\n"
            "E   assert 1 == 2\n"
            "=========================== short test summary info ===========================\n"
            "FAILED reports/sample_fail_test.py::test_will_fail - assert 1 == 2\n"
            "1 failed, 1 passed in 1.35s\n"
        )
        p.write_bytes(b"\xff\xfe" + content.encode("utf-16-le"))
        rep = parse_text_log(p)
        assert rep.failed == 1
        assert rep.failures[0].category == "assertion"
        assert rep.passed == 1
        assert rep.total == 2

    def test_unparsed_blocks_are_honest(self, text_log):
        # summary claims 5 failed but only 1 block parses -> synthetic entry
        rep = parse_text_log(text_log("""
            _____ test_a _____
            E   AssertionError: boom
            5 failed, 10 passed in 1.0s
        """))
        assert rep.failed == 2  # 1 parsed + 1 honest synthetic
        assert rep.by_category.get("other", 0) >= 1
        assert rep.exit_code() == 2


# ---------------------------------------------------------------------------
# Markdown rendering + Failure helpers
# ---------------------------------------------------------------------------


class TestRender:
    def test_pass_report(self, junit_file):
        md = build_markdown(parse_junitxml(junit_file([])))
        assert "全部通过" in md
        assert "0" in md

    def test_failure_report_has_categories(self, junit_file):
        md = build_markdown(parse_junitxml(junit_file([
            ("test_a", "AssertionError", "assert 1 == 2"),
        ])))
        assert "| assertion | 1 | 可修复 |" in md
        assert "## 根因摘要" in md

    def test_failure_empty_message(self):
        f = Failure(name="t", category="other", message="")
        assert f.root_cause() == "(empty message)"


class TestReportHelpers:
    def test_exit_code_all_pass(self):
        assert Report(total=10, passed=10).exit_code() == 0

    def test_exit_code_mixed(self):
        rep = Report(failures=[
            Failure("a", "assertion"),
            Failure("b", "timeout"),
        ])
        assert rep.exit_code() == 2

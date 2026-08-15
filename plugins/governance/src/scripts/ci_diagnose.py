"""CI failure diagnostician — classify pytest failures into actionable categories.

Reads pytest output (structured --junitxml preferred, plain-text log fallback)
and produces a categorized Markdown report with root-cause summaries.

Failure categories:
  assertion   — test logic mismatch (fixable by engineer)
  timeout     — hung/slow test (env or code issue, human attention)
  import      — missing/broken module (env/dependency issue)
  syntax      — parse error in code/test (fixable)
  fixture     — missing/unknown fixture (fixable)
  collection  — collection error / error at setup (often human attention)
  other       — unclassified (human attention)

Exit codes:
  0  — all tests passed
  1  — failures exist, all fixable (assertion/syntax/fixture)
  2  — failures need human attention (timeout/import/collection/other)

Run:
  .venv-b1/Scripts/python.exe scripts/ci_diagnose.py --junitxml reports/pytest.xml
  .venv-b1/Scripts/python.exe scripts/ci_diagnose.py --log pytest.log
  pytest tests -q --junitxml=reports/pytest.xml && python scripts/ci_diagnose.py --junitxml reports/pytest.xml
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

_FIXABLE_CATEGORIES = {"assertion", "syntax", "fixture"}
_HUMAN_CATEGORIES = {"timeout", "import", "collection", "other"}


def classify_failure(message: str, type_: str = "") -> str:
    """Classify a single failure message into a category (priority-ordered)."""
    blob = f"{message}\n{type_}".lower()

    if "error at setup of" in blob or "collection failed" in blob \
            or blob.strip().startswith("error in ") or "collectionerror" in blob:
        return "collection"
    if "modulenotfounderror" in blob or "importerror" in blob:
        return "import"
    if "syntaxerror" in blob or "indentationerror" in blob or "parseerror" in blob:
        return "syntax"
    if "timeouterror" in blob or "timeout" in blob or "failed: timeout" in blob \
            or ">120.0s" in blob or "timed out" in blob:
        return "timeout"
    if "fixturelookuperror" in blob or "fixture '" in blob and "not found" in blob \
            or "fixture" in blob and "does not exist" in blob:
        return "fixture"
    if "assertionerror" in blob or "assert " in blob or "did not" in blob \
            or "failed: assert" in blob:
        return "assertion"
    return "other"


@dataclass
class Failure:
    name: str
    category: str
    message: str = ""

    def root_cause(self, max_len: int = 160) -> str:
        """Most informative line of the failure message.

        Preference: pytest's `E ` error lines (real assertion output), then
        `> ` source lines (where the failure occurred), then any non-empty
        line.
        """
        e_lines = [l for l in self.message.splitlines() if l.strip().startswith("E ")]
        if e_lines:
            return re.sub(r"\s+", " ", e_lines[0].strip())[:max_len]
        src_lines = [l for l in self.message.splitlines() if l.strip().startswith("> ")]
        if src_lines:
            return re.sub(r"\s+", " ", src_lines[0].strip())[:max_len]
        for line in self.message.splitlines():
            line = line.strip()
            if not line:
                continue
            line = re.sub(r"\s+", " ", line)
            return line[:max_len]
        return "(empty message)"


@dataclass
class Report:
    total: int = 0
    passed: int = 0
    skipped: int = 0
    failures: list = field(default_factory=list)
    source: str = ""

    @property
    def failed(self) -> int:
        return len(self.failures)

    @property
    def by_category(self) -> dict:
        cats: dict = {}
        for f in self.failures:
            cats[f.category] = cats.get(f.category, 0) + 1
        return cats

    @property
    def fixable(self) -> bool:
        return all(f.category in _FIXABLE_CATEGORIES for f in self.failures)

    def exit_code(self) -> int:
        if self.failed == 0:
            return 0
        return 1 if self.fixable else 2


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_junitxml(path: Path) -> Report:
    """Parse pytest --junitxml output into a Report.

    Handles both flat (<testsuite> root) and pytest 9.x nested
    (<testsuites><testsuite>) layouts.
    """
    root = ET.parse(path).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        raise ValueError(f"{path}: no <testsuite> element found")
    rep = Report(source=f"junitxml:{path.name}")
    rep.total = int(suite.attrib.get("tests", 0))
    failures = int(suite.attrib.get("failures", 0))
    errors = int(suite.attrib.get("errors", 0))
    rep.skipped = int(suite.attrib.get("skipped", 0))
    # pytest junitxml does NOT emit a "passed" attribute — derive it
    rep.passed = max(rep.total - failures - errors - rep.skipped, 0)

    for case in suite.iter("testcase"):
        for kind in ("failure", "error"):
            node = case.find(kind)
            if node is None:
                continue
            msg = node.attrib.get("message", "") or (node.text or "")
            type_ = node.attrib.get("type", "")
            rep.failures.append(Failure(
                name=case.attrib.get("classname", "") + "::" + case.attrib.get("name", ""),
                category=classify_failure(msg, type_),
                message=msg,
            ))
    return rep


def _read_text(path: Path) -> str:
    """Read with encoding detection.

    Windows PowerShell 5.1 redirects (pytest.log > pytest.log) write UTF-16LE
    with BOM, while CI/bash tools write UTF-8. Sniff the BOM, fall back to
    UTF-8 with replacement (never crash on foreign encodings).
    """
    raw = path.read_bytes()
    if raw.startswith(b"\xff\xfe"):
        return raw.decode("utf-16-le", errors="replace")
    if raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16-be", errors="replace")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig", errors="replace")
    return raw.decode("utf-8", errors="replace")


def parse_text_log(path: Path) -> Report:
    """Fallback: parse plain pytest text output (pytest.log style)."""
    text = _read_text(path)
    rep = Report(source=f"log:{path.name}")

    m = re.search(r"(\d+)\s+passed", text)
    rep.passed = int(m.group(1)) if m else 0
    m = re.search(r"(\d+)\s+(?:skipped|xfailed)", text)
    rep.skipped = int(m.group(1)) if m else 0
    m = re.search(r"(\d+)\s+failed", text)
    failed_count = int(m.group(1)) if m else 0
    m = re.search(r"(\d+)\s+error", text)
    error_count = int(m.group(1)) if m else 0
    rep.total = rep.passed + rep.skipped + failed_count + error_count

    # failed testcase blocks look like (pytest uses 5+ underscores, names may
    # themselves contain underscores, e.g. test_update_without_where):
    #   _____ test_name _____
    #   ... traceback ...
    #   tests/x.py:NN: in fn
    #       assert ...
    #   E   AssertionError: ...
    blocks = re.split(r"_{5,}\s*(.+?)\s*_{5,}\s*$", text, flags=re.MULTILINE)
    # blocks: [pre, name1, body1, name2, body2, ...]
    for i in range(1, len(blocks) - 1, 2):
        name, body = blocks[i].strip(), blocks[i + 1]
        if not body.strip():
            continue
        rep.failures.append(Failure(
            name=name,
            category=classify_failure(body),
            message=body.strip(),
        ))

    if rep.failed < failed_count + error_count:
        # unmatched failures — attach synthetic entries so the count is honest
        rep.failures.append(Failure(
            name="(unparsed failures)",
            category="other",
            message=f"text log shows {failed_count} failed / {error_count} error but only "
                    f"{rep.failed} blocks parsed; rerun with --junitxml for full detail.",
        ))
    return rep


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------

def build_markdown(rep: Report) -> str:
    """Render a Report as a Markdown diagnostic."""
    lines = [
        f"# CI 诊断报告",
        f"",
        f"- **来源**: `{rep.source}`",
        f"- **总用例**: {rep.total} | **通过**: {rep.passed} | **跳过**: {rep.skipped} | **失败**: {rep.failed}",
        f"- **退出码**: {rep.exit_code()} ({'ALL PASS' if rep.failed == 0 else '可修复' if rep.fixable else '需人工介入'})",
        f"",
    ]
    if rep.failed == 0:
        lines.append("✅ 全部通过,无失败分类。")
        return "\n".join(lines)

    lines.append("## 失败分类")
    lines.append("")
    lines.append("| 类别 | 数量 | 处置 |")
    lines.append("|------|:----:|------|")
    for cat in sorted(rep.by_category, key=lambda c: -rep.by_category[c]):
        action = "可修复" if cat in _FIXABLE_CATEGORIES else "需人工介入"
        lines.append(f"| {cat} | {rep.by_category[cat]} | {action} |")
    lines.append("")

    lines.append("## 根因摘要")
    lines.append("")
    for f in rep.failures:
        lines.append(f"- **[{f.category}]** `{f.name}`")
        lines.append(f"  - {f.root_cause()}")
    lines.append("")

    if not rep.fixable:
        lines.append("> ⚠️ 存在需人工介入类别(timeout/import/collection/other),建议结合环境证据判断,")
        lines.append("> 勿盲目重试或绕过。")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description="pytest failure diagnostician")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--junitxml", metavar="FILE", help="pytest --junitxml output file")
    src.add_argument("--log", metavar="FILE", help="plain pytest text log (fallback)")
    ap.add_argument("--no-color", action="store_true", help="accepted for CI compat")
    args = ap.parse_args(argv)

    # Windows consoles default to cp1252/cp950 which cannot encode CJK report
    # headers — force UTF-8 stdout (harmless elsewhere, errors never crash).
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    path = Path(args.junitxml or args.log)
    if not path.exists():
        print(f"[ci_diagnose] ERROR: {path} not found", file=sys.stderr)
        return 2

    rep = parse_junitxml(path) if args.junitxml else parse_text_log(path)
    print(build_markdown(rep))
    return rep.exit_code()


if __name__ == "__main__":
    sys.exit(main())

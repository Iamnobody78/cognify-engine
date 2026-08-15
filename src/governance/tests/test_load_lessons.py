"""load_lessons.py 测试 — 学习注入 (tmp_path 隔离)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import load_lessons as ll  # noqa: E402

PATTERNS = """# 高频经验模式
failure_patterns:
  - pattern: "tag:回归"
    count: 12
    last_occurrence: "2026-08-04"
    suggested_fix: "变更后必须运行相关测试套件验证无回归"
  - pattern: "tag:误报"
    count: 5
    last_occurrence: "2026-08-03"
    suggested_fix: "规则/扫描器变更后需跑基准语料确认零误报"
  - pattern: "tag:回归"
    count: 3
    last_occurrence: "2026-08-02"
    suggested_fix: "变更后必须运行相关测试套件验证无回归"  # 重复 fix 应去重
"""

PREFERENCES = """# 行为偏好统计
preferences:
  dominant_type: lesson
  type_distribution:
    lesson: 10
    decision: 3
"""


@pytest.fixture
def kn(tmp_path):
    d = tmp_path / "knowledge"
    d.mkdir()
    (d / "patterns.yaml").write_text(PATTERNS, encoding="utf-8")
    (d / "preferences.yaml").write_text(PREFERENCES, encoding="utf-8")
    return d


def test_load_patterns_parses(kn):
    ps = ll.load_patterns(kn)
    assert len(ps) == 3
    assert ps[0]["pattern"] == "tag:回归"
    assert ps[0]["count"] == 12
    assert "回归" in ps[0]["suggested_fix"]


def test_load_preferences_parses(kn):
    prefs = ll.load_preferences(kn)
    assert prefs["dominant_type"] == "lesson"


def test_build_lesson_context_dedup_fix(kn):
    ps = ll.load_patterns(kn)
    lines, rules = ll.build_lesson_context(ps)
    assert len(rules) == 2, "重复 suggested_fix 必须去重"
    assert "已加载 3 条经验教训, 生成 2 条规则建议" in lines[0]
    assert "1. ✅" in lines[1] and "2. ✅" in lines[2]


def test_build_lesson_context_max(kn):
    ps = ll.load_patterns(kn)
    _, rules = ll.build_lesson_context(ps, max_rules=1)
    assert len(rules) == 1


def test_main_human_readable(kn, capsys):
    rc = ll.main(["--knowledge", str(kn)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "[LESSON_CONTEXT]" in out
    assert "2 条规则建议" in out
    assert "[PREFERENCE]" in out


def test_main_json(kn, capsys):
    rc = ll.main(["--knowledge", str(kn), "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out.strip())
    assert data["lesson_count"] == 3
    assert data["rule_count"] == 2
    assert data["preferences"]["dominant_type"] == "lesson"


def test_empty_knowledge(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    rc = ll.main(["--knowledge", str(empty)])
    assert rc == 0
    assert "无已学习模式" in capsys.readouterr().out

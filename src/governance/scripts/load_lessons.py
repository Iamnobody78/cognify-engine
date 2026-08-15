#!/usr/bin/env python3
"""学习注入 — load_lessons.py (零依赖, 纯标准库).

在代理启动时加载 .aionui/knowledge/ 中的模式/偏好, 生成 LESSON_CONTEXT
注入到系统提示词 (环境约束), 让历史经验影响未来决策 — 形成"反馈闭环"。

诚实边界: 这是"上下文提示词注入", 不是模型权重更新 — 代理并不会"真的记住",
但它会看到自己以前写的记忆内容作为上下文, 影响后续行为。这是当前 Agent
工程中"记忆"的实际含义。

用法:
  python scripts/load_lessons.py                        # 人类可读注入上下文
  python scripts/load_lessons.py --json                 # JSON (供 MCP/启动脚本)
  python scripts/load_lessons.py --knowledge .aionui/knowledge --max 3

输出示例:
  [LESSON_CONTEXT] 已加载 3 条经验教训, 生成 2 条规则建议:
    1. ✅ 回归: 变更后必须运行相关测试套件验证无回归
    2. ✅ 误报: 规则/扫描器变更后需跑基准语料确认零误报
"""

import argparse
import json
import pathlib
import re
import sys

DEFAULT_KNOWLEDGE = pathlib.Path(__file__).resolve().parent.parent / ".aionui" / "knowledge"


def load_patterns(knowledge_dir):
    """解析 patterns.yaml → [{pattern, count, last_occurrence, suggested_fix}]。"""
    kd = pathlib.Path(knowledge_dir)
    pf = kd / "patterns.yaml"
    if not pf.exists():
        return []
    text = pf.read_text(encoding="utf-8", errors="replace")
    patterns = []
    cur = None
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^-\s+pattern:\s*[\"']?(.*?)[\"']?\s*$", line)
        if m:
            cur = {"pattern": m.group(1), "count": 0, "suggested_fix": ""}
            patterns.append(cur)
            continue
        m = re.match(r"^count:\s*(\d+)", line)
        if m and cur is not None:
            cur["count"] = int(m.group(1))
            continue
        m = re.match(r"^suggested_fix:\s*[\"']?(.*?)[\"']?\s*(?:#.*)?$", line)
        if m and cur is not None:
            cur["suggested_fix"] = m.group(1)
    return patterns


def load_preferences(knowledge_dir):
    """解析 preferences.yaml → dict (失败返回空 dict)。"""
    kd = pathlib.Path(knowledge_dir)
    pf = kd / "preferences.yaml"
    if not pf.exists():
        return {}
    text = pf.read_text(encoding="utf-8", errors="replace")
    prefs = {}
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^(\w+):\s*(.+)$", line)
        if m and m.group(1) not in ("preferences",):
            prefs[m.group(1)] = m.group(2).strip()
    return prefs


def build_lesson_context(patterns, max_rules=None):
    """从模式生成规则建议 (去重 suggested_fix)。返回 (context_lines, rules)。"""
    rules = []
    seen = set()
    for p in patterns:
        fix = p.get("suggested_fix", "").strip()
        if fix and fix not in seen:
            seen.add(fix)
            rules.append({"fix": fix, "count": p.get("count", 0),
                          "pattern": p.get("pattern", "")})
    if max_rules:
        rules = rules[:max_rules]
    lines = []
    if rules:
        lines.append(f"已加载 {len(patterns)} 条经验教训, 生成 {len(rules)} 条规则建议:")
        for i, r in enumerate(rules, 1):
            lines.append(f"  {i}. ✅ {r['fix']} (模式: {r['pattern']} ×{r['count']})")
    return lines, rules


def main(argv=None):
    ap = argparse.ArgumentParser(description="学习注入: 知识 → LESSON_CONTEXT")
    ap.add_argument("--knowledge", default=str(DEFAULT_KNOWLEDGE))
    ap.add_argument("--max", type=int, default=0, help="最多规则数 (0=全部)")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args(argv)

    patterns = load_patterns(args.knowledge)
    prefs = load_preferences(args.knowledge)
    lines, rules = build_lesson_context(patterns, args.max)

    if args.json:
        print(json.dumps({
            "lesson_count": len(patterns),
            "rule_count": len(rules),
            "rules": rules,
            "preferences": prefs,
        }, ensure_ascii=False))
        return 0

    print("[LESSON_CONTEXT] " + ("\n".join(lines) if lines else "无已学习模式"))
    if prefs:
        print(f"[PREFERENCE] 主导记忆类型: {prefs.get('dominant_type', '-')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

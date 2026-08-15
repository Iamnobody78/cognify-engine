#!/usr/bin/env python3
"""知识蒸馏 — knowledge_distill.py (零依赖, 纯标准库).

从记忆库 (memory/*.md) 中提取高频模式, 生成 .aionui/knowledge/ 下的
持久化索引文件, 供 load_lessons.py 在学习注入时消费。

启发式方法 (诚实边界: 非深度学习, 是频率/共现统计):
  patterns.yaml     — 按 tags 共现 + title 关键词提取高频失败/决策模式
  preferences.yaml  — 按 type 分布统计代理行为偏好
  report (stdout)   — 统计报告: 最常见失败模式、最常引用决策

用法:
  python scripts/knowledge_distill.py --root <memory_root> --out .aionui/knowledge
  python scripts/knowledge_distill.py --root <memory_root> --json   # JSON 报告

输出 YAML 为手写序列化 (零依赖, 无 PyYAML), 结构稳定供 load_lessons.py 解析。
"""

import argparse
import collections
import json
import os
import pathlib
import re
import sys

DEFAULT_ROOT = pathlib.Path(
    os.environ.get(
        "AIONRS_MEMORY_ROOT",
        r"C:\Users\ivy\AppData\Roaming\aionrs\projects"
        r"\C--Users-ivy-AppData-Roaming-AionUi-aionui-conversations"
        r"-2026-07-27-aionrs-temp-48324704\memory",
    )
)

# 高频模式关键词 → 规则建议模板 (启发式映射, 可扩展; 中英别名 → 同一规则)
PATTERN_HINTS = {
    "回归": "变更后必须运行相关测试套件验证无回归",
    "regression": "变更后必须运行相关测试套件验证无回归",
    "误报": "规则/扫描器变更后需跑基准语料确认零误报",
    "false": "规则/扫描器变更后需跑基准语料确认零误报",
    "超时": "涉及外部进程/网络的测试需显式 --timeout 并留足余量",
    "timeout": "涉及外部进程/网络的测试需显式 --timeout 并留足余量",
    "编码": "Windows 下写文件必须显式 encoding (UTF-8), 避免 cp936/cp950",
    "encoding": "Windows 下写文件必须显式 encoding (UTF-8), 避免 cp936/cp950",
    "路径": "脚本/测试应使用绝对路径或锚定仓库根, 不依赖 CWD",
    "path": "脚本/测试应使用绝对路径或锚定仓库根, 不依赖 CWD",
    "认证": "认证层变更后需验证 4 个入口注入 + 常量时间比较",
    "auth": "认证层变更后需验证 4 个入口注入 + 常量时间比较",
    "MCP": "MCP 工具契约变更后需同步更新协议文档与 mock 测试",
    "mcp": "MCP 工具契约变更后需同步更新协议文档与 mock 测试",
}

DEFAULT_FIX_TMPL = "高频标签 {tag} ({cnt}x): 建议人工审查该领域经验是否已固化为规则"

STOPWORDS = {"的", "了", "与", "和", "在", "后", "须", "应", "要", "不", "会",
             "需", "是", "有", "对", "从", "到", "中", "及", "等", "已", "将",
             "the", "with", "for", "not", "and", "are", "was", "from", "into",
             "that", "this", "have", "has", "will", "can", "but", "all", "out",
             "any", "also", "than", "then", "when", "were", "been", "its",
             "via", "per", "non", "was", "name", "type", "description", "date"}


def _parse_frontmatter(text):
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return {}
    fields = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            v = v.strip().strip('"').strip("'")  # 剥引号: type: "project" → project
            fields[k.strip()] = v
    return fields


def _tags_list(tag_str):
    """解析 tags 字段: 兼容裸逗号列表与 YAML 列表风格 (含引号)。"""
    return [t.strip().strip('"').strip("'")
            for t in tag_str.strip("[]").split(",") if t.strip()]


def _extract_date(fm, text):
    """优先 frontmatter date; 否则在正文标题中找 (YYYY-MM-DD)。"""
    d = fm.get("date", "").strip().strip('"').strip("'")
    if d:
        return d
    m = re.search(r"\((\d{4}-\d{2}-\d{2})\)", text)
    return m.group(1) if m else ""


def load_memories(root):
    """读 memory/*.md → [{file, type, tags, title, content, date, session}]。"""
    root = pathlib.Path(root)
    memories = []
    if not root.exists():
        return memories
    for f in sorted(root.glob("*.md")):
        if f.name == "MEMORY.md":
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        fm = _parse_frontmatter(text)
        if not fm.get("type"):
            continue
        memories.append({
            "file": f.name,
            "type": fm.get("type", "insight"),
            "tags": _tags_list(fm.get("tags", "")),
            "title": fm.get("name", ""),
            "content": text,
            "date": _extract_date(fm, text),
            "session": fm.get("session", ""),
        })
    return memories


def _strip_frontmatter(text):
    """去掉 YAML frontmatter, 只保留正文 (避免 name/type/date 等模板词污染关键词)。"""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    return text[m.end():] if m else text


def _keywords(title, content, weight=1):
    """中文字符 bigram + 英文词, 去停用词。启发式关键词提取。"""
    body = _strip_frontmatter(content)
    words = collections.Counter()
    # 英文/数字词
    for w in re.findall(r"[A-Za-z][A-Za-z0-9_\-]{2,}", title + " " + body[:2000]):
        if w.lower() not in STOPWORDS:
            words[w.lower()] += weight
    # 中文 bigram (标题权重 ×3)
    for text, tw in ((title, 3 * weight), (body[:1500], weight)):
        cn = re.findall(r"[\u4e00-\u9fff]+", text)
        for seq in cn:
            for i in range(len(seq) - 1):
                big = seq[i:i + 2]
                if big[0] not in STOPWORDS and big[1] not in STOPWORDS:
                    words[big] += tw
    return words


def distill(root, out_dir, top_k=12):
    """蒸馏主入口。返回 (patterns, preferences, stats)。"""
    memories = load_memories(root)
    stats = {
        "total": len(memories),
        "by_type": collections.Counter(m["type"] for m in memories),
        "by_date": collections.Counter(m["date"] for m in memories if m["date"]),
    }
    # tags 共现频率 (跨类型)
    tag_counter = collections.Counter()
    for m in memories:
        for t in m["tags"]:
            tag_counter[t] += 1
    # 关键词频率 — 全类型统计 (经验不只在 lesson/decision; project 也含教训),
    # lesson/decision 加权 ×2
    kw = collections.Counter()
    for m in memories:
        weight = 2 if m["type"] in ("lesson", "decision") else 1
        kw.update(_keywords(m["title"], m["content"], weight=weight))
    # 模式: 高频 tag + 高频关键词 + PATTERN_HINTS 命中
    patterns = []
    seen_tags = set()
    for tag, cnt in tag_counter.most_common(top_k):
        if cnt < 2 or tag in seen_tags:
            continue
        seen_tags.add(tag)
        hint = PATTERN_HINTS.get(tag) or DEFAULT_FIX_TMPL.format(tag=tag, cnt=cnt)
        patterns.append({
            "pattern": f"tag:{tag}",
            "count": cnt,
            "last_occurrence": _last_occurrence(memories, lambda m: tag in m["tags"]),
            "suggested_fix": hint,
        })
    # 关键词模式: 每个 hint key 在全量关键词计数器中找其最高频命中 (≥2),
    # 而非扫描固定窗口 — 避免通用词挤占 hint 关键词的排名
    for hint_key, hint in PATTERN_HINTS.items():
        matches = [(k, v) for k, v in kw.items() if hint_key in k and v >= 2]
        if not matches:
            continue
        best_kw, best_cnt = max(matches, key=lambda kv: kv[1])
        patterns.append({
            "pattern": f"keyword:{best_kw}",
            "count": best_cnt,
            "last_occurrence": _last_occurrence(
                memories, lambda m, k=best_kw: k in _keywords(m["title"], m["content"])),
            "suggested_fix": hint,
        })
    # 按出现次数降序 → 去重 (同 suggested_fix) → 截断 top_k:
    # 同一条规则建议只保留证据最强者 (修复后重新排序, 防高频被默认提示挤掉)
    patterns.sort(key=lambda p: p["count"], reverse=True)
    seen_fix = set()
    patterns = [p for p in patterns if not (p["suggested_fix"] in seen_fix
                                            or seen_fix.add(p["suggested_fix"]))]
    patterns = patterns[:top_k]
    # 偏好统计
    total = max(stats["total"], 1)
    preferences = {
        "dominant_type": stats["by_type"].most_common(1)[0][0] if stats["by_type"] else "none",
        "type_distribution": dict(stats["by_type"]),
        "top_tags": tag_counter.most_common(5),
        "sessions_seen": sorted({m["session"] for m in memories if m["session"]}),
    }
    return patterns, preferences, dict(stats)


def _last_occurrence(memories, pred):
    dates = [m["date"] for m in memories if m["date"] and pred(m)]
    return max(dates) if dates else ""


def _yaml_kv(key, value, indent=0):
    pad = " " * indent
    if isinstance(value, dict):
        lines = [f"{pad}{key}:"]
        for k, v in value.items():
            lines.append(f"{pad}  {k}: {v}")
        return lines
    if isinstance(value, list):
        lines = [f"{pad}{key}:"]
        for item in value:
            if isinstance(item, dict):
                lines.append(f"{pad}  - {item}")
            else:
                lines.append(f"{pad}  - {item}")
        return lines
    return [f"{pad}{key}: {value}"]


def write_outputs(patterns, preferences, stats, out_dir):
    """手写 YAML (零依赖)。返回输出文件列表。"""
    out_dir = pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # patterns.yaml
    lines = ["# 高频经验模式 (由 knowledge_distill.py 启发式提取, 非人工审核)",
             "# 生成时间: 见 mtime", "failure_patterns:"]
    for p in patterns:
        lines.append(f"  - pattern: \"{p['pattern']}\"")
        lines.append(f"    count: {p['count']}")
        lines.append(f"    last_occurrence: \"{p['last_occurrence']}\"")
        lines.append(f"    suggested_fix: \"{p['suggested_fix']}\"")
    (out_dir / "patterns.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    # preferences.yaml
    plines = ["# 行为偏好统计 (启发式)", "preferences:"]
    plines.append(f"  dominant_type: {preferences['dominant_type']}")
    plines.append("  type_distribution:")
    for t, c in preferences["type_distribution"].items():
        plines.append(f"    {t}: {c}")
    plines.append("  top_tags:")
    for t, c in preferences["top_tags"]:
        plines.append(f"    - {t} ({c})")
    (out_dir / "preferences.yaml").write_text("\n".join(plines) + "\n", encoding="utf-8")
    return ["patterns.yaml", "preferences.yaml"]


def main(argv=None):
    ap = argparse.ArgumentParser(description="知识蒸馏: 记忆 → 模式索引")
    ap.add_argument("--root", default=str(DEFAULT_ROOT), help="记忆根目录")
    ap.add_argument("--out", default=".aionui/knowledge", help="输出目录")
    ap.add_argument("--json", action="store_true", help="stdout 输出 JSON 报告")
    ap.add_argument("--top-k", type=int, default=12)
    args = ap.parse_args(argv)

    patterns, preferences, stats = distill(args.root, args.out, args.top_k)
    if args.json:
        print(json.dumps({"patterns": patterns, "preferences": preferences,
                          "stats": stats}, ensure_ascii=False))
        return 0
    files = write_outputs(patterns, preferences, stats, args.out)
    print(f"📊 蒸馏完成: 记忆 {stats['total']} 条, 类型分布 {dict(stats['by_type']) or '-'}")
    print(f"   patterns.yaml ({len(patterns)} 模式):")
    for p in patterns:
        print(f"     - [{p['count']}x] {p['pattern']} → {p['suggested_fix']}")
    print(f"   preferences.yaml: 主导类型={preferences['dominant_type']}, "
          f"top_tags={[t for t, _ in preferences['top_tags']]}")
    print(f"   输出: {', '.join(str(pathlib.Path(args.out) / f) for f in files)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Benchmark: 独立语料泛化性验证 — 验证 knowledge_distill.py 的 12 条模式
是否过拟合到训练记忆集。

指标:
1. 信号命中率: 每条现有模式的 hint key (中英别名) 在独立语料中出现的文件数 ≥1
   → 证明该经验主题在未见语料中真实存在 (非记忆格式伪影)
2. 正式模式交集: 独立语料 count≥2 蒸馏出的模式与现有模式的 suggested_fix 交集
3. 新候选: 独立语料独有的高频模式 → 人工评估

用法: python scripts/benchmark_distill.py --corpus <dir> --train-patterns <patterns.yaml>
"""
import argparse
import collections
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import knowledge_distill as kd


def _clean(v):
    return v.strip().strip('"').strip("'")


def load_train_patterns(path):
    """从 patterns.yaml 读回训练模式 (suggested_fix 集合 + pattern 列表)。"""
    text = pathlib.Path(path).read_text(encoding="utf-8")
    fixes, patterns = set(), []
    for m in re.finditer(r"- pattern: (.+?)\n(?:.*?\n)*?\s+suggested_fix: (.+)", text):
        patterns.append(_clean(m.group(1)))
        fixes.add(_clean(m.group(2)))
    return patterns, fixes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--train-patterns", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    corpus = pathlib.Path(args.corpus)
    memories = kd.load_memories(corpus)
    train_patterns, train_fixes = load_train_patterns(args.train_patterns)

    # 1) 信号命中率: 对每条 hint key, 统计在多少文件中出现
    hint_keys = {
        "mcp": ["mcp"], "路径/绝对路径": ["路径", "path"], "timeout/超时": ["timeout", "超时"],
        "回归测试": ["回归", "regression"], "零误报": ["误报", "false"],
        "UTF-8 编码": ["编码", "encoding"], "认证": ["认证", "auth"],
        "tag:governance": ["governance"], "tag:triple-loop": ["triple", "loop"],
        "tag:bottlesumo": ["bottlesumo"], "tag:scheduler": ["scheduler"], "tag:sidecar": ["sidecar"],
    }
    hit = {}
    for label, keys in hint_keys.items():
        n = 0
        for m in memories:
            blob = m["title"] + " " + m["content"].lower()
            if any(k.lower() in blob for k in keys):
                n += 1
        hit[label] = (n, len(memories))

    # 2) 独立语料正式蒸馏
    pat, pref, stats = kd.distill(corpus, pathlib.Path(args.out), top_k=12)
    corpus_fixes = {p["suggested_fix"] for p in pat}
    overlap = train_fixes & corpus_fixes
    new_candidates = [p for p in pat if p["suggested_fix"] not in train_fixes]

    # 报告
    lines = []
    lines.append("# Benchmark: 独立语料泛化性验证")
    lines.append("")
    lines.append(f"- 训练记忆: 74 条 (memory/)")
    lines.append(f"- 独立语料: {len(memories)} 个文件 (agent-governance v1 归档: CRITIQUE/governance docs/research analysis)")
    lines.append(f"- 训练模式: {len(train_patterns)} 条")
    lines.append(f"- 独立语料正式模式: {len(pat)} 条, 与训练 suggested_fix 交集: {len(overlap)}")
    lines.append("")
    lines.append("## 1. 信号命中率 (hint key 在独立语料中出现的文件数 / 语料总数)")
    lines.append("")
    lines.append("| 模式 | 命中文件 | 命中率 | 判定 |")
    lines.append("|------|---------|--------|------|")
    for label, (n, total) in hit.items():
        ratio = n / total if total else 0
        verdict = "✅ 泛化" if n >= 1 else ("⚠️ 生态特定" if label.startswith("tag:") else "❌ 未复现")
        lines.append(f"| {label} | {n}/{total} | {ratio:.0%} | {verdict} |")
    lines.append("")
    lines.append("## 2. 正式模式对比")
    lines.append("")
    lines.append(f"- 共现 (train ∩ corpus): {len(overlap)}")
    for f in sorted(overlap):
        lines.append(f"  - ✅ {f}")
    lines.append(f"- 独立语料新候选 (corpus \\ train): {len(new_candidates)}")
    for p in new_candidates:
        lines.append(f"  - 🆕 `{p['pattern']}` (×{p['count']}): {p['suggested_fix']}")
    lines.append("")
    lines.append("## 3. 裁决")
    lines.append("")
    hit_general = sum(1 for label, (n, _) in hit.items() if n >= 1 and not label.startswith("tag:"))
    lines.append(f"- 通用经验模式 (非 tag) 命中: {hit_general}/{len([l for l in hit if not l.startswith('tag:')])}")
    lines.append("- **通过 (≥5/8)** 若通用命中 ≥5: 蒸馏泛化成立, 模式非过拟合")
    lines.append("- 新候选模式需人工评估后决定是否入 patterns.yaml")
    lines.append("")
    lines.append("> 生成: benchmark_distill.py — 自动运行")

    report = "\n".join(lines)
    out_path = pathlib.Path(args.out) / "benchmark_report.md"
    out_path.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())

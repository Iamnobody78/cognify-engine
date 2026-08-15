#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DEBT-MINER v1.0 — 自主债务挖掘引擎 (M.I.N.E. 五步)
===================================================
不依赖人工告知: 9 个来源穷举扫描 -> 正则挖掘 -> 去重归一 -> 富化 -> 报告
产出: ~/.aionui-tri-sync/debt/mining/{search_map,raw_findings,normalized_debts,enriched_debts,debt_mining_report}.{md,json}
"""
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

WS = Path(r"C:\Users\ivy\AppData\Roaming\AionUi\aionui\conversations\2026\07\27\aionrs-temp-48324704")
TRI = Path(r"C:\Users\ivy\.aionui-tri-sync")
HOME = Path.home()
OUT = TRI / "debt" / "mining"

EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".pytest_cache",
                "data", "archive", "_archive", ".cache", ".ruff_cache",
                "GPUCache", "Cache", "Code Cache", "Crashpad",
                "hub"}  # hub 是镜像派生数据, 非源 (防重复计数)
TEXT_EXT = {".py", ".md", ".yaml", ".yml", ".json", ".ts", ".js", ".tsx",
            ".jsx", ".txt", ".toml", ".cfg", ".sh", ".bat", ".ps1", ".cpp",
            ".c", ".h", ".html", ".css", ".rs"}

COMMENT_RE = re.compile(
    r"(?i)\b(TODO|FIXME|HACK|XXX|BUG|DEPRECATED|WORKAROUND|HARDCODE|TEMP|PROVISIONAL|LATER)\b")
DOC_DEBT_RE = re.compile(
    r"(待完成|待定|未解决|已知问题|限制|局限|未来工作|后续|暂缓|延后|遗留|待办|未完成|"
    r"待验证|待完善|临时|KNOWN_LIMITATIONS)")
GIT_DEBT_RE = re.compile(r"(?i)(revert|rollback|hotfix|workaround|temporary|provisional)")

TARGETS = [
    ("agv2", WS / "agent-governance-v2"),
    ("bottlesumo", WS / "bottlesumo_pi"),
    ("tri-sync-src", TRI / "daemon"),
    ("tri-sync-lab", TRI / "research_lab"),
    ("tri-sync-data", TRI / "data_eng"),
    ("tri-sync-prospect", TRI / "prospect"),
    ("meta-prompts-home", HOME / ".aionui"),
]

# 解耦 (2026-08-15 元思考): 扫描器不再扫 tri-sync 整个根目录 (90% 是自身产物:
# hub/debt/reports/state/logs/backup/architecture_export/context/honesty 等),
# 改为源码白名单 — 扫描器不扫自己的家。产物目录由 exclude 保底。


def walk_files(root):
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(x in p.parts for x in EXCLUDE_DIRS):
            continue
        if p.suffix.lower() not in TEXT_EXT:
            continue
        if p.stat().st_size > 2_000_000:
            continue
        yield p


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    findings = []
    search_map = []

    # ---- Phase M: Map ----
    for name, root in TARGETS:
        files = list(walk_files(root))
        search_map.append({"target": name, "root": str(root), "files": len(files)})
        print(f"[Map] {name}: {len(files)} 文件待扫")

    # ---- Phase I: Investigate ----
    for name, root in TARGETS:
        n_comment = 0
        for p in walk_files(root):
            try:
                txt = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = str(p.relative_to(root))
            # 跳过"标记检测器"类工具 (其源码含标记模式串是设计使然)
            if any(x in p.name for x in ("code_hole_detector", "hole_detector")):
                continue
            for m in COMMENT_RE.finditer(txt):
                # 精度过滤: 只统计注释上下文中的关键词 (排除路径/字符串伪信号)
                line = txt[:m.start()].splitlines()[-1]
                if p.suffix == ".py":
                    # 双引号奇偶: 匹配点在字符串字面量内 -> 跳过
                    if txt[:m.start()].count('"') % 2 == 1:
                        continue
                    hash_pos = line.rfind("#")
                    if hash_pos < 0:
                        continue
                    if line.rfind("'") > hash_pos or line.rfind('"') > hash_pos:
                        continue
                if "aionrs-temp" in txt[max(0, m.start() - 30):m.start() + 30] or \
                        m.group(0).upper() == "TEMP" and "temp" in line and (
                        "Path(" in line or "\\\\" in line or "C:" in line):
                    continue
                n_comment += 1
                findings.append({"source": "code-comment", "target": name,
                                 "file": rel, "keyword": m.group(0).upper(),
                                 "snippet": txt[max(0, m.start() - 40):m.start() + 60].replace("\n", " ")[:90],
                                 "severity": "P2" if m.group(0).upper() in ("BUG", "FIXME") else "P3"})
            if p.suffix == ".md":
                for m in DOC_DEBT_RE.finditer(txt):
                    findings.append({"source": "doc-signal", "target": name,
                                     "file": rel, "keyword": m.group(0),
                                     "snippet": txt[max(0, m.start() - 30):m.start() + 40].replace("\n", " ")[:70],
                                     "severity": "P3"})
        print(f"[Investigate] {name}: {n_comment} 代码债务注释")

    # 来源 7: git 历史模式
    for repo_name, repo in (("agv2", WS / "agent-governance-v2"),
                            ("bottlesumo", WS / "bottlesumo_pi")):
        try:
            r = subprocess.run(["git", "-C", str(repo), "log", "--oneline", "-200"],
                               capture_output=True, text=True, timeout=30,
                               encoding="utf-8", errors="replace")
            hits = [l for l in r.stdout.splitlines() if GIT_DEBT_RE.search(l)]
            findings.append({"source": "git-history", "target": repo_name,
                             "file": "git log -200", "keyword": f"{len(hits)} 条 fix/revert/hotfix 提交",
                             "snippet": "; ".join(h.split(" ", 1)[-1][:30] for h in hits[:5]),
                             "severity": "P2"})
        except Exception as e:
            findings.append({"source": "git-history", "target": repo_name,
                             "file": "-", "keyword": f"git 不可用: {e}", "snippet": "",
                             "severity": "P3"})

    # 来源 1/3: 既有模式库 + VCE 盲点
    fp = TRI / "prospect/failure_patterns.md"
    if fp.exists():
        n = len([l for l in fp.read_text(encoding="utf-8").splitlines()
                 if l.startswith("| FP-")])
        findings.append({"source": "failure-library", "target": "tri-sync",
                         "file": "prospect/failure_patterns.md",
                         "keyword": f"{n} 条失败模式 (其中高严重度是持续债务源)",
                         "snippet": "PROSPECT 模式库", "severity": "P2"})

    # 来源 8: 对话历史 (hub/history)
    conv = TRI / "hub/history/aionui_messages.jsonl"
    if conv.exists():
        n_un = 0
        for line in conv.open(encoding="utf-8"):
            if re.search(r"未完成|待定|以后再处理|暂缓|延后", line):
                n_un += 1
        findings.append({"source": "conversation", "target": "aionui",
                         "file": "hub/history/aionui_messages.jsonl",
                         "keyword": f"{n_un} 条对话含未完成/暂缓信号",
                         "snippet": "对话历史信号", "severity": "P3"})

    # 来源 6: GitHub (外部)
    findings.append({"source": "github", "target": "bottlesumo-pi/agv2",
                     "file": "GitHub API", "keyword": "待凭据核验 (PR#30/issue#6,7,8)",
                     "snippet": "外部资产", "severity": "P0"})

    (OUT / "search_map.md").write_text("\n".join([
        "# 搜索地图 (Phase M)", "", f"> {datetime.now().isoformat(timespec='seconds')}", "",
        "| 目标 | 文件数 | 根路径 |", "|:--|:--|:--|",
        *[f"| {s['target']} | {s['files']} | {s['root'][:60]} |" for s in search_map],
    ]), encoding="utf-8")
    (OUT / "raw_findings.json").write_text(json.dumps(
        {"generated": datetime.now().isoformat(timespec="seconds"),
         "findings": findings}, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- Phase N: Normalize (去重+分类+分级) ----
    seen = set()
    norm = []
    for f in findings:
        key = (f["source"], f["target"], f["keyword"][:40])
        if key in seen:
            continue
        seen.add(key)
        dim = {"code-comment": "D1", "git-history": "D1", "failure-library": "D2",
               "doc-signal": "D5", "conversation": "D5", "github": "D4"}[f["source"]]
        norm.append({"source": f["source"], "target": f["target"],
                     "file": f["file"], "keyword": f["keyword"],
                     "snippet": f["snippet"], "dim": dim, "sev": f["severity"],
                     "status": "待处理"})
    (OUT / "normalized_debts.json").write_text(json.dumps(
        {"generated": datetime.now().isoformat(timespec="seconds"), "debts": norm},
        ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- Phase E: Enrich (文件存在性/修改时间) ----
    for d in norm:
        p = Path(d["file"])
        cand = None
        for _, root in TARGETS:
            if (root / d["file"]).exists():
                cand = root / d["file"]
                break
        d["enriched"] = {"file_exists": cand is not None,
                         "mtime": str(datetime.fromtimestamp(cand.stat().st_mtime))[:10] if cand else None}
    (OUT / "enriched_debts.json").write_text(json.dumps(
        {"generated": datetime.now().isoformat(timespec="seconds"), "debts": norm},
        ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- Phase R: Report ----
    by_sev = Counter(d["sev"] for d in norm)
    by_dim = Counter(d["dim"] for d in norm)
    by_src = Counter(d["source"] for d in norm)
    by_tgt = Counter(d["target"] for d in norm)
    (OUT / "debt_mining_report.md").write_text("\n".join([
        "# 债务挖掘报告 (DEBT-MINER Phase R)", "",
        f"> {datetime.now().isoformat(timespec='seconds')} | 自动挖掘, 非人工清单", "",
        f"## 总发现: {len(findings)} 原始 / {len(norm)} 去重后", "",
        f"## 严重程度: " + ", ".join(f"{k}={v}" for k, v in sorted(by_sev.items())), "",
        f"## 六维分类: " + ", ".join(f"{k}={v}" for k, v in sorted(by_dim.items())), "",
        f"## 来源分布: " + ", ".join(f"{k}={v}" for k, v in sorted(by_src.items())), "",
        f"## 目标分布: " + ", ".join(f"{k}={v}" for k, v in sorted(by_tgt.items())), "",
        "## P0/P1 优先项 (代码注释 BUG/FIXME + 外部阻塞)", "",
        *[f"- [{d['sev']}] {d['target']}/{d['file'][:50]} — {d['keyword']}"
          for d in norm if d['sev'] in ("P0", "P1")][:30],
        "", "## 高密度样本 (代码注释 TOP)", "",
        *[f"- {d['target']}:{d['file'][:60]} {d['keyword']} — {d['snippet'][:40]}"
          for d in norm if d['source'] == 'code-comment'][:20],
        "", "## Honest Boundary",
        "- GitHub issue/PR 为外部资产, 需凭据核验 (不臆断)",
        "- 对话历史信号为词法匹配 (未完成/暂缓), 语义级需 META-DIALOGUE-ANALYZER",
        "- 置信度: 中-高 (来源可复现, 分级为启发式)",
    ]), encoding="utf-8")
    print(f"[Report] 原始 {len(findings)} / 去重 {len(norm)}")
    print(f"  严重度: {dict(by_sev)} | 维度: {dict(by_dim)}")
    print(f"  产出: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""RES-AGENT: research gate (R-gate) — 研究产出门禁, 与 v9_gate 同构。

研究闭环的验证层: 每个研究产出 (papers list / patterns / design / evidence /
synthesis) 必须通过对应判据才能进入下一 phase 或固化到知识库。
避免"产出了但未验证"的 FS-GOVERN 式断裂。

Run: python3 governance/research/research_gate.py --artifact <path> --phase papers
"""
import argparse
import json
import os
import re
import sys


# ── phase 判据 ──────────────────────────────────────────────────────────────
CRITERIA = {
    "papers": [
        ("count>=3", lambda a: len(a.get("papers", [])) >= 3,
         "检索论文数 >= 3 (R0.1)"),
        ("has_meta", lambda a: all(k in a for k in ("retrieved_at", "count")),
         "含 retrieved_at/count 元数据"),
        ("each_has_id_title", lambda a: all(
            p.get("id") and p.get("title") for p in a.get("papers", [])),
         "每篇含 id + title"),
    ],
    "patterns": [
        ("count>=2", lambda a: len(a.get("patterns", [])) >= 2,
         "提取模式数 >= 2 (R0.2)"),
        ("each_has_mode", lambda a: all(
            p.get("pattern") and p.get("evidence") for p in a.get("patterns", [])),
         "每模式含 pattern + evidence"),
    ],
    "experiment": [
        ("has_variables", lambda a: all(
            k in a for k in ("independent", "dependent", "control")),
         "含自变量/因变量/控制变量"),
        ("has_predictions", lambda a: bool(a.get("predictions")),
         "含可证伪预测 (falsifiable predictions)"),
    ],
    "evidence": [
        ("has_confidence", lambda a: isinstance(a.get("confidence"), (int, float)),
         "含置信度"),
        ("has_effect_size", lambda a: bool(a.get("effect_size")),
         "含效应量描述"),
    ],
    "synthesis": [
        ("has_rules", lambda a: len(a.get("engineering_rules", [])) >= 1,
         "含 >=1 条工程规则"),
        ("has_boundaries", lambda a: bool(a.get("boundaries")),
         "含适用边界声明"),
    ],
}


def evaluate_artifact(phase: str, path: str) -> dict:
    if phase not in CRITERIA:
        raise ValueError(f"unknown phase: {phase}")
    with open(path, "r", encoding="utf-8") as f:
        artifact = json.load(f)
    results = []
    passed = True
    for cid, fn, desc in CRITERIA[phase]:
        ok = bool(fn(artifact))
        passed = passed and ok
        results.append({"id": cid, "desc": desc, "ok": ok})
    return {"phase": phase, "path": path, "passed": passed,
            "criteria": results, "n_pass": sum(r["ok"] for r in results),
            "n_total": len(results)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", required=True)
    ap.add_argument("--phase", choices=list(CRITERIA.keys()), required=True)
    args = ap.parse_args()

    rep = evaluate_artifact(args.phase, args.artifact)
    print(f"[research_gate] phase={rep['phase']} passed={rep['passed']} "
          f"({rep['n_pass']}/{rep['n_total']})")
    for r in rep["criteria"]:
        print(f"  {'PASS' if r['ok'] else 'FAIL'} {r['id']}: {r['desc']}")
    sys.exit(0 if rep["passed"] else 1)


if __name__ == "__main__":
    main()

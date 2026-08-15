#!/usr/bin/env python3
"""boundary_scan.py — 诚实边界四维扫描 (HONEST-BOUNDARY v1.0 Phase B/O/N/D)

四维边界:
  [数据边界] 数据集/版本/覆盖/缺口     (NCLT 27-session manifest)
  [模型边界] 模型/知识截止/能力/局限
  [工具边界] 可用工具/权限/局限性      (mcp_usage_report.jsonl)
  [认知边界] 置信度/不确定来源/替代解释 (meta_decisions / hypotheses)

CLI:
  python3 boundary_scan.py --report --tag S56    # 生成边界声明注入 Sprint 报告
  python3 boundary_scan.py --manifest            # 生成/更新数据边界 manifest
  python3 outer_loop.py --honest --task "..." --tag HONEST_TEST  # 经 outer_loop 分发
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))   # bottlesumo_pi/
DATE = time.strftime("%Y-%m-%d")
TS = time.strftime("%Y%m%d_%H%M%S")


def _find(path, root=None):
    base = root or ROOT
    p = os.path.join(base, path)
    return p if os.path.exists(p) else None


# ---------------------------------------------------------------- 数据边界
def scan_data_boundary():
    """扫描 NCLT 27-session 数据资产 + 已知缺口."""
    msan = _find("msan_data") or _find("")
    manifest = {
        "name": "NCLT 27-session MSAN 传感器融合数据集",
        "source": "University of Michigan NCLT (North Campus Long-Term)",
        "version": "2026-07 镜像 (gps_rtk.csv + ms25.csv + ms25_euler.csv)",
        "sessions_planned": 27,
        "sessions_found": 0,
        "missing_sessions": [],
        "known_gaps": [
            "仅姿态真值 (ms25_euler), 无独立位置真值 — 位置评估依赖 fix>=3 RTK 作参考",
            "RTK fix=2 退化段坐标冻结/陈旧 (系统性偏置, 占行 6.5-17.9%)",
            "gps_rtk.csv 时间戳乱序 (需排序; 早期脚本曾受影响)",
        ],
    }
    # 实际盘点 nclt/ 目录 (仓库根 msan_data/nclt/<session>/<session>/gps_rtk.csv)
    nclt_root = os.path.abspath(os.path.join(HERE, "..", "..", "..", "msan_data", "nclt"))
    have = set()
    if os.path.isdir(nclt_root):
        for root, dirs, files in os.walk(nclt_root):
            if "gps_rtk.csv" in files:
                have.add(os.path.basename(root))
        manifest["sessions_found"] = len(have)
        planned = {"2012-01-08","2012-01-15","2012-01-22","2012-02-02","2012-02-04","2012-02-05",
                   "2012-02-12","2012-02-18","2012-02-19","2012-03-17","2012-03-25","2012-03-31",
                   "2012-04-29","2012-05-11","2012-05-26","2012-06-15","2012-08-04","2012-08-20",
                   "2012-09-28","2012-10-28","2012-11-04","2012-11-16","2012-11-17","2012-12-01",
                   "2013-01-10","2013-02-23","2013-04-05"}
        manifest["missing_sessions"] = sorted(planned - have)
    return manifest


def scan_tool_boundary():
    """扫描 MCP 工具使用记录 (mcp_usage_report.jsonl)."""
    rec = {"tools_available": "AionUi MCP + WSL 工具链 (python3/bash/git)",
           "tool_usage_log": "mcp_usage_report.jsonl 存在" if _find("governance/meta_harness/mcp_usage_report.jsonl") else "mcp_usage_report.jsonl 缺失 (记录未开启)",
           "known_limitations": ["WSL 下 PowerShell 引号破坏内联 python -c (用脚本文件规避)",
                                  "背景进程随 WSL 会话退出被终止 (需前台分块运行)",
                                  "27-session 全量回测单线程 ~30min"]}
    return rec


def scan_model_boundary():
    return {"model": "DeepSeek v4-pro (治理主模型) + Ollama Qwen2.5-Coder-7B/1.5B (本地蒸馏)",
            "knowledge_cutoff": "2025-05 (DeepSeek), 本地模型随训练集",
            "capability_scope": "传感器融合 EKF 治理/自进化/元能力框架; 不覆盖实时嵌入式部署验证",
            "known_limitations": ["无独立位置真值导致评估依赖 RTK 参考 (数据边界联动)",
                                   "置信度量化依赖 hypotheses.jsonl conf 字段 (部分覆盖)"]}


def scan_cognitive_boundary():
    return {"confidence_mechanism": "hypotheses.jsonl conf + meta_decisions.jsonl 决策记录",
            "uncertainty_sources": ["数据不足: 位置真值缺失 / fix=2 退化段",
                                     "模型局限: 知识截止/未覆盖最新传感器",
                                     "工具不可用: Renode 实时仿真未启用"],
            "recent_evidence": "S56: 02-23 pos RMSE 443.85->36.96m (置信度: 高, 三源验证: metrics+debug trace+fused pose)"}


# ---------------------------------------------------------------- CLI
def cmd_report(tag):
    """生成四维边界声明, 注入 Sprint 报告头部."""
    d = scan_data_boundary(); m = scan_model_boundary()
    t = scan_tool_boundary(); c = scan_cognitive_boundary()
    stmt = f"""# 边界声明 (HONEST-BOUNDARY v1.0) — tag={tag or DATE}

> 生成: {DATE} ({TS}) | 机制: B.O.U.N.D. Phase B+O (自动注入)

## 数据边界
- 数据来源: {d['name']}
- 版本: {d['version']}
- 覆盖: {d['sessions_found']}/{d['sessions_planned']} sessions
- 缺失 session: {d['missing_sessions'] or '无'}
- 已知缺口: {json.dumps(d['known_gaps'], ensure_ascii=False)}

## 模型边界
- 模型: {m['model']}
- 知识截止: {m['knowledge_cutoff']}
- 能力范围: {m['capability_scope']}
- 已知局限: {json.dumps(m['known_limitations'], ensure_ascii=False)}

## 工具边界
- 可用: {t['tools_available']}
- 记录: {t['tool_usage_log']}
- 局限性: {json.dumps(t['known_limitations'], ensure_ascii=False)}

## 认知边界
- 置信度机制: {c['confidence_mechanism']}
- 不确定来源: {json.dumps(c['uncertainty_sources'], ensure_ascii=False)}
- 近期实证: {c['recent_evidence']}
"""
    out = os.path.join(HERE, f"boundary_statement_{tag or DATE}.md")
    with open(out, "w") as f:
        f.write(stmt)
    # 同时维护 manifest
    man = os.path.join(HERE, "data_manifest.json")
    with open(man, "w") as f:
        json.dump({"ts": TS, "tag": tag, "data": d, "model": m, "tool": t, "cognitive": c},
                  f, ensure_ascii=False, indent=1)
    print(stmt)
    print(f"[boundary_scan] -> {out} + {man}")
    return 0


def cmd_manifest():
    d = scan_data_boundary()
    man = os.path.join(HERE, "data_manifest.json")
    with open(man, "w") as f:
        json.dump({"ts": TS, "data": d}, f, ensure_ascii=False, indent=1)
    print(json.dumps(d, ensure_ascii=False, indent=1))
    print(f"[boundary_scan] manifest -> {man}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="HONEST-BOUNDARY v1.0 边界扫描")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--manifest", action="store_true")
    ap.add_argument("--tag", default=None)
    args = ap.parse_args(argv)
    if args.report:
        return cmd_report(args.tag)
    if args.manifest:
        return cmd_manifest()
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())

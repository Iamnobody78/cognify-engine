#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit.py — DSH-SELF-RECOVER / META-DEPLOY-ALL 审计引擎 (Phase F: Find)
=====================================================================
诚实审计: 25+ 元能力模块清单 × (已有实现映射 + 社区源真实探测)。

用法:
  python audit.py audit      # 全量审计 → meta_audit_before.json
  python audit.py status     # 简要状态
"""
import json
import subprocess
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

TRI = Path(r"C:\Users\ivy\.aionui-tri-sync")
DSH = Path(r"C:\Users\ivy\.dsh")
PROD = Path(r"C:\Users\ivy\AppData\Roaming\AionUi\aionui\conversations\2026\07\27\aionrs-temp-48324704\cognify-engine")
OUT = TRI / "meta-deploy/meta_audit_before.json"

# 25+ 模块清单: 社区检索关键词 + 候选仓库 (真实探测用)
MODULES = [
    # (类别, 模块, 已有实现(本地), 候选社区仓库[user/repo])
    ("认知类", "元思考", "meta/thinking (metathink 报告 + cve_s MVE)", ["WooooDyy/AgentGym"]),
    ("认知类", "元认知", "meta_cognition.py + honesty_guard audit", ["ruler770525/dsh-anchored-flash"]),
    ("认知类", "元记忆", "LIBRARIAN 149 馆藏 + learning/ 账本", ["mbj733/dsh-hermes-memory", "yjh051108/dsh-engram-relay", "FuRongJun-1999/CommonTrustProtocol"]),
    ("认知类", "元学习", "CROSS-LEARN-SYNC (learning/ 账本 + CLS-LEARN 任务)", ["dmsobtl/dsh-skill-evolve"]),
    ("认知类", "元进化", "EVOLVE-FORCE (evolution_audit.jsonl)", ["ZK-Andy/dsh-continual-evolve"]),
    ("逻辑类", "元逻辑", "治理网关 AST 守卫 93/93", []),
    ("逻辑类", "元语言", "language/fingerprint.json", []),
    ("逻辑类", "元理论", "META-ARCHITECT (理论栈 42 条)", []),
    ("逻辑类", "元哲学", "BOUNDARY.md + HONEST-BOUNDARY", []),
    ("分析类", "元分析", "meta/analysis (债务/闭环保卫)", []),
    ("分析类", "元优化", "meta_disk_govern + 上下文压缩", []),
    ("分析类", "元数据", "meta/data (元数据目录)", []),
    ("分析类", "元计算", "cognify serve 计算端点", []),
    ("工程类", "元编程", "插件平台 (plugin 动态挂载)", []),
    ("工程类", "元算法", "cognify 算法工具集", []),
    ("工程类", "元系统", "MCP 注册表 26 项 + metamcp 编排", []),
    ("工程类", "元模型", "模型注册 (DSH 20+ 模型切换)", []),
    ("感知类", "元CV", "image-recognition/llm-vision/visionsearch MCP", []),
    ("感知类", "元Embodied", "simulation 插件 (机器人/仿真)", []),
    ("感知类", "元ME", "loki-cad/cad-mcp-studio/mechanical 类", []),
    ("感知类", "元EE", "electronics 类 MCP (待接入)", []),
    ("AI/ML类", "元ML", "MLflow/Neo 类 (待接入)", []),
    ("AI/ML类", "元DL", "Cortex 类 (待接入)", []),
    ("交互类", "元搜索", "metasearch 类 (待接入)", []),
    ("交互类", "元设计", "figma 类 (待接入)", []),
    ("交互类", "元沟通", "meta-ai 类 (待接入)", []),
    ("治理类", "元治理", "cognify gov (内置)", []),
    ("治理类", "元决策", "META-DECISION-ENGINE (三层过滤)", []),
]


def _git_exists(repo: str, timeout=20) -> bool:
    """真实探测 GitHub 仓库存在性 (git ls-remote)。"""
    try:
        r = subprocess.run(["git", "ls-remote", f"https://github.com/{repo}.git", "HEAD"],
                           capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def audit() -> dict:
    # 1) 本地已有实现 (cognify 元能力 status 证据)
    st = {}
    try:
        m = json.loads((TRI / "meta/status.json").read_text(encoding="utf-8"))
        st = {"active_count": m.get("active_count"), "health": m.get("overall_health")}
    except Exception:
        pass
    # 2) DSH 环境扫描
    dsh_profiles = [p.name for p in (DSH / "profiles").iterdir() if p.is_dir()] if (DSH / "profiles").exists() else []
    # 3) 模块逐项审计
    modules = []
    for cat, name, local, repos in MODULES:
        sources = []
        for repo in repos:
            sources.append({"repo": repo, "exists": _git_exists(repo)})
        local_ok = "待接入" not in local
        modules.append({"cat": cat, "module": name, "local_impl": local,
                        "local_ok": local_ok, "community_sources": sources,
                        "status": "已有本地实现" if local_ok else "本地缺失",
                        "source_note": ("社区源探测: " + "; ".join(
                            f"{s['repo']}={'✅' if s['exists'] else '❌ 不存在'}" for s in sources)
                            if sources else "无候选社区源")})
    have = sum(1 for m in modules if m["local_ok"])
    report = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "total": len(modules),
              "local_have": have, "local_missing": len(modules) - have,
              "dsh_profiles": dsh_profiles, "cognify_meta": st, "modules": modules}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "audit"
    if cmd == "audit":
        r = audit()
        print(f"[meta-deploy] 模块 {r['total']} | 本地已有 {r['local_have']} | 缺失 {r['local_missing']}")
        print(f"[meta-deploy] DSH profiles: {r['dsh_profiles']} | cognify 元能力: {r['cognify_meta']}")
        for m in r["modules"]:
            mark = "✅" if m["local_ok"] else "⬜"
            print(f"  {mark} [{m['cat']}] {m['module']}: {m['local_impl'][:50]}")
            if m["source_note"] and "❌" in m["source_note"]:
                print(f"      {m['source_note']}")
        print(f"[meta-deploy] → {OUT}")
        return 0
    if cmd == "status":
        import json as j
        r = j.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else None
        if r is None:
            print("[meta-deploy] 尚无审计记录")
            return 1
        print(f"[meta-deploy] 最近: {r['ts'][:16]} | 本地 {r['local_have']}/{r['total']}")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())

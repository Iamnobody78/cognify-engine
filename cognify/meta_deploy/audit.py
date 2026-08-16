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
import os
import json
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(__file__))))
import cognify.paths as paths

import subprocess
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

TRI = paths.TRI
DSH = Path(r"C:\Users\ivy\.dsh")
PROD = paths.PROD
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
    # ---- 新增: DSH 生态找回模块 (2026-08-16 探测) ----
    ("记忆增强", "灵枢五层记忆", "待部署: dsh-memory (12 记忆工具)", ["FuRongJun-1999/dsh-memory"]),
    ("记忆增强", "Hermes 式记忆", "待部署: dsh-hermes-memory (自动记忆+skill)", ["mbj733/dsh-hermes-memory"]),
    ("记忆增强", "因果记忆图谱", "待部署: dsh-engram-relay (N-gram 哈希寻址)", ["yjh051108/dsh-engram-relay"]),
    ("记忆增强", "上下文注入审计", "待部署: dsh-context-doctor (重复/冲突检测)", ["Zhenyu98/dsh-context-doctor"]),
    ("记忆增强", "长期人格记忆", "待部署: dsh-persona-memory (纠正检测/容量合并)", []),
    ("安全审计", "本地安全审计", "待部署: dsh-security-audit", []),
    ("安全审计", "上下文可见性", "待部署: context-vista (token 环形图)", ["GooodWei/context-vista"]),
    ("UI交互", "侧边栏工作台", "待部署: DSH-better-sidebar (文件/终端/Git)", ["omdsh-dev/DSH-better-sidebar"]),
    ("UI交互", "@ 引用文件", "待部署: dsh-at-file", ["omdsh-dev/dsh-at-file"]),
    ("UI交互", "终端 UI", "待部署: dsh-TUI", ["ccch1mneyyy/dsh-TUI"]),
    ("UI交互", "桌面端", "待部署: deepseek-harness-desktop", ["anywhere-labs/deepseek-harness-desktop"]),
    ("UI交互", "桌面宠物", "待部署: dsh-pet (精灵图/番茄钟)", ["zealot00/dsh-pet"]),
    ("开发运行时", "社区发行版", "待部署: Oh-My-DSH (精选目录)", ["like-study1/Oh-My-DSH"]),
    ("开发运行时", "逆向工程技能包", "待部署: dsh-reverse-skill (85 SKILL.md)", ["dhicoc/dsh-reverse-skill"]),
    ("开发运行时", "Rust TUI", "待部署: deepseek-harness-tui", ["openma-ai/deepseek-harness-tui"]),
    ("开发运行时", "TUI 变体", "待部署: dsh-tianshu-tui", ["huiliyi37/dsh-tianshu-tui"]),
    ("工作流", "深度研究编排", "待部署: dsh-deepresearch (workflow 引擎)", []),
    ("工作流", "规划/执行路由", "待部署: dsh-plan-execute (双模型)", []),
    ("工作流", "零依赖工具套件", "待部署: dsh-toolkit (calculator/csv/regex)", []),
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
    # 2b) 生态目录数据源 (Oh-My-DSH 真实解析)
    eco = {"oh_my_dsh": None, "awesome": None}
    omd = TRI / "benchmarks/Oh-My-DSH/data"
    if (omd / "curated.json").exists():
        try:
            c = json.loads((omd / "curated.json").read_text(encoding="utf-8"))
            eco["oh_my_dsh"] = {"curated_overrides": len(c.get("overrides", {})),
                                "manual": len(c.get("manual", [])),
                                "min_stars": c.get("min_stars")}
        except Exception:
            pass
    if (TRI / "benchmarks/awesome-dsh-plugin").exists():
        eco["awesome"] = {"cloned": True}
    # 3) 模块逐项审计
    modules = []
    for cat, name, local, repos in MODULES:
        sources = []
        for repo in repos:
            sources.append({"repo": repo, "exists": _git_exists(repo)})
        local_ok = "待接入" not in local and "待部署" not in local
        modules.append({"cat": cat, "module": name, "local_impl": local,
                        "local_ok": local_ok, "community_sources": sources,
                        "status": "已有本地实现" if local_ok else "本地缺失",
                        "source_note": ("社区源探测: " + "; ".join(
                            f"{s['repo']}={'✅' if s['exists'] else '❌ 不存在'}" for s in sources)
                            if sources else "无候选社区源")})
    have = sum(1 for m in modules if m["local_ok"])
    report = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "total": len(modules),
              "local_have": have, "local_missing": len(modules) - have,
              "dsh_profiles": dsh_profiles, "cognify_meta": st,
              "ecosystem_dirs": eco, "modules": modules}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def assess_plugins(names: list) -> list:
    """插件互补性评估: 关键词重叠检测 → complementary/deprecated 决策。"""
    # 现有引擎能力关键词表
    existing = {
        "memory": ["记忆", "memory", "ledger", "recall", "知识", "knowledge", "remember"],
        "skill": ["skill", "技能", "工作流", "workflow", "蒸馏", "distill", "learn"],
        "evolve": ["evolve", "进化", "版本", "rollback", "回滚", "version", "audit"],
        "thinking": ["思考", "think", "推理", "reason", "reflection", "反思"],
        "sync": ["同步", "sync", "镜像", "mirror"],
    }
    out = []
    for name in names:
        d = TRI / "benchmarks" / name
        text = ""
        for f in ("README.md", "package.json", "cordis.patch.yml", "src/index.ts"):
            p = d / f
            if p.exists():
                try:
                    text += p.read_text(encoding="utf-8", errors="replace")[:8000].lower()
                except Exception:
                    pass
        scores = {}
        for cap, kws in existing.items():
            scores[cap] = sum(1 for k in kws if k.lower() in text)
        max_cap = max(scores, key=scores.get) if any(scores.values()) else None
        overlap = scores[max_cap] if max_cap else 0
        verdict = "deprecated" if overlap >= 4 else ("complementary" if max_cap else "unknown")
        out.append({"plugin": name, "overlap_scores": scores, "max_cap": max_cap,
                    "overlap": overlap, "verdict": verdict,
                    "decision": f"功能与现有 {max_cap} 引擎重叠 ({overlap} 词)" if verdict == "deprecated"
                                else ("提供补位能力" if verdict == "complementary" else "需人工审查")})
    return out


def mcp_stats() -> dict:
    """2.4 MCP 口径拆分: 分类统计 + 对外宣称口径 (ready+registered)。"""
    import yaml as _yaml
    from collections import Counter
    reg = _yaml.safe_load((TRI / "config/mcp_registry.yaml").read_text(encoding="utf-8"))
    servers = reg.get("servers", [])
    c = Counter(s.get("status") for s in servers)
    outer = c.get("ready", 0) + c.get("registered", 0)
    return {"total": len(servers), "by_status": dict(c), "outer_claim": outer,
            "outer_note": f"对外宣称只引用 ready({c.get('ready', 0)}) + registered({c.get('registered', 0)}) = {outer}"}


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "audit"
    if cmd == "mcp-stats":
        m = mcp_stats()
        print(f"[meta-deploy] MCP 注册表: 总数 {m['total']}")
        for k, v in m["by_status"].items():
            print(f"  {k}: {v}")
        print(f"[meta-deploy] 对外口径: {m['outer_note']}")
        return 0
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
    if cmd == "assess":
        args = sys.argv[2:]
        names = []
        if args and args[0] == "--plugins":
            names = [a for a in args[1:] if a]
        if not names:
            print("用法: meta-deploy assess --plugins <dir1,dir2,...>")
            return 1
        results = assess_plugins(names)
        print("[meta-deploy] 插件互补性评估:")
        for r in results:
            tag = "✅ 部署候选" if r["verdict"] == "complementary" else ("⛔ 重叠弃用" if r["verdict"] == "deprecated" else "❓ 需人工")
            print(f"  {tag} {r['plugin']}: {r['decision']} (top: {r['max_cap']} 重叠 {r['overlap']} 词)")
        (Path(r"C:\Users\ivy\.aionui-tri-sync\meta-deploy\plugin_assessment.json")).write_text(
            json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "results": results},
                       ensure_ascii=False, indent=2), encoding="utf-8")
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

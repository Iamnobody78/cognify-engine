"""S62 R1-A2: .aionui 记忆库脚手架生成器.

来自 Notion "Aionui 记忆库设计" 页 (N3): tools/config/context/sessions/templates
五目录 + README.md + manifest.json + 每文件模板.
设计: dry-run 模式 (只打印结构, 不写盘) + 实跑模式 (生成到目标目录).

Run:
  python3 governance/memory_scaffold.py --dry-run
  python3 governance/memory_scaffold.py --target /path/to/.aionui  (default: governance/memory_demo/)
"""
import argparse
import json
import os
import sys
from datetime import date

# N3 页面目录方案
SCAFFOLD = {
    "tools": {
        "installed.md": "# 已安装工具清单\n\n| 工具 | 版本 | 用途 | 验证 |\n|---|---|---|---|\n",
        "mcp_servers.md": "# MCP 服务器\n\n| 服务器 | 状态 | 端口 |\n|---|---|---|\n",
        "cli_tools.md": "# CLI 工具\n\n| 命令 | 说明 |\n|---|---|\n",
    },
    "config": {
        "agent_preferences.md": "# Agent 偏好\n\n- 沟通风格: \n- 决策偏好: \n",
        "project_config.md": "# 项目配置\n\n| 键 | 值 |\n|---|---|\n",
        "dependencies.md": "# 依赖清单\n\n- \n",
    },
    "context": {
        "project_overview.md": "# 项目概述\n\n- 目标: \n- 范围: \n",
        "current_state.md": "# 当前状态\n\n- 进度: \n- 阻塞: \n",
        "decision_log.md": "# 决策记录\n\n| 日期 | 决策 | 理由 | 后果 |\n|---|---|---|---|\n",
        "lessons_learned.md": "# 经验教训\n\n| 日期 | 事件 | 教训 |\n|---|---|---|\n",
    },
    "sessions": {
        "README.md": "# 会话索引\n\n| 会话 | 日期 | 主题 | 摘要 |\n|---|---|---|---|\n",
    },
    "templates": {
        "prompt_template.md": "# 提示词模板\n\n## 任务\n\n## 约束\n\n## 输出\n",
        "report_template.md": "# 报告模板\n\n## 结论\n\n## 数据\n\n## 风险\n",
        "review_template.md": "# 审查模板\n\n## 通过/拒绝\n\n## 理由\n",
    },
}

TOTAL_FILE_COUNT = sum(len(v) for v in SCAFFOLD.values()) + 2  # README.md + manifest.json

ROOT_FILES = {
    "README.md": "# .aionui 记忆库\n\n本项目使用 .aionui/ 目录持久化跨会话上下文。\n\n"
                 "## 目录\n\n- `tools/`: 已安装工具清单\n- `config/`: Agent 配置与偏好\n"
                 "- `context/`: 项目状态与决策记录\n- `sessions/`: 会话索引与摘要\n"
                 "- `templates/`: 可复用模板\n\n## 新会话恢复\n\n读取 `context/current_state.md` "
                 "+ `context/decision_log.md` 恢复上下文。\n",
    "manifest.json": json.dumps({
        "schema_version": "1.0",
        "name": ".aionui memory scaffold",
        "source": "notion:N3 (Aionui 记忆库设计)",
        "created": str(date.today()),
        "dirs": list(SCAFFOLD.keys()),
        "file_count": TOTAL_FILE_COUNT,
    }, ensure_ascii=False, indent=2),
}


def scaffold(target: str, dry_run: bool = False) -> dict:
    """Generate the .aionui/ scaffold under target. Returns {path: action}."""
    actions = {}
    if dry_run:
        actions[target] = "dry-run (no writes)"
    else:
        os.makedirs(target, exist_ok=True)

    for fname, content in ROOT_FILES.items():
        p = os.path.join(target, fname)
        if dry_run:
            actions[p] = "would-write"
        else:
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
            actions[p] = "written"

    for dname, files in SCAFFOLD.items():
        dpath = os.path.join(target, dname)
        if dry_run:
            actions[dpath] = "would-mkdir"
        else:
            os.makedirs(dpath, exist_ok=True)
            actions[dpath] = "mkdir"
        for fname, content in files.items():
            p = os.path.join(dpath, fname)
            if dry_run:
                actions[p] = "would-write"
            else:
                with open(p, "w", encoding="utf-8") as f:
                    f.write(content)
                actions[p] = "written"
    return actions


def verify(target: str) -> dict:
    """Verify scaffold integrity: all dirs/files exist, manifest JSON valid."""
    report = {"dirs_ok": 0, "dirs_total": len(SCAFFOLD), "files_ok": 0,
              "files_total": sum(len(v) for v in SCAFFOLD.values()) + len(ROOT_FILES),
              "manifest_valid": False}
    for d in SCAFFOLD:
        if os.path.isdir(os.path.join(target, d)):
            report["dirs_ok"] += 1
    for d, files in SCAFFOLD.items():
        for f in files:
            if os.path.isfile(os.path.join(target, d, f)):
                report["files_ok"] += 1
    for f in ROOT_FILES:
        if f == "manifest.json":
            p = os.path.join(target, f)
            if os.path.isfile(p):
                try:
                    json.load(open(p, encoding="utf-8"))
                    report["manifest_valid"] = True
                    report["files_ok"] += 1
                except Exception:
                    pass
        elif os.path.isfile(os.path.join(target, f)):
            report["files_ok"] += 1
    report["complete"] = (report["dirs_ok"] == report["dirs_total"] and
                          report["files_ok"] == report["files_total"] and
                          report["manifest_valid"])
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", default=None, help="output dir (default governance/memory_demo)")
    ap.add_argument("--dry-run", action="store_true", help="print plan, write nothing")
    args = ap.parse_args()

    target = args.target or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "memory_demo")
    actions = scaffold(target, dry_run=args.dry_run)
    n_write = sum(1 for a in actions.values() if "write" in a)
    print(f"[A2] {'dry-run plan' if args.dry_run else 'scaffolded'} {target}: "
          f"{len(actions)} paths ({n_write} file writes)")

    if not args.dry_run:
        rep = verify(target)
        print(f"[A2] verify: dirs {rep['dirs_ok']}/{rep['dirs_total']}, "
              f"files {rep['files_ok']}/{rep['files_total']}, "
              f"manifest_valid={rep['manifest_valid']}, complete={rep['complete']}")
        sys.exit(0 if rep["complete"] else 1)


if __name__ == "__main__":
    main()

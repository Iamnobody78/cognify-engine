# -*- coding: utf-8 -*-
"""environment_bootstrap_server.py — P1-3 MCP 服务器: 环境引导封装.

对齐 SuperagenticAI/metaharness 的自动环境引导快照 + 写作用域强制。
封装 P1-2 模块:
- build_environment_snapshot(): 结构化快照 (git_head/文件 size+mtime/工具/磁盘)
- save_candidate_workspace(): 候选工作空间四件套
- ALLOWED_WRITE_PATHS: 写作用域白名单 (双层防御)

工具:
- environment_snapshot : 采集当前环境快照 (对齐 Terminal-Bench 2.0 格式)
- check_write_scope    : 校验目标文件是否在写作用域白名单内
- candidate_workspace  : 创建候选工作空间 (snapshot/proposal/diff 落盘)

启动: python -m mcp_servers.environment_bootstrap_server (stdio)
"""
import json
import os
import sys

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("需要 MCP SDK: pip install mcp", file=sys.stderr)
    sys.exit(1)

META_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, META_DIR)

mcp = FastMCP(
    "environment-bootstrap",
    instructions="BottleSumo 环境引导: 环境快照 + 写作用域强制 + 候选工作空间",
)


@mcp.tool()
def environment_snapshot() -> str:
    """采集当前环境快照 (对齐 Terminal-Bench 2.0 格式).

    Returns:
        JSON: {repo_root, python, model, git_head, harness_files_ready,
               files(size/mtime), tools, disk_free_gb, ts}
    """
    try:
        import code_agent_proposer as cap
        snap = cap.build_environment_snapshot()
        return json.dumps(snap, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
def check_write_scope(target_file: str) -> str:
    """校验目标文件是否在写作用域白名单内 (P1-2 双层防御).

    Args:
        target_file: 目标相对路径 (如 simulation/lightweight_env.py)
    Returns:
        JSON: {allowed, target, policy, reason}
    """
    try:
        import code_agent_proposer as cap
        norm = target_file.replace("\\", "/")
        allowed = norm in cap.ALLOWED_WRITE_PATHS
        return json.dumps({
            "allowed": allowed,
            "target": norm,
            "policy": "allowed_write_paths = Harness 五文件",
            "whitelist": sorted(cap.ALLOWED_WRITE_PATHS),
            "reason": None if allowed else "越权: 目标不在写作用域白名单",
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@mcp.tool()
def candidate_workspace(candidate_id: str, proposals: str = "[]") -> str:
    """创建候选工作空间 (Filesystem Run Store).

    Args:
        candidate_id: 候选 ID (如 ca_rules_20260807_001)
        proposals: JSON 数组字符串 [{id,layer,target_file,hypothesis,evidence,
                   bloodline,diff:[{old,new}]}]
    Returns:
        JSON: {workspace, files: {snapshot.json, proposal.md, diff.patch},
               gate_result: 待评估回写}
    """
    try:
        import code_agent_proposer as cap
        snap = cap.build_environment_snapshot()
        try:
            props = json.loads(proposals) if isinstance(proposals, str) else proposals
        except json.JSONDecodeError:
            props = []
        ws = cap.save_candidate_workspace(candidate_id, snap, props)
        files = {}
        for fname in ("snapshot.json", "proposal.md", "diff.patch"):
            fp = os.path.join(ws, fname)
            files[fname] = {"size": os.path.getsize(fp),
                            "path": fp} if os.path.exists(fp) else None
        return json.dumps({
            "workspace": ws,
            "files": files,
            "gate_result": "pending (评估后由 outer_loop 回写)",
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run(transport="stdio")

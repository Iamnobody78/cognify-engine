#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mcp_sync.py — 三方 MCP 统一同步器 (书同文车同轨 · 一处配置三处使用)
==================================================================
读取 config/mcp_registry.yaml (status=ready) → 同步到:
  - Hermes: AppData/Local/hermes/config.yaml → mcp_servers
  - AionUi: aionui-backend.db → mcp_servers 表
  - DSH:    无原生 MCP 客户端 (cordis 插件架构) → 注册表参考 + cognify profile 文档

幂等: 已存在的服务器跳过 (同名), 可重复运行。

用法: python mcp_sync.py [--dry-run]
"""
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

TRI = Path(r"C:\Users\ivy\.aionui-tri-sync")
REGISTRY = TRI / "config/mcp_registry.yaml"
HERMES_CFG = Path(r"C:\Users\ivy\AppData\Local\hermes\config.yaml")
AIONUI_DB = Path(r"C:\Users\ivy\AppData\Roaming\AionUi\aionui\aionui-backend.db")
USER_ID = "user_019fe0c8-bc20-71d2-a01e-f93e97cc51b3"
DSH_PROFILE = Path(r"C:\Users\ivy\.dsh\profiles\cognify")

DRY = "--dry-run" in sys.argv


def load_registry() -> list:
    import yaml
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8")).get("servers", [])


def gh_token() -> str:
    try:
        r = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True,
                           timeout=30)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:  # noqa: BLE001
        return ""


def sync_hermes(servers) -> list:
    """Hermes: config.yaml mcp_servers 合并 (幂等)。"""
    added = []
    txt = HERMES_CFG.read_text(encoding="utf-8")
    for s in servers:
        if "hermes" not in s.get("systems", []):
            continue
        name = s["id"]
        if f"\n  {name}:" in txt or f"  {name}:" in txt.split("mcp_servers:")[-1]:
            continue
        args = "".join(f"\n    - {json.dumps(a)}" for a in s.get("args", []))
        env = ""
        for k, v in (s.get("env") or {}).items():
            if k == "GITHUB_PERSONAL_ACCESS_TOKEN" and v == "<gh-auth-token>":
                v = gh_token()
            if v:
                env += f"\n    {k}: {v}"
        block = f"\n  {name}:\n    command: {s['command']}\n    args:{args}{env}\n    enabled: true"
        # 插入到 mcp_servers: 之后第一行 (对齐 2 空格缩进)
        marker = "mcp_servers:"
        idx = txt.index(marker) + len(marker)
        txt = txt[:idx] + block + "\n" + txt[idx:]
        added.append(name)
    if added and not DRY:
        HERMES_CFG.write_text(txt, encoding="utf-8")
    return added


def sync_aionui(servers) -> list:
    """AionUi: mcp_servers 表插入 (幂等)。"""
    added = []
    import sqlite3
    con = sqlite3.connect(AIONUI_DB)
    cur = con.cursor()
    for s in servers:
        if "aionui" not in s.get("systems", []):
            continue
        name = s["id"]
        exists = cur.execute("SELECT id FROM mcp_servers WHERE name=? AND deleted_at IS NULL",
                             (name,)).fetchone()
        if exists:
            continue
        cfg = {"command": s["command"], "args": s.get("args", [])}
        env = {}
        for k, v in (s.get("env") or {}).items():
            if k == "GITHUB_PERSONAL_ACCESS_TOKEN" and v == "<gh-auth-token>":
                v = gh_token()
            if v:
                env[k] = v
        if env:
            cfg["env"] = env
        now = str(int(__import__("time").time() * 1000))
        cur.execute(
            "INSERT INTO mcp_servers (id, user_id, name, description, enabled, transport_type, "
            "transport_config, tools, last_test_status, last_connected, original_json, builtin, "
            "deleted_at, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, '1', 'stdio', ?, NULL, 'pending', NULL, ?, '0', NULL, ?, ?)",
            (f"mcp_{uuid.uuid4()}", USER_ID, name, f"Unified MCP: {name} (mcp_registry.yaml)",
             json.dumps(cfg), json.dumps({"mcpServers": {name: cfg}}, ensure_ascii=False, indent=2),
             now, now))
        added.append(name)
    if added and not DRY:
        con.commit()
    con.close()
    return added


def sync_dsh(servers) -> list:
    """DSH: 无原生 MCP 客户端 → 注册表参考写入 cognify profile (诚实边界)。"""
    ready = [s["id"] for s in servers if "dsh" in s.get("systems", []) or s["status"] == "ready"]
    lines = [
        "# DSH MCP 参考 (UNIFIED MCP REGISTRY)",
        "",
        "DSH 使用 cordis 插件架构 (无原生 MCP 客户端)。MCP 能力经以下路径可用:",
        "",
        "- **cognify MCP 桥** (Hermes 侧注册, DSH 可经 ACP 复用): cognify_governance/cognitive/sync/meta/debt",
        "- **注册表**: ~/.aionui-tri-sync/config/mcp_registry.yaml (一处配置三处使用)",
        "- **ready 服务器** (npx 免安装, 经 bash 直接调用): " + ", ".join(ready),
        "- **待接入** (凭据/软件/硬件): 见注册表 status 字段",
    ]
    f = DSH_PROFILE / "MCP_REFERENCE.md"
    if not DRY:
        f.write_text("\n".join(lines), encoding="utf-8")
    return ready


def main() -> int:
    servers = load_registry()
    ready = [s for s in servers if s.get("status") == "ready"]
    hermes_added = sync_hermes(ready)
    aionui_added = sync_aionui(ready)
    dsh_ref = sync_dsh(ready)
    print(f"[mcp-sync] 注册表 {len(servers)} 项 | ready {len(ready)}")
    print(f"[mcp-sync] Hermes 新增: {hermes_added or '无 (幂等)'}")
    print(f"[mcp-sync] AionUi 新增: {aionui_added or '无 (幂等)'}")
    print(f"[mcp-sync] DSH 参考: {len(dsh_ref)} 项 → profiles/cognify/MCP_REFERENCE.md")
    rep = {"ts": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
           "registry": len(servers), "ready": len(ready),
           "hermes_added": hermes_added, "aionui_added": aionui_added}
    (TRI / "adaptation/mcp_sync_report.json").write_text(
        json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DSH-INHERIT-DEBT v1.1 引擎 — 债务库数据/逻辑解耦版
==================================================
v1.1 (2026-08-15 元思考): 债务库从代码硬编码迁至 debt/debt_library.yaml。
引擎只负责: 加载 YAML -> 解析路径令牌 -> 执行检查注册表 -> 生成报告。
检查类型: has | contains | port | not_port | never
路径令牌: WS=工作区 TRI=tri-sync HOME=用户目录
"""
import json
import re
import socket
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass
try:
    import yaml
except ImportError:
    yaml = None

WS = Path(r"C:\Users\ivy\AppData\Roaming\AionUi\aionui\conversations\2026\07\27\aionrs-temp-48324704")
TRI = Path(r"C:\Users\ivy\.aionui-tri-sync")
HOME = Path.home()
DEBT = TRI / "debt"
LIBRARY = DEBT / "debt_library.yaml"
NOW = datetime.now()

TOKENS = {"WS": WS, "TRI": TRI, "HOME": HOME}


def resolve(path):
    for tok, base in TOKENS.items():
        if path.startswith(tok + "/"):
            return base / path[len(tok) + 1:]
    return Path(path)


# ---------------------------------------------------------------- 检查注册表
def chk_has(path, **kw):
    return resolve(path).exists()


def chk_contains(path, pattern, **kw):
    try:
        return re.search(pattern, resolve(path).read_text(
            encoding="utf-8", errors="replace")) is not None
    except OSError:
        return False


def chk_port(port, **kw):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    try:
        s.connect(("127.0.0.1", int(port)))
        return True
    except OSError:
        return False
    finally:
        s.close()


def chk_not_port(port, **kw):
    return not chk_port(port)


def chk_never(**kw):
    return False


def chk_pass(**kw):
    return True


CHECKS = {"has": chk_has, "contains": chk_contains, "port": chk_port,
          "not_port": chk_not_port, "never": chk_never, "pass": chk_pass}


def load_library():
    """从 YAML 加载债务库 (数据与逻辑解耦)。"""
    if not LIBRARY.exists():
        raise RuntimeError(f"债务库缺失: {LIBRARY}")
    data = yaml.safe_load(LIBRARY.read_text(encoding="utf-8"))
    return data.get("debts", [])


def evaluate(debt):
    """执行证据裁决: resolved_when_true=True 的检查通过 -> 已解决"""
    resolved = 0
    detail = []
    for ev in debt.get("evidence", []):
        fn = CHECKS.get(ev.get("check"))
        if fn is None:
            continue
        try:
            ok = bool(fn(**{k: v for k, v in ev.items() if k not in ("check", "resolved_when_true", "note")}))
        except Exception:
            ok = False
        rwt = bool(ev.get("resolved_when_true"))
        detail.append({"check": ev.get("check", "?"),
                       "label": ev.get("note", "") or ev.get("path", ev.get("port", "?")),
                       "ok": ok, "meaning": "resolved" if rwt else "unresolved"})
        if ok and rwt:
            resolved += 1
    if resolved:
        return "已解决", detail
    if any(d["ok"] for d in detail):
        return "部分", detail
    return "待解决", detail


MODULES = {
    "agent-governance-v2": "治理引擎", "bottlesumo-pi": "仿真模块",
    "tri-sync": "同步机制", "Hermes": "基础设施", "AionUi": "基础设施",
    "COST-CONTROL": "治理引擎", "CACHE-OPTIMIZER": "治理引擎",
    "文档": "文档/知识库", "research": "文档/知识库", "pattern-library": "文档/知识库",
    "honesty": "治理引擎", "knowledge": "文档/知识库", "基础设施": "基础设施",
    "tri-sync/MCP": "同步机制",
}


def main():
    DEBT.mkdir(parents=True, exist_ok=True)
    debts = load_library()
    inventory = []
    for d in debts:
        status, detail = evaluate(d)
        inventory.append({**{k: d.get(k) for k in
                             ("id", "dim", "sev", "module", "desc", "root",
                              "solution", "accept", "est")},
                          "status": status, "evidence": detail})
    (DEBT / "debt_inventory.json").write_text(json.dumps(
        {"generated": NOW.isoformat(timespec="seconds"), "debts": inventory},
        ensure_ascii=False, indent=2), encoding="utf-8")
    (DEBT / "debt_manifest.md").write_text("\n".join([
        "# 债务清单 (debt_manifest, YAML 驱动)", "",
        f"> {NOW.isoformat(timespec='seconds')} | 库: debt_library.yaml ({len(debts)} 条)",
        "", "| ID | 维度 | 优先级 | 模块 | 描述 | 状态 |", "|:--|:--|:--|:--|:--|:--|",
        *[f"| {d['id']} | {d['dim']} | {d['sev']} | {MODULES.get(d['module'], d['module'])} "
          f"| {d['desc'][:40]} | {d['status']} |" for d in inventory],
    ]), encoding="utf-8")
    cnt = Counter(d["status"] for d in inventory)
    print(f"[debt v1.1] {len(debts)} 条债务 (YAML 库): "
          f"已解决 {cnt.get('已解决', 0)} / 部分 {cnt.get('部分', 0)} / 待解决 {cnt.get('待解决', 0)}")
    for d in inventory:
        mark = {"已解决": "✅", "部分": "🟡", "待解决": "🔴"}[d["status"]]
        print(f"  {mark} {d['id']} [{d['sev']}] {d['desc'][:44]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

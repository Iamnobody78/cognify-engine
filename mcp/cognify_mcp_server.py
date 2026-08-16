#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cognify_mcp_server.py — Cognify MCP 服务器 (SELF-ADAPT v1.0, Hermes 适配层)
==========================================================================
MCP (Model Context Protocol) stdio 服务器, 向 Hermes 暴露 cognify 能力:

  cognify_governance  治理裁决 (五层: ALLOW/ALLOW_WITH_WARNING/ESCALATE/DENY/SUSPEND)
  cognify_cognitive   MCE 认知编译
  cognify_sync        三方同步状态
  cognify_meta        25 维元能力状态
  cognify_debt        债务扫描

协议: JSON-RPC 2.0 over stdio (Content-Length 帧), 不修改任何核心代码 (红线 3)。
"""
import json
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

PY = r"C:\Users\ivy\AppData\Local\Programs\Python\Python312\python.exe"
TRI = Path(r"C:\Users\ivy\.aionui-tri-sync")
PROD = Path(r"C:\Users\ivy\AppData\Roaming\AionUi\aionui\conversations\2026\07\27\aionrs-temp-48324704\cognify-engine")
CLI = PROD / "cli/cognify.py"

NAME = "cognify"
VERSION = "2.1.0"

TOOLS = [
    {
        "name": "cognify_governance",
        "description": "治理裁决: 对输入文本执行五层裁决 (ALLOW/ALLOW_WITH_WARNING/ESCALATE/DENY/SUSPEND)",
        "inputSchema": {"type": "object",
                        "properties": {"input": {"type": "string"}},
                        "required": ["input"]},
    },
    {
        "name": "cognify_cognitive",
        "description": "MCE 认知编译: 识别输入的主导认知模型并外化",
        "inputSchema": {"type": "object",
                        "properties": {"input": {"type": "string"}},
                        "required": ["input"]},
    },
    {
        "name": "cognify_sync",
        "description": "三方同步状态: AionUi/Hermes/DSH 守护与镜像",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "cognify_meta",
        "description": "元能力状态: 25 维元能力 active 与健康度",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "cognify_debt",
        "description": "债务扫描: 债务库存 (已解决/部分/待解决)",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _run_cli(*args, timeout=120):
    try:
        r = subprocess.run([PY, str(CLI), *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        return (r.stdout or r.stderr or "")[-800:].strip()
    except Exception as exc:  # noqa: BLE001
        return f"错误: {exc}"


def call_tool(name: str, args: dict) -> dict:
    if name == "cognify_governance":
        return {"content": [{"type": "text", "text": _run_cli("gov", "--evaluate", args.get("input", ""))}]}
    if name == "cognify_cognitive":
        return {"content": [{"type": "text", "text": _run_cli("cognitive", "--mce", args.get("input", ""))}]}
    if name == "cognify_sync":
        return {"content": [{"type": "text", "text": _run_cli("sync")}]}
    if name == "cognify_meta":
        return {"content": [{"type": "text", "text": _run_cli("meta", "--status")}]}
    if name == "cognify_debt":
        return {"content": [{"type": "text", "text": _run_cli("debt", "scan")}]}
    raise ValueError(f"未知工具: {name}")


def _read_line() -> bytes | None:
    """读一行 (含换行)。EOF 返回 None。"""
    line = sys.stdin.buffer.readline()
    return line if line else None


def _read_n(n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sys.stdin.buffer.read(n - len(buf))
        if not chunk:
            break
        buf += chunk
    return buf


def _read_message():
    """双模帧读取: 换行 JSON (新 SDK 2025-11-25+) / Content-Length (旧协议)。

    返回 (message, mode); mode ∈ {"newline", "lsp"} 用于统一响应格式。
    """
    line = _read_line()
    if line is None:
        return None, None
    stripped = line.strip()
    if not stripped:
        return _read_message()  # 跳过空行
    if stripped.startswith(b"Content-Length"):
        headers = {}
        while True:
            h = _read_line()
            if h is None:
                return None, None
            if h.strip() in (b"", b"\r"):
                break
            k, _, v = h.partition(b":")
            headers[k.strip().lower()] = v.strip()
        n = int(headers.get(b"content-length", b"0"))
        body = _read_n(n)
        return json.loads(body.decode("utf-8", errors="replace")), "lsp"
    return json.loads(stripped.decode("utf-8", errors="replace")), "newline"


_mode = {"current": "newline"}  # 默认新帧; 首条消息后按检测结果固定


def _write_frame(payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if _mode["current"] == "lsp":
        sys.stdout.buffer.write(b"Content-Length: %d\r\n\r\n" % len(body))
    sys.stdout.buffer.write(body + b"\n")
    sys.stdout.buffer.flush()


def main() -> int:
    while True:
        msg, mode = _read_message()
        if msg is None:
            break
        _mode["current"] = mode  # 按首条消息固定响应帧格式
        try:
            req = msg if isinstance(msg, dict) else {}
        except json.JSONDecodeError:
            continue
        rid = req.get("id")
        method = req.get("method", "")
        params = req.get("params", {}) or {}
        if method == "initialize":
            _write_frame({"jsonrpc": "2.0", "id": rid,
                          "result": {"protocolVersion": params.get("protocolVersion", "2025-03-26"),
                                     "capabilities": {"tools": {}},
                                     "serverInfo": {"name": NAME, "version": VERSION}}})
        elif method == "notifications/initialized":
            continue
        elif method == "ping":
            _write_frame({"jsonrpc": "2.0", "id": rid, "result": {}})
        elif method == "tools/list":
            _write_frame({"jsonrpc": "2.0", "id": rid,
                          "result": {"tools": TOOLS}})
        elif method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments", {}) or {}
            try:
                result = call_tool(name, args)
                _write_frame({"jsonrpc": "2.0", "id": rid, "result": result})
            except Exception as exc:  # noqa: BLE001
                _write_frame({"jsonrpc": "2.0", "id": rid,
                              "error": {"code": -32602, "message": str(exc)}})
        else:
            _write_frame({"jsonrpc": "2.0", "id": rid,
                          "error": {"code": -32601, "message": f"未知方法: {method}"}})
    return 0


if __name__ == "__main__":
    sys.exit(main())

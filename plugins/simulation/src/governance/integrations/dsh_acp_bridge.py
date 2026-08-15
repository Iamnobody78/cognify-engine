#!/usr/bin/env python3
"""DSH-ACP Bridge -- DeepSeek Harness as AionUi ACP agent

Bridge: AionUi (ACP JSON-RPC over stdio) <-> DeepSeek Harness (headless mode).

- AionUi 把 DSH 当作 ACP 对话代理 (command=python args=[...dsh_acp_bridge.py])
- 每个 session_prompt → 调用 `dsh --profile headless "<prompt>"`
- 结果经 ACP 返回给 AionUi, 会话记录在 DSH 的 storages/ (同步层天然可用)

需求: DSH 已安装且 DEEPSEEK_API_KEY 已配置 (dsh-credentials-local 支持 .env)
生成: 2026-08-14  PERMANENT-ANCHOR 治理栈 · AION-MULTI-AGENT 集成层
"""
from __future__ import annotations
import sys
import os
import json
import time
import subprocess
import traceback
from typing import Dict, List, Any
from abc import ABC, abstractmethod
from datetime import datetime, timezone

# Windows: binary mode for reliable stdio
if sys.platform == "win32":
    import msvcrt
    msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
    msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)

_STDIN = sys.stdin.buffer
_STDOUT = sys.stdout.buffer
_CRLF = chr(13) + chr(10)

def _resolve_dsh_cmd() -> str:
    """解析 dsh 可执行文件完整路径 (Windows: 全局 npm bin 下的 .cmd/.ps1)。"""
    env = os.environ.get("DSH_CMD", "")
    if env:
        return env
    candidates = [
        os.path.expanduser("~\\AppData\\Local\\hermes\\node\\dsh.cmd"),
        os.path.expanduser("~\\AppData\\Roaming\\npm\\dsh.cmd"),
        os.path.expanduser("~\\AppData\\Roaming\\npm\\dsh"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    # 最后尝试 PATH
    for p in os.environ.get("PATH", "").split(os.pathsep):
        cand = os.path.join(p, "dsh.cmd")
        if os.path.exists(cand):
            return cand
    return "dsh"


DSH_CMD = _resolve_dsh_cmd()
DSH_PROFILE = os.environ.get("DSH_PROFILE", "headless")
DSH_TIMEOUT = int(os.environ.get("DSH_TIMEOUT", "600"))  # headless 任务超时(秒)


def _run_dsh(task: str, cwd=None) -> str:
    """调用 DSH headless 模式执行任务, 返回最终消息。cwd 用于固定工作区 (车同轨)。"""
    cmd = [DSH_CMD, "--profile", DSH_PROFILE, task]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=DSH_TIMEOUT, encoding="utf-8", errors="replace",
                           cwd=cwd)
    except subprocess.TimeoutExpired:
        return "[DSH-ACP] 任务超时 (%ds) — 可增大 DSH_TIMEOUT" % DSH_TIMEOUT
    except FileNotFoundError:
        return "[DSH-ACP] 错误: 找不到 dsh 命令。请先 npm install -g @deepseek-ai/dsh"
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    # 鲁棒: 某些环境(PYTHONPATH sitecustomize patch)下 returncode 可能为 None
    rc = r.returncode if r.returncode is not None else 0
    if rc != 0:
        return "[DSH-ACP] DSH 返回码 %d\n%s" % (rc, (err or out)[:2000])
    return out if out else (err[:2000] if err else "(DSH 无输出)")


class _JsonRpcError:
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INTERNAL_ERROR = -32603

    @staticmethod
    def make(code: int, message: str, data: Any = None, req_id: Any = None) -> dict:
        err = {"code": code, "message": message}
        if data is not None:
            err["data"] = data
        return {"jsonrpc": "2.0", "error": err, "id": req_id}

    @staticmethod
    def make_response(result: Any, req_id: Any = None) -> dict:
        return {"jsonrpc": "2.0", "result": result, "id": req_id}


class _DshAcpAgent(ABC):
    PROTOCOL_VERSION = 1
    ACP_VERSION = "1.0.0"

    def __init__(self):
        self._initialized = False
        self._sessions: dict = {}

    def _uuid(self) -> str:
        b = list(os.urandom(16))
        b[6] = (b[6] & 0x0f) | 0x40
        b[8] = (b[8] & 0x3f) | 0x80
        hex_str = "".join(f"{x:02x}" for x in b)
        return f"{hex_str[:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:]}"

    def initialize(self, params: dict) -> dict:
        if self._initialized:
            raise RuntimeError("Already initialized")
        self._initialized = True
        return {"protocolVersion": self.PROTOCOL_VERSION,
                "agentCapabilities": self.get_agent_capabilities()}

    def authenticate(self, params: dict) -> dict:
        return {}

    def logout(self, params: dict) -> dict:
        return {}

    def _session_defaults(self) -> dict:
        # 车同轨: 会话 cwd 优先取 AionUi 传入, 否则取 AIONUI_WORKSPACE (中央工作区), 再否则进程 cwd
        return {"mode": "default", "config": {},
                "cwd": os.environ.get("AIONUI_WORKSPACE") or os.getcwd()}

    def session_new(self, params: dict) -> dict:
        sid = self._uuid()
        s = self._session_defaults()
        if params.get("cwd"):
            s["cwd"] = params["cwd"]
        self._sessions[sid] = s
        return {"sessionId": sid}

    def session_load(self, params: dict) -> dict:
        sid = params.get("sessionId") or self._uuid()
        self._sessions.setdefault(sid, self._session_defaults())
        return {"sessionId": sid}

    def session_set_mode(self, params: dict) -> dict:
        sid = params.get("sessionId", "")
        if sid in self._sessions:
            self._sessions[sid]["mode"] = params.get("mode", "default")
        return {}

    def session_set_config_option(self, params: dict) -> dict:
        sid = params.get("sessionId", "")
        if sid in self._sessions:
            key = params.get("key", "")
            val = params.get("value")
            self._sessions[sid]["config"][key] = val
        return {}

    def session_prompt(self, params: dict) -> dict:
        sid = params.get("sessionId", "")
        prompt_text = ""
        messages = params.get("messages", [])
        for msg in messages:
            if isinstance(msg, dict) and msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    prompt_text = content
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            prompt_text = block.get("text", "")
                            break
        # 转发给 DSH headless
        reply = self.handle_prompt(sid, prompt_text, params)
        return {"stopReason": "end_turn",
                "message": {"role": "assistant",
                            "content": [{"type": "text", "text": reply}]}}

    def session_cancel(self, params: dict) -> dict:
        return {}

    def session_close(self, params: dict) -> dict:
        sid = params.get("sessionId", "")
        self._sessions.pop(sid, None)
        return {}

    def session_list(self, params: dict) -> dict:
        return {"sessions": list(self._sessions.keys())}

    def session_delete(self, params: dict) -> dict:
        sid = params.get("sessionId", "")
        self._sessions.pop(sid, None)
        return {}

    def session_fork(self, params: dict) -> dict:
        sid = self._uuid()
        self._sessions[sid] = {"mode": "default", "config": {}}
        return {"sessionId": sid}

    def session_resume(self, params: dict) -> dict:
        sid = params.get("sessionId") or self._uuid()
        if sid not in self._sessions:
            self._sessions[sid] = {"mode": "default", "config": {}}
        return {"sessionId": sid}

    def providers_list(self, params: dict) -> dict:
        return {"providers": self.get_providers()}

    def providers_set(self, params: dict) -> dict:
        return {}

    def providers_disable(self, params: dict) -> dict:
        return {}

    def nes_start(self, params: dict) -> dict:
        return {}

    def nes_suggest(self, params: dict) -> dict:
        return {}

    def nes_accept(self, params: dict) -> dict:
        return {}

    def nes_reject(self, params: dict) -> dict:
        return {}

    def get_server_info(self) -> dict:
        return {"name": "dsh-acp-bridge",
                "version": "1.0.0",
                "description": "DeepSeek Harness via ACP (headless)",
                "protocolVersion": self.PROTOCOL_VERSION,
                "capabilities": {"loadSession": True, "setMode": True,
                                 "setConfigOption": True, "listSessions": True},
                "auth": {"type": "none"}}

    def get_agent_capabilities(self) -> dict:
        return {"loadSession": True, "setMode": True,
                "setConfigOption": True, "listSessions": True}

    def get_providers(self) -> list:
        return [{"id": "deepseek-harness", "name": "DeepSeek Harness (headless)",
                 "models": [{"id": "deepseek", "name": "DSH 默认模型"}]}]

    def handle_prompt(self, session_id: str, prompt_text: str, params: dict) -> str:
        if not prompt_text.strip():
            return "(空消息)"
        s = self._sessions.get(session_id) or self._session_defaults()
        return _run_dsh(prompt_text, cwd=s.get("cwd"))


def _dispatch(agent: _DshAcpAgent, method: str, params: dict) -> Any:
    m = {
        "initialize": agent.initialize,
        "authenticate": agent.authenticate,
        "logout": agent.logout,
        "session/new": agent.session_new,
        "session/load": agent.session_load,
        "session/set_mode": agent.session_set_mode,
        "session/set_config_option": agent.session_set_config_option,
        "session/prompt": agent.session_prompt,
        "session/cancel": agent.session_cancel,
        "session/close": agent.session_close,
        "session/list": agent.session_list,
        "session/delete": agent.session_delete,
        "session/fork": agent.session_fork,
        "session/resume": agent.session_resume,
        "providers/list": agent.providers_list,
        "providers/set": agent.providers_set,
        "providers/disable": agent.providers_disable,
        "nes/start": agent.nes_start,
        "nes/suggest": agent.nes_suggest,
        "nes/accept": agent.nes_accept,
        "nes/reject": agent.nes_reject,
        "get_server_info": agent.get_server_info,
    }.get(method)
    if m is None:
        raise KeyError("Method not found: %s" % method)
    return m(params)


def main() -> int:
    agent = _DshAcpAgent()
    for line in _STDIN:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line.decode("utf-8"))
        except Exception:
            resp = _JsonRpcError.make(_JsonRpcError.PARSE_ERROR,
                                      "Parse error", None, None)
            _STDOUT.write((json.dumps(resp) + _CRLF).encode("utf-8"))
            _STDOUT.flush()
            continue
        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params", {}) or {}
        try:
            result = _dispatch(agent, method, params)
            resp = _JsonRpcError.make_response(result, req_id)
        except KeyError as e:
            resp = _JsonRpcError.make(_JsonRpcError.METHOD_NOT_FOUND,
                                      str(e), None, req_id)
        except Exception as e:
            resp = _JsonRpcError.make(_JsonRpcError.INTERNAL_ERROR,
                                      "%s: %s" % (type(e).__name__, e),
                                      {"trace": traceback.format_exc()[-1500:]}, req_id)
        _STDOUT.write((json.dumps(resp, ensure_ascii=False) + _CRLF).encode("utf-8"))
        _STDOUT.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())

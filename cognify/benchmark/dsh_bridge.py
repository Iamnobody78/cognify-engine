#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dsh_bridge.py — DSH 模型桥接代理 (OpenAI 兼容 /v1/chat/completions)
====================================================================
把 DeepSeek Harness headless profile (本地 deepseek-v4-flash) 暴露为
OpenAI 兼容端点, 供 AgentGym / AgencyBench 等外部基准的评估脚本调用。

用法:
  python dsh_bridge.py [--port 8237]     # 启动代理
  # 客户端: OPENAI_BASE_URL=http://127.0.0.1:8237/v1 OPENAI_API_KEY=dsh
  #         OPENAI_MODEL=deepseek-v4-flash

实现: 纯标准库 (http.server), 每次请求 spawn `dsh --profile headless <prompt>`。
真实模型推理, 不造假; 慢但诚实 (每次调用 ~5-30s)。
"""
import argparse
import json
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

NODE = r"C:\Users\ivy\AppData\Local\hermes\node\node.exe"
DSH = r"C:\Users\ivy\AppData\Local\hermes\node\node_modules\@deepseek-ai\dsh\lib\bin.js"
DSH_HOME = r"C:\Users\ivy\.dsh"
LOG = Path(r"C:\Users\ivy\.aionui-tri-sync\benchmark\external\dsh_bridge_log.jsonl")


def call_dsh(prompt: str, timeout: int = 600) -> str:
    """调用 DSH headless profile 单次推理, 返回模型输出。
    大提示词/长输出可达数分钟, 默认 600s 超时。"""
    env = dict(__import__("os").environ)
    env["DSH_HOME"] = DSH_HOME
    r = subprocess.run([NODE, DSH, "--profile", "headless", prompt],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, env=env)
    out = (r.stdout or "").strip()
    if not out:
        out = (r.stderr or "").strip()[-500:]
    return out


def log_call(model: str, prompt_chars: int, out_chars: int, ms: int, ok: bool) -> None:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                 "model": model, "prompt_chars": prompt_chars,
                                 "out_chars": out_chars, "ms": ms, "ok": ok},
                                ensure_ascii=False) + "\n")
    except Exception:
        pass


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 静默
        pass

    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path == "/v1/models":
            self._json(200, {"object": "list", "data": [
                {"id": "deepseek-v4-flash", "object": "model", "owned_by": "dsh"}]})
        elif self.path == "/health":
            self._json(200, {"status": "ok"})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        if self.path not in ("/v1/chat/completions", "/chat/completions"):
            self._json(404, {"error": "not found"})
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception as exc:  # noqa: BLE001
            self._json(400, {"error": str(exc)})
            return
        messages = body.get("messages") or []
        model = body.get("model", "deepseek-v4-flash")
        # 拼接消息 (OpenAI 格式 → 单一提示)
        parts = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if isinstance(content, list):  # 多模态数组 → 只取 text
                content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
            parts.append(f"[{role}]\n{content}")
        prompt = "\n\n".join(parts)
        t0 = time.time()
        try:
            out = call_dsh(prompt)
            ok = True
        except Exception as exc:  # noqa: BLE001
            out = f"DSH 调用失败: {exc}"
            ok = False
        ms = int((time.time() - t0) * 1000)
        log_call(model, len(prompt), len(out), ms, ok)
        self._json(200 if ok else 502, {
            "id": f"chatcmpl-dsh-{int(t0)}",
            "object": "chat.completion",
            "created": int(t0),
            "model": model,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": out},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": len(prompt) // 3, "completion_tokens": len(out) // 3,
                      "total_tokens": (len(prompt) + len(out)) // 3},
        })


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8237)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[dsh-bridge] OpenAI 兼容端点: http://{args.host}:{args.port}/v1 (Ctrl+C 停止)")
    print("[dsh-bridge] 模型: deepseek-v4-flash via DSH headless | 日志:", LOG)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[dsh-bridge] 停止")
    return 0


if __name__ == "__main__":
    sys.exit(main())

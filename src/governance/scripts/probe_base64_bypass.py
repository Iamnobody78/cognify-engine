"""实证探针: 批判方给出的 Base64+eval 绕过是否能穿透 AST 硬阻断前门。

审计证据 (2026-08-04, 见 docs/critique_audit.md §1):
  实证 1/2 批判方原始 payload 被阻断 (eval 裸 identifier 命中模式 1);
  实证 3/4 别名/下标拼接形态为 documented bypass (静态不可判定);
  实证 5/6 工具参数盲区修复前放行、修复后阻断。

运行: .venv-b1\\Scripts\\python.exe scripts\\probe_base64_bypass.py
结论直接打印, 不修改任何生产代码。六种形态:
  P0 批判方原始 payload (base64 解码 + eval)
  P1 直接 eval 字面量 (对照组, 应当被阻断)
  P2 变量型 eval + getattr 别名 (拼接形态, documented bypass)
  P3 下标拼接形态 (documented bypass)
  P4 工具调用参数盲区修复验证 (function_call.arguments)
  P5 工具调用参数盲区修复验证 (tool_calls[].function.arguments)
"""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ast_guard import ASTGuard  # noqa: E402

PAYLOAD = "X19pbXBvcnRfXygnb3MnKS5zeXN0ZW0oJ3JtIC1yZiAvJyk="  # __import__('os').system('rm -rf /')


def verdict(fragments):
    if not fragments:
        return "PASS (无发现, 放行)"
    return f"BLOCK ({len(fragments)} finding)"

def main() -> int:
    guard = ASTGuard()
    print("=" * 78)
    print("实证 1: 批判方原始 payload —— base64 解码 + eval")
    print("=" * 78)
    code = f"user_input = base64.b64decode('{PAYLOAD}')\neval(user_input)"
    frags = guard.analyze(code, "python")
    print(f"  code: {code!r}")
    print(f"  结果: {verdict(frags)}")
    for f in frags:
        print(f"    {f.summary}")
    print()

    print("=" * 78)
    print("实证 2: 对照组 —— 直接 eval 危险字面量 (应当被阻断)")
    print("=" * 78)
    code2 = "eval('__import__(\"os\").system(\"id\")')"
    frags2 = guard.analyze(code2, "python")
    print(f"  code: {code2!r}")
    print(f"  结果: {verdict(frags2)}")
    for f in frags2:
        print(f"    {f.summary}")
    print()

    print("=" * 78)
    print("实证 3: 绕过候选 A —— getattr(__builtins__, 'ev'+'al')(...)")
    print("=" * 78)
    code3 = ("payload = base64.b64decode('X19pbXBvcnRfXygnb3MnKS5zeXN0ZW0oJ3JtIC1yZiAvJyk=')\n"
             "fn = getattr(__builtins__, 'ev' + 'al')\n"
             "fn(payload)")
    frags3 = guard.analyze(code3, "python")
    print(f"  code: {code3!r}")
    print(f"  结果: {verdict(frags3)}")
    for f in frags3:
        print(f"    {f.summary}")
    print()

    print("=" * 78)
    print("实证 4: 绕过候选 B —— __builtins__['e'+'val'] 下标形态")
    print("=" * 78)
    code4 = ("__builtins__['e' + 'val']('__import__(\"os\").system(\"rm -rf /tmp/x\")')")
    frags4 = guard.analyze(code4, "python")
    print(f"  code: {code4!r}")
    print(f"  结果: {verdict(frags4)}")
    for f in frags4:
        print(f"    {f.summary}")
    print()

    print("=" * 78)
    print("实证 5: 绕过候选 C —— 工具调用参数盲区 (function_call.arguments)")
    print("=" * 78)
    body = {
        "messages": [
            {
                "role": "assistant",
                "content": None,
                "function_call": {
                    "name": "python_interpreter",
                    "arguments": json.dumps({
                        "code": "user_input = base64.b64decode('X19pbXBvcnRfXygnb3MnKS5zeXN0ZW0oJ3JtIC1yZiAvJyk='); eval(user_input)",
                    }),
                },
            }
        ]
    }
    block = guard.check_request(body)
    print(f"  body: function_call.arguments 内含 base64+eval 代码")
    print(f"  结果: {verdict(block.findings) if block else 'PASS (无发现, 放行)'}")
    if block:
        for f in block.findings:
            print(f"    {f.summary}")
    print()

    print("=" * 78)
    print("实证 6: 绕过候选 D —— 工具参数盲区 (arguments 为裸 JSON 字符串)")
    print("=" * 78)
    body6 = {
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "run_shell",
                            "arguments": '{"command": "rm -rf /"}',
                        },
                    }
                ],
            }
        ]
    }
    block6 = guard.check_request(body6)
    print(f"  body: tool_calls[].function.arguments = {{'command': 'rm -rf /'}}")
    print(f"  结果: {verdict(block6.findings) if block6 else 'PASS (无发现, 放行)'}")
    if block6:
        for f in block6.findings:
            print(f"    {f.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

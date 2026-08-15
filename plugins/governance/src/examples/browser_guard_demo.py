"""浏览器代理防护演示（阶段 B）— 治理层拦截浏览器 Agent 的危险工具调用。

场景: browser-use 风格的 Agent 通过 MCP/工具层请求执行代码。治理网关
在 Priority 0 前门用 ASTGuard 逐段分析，拦截 eval/exec、危险 Bash、
无 WHERE 的 SQL DELETE 等——浏览器代理"看得见"但"做不了"。

演示 4 类拦截 + 1 类放行（全部真实生产路径，非桩）:
  1. JS/Python eval — 浏览器环境执行任意表达式 → 拦截
  2. Bash 破坏性命令 — rm -rf /dev/sd* 重定向 → 拦截
  3. SQL 危险 DDL — DROP/DELETE 无 WHERE → 拦截
  4. 良性工具调用 — 点击/输入/读取 → 放行

运行: .venv-b2/Scripts/python.exe examples/browser_guard_demo.py
证据: stdout 含 [BLOCK] / [ALLOW] + finding 明细行。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows cp950 兼容

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
sys.path.insert(0, str(SRC.parent))

from src.ast_guard import ASTGuard  # noqa: E402
from src.policy import PolicyEngine  # noqa: E402


def verdict_line(rule, n_findings: int) -> str:
    if rule is None:
        return f"[ALLOW] 放行 (0 findings)"
    action = rule.get("action") if isinstance(rule, dict) else str(rule)
    return f"[BLOCK] 拦截 action={action} findings={n_findings}"


def main() -> int:
    guard = ASTGuard()
    engine = PolicyEngine(
        config_path=str(REPO_ROOT / "config" / "policies.yaml"),
        ast_guard=guard,
    )
    print("=== 浏览器代理治理演示：看得见，但做不了 ===")
    print(f"已加载语言: {guard.loaded_languages}\n")

    cases = [
        # (场景, body)
        ("JS eval — 浏览器执行任意表达式",
         {"code": "eval('document.cookie = ' + 'xss')"}),
        ("Python exec — 页面注入后门",
         {"code": "exec('import os; os.system(\"whoami\")')"}),
        ("Bash 破坏性命令 — 清空文件系统",
         {"script": "rm -rf /home/user && dd if=/dev/zero of=/dev/sda bs=1M count=1"}),
        ("Bash 重定向敏感文件 — 覆写 /etc/passwd",
         {"script": "echo pwned > /etc/passwd"}),
        ("SQL 危险 DDL — 删表",
         {"query": "DROP TABLE users;"}),
        ("SQL 无 WHERE 删除 — 数据丢失",
         {"query": "DELETE FROM audit_log;"}),
        ("良性: 点击按钮",
         {"code": "click('submit-btn')"}),
        ("良性: 读取页面文本",
         {"code": "text = get_text('#username-field')"}),
        ("良性: 带 WHERE 的 SQL 查询",
         {"query": "SELECT * FROM users WHERE id = 42;"}),
    ]

    total, blocked, allowed = 0, 0, 0
    for label, body in cases:
        total += 1
        fragments_findings = []
        # 先走 AST 前门（真实路径）
        ast_block = guard.check_request(body)
        n = len(ast_block.findings) if ast_block else 0
        # 再走完整策略引擎（含 AST 门 + YAML 规则）
        rule = engine.evaluate("/v1/chat/completions", "POST", body)

        if rule is not None or ast_block is not None:
            blocked += 1
        else:
            allowed += 1
        fragments_findings.append(n)

        print(f"  {label}")
        if ast_block and ast_block.findings:
            for f in ast_block.findings:
                print(f"    ├─ {f.language}/{f.query}: {f.capture} "
                      f"(L{f.line}:{f.col}) `{f.text[:48]}`")
        print(f"    └─ {verdict_line(rule, sum(fragments_findings))}")

    print(f"\n统计: {blocked}/{total} 被拦截, {allowed}/{total} 放行")
    print("=== 演示完毕：治理层在浏览器代理与执行环境之间生效 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

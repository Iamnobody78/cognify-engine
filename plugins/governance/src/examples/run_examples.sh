#!/usr/bin/env bash
# P9 一键验收：启动 stub LLM + 网关 → 跑 3 示例 → 校验治理证据 → 清理。
# 用法: bash examples/run_examples.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY_B1="$ROOT/.venv-b1/Scripts/python.exe"   # langchain SDK
PY_B2="$ROOT/.venv-b2/Scripts/python.exe"   # autogen SDK + 网关运行
GW_PORT=9000
STUB_PORT=8000
PASS=0
FAIL=0

echo "=== [1/4] 启动 stub LLM (:$STUB_PORT) + 治理网关 (:$GW_PORT) ==="
"$PY_B2" "$ROOT/examples/_stub_llm.py" >/dev/null 2>&1 &
STUB_PID=$!
"$PY_B2" -m src.main >/dev/null 2>&1 &
GW_PID=$!
trap 'kill $STUB_PID $GW_PID 2>/dev/null || true' EXIT
sleep 2  # 等待监听就绪

check() {  # check <name> <cmd...>
  local name="$1"; shift
  echo ""
  echo "--- [$name] ---"
  if "$@" >/tmp/p9_$name.log 2>&1; then
    echo "PASS: $name (exit 0)"
    PASS=$((PASS + 1))
  else
    echo "FAIL: $name (exit $?)"
    FAIL=$((FAIL + 1))
  fi
  cat /tmp/p9_$name.log | tail -12
}

echo "=== [2/4] 通用 Python Agent（进程内 agent_tools）==="
check external_agent_demo "$PY_B2" "$ROOT/examples/external_agent_demo.py"

echo "=== [3/4] LangChain Agent（零侵入 base_url, 真实 SDK）==="
check langchain_agent "$PY_B1" "$ROOT/examples/langchain_agent.py"

echo "=== [4/4] AutoGen Agent（零侵入 base_url, 真实 SDK）==="
check autogen_agent "$PY_B2" "$ROOT/examples/autogen_agent.py"

echo ""
echo "=== 治理证据校验 ==="
grep -q "DENY" /tmp/p9_langchain_agent.log && echo "PASS: LangChain 触发 DENY" || echo "FAIL: 无 DENY"
grep -q "ESCALATE" /tmp/p9_langchain_agent.log && echo "PASS: LangChain 触发 ESCALATE" || echo "FAIL: 无 ESCALATE"
grep -q "DENY" /tmp/p9_autogen_agent.log && echo "PASS: AutoGen 触发 DENY" || echo "FAIL: 无 DENY"
grep -q "trace_id" /tmp/p9_autogen_agent.log && echo "PASS: AutoGen 调用链可追踪" || echo "FAIL: 无 trace_id"

echo ""
echo "=== 汇总: PASS=$PASS FAIL=$FAIL ==="
[ "$FAIL" -eq 0 ]

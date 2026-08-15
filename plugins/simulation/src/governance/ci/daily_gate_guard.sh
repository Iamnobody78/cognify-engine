#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# BottleSumo Daily Gate Regression Guard (Sprint 46 T1)
#
# 每日运行双轨门禁 (nano 边缘 + dagger 在线), 低于 92.5% 基线触发告警。
# 这是 Sprint 46 PM 裁决 B (CI 增强) 的本地守护脚本 — 仓库无 GitHub remote,
# GH Actions 仅形式化; 本脚本是实际每日回归执行机制。
#
# 用法:
#   bash governance/ci/daily_gate_guard.sh          # 完整 40ep × 2 策略
#   bash governance/ci/daily_gate_guard.sh --fast   # 快速 10ep × 2 (冒烟)
#   bash governance/ci/daily_gate_guard.sh --check  # 检查上次报告, 不重跑
#
# 退出码: 0 = 双轨 ≥92.5% PASS | 1 = 任一 <92.5% FAIL (告警) | 2 = 运行错误
# 调度建议 (WSL cron): 30 2 * * * cd /path/to/bottlesumo_pi && bash governance/ci/daily_gate_guard.sh
# ═══════════════════════════════════════════════════════════════════════════
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # .../bottlesumo_pi
cd "${REPO_ROOT}" || { echo "[FATAL] cannot cd bottlesumo_pi"; exit 2; }

GATE_SCRIPT="simulation/v9_gate_evaluator.py"
BASELINE=92.5
DATE_TAG="$(date +%Y-%m-%d)"
REPORT_DIR="governance/ci/daily"
REPORT_FILE="${REPORT_DIR}/${DATE_TAG}.json"
EPISODES=40
MODE="full"
BASELINE=92.5

if [[ "${1:-}" == "--fast" ]]; then EPISODES=10; MODE="fast"; BASELINE=90.0; fi
# 说明: fast (10ep) 下 92.5% (37/40) 统计等价于 9/10=90% 或 10/10 — 90% 为
# 统计下界; full (40ep) 为正式基线 92.5% (S45 冻结)。
if [[ "${1:-}" == "--check" ]]; then
  if [[ ! -f "${REPORT_FILE}" ]]; then
    echo "[CHECK] no report for ${DATE_TAG} yet — run without --check"
    exit 2
  fi
  python3 -c "
import json, sys
d = json.load(open('${REPORT_FILE}'))
ok = all(v['winrate']*100 >= ${BASELINE} for v in d['policies'].values())
print(f\"[CHECK] {d['date']} {d['mode']}: nano={d['policies']['nano']['winrate']*100:.1f}% dagger={d['policies']['dagger']['winrate']*100:.1f}% -> {'PASS' if ok else 'FAIL'}\")
sys.exit(0 if ok else 1)
"
  exit $?
fi

mkdir -p "${REPORT_DIR}"
echo "=== [$(date +%H:%M:%S)] Daily Gate Guard (${MODE}, ${EPISODES}ep) ==="
echo "=== Baseline: ${BASELINE}% (S45 冻结基线) ==="

declare -A WR

for POLICY in nano dagger; do
  echo "--- ${POLICY} (${EPISODES}ep) ---"
  LOG="${REPORT_DIR}/_${DATE_TAG}_${POLICY}.log"
  timeout 1500 python3 -u "${GATE_SCRIPT}" --agent rl --policy "${POLICY}" \
      --episodes "${EPISODES}" --json > "${LOG}" 2>&1
  RC=$?
  if [[ ${RC} -ne 0 ]]; then
    echo "[FAIL] ${POLICY} gate run exited ${RC} (timeout/error)"
    tail -5 "${LOG}"
    exit 2
  fi
  WR[$POLICY]=$(python3 -c "
import json
d = json.load(open('../.aionui/meta_governance/gate/v9_gate_report.json'))
print(f\"{d['winrate']:.4f}\")
")
  echo "${POLICY} WR = ${WR[$POLICY]}"
done

NANO_WR="${WR[nano]}"
DAGGER_WR="${WR[dagger]}"

python3 - <<EOF
import json
report = {
    "date": "${DATE_TAG}",
    "mode": "${MODE}",
    "baseline_pct": ${BASELINE},
    "policies": {
        "nano":   {"model": "nano_s44_t1_data.pt", "winrate": float("${NANO_WR}")},
        "dagger": {"model": "chase_dqn_dagger_s40.pt", "winrate": float("${DAGGER_WR}")},
    },
    "passed": float("${NANO_WR}") >= ${BASELINE}/100.0
              and float("${DAGGER_WR}") >= ${BASELINE}/100.0,
    "generated_at": "$(date -Is)",
}
with open("${REPORT_FILE}", "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)
print("report -> ${REPORT_FILE}")
EOF

NANO_PCT=$(python3 -c "print(f'${NANO_WR}'*100 if False else round(float('${NANO_WR}')*100,1))")
DAGGER_PCT=$(python3 -c "print(round(float('${DAGGER_WR}')*100,1))")

echo ""
echo "=== [$(date +%H:%M:%S)] GATE GUARD SUMMARY ==="
echo "  nano   (edge)  : ${NANO_PCT}%  (基线 ${BASELINE}%)"
echo "  dagger (online): ${DAGGER_PCT}%  (基线 ${BASELINE}%)"

if python3 -c "exit(0 if float('${NANO_WR}') >= ${BASELINE}/100.0 and float('${DAGGER_WR}') >= ${BASELINE}/100.0 else 1)"; then
  echo "  ✅ GATE GUARD PASS — 双轨均 ≥ ${BASELINE}%"
  exit 0
else
  echo "  🚨 GATE GUARD FAIL — 至少一策略 < ${BASELINE}% (低于 S45 冻结基线)"
  exit 1
fi

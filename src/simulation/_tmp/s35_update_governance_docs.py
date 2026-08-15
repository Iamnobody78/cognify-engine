#!/usr/bin/env python3
# S35: failure_analysis.md + pareto_frontier.md 顶部插入 S35 记录（字节级，保持 CRLF）
import sys

BASE = r"/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/governance/meta_harness/"

fa_section = """## Sprint 35 记录 (2026-08-08, S35_SYMBOLIC_EXPLORATION) — Z3 第四层防护 + 新领域勘探

**背景**: PM 裁决 S35 T1 = Z3 符号验证集成 (P0, 第四层防护), T2 = 奖励/物理参数域勘探
(P1, 并行), V9 门 plateau_explorer 自蒸馏与 Hermes B2 延后。

**T1 第四层防护 (SYMBOLIC_PROOF_FAIL)**: 新增 symbolic_verify.py — ABDL 条件→SMT-LIB 翻译,
不变量 I1 (∀输入点∈物理定义域, 至少一条规则匹配) + 新增空洞查询 (∃x: 基线有匹配 ∧ 候选无匹配,
数学精确的覆盖包含验证)。集成于 precheck_topology_validity (S32 之后), 3 层经验验证 → 4 层
(经验 + 数学证明)。**核心发现**: S34 合入后的 12 规则基线存在 S32 单维投影盲区的真实联合空洞
(opp_found=False ∧ edge∈(0.6,0.8] — CAUTIOUS-EDGE 删除后留下的真空; D4-3 "邻居完全吸收"
在数学级被证伪为"部分吸收")。探针候选 mh_rules_close_edge_030 (CLOSE-PUSH edge 0.65→0.30
收窄): S32 放行, **Z3 稳定拦截 3/3 轮** — 验收①达成, 验证延迟 0.027s/候选 ≪ 5s 线。

**T2 新领域勘探 (GRIP_DECAY 双向)**: 动量轴 (ROUND 2 0.90/0.875 被支配) 已证伪 → 选未勘探
GRIP_DECAY: grip_020 (0.10→0.20) / grip_000 (0.10→0.0) 双候选均 INCONCLUSIVE (Q≈0.00,
avg_steps 21.4 持平)。与动量轴、奖励轴 (ROUND 10 push_threshold) 汇聚为同一结论: **外层参数轴
对规则引擎解耦** — 规则 avg_steps 由拓扑分支结构决定, 外层扰动在 ±0.005 步噪声内。

**失败模式**: 无新 FP (T1/T2 均为执行类 + 探针验证)。运维确认:
- RULE-PR-002 (WSL 长 Python 命令用脚本文件) 第四次应验 — PowerShell 引号嵌套解析失败 ×1。
- PEP 668: WSL Ubuntu python3.14 系统级 pip 需 --break-system-packages (z3-solver 5.0.0.0)。
- **集成回归教训**: 新防护必须与既有预检 (S32) 保持相同"跳过语义" — 初次集成无 involved-guard,
  mock 场景 (裸文本 `dist < 0.20` 无 sensor()) 被真实 ABDL 锚点检查误拦截 → 加
  "无数值传感器条件变更则跳过" guard (与 S32 一致) 后 215/215 全绿。FP 类同 S32 集成期。

**V9 门**: 胜率仍 10% (1/10)。T2 三轴 (reward/momentum/GRIP_DECAY) 解耦证据支持 PM 预判 —
规则空间收敛 + 外层参数解耦 → V9 门需 RL 轨道 (PyTorch) 提供正样本, 规则勘探已到边际。

"""

pf_section = """## Sprint 35 运行记录 (2026-08-08, S35_SYMBOLIC_EXPLORATION) — 第四层防护落地 + 轴证伪

**背景**: PM 裁决 S35 T1 = Z3 符号验证 (P0), T2 = 新领域勘探 (P1, 并行), 延后 V9 自蒸馏/Hermes B2。

**T1 验证 (outer_loop --round 14 --symbolic-verify --iterations 3 --tag S35_T1T2)**:
| 候选 | 判定 | 关键 |
| :--- | :--- | :--- |
| mh_rules_close_edge_030 (T1 探针) | **TOPO-PRECHECK-FAIL ×3** | SYMBOLIC_PROOF_FAIL: 联合空洞 (edge∈(0.30,0.65) 收窄, S32 放行) — Z3 数学级拦截 |
| mh_physics_grip_020 (T2) | INCONCLUSIVE (Q=0.00) | avg_steps 21.4→21.3, reward 296.64 — 无行为影响 |
| mh_physics_grip_000 (T2) | INCONCLUSIVE (Q=0.00) | avg_steps 21.4→21.4, reward 298.13 — 无行为影响 |

**Pareto 意义**:
1. **第四层防护从概念到实证**: S32 单维投影 (启发式) 与 Z3 联合覆盖 (数学证明) 的盲区差
   异被同一候选的"放行 vs 拦截"直接演示 — 覆盖验证从"保守近似"升级为"精确包含"。
2. **基线知识**: 12 规则基线的联合空洞 (edge∈(0.6,0.8], opp_found=False) 作为知识基线记录,
   后续候选若扩大该空洞即被拦截 (防止 S34 精简的隐性回退)。
3. **三轴解耦收敛**: reward (S10/ROUND 10) + momentum (ROUND 2) + GRIP_DECAY (S35) 三独立
   证据链 → 规则引擎 avg_steps 由拓扑决定, 外层参数轴已证伪 — 探索预算应转向 RL 轨道。
4. 基线保持: avg_steps=21.4 / winrate=1.0 / 触发 214 (第四层防护不改变基线行为, 零副作用)。

"""


def insert_after_title(path, title_line, section):
    with open(path, "rb") as f:
        raw = f.read()
    eol = b"\r\n" if b"\r\n" in raw else b"\n"
    text = raw.decode("utf-8")
    eol_s = eol.decode("utf-8")

    if section.splitlines()[0] in text:
        print(f"ALREADY PRESENT: {path}")
        return

    marker = title_line + eol_s + eol_s
    if marker not in text:
        print(f"ERROR: title marker not found in {path}")
        sys.exit(1)
    text = text.replace(marker, marker + section, 1)
    with open(path, "wb") as f:
        f.write(text.encode("utf-8"))
    print(f"OK: inserted into {path}")


insert_after_title(
    BASE + "failure_analysis.md",
    "# BottleSumo TASK-005d — V9 门 aggressive 0/2 失败分析 (2026-08-05)",
    fa_section,
)
insert_after_title(
    BASE + "pareto_frontier.md",
    "# TASK-005d Pareto (BottleSumo V9 门, 2026-08-05)",
    pf_section,
)
print("DONE")

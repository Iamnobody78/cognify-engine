#!/usr/bin/env python3
# S34: failure_analysis.md + pareto_frontier.md 顶部插入 S34 记录（字节级，保持 CRLF）
import sys

BASE = r"/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi/governance/meta_harness/"

fa_section = """## Sprint 34 记录 (2026-08-08, S34_RULE_PRUNE_DISTILL) — 候选 G 合入主规则 + D5 蒸馏入库

**背景**: PM 裁决 S34 P0 = 候选 G 合入主规则 (CAUTIOUS-EDGE 移除, 8→7 规则精简),
P1 = D5 高价值规则蒸馏 (conf≥0.3 入库 engineering_rules.md), P2 = Hermes B2 (延后 S35)。

**P0 候选 G 合入 (simulation_rules.abdl)**: CAUTIOUS-EDGE 块 (SIM-HEUR-CAUTIOUS-EDGE,
L137-144) 物理删除 — 13→12 条规则 id, CAUTIOUS 出现次数 0, git diff 9 行纯删除
(字节级 WSL python3 编辑, 无行尾污染)。基线验证 (outer_loop --iterations 3 --tag
S34_G_MERGE): avg_steps=21.4 / winrate=1.0 / rules 触发 214, 与 S33 完全一致 —
CAUTIOUS-EDGE 的 13 次触发被邻居 (CLOSE-PUSH<0.65 + FLANK<0.80) 无损吸收, D4-3 冗余
判定在物理删除后成立。全部已知候选判定干净复现 (topo_A INC / topo_B REGRESSION /
候选 C TOPO-PRECHECK-FAIL / mapping_001 REGRESSION / mapping_002 INC /
physics_seed_001 REGRESSION / seed_002-003 INC / action_map_001 REGRESSION),
无锚点崩溃无预检混淆。探索饱和 3 轮无有效结果 (规则空间已固定, 预期行为)。

**P1 D5 蒸馏入库 (engineering_rules.md 高置信度规则章节)**: 三强规则
(RULE-HC-001 topo_B 0.48 / RULE-HC-002 mapping_001 0.30 / RULE-HC-003 topo_A 0.26)
写入 governance/dashboard/engineering_rules.md。验证: 12 规则基线下重跑
distill_loop --recalibrate, 三强规则置信度稳定复现 (0.48/0.30/0.26, 零漂移) —
蒸馏入库不产生副作用。副作用路径确认: distill_loop 不消费 engineering_rules.md
(HC 规则为后续候选生成的治理指导, 非管道输入), cell_learner 写 meta_engineering_rules.md
为另一文件 — 治理规则库与管道零耦合。

**失败模式**: 本 Sprint 无新 FP (P0/P1 均为执行类任务)。运维确认: RULE-PR-002
(WSL 长 Python 命令一律脚本文件方式) 第三次应验 — PowerShell 引号嵌套解析失败 ×2
(重跑 recalibrate 管道时)。CRLF 维护: engineering_rules.md 经 WSL python3 字节级
插入 HC 章节, git diff 干净无行尾污染。

"""

pf_section = """## Sprint 34 运行记录 (2026-08-08, S34_RULE_PRUNE_DISTILL) — 规则数净减落地 + D5 蒸馏入库

**背景**: PM 裁决 S34 P0 = 候选 G 合入主规则 (8→7 规则精简), P1 = D5 高价值规则蒸馏
(conf≥0.3 入库), P2 = Hermes B2 延后 S35。

**P0 合入验证 (outer_loop --iterations 3 --tag S34_G_MERGE, 12 规则基线)**:
| 候选 | 判定 | avg_steps | 关键 |
| :--- | :--- | :--- | :--- |
| 基线 (CAUTIOUS-EDGE 移除) | — | **21.4** | 与 S33 完全一致, 214 触发零 CAUTIOUS-EDGE |
| mh_rules_topo_A (回放) | SUSPICIOUS | 60→59 | 复现 |
| mh_mapping_001 (回放) | REGRESSION (-0.17) | 21.4→29.3 | 第四次复现 |
| 探索饱和 | 3 轮无有效结果 | — | 规则空间已固定 (预期) |

**Pareto 意义**: 规则数净减从「评估结论」(S33) 落地为「主分支事实」— 12 条规则 id
(13→12, CAUTIOUS=0), 冗余分支不再消耗信号带宽且减少一条维护路径。**D5 蒸馏入库**:
三强规则 (topo_B 0.48 / mapping_001 0.30 / topo_A 0.26) 写入 engineering_rules.md
HC 章节 (RULE-HC-001/002/003), 12 规则基线下重跑 --recalibrate 置信度零漂移 —
蒸馏管道与规则精简正交, HC 规则为治理指导 (非管道输入) 无副作用。134/134 全绿。

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

    # 标题行 + 空行 => marker
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

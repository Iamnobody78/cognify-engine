#!/usr/bin/env python3
"""BottleSumo Meta-Harness 变体生成器 (P1, 内环自动化引擎).

实现 Stanford IRIS Lab Meta-Harness (arXiv:2603.28052) 的 Agentic Proposer 职责:
    读取血缘 (failure_analysis.md F-100..F-106 + pareto_frontier.md TASK-005d 表
              + v9_gate_report.json 最近评估) -> 产出 3 个候选变体
              (规则层 / 映射层 / 物理层 各 1)。

每个变体携带:
    id          : 唯一标识 (mh_<layer>_<seq>)
    layer       : rules | mapping | physics
    target_file : 相对仓库根的 Harness 文件路径
    diff        : [{"old": ..., "new": ...}] 精确替换对 (可机器应用/回滚)
    hypothesis  : 一句话因果假说 (为什么这个改动能提升?)
    evidence    : [F-xxx] 缺陷库编号
    bloodline   : 血缘链 (pareto 前沿演化轨迹)

硬约束:
    - 绝不修改非 Harness 文件 (domain_spec.md §1 五文件清单)
    - 单变体只改 1 个假说 (可含多个 diff 对, 但必须同属一个因果命题)
    - 物理约束: 线速度 <= 0.534 m/s, 角速度 <= 4.0 rad/s (违反即不产出)
    - 只读磁盘真实文件, 不捏造数据; 文件缺失时降级为内置种子模板并标注

用法:
    python3 governance/meta_harness/variants.py [--json out.json] [--max-per-layer N]
    python3 governance/meta_harness/variants.py --self-test   # 离线路血缘解析自检
"""
import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict

# Windows cp950 控制台编码修复: 打印中文血缘标题时避免 UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
META_HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))

# --------------------------------------------------------------------------
# Harness 文件清单 (domain_spec.md §1) — 变体唯一合法目标
# Sprint 28: 新增 action_map 层 (simulation/wheel_to_discrete.py) —
#   PM 轮速增益指令 (TURN_*_MED 0.6->0.8) 的唯一合法扰动目标。
#   可达性检查 (FP-NEG-002 新规则) 已通过: TURN_R_MED 调用点
#   abdl_action_bridge.py:217 (mapping flank 分离态) + wheel_to_discrete.py:198
#   (heuristic fallback); TURN_L_MED 调用点 abdl_action_bridge.py:225 +
#   wheel_to_discrete.py:162/196 — 全部在评估路径上 (非死代码)。
# --------------------------------------------------------------------------
HARNESS_FILES = {
    "rules":   "governance/meta_language/simulation_rules.abdl",
    "mapping": "core/meta_language/abdl_action_bridge.py",
    "physics": "simulation/lightweight_env.py",
    "reward":  "simulation/reward_functions.py",
    "gate":    "simulation/v9_gate_evaluator.py",
    "action_map": "simulation/wheel_to_discrete.py",
}

# 物理约束 (meta-prompt v1.0 §1)
MAX_LINEAR_SPEED = 0.534   # m/s (实测标定 steady_v 0.5279)
MAX_ANGULAR_RATE = 4.0     # rad/s

# --------------------------------------------------------------------------
# Sprint 20 P1: 恒 False 模式检测器
# (生成层 resolve_diff + 运行时 apply_precheck 共享; PM 指令: 自引用比较
#  dist < dist / 空条件 等, 作为 apply 预检的补充层, 拦截明显损坏候选)
# --------------------------------------------------------------------------
# 1. 自引用比较: dist < dist / angle >= angle (同一标识符与自身比较)
_AF_SELF_CMP = re.compile(r"\b([A-Za-z_]\w*)\s*(<=|>=|<|>)\s*\1\b")
# 2. 空条件: if: / if (): (条件表达式为空, 语法级恒错)
_AF_EMPTY_COND = re.compile(r"\b(?:if|elif|while)\s*[:(]?\s*[)]?\s*:")
# 3. 恒 False 字面量条件: if 0: / while False: / if 0.0: (分支不可达)
_AF_FALSE_LITERAL = re.compile(
    r"\b(?:if|elif|while)\s+(?:0(?:\.0+)?(?![\d.])|False|None)\b")


def detect_always_false(old_line: str, new_line: str) -> str:
    """P1: 检测 diff 引入的恒 False 模式。命中返回原因串, 否则返回 ""。

    覆盖三类 (PM Sprint 20 指令): 自引用比较 / 空条件 / 恒 False 字面量。
    限制 (第一版): 不做逻辑推导 (如 dist<0.2 and dist>0.8 互斥区间),
    也不做函数调用自比较 (sensor(x) < sensor(x)); 此类留待语义级分析。
    """
    for needle in (old_line, new_line):
        if not needle:
            continue
        m = _AF_SELF_CMP.search(needle)
        if m:
            verdict = "恒 True" if m.group(2) in ("<=", ">=") else "恒 False"
            return (f"自引用比较 {m.group(1)} {m.group(2)} {m.group(1)} "
                    f"({verdict}, 无信息量)")
        if _AF_EMPTY_COND.search(needle):
            return "空条件 (if/elif/while 后无表达式, 语法级恒错)"
        m = _AF_FALSE_LITERAL.search(needle)
        if m:
            return f"恒 False 字面量条件 {m.group(0)!r} (分支不可达)"
    return ""


@dataclass
class Variant:
    id: str
    layer: str
    target_file: str
    diff: list
    hypothesis: str
    evidence: list
    bloodline: str
    parent: str = ""
    source: str = "generated"          # 血缘来源 (failure_analysis / pareto / gate)
    score: dict = field(default_factory=lambda: {"winrate": None, "passed": None})
    provenance: str = ""               # 文件缺失时标注降级来源
    extra_files: dict = field(default_factory=dict)   # 组合变体: {layer: [diff pairs]} 多文件 diff
    lineage_ctx: dict = field(default_factory=dict)
    workspace: str = ""               # P1-2: 候选工作空间目录 (candidates/<candidate_id>/)

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------
# 血缘解析: failure_analysis.md (BottleSumo 段 F-100..F-106)
# --------------------------------------------------------------------------
def _find_file(*rel_parts: str) -> str:
    """从多个候选位置定位文件 (meta_harness 专属目录优先, 其次 repo 根与上层工作区)。

    2026-08-06 修复: P1 血缘文件 (pareto_frontier.md / failure_analysis.md) 已迁移至
    meta_harness/ 目录, 避免命中工作区根被 AST Guard 内容污染的旧文件。
    """
    for base in (META_HARNESS_DIR, REPO_ROOT, os.path.join(REPO_ROOT, "..", "..")):
        p = os.path.abspath(os.path.join(base, *rel_parts))
        if os.path.exists(p):
            return p
    return ""


def _read_text(path: str):
    for enc in ("utf-8", "utf-8-sig", "gbk"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, OSError):
            continue
    return None


def load_failure_analysis(path: str = None) -> dict:
    """解析 failure_analysis.md 的 BottleSumo TASK-005d 段, 返回 {F-xxx: 标题}。"""
    path = path or _find_file("failure_analysis.md") or _find_file("..", "failure_analysis.md")
    if not path:
        return {"_missing": "failure_analysis.md 不在磁盘; 使用内置 F-100..F-106 摘要模板"}

    text = _read_text(path)
    if text is None:
        return {"_missing": f"无法解码 {path}"}

    defects = {}
    bs_start = text.find("BottleSumo TASK-005d")
    if bs_start >= 0:
        text = text[bs_start:]
    for m in re.finditer(r"^## (F-\d{3}): (.+)$", text, re.MULTILINE):
        defects[m.group(1)] = m.group(2).strip()
    return defects


def load_pareto(path: str = None) -> dict:
    """解析 pareto_frontier.md 的 TASK-005d 段, 返回最后一行的当前最优。"""
    path = path or _find_file("pareto_frontier.md") or _find_file("..", "pareto_frontier.md")
    if not path:
        return {"_missing": "pareto_frontier.md 不在磁盘", "current_best": "1.0 (970c209)"}

    text = _read_text(path)
    if text is None:
        return {"_missing": f"无法解码 {path}", "current_best": "1.0 (970c209)"}

    start = text.find("TASK-005d Pareto")
    if start >= 0:
        text = text[start:]
    rows = re.findall(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", text, re.MULTILINE)
    best = None
    for name, score in rows:
        name, score = name.strip(), score.strip()
        if not name or score.startswith("质量") or name == "变体":
            continue
        best = {"variant": name, "quality": score}
    return {
        "current_best": best["quality"] if best else "1.0 (970c209)",
        "last_row": best,
    }


def load_last_gate_report() -> dict:
    """读取最近一次 V9 门评估报告 (v9_gate_report.json)。"""
    for rel in (
        os.path.join(".aionui", "meta_governance", "gate", "v9_gate_report.json"),
        os.path.join("..", "..", ".aionui", "meta_governance", "gate", "v9_gate_report.json"),
    ):
        p = _find_file(rel)
        if not p:
            continue
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                "file": p,
                "winrate": data.get("winrate"),
                "passed": data.get("passed"),
                "per_strategy": data.get("per_strategy", {}),
            }
        except (OSError, json.JSONDecodeError):
            continue
    return {"_missing": "v9_gate_report.json 不在磁盘"}


# --------------------------------------------------------------------------
# 物理变体工厂 (模块级, 供 ROUND 2/3/4 共用)
# --------------------------------------------------------------------------
def _mk_physics(cur: float, new_coef: float, vid: str, hyp: str,
                ev: list, parent_tag: str, layer: str = "physics",
                extra_diff: list = None) -> Variant:
    """构造物理层变体; extra_diff 用于组合变体附加 diff (如规则层叠加)。"""
    new_str = f"momentum = net * TIMESTEP * {new_coef}"
    target = f"momentum = net * TIMESTEP * {cur}"
    diff = [{"old": target, "new": new_str}]
    if extra_diff:
        diff.extend(extra_diff)
    return Variant(
        id=vid, layer=layer, target_file=HARNESS_FILES["physics"],
        diff=diff,
        hypothesis=hyp, evidence=ev,
        bloodline=f"{parent_tag} (动量 {cur}->{new_coef})",
        parent=parent_tag, source="failure_analysis(自适应物理)",
        provenance="lightweight_env.py 磁盘实读 (动量自适应)",
    )


# --------------------------------------------------------------------------
# 磁盘感知的变体生成 (只读真实文件, 按实际存在的阈值产出)
# --------------------------------------------------------------------------
def _mk_combined(cur_mom: float, new_mom: float, flank_old: str, flank_new: str,
                 vid: str, hyp: str, ev: list, parent_tag: str) -> Variant:
    """构造组合变体: 双文件 diff (physics 动量 + rules FLANK 角度), ROUND 4 起用。

    target_file 指向 physics (动量), extra_files["rules"] 携带 FLANK 角度 diff;
    outer_loop.apply_variant 会先全量校验再逐文件写入 (原子性)。
    """
    mom_diff = [{"old": f"momentum = net * TIMESTEP * {cur_mom}",
                 "new": f"momentum = net * TIMESTEP * {new_mom}", "expected": 1}]
    flank_diff = [
        {"old": f"sensor(opponent_angle) < -{flank_old}",
         "new": f"sensor(opponent_angle) < -{flank_new}", "expected": 1},
        {"old": f"sensor(opponent_angle) > {flank_old}",
         "new": f"sensor(opponent_angle) > {flank_new}", "expected": 1},
    ]
    return Variant(
        id=vid, layer="combined", target_file=HARNESS_FILES["physics"],
        diff=mom_diff, extra_files={"rules": flank_diff},
        hypothesis=hyp, evidence=ev,
        bloodline=f"{parent_tag} (FLANK {flank_old}°→{flank_new}° + 动量 {cur_mom}→{new_mom})",
        parent=parent_tag,
        source="ROUND 3 实证 (288 步) + F-103/F-106",
        provenance="lightweight_env.py + simulation_rules.abdl 磁盘实读 (HEAD 9c6fd50)",
    )


def _gen(layer: str, defects: dict) -> list:
    """通用入口: 读磁盘目标文件, 用 verified 精确串匹配生成变体。

    diff 中的 old/new 全部来自 2026-08-05 磁盘实读 (git HEAD 970c209/4fcb55c)。
    """
    path = os.path.join(REPO_ROOT, HARNESS_FILES[layer])
    if not os.path.exists(path):
        return _seed_variants(layer, defects, f"{HARNESS_FILES[layer]} 缺失")
    text = _read_text(path)
    if text is None:
        return _seed_variants(layer, defects, f"{HARNESS_FILES[layer]} 无法解码")

    out = []
    if layer == "rules":
        # ── ROUND 1: 变体 A (F-100): CLOSE-PUSH 接战窗 ±15° -> ±10° ──
        if "BETWEEN(sensor(opponent_angle), -15, 15)" in text:
            out.append(Variant(
                id="mh_rules_001",
                layer="rules",
                target_file=HARNESS_FILES["rules"],
                diff=[{"old": "BETWEEN(sensor(opponent_angle), -15, 15)",
                       "new": "BETWEEN(sensor(opponent_angle), -10, 10)"}],
                hypothesis="近战接战窗 ±15°→±10°: 对手侧滑角度大时推迟全力推挤, "
                           "避免推力打在切向分量 (F-100 遮蔽修复后的剩余浪费)",
                evidence=["F-100"],
                bloodline="970c209 -> mh_rules_001",
                parent="970c209",
                source="failure_analysis(F-100)",
                provenance="simulation_rules.abdl 磁盘实读 (HEAD 970c209)",
            ))
        # ── ROUND 2: 变体 mh_rules_002 (F-106): Circler 切线接近角 ──
        # Circler 平均 67.5 步 (vs Defensive 77.5 仍偏高)。弧线运动下,
        # FLANK 角度阈值 18° 决定机器人多早切入对手切向路径。
        # 收窄到 15° (复用 CLOSE-PUSH 窗, 不引入新魔数): 更早触发侧翼拦截,
        # 在对手弧线尚未生成大角度差时即压上 — 压缩 circler 拖长对局。
        # 基于 F-106 混合侧翼框架 (角度阈值属于该框架既有旋钮)。
        if "sensor(opponent_angle) > 18" in text and "sensor(opponent_angle) < -18" in text:
            out.append(Variant(
                id="mh_rules_002",
                layer="rules",
                target_file=HARNESS_FILES["rules"],
                diff=[
                    {"old": "sensor(opponent_angle) < -18",
                     "new": "sensor(opponent_angle) < -15",
                     "expected": 1},
                    {"old": "sensor(opponent_angle) > 18",
                     "new": "sensor(opponent_angle) > 15",
                     "expected": 1},
                ],
                hypothesis="Circler 切线接近角: FLANK 角度阈值 18°→15° (复用 CLOSE-PUSH 窗值, "
                           "零新魔数): 更早切入弧线对手的切向路径, 压缩 67.5 步拖长对局 (F-106 框架)",
                evidence=["F-106"],
                bloodline="970c209 -> mh_rules_002",
                parent="970c209",
                source="failure_analysis(F-106) + gate 报告 (circler 67.5 步)",
                provenance="simulation_rules.abdl 磁盘实读 (HEAD 970c209)",
            ))
        # ── Sprint 29 A1 (PM 裁决 P0): 规则拓扑探索 (解 RULES CLOSED 禁令) ──
        # S24 禁令根因是 FP-MC-020: S22/S23 用 abs 阈值扰动 0-1 语义参数 (edge_proximity
        # 变 -7.20 恒 True) → edge-loop。本次全部为**拓扑级文本变更** (阈值/前提/优先级),
        # 不涉及参数级 bump, 规避原禁令的扰动器 bug。三个候选基于 S28 四轴饱和结论:
        # 行为参数正扰动空间耗尽 → 需要结构性变化 (Do Agent Optimizers Compound? 76.4%
        # 第二次预算无法改进 ↔ 四轴饱和同构)。
        # 可达性检查 (FP-NEG-002 新规则, 2026-08-08 执行):
        #   A: CLOSE-PUSH edge 0.65→0.80 与 FLANK edge<0.80 对齐 → 消除 edge∈[0.65,0.80)
        #      且 angle∈[-10,10] 的 L2 无人接管空洞 (落回 L3 减速), 变更后条件仍活。
        #   B: OPPONENT-FOUND 前提 dist>0.6 → >=0.3 → pursue 域与 close-combat 域
        #      (dist<0.6) 重叠于 [0.3,0.6), 由 priority (700>500/480/470) 裁决 pursue,
        #      FLANK 分离态 dist<0.6 仍在, 无死路径。
        #   C: SPEED-ADAPT 300→350 仅优先级数字变更, 条件不变, 消费路径 (resolve_top
        #      priority 降序) 不变, 无死路径。
        # 拓扑空洞实测 (候选 A 动机): 基线 steps=[6,8,7,19,42,49,12,60,5,6], 第 8 局
        # 60 步贴边极限对局 — edge 高位 (0.65-0.8) 且角度对齐时 CLOSE-PUSH 不触发
        # (edge<0.65 超限), FLANK 不触发 (angle 在 ±10 内) → 无 L2 接管, 只能 L3 减速。
        # ------------------------------------------------------------------
        cnt_cp = text.count("sensor(edge_proximity) < 0.65")
        if cnt_cp >= 1:
            out.append(Variant(
                id="mh_rules_topo_A",
                layer="rules",
                target_file=HARNESS_FILES["rules"],
                diff=[{"old": "sensor(edge_proximity) < 0.65",
                       "new": "sensor(edge_proximity) < 0.80",
                       "expected": cnt_cp}],
                hypothesis="S29 A1-拓扑A (空洞修复): CLOSE-PUSH edge 上界 0.65→0.80 与 "
                           "FLANK edge<0.80 对齐 — 消除 edge∈[0.65,0.80) 且 angle∈[-10,10] "
                           "的 L2 无人接管空洞 (基线 60 步贴边极限对局第 8 局): 边缘高位对齐 "
                           "时 CLOSE-PUSH 直接接管, 不让 L3 减速白白放弃推挤窗口",
                evidence=["F-103", "F-106"],
                bloodline="970c209 -> mh_rules_topo_A (拓扑空洞修复)",
                parent="970c209",
                source="PM Sprint 29 裁决 A1 + S28 四轴饱和 + 规则拓扑分析 (L2 空洞)",
                provenance="simulation_rules.abdl 磁盘实读 (2026-08-08, line 99)",
            ))
        # 候选 B: OPPONENT-FOUND 触发域重组 — dist>0.6 与 CLOSE-PUSH dist<0.6 无缝隙
        # (S28 直冲窗死代码 FP-NEG-002 的域级修复: pursue 提前接管 [0.3,0.6) 追赶域)
        cnt_of = text.count("sensor(opponent_dist) > 0.6")
        if cnt_of >= 1:
            out.append(Variant(
                id="mh_rules_topo_B",
                layer="rules",
                target_file=HARNESS_FILES["rules"],
                diff=[{"old": "sensor(opponent_dist) > 0.6",
                       "new": "sensor(opponent_dist) >= 0.3",
                       "expected": cnt_of}],
                hypothesis="S29 A1-拓扑B (触发域重组): OPPONENT-FOUND 前提 dist>0.6 → >=0.3 — "
                           "pursue 域与 close-combat 域重叠于 [0.3,0.6) 由 priority (700) 裁决, "
                           "消除中距追赶真空 (0.3-0.6m 对手既不在 pursue 域也不触发 CLOSE-PUSH/FLANK "
                           "时由 OPPONENT-LOST 系接管的风险)",
                evidence=["F-103"],
                bloodline="970c209 -> mh_rules_topo_B (触发域重组)",
                parent="970c209",
                source="PM Sprint 29 裁决 A1 + FP-NEG-002 死代码教训 (S27)",
                provenance="simulation_rules.abdl 磁盘实读 (2026-08-08, line 68)",
            ))
        # 候选 C: SPEED-ADAPT 优先级 300→350 — 最后 50 步时间压力优先于 CAUTIOUS-EDGE(250)
        # (结束阶段速度爆发不被边缘谨慎过早抑制; 拓扑级=仅 priority 数字变更, 条件不变)
        if "priority: 300" in text:
            out.append(Variant(
                id="mh_rules_topo_C",
                layer="rules",
                target_file=HARNESS_FILES["rules"],
                diff=[{"old": "priority: 300",
                       "new": "priority: 350",
                       "expected": 1}],
                hypothesis="S29 A1-拓扑C (优先级重排): SPEED-ADAPT 300→350 — 时间压力 (>50 步) "
                           "优先于 CAUTIOUS-EDGE(250) 边缘谨慎: 结束阶段速度爆发不被过早抑制, "
                           "与 Adaptive Auto-Harness 'Harness Tree 路由' 同构 (不同状态路由到 "
                           "不同优先级策略)",
                evidence=["F-106"],
                bloodline="970c209 -> mh_rules_topo_C (优先级重排)",
                parent="970c209",
                source="PM Sprint 29 裁决 A1 + Adaptive Auto-Harness (arXiv:2606.01770)",
                provenance="simulation_rules.abdl 磁盘实读 (2026-08-08, line 132)",
            ))
        # ------------------------------------------------------------------
        # Sprint 31 (PM 裁决 P0): 规则拓扑第二波 — 基于 FP-NEG-004 branch_hist 修正归因
        #   S29 假设证伪: 60 步局不是"L2 空洞"而是 FLANK 侧翼死循环。
        #   基线 10 局 branch_hist 全景 (S31 T1 实证):
        #     FLANK 类分支全局占比 67.3% (144/214 触发)
        #     慢局 (42/49/60步) 全部 FLANK 主导 (86%/80%/75%), 快局 (5-8步) CLOSE-PUSH 主导
        #     ep7 (60步): FLANK-RIGHT:45 + CAUTIOUS-EDGE:13 — 侧翼校准在边缘被
        #       CAUTIOUS-EDGE (BETWEEN 0.55-0.78) 与 FLANK (edge<0.80) 条件重叠区交替让路
        #   M2 四通道已就绪 (S30): branch_hist 熵第四通道可评估拓扑变更有效性。
        # ------------------------------------------------------------------
        # 候选 D: FLANK 角度阈值收紧 — 触发域收窄 (10°→15°), 小角度偏离不进入侧翼
        cnt_fr = text.count("sensor(opponent_angle) < -10")
        cnt_fl = text.count("sensor(opponent_angle) > 10")
        if cnt_fr >= 1 and cnt_fl >= 1:
            out.append(Variant(
                id="mh_rules_topo_D",
                layer="rules",
                target_file=HARNESS_FILES["rules"],
                diff=[{"old": "sensor(opponent_angle) < -10",
                       "new": "sensor(opponent_angle) < -15",
                       "expected": cnt_fr},
                      {"old": "sensor(opponent_angle) > 10",
                       "new": "sensor(opponent_angle) > 15",
                       "expected": cnt_fl}],
                hypothesis="S31 D-拓扑D (FLANK 触发域收窄): 侧翼角度阈值 ±10°→±15° — "
                           "小角度偏离 (10-15°) 不进入纯转向侧翼, 减少 FLANK 过度触发 "
                           "(基线 FLANK 全局 67.3%), 预期部分局转 CLOSE-PUSH 对齐窗口",
                evidence=["FP-NEG-004"],
                bloodline="970c209 -> mh_rules_topo_D (FLANK 触发域收窄)",
                parent="970c209",
                source="PM Sprint 31 裁决 T1 + FP-NEG-004 branch_hist 修正归因 (FLANK 67.3%)",
                provenance="simulation_rules.abdl 磁盘实读 (2026-08-08, line 104/113)",
            ))
        # 候选 E: CAUTIOUS-EDGE 循环打断 — 边缘让路条件收窄 (0.55→0.60)
        cnt_ce = text.count("BETWEEN(sensor(edge_proximity), 0.55, 0.78)")
        if cnt_ce >= 1:
            out.append(Variant(
                id="mh_rules_topo_E",
                layer="rules",
                target_file=HARNESS_FILES["rules"],
                diff=[{"old": "BETWEEN(sensor(edge_proximity), 0.55, 0.78)",
                       "new": "BETWEEN(sensor(edge_proximity), 0.60, 0.78)",
                       "expected": cnt_ce}],
                hypothesis="S31 E-拓扑E (边缘让路收窄): CAUTIOUS-EDGE 下界 0.55→0.60 — "
                           "0.55-0.60 边缘风险带让 FLANK 完成校准, 打断 ep7 (60步) 的 "
                           "FLANK↔CAUTIOUS-EDGE 交替死循环 (45+13 次)",
                evidence=["FP-NEG-004"],
                bloodline="970c209 -> mh_rules_topo_E (CAUTIOUS-EDGE 循环打断)",
                parent="970c209",
                source="PM Sprint 31 裁决 T1 + FP-NEG-004 (ep7 交替死循环)",
                provenance="simulation_rules.abdl 磁盘实读 (2026-08-08, line 141)",
            ))
        # 候选 F: FLANK 退出机制 — stuck_counter<3 打断连续侧翼死循环 (45 次无收敛)
        #   EXPLORE 已用 sensor(stuck_counter)<3 (line 150) — 引擎支持该传感器!
        cnt_fr2 = text.count("sensor(opponent_angle) < -15") if cnt_fr >= 1 else 0
        if cnt_fr >= 1 and cnt_fl >= 1:
            out.append(Variant(
                id="mh_rules_topo_F",
                layer="rules",
                target_file=HARNESS_FILES["rules"],
                diff=[{"old": "sensor(opponent_angle) < -10 AND sensor(opponent_dist) < 0.6 AND sensor(edge_proximity) < 0.80",
                       "new": "sensor(opponent_angle) < -10 AND sensor(opponent_dist) < 0.6 AND sensor(edge_proximity) < 0.80 AND sensor(stuck_counter) < 3",
                       "expected": 1},
                      {"old": "sensor(opponent_angle) > 10 AND sensor(opponent_dist) < 0.6 AND sensor(edge_proximity) < 0.80",
                       "new": "sensor(opponent_angle) > 10 AND sensor(opponent_dist) < 0.6 AND sensor(edge_proximity) < 0.80 AND sensor(stuck_counter) < 3",
                       "expected": 1}],
                hypothesis="S31 F-拓扑F (FLANK 退出机制): 侧翼加 stuck_counter<3 上限 — "
                           "打断 45 次连续侧翼无收敛 (基线 ep7 FLANK-RIGHT:45), 卡住 3 步后 "
                           "退出侧翼允许 L3 接管, 与 EXPLORE (stuck_counter<3) 同机制复用",
                evidence=["FP-NEG-004"],
                bloodline="970c209 -> mh_rules_topo_F (FLANK 退出机制)",
                parent="970c209",
                source="PM Sprint 31 裁决 T1 + FP-NEG-004 (FLANK 45 次无收敛)",
                provenance="simulation_rules.abdl 磁盘实读 (2026-08-08, line 104/113 + 引擎支持 stuck_counter)",
            ))

        # 候选 G (Sprint 33, PM 裁决 P0, D4-3 依据): CAUTIOUS-EDGE 移除评估
        #   topo_A 回放实证 (S31): CLOSE-PUSH edge 0.65→0.80 对齐后 CAUTIOUS-EDGE 13→0
        #   消失, 步数仅 -1 (60→59) → CAUTIOUS-EDGE 是近似冗余分支, 可被 CLOSE-PUSH
        #   无损替代。D4-3 规则: 触发域 ⊆ 邻居触发域且移除步数变化 ≤1 → 冗余候选。
        #   移除方式: 注释化整条规则块 (拓扑级文本变更, 非参数 bump, S29 禁令合规)。
        #   覆盖预检 (S32): edge 维度 0.55-0.78 区间被 CLOSE-PUSH <0.65 + FLANK <0.80
        #   覆盖 → 移除后无新增空洞 → 预检放行。
        cnt_g = text.count('  - id: "SIM-HEUR-CAUTIOUS-EDGE"')
        if cnt_g >= 1:
            out.append(Variant(
                id="mh_rules_topo_G",
                layer="rules",
                target_file=HARNESS_FILES["rules"],
                diff=[{"old": '  - id: "SIM-HEUR-CAUTIOUS-EDGE"\n'
                              '    level: 3\n'
                              '    condition: "BETWEEN(sensor(edge_proximity), 0.55, 0.78)"\n'
                              '    action: "EXECUTE(PolicyCautiousEdge) AND LOG(\'cautious_edge\')"\n'
                              '    priority: 250\n'
                              '    description: "When moderate edge risk, reduce speed and widen turns"\n'
                              '    context: "edge_awareness"\n'
                              '    source: "simulation_rules.abdl > L3 Heuristic"',
                       "new": '#  [S33 REMOVED] SIM-HEUR-CAUTIOUS-EDGE — 冗余分支 (D4-3 判定)\n'
                              '#    condition: "BETWEEN(sensor(edge_proximity), 0.55, 0.78)"\n'
                              '#    action: "EXECUTE(PolicyCautiousEdge) AND LOG(\'cautious_edge\')"\n'
                              '#    priority: 250\n'
                              '#    reason: topo_A 回放 (S31) CAUTIOUS-EDGE 13->0 消失步数仅 -1,\n'
                              '#    CLOSE-PUSH/FLANK 已覆盖其触发域, 移除评估 (S33 候选 G)',
                       "expected": cnt_g}],
                hypothesis="S33 G-候选G (CAUTIOUS-EDGE 移除): 注释化 SIM-HEUR-CAUTIOUS-EDGE — "
                           "D4-3 冗余判定 (topo_A 回放 13→0 触发消失步数仅 -1), 触发域 "
                           "BETWEEN(0.55,0.78) 已被 CLOSE-PUSH(<0.65)+FLANK(<0.80) 完全包含, "
                           "移除后预期步数变化 ≤1 且无新增 REGRESSION",
                evidence=["D4-3", "S31 topo_A 回放 (INCONCLUSIVE→SUSPICIOUS, M2 四通道捕获)"],
                bloodline="31fb72e -> mh_rules_topo_G (CAUTIOUS-EDGE 移除评估)",
                parent="31fb72e",
                source="PM Sprint 33 裁决 P0 + D4-3 冗余分支识别规则",
                provenance="simulation_rules.abdl 磁盘实读 (2026-08-08, line 137-144)",
            ))
    elif layer == "mapping":
        # ── 变体 C (Sprint 27 A1 v3): flank 弧线触发大幅收窄 0.20→0.15 (活路径, 实证驱动) ──
        # 因果裁决 v3: PM 推荐锚点均不可行 (V9_WINRATE_THRESHOLD=评估器及格线非行为参数 /
        # PUSH_REWARD_SCALE=零命中虚构 / reward 默认值=env 显式传参遮蔽 no-op)。
        # 实证阶梯: 首探 pursue 直冲窗=死代码 (FP-NEG-002, identical:true, rules 前提
        # dist>0.6 与直冲窗互斥); 修正 v2 flank 0.20→0.25=REGRESSION (winrate 1.00→0.90,
        # 更少弧线=负效应); S26 变体 D 0.20→0.18=INCONCLUSIVE (幅度不足)。
        # → 反向补齐: 0.20→0.15 (abs 0.05) 让 dist∈[0.15,0.20) 改走 FW_*_HARD 弧线
        #   (制胜策略强化), 预期 PASSED 或显著正 Q。flank 前提 dist<0.6 与 0.15 不互斥。
        cnt_sep = text.count("if dist < 0.20:")
        if cnt_sep >= 2:  # flank right + left 两处
            out.append(Variant(
                id="mh_mapping_001",
                layer="mapping",
                target_file=HARNESS_FILES["mapping"],
                diff=[{"old": "if dist < 0.20:",
                       "new": "if dist < 0.15:",
                       "expected": cnt_sep}],
                hypothesis="flank 弧线触发 0.20→0.15 (Sprint 27 A1 v3, 大幅收窄强化弧线): "
                           "dist∈[0.15,0.20) 的分离态改走 FW_*_HARD 弧线 (接触保持 0.23m/s "
                           "推力, 防 aggressive 推挤), 与 v2 放宽 REGRESSION 反向——"
                           "更少弧线=负效应实证后, 更多弧线预期正效应 (F-106 侧接触锁定 -37° 规避)",
                evidence=["F-106"],
                bloodline="970c209 -> mh_mapping_001 (flank 弧线收窄)",
                parent="970c209",
                source="PM Sprint 27 裁决 A1 + FP-NEG-002 + v2 REGRESSION 斜率定向",
                provenance="abdl_action_bridge.py 磁盘实读 (HEAD 970c209, 215/223 行)",
            ))
        # ── 变体 D (F-103/F-106): 压进弧线门 0.20 -> 0.18 ──
        # Sprint 19 修复: diff 声明真实 expected (text.count), 消除多匹配 FAIL
        # (S19_DIAG 实证: dist<0.20 当前工作树 3 处 — 注释+2 代码, 默认 expected=1 必 FAIL)
        cnt_dist = text.count("dist < 0.20")
        if cnt_dist > 0:
            out.append(Variant(
                id="mh_mapping_002",
                layer="mapping",
                target_file=HARNESS_FILES["mapping"],
                diff=[{"old": "dist < 0.20", "new": "dist < 0.18",
                       "expected": cnt_dist}],
                hypothesis="压进弧线门 0.20→0.18m: 只有贴得更近才用 FW_*_HARD 弧线保推力, "
                           "中距优先纯转向对准 — 减少对称僵局 (F-103) 与弧线不收敛 (F-106)",
                evidence=["F-103", "F-106"],
                bloodline="970c209 -> mh_mapping_002",
                parent="970c209",
                source="failure_analysis(F-103,F-106)",
                provenance="abdl_action_bridge.py 磁盘实读 (HEAD 970c209)",
            ))

    elif layer == "physics":
        # ── 物理变体: 从磁盘自适应当前动量系数 (避免子串误匹配) ──
        m = re.search(r"momentum = net \* TIMESTEP \* (\d+(?:\.\d+)?)", text)
        if not m:
            return _seed_variants("physics", defects, "物理文件未匹配到动量行")
        cur = float(m.group(1))
        max_lin = MAX_LINEAR_SPEED

        # ROUND 2 授权: mh_physics_002 (0.90) + mh_physics_003 (0.875 二分插值)
        # 物理约束说明: 动量系数是无量纲碰撞冲量倍率, 非速度本身;
        # 结果速度由驱动动作上限 (<=0.53 m/s) 决定, 与 0.534 物理上限正交。
        # PM 授权范围内 (0.85->0.875/0.90) 均不触顶。
        if cur < 0.90:
            out.append(_mk_physics(
                cur, round(cur + 0.05, 3), "mh_physics_002",
                f"动量梯度 {cur}->{cur+0.05:.3f}: 继续压缩对称僵局窗口 (F-103); "
                f"若 >370 步反弹则触发 PM 硬性回滚条件 (回滚至 {cur})",
                ["F-103"], "2181108"))
        if abs(cur - 0.85) < 1e-9:
            out.append(_mk_physics(
                cur, 0.875, "mh_physics_003",
                "二分插值 0.875 (0.85 与 0.90 中点): 测绘帕累托前沿精确曲率 — "
                "若逼近 360 步, 说明最优在 0.86~0.88 陡峭效率悬崖 (PM 裁决 1)",
                ["F-103"], "2181108"))
        # ROUND 3 授权: mh_physics_004 (0.90 -> 0.95 对照 A, 验证线性收益延续)
        if cur <= 0.90:
            out.append(_mk_physics(
                cur, 0.95, "mh_physics_004",
                "动量梯度 0.90→0.95 (对照 A): 验证动量是否继续线性收益; "
                "若 0.95 步数 > 360, 说明 0.90 附近存在最优拐点; "
                "1.0 为硬上限 (对应物理极限, 不可逾越)",
                ["F-103"], "d8ad9d7"))
        if not out:
            return _seed_variants("physics", defects, "物理动量已在边界, 无新梯度")
        # 旧的 mh_physics_001 (0.8->0.85) 仅在基线仍为 0.8 时生成 (向后兼容)
        if abs(cur - 0.8) < 1e-9:
            out.insert(0, _mk_physics(
                cur, 0.85, "mh_physics_001",
                "推力碰撞动量系数 0.8→0.85: 压缩对称僵局窗口 (F-103)",
                ["F-103"], "970c209"))

    elif layer == "action_map":
        # ── Sprint 28 A1 (PM 裁决, P0): TURN_*_MED 轮速增益 0.6 -> 0.8 ──
        # 可达性检查 (FP-NEG-002 新规则) 已通过: TURN_R_MED 调用点
        #   abdl_action_bridge.py:217 (mapping flank 分离态) + wheel_to_discrete.py:198
        #   (heuristic fallback); TURN_L_MED 调用点 abdl_action_bridge.py:225 +
        #   wheel_to_discrete.py:162/196 — 全部在评估路径上, 非死代码。
        # 对称性要求: PM 指令只提 TURN_R_MED, 但左右轮速必须对称保持
        #   (单侧增益会引入转向偏差, 违反物理对称约束), 故 L/R 同步 0.6->0.8。
        # 锚点用 "Action.TURN_*_MED: (0.0, ±0.6)" 精确匹配 ACTION_MAP 实际生效值
        #   (枚举注释行 "TURN_R_MED = 11  # (0.0, -0.6)" 不含 Action. 前缀, 不会误匹配)。
        cnt_r = text.count("Action.TURN_R_MED: (0.0, -0.6)")
        cnt_l = text.count("Action.TURN_L_MED: (0.0, 0.6)")
        if cnt_r >= 1 and cnt_l >= 1:
            out.append(Variant(
                id="mh_action_map_001",
                layer="action_map",
                target_file=HARNESS_FILES["action_map"],
                diff=[
                    {"old": "Action.TURN_R_MED: (0.0, -0.6)",
                     "new": "Action.TURN_R_MED: (0.0, -0.8)",
                     "expected": cnt_r},
                    {"old": "Action.TURN_L_MED: (0.0, 0.6)",
                     "new": "Action.TURN_L_MED: (0.0, 0.8)",
                     "expected": cnt_l},
                ],
                hypothesis="TURN_*_MED 轮速增益 0.6→0.8 (Sprint 28 A1, PM 裁决 P0): "
                           "中速转向轮速幅值提升 33% — flank 分离态 (mapping) 与 heuristic "
                           "回退 (physics 层) 的转向到位更快, 压缩直冲/贴边对局的姿态调整耗时; "
                           "轮速增益是行为参数 (非评估器参数), 直接作用于动作执行层, "
                           "预期缩短 avg_steps 或提升获胜回合 (F-103 对称僵局 / F-106 侧接触锁定)",
                evidence=["F-103", "F-106"],
                bloodline="970c209 -> mh_action_map_001 (TURN_*_MED 轮速增益)",
                parent="970c209",
                source="PM Sprint 28 裁决 A1 + FP-NEG-002 可达性检查 (abdl_action_bridge.py:217/225, wheel_to_discrete.py:162/196/198)",
                provenance="wheel_to_discrete.py 磁盘实读 (HEAD 970c209, ACTION_MAP 81/84 行)",
            ))
        else:
            return _seed_variants("action_map", defects,
                                  "wheel_to_discrete.py 未匹配到 TURN_*_MED 锚点 "
                                  f"(R={cnt_r}, L={cnt_l})")


    elif layer == "rules3":
        # ── ROUND 3: mh_rules_003 (对照 B): FLANK 15° -> 12° 激进收窄 ──
        # 磁盘当前 FLANK=15° (ROUND 2 保留)。12° 复用既有角度值 (15/10 之间的既有刻度,
        # CLOSE-PUSH 10° 窗已有先例), 零新魔数。
        if text.count("sensor(opponent_angle) > 15") >= 1 and \
           text.count("sensor(opponent_angle) < -15") >= 1:
            out.append(Variant(
                id="mh_rules_003",
                layer="rules",
                target_file=HARNESS_FILES["rules"],
                diff=[
                    {"old": "sensor(opponent_angle) < -15",
                     "new": "sensor(opponent_angle) < -12",
                     "expected": 1},
                    {"old": "sensor(opponent_angle) > 15",
                     "new": "sensor(opponent_angle) > 12",
                     "expected": 1},
                ],
                hypothesis="FLANK 15°→12° 激进收窄 (对照 B): 验证 FLANK 角度极限 — "
                           "若步数反弹 (过冲/振荡), 说明 15° 是当前摩擦下的最佳切角; "
                           "12° 复用既有角度刻度, 零新魔数 (F-106 框架)",
                evidence=["F-106"],
                bloodline="d8ad9d7 -> mh_rules_003",
                parent="d8ad9d7",
                source="failure_analysis(F-106) + ROUND 2 实证 (290 步)",
                provenance="simulation_rules.abdl 磁盘实读 (HEAD d8ad9d7, FLANK=15°)",
            ))

    if not out:
        return _seed_variants(layer, defects, f"{HARNESS_FILES[layer]} 未匹配到已知阈值")
    return out


# 种子模板 (仅文件缺失/未匹配时降级用; 与 domain_spec 种子基线的参数一致)
_SEED_PARAMS = {
    "rules": [
        {"old": "BETWEEN(sensor(opponent_angle), -15, 15)",
         "new": "BETWEEN(sensor(opponent_angle), -10, 10)",
         "hypothesis": "近战接战窗 ±15°→±10° (F-100)", "evidence": ["F-100"],
         "perturb": {"mode": "abs", "threshold": 8.0, "unit": "度", "kind": "角度锚点"}},
        {"old": "sensor(edge_proximity) < 0.80",
         "new": "sensor(edge_proximity) < 0.72",
         "hypothesis": "侧翼边沿门 0.80→0.72 (F-106)", "evidence": ["F-106"],
         "perturb": {"mode": "rel", "threshold": 0.20, "unit": "相对", "kind": "边沿门阈值(0-1 归一化)"}},
    ],
    "mapping": [
        # Sprint 27 A1 修正 v3: flank 分离阈值 0.20→0.15 (大幅收窄, 更多弧线)。
        # 因果裁决 v3 (实证驱动): 
        #   * 首探 pursue 直冲窗 = 死代码 (FP-NEG-002, identical:true)
        #   * 修正 v2 flank 0.20→0.25 (放宽纯转向区) = REGRESSION (winrate 1.00→0.90)
        #     → 斜率方向明确: 更少弧线=负效应
        #   * S26 变体 D 0.20→0.18 (小幅收窄) = INCONCLUSIVE (幅度不足)
        #   → 反向补齐: 0.20→0.15 (abs 0.05) 让 dist∈[0.15,0.20) 改走 FW_*_HARD 弧线
        #     (制胜策略强化), 预期 PASSED 或显著正 Q
        # M3 abs 模式: 距离绝对差 0.05, threshold 0.05 直接达标。
        {"old": "if dist < 0.20:",
         "new": "if dist < 0.15:",
         "hypothesis": "flank 弧线触发 0.20→0.15 (Sprint 27 A1 v3, 大幅收窄强化弧线, F-106)",
         "evidence": ["F-106"],
         "perturb": {"mode": "abs", "threshold": 0.05, "unit": "距离", "kind": "flank 弧线触发阈值"}},
        {"old": "dist < 0.20", "new": "dist < 0.18",
         "hypothesis": "压进弧线门 0.20→0.18 (F-103/F-106)", "evidence": ["F-103", "F-106"],
         "perturb": {"mode": "rel", "threshold": 0.20, "unit": "相对", "kind": "距离阈值"}},
    ],
    "physics": [
        # Sprint 25 A1 修复: 旧锚点 TIMESTEP * 0.8 已死 (工作树演进为
        # momentum = net * TIMESTEP * 1.0)。改为动态锚点: "old" 用正则锚串
        # (anchor=regex), 主循环解析当前动量系数 cur, new 由 cur 计算 —
        # 永远对齐真实工作树 (S19 FP-MC-017 动态适配原则)。
        {"anchor": "regex",
         "old": r"momentum = net \* TIMESTEP \* ([\d.]+)",
         "new": None,  # 由 cur 计算: cur + 0.05 (主循环注入)
         "delta": 0.05,  # 动量系数 +0.05
         "replacement": "momentum = net * TIMESTEP * {coef}",
         "hypothesis": "动量系数 +0.05 (F-103, 自适应当前值)",
         "evidence": ["F-103"],
         "perturb": {"mode": "abs", "threshold": 0.20, "unit": "绝对", "kind": "动量系数"}},
        # Sprint 25 A1 修复: 旧锚点 (DOHYO_RADIUS - r) / DOHYO_EDGE_ZONE (线性)
        # 已演进为二次形式 (行 309)。锚定已演进的二次形式, 扰动指数 2 -> 3
        # (更强的边沿抓地衰减 = 更早进入安全区, F-103/F-104 同向验证)。
        {"old": "((DOHYO_RADIUS - r) / DOHYO_EDGE_ZONE) * ((DOHYO_RADIUS - r) / DOHYO_EDGE_ZONE)",
         "new": "((DOHYO_RADIUS - r) / DOHYO_EDGE_ZONE) * ((DOHYO_RADIUS - r) / DOHYO_EDGE_ZONE) * ((DOHYO_RADIUS - r) / DOHYO_EDGE_ZONE)",
         "hypothesis": "抓地衰减二次→三次 (F-103/F-104)", "evidence": ["F-103", "F-104"],
         "perturb": None},
        # Sprint 25 A1: physics seed_3 — 动态锚点 GRIP_DECAY (行 47, 环境变量
        # BOTTLE_GRIP_DECAY 默认 0.10)。扰动 0.10->0.15: 边沿区抓地衰减加大,
        # 滑出边缘更快减速 (行为变化可感知; 环境变量注入, 无工作树污染)。
        {"anchor": "regex",
         "old": r'GRIP_DECAY = float\(os\.environ\.get\("BOTTLE_GRIP_DECAY", "([\d.]+)"\)\)',
         "new": None,  # 由 cur 计算: cur + 0.05 (主循环注入)
         "delta": 0.05,
         "replacement": 'GRIP_DECAY = float(os.environ.get("BOTTLE_GRIP_DECAY", "{coef}"))',
         "hypothesis": "GRIP_DECAY 0.10→0.15 (F-103, 抓地衰减加大)",
         "evidence": ["F-103"],
         "perturb": {"mode": "abs", "threshold": 0.20, "unit": "绝对", "kind": "抓地衰减系数"}},
    ],
    "action_map": [
        # Sprint 28 A1 (PM 裁决 P0): TURN_*_MED 轮速增益 0.6->0.8 (对称保持)。
        # 降级路径种子 — 主路径 _gen("action_map") 生成 mh_action_map_001;
        # 此处仅当 wheel_to_discrete.py 锚点文本演进后主路径未匹配时使用。
        # M3 abs 模式: 轮速绝对差 0.2, threshold 0.20 恰好达标 (0.6->0.8 = 0.2)。
        {"old": "Action.TURN_R_MED: (0.0, -0.6)",
         "new": "Action.TURN_R_MED: (0.0, -0.8)",
         "hypothesis": "TURN_R_MED 轮速 -0.6→-0.8 (Sprint 28 A1, 右转增益 33%)",
         "evidence": ["F-103", "F-106"],
         "perturb": {"mode": "abs", "threshold": 0.20, "unit": "绝对", "kind": "TURN_R_MED 轮速"}},
        {"old": "Action.TURN_L_MED: (0.0, 0.6)",
         "new": "Action.TURN_L_MED: (0.0, 0.8)",
         "hypothesis": "TURN_L_MED 轮速 0.6→0.8 (Sprint 28 A1, 左转增益 33%, 对称保持)",
         "evidence": ["F-103", "F-106"],
         "perturb": {"mode": "abs", "threshold": 0.20, "unit": "绝对", "kind": "TURN_L_MED 轮速"}},
    ],
}


# --------------------------------------------------------------------------
# Sprint 22 M3 扩展: 种子扰动幅度阈值 (D2_PRIOR 下沉至种子生成路径)
# 依据: FP-MC-019 (蒸馏规则未被生成路径消费) — S21 实证 rules 层 INCONCLUSIVE 10/10
# 根因: 种子模板扰动幅度 (如角度 ±2°~±5°) 远低于行为感知阈值 (角度 10°)
# --------------------------------------------------------------------------
SEED_PERTURBATION_THRESHOLDS = {
    # S23 回标: rules 10.0 -> 8.0 (INCONCLUSIVE 下界 5° + REGRESSION 上界 10°(不对称) 取安全区间)
    "rules":   {"kind": "角度", "threshold": 8.0, "mode": "abs", "unit": "度",
                "note": "S23 回标: 感知下界 5° / 劣化上界 10°(不对称), 安全区间 8°"},
    "mapping": {"kind": "阈值", "threshold": 0.20, "mode": "rel", "unit": "相对"},
    "physics": {"kind": "系数", "threshold": 0.20, "mode": "abs", "unit": "绝对"},
    # Sprint 28 A1: 轮速绝对差 0.6->0.8 = 0.2, 恰好达标 (无需 bump)。
    "action_map": {"kind": "轮速", "threshold": 0.20, "mode": "abs", "unit": "绝对",
                   "note": "S28 A1: TURN_*_MED 0.6->0.8 幅度 0.2, 与阈值 0.20 对齐"},
}


def _nums(s):
    """提取字符串中所有数值 (含负数/小数)。"""
    return [float(x) for x in re.findall(r"[-+]?\d*\.?\d+", s or "")]


def perturbation_magnitude(old: str, new: str, layer: str, cfg: dict = None):
    """M3: 计算种子 diff 扰动幅度。返回 (mag, cfg) ; 无法解析返回 (None, cfg)。

    cfg 优先取参数级配置 (p["perturb"]), 缺省回退层默认表。
    abs 模式: max|new_i - old_i| (位置配对)
    rel 模式: max|new_i - old_i| / max|old_i| (相对变化, 防除零)
    """
    if cfg is None:
        cfg = SEED_PERTURBATION_THRESHOLDS.get(layer)
    no, nn = _nums(old), _nums(new)
    if cfg is None or not no or not nn:
        return None, cfg
    if cfg["mode"] == "rel":
        denom = max(abs(x) for x in no) or 1.0
        mag = max((abs(b - a) for a, b in zip(no, nn)), default=0.0) / denom
    else:
        mag = max((abs(b - a) for a, b in zip(no, nn)), default=0.0)
    return mag, cfg


def _fmt_num(x, orig):
    """按原始数值格式输出 (整数保持整数, 小数 2 位)。"""
    if abs(orig - round(orig)) < 1e-9:
        return "%.0f" % x
    return "%.2f" % x


def bump_magnitude(old: str, new: str, layer: str, cfg: dict):
    """M3: 加大扰动至满足阈值。返回 (new_adj, note) ; 无法加大返回 (None, note)。

    S23 修复 (FP-MC-020 根因): BETWEEN 对称区间 (数值对 b≈-a) 双侧同步调整,
    保持区间对称语义——S22 REGRESSION 根因正是单侧替换破坏对称
    (±15,15 -> -5,10 不对称窗, defensive 对手 winrate 0.0)。
    非对称形态走原单侧逻辑 (保持方向 + 数值格式)。
    """
    no, nn = _nums(old), _nums(new)
    if not no or not nn:
        return None, "无法解析数值"
    if cfg["mode"] == "rel":
        denom = max(abs(x) for x in no) or 1.0
        target = cfg["threshold"] * denom
    else:
        target = cfg["threshold"]
    pat = re.compile(r"[-+]?\d*\.?\d+")
    # --- 对称区间 (BETWEEN): 双侧同步, 保持对称语义 ---
    if len(no) == 2 and len(nn) == 2 and abs(no[0] + no[1]) < 1e-9 and abs(nn[0] + nn[1]) < 1e-9:
        a0, b0 = no[0], nn[0]
        nb0 = a0 + target if b0 >= a0 else a0 - target
        nb1 = -nb0
        ms = list(pat.finditer(new))
        if len(ms) >= 2:
            new_adj = (new[:ms[0].start()] + _fmt_num(nb0, nn[0])
                       + new[ms[0].end():ms[1].start()] + _fmt_num(nb1, nn[1])
                       + new[ms[1].end():])
            mag2, _ = perturbation_magnitude(old, new_adj, layer, cfg)
            if mag2 is not None and mag2 + 1e-9 >= cfg["threshold"]:
                return new_adj, (f"扰动加大(对称) {b0:g}->{nb0:g}± "
                                 f"(阈值 {cfg['threshold']:g}{cfg['unit']})")
        return None, "对称区间加大失败"
    # --- 非对称 (单数值/多数值): 原单侧逻辑 ---
    a0, b0 = no[0], nn[0]
    nb = a0 + target if b0 >= a0 else a0 - target
    # S23 符号安全网 (FP-MC-020 通用防线): 数值语义域检查——
    # 0.80 -> -7.20 (abs 阈值误用于 0-1 归一化参数) 会生成恒 True 条件, 破坏语义
    if a0 > 0 and nb < 0:
        return None, f"加大后跨越符号边界 ({a0:g}->{nb:g}), 语义破坏"
    if a0 < 0 and nb > 0:
        return None, f"加大后跨越符号边界 ({a0:g}->{nb:g}), 语义破坏"
    m = pat.search(new)
    if not m:
        return None, "无法定位数值"
    new_adj = new[:m.start()] + _fmt_num(nb, nn[0]) + new[m.end():]
    mag2, _ = perturbation_magnitude(old, new_adj, layer, cfg)
    if mag2 is None or mag2 + 1e-9 < cfg["threshold"]:  # 浮点容差
        return None, f"加大后仍不足 ({mag2} < {cfg['threshold']})"
    return new_adj, f"扰动加大 {b0:g}->{nb:g} (阈值 {cfg['threshold']:g}{cfg['unit']})"


def _seed_variants(layer: str, defects: dict, reason: str) -> list:
    """降级路径 (Sprint 19 修复): 感知当前工作树的动态种子生成。

    修复前: 静态历史模板 (基于旧 HEAD 970c209) — 工作树演进后锚点必失效,
    生成即 FAIL (apply 0 次匹配)。三类失效实证 (S19_DIAG, 5 轮 apply 成功率 0%):
      A. 锚点缺失: BETWEEN(opponent_angle,-15,15) / TIMESTEP*0.8 在当前工作树 0 处
      B. 多匹配:   dist<0.20 出现 3 处 (注释+2代码) 而默认 expected=1
      C. 死锚点:   physics 动量已演进到 TIMESTEP*1.0

    修复后: 读取目标文件真实文本, 对每个种子参数检查 text.count(old):
      存在 -> 生成并声明真实 expected (多匹配也干净 apply)
      缺失 -> 跳过该种子 (不生成必 FAIL 候选)
    返回 [] 表示该层无可应用候选 (而非生成垃圾)。
    """
    out = []
    # Sprint 24 裁决 2: rules 层种子移出扰动循环 (RULES CLOSED 外部治理,
    # 自 ROUND 11 起禁止 rules 层新候选, 含距离阈值扰动)。
    # S22/S23 实证: rules 层扰动与 regressive 劣化强相关 (3/3 REGRESSION)。
    if layer == "rules":
        print("[seed] rules-layer excluded (RULES CLOSED 外部治理, Sprint 24 裁决 2)",
              flush=True)
        return out
    target = os.path.join(REPO_ROOT, HARNESS_FILES[layer])
    text = _read_text(target) or ""
    if not text:
        return out  # 文件缺失: 无候选可生成 (修复前会生成必 FAIL 候选)
    for i, p in enumerate(_SEED_PARAMS[layer], start=1):
        # Sprint 25 A1: 动态锚点 (anchor="regex") — physics 层种子 1。
        # 旧锚点 (TIMESTEP * 0.8 等) 在 S19 工作树演进后已死, 静态 old 串必然
        # count=0 跳过 (S22/S23 期间 physics 每次只产出 1 个种子的根因)。
        # 动态锚点: 正则解析当前数值, new 由 cur 计算 — 永远对齐真实工作树。
        if p.get("anchor") == "regex":
            m = re.search(p["old"], text)
            if not m:
                print(f"  [seed] {layer} seed_{i} 正则锚点未命中, 跳过: {p['old'][:50]}",
                      flush=True)
                continue
            cur_str = m.group(1)
            try:
                cur = float(cur_str)
            except (TypeError, ValueError):
                print(f"  [seed] {layer} seed_{i} 锚点数值解析失败: {cur_str!r}", flush=True)
                continue
            # Sprint 25 A1: 动态扰动幅度按种子声明 (delta) — mapping 角度 -5°,
            # physics 动量 +0.05。replacement 模板声明行重建方式 (对齐工作树语法)。
            delta = p.get("delta", 0.05)
            new_coef = _fmt_num(cur + delta, cur + delta)
            new_line = p["replacement"].format(coef=new_coef)
            cnt_anchor = len(re.findall(p["old"], text))  # Sprint 19: 动态 expected
            diff = [{"old": m.group(0), "new": new_line, "expected": cnt_anchor}]
            cfg = p.get("perturb") or SEED_PERTURBATION_THRESHOLDS.get(layer)
            mag, _ = perturbation_magnitude(m.group(0), new_line, layer, cfg)
            m3_note = ""
            if cfg is not None and mag is not None and mag < cfg["threshold"]:
                new_adj, note = bump_magnitude(m.group(0), new_line, layer, cfg)
                if new_adj is not None:
                    new_line = new_adj
                    diff = [{"old": m.group(0), "new": new_adj,
                             "expected": cnt_anchor}]
                    m3_note = f"; M3: {note}"
                else:
                    print(f"  [seed] {layer} seed_{i} 扰动不足且无法加大, 跳过: "
                          f"({note})", flush=True)
                    continue
            out.append(Variant(
                id=f"mh_{layer}_seed_{i:03d}",
                layer=layer,
                target_file=HARNESS_FILES[layer],
                diff=diff,
                hypothesis=p["hypothesis"] + m3_note,
                evidence=p["evidence"],
                bloodline="SEED_TEMPLATE (动态锚点: 正则解析当前值 + M3 扰动校验)",
                parent="970c209",
                source="seed_template",
                provenance=reason,
            ))
            continue
        cnt = text.count(p["old"])
        if cnt == 0:
            print(f"  [seed] {layer} seed_{i} 锚点缺失 (0 处), 跳过: {p['old'][:50]}", flush=True)
            continue
        # Sprint 22 M3 扩展 + S23 参数级扰动配置:
        # cfg 优先参数级 (p["perturb"], 按参数语义声明 mode/threshold), 缺省回退层默认
        new_txt = p["new"]
        cfg = p.get("perturb") or SEED_PERTURBATION_THRESHOLDS.get(layer)
        mag, _ = perturbation_magnitude(p["old"], p["new"], layer, cfg)
        m3_note = ""
        if cfg is not None and mag is not None and mag < cfg["threshold"]:
            new_adj, note = bump_magnitude(p["old"], p["new"], layer, cfg)
            if new_adj is not None:
                new_txt = new_adj
                m3_note = f"; M3: {note}"
                print(f"  [seed] {layer} seed_{i} 扰动不足 ({mag:g}<{cfg['threshold']:g}{cfg['unit']}), "
                      f"加大: {p['new'][:40]} -> {new_adj[:40]}", flush=True)
            else:
                print(f"  [seed] {layer} seed_{i} 扰动不足且无法加大, 跳过: {p['new'][:40]} "
                      f"({note})", flush=True)
                continue
        out.append(Variant(
            id=f"mh_{layer}_seed_{i:03d}",
            layer=layer,
            target_file=HARNESS_FILES[layer],
            diff=[{"old": p["old"], "new": new_txt, "expected": cnt}],
            hypothesis=p["hypothesis"] + m3_note,
            evidence=p["evidence"],
            bloodline="SEED_TEMPLATE (动态适配: 锚点感知工作树 + M3 扰动校验)",
            parent="970c209",
            source="seed_template",
            provenance=reason,
        ))
    return out


# --------------------------------------------------------------------------
# 公开 API: generate_variants (PM 授权签名)
# --------------------------------------------------------------------------
def generate_variants(harness_snapshot: dict = None,
                      failure_analysis: dict = None,
                      pareto_frontier: dict = None,
                      max_per_layer: int = 1,
                      round_no: int = 1) -> list:
    """生成候选变体列表。

    Args:
        harness_snapshot : 可选; 五文件快照 (未来 outer_loop 传入), 当前直接读磁盘
        failure_analysis : 可选; 预解析缺陷库 {F-xxx}, None 时从磁盘解析
        pareto_frontier  : 可选; 预解析 Pareto 前沿, None 时从磁盘解析
        max_per_layer    : 每层返回最大候选数 (ROUND 1: 1 -> 3 候选)
        round_no         : ROUND 2 计划 = physics×2 (0.875/0.90 二分) + rules×1 (Circler)

    Returns:
        list[Variant] — ROUND 1: 规则1+映射1+物理1; ROUND 2: 规则1+物理2
    """
    defects = failure_analysis or load_failure_analysis()
    pareto = pareto_frontier or load_pareto()
    gate = load_last_gate_report()

    if round_no == 3:
        # ROUND 3 (PM 裁决 1): 正交组合优先
        #   mh_combined_001: FLANK 15° (基线已有, HEAD d8ad9d7) + 动量 0.85->0.90 叠加
        #   mh_physics_004 : 动量 0.90->0.95 (对照 A, 线性收益验证)
        #   mh_rules_003   : FLANK 15°->12° (对照 B, 角度极限验证)
        candidates = []
        # 主攻手: 组合变体 (规则层 diff 已在基线, 此处仅叠加物理层; diff 列表同时声明规则侧以记录血统)
        m_phys = re.search(r"momentum = net \* TIMESTEP \* (\d+(?:\.\d+)?)",
                           _read_text(os.path.join(REPO_ROOT, HARNESS_FILES["physics"])) or "")
        cur = float(m_phys.group(1)) if m_phys else 0.85
        combined = _mk_physics(
            cur, 0.90, "mh_combined_001",
            "正交叠加: 基线 FLANK 15° (d8ad9d7 已保留) + 动量 0.85→0.90 — "
            "探索线性物理收益与角度杠杆的乘法效应; 目标 < 290 步 (PM 裁决 1)",
            ["F-103", "F-106"], "d8ad9d7",
            layer="combined",
            extra_diff=[{"old": "sensor(opponent_angle) > 18", "new": "sensor(opponent_angle) > 15",
                         "expected": 0, "note": "基线已含 FLANK15°, 该 diff 仅记录血统"}])
        # 从候选列表中移除血统记录项 (expected=0 不实际应用)
        combined.diff = [d for d in combined.diff if d.get("expected", 1) != 0]
        candidates.append(combined)
        # 对照 A: 动量 0.95 (纯物理梯度)
        for v in _gen("physics", defects):
            if v.id == "mh_physics_004":
                candidates.append(v)
                break
        # 对照 B: FLANK 12°
        rules_txt = _read_text(os.path.join(REPO_ROOT, HARNESS_FILES["rules"])) or ""
        if "sensor(opponent_angle) > 15" in rules_txt:
            candidates.append(Variant(
                id="mh_rules_003", layer="rules",
                target_file=HARNESS_FILES["rules"],
                diff=[
                    {"old": "sensor(opponent_angle) < -15",
                     "new": "sensor(opponent_angle) < -12", "expected": 1},
                    {"old": "sensor(opponent_angle) > 15",
                     "new": "sensor(opponent_angle) > 12", "expected": 1},
                ],
                hypothesis="FLANK 15°→12° 激进收窄 (对照 B): 验证角度极限 — "
                           "若反弹说明 15° 为当前摩擦下最佳切角; 复用既有刻度零新魔数 (F-106)",
                evidence=["F-106"],
                bloodline="d8ad9d7 -> mh_rules_003", parent="d8ad9d7",
                source="ROUND 2 实证 (290 步) + F-106",
                provenance="simulation_rules.abdl 磁盘实读 (HEAD d8ad9d7)"))
    elif round_no == 4:
        # ROUND 4 (PM 裁决 1): 精细化搜索 — 围绕 15° 与 0.90 微扰动 (2×2 因子补全)
        #   基线: FLANK 15° + 动量 0.90 (mh_combined_001, 288 步, 当前帕累托前沿)
        #   mh_combined_002: FLANK 14° + 动量 0.89 (PM 建议方向 14°+0.89) — 主攻手
        #   mh_rules_004   : FLANK 14° 纯角度微扰 (对照 A — 角度是否仍是主杠杆)
        #   mh_physics_005 : 动量 0.89 纯物理微扰 (对照 B — 0.90 是否局部峰; 2×2 因子补全)
        #   目标: < 288 步 (超越 mh_combined_001)
        #   遗留队列: mh_physics_004 (0.95) 因 ROUND 3 突破性提前停止未评估,
        #             若动量单调延续建议 ROUND 5 向 1.0 硬上限推进
        candidates = []
        phys_txt = _read_text(os.path.join(REPO_ROOT, HARNESS_FILES["physics"])) or ""
        rules_txt = _read_text(os.path.join(REPO_ROOT, HARNESS_FILES["rules"])) or ""
        m_phys = re.search(r"momentum = net \* TIMESTEP \* (\d+(?:\.\d+)?)", phys_txt)
        cur_mom = float(m_phys.group(1)) if m_phys else 0.90
        has_flank15 = ("sensor(opponent_angle) > 15" in rules_txt
                       and "sensor(opponent_angle) < -15" in rules_txt)

        # 主攻手: mh_combined_002 = FLANK 14° + 动量 0.89 (双文件, PM 建议方向)
        if has_flank15 and abs(cur_mom - 0.90) < 1e-9:
            candidates.append(_mk_combined(
                0.90, 0.89, "15", "14", "mh_combined_002",
                "精细化正交叠加: FLANK 15°→14° + 动量 0.90→0.89 (PM 建议方向 14°+0.89) — "
                "在 mh_combined_001 (288) 邻域做 2×2 因子微扰, 探测前沿曲率与加性边界; "
                "目标 < 288 步",
                ["F-103", "F-106"], "9c6fd50"))
        # 对照 A: FLANK 14° 纯角度微扰 (mh_rules_004)
        if has_flank15:
            candidates.append(Variant(
                id="mh_rules_004", layer="rules",
                target_file=HARNESS_FILES["rules"],
                diff=[
                    {"old": "sensor(opponent_angle) < -15",
                     "new": "sensor(opponent_angle) < -14", "expected": 1},
                    {"old": "sensor(opponent_angle) > 15",
                     "new": "sensor(opponent_angle) > 14", "expected": 1},
                ],
                hypothesis="FLANK 15°→14° 纯角度微扰 (对照 A): 角度是否仍是主杠杆? "
                           "15°→14° 逐度边际测绘 (290→288 增益是否延续); "
                           "复用既有角度刻度, 零新魔数 (F-106 框架)",
                evidence=["F-106"],
                bloodline="9c6fd50 -> mh_rules_004", parent="9c6fd50",
                source="ROUND 3 实证 (combined 288) + F-106",
                provenance="simulation_rules.abdl 磁盘实读 (HEAD 9c6fd50, FLANK=15°)"))
        # 对照 B: 动量 0.89 纯物理微扰 (mh_physics_005, 2×2 因子补全)
        if abs(cur_mom - 0.90) < 1e-9:
            candidates.append(_mk_physics(
                0.90, 0.89, "mh_physics_005",
                "动量 0.90→0.89 纯物理微扰 (对照 B): 0.90 是否为局部峰? "
                "若 0.89 步数 > 360 说明 0.90 附近为最优邻域; "
                "完成 2×2 因子设计 (14°/15° × 0.89/0.90) 验证加性边界的局部稳定性",
                ["F-103"], "9c6fd50"))
    elif round_no == 5:
        # ROUND 5 (自组织, PM 硬性指示"每轮必产 1 个新变体"): 动量阶梯延续 + 角度阶梯
        #   基线: FLANK 15° + 动量 0.90 (mh_combined_001, 288 步, 帕累托前沿)
        #   mh_physics_006: 动量 0.90→0.95 (主攻手 — ROUND 3 遗留队列 mh_physics_004,
        #                   向 1.0 硬上限推进; FLANK 15° 处动量单调: 0.85→290, 0.89→289, 0.90→288)
        #   mh_rules_005   : FLANK 15°→13° (对照 A — 14° 中性, 13° 恢复坡度还是平台期?)
        #   mh_combined_003: FLANK 13° + 动量 0.95 (对照 B — 新点 (13°,0.95) 因子设计)
        #   目标: < 288 步 (超越 mh_combined_001)
        candidates = []
        phys_txt = _read_text(os.path.join(REPO_ROOT, HARNESS_FILES["physics"])) or ""
        rules_txt = _read_text(os.path.join(REPO_ROOT, HARNESS_FILES["rules"])) or ""
        m_phys = re.search(r"momentum = net \* TIMESTEP \* (\d+(?:\.\d+)?)", phys_txt)
        cur_mom = float(m_phys.group(1)) if m_phys else 0.90
        has_flank15 = ("sensor(opponent_angle) > 15" in rules_txt
                       and "sensor(opponent_angle) < -15" in rules_txt)

        # 主攻手: mh_physics_006 = 动量 0.90→0.95 (ROUND 3 遗留队列)
        if abs(cur_mom - 0.90) < 1e-9:
            candidates.append(_mk_physics(
                0.90, 0.95, "mh_physics_006",
                "动量 0.90→0.95 (ROUND 3 遗留 mh_physics_004): 动量阶梯在 FLANK 15° 处单调 "
                "(0.85→290, 0.89→289, 0.90→288), 向 1.0 硬上限推进; 若 <288 步则动量仍是主梯度",
                ["F-103"], "7e74be7"))
        # 对照 A: FLANK 15°→13° (mh_rules_005)
        if has_flank15:
            candidates.append(Variant(
                id="mh_rules_005", layer="rules",
                target_file=HARNESS_FILES["rules"],
                diff=[
                    {"old": "sensor(opponent_angle) < -15",
                     "new": "sensor(opponent_angle) < -13", "expected": 1},
                    {"old": "sensor(opponent_angle) > 15",
                     "new": "sensor(opponent_angle) > 13", "expected": 1},
                ],
                hypothesis="FLANK 15°→13° 纯角度微扰 (对照 A): 14° 处增益归零 (288 持平), "
                           "13° 是恢复坡度 (更早切入) 还是进入平台期; 零新魔数 (F-106)",
                evidence=["F-106"],
                bloodline="7e74be7 -> mh_rules_005", parent="7e74be7",
                source="ROUND 4 因子表 (14° 中性) + F-106",
                provenance="simulation_rules.abdl 磁盘实读 (HEAD 7e74be7, FLANK=15°)"))
        # 对照 B: FLANK 13° + 动量 0.95 (mh_combined_003, 新点因子设计)
        if has_flank15 and abs(cur_mom - 0.90) < 1e-9:
            candidates.append(_mk_combined(
                0.90, 0.95, "15", "13", "mh_combined_003",
                "组合变体: FLANK 13° + 动量 0.95 — 在 (13°, 0.95) 新点完成因子设计; "
                "若加性成立: 288 + Δ(0.95) + Δ(13°); 目标 < 288 步",
                ["F-103", "F-106"], "7e74be7"))
    elif round_no == 6:
        # ROUND 6 (自组织延续): 动量 1.0 硬上限探针 + 角度平台期边缘 (12°)
        #   基线: FLANK 15° + 动量 0.95 (mh_physics_006, 286 步, 帕累托前沿)
        #   mh_physics_007: 动量 0.95→1.0 (主攻手 — 硬上限探针; PM 裁决 2: 动量达 1.0
        #                   且边际 <1% 才评估 TASK-005f 视觉解冻)
        #   mh_rules_006   : FLANK 15°→12° (对照 A — ROUND 3 遗留 rules_003; 13°-15° 平台期,
        #                   12° 探平台边缘, 接近 CLOSE-PUSH 15° 窗)
        #   mh_combined_004: FLANK 12° + 动量 1.0 (对照 B — 新点 (12°,1.0) 因子设计)
        #   目标: < 286 步 (超越 mh_physics_006)
        candidates = []
        phys_txt = _read_text(os.path.join(REPO_ROOT, HARNESS_FILES["physics"])) or ""
        rules_txt = _read_text(os.path.join(REPO_ROOT, HARNESS_FILES["rules"])) or ""
        m_phys = re.search(r"momentum = net \* TIMESTEP \* (\d+(?:\.\d+)?)", phys_txt)
        cur_mom = float(m_phys.group(1)) if m_phys else 0.95
        has_flank15 = ("sensor(opponent_angle) > 15" in rules_txt
                       and "sensor(opponent_angle) < -15" in rules_txt)

        # 主攻手: mh_physics_007 = 动量 0.95→1.0 (硬上限)
        if abs(cur_mom - 0.95) < 1e-9:
            candidates.append(_mk_physics(
                0.95, 1.0, "mh_physics_007",
                "动量 0.95→1.0 (硬上限探针): 动量阶梯单调 (0.89→289, 0.90→288, 0.95→286), "
                "1.0 为物理层硬上限; 若 >=286 步则动量收益饱和于 0.95 附近 (<1% 边际), "
                "触发 PM 裁决 2 的 TASK-005f 视觉解冻评估条件",
                ["F-103"], "1517a2e"))
        # 对照 A: FLANK 15°→12° (mh_rules_006, ROUND 3 遗留)
        if has_flank15:
            candidates.append(Variant(
                id="mh_rules_006", layer="rules",
                target_file=HARNESS_FILES["rules"],
                diff=[
                    {"old": "sensor(opponent_angle) < -15",
                     "new": "sensor(opponent_angle) < -12", "expected": 1},
                    {"old": "sensor(opponent_angle) > 15",
                     "new": "sensor(opponent_angle) > 12", "expected": 1},
                ],
                hypothesis="FLANK 15°→12° 纯角度微扰 (对照 A, ROUND 3 遗留 rules_003): "
                           "13°-15° 平台期 (全部 288), 12° 探平台边缘 — 接近 CLOSE-PUSH 15° 窗, "
                           "测试角度杠杆是否在窗口边界重新获得收益; 零新魔数 (F-106)",
                evidence=["F-106"],
                bloodline="1517a2e -> mh_rules_006", parent="1517a2e",
                source="ROUND 5 平台期证据 + F-106",
                provenance="simulation_rules.abdl 磁盘实读 (HEAD 1517a2e, FLANK=15°)"))
        # 对照 B: FLANK 12° + 动量 1.0 (mh_combined_004, 新点因子设计)
        if has_flank15 and abs(cur_mom - 0.95) < 1e-9:
            candidates.append(_mk_combined(
                0.95, 1.0, "15", "12", "mh_combined_004",
                "组合变体: FLANK 12° + 动量 1.0 — 在 (12°, 1.0) 新点完成因子设计; "
                "若加性成立: 286 + Δ(1.0) + Δ(12°); 目标 < 286 步",
                ["F-103", "F-106"], "1517a2e"))
    elif round_no == 7:
        # ROUND 7 (2e33751 自组织延续): 新正交轴 (grip decay) 三次方下探 + 角度平台期外下探
        #   基线: grip 二次衰减 + 动量 1.0 + FLANK 15° + mapping 40° (seed_002 = 259, 帕累托前沿)
        #   mh_physics_008: grip decay 二次→三次 (主攻手 — seed_002 新轴延续; 边缘区抓地损失
        #                   更快 → 内圈高抓地权重进一步上升; 若增益 <1 步则 grip 轴趋饱和)
        #   mh_rules_007   : FLANK 15°→10° (对照 A — 12°-15° 平台期外下探, 边界窗测试)
        #   mh_combined_005: grip 三次 + FLANK 10° (对照 B — 新点 (cubic,10°) 因子设计)
        #   目标: < 259 步 (超越 seed_002)
        candidates = []
        phys_txt = _read_text(os.path.join(REPO_ROOT, HARNESS_FILES["physics"])) or ""
        rules_txt = _read_text(os.path.join(REPO_ROOT, HARNESS_FILES["rules"])) or ""
        grip_quad = ("((DOHYO_RADIUS - r) / DOHYO_EDGE_ZONE) * ((DOHYO_RADIUS - r) / DOHYO_EDGE_ZONE)")
        grip_cubic = grip_quad + " * ((DOHYO_RADIUS - r) / DOHYO_EDGE_ZONE)"
        has_quad_grip = grip_quad in phys_txt
        has_flank15 = ("sensor(opponent_angle) > 15" in rules_txt
                       and "sensor(opponent_angle) < -15" in rules_txt)

        # 主攻手: mh_physics_008 = grip decay 二次→三次 (新轴延续)
        if has_quad_grip:
            candidates.append(Variant(
                id="mh_physics_008", layer="physics",
                target_file=HARNESS_FILES["physics"],
                diff=[{"old": grip_quad, "new": grip_cubic, "expected": 1}],
                hypothesis="grip decay 二次→三次 (seed_002 新轴延续): 边缘区抓地损失更快, "
                           "内圈高抓地权重进一步上升; 若增益 <1 步则 grip 轴趋饱和, "
                           "宣告新轴闭合, 转向角度/奖励函数轴",
                evidence=["F-103", "F-104"], parent="2e33751",
                bloodline="2e33751 (seed_002 轴延续: grip 二次→三次)",
                source="ROUND 6-B sweep 首杀证据 + F-103/F-104",
                provenance="lightweight_env.py 磁盘实读 (HEAD 2e33751, grip 二次衰减)"))
        # 对照 A: FLANK 15°→10° (mh_rules_007, 平台期外下探)
        if has_flank15:
            candidates.append(Variant(
                id="mh_rules_007", layer="rules",
                target_file=HARNESS_FILES["rules"],
                diff=[
                    {"old": "sensor(opponent_angle) < -15",
                     "new": "sensor(opponent_angle) < -10", "expected": 1},
                    {"old": "sensor(opponent_angle) > 15",
                     "new": "sensor(opponent_angle) > 10", "expected": 1},
                ],
                hypothesis="FLANK 15°→10° 纯角度下探 (对照 A): 12° 持平后探平台期外, "
                           "接近 CLOSE-PUSH ±10° 窗; 测试角度杠杆在窗口外是否重新获得收益; "
                           "零新魔数 (F-106)",
                evidence=["F-106"], parent="2e33751",
                bloodline="2e33751 -> mh_rules_007",
                source="ROUND 6 角度平台期证据 + F-106",
                provenance="simulation_rules.abdl 磁盘实读 (HEAD 2e33751, FLANK=15°)"))
        # 对照 B: grip 三次 + FLANK 10° (mh_combined_005, 新点因子设计)
        if has_quad_grip and has_flank15:
            flank_diff = [
                {"old": "sensor(opponent_angle) < -15",
                 "new": "sensor(opponent_angle) < -10", "expected": 1},
                {"old": "sensor(opponent_angle) > 15",
                 "new": "sensor(opponent_angle) > 10", "expected": 1},
            ]
            candidates.append(Variant(
                id="mh_combined_005", layer="combined",
                target_file=HARNESS_FILES["physics"],
                diff=[{"old": grip_quad, "new": grip_cubic, "expected": 1}],
                extra_files={"rules": flank_diff},
                hypothesis="组合变体: grip 三次 + FLANK 10° — 在新点 (cubic, 10°) 完成因子设计; "
                           "若加性成立: 259 + Δ(cubic) + Δ(10°); 目标 < 259 步",
                evidence=["F-103", "F-104", "F-106"], parent="2e33751",
                bloodline="2e33751 (grip 三次 + FLANK 10°)",
                source="ROUND 3 加性实证 + ROUND 6-B sweep 证据",
                provenance="lightweight_env.py + simulation_rules.abdl 磁盘实读 (HEAD 2e33751)"))

    elif round_no == 8:
        # ROUND 8 (PM 裁决 2A): FLANK 10°→8° 角度下探 + 优先级语义重算
        #   基线: FLANK 10° + grip 二次 + 动量 1.0 + mapping 40° (mh_rules_007 = 258)
        #   mh_rules_008: FLANK 10°→8° — 平台期外继续下探 (OBS-007: 斜率 -0.17 步/轮)
        #   优先级语义 (磁盘实读 simulation_rules.abdl @ 9107662):
        #     CLOSE-PUSH (p500): BETWEEN(angle, -15, 15), edge<0.65  ← 窗口 = ±15° (PM 前提 ±10° 修正)
        #     FLANK-RIGHT (p480): angle < -8 (现 -10), edge<0.80
        #     FLANK-LEFT  (p470): angle > 8  (现 10),  edge<0.80
        #   重叠带 (8°,15°) 由 p500 单一赢家接管 (resolve_action 单动作语义) → 无行为颠簸
        #   新死区扩展: 角度 (8°,10°) ∩ edge∈[0.65,0.80) 从无规则 → FLANK 接管 (同 ROUND 7 机制)
        #   监控 (PM 裁决 2): 若 252~255 → 角度轴有深度, ROUND 9 向 5° 推进;
        #                     若 >260 → git revert 回滚 10° 并锁定"最佳切角"
        candidates = []
        rules_txt = _read_text(os.path.join(REPO_ROOT, HARNESS_FILES["rules"])) or ""
        has_flank10 = ("sensor(opponent_angle) > 10" in rules_txt
                       and "sensor(opponent_angle) < -10" in rules_txt)
        if has_flank10:
            candidates.append(Variant(
                id="mh_rules_008", layer="rules",
                target_file=HARNESS_FILES["rules"],
                diff=[
                    {"old": "sensor(opponent_angle) < -10",
                     "new": "sensor(opponent_angle) < -8", "expected": 1},
                    {"old": "sensor(opponent_angle) > 10",
                     "new": "sensor(opponent_angle) > 8", "expected": 1},
                ],
                hypothesis="FLANK 10°→8° 纯角度下探 (PM 裁决 2A): 死区扩展到 (8°,10°)∩edge∈[0.65,0.80); "
                           "CLOSE-PUSH 窗 = ±15° (磁盘实读) 非 PM 前提 ±10° — 重叠带 (8°,15°) 由 p500 "
                           "单一赢家接管 → 无行为颠簸; 若 8° 增益收窄则角度轴趋饱和 (OBS-007 斜率 -0.17), "
                           "若 >260 立即回滚锁定 10° 为最佳切角",
                evidence=["F-106"], parent="9107662",
                bloodline="9107662 -> mh_rules_008 (角度轴延续)",
                source="PM 裁决 2A + OBS-007 收敛预测",
                provenance="simulation_rules.abdl 磁盘实读 (HEAD 9107662, FLANK=10°, CLOSE-PUSH=±15°)"))

    elif round_no == 10:
        # ROUND 10 (PM 裁决 2C 排期): 奖励轴首探 — mh_reward_001 证伪测试
        #   基线: 214 (CLOSE-PUSH ±10° + FLANK 10° + grip 二次 + 动量 1.0 + mapping 40°)
        #   预判 (磁盘实读推理): 规则智能体由 ABDL 规则选动作 (非奖励驱动); 终止 (done) 仅由
        #   出界事件决定; env 显式传参 V10Reward(edge_penalty_weight, push_threshold) 遮蔽
        #   reward_functions.py 默认值 → **奖励幅值改动对步数指标为 no-op** → 预期 214 持平。
        #   本候选是**证伪测试**: 若持平 → 用数据关闭"规则引擎奖励轴" (奖励仅对 RL 训练轨道有效);
        #   若意外改变步数 → 发现奖励回馈到终止逻辑的隐藏路径 (重大发现)。
        #   改动: push_threshold 0.2→0.285 (文件头自述 BayesOpt 最优 0.285m — F-106 零新魔数)
        candidates = []
        reward_txt = _read_text(os.path.join(REPO_ROOT, HARNESS_FILES["reward"])) or ""
        has_pt02 = "push_threshold: float = 0.2" in reward_txt
        if has_pt02:
            candidates.append(Variant(
                id="mh_reward_001", layer="reward",
                target_file=HARNESS_FILES["reward"],
                diff=[{"old": "push_threshold: float = 0.2",
                       "new": "push_threshold: float = 0.285", "expected": 1}],
                hypothesis="奖励轴证伪测试 (PM 裁决 2C): push_threshold 0.2→0.285 (文件头自述 "
                           "BayesOpt 最优值)。预判: 规则引擎非奖励驱动 + env 显式传参遮蔽默认值 "
                           "→ 214 持平 (奖励幅值对步数指标解耦)。持平 → 关闭规则引擎奖励轴, "
                           "记录奖励轴仅对 RL 轨道有效; 非持平 → 奖励回馈终止逻辑的隐藏路径",
                evidence=["F-104"], parent="69abd93",
                bloodline="69abd93 -> mh_reward_001 (奖励轴首探, 证伪测试)",
                source="PM 裁决 2C (ROUND 10 排期) + 磁盘实读推理",
                provenance="reward_functions.py 磁盘实读 (HEAD 69abd93, push_threshold=0.2, "
                           "env 显式传参遮蔽默认值)"))

    elif round_no == 14:
        # ROUND 14 (Sprint 35, PM 裁决 T1+T2): Z3 符号验证探针 + 物理 GRIP_DECAY 双向勘探
        #   T1 探针: mh_rules_close_edge_030 (CLOSE-PUSH edge 0.65->0.30 收窄) —
        #       S32 单维投影无新增空洞 (edge 维度被 FLANK 0.80/OF 0.5 覆盖),
        #       但 Z3 联合空间 (opp_found=True, dist<0.6, angle∈(-10,10), edge∈(0.30,0.65))
        #       成空洞 -> 预期 SYMBOLIC_PROOF_FAIL 拦截, 不进评估 (第四层防护验收探针)。
        #   T2: mh_physics_grip_020 / mh_physics_grip_000 (GRIP_DECAY 双向勘探,
        #       动量轴已证伪: ROUND 2 mh_physics_002/003 0.90/0.875 被支配 360/362 步)。
        candidates = []
        # ── T1: Z3 拦截探针 (rules 层, 预期 SYMBOLIC_PROOF_FAIL) ──
        candidates.append(Variant(
            id="mh_rules_close_edge_030", layer="rules",
            target_file=HARNESS_FILES["rules"],
            diff=[{"old": "sensor(edge_proximity) < 0.65",
                   "new": "sensor(edge_proximity) < 0.30", "expected": 1}],
            hypothesis="Z3 符号验证探针 (S35 T1, PM 验收①): CLOSE-PUSH edge 0.65->0.30 "
                       "收窄 — S32 单维投影放行 (edge 维度被 FLANK<0.80/OF<0.5 覆盖), "
                       "但 Z3 联合空间证明存在新增空洞 -> SYMBOLIC_PROOF_FAIL, 不进评估",
            evidence=["F-108"], parent="bd07d5e",
            bloodline="bd07d5e -> mh_rules_close_edge_030 (S35 T1 Z3 拦截探针)",
            source="PM 裁决 T1 (Sprint 35) + symbolic_verify_diff 数学证明"))
        # ── T2: GRIP_DECAY 双向勘探 (physics 层, 未勘探轴) ──
        phys_txt = _read_text(os.path.join(REPO_ROOT, HARNESS_FILES["physics"])) or ""
        if 'GRIP_DECAY = float(os.environ.get("BOTTLE_GRIP_DECAY", "0.10"))' in phys_txt:
            candidates.append(Variant(
                id="mh_physics_grip_020", layer="physics",
                target_file=HARNESS_FILES["physics"],
                diff=[{"old": 'GRIP_DECAY = float(os.environ.get("BOTTLE_GRIP_DECAY", "0.10"))',
                       "new": 'GRIP_DECAY = float(os.environ.get("BOTTLE_GRIP_DECAY", "0.20"))',
                       "expected": 1}],
                hypothesis="物理抓地系数勘探 (S35 T2, PM 裁决②): GRIP_DECAY 0.10->0.20 — "
                           "边缘区轮地抓地衰减翻倍, 机器人近边缘更易打滑 -> 预期规则引擎 "
                           "更早避让边缘, 步数分布变化 (新领域首探, 动量轴 ROUND 2 已证伪)",
                evidence=["F-108"], parent="bd07d5e",
                bloodline="bd07d5e -> mh_physics_grip_020 (S35 T2 GRIP_DECAY 增大)",
                source="PM 裁决 T2 (Sprint 35) + lightweight_env.py 磁盘实读 (GRIP_DECAY=0.10)"))
            candidates.append(Variant(
                id="mh_physics_grip_000", layer="physics",
                target_file=HARNESS_FILES["physics"],
                diff=[{"old": 'GRIP_DECAY = float(os.environ.get("BOTTLE_GRIP_DECAY", "0.10"))',
                       "new": 'GRIP_DECAY = float(os.environ.get("BOTTLE_GRIP_DECAY", "0.0"))',
                       "expected": 1}],
                hypothesis="物理抓地系数勘探 (S35 T2, PM 裁决②): GRIP_DECAY 0.10->0.0 — "
                           "边缘区无抓地损失 (全域 1.0), 对抗极限区推力保持 -> 与 grip_020 "
                           "构成双向包络, 定位抓地-边缘权衡拐点",
                evidence=["F-108"], parent="bd07d5e",
                bloodline="bd07d5e -> mh_physics_grip_000 (S35 T2 GRIP_DECAY 归零)",
                source="PM 裁决 T2 (Sprint 35) + lightweight_env.py 磁盘实读 (GRIP_DECAY=0.10)"))

    elif round_no == 13:
        # ROUND 13 (Sprint 33, PM 裁决 P0): 候选 G CAUTIOUS-EDGE 移除评估
        #   D4-3 冗余分支判定依据 (S31 topo_A 回放: 13→0 消失步数仅 -1)。
        #   三层防护已就绪 (S21 diff_gate + S30 priority 预检 + S32 COVERAGE_GAP),
        #   移除评估副作用可被预检覆盖 (edge 维度 0.55-0.78 被 CLOSE-PUSH/FLANK 覆盖,
        #   无新增空洞 -> 放行)。
        candidates = []
        rules_variants = _gen("rules", defects)
        topo_g = [v for v in rules_variants if v.id == "mh_rules_topo_G"]
        candidates.extend(topo_g[:1])
        # 交叉验证池: topo_A 回放 (S31 冗余证据源) + mapping_001 (S29 REGRESSION 复现)
        topo_legacy = [v for v in rules_variants if v.id == "mh_rules_topo_A"]
        candidates.extend(topo_legacy[:1])
        candidates.extend(_gen("mapping", defects)[:1])

    elif round_no == 12:
        # ROUND 12 (Sprint 31, PM 裁决 P0): 规则拓扑第二波 — FP-NEG-004 branch_hist
        # 修正归因。M2 四通道 (S30) 已就绪, 第四通道 branch_hist 熵可评估拓扑有效性。
        #   拓扑候选 D/E/F 全部进入 (FLANK 收窄 / 边缘让路打断 / FLANK 退出机制),
        #   附带动 mh_rules_topo_A (空洞假设证伪后回放, M2 判定变化) 交叉验证。
        candidates = []
        rules_variants = _gen("rules", defects)
        topo2 = [v for v in rules_variants if v.id in ("mh_rules_topo_D",
                                                       "mh_rules_topo_E",
                                                       "mh_rules_topo_F")]
        topo_legacy = [v for v in rules_variants if v.id == "mh_rules_topo_A"]
        candidates.extend(topo2[:3])
        candidates.extend(topo_legacy[:1])
        # 附带动 mapping 层 S27 遗留交叉验证 (M2 四通道下判定变化)
        candidates.extend(_gen("mapping", defects)[:1])

    elif round_no == 11:
        # ROUND 11 (Sprint 29, PM 裁决 P0): 规则拓扑探索 (解 RULES CLOSED 禁令)
        #   三个拓扑候选 (mh_rules_topo_A/B/C) 全部进入候选池, 由外环 apply/评估/回滚。
        #   拓扑级文本变更 (阈值/前提/优先级), 非参数级 bump — 规避 S24 禁令根因
        #   FP-MC-020 (abs 阈值误用于 0-1 语义参数)。max_per_layer=3 → rules 变体
        #   取前 3 (mh_rules_001/002 + topo_A), 用 --round 11 时专用完整 5 变体。
        candidates = []
        rules_variants = _gen("rules", defects)
        # 拓扑候选优先 (A/B/C), 旧规则变体 (001/002 已实证) 排后
        topo = [v for v in rules_variants if "topo" in v.id]
        legacy = [v for v in rules_variants if "topo" not in v.id]
        candidates.extend(topo[:3])
        candidates.extend(legacy[: max(0, max_per_layer - len(topo))])
        # 附带动 mapping 层 S27 遗留 (flank 0.20→0.15) 交叉验证拓扑-行为联动
        candidates.extend(_gen("mapping", defects)[:1])

    elif round_no >= 2:
        # ROUND 2 (PM 裁决 1): 动量梯度 0.85->0.875/0.90 二分 + Circler 切线接近角
        candidates = _gen("physics", defects)[:2]   # mh_physics_002 (0.90), mh_physics_003 (0.875)
        rules = _gen("rules", defects)               # mh_rules_001 (旧) + mh_rules_002 (Circler)
        circler = [v for v in rules if v.id == "mh_rules_002"]
        candidates.extend(circler[:1])
    else:
        # ROUND 1: 每层 1 个 (规则/映射/物理/动作映射 — Sprint 28 新增 action_map)
        # 动态过滤 HARNESS_FILES 存在性 (S24 动态适配哲学): 测试 fixture
        # 可能 patch 掉部分层, 缺失层跳过不生成候选。
        candidates = []
        for layer in ("rules", "mapping", "physics", "action_map"):
            if layer not in HARNESS_FILES:
                continue
            candidates.extend(_gen(layer, defects)[:max_per_layer])

    lineage_ctx = {
        "pareto_current_best": pareto.get("current_best"),
        "gate_winrate": gate.get("winrate"),
        "gate_passed": gate.get("passed"),
        "defect_library_size": len([k for k in defects if k.startswith("F-1")]),
    }
    for v in candidates:
        v.lineage_ctx = dict(lineage_ctx)

    return candidates


def _self_test() -> int:
    """离线自检: 血缘解析 + 变体生成 (不评估)。"""
    print("== lineage: failure_analysis.md ==")
    defects = load_failure_analysis()
    for k, v in sorted(defects.items()):
        print(f"  {k}: {v}")
    if not defects or "_missing" in defects:
        print("  WARNING: 缺陷库未找到 (文件缺失?)")

    print("== lineage: pareto_frontier.md ==")
    pareto = load_pareto()
    print(f"  current_best = {pareto.get('current_best')}")
    if pareto.get("last_row"):
        print(f"  last_row = {pareto['last_row']}")

    print("== lineage: v9_gate_report.json ==")
    gate = load_last_gate_report()
    print(f"  winrate={gate.get('winrate')} passed={gate.get('passed')} "
          f"file={gate.get('file', gate.get('_missing'))}")

    print("== generate_variants (max 1 per layer) ==")
    variants = generate_variants(max_per_layer=1)
    for v in variants:
        d = v.to_dict()
        print(f"  {d['id']} [{d['layer']}] -> {d['target_file']}")
        print(f"    diff: {d['diff']}")
        print(f"    hypothesis: {d['hypothesis']}")
        print(f"    evidence: {d['evidence']} | bloodline: {d['bloodline']}")
        print(f"    provenance: {d.get('provenance')}")
    assert len(variants) == 4, (
        "expected 4 variants (rules/mapping/physics/action_map); "
        "rules 拓扑层已由 Sprint 29 A1 (PM 裁决 P0) 解禁 RULES CLOSED 禁令, "
        f"不再是 3 层, got {len(variants)}"
    )
    print("SELF-TEST OK")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="BottleSumo Meta-Harness 变体生成器 (P1)")
    ap.add_argument("--json", default=None, help="将变体列表写入 JSON 文件")
    ap.add_argument("--max-per-layer", type=int, default=1)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return _self_test()

    variants = generate_variants(max_per_layer=args.max_per_layer)
    payload = [v.to_dict() for v in variants]
    out = json.dumps(payload, indent=1, ensure_ascii=False)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"variants written -> {args.json}")
    print(out)
    return 0


# ==========================================================================
# 预生成模板区 (PM 裁决 2C / 裁决 1 — 预研但不评估, 不进入评估循环)
# ==========================================================================

# --- ROUND 9 奖励轴候选模板 (PM 裁决 2C: 预生成 1 个, ROUND 9 启用) -------------
# 基于 V9 门奖励结构性调整 (F-104 探针判死已修复, Queue #4)。启用方式: 在
# generate_variants() 的 round_no == 9 分支中实例化并加入 candidates。
REWARD_V9_TEMPLATE = dict(
    id="mh_reward_001",
    layer="reward",
    target_file="simulation/reward_functions.py",
    hypothesis=("奖励轴首探 (PM 裁决 2C): V9 门奖励结构性调整 — 基于 F-104 探针判死修复 "
                "(Queue #4), 强化出界终结权重 (出界即胜/败为最高优先级信号), 弱化时间惩罚 "
                "的线性项; 预期缩短 defensive 僵持局步数"),
    evidence=["F-104"],
    bloodline="9107662 -> mh_reward_001 (预生成, ROUND 9 启用)",
    source="PM 裁决 2C 预生成模板",
    provenance="预生成模板 — 尚未实例化评估, diff 待 ROUND 9 按磁盘实读填写",
)

# --- TASK-005f 视觉预研占位 (PM 裁决 1→ROUND 11: THAW_PENDING → ACTIVE) ----
# EVAI v1.0 (重建版, .aionui/meta_prompts/evai_vision_action_v1.md) 已挂载。
# R-I-C-E 四步法: Recognize (感知张量: edge_proximity/opponent_angle 热区) →
# Interpret (战术上下文, D3 轨迹锚点) → Command (选择 ABDL 动作, 不发明新动作) →
# Execute (帧差验证, 失败写 LIVE_OBS)。
# 视觉管线: lightweight_env 状态 → 合成摄像头帧 → Rerun Web Viewer (localhost:9090)。
# 约束: overlay 只读不写 — 不修改物理/规则层, 不破坏 214 基线。
TASK005F_VISION_PRE_RESEARCH = dict(
    status="ACTIVE",
    trigger="3-2-1 触发器已触发 (3/3: ROUND 8-B P1 8°持平 + ROUND 10 奖励持平 + ROUND 11 规则引擎宣告闭合)",
    meta_prompt=".aionui/meta_prompts/evai_vision_action_v1.md (重建版, EVAI-V1R)",
    method="R-I-C-E 四步法 (Recognize/Interpret/Command/Execute)",
    overlay_hook="outer_loop.py --vision-probe: sim 状态 → 合成摄像头帧 → Rerun :9090 (首帧验证)",
    eval_loop_integration="ALLOWED after --vision-probe dry-run 验证 (ROUND 12+); 仅选择 ABDL 动作, 不修改规则/物理层",
)


if __name__ == "__main__":
    sys.exit(main())

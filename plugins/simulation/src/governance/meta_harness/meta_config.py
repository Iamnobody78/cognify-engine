# -*- coding: utf-8 -*-
"""meta_config.py — P2-V4 自指改进: meta_config 门裁决机制

范围 (PM 强约束): 仅 meta_config 门裁决 — 当编码代理连续 2 轮候选均为无效
(门分数 < 1.0 或步数 >= 基线 214 (持平/更差) 或无可解析候选) 时,
自动调整提议器参数:
  - temperature: 降 0.1 (下限 0.1, 提高结构遵循度)
  - retrieval_threshold: 提高 0.05 (上限 0.90, 检索结果更严格)
  - target_priority: 目标文件优先级切换 (Sprint 16 域: reward -> bridge, physics 已饱和移出)
不修改 outer_loop 主循环结构或 Harness 文件底层逻辑。

裁决历史写入 meta_decisions.jsonl, 供后续迭代参考 (自指改进记忆)。
"""
import json
import os
import time

META_DIR = os.path.dirname(os.path.abspath(__file__))
DECISION_LOG = os.path.join(META_DIR, "meta_decisions.jsonl")

# 默认 meta_config (P1-V3 验收基线, 2026-08-07; Sprint 16 领域切换 2026-08-07)
DEFAULT_META_CONFIG = {
    "temperature": 0.3,           # P1-V3 基线: 0.3 (7b 结构遵循度最优)
    "retrieval_threshold": 0.45,  # 相似度下限: 低于此的检索命中视为不可靠
    "target_priority": ["simulation/reward_functions.py",
                        "core/meta_language/abdl_action_bridge.py"],  # S16: reward+bridge (physics 已饱和)
    "consecutive_invalid": 0,     # 连续无效轮计数
    "adjusted_at": None,          # 最近一次调整 ts
    "adjust_count": 0,            # 累计调整次数
}

# 目标文件优先级轮换表 (切换顺序; Sprint 16 域: reward/bridge, 不含已饱和 physics)
TARGET_PRIORITY_CYCLE = [
    ["simulation/reward_functions.py",
     "core/meta_language/abdl_action_bridge.py"],   # 0: reward + bridge (S16 初始)
    ["simulation/reward_functions.py"],             # 1: 收敛到 reward
    ["core/meta_language/abdl_action_bridge.py"],   # 2: 收敛到 bridge
]

# 步数基线 (规则轨 214 / 视觉轨 418; meta_config 门裁决默认规则轨)
STEPS_BASELINE = 214
SCORE_BASELINE = 1.0


def _now() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def load_meta_config() -> dict:
    """从 meta_decisions.jsonl 尾部恢复当前生效的 meta_config (无则默认)。"""
    cfg = dict(DEFAULT_META_CONFIG)
    if not os.path.exists(DECISION_LOG):
        return cfg
    try:
        with open(DECISION_LOG, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("new_config"):
                    cfg = dict(DEFAULT_META_CONFIG)
                    cfg.update(rec["new_config"])
    except OSError:
        pass
    return cfg


def record_decision(decision: dict):
    """追加裁决记录到 meta_decisions.jsonl。"""
    os.makedirs(os.path.dirname(DECISION_LOG), exist_ok=True)
    with open(DECISION_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(decision, ensure_ascii=False) + "\n")


def is_invalid(result: dict) -> bool:
    """单轮候选是否无效: 无分数 / 分数 < 基线 / 步数 >= 基线 (持平或更差) / 无有效候选。

    Sprint 12 修复 (2026-08-07): steps 判定从 > 基线 改为 >= 基线。
    原因: 物理层已收敛至基线 214 步 — score=1.0/214 (持平) 意味着无帕累托
    改进, 应视为无效以触发 target_priority 轮换 (physics->reward->bridge),
    否则门裁决永不触发 (S12 首轮 5 轮全持平, meta_decisions.jsonl 为空)。
    """
    score = result.get("score")
    if score is None:
        return True
    try:
        score = float(score)
    except (TypeError, ValueError):
        return True
    if score < SCORE_BASELINE:
        return True
    steps = result.get("steps")
    if steps is not None:
        try:
            if int(steps) >= STEPS_BASELINE:
                return True
        except (TypeError, ValueError):
            pass
    return False


def evaluate_round(round_results: list, meta_cfg: dict) -> dict:
    """门裁决: 检查最近 2 轮 (含本轮) 是否连续无效。

    返回裁决记录 (触发时) 或 None (未触发)。
    round_results: 最近轮次的结果列表 (本轮为最后一项),
                   每项为 dict {score, passed, steps} 或 None (无候选)。
    """
    last_two = [r for r in round_results[-2:] if r is not None]
    if len(last_two) < 2:
        return None
    if not all(is_invalid(r) for r in last_two):
        meta_cfg["consecutive_invalid"] = 0
        return None

    # 触发调整: 温度降 0.1 / 检索阈值提 0.05 / 目标文件优先级切换
    new_temp = round(max(0.1, meta_cfg["temperature"] - 0.1), 2)
    new_threshold = round(min(0.90, meta_cfg["retrieval_threshold"] + 0.05), 2)
    cur_pri = meta_cfg.get("target_priority", DEFAULT_META_CONFIG["target_priority"])
    try:
        pri_idx = TARGET_PRIORITY_CYCLE.index(cur_pri)
    except ValueError:
        pri_idx = 0
    new_pri = TARGET_PRIORITY_CYCLE[(pri_idx + 1) % len(TARGET_PRIORITY_CYCLE)]

    decision = {
        "ts": _now(),
        "type": "meta_config_adjust",
        "trigger": "consecutive_2_invalid",
        "rounds": [str(r.get("variant", "?")) for r in last_two if isinstance(r, dict)],
        "scores": [r.get("score") for r in last_two if isinstance(r, dict)],
        "adjustments": {
            "temperature": {"from": meta_cfg["temperature"], "to": new_temp},
            "retrieval_threshold": {"from": meta_cfg["retrieval_threshold"], "to": new_threshold},
            "target_priority": {"from": cur_pri, "to": new_pri},
        },
        "new_config": {
            "temperature": new_temp,
            "retrieval_threshold": new_threshold,
            "target_priority": new_pri,
            "consecutive_invalid": 0,
            "adjusted_at": _now(),
            "adjust_count": meta_cfg.get("adjust_count", 0) + 1,
        },
    }
    meta_cfg.update(decision["new_config"])
    record_decision(decision)
    return decision


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    # 自测: 连续 2 轮无效 -> 触发; 有效 -> 不触发
    cfg = dict(DEFAULT_META_CONFIG)
    d1 = evaluate_round([{"variant": "v1", "score": 0.8, "steps": 214},
                         {"variant": "v2", "score": None, "steps": None}], cfg)
    print("连续2轮无效 -> 触发:", d1 is not None)
    if d1:
        print("  调整:", d1["adjustments"])
        print("  新配置:", cfg["temperature"], cfg["retrieval_threshold"], cfg["target_priority"])
    cfg2 = dict(DEFAULT_META_CONFIG)
    d2 = evaluate_round([{"variant": "v1", "score": 1.0, "steps": 214},
                         {"variant": "v2", "score": 1.0, "steps": 214}], cfg2)
    print("连续2轮有效 -> 不触发:", d2 is None)
    print("  计数复位:", cfg2["consecutive_invalid"])

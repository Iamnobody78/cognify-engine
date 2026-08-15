# -*- coding: utf-8 -*-
"""gap_function.py — MAA-ARCH D2 Gap Function 响应层 (Sprint 15 C2)

Gap Function 原语 (Lanham 2026): delta = R(期望) - O(实际), 根据 delta 选择
响应策略:
  - delta 小 (接近目标)   -> continue          : 继续当前方向
  - delta 中              -> adjust            : 微调参数 (温度/检索阈值)
  - delta 大              -> switch_strategy   : 切换目标文件优先级 / 探索方向
  - delta 过大/不可恢复   -> escalate          : 记录等待人类介入 (V9 裁决门)

与 meta_config.py 的关系: gap_function 是"策略路由器", 将 delta 语义映射到
meta_config 的具体调参动作 (temperature/retrieval_threshold/target_priority),
而非重复实现调参逻辑。

设计原则 (MAA-ARCH 红线):
  - 单轮最多 1 次策略调整, 避免振荡 (adjust_count 护栏)
  - delta 计算基于真实指标: score (质量轴) 与 steps (效率轴)
"""
import json
import os
import time

META_DIR = os.path.dirname(os.path.abspath(__file__))
DECISION_LOG = os.path.join(META_DIR, "meta_decisions.jsonl")

# Gap 阈值 (基于 V9 裁决门 60% 与规则轨基线 214 步)
DELTA_SMALL = 0.03     # score 差 < 0.03 -> continue (接近达标)
DELTA_MED = 0.15       # score 差 < 0.15 -> adjust (微调)
DELTA_LARGE = 0.40     # score 差 < 0.40 -> switch_strategy; >= -> escalate

SCORE_TARGET = 1.0     # R(期望): 规则轨满分
STEPS_BASELINE = 214


def compute_delta(score: float | None, steps: int | None,
                  target_score: float = SCORE_TARGET) -> dict:
    """计算 delta = R(期望) - O(实际), 返回质量/效率两轴偏差。"""
    if score is None:
        return {"score_delta": None, "steps_delta": None,
                "magnitude": DELTA_LARGE + 1.0, "axis": "unknown"}
    score_delta = max(0.0, target_score - float(score))
    steps_delta = None
    if steps is not None:
        steps_delta = max(0, int(steps) - STEPS_BASELINE)
    # 综合量级: 质量差为主轴, 步数反弹放大
    magnitude = score_delta
    if steps_delta and steps_delta > 0:
        magnitude += min(0.15, steps_delta / 1000.0)  # 步数反弹最多放大 0.15
    return {
        "score_delta": round(score_delta, 3),
        "steps_delta": steps_delta,
        "magnitude": round(magnitude, 3),
        "axis": "quality" if score_delta >= 0.05 else "efficiency",
    }


def select_strategy(delta: dict) -> str:
    """根据 delta 选择策略 (MAA-ARCH Phase A: Assess)。"""
    mag = delta["magnitude"]
    if delta["score_delta"] is None:
        return "switch_strategy"   # 无分数 -> 候选生成失败, 切换方向
    if mag < DELTA_SMALL:
        return "continue"
    if mag < DELTA_MED:
        return "adjust"
    if mag < DELTA_LARGE:
        return "switch_strategy"
    return "escalate"


def resolve_action(strategy: str, meta_cfg: dict) -> dict:
    """将策略映射到 meta_config 调参动作 (与 meta_config 调参语义一致)。

    返回 {action, adjustments, new_config} 或 {action: continue} (无调整)。
    """
    if strategy == "continue":
        return {"action": "continue", "adjustments": None, "new_config": None}

    from meta_config import TARGET_PRIORITY_CYCLE

    new_temp = meta_cfg["temperature"]
    new_threshold = meta_cfg["retrieval_threshold"]
    cur_pri = meta_cfg.get("target_priority", TARGET_PRIORITY_CYCLE[0])

    if strategy == "adjust":
        new_temp = round(max(0.1, new_temp - 0.1), 2)
        new_threshold = round(min(0.90, new_threshold + 0.05), 2)
    elif strategy == "switch_strategy":
        # 切换目标文件优先级 (physics -> reward -> bridge)
        try:
            pri_idx = TARGET_PRIORITY_CYCLE.index(cur_pri)
        except ValueError:
            pri_idx = 0
        cur_pri = TARGET_PRIORITY_CYCLE[pri_idx]
        new_pri = TARGET_PRIORITY_CYCLE[(pri_idx + 1) % len(TARGET_PRIORITY_CYCLE)]
        new_temp = round(max(0.1, new_temp - 0.15), 2)  # 更大温度降幅: 提高遵循度
        return {
            "action": "switch_strategy",
            "adjustments": {
                "temperature": {"from": meta_cfg["temperature"], "to": new_temp},
                "target_priority": {"from": cur_pri, "to": new_pri},
            },
            "new_config": {
                **meta_cfg,
                "temperature": new_temp,
                "target_priority": new_pri,
                "consecutive_invalid": 0,
                "adjusted_at": time.strftime("%Y%m%d_%H%M%S"),
                "adjust_count": meta_cfg.get("adjust_count", 0) + 1,
            },
        }

    # adjust 路径返回
    return {
        "action": "adjust",
        "adjustments": {
            "temperature": {"from": meta_cfg["temperature"], "to": new_temp},
            "retrieval_threshold": {"from": meta_cfg["retrieval_threshold"], "to": new_threshold},
        },
        "new_config": {
            **meta_cfg,
            "temperature": new_temp,
            "retrieval_threshold": new_threshold,
            "consecutive_invalid": 0,
            "adjusted_at": time.strftime("%Y%m%d_%H%M%S"),
            "adjust_count": meta_cfg.get("adjust_count", 0) + 1,
        },
    }


def respond(delta: dict, meta_cfg: dict) -> dict:
    """MAA-ARCH Phase R: 完整响应 — 选择策略并执行调参, 记录 decision。

    返回 {trigger, delta, strategy, action, decision_written} 或 None (continue)。
    """
    strategy = select_strategy(delta)
    if strategy == "continue":
        return None
    if strategy == "escalate":
        decision = {
            "ts": time.strftime("%Y%m%d_%H%M%S"),
            "type": "gap_response",
            "trigger": "delta_large",
            "delta": delta,
            "strategy": "escalate",
            "action": "escalate",
            "note": "delta 过大 -> 记录等待 V9 裁决门 / 人类介入",
        }
        _write(decision)
        return decision

    resolved = resolve_action(strategy, meta_cfg)
    decision = {
        "ts": time.strftime("%Y%m%d_%H%M%S"),
        "type": "gap_response",
        "trigger": "gap_function",
        "delta": delta,
        "strategy": strategy,
        "action": resolved["action"],
        "adjustments": resolved["adjustments"],
        "new_config": resolved["new_config"],
    }
    _write(decision)
    if resolved["new_config"]:
        meta_cfg.update(resolved["new_config"])
    return decision


def _write(decision: dict) -> None:
    os.makedirs(os.path.dirname(DECISION_LOG), exist_ok=True)
    with open(DECISION_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(decision, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    from meta_config import DEFAULT_META_CONFIG

    # 自测: 不同 delta 级别的策略选择
    cases = [
        (1.0, 200, "continue"),    # 达标
        (0.97, 205, "adjust"),     # 接近
        (0.85, 240, "switch_strategy"),  # 明显差距
        (0.50, 300, "escalate"),   # 大差距
        (None, None, "switch_strategy"),  # 无分数
    ]
    for score, steps, expect in cases:
        d = compute_delta(score, steps)
        s = select_strategy(d)
        print(f"score={score} steps={steps} -> delta={d['magnitude']} strategy={s} "
              f"(期望 {expect}, {'OK' if s == expect else 'MISMATCH'})")
    # respond 写日志验证
    cfg = dict(DEFAULT_META_CONFIG)
    d = compute_delta(0.85, 240)
    dec = respond(d, cfg)
    print("respond ->", dec["strategy"], dec["action"] if dec else None)

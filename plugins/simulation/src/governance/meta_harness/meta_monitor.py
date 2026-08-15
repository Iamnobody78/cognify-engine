# -*- coding: utf-8 -*-
"""meta_monitor.py — MAA-ARCH 元认知监控层 (Sprint 15 C1)

MAA-ARCH Phase M (Monitor): 每轮迭代结束后检测三种触发器:
  - stagnation       : 连续 N 轮无 Pareto 改进 (score/步数均未超越基线)
  - loop_detected    : 同一变体/同一策略重复出现 (提议器陷入循环)
  - latency_anomaly  : 单轮评估耗时 > 2x 滚动平均 (环境/资源异常)

输出: monitoring_report 追加至 meta_decisions.jsonl (与 meta_config 共用日志),
记录 {ts, round, trigger(s), context, delta, strategy}。

设计原则 (MAA-ARCH 红线):
  - 禁止忽略监控信号: 任何触发器必须记录
  - 禁止过度响应: 单轮最多 1 次策略调整 (由 gap_function 裁决)
  - 与 meta_config 门裁决互补: monitor 检测"广义停滞", meta_config 执行
    "具体调参"; 两者共用 meta_decisions.jsonl 作为自指改进记忆
"""
import json
import os
import statistics
import time

META_DIR = os.path.dirname(os.path.abspath(__file__))
DECISION_LOG = os.path.join(META_DIR, "meta_decisions.jsonl")

# 触发器默认阈值 (MAA-ARCH D1 元认知监控)
DEFAULTS = {
    "stagnation_rounds": 3,        # 连续 3 轮无改进 -> stagnation
    "loop_repeat": 2,              # 同一变体 id 出现 >= 2 次 -> loop_detected
    "latency_multiplier": 2.0,     # 耗时 > 2x 滚动平均 -> latency_anomaly
    "min_latency_samples": 3,      # 至少 3 个样本才计算滚动平均
}


class MetaMonitor:
    """MAA-ARCH Phase M 监控器: 检测触发器并写 monitoring_report。"""

    def __init__(self, thresholds: dict | None = None, log_path: str = DECISION_LOG):
        self.t = {**DEFAULTS, **(thresholds or {})}
        self.log_path = log_path
        self.round_history: list[dict] = []   # 每轮 {round, variant, score, steps, wall_s, kept}
        self.trigger_counts = {"stagnation": 0, "loop_detected": 0, "latency_anomaly": 0}

    # ---- 状态记录 -----------------------------------------------------
    def record_round(self, round_no: int, variant_id: str | None,
                     score: float | None, steps: int | None,
                     wall_s: float | None, kept: bool) -> None:
        """记录一轮评估结果 (供触发器判定)。"""
        self.round_history.append({
            "round": round_no,
            "variant": variant_id,
            "score": score,
            "steps": steps,
            "wall_s": wall_s,
            "kept": kept,
        })

    # ---- 触发器检测 ---------------------------------------------------
    def _detect_stagnation(self, round_no: int) -> dict | None:
        """stagnation: 连续 N 轮 kept=False (无 Pareto 改进)。"""
        recent = [r for r in self.round_history if r["round"] <= round_no]
        recent = recent[-self.t["stagnation_rounds"]:]
        if len(recent) < self.t["stagnation_rounds"]:
            return None
        if all(not r["kept"] for r in recent):
            scores = [r["score"] for r in recent if r["score"] is not None]
            return {
                "trigger": "stagnation",
                "rounds": [r["round"] for r in recent],
                "variants": [r["variant"] for r in recent],
                "scores": scores,
                "window": self.t["stagnation_rounds"],
            }
        return None

    def _detect_loop(self, round_no: int) -> dict | None:
        """loop_detected: 同一变体 id 在最近窗口内重复 >= loop_repeat 次。"""
        recent = [r for r in self.round_history if r["round"] <= round_no]
        recent = recent[-self.t["stagnation_rounds"]:]
        counts: dict[str, int] = {}
        for r in recent:
            if r["variant"]:
                counts[r["variant"]] = counts.get(r["variant"], 0) + 1
        for vid, n in counts.items():
            if n >= self.t["loop_repeat"]:
                return {
                    "trigger": "loop_detected",
                    "variant": vid,
                    "repeat": n,
                    "rounds": [r["round"] for r in recent if r["variant"] == vid],
                }
        return None

    def _detect_latency(self, round_no: int, wall_s: float | None) -> dict | None:
        """latency_anomaly: wall_s > 2x 滚动平均 (至少 min_latency_samples 样本)。"""
        if wall_s is None:
            return None
        prior = [r["wall_s"] for r in self.round_history
                 if r["round"] < round_no and r["wall_s"] is not None]
        if len(prior) < self.t["min_latency_samples"]:
            return None
        avg = statistics.mean(prior)
        if wall_s > self.t["latency_multiplier"] * avg:
            return {
                "trigger": "latency_anomaly",
                "wall_s": round(wall_s, 1),
                "avg_wall_s": round(avg, 1),
                "multiplier": round(wall_s / avg, 2) if avg else None,
            }
        return None

    # ---- 分析入口 -----------------------------------------------------
    def analyze_iteration(self, round_no: int, variant_id: str | None,
                          score: float | None, steps: int | None,
                          wall_s: float | None, kept: bool) -> list[dict]:
        """每轮迭代末尾调用: 记录本轮 + 检测触发器 + 写 monitoring_report。

        返回触发的触发器列表 (空 = 无触发器)。
        """
        self.record_round(round_no, variant_id, score, steps, wall_s, kept)

        triggers: list[dict] = []
        # 显式调用三检测器 (避免绑定方法比较歧义)
        hit = self._detect_stagnation(round_no)
        if hit:
            triggers.append(hit)
            self.trigger_counts[hit["trigger"]] += 1
        hit = self._detect_loop(round_no)
        if hit:
            triggers.append(hit)
            self.trigger_counts[hit["trigger"]] += 1
        hit = self._detect_latency(round_no, wall_s)
        if hit:
            triggers.append(hit)
            self.trigger_counts[hit["trigger"]] += 1

        if triggers:
            report = {
                "ts": time.strftime("%Y%m%d_%H%M%S"),
                "type": "monitoring_report",
                "round": round_no,
                "variant": variant_id,
                "triggers": triggers,
                "trigger_counts": dict(self.trigger_counts),
            }
            self._write(report)
        return triggers

    def _write(self, report: dict) -> None:
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(report, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    # 自测: 3 轮无改进 -> stagnation; 同变体重复 -> loop; 耗时异常 -> latency
    m = MetaMonitor()
    for rnd in range(1, 6):
        # 第 1-3 轮全失败; 第 4 轮同变体重复; 第 5 轮耗时 5x
        wall = 10.0 if rnd < 5 else 60.0
        trigs = m.analyze_iteration(
            round_no=rnd,
            variant_id="mh_probe_01" if rnd >= 4 else f"mh_fail_{rnd}",
            score=0.8 if rnd < 4 else 1.0,
            steps=240 if rnd < 4 else 200,
            wall_s=wall,
            kept=(rnd >= 5),
        )
        print(f"round {rnd}: triggers={[t['trigger'] for t in trigs]}")
    print("trigger_counts:", m.trigger_counts)

# -*- coding: utf-8 -*-
"""cell_learner.py — FSCL-ARCH Phase L (Learn & Evolve) 学习闭环 (Sprint 15 C3)

C3 职责:
  1. 连续 3 轮无改进 (stagnation) 时触发学习
  2. 将失败模式沉淀至 engineering_rules.md (SEFS-ARCH 已定义规则库)
  3. 根据 monitoring_report 自适应 outer_loop 参数 (检索阈值/温度上下界)

与 meta_config / gap_function 的分工:
  - meta_config  : 连续 2 轮无效 -> 调参 (既有, P2-V4)
  - gap_function : delta -> 策略路由 (C2, 实时响应)
  - cell_learner : stagnation -> 规则沉淀 + 参数上下界自适应 (C3, 周期性学习)

规则沉淀格式 (追加制, 永不删除, 仅标记 OBSOLETE):
  | RULE-MC-<n> | <规则> | <来源> |
"""
import copy
import json
import os
import time

META_DIR = os.path.dirname(os.path.abspath(__file__))
DECISION_LOG = os.path.join(META_DIR, "meta_decisions.jsonl")
# 元认知规则库 (MAA-ARCH/FSCL-ARCH 专属), 与 dashboard 工程规则库分离
RULES_FILE = os.path.join(META_DIR, "meta_engineering_rules.md")

# 参数自适应上下界 (温度/检索阈值, 供 outer_loop 提议器使用)
PARAM_BOUNDS = {
    "temperature": {"min": 0.1, "max": 0.7, "step": 0.05},
    "retrieval_threshold": {"min": 0.30, "max": 0.90, "step": 0.05},
}

# 已知失败模式 -> 规则模板 (从 failure_analysis 提炼)
FAILURE_TEMPLATES = {
    "stagnation": "探索停滞: 连续 {window} 轮无 Pareto 改进, 应切换目标文件优先级 "
                  "或扩大检索范围, 而非重复同层候选",
    "loop_detected": "提议器循环: 变体 {variant} 在 {rounds} 轮内重复 {repeat} 次, "
                     "需注入多样性 (温度扰动或换层)",
    "latency_anomaly": "评估延迟异常: 单轮耗时 {wall_s}s > {multiplier}x 滚动平均, "
                       "检查环境负载/资源水位后再继续迭代",
}


class CellLearner:
    """FSCL-ARCH Phase L: 从失败模式学习并沉淀规则。"""

    def __init__(self, log_path: str = DECISION_LOG, rules_file: str = RULES_FILE):
        self.log_path = log_path
        self.rules_file = rules_file
        self.learned_rules: list[str] = []

    def learn_from_triggers(self, triggers: list[dict]) -> list[str]:
        """根据监控触发器沉淀规则, 返回新增规则 id 列表 (按模板文本去重)。"""
        new_rules = []
        existing_texts = self._existing_rule_texts()
        next_id = self._next_rule_id()  # 一次性确定起始编号, 批次内递增
        for t in triggers:
            rule = self._template_rule(t, next_id)
            if not rule:
                continue
            # 去重: 同一模板文本不重复沉淀 (RULE-MC 编号递增)
            text = rule.split(" | ", 2)[1]
            if text in existing_texts:
                continue
            new_rules.append(rule)
            self.learned_rules.append(rule)
            next_id += 1
        if new_rules:
            self._append_rules(new_rules, source="cell_learner")
            self._record_learning(new_rules)
        return new_rules

    def _existing_rule_texts(self) -> set:
        """读取规则库已存在的规则文本 (去重用)。"""
        texts = set()
        if not os.path.exists(self.rules_file):
            return texts
        with open(self.rules_file, encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(" | ")
                if len(parts) >= 3:
                    texts.add(parts[1])
        return texts

    def _template_rule(self, trigger: dict, rule_id: int) -> str | None:
        kind = trigger.get("trigger")
        if kind not in FAILURE_TEMPLATES:
            return None
        text = FAILURE_TEMPLATES[kind].format(**trigger)
        return f"| RULE-MC-{rule_id:03d} | {text} | cell_learner {time.strftime('%Y-%m-%d')} |"

    def _next_rule_id(self) -> int:
        """基于现有规则库的最大 RULE-MC 编号 + 1 (跨运行连续编号)。"""
        max_id = 0
        if os.path.exists(self.rules_file):
            with open(self.rules_file, encoding="utf-8") as f:
                for line in f:
                    import re

                    m = re.search(r"RULE-MC-(\d+)", line)
                    if m:
                        max_id = max(max_id, int(m.group(1)))
        return max_id + 1

    def _append_rules(self, rules: list[str], source: str) -> None:
        os.makedirs(os.path.dirname(self.rules_file), exist_ok=True)
        with open(self.rules_file, "a", encoding="utf-8") as f:
            f.write("\n")
            for r in rules:
                f.write(r + "\n")
        print(f"[cell_learner] {source}: 追加 {len(rules)} 条规则 -> {self.rules_file}")

    def _record_learning(self, rules: list[str]) -> None:
        rec = {
            "ts": time.strftime("%Y%m%d_%H%M%S"),
            "type": "cell_learning",
            "rules_added": len(rules),
            "rules": rules,
        }
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def adapt_params(self, meta_cfg: dict, triggers: list[dict]) -> dict:
        """根据触发器自适应参数上下界 (写入 meta_config 的 bounds 字段)。

        注意: 必须深拷贝 PARAM_BOUNDS, 否则会污染全局配置 (嵌套 dict 共享引用)。
        """
        bounds = copy.deepcopy(PARAM_BOUNDS)
        for t in triggers:
            if t.get("trigger") == "stagnation":
                # 停滞: 扩大温度上界 (更多多样性) + 降低检索阈值下界
                bounds["temperature"]["max"] = round(min(
                    0.9, bounds["temperature"]["max"] + 0.1), 2)
                bounds["retrieval_threshold"]["min"] = round(max(
                    0.1, bounds["retrieval_threshold"]["min"] - 0.05), 2)
            elif t.get("trigger") == "loop_detected":
                # 循环: 收紧温度范围 (提高遵循度) + 提高检索阈值 (更严格)
                bounds["temperature"]["max"] = round(max(
                    bounds["temperature"]["min"],
                    bounds["temperature"]["max"] - 0.1), 2)
                bounds["retrieval_threshold"]["min"] = round(min(
                    0.9, bounds["retrieval_threshold"]["min"] + 0.05), 2)
        if bounds != PARAM_BOUNDS:
            meta_cfg["param_bounds"] = bounds
            self._record_bounds(bounds, [t.get("trigger") for t in triggers])
        return bounds

    def _record_bounds(self, bounds: dict, triggers: list) -> None:
        rec = {
            "ts": time.strftime("%Y%m%d_%H%M%S"),
            "type": "param_bounds_update",
            "triggers": triggers,
            "bounds": bounds,
        }
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    from meta_config import DEFAULT_META_CONFIG

    # 自测: 3 个触发器 -> 规则沉淀 + 参数自适应
    learner = CellLearner()
    triggers = [
        {"trigger": "stagnation", "window": 3, "rounds": [1, 2, 3],
         "variants": ["a", "b", "c"], "scores": [0.8, 0.8, 0.8]},
        {"trigger": "loop_detected", "variant": "mh_probe_01", "repeat": 2,
         "rounds": [3, 4]},
        {"trigger": "latency_anomaly", "wall_s": 60.0, "avg_wall_s": 12.0,
         "multiplier": 5.0},
    ]
    new = learner.learn_from_triggers(triggers)
    print("新增规则:", len(new))
    for r in new:
        print(" ", r)

    cfg = dict(DEFAULT_META_CONFIG)
    bounds = learner.adapt_params(cfg, triggers)
    print("自适应 bounds:", json.dumps(bounds, ensure_ascii=False))
    print("meta_cfg.param_bounds:", cfg.get("param_bounds") is not None)

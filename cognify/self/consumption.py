#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
consumption.py — 闭环运行时化 (批判 2.3)
========================================
产出→消费者审计: 各引擎真实读取产出时写审计日志, 按日统计真实消费率。
静态 CLOSURES 映射表降级为 fallback。

用法: import consumption; consumption.log_consumption(producer, consumer, artifact)
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

TRI = Path(os.environ.get("COGNIFY_TRI", r"C:\Users\ivy\.aionui-tri-sync"))
LOG = TRI / "closure/consumption_log.jsonl"

# 期望消费配对 (静态映射, fallback 用; 真实消费率以审计日志为准)
EXPECTED = [
    ("learning/ledger", "meta_call"),
    ("meta-call/certification_report", "evolve"),
    ("meta/status", "generate-status"),
    ("debt/debt_inventory", "generate-status"),
    ("meta/status", "meta_smoke"),
    ("meta-call/certification_report", "meta_smoke"),
    ("benchmark/trend_data", "generate-status"),
    ("learning/ledger", "meta_smoke"),
]


def log_consumption(producer: str, consumer: str, artifact: str) -> None:
    """产出消费审计: producer 的 artifact 被 consumer 读取。"""
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"),
                                 "day": datetime.now().strftime("%Y-%m-%d"),
                                 "producer": producer, "consumer": consumer,
                                 "artifact": artifact}, ensure_ascii=False) + "\n")
    except Exception:
        pass


def runtime_closure_rate() -> dict:
    """按日统计真实消费率: 今日实际消费配对 / 期望配对。"""
    today = datetime.now().strftime("%Y-%m-%d")
    seen = set()
    if LOG.exists():
        for line in LOG.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                e = json.loads(line)
                if e.get("day") == today:
                    seen.add((e.get("producer"), e.get("consumer")))
            except Exception:
                continue
    matched = sum(1 for p, c in EXPECTED if (p, c) in seen)
    rate = round(matched / len(EXPECTED), 3) if EXPECTED else 0.0
    return {"day": today, "consumed": matched, "expected": len(EXPECTED),
            "runtime_rate": rate, "consumed_pairs": sorted(seen),
            "missing": [(p, c) for p, c in EXPECTED if (p, c) not in seen]}

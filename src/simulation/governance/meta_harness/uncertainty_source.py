# -*- coding: utf-8 -*-
"""uncertainty_source.py — 元认知-不确定性来源识别 形式化 (RULE-MC-014).

背景: SELF-EVOLVE D1(可靠性) 要求"输出不确定时必须标注来源, 不得静默继续"。
本模块将不确定性来源识别固化为三通道分类 + 可复用标注机制, 闭合
meta_capability_scorecard.md 中"元认知-不确定性来源识别未形式化"缺口。

三通道 (与框架自评一致):
  - DATA_INSUFFICIENT  数据不足   (输入稀疏/缺失/样本不足)
  - MODEL_LIMITATION   模型局限   (超出能力边界/知识截止/幻觉风险)
  - TOOL_UNAVAILABLE   工具不可用 (依赖工具缺失/调用失败/权限拒绝)

用法:
  from uncertainty_source import classify_uncertainty, annotate_uncertainty
  r = classify_uncertainty(data_sparse=True, model_limited=False, tool_failed=False)
  # r == {"uncertain": True, "sources": ["DATA_INSUFFICIENT"], ...}
  annotate_uncertainty(context="NCLT 27-session 回测缺 01-15 数据", sources=r["sources"])
"""
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
UNCERTAINTY_LOG = os.path.join(HERE, "uncertainty_annotations.jsonl")

# 三通道不确定性来源 (可扩展: 新增通道需同步 RULE-MC-014 表格)
UNCERTAINTY_CHANNELS = {
    "DATA_INSUFFICIENT": "数据不足 (输入稀疏/缺失/样本不足)",
    "MODEL_LIMITATION": "模型局限 (超出能力边界/知识截止/幻觉风险)",
    "TOOL_UNAVAILABLE": "工具不可用 (依赖工具缺失/调用失败/权限拒绝)",
}

# 诚实边界: 只有命中的通道才计入; 不伪造"不确定"标签
def classify_uncertainty(*, data_sparse=False, model_limited=False, tool_failed=False):
    """三通道不确定性来源识别.

    至少一个通道命中 -> uncertain=True (应标注来源);
    全不命中 -> uncertain=False (可判定为确定, 但需谨慎——未命中不等于无不确定性).

    Returns:
        dict: {"uncertain": bool, "sources": [channel_keys],
               "labels": [中文标签]}
    """
    sources = []
    if data_sparse:
        sources.append("DATA_INSUFFICIENT")
    if model_limited:
        sources.append("MODEL_LIMITATION")
    if tool_failed:
        sources.append("TOOL_UNAVAILABLE")
    return {
        "uncertain": bool(sources),
        "sources": sources,
        "labels": [UNCERTAINTY_CHANNELS[s] for s in sources],
    }


def annotate_uncertainty(context="", sources=None):
    """将一次不确定性标注写入日志 (可复用, 供 meta_monitor 统计).

    Args:
        context: 上下文描述 (如 "NCLT 27-session 回测缺 01-15 数据")
        sources: classify_uncertainty 返回的 sources 列表
    Returns:
        dict: 写入的记录 (含 ts)
    """
    sources = sources or []
    rec = {
        "ts": time.strftime("%Y%m%d_%H%M%S"),
        "context": context,
        "sources": sources,
        "n_channels": len(sources),
    }
    with open(UNCERTAINTY_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def uncertainty_summary():
    """聚合不确定性标注: 各通道命中次数 (供 scorecard 证据)."""
    if not os.path.exists(UNCERTAINTY_LOG):
        return {"total": 0, "channels": {}}
    counts = {k: 0 for k in UNCERTAINTY_CHANNELS}
    total = 0
    with open(UNCERTAINTY_LOG, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            total += 1
            for s in rec.get("sources", []):
                if s in counts:
                    counts[s] += 1
    return {"total": total, "channels": counts}


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    demo = classify_uncertainty(data_sparse=True, model_limited=True, tool_failed=False)
    print("classify_uncertainty demo:", json.dumps(demo, ensure_ascii=False))
    print("summary:", json.dumps(uncertainty_summary(), ensure_ascii=False))

# -*- coding: utf-8 -*-
"""
MEF-OS v1.0 — 元教育认知工厂闭环流水线 (MCE -> VCE -> CEE -> TRACE)

阶段:
  MCE 2.0: 输入编译为 AST (Core_Directive / Entities / Structural_Constraints / Tension_Vectors / Entropy_Score)
  VCE 2.0: 价值扫描 (Polarization_Index / Value_Tensions / Asymmetric_Perspectives)
  CEE:     三阶段推演 (生存 -> 沉淀 -> 释放)
  TRACE:   归档到 governance/meta_evolution/ + .aionui/metacognition/thoughts/

用法:
  python meta_edu.py --url <URL> --tag <TAG>     # 对链接执行元教育闭环
  python meta_edu.py --task "<任务描述>" --tag <TAG>  # 对任务执行元教育闭环
"""
import argparse
import io
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TRACE_DIR = os.path.join(REPO_ROOT, "governance", "trace")
META_EVOL = os.path.join(REPO_ROOT, "governance", "meta_evolution")
THOUGHTS = os.path.join(REPO_ROOT, ".aionui", "metacognition", "thoughts")

# VCE 价值扫描词典 (极化/冲突标记)
POLARITY_TERMS = {
    "high_polarity": ["绝对", "永远", "彻底", "必须", "禁止", "唯一", "全部", "always", "never",
                      "completely", "undeniably", "the only"],
    "value_tension": ["vs", "versus", "冲突", "矛盾", "tradeoff", "代价", "平衡", "但", "然而"],
    "asymmetry": ["只考虑", "忽略", "偏袒", "片面", "one-sided", "ignoring", "overlook"],
}


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fetch(url, timeout=20):
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read().decode("utf-8", errors="replace")
        cjk = len(re.findall(r"[\u4e00-\u9fff]", data))
        if cjk > 200:
            # 粗提取正文文本
            text = re.sub(r"<script[^>]*>.*?</script>", " ", data, flags=re.S)
            text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.S)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text)
            return {"ok": True, "text": text[:6000], "note": "direct_fetch"}
        return {"ok": False, "text": "", "note": "JS shell (cjk=%d)" % cjk}
    except Exception as e:
        return {"ok": False, "text": "", "note": "fetch error: %s" % e}


def mce_compile(raw_text):
    """MCE 2.0: 输入 -> AST。"""
    entities = []
    for m in re.finditer(r"([A-Z][A-Z0-9-]{2,}|[A-Za-z_]{4,})", raw_text):
        token = m.group(1)
        if token.upper() not in (e.upper() for e in entities):
            entities.append(token)
    entities = entities[:12]
    entropy = min(0.9, max(0.1, len(set(entities)) / 24.0 + 0.1))
    return {
        "Core_Directive": raw_text.strip()[:200] if len(raw_text.strip()) <= 200
                          else raw_text.strip()[:150] + "...",
        "Entities": entities,
        "Structural_Constraints": [
            "数据边界: 链接无法程序化抓取时以用户消息为内容源",
            "递归边界: L0 锚点不可触碰, 递归 <=3 层",
        ],
        "Tension_Vectors": [],
        "Entropy_Score": round(entropy, 3),
    }


def vce_scan(ast, raw_text):
    """VCE 2.0: 极化系数 / 价值张力 / 不对称视角。"""
    pol = 0.0
    tensions = []
    asym = []
    lower = raw_text.lower()
    for kw in POLARITY_TERMS["high_polarity"]:
        if kw in lower:
            pol += 0.12
    for kw in POLARITY_TERMS["value_tension"]:
        if kw in lower:
            tensions.append(kw)
    for kw in POLARITY_TERMS["asymmetry"]:
        if kw in lower:
            asym.append(kw)
    return {
        "Polarization_Index": round(min(1.0, pol), 3),
        "Value_Tensions": tensions[:6],
        "Asymmetric_Perspectives": asym[:4],
    }


def cee_plan(ast, vce):
    """CEE: 生存 -> 沉淀 -> 释放 三阶段。"""
    pol = vce["Polarization_Index"]
    return {
        "survival": {"action": "最小可行行动: 编译内容 -> 写入知识库",
                     "trigger": "内容源可用或用户已提供摘要"},
        "precipitation": {"action": "加固: 交叉验证 + 纳入 engineering_rules",
                          "condition": "polarization < 0.7 或已通过看门狗闸门"},
        "release": {"action": "释放: 固化为可检索知识并接入决策检索",
                    "horizon": "下一个 Sprint"},
        "gate_note": "高极化(>0.7)时先执行 VCE 价值审计再进入沉淀" if pol > 0.7 else "极化度正常, 可进入沉淀",
    }


def trace_archive(loop, tag):
    """TRACE: 归档到 meta_evolution + thoughts。"""
    os.makedirs(META_EVOL, exist_ok=True)
    os.makedirs(THOUGHTS, exist_ok=True)
    trace_file = os.path.join(META_EVOL, "meta_edu_trace.jsonl")
    with io.open(trace_file, "a", encoding="utf-8") as f:
        f.write(json.dumps({"type": "meta_edu_loop", "ts": now_iso(), "tag": tag, **loop},
                           ensure_ascii=False) + "\n")
    thoughts_file = os.path.join(THOUGHTS, "%s_MEF_trace.md" % now_iso().replace(":", "-")[:16])
    with io.open(thoughts_file, "w", encoding="utf-8") as f:
        f.write("# MEF-OS 元教育闭环 trace\n\n- tag: %s\n- ts: %s\n\n" % (tag, now_iso()))
        f.write("## MCE 编译\n\n%s\n\n## VCE 扫描\n\n%s\n\n## CEE 推演\n\n%s\n"
                % (json.dumps(loop["mce"], ensure_ascii=False, indent=2),
                   json.dumps(loop["vce"], ensure_ascii=False, indent=2),
                   json.dumps(loop["cee"], ensure_ascii=False, indent=2)))
    return trace_file, thoughts_file


def run_loop(url, tag):
    """MEF-OS 闭环入口。"""
    if url:
        fetch = _fetch(url)
        if fetch["ok"]:
            raw_text = fetch["text"]
            source = {"url": url, "note": fetch["note"]}
        else:
            # 诚实回退: 无法抓取时记录边界, 空文本走编译框架
            raw_text = ""
            source = {"url": url, "note": fetch["note"], "data_boundary": "not_fetchable"}
    else:
        raw_text = tag or ""
        source = {"task": tag}

    mce = mce_compile(raw_text)
    vce = vce_scan(mce, raw_text)
    cee = cee_plan(mce, vce)
    loop = {"source": source, "mce": mce, "vce": vce, "cee": cee}
    trace_file, thoughts_file = trace_archive(loop, tag or "MEF")
    print(json.dumps({"source": source, "MCE": mce, "VCE": vce, "CEE": cee,
                      "trace_file": trace_file, "thoughts_file": thoughts_file},
                     ensure_ascii=False, indent=2))
    return 0


def main():
    ap = argparse.ArgumentParser(description="MEF-OS v1.0 元教育闭环")
    ap.add_argument("--url", default=None)
    ap.add_argument("--task", default=None)
    ap.add_argument("--tag", default="MEF")
    args = ap.parse_args()
    return run_loop(args.url or args.task, args.tag)


if __name__ == "__main__":
    sys.exit(main())

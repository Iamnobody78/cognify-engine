"""S62 R1-A1: 协议表 → YAML 规范编译器.

来自 Notion 人機協作協議頁 (N1): 11 列协议表 schema 编译为声明式 YAML 规范.
每个协议模块生成独立 YAML, 含全部 11 列字段, 供治理规则声明式引用.

11 列: 协议模組 / 分類 / 層級 / 核心目的 / 元認知提問 / 人機協作指令 /
        觸發情境 / 自我檢核·倫理邊界 / 來源對應 / 操作頻率 / 實作策略 /
        預期產出·判斷指標   (注: 页面为 11 列 + 模块名 = 12 字段实际)

Run: python3 governance/protocols/protocol_compiler.py [--input input.json] [--output-dir schema/]
"""
import argparse
import json
import os
import sys

try:
    import yaml
except ImportError:
    yaml = None

# 必需字段 (来自 N1 页面 11 列)
REQUIRED_FIELDS = [
    "module",            # 协议模組
    "category",          # 分類
    "level",             # 層級
    "core_purpose",      # 核心目的
    "metacognitive_q",   # 元認知提問
    "collab_directive",  # 人機協作指令
    "trigger",           # 觸發情境
    "ethics_boundary",   # 自我檢核·倫理邊界
    "source",            # 來源對應
    "frequency",         # 操作頻率
    "strategy",          # 實作策略
    "expected_output",   # 預期產出·判斷指標
]


def compile_protocols(records: list, output_dir: str) -> dict:
    """Compile list of protocol records (dicts) into per-module YAML files.

    Returns {module: filepath} mapping. Validates all REQUIRED_FIELDS present.
    """
    os.makedirs(output_dir, exist_ok=True)
    written = {}
    for i, rec in enumerate(records):
        missing = [f for f in REQUIRED_FIELDS if f not in rec]
        if missing:
            raise ValueError(f"record #{i} missing required fields: {missing}")
        module = rec["module"]
        safe = "".join(c for c in module if c.isalnum() or c in "_-") or f"protocol_{i}"
        fpath = os.path.join(output_dir, f"{safe}.yaml")
        doc = {
            "schema_version": "11-col-v1",
            "source": rec.get("source", "notion:N1"),
            "protocol": rec,
        }
        with open(fpath, "w", encoding="utf-8") as f:
            if yaml is not None:
                yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False)
            else:
                f.write(json.dumps(doc, ensure_ascii=False, indent=2))
        written[module] = fpath
    return written


def verify_yaml(fpath: str) -> bool:
    """Verify a compiled YAML parses and has all required fields."""
    if yaml is None:
        return os.path.exists(fpath)
    with open(fpath, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    proto = doc.get("protocol", {})
    return all(k in proto for k in REQUIRED_FIELDS)


def demo_records():
    """Demo protocol records extracted from N1 page summary."""
    return [
        {
            "module": "feynman_test",
            "category": "自我檢核",
            "level": "L2",
            "core_purpose": "验证理解深度 — 能否用费曼方式解释协议",
            "metacognitive_q": "我能向新手解释这个协议吗？",
            "collab_directive": "请用费曼测试检查我对该协议的理解",
            "trigger": "每次新协议入库时",
            "ethics_boundary": "不用于误导性简化",
            "source": "notion:N1 (人機協作協議)",
            "frequency": "每次入库",
            "strategy": "AI 自动审核 + 费曼问答对",
            "expected_output": "理解深度评分 ≥ 80%",
        },
        {
            "module": "entropy_denoise",
            "category": "熵值去噪",
            "level": "L3",
            "core_purpose": "从噪声输入中提取有效信号",
            "metacognitive_q": "这条信息的信噪比是多少？",
            "collab_directive": "请去噪后重述核心意图",
            "trigger": "输入信息熵 > 阈值时",
            "ethics_boundary": "不曲解原始意图",
            "source": "notion:N1 (人機協作協議)",
            "frequency": "按需",
            "strategy": "熵值计算 + 结构化重述",
            "expected_output": "去噪后的要点列表",
        },
        {
            "module": "logic_chain_check",
            "category": "逻辑链检查",
            "level": "L2",
            "core_purpose": "验证推理链完整性",
            "metacognitive_q": "结论的前提是否都成立？",
            "collab_directive": "请逐环检查我的推理链",
            "trigger": "关键决策前",
            "ethics_boundary": "不攻击人格只检查逻辑",
            "source": "notion:N1 (人機協作協議)",
            "frequency": "关键决策时",
            "strategy": "前提-推理-结论三段检查",
            "expected_output": "逻辑链完整性报告",
        },
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=None, help="JSON list of protocol records")
    ap.add_argument("--output-dir", default=None,
                    help="output dir for YAML schema files")
    args = ap.parse_args()

    if args.input:
        with open(args.input, "r", encoding="utf-8") as f:
            records = json.load(f)
    else:
        records = demo_records()
        print("[A1] using demo records (3 protocols from N1 page)")

    out_dir = args.output_dir or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "schema")
    written = compile_protocols(records, out_dir)
    ok = all(verify_yaml(p) for p in written.values())
    print(f"[A1] compiled {len(written)} protocols -> {out_dir}")
    for m, p in written.items():
        print(f"      {m}: {p} verified={verify_yaml(p)}")
    print(f"[A1] all verified: {ok}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

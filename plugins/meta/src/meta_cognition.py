#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
META-COGNITION v1.0 — 不确定性来源识别模块 (解耦自 honesty_guard)
=================================================================
META-BOOTSTRAP 五维中"元认知"的形式化组件 (得分 3.0 → 目标 4.0)。

对任意声明/断言输出结构化不确定性评估:
  - source: verified(已验证) | data_insufficient(数据不足) | model_limit(模型局限)
            | tool_unavailable(工具不可用) | external_unknown(外部未知)
  - confidence: 0.0-1.0
  - evidence: 判定依据 (文件/端口/注册表)
  - action: 建议动作 (继续输出/标注不确定/降级计划中/拒绝)

用法:
  python meta_cognition.py assess "治理网关已通过 AST 测试"
  python meta_cognition.py audit <reports_dir>   # 批量审计自有报告中的声明
"""
import json
import re
import socket
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# 路径中心化 (2026-08-15): 从 trisync_paths 读取, 不再硬编码
sys.path.insert(0, str(Path(__file__).parent))
from trisync_paths import WS, TRI, HOME  # noqa: E402

# 声明模式: 强声称 (已/通过/完成) 与弱声称 (可能/大概/预计)
STRONG_RE = re.compile(r"(?:已|通过了?|完成|落地|部署|实现|验证|PASS|通过)")
WEAK_RE = re.compile(r"(?:可能|大概|预计|估计|也许|计划|建议|待|TODO|候选)")

# 本地可验证能力 (与 honesty_guard 注册表同源, 但独立维护以免耦合)
VERIFIABLE = {
    "三方同步守护": ("file", TRI / "daemon/sync_daemon.py"),
    "状态检查": ("file", TRI / "daemon/sync_status.py"),
    "看门狗": ("file", TRI / "daemon/watchdog.py"),
    "继承": ("file", TRI / "daemon/inherit.py"),
    "元提示词系统": ("file", HOME / ".aionui/meta_prompts/.system/meta_system.py"),
    "图书馆": ("file", HOME / ".aionui/library/library.py"),
    "上下文治理": ("file", TRI / "daemon/context_govern.py"),
    "元前瞻": ("file", TRI / "daemon/prospect_reflect.py"),
    "诚实守卫": ("file", TRI / "daemon/honesty_guard.py"),
    "元认知": ("file", TRI / "daemon/meta_cognition.py"),
    "债务引擎": ("file", TRI / "debt/debt_library.yaml"),
    "数据管道": ("file", TRI / "data_eng/pipeline/pipeline_cost.py"),
    "科研循环": ("file", TRI / "research_lab/experiment_code/bench_scoring.py"),
    "治理网关": ("file", WS / "agent-governance-v2/src/protocol_gateway.py"),
    "VCE 扫描": ("file", WS / "agent-governance-v2/src/vce_scanner.py"),
    "AST 守卫": ("file", WS / "agent-governance-v2/src/ast_guard.py"),
    "标定器": ("file", WS / "bottlesumo_pi/scripts/step_response_calibrator.py"),
    "Rerun 画布": ("port", 9090),
    "DSH Web UI": ("port", 3080),
    "AFFiNE": ("port", 3001),
    "元思考报告": ("file", TRI / "reports/metathink_report.md"),
}

MODEL_LIMIT_KEYWORDS = ["2026 之后", "实时", "最新", "当前价格", "内部权重",
                        "训练数据", "未来", "趋势", "预测", "SOTA", "基准分数"]
TOOL_KEYWORDS = ["工具", "CLI", "命令", "端口", "服务", "API", "MCP", "GUI", "硬件", "真机"]


def port_up(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1)
    try:
        s.connect(("127.0.0.1", int(port)))
        return True
    except OSError:
        return False
    finally:
        s.close()


def assess(claim):
    """四分类不确定性评估 (解耦: 判定逻辑独立于 honesty_guard 的二元检查)"""
    c = claim.strip()
    # 1. 能力注册表命中 -> 验证存在性
    for name, (kind, target) in VERIFIABLE.items():
        if name in c:
            ok = target.exists() if kind == "file" else port_up(target)
            if ok:
                return {"claim": c[:60], "source": "verified", "confidence": 0.95,
                        "evidence": f"{name} ({kind}={target})",
                        "action": "继续输出", "matched": name}
            return {"claim": c[:60], "source": "tool_unavailable", "confidence": 0.4,
                    "evidence": f"{name} 目标缺失/端口关闭 ({target})",
                    "action": "降级为计划中/建议", "matched": name}
    # 2. 计划性表述优先 (避免强声称词"完成"误判计划句)
    if WEAK_RE.search(c):
        return {"claim": c[:60], "source": "external_unknown", "confidence": 0.5,
                "evidence": "计划性/预估性表述",
                "action": "按计划处理", "matched": None}
    # 3. 模型局限关键词
    if any(k in c for k in MODEL_LIMIT_KEYWORDS):
        return {"claim": c[:60], "source": "model_limit", "confidence": 0.3,
                "evidence": "涉及模型知识截止/外部实时信息",
                "action": "标注'需搜索核验'", "matched": None}
    # 4. 强声称但无本地证据
    if STRONG_RE.search(c):
        return {"claim": c[:60], "source": "data_insufficient", "confidence": 0.2,
                "evidence": "强声称但无注册表/文件证据",
                "action": "拒绝或降级", "matched": None}
    # 5. 默认
    return {"claim": c[:60], "source": "external_unknown", "confidence": 0.4,
            "evidence": "无特征", "action": "标注不确定", "matched": None}


def audit_dir(reports_dir):
    """自举: 批量审计自有报告中的声明行, 统计不确定性来源分布"""
    dist = {}
    samples = []
    for f in sorted(Path(reports_dir).glob("*.md")):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if not s or not (STRONG_RE.search(s) or WEAK_RE.search(s)):
                continue
            if len(s) < 12 or s.startswith(("|", "#", "-", ">")):
                continue
            r = assess(s)
            dist[r["source"]] = dist.get(r["source"], 0) + 1
            if r["source"] != "verified" and len(samples) < 8:
                samples.append({"file": f.name, "line": s[:70], "source": r["source"]})
    return dist, samples


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "assess"
    if cmd == "assess":
        claim = " ".join(sys.argv[2:]) or "示例声明"
        print(json.dumps(assess(claim), ensure_ascii=False, indent=2))
    elif cmd == "audit":
        dist, samples = audit_dir(TRI / "reports")
        print(f"[audit] 自有报告声明不确定性来源分布:")
        for k, v in sorted(dist.items(), key=lambda x: -x[1]):
            print(f"  {k}: {v}")
        print("\n[非 verified 样本]:")
        for s in samples:
            print(f"  [{s['source']}] {s['file']}: {s['line']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

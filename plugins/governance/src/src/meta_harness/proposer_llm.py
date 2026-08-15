"""proposer_llm — MH 阶段 2': 把 LLM 接为 Proposer 的"脑"（策略规则候选生成）。

对照斯坦福 Meta-Harness（docs/meta_harness_verification.md, AUDIT-0059）:
  - 已有: 轨迹库 (trace/), 整树变异算子 (proposer/writer.py), Pareto 前沿
    (pareto/frontier.py), 沙箱验证 (meta_harness/sandbox.py), 确定性聚合
    建议器 (meta_harness/adapter.py)
  - 缺口: Proposer 是外部注入的确定性聚合, 无 LLM 驱动的候选生成
  - 本模块: LLMProposer —— 读取 (当前策略 + 最近决策轨迹诊断) → LLM 生成
    更丰富的规则候选（含 json_path/tool_args 形态）→ fail-closed 验证

安全边界（与 L5 只读原则 + 人工在环一致）:
  - 候选域 = 策略规则 YAML（PolicyEngine 可加载验证的 harness 策略组件）
  - 不自动注入 config/policies.yaml（人工/仲裁裁决后注入）
  - 不修改核心引擎代码（main.py/policy.py 自动化变异 = v2.0/阶段 3）
  - fail-closed: LLM 不可达/超时/解析失败 → 零候选（绝不编造）

环境变量:
  MH_PROPOSER_URL      : Ollama 兼容端点 (默认 http://127.0.0.1:11434/api/generate)
  MH_PROPOSER_MODEL    : 模型名 (默认 qwen2.5-coder:1.5b)
  MH_PROPOSER_TIMEOUT  : 秒 (默认 60)
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from typing import Callable, Optional

MH_PROPOSER_URL = os.environ.get(
    "MH_PROPOSER_URL", "http://127.0.0.1:11434/api/generate")
MH_PROPOSER_MODEL = os.environ.get("MH_PROPOSER_MODEL", "qwen2.5-coder:1.5b")
MH_PROPOSER_TIMEOUT = float(os.environ.get("MH_PROPOSER_TIMEOUT", "60"))

_YAML_FENCE_RE = re.compile(  # noqa: policy (markdown YAML code-fence extractor for LLM output)
    r"```(?:yaml|yml)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def build_proposer_prompt(
    incumbent_rules: list[dict],
    diagnosis_lines: list[str],
) -> str:
    """构造 Proposer 提示: 角色 + 当前策略 + 轨迹诊断 + 严格输出约束。

    约束要点: 只输出 YAML (rules 列表), 每条规则字段为
    name/path_pattern/method/(json_path|json_pattern|tool_args)/action/
    priority/reason; 不得输出核心引擎代码; 不得重复现有规则。
    """
    inc = json.dumps(incumbent_rules, ensure_ascii=False, indent=1) if incumbent_rules else "(空)"
    diag = "\n".join(diagnosis_lines) if diagnosis_lines else "(无可用诊断)"
    return (
        "[Meta-Harness Proposer] 你是 agent-governance-v2 的策略建议器。\n"
        "任务: 基于当前策略与最近治理决策轨迹, 提出 1-3 条新的或改进的 "
        "YAML 策略规则候选, 用于修复轨迹中暴露的治理缺口。\n\n"
        "== 当前策略 (incumbent) ==\n" + inc + "\n\n"
        "== 最近决策轨迹诊断 ==\n" + diag + "\n\n"
        "== 输出约束 (必须遵守) ==\n"
        "1. 只输出 YAML, 顶层为 rules: 列表; 不要输出任何解释文字或代码块围栏之外的内容。\n"
        "2. 每条规则字段: name(唯一), path_pattern, method, 以及以下三种匹配之一:\n"
        "   - json_path: \"$..key\" (+ 可选 json_pattern 正则)\n"
        "   - tool_args: {name: 工具名(glob), 参数键: glob 值}  ← 推荐用于工具调用治理\n"
        "3. action: DENY(默认) 或 ESCALATE; priority 数值越小越先命中。\n"
        "4. reason 用中文说明针对的缺口 (引用诊断证据)。\n"
        "5. 不得重复 incumbent 已覆盖的 (path_pattern, method, name); 不得修改核心引擎。\n"
    )


def _extract_yaml_blocks(text: str) -> list[str]:
    """从 LLM 输出提取 YAML 块: 优先 ```yaml 围栏块; 无围栏时整段作为候选。"""
    blocks = [m.group(1).strip() for m in _YAML_FENCE_RE.finditer(text)]
    if blocks:
        return blocks
    stripped = text.strip()
    if stripped and ("rules:" in stripped):
        return [stripped]
    return []


def _urllib_client(prompt: str, url: str, model: str, timeout: float) -> str:
    """默认 LLM 客户端: POST {url} {model: ..., prompt: ..., stream: false}。
    返回模型生成文本。抛异常 = 不可达/超时/非 2xx → 调用方 fail-closed。"""
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.4},
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8", "replace"))
    text = body.get("response") or body.get("choices", [{}])[0].get("text") or ""
    if not text.strip():
        raise ValueError("LLM 返回空响应 (fail-closed)")
    return text


class LLMProposer:
    """LLM 驱动的策略规则提议器（阶段 2'）。

    propose() 输入: incumbent 规则 + 诊断行; 输出: 验证通过的候选列表
    [{"yaml_text", "rules", "reason"}]; 失败路径一律返回空候选 + llm_error,
    绝不编造。client 可注入 (测试用 FakeClient)。
    """

    def __init__(
        self,
        url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        client: Optional[Callable[[str, str, str, float], str]] = None,
    ):
        self.url = url or MH_PROPOSER_URL
        self.model = model or MH_PROPOSER_MODEL
        self.timeout = timeout if timeout is not None else MH_PROPOSER_TIMEOUT
        self._client = client or _urllib_client

    def propose(
        self,
        incumbent_rules: list[dict],
        diagnosis_lines: list[str],
        max_candidates: int = 3,
    ) -> dict:
        """生成并验证候选规则。

        返回: {"candidates": [...], "dropped": [str], "llm_error": str|None}
        candidates 项: {"yaml_text", "rules", "reason", "rule_count"}
        """
        if max_candidates < 1:
            raise ValueError("max_candidates 必须 ≥ 1")
        prompt = build_proposer_prompt(incumbent_rules, diagnosis_lines)
        try:
            raw = self._client(prompt, self.url, self.model, self.timeout)
        except Exception as exc:  # 不可达/超时/HTTP 错误 → fail-closed
            return {"candidates": [], "dropped": [],
                    "llm_error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        if not raw or not raw.strip():  # 空输出同样 fail-closed, 不静默
            return {"candidates": [], "dropped": [], "llm_error": "空响应 (fail-closed)"}

        from .adapter import validate_candidate  # 复用 fail-closed 验证

        candidates, dropped = [], []
        for block in _extract_yaml_blocks(raw)[:max_candidates]:
            import yaml as _yaml
            try:
                data = _yaml.safe_load(block)
            except Exception as exc:
                dropped.append(f"YAML 解析失败: {str(exc)[:100]}")
                continue
            if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
                dropped.append("顶层不是 rules: 列表")
                continue
            rules = [r for r in data["rules"] if isinstance(r, dict)]
            if not rules:
                dropped.append("规则列表为空")
                continue
            # fail-closed: 候选与现有策略合并加载, 任一坏规则 → 丢弃
            import tempfile
            from pathlib import Path
            with tempfile.NamedTemporaryFile(
                    "w", suffix=".yaml", encoding="utf-8", delete=False) as tf:
                _yaml.safe_dump({"name": "candidate", "version": "0.0.1",
                                 "rules": rules}, tf, allow_unicode=True)
                tmp_path = tf.name
            try:
                result = validate_candidate(tmp_path)
            finally:
                Path(tmp_path).unlink(missing_ok=True)
            if not result["valid"]:
                dropped.append(f"验证失败: {result['reason'][:120]}")
                continue
            candidates.append({
                "yaml_text": block,
                "rules": rules,
                "reason": rules[0].get("reason", ""),
                "rule_count": len(rules),
            })
        return {"candidates": candidates, "dropped": dropped, "llm_error": None}


def main(argv: list[str] | None = None) -> int:
    """CLI: mh-propose --incumbent config/policies.yaml [--db audit.db]"""
    import argparse
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(prog="mh-propose")
    parser.add_argument("--incumbent", default="config/policies.yaml")
    parser.add_argument("--db", help="审计库路径 (提供则注入诊断)")
    parser.add_argument("--out", default=".aionui/context/mh_propose.md")
    args = parser.parse_args(argv)

    from pathlib import Path
    import yaml as _yaml

    incumbent = []
    p = Path(args.incumbent)
    if p.exists():
        data = _yaml.safe_load(p.read_text(encoding="utf-8"))
        incumbent = data.get("rules", []) if isinstance(data, dict) else []
    diag = []
    if args.db:
        from ..storage import Storage
        storage = Storage(db_path=args.db)
        agg: dict = {}
        for rec in storage.get_recent(limit=200):
            if rec.get("verdict") not in ("DENY", "ESCALATE"):
                continue
            key = (rec.get("method", "?"), rec.get("path", "?"),
                   rec.get("tool_name") or "?")
            agg[key] = agg.get(key, 0) + 1
        for (m, path, tool), cnt in sorted(agg.items(), key=lambda kv: -kv[1])[:15]:
            diag.append(f"x{cnt} {m} {path} tool={tool}")

    result = LLMProposer().propose(incumbent, diag)
    report = [f"# mh-propose 报告 ({LLMProposer().model})",
              f"- LLM 错误: {result['llm_error'] or '无'}",
              f"- 候选: {len(result['candidates'])}  丢弃: {len(result['dropped'])}"]
    for i, c in enumerate(result["candidates"], 1):
        report.append(f"\n## 候选 {i}\n```yaml\n{c['yaml_text']}\n```")
    for d in result["dropped"]:
        report.append(f"\n- (丢弃) {d}")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(report), encoding="utf-8")
    print(f"[mh-propose] 候选={len(result['candidates'])} 丢弃={len(result['dropped'])} "
          f"error={result['llm_error'] or '无'} → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

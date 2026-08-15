#!/usr/bin/env python3
"""编码代理 Proposer (P0-V1) + 元认知模块 (P0-V2) — MHA-ARCH v1.0 学术对齐.

斯坦福 Meta-Harness (arXiv:2603.28052) 核心复刻: 用本地 LLM 作为编码代理,
读取全部历史候选的 源码/分数/执行轨迹 后自由生成候选变体 (而非规则模板)。

与 variants.py 的关系:
    - 平行共存, 不替换 (向后兼容, 红线#3: 默认路径零变化)
    - 启用方式: --proposer code_agent (outer_loop) 或本文件独立 CLI
    - 输出与 Variant 同构 (variants.py::Variant), 必须通过 diff 精确串匹配校验

引擎: 本地 Ollama qwen2.5:7b (OpenAI 兼容 API http://localhost:11434/v1)
     (angrysky56/meta-harness 分支的 Ollama 支持路径, 适配本地 DeepSeek 部署)

会话契约: 参照官方 claude_wrapper.py SessionResult
    (prompt/text/files_read/token_usage/duration/model) -> experience/sessions.jsonl

元认知 (P0-V2, advanced-reasoning 轻量本地版):
    - 置信度追踪: proposer 自报 confidence + 依据
    - 假设检验: 假设->评估结果配对 -> experience/hypotheses.jsonl, 命中率注入下次提议

用法:
    python3 governance/meta_harness/code_agent_proposer.py --probe        # 实测一轮 (建议先跑)
    python3 governance/meta_harness/code_agent_proposer.py --json out.json # 输出候选
    python3 governance/meta_harness/code_agent_proposer.py --self-test    # 离线自检 (无 LLM)
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
import uuid
from dataclasses import dataclass, field, asdict

# Windows cp950 控制台修复 (既有缺陷同类): 强制 UTF-8 输出
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from variants import Variant, HARNESS_FILES, _find_file, _read_text, detect_always_false  # noqa: E402

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
META_HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
# 血缘文件搜索基数: 注意布局是 <工作区根>/bottlesumo_pi/... (variants.py 的
# REPO_ROOT/../.. 会越过工作区根, 这里是本地修正, 不动 variants.py)
WORKSPACE_ROOT = os.path.abspath(os.path.join(REPO_ROOT, ".."))
EXPERIENCE_DIR = os.path.join(os.path.dirname(__file__), "experience")
SESSIONS_LOG = os.path.join(EXPERIENCE_DIR, "sessions.jsonl")
HYPOTHESES_LOG = os.path.join(EXPERIENCE_DIR, "hypotheses.jsonl")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/v1/chat/completions")
PROPOSER_MODEL = os.environ.get("PROPOSER_MODEL", "qwen2.5:7b")
MAX_VARIANTS = 3          # 与 variants.py 一致: 每轮最多 3 候选
OLLAMA_TIMEOUT_S = 900    # FP-MC-006: 480s 在模型冷启动+大prompt时不足 (S16 ROUND1 实证超时); 900s=15min
OLLAMA_MAX_TOKENS = 250   # 候选 JSON 上限 (1-3 候选 + 简短 reasoning); 400 时偶发超 420s (实证超时)

# 时延基线 (2026-08-07, PM 裁决 1 记录, P2-V4 性能参照):
#   P0 基线 (无检索):        335-341s/轮 (prompt 2828 tokens)
#   P1-V3 基线 (bge-m3 检索): 371-434s/轮 (prompt 3137 tokens, 均值 ~392s, 增量 +31~93s)
#   检索本身: 3.7-10.5s/轮 (≤30s 预算)
#   P2-V4 触发阈值: 总时延 > 500s/轮 时执行压缩方案
#     (max_tokens 250->230 + format_experience max_chars 400->300, 预期均值增量降至 +30-40s)
#   实测参照: prompt 2828->3137 (+309 tokens) 预填充 +10-15s; ROUND 3 的 434s 受
#   max_tokens=250 截断影响 (completion 达上限 250)
OLLAMA_NUM_CTX = 4096     # 显式上下文窗口 (prompt ~2k tokens + 输出, 默认 2048 会截断)

# 领域知识注入 (与 domain_spec.md / PM 映射公式保持一致)
DOMAIN_KNOWLEDGE = f"""
领域: BottleSumo 相扑机器人 Harness 优化。合法目标文件 (只改这 5 个):
  {json.dumps(HARNESS_FILES, ensure_ascii=False)}
物理约束: 线速度 <= 0.534 m/s, 角速度 <= 4.0 rad/s。
核心闭环: 视觉检测 edge_min < 0.20 时注入 decay=0.06+0.02*(0.20-edge_min)/0.20 (范围 0.06-0.10,
          edge_min<0.05 封顶 0.10)。门阈值 0.6, 评估 10 局确定性种子 (5 对手 x 2)。
改进方向参考: 接战窗 CLOSE-PUSH ±15°、FLANK 角、动量系数 (momentum = net * TIMESTEP * X)、
  GRIP_DECAY 默认值 0.06、奖励权重。
"""


@dataclass
class SessionResult:
    """官方 claude_wrapper.py SessionResult 契约 (本地实现).

    P1-1 (Sprint 9, 2026-08-05) 标准化: 对齐官方字段
    session_id/tool_calls/token_usage/reasoning_chain, 旧字段
    prompt_tokens/completion_tokens/duration_s 保留向后兼容。
    """
    model: str
    session_id: str = ""            # 官方契约: 会话唯一 ID (uuid8 + ts)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    duration_s: float = 0.0
    n_variants_raw: int = 0
    n_variants_valid: int = 0
    ts: str = ""
    note: str = ""
    tool_calls: list = field(default_factory=list)      # 官方契约: 工具调用实录
    token_usage: dict = field(default_factory=dict)     # 官方契约: {prompt,completion,total}
    reasoning_chain: list = field(default_factory=list) # P1-1: 检索->工具->重试 完整推理链


# --------------------------------------------------------------------------
# 历史血缘加载 (编码代理的"文件系统访问")
# --------------------------------------------------------------------------
def load_history() -> dict:
    """读取 候选库 + Pareto + 缺陷库 + 最近门报告 + 假设检验历史。"""
    hist = {"candidates": [], "pareto": {}, "defects": {}, "gate": {}, "hypothesis_hits": {}}

    # 1. harness_candidates.json (候选库) — 修正搜索基数 (工作区根 vs repo 根)
    for p in (os.path.join(WORKSPACE_ROOT, "harness_candidates.json"),
              os.path.join(REPO_ROOT, "harness_candidates.json"),
              _find_file("harness_candidates.json")):
        if p and os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                hist["candidates"] = data if isinstance(data, list) else data.get("candidates", [])
                break
            except (OSError, json.JSONDecodeError):
                continue

    # 2. pareto_frontier.md + failure_analysis.md (variants.py 既有解析器)
    hist["pareto"] = variants_load_pareto()
    hist["defects"] = variants_load_defects()

    # 3. v9_gate_report.json (最近门评估)
    hist["gate"] = variants_load_gate()

    # 4. 假设检验命中率 (元认知: 经验->能力)
    hits = {"confirmed": 0, "rejected": 0}
    hyps = load_hypotheses()
    for h in hyps:
        if h.get("outcome") == "confirmed":
            hits["confirmed"] += 1
        elif h.get("outcome") == "rejected":
            hits["rejected"] += 1
    hist["hypothesis_hits"] = hits
    hist["n_hypotheses"] = len(hyps)
    return hist


def _find_ws(name: str) -> str:
    """血缘文件定位: meta_harness 专属目录优先, 其次工作区根与 repo 根。

    2026-08-06 修复: P1 血缘文件已迁至 meta_harness/, 避免命中工作区根
    被 AST Guard 内容污染的旧文件 (跨项目污染修复)。
    """
    for p in (
        os.path.join(META_HARNESS_DIR, name),
        os.path.join(WORKSPACE_ROOT, name),
        os.path.join(REPO_ROOT, name),
    ):
        if os.path.exists(p):
            return p
    return ""


def variants_load_pareto() -> dict:
    from variants import load_pareto
    return load_pareto(_find_ws("pareto_frontier.md"))


def variants_load_defects() -> dict:
    from variants import load_failure_analysis
    return load_failure_analysis(_find_ws("failure_analysis.md"))


def variants_load_gate() -> dict:
    from variants import load_last_gate_report
    return load_last_gate_report()


# --------------------------------------------------------------------------
# 系统提示构建 (Meta-Harness 理论 + 领域知识 + JSON 契约)
# --------------------------------------------------------------------------
# Sprint 21 M3: 扰动-行为映射先验 (P2 蒸馏 D2 注入, 从 S19_VERIFY/S20_P2DATA INCONCLUSIVE 案例归纳)
# 18 次门禁拦截中 6 次 INCONCLUSIVE = 扰动未跨越行为感知阈值 (行为指纹不变, 信号相同)
PERTURBATION_PRIOR = (
    "行为感知阈值 (Sprint 21 蒸馏先验, INCONCLUSIVE 案例归纳): 候选扰动必须跨越行为感知阈值, "
    "否则行为指纹不变 -> 差分门禁判定 INCONCLUSIVE 不入 Pareto:\n"
    "  - 角度锚点 (BETWEEN/abs 比较): 变化幅度 >= 10 度\n"
    "  - 数值阈值 (dist/score 常量): 变化幅度 >= 20%%\n"
    "  - 物理系数 (momentum/decay/TIMESTEP 乘数): 变化幅度 >= 0.2\n"
    "  若你的 diff 扰动低于上述阈值, 请显著加大幅度或改选其他锚点。"
)


def build_system_prompt(hist: dict, retrieved: str = None,
                        target_priority: list = None,
                        mcp_context: str = None) -> str:
    cands = hist["candidates"][-8:]  # 最近 8 个候选 (上下文限制)
    # FP-MC-010: 领域迁移时 (targets 非默认), 过滤历史候选到目标域 —
    # 否则 physics 历史候选主导 LLM 复制其 target_file/anchor (S16 实证 4 轮 0 候选)
    targets0 = target_priority or ["simulation/lightweight_env.py"]
    if targets0 != ["simulation/lightweight_env.py"]:
        cands = [c for c in cands if c.get("target_file") in targets0][-8:]
    cand_txt = "\n".join(
        f"  - {c.get('id', '?')} layer={c.get('layer')} score={c.get('score', c.get('winrate'))} "
        f"hyp={str(c.get('hypothesis'))[:80]}"
        for c in cands
    ) or "  (无历史候选)"
    retrieved_txt = f"\n检索到的历史经验 (语义检索, 来源标注):\n{retrieved}\n" if retrieved else ""
    # Sprint 11: MCP 增强上下文 (元认知/环境引导/语义检索, 经 MCP 协议调用)
    mcp_txt = f"\nMCP 实时增强上下文:\n{mcp_context}\n" if mcp_context else ""
    # P2-V4: 目标文件约束按 meta_config 优先级列表 (门裁决可切换)
    targets = target_priority or ["simulation/lightweight_env.py"]
    target_constraint = (
        f"\n目标文件约束 (硬性): 本轮候选的目标文件必须从以下列表选择 (禁止列表外文件): "
        f"{', '.join(targets)} (优先修改排位最前的目标文件); "
        "diff 的 anchor 必须是目标文件中唯一出现的行;"
        "禁止修改 governance/meta_language/simulation_rules.abdl 等规则文件。"
        "检索到的历史经验仅供决策参考, 不得照抄其中的锚点/行内容;"
        "若历史候选来自其他领域, 严禁沿用其 target_file/anchor。"
    ) if retrieved else ""
    return f"""你是斯坦福 Meta-Harness 的编码代理 Proposer。你通过文件系统访问所有历史候选的源码、
分数与执行轨迹, 搜索更优的 Harness。你的任务是提出 1-3 个候选变体。

{DOMAIN_KNOWLEDGE}

历史候选 (最近 8 个):
{cand_txt}

当前 Pareto 最优: {json.dumps(hist['pareto'], ensure_ascii=False)[:200]}
缺陷库: {json.dumps(hist['defects'], ensure_ascii=False)[:300]}
最近门评估: {json.dumps(hist['gate'], ensure_ascii=False)[:200]}
假设检验历史: confirmed={hist['hypothesis_hits'].get('confirmed', 0)} rejected={hist['hypothesis_hits'].get('rejected', 0)}
{retrieved_txt}
{mcp_txt}
{target_constraint}
硬约束:
1. diff 用 **anchor 形态**: anchor 必须是目标文件中的精确短串 (从摘录逐字符复制,
   禁止改写/补全), 代码侧会自动把 anchor 定位到所在整行作为 old; new 给出替换后的完整行。
   若确有把握, 也可用 old 形态 (old 必须逐字符匹配磁盘)。
2. 每个变体只改 1 个因果假说 (可含多个 diff 对, 但同属一个命题)。
3. 物理约束: 线速度 <= 0.534 m/s, 角速度 <= 4.0 rad/s。
4. {PERTURBATION_PRIOR}

输出严格 JSON (无其他文字), 格式:
{{"variants": [{{"id": "ca_<layer>_<seq>", "layer": "rules|mapping|physics|reward|gate",
  "target_file": "相对仓库根路径", "diff": [{{"anchor": "精确短串(从摘录复制)", "new": "替换后的完整行",
  "expected": 1}}], "hypothesis": "一句话因果假说", "evidence": ["F-xxx 或 数据依据"],
  "confidence": 0.0-1.0, "reasoning": "你读了哪些历史轨迹, 为什么这个改动能提升"}}]}}
"""


def _code_snippet(target: str, keywords: tuple, ctx_lines: int = 2, max_hits: int = 6) -> str:
    """提取目标文件含关键符号的行及其上下文 (编码代理的"文件系统访问"本地等价物)。

    让 LLM 基于真实源码提议 diff, 而非凭记忆编造 (降低幻觉率)。
    体积控制: abdl 规则声明行较长, ctx=3; 普通 py 文件 ctx=2。
    """
    path = os.path.join(REPO_ROOT, target)
    text = _read_text(path)
    if not text:
        return f"(无法读取 {target})"
    lines = text.splitlines()
    header = "\n".join(f"  H{i + 1}: {l[:110]}" for i, l in enumerate(lines[:12]))
    hits = []
    # FP-MC-011: 常量定义行 (NAME = 数值) 优先入列 — 它们是唯一锚点 (如 EDGE_*),
    # 若被关键字命中行淹没, LLM 会退而选函数体内重复行 (S16 实证 dist anchor 3 次重复)
    const_hits = []
    for i, ln in enumerate(lines):
        if re.match(r"^[A-Z][A-Z_0-9]*\s*=\s*-?\d", ln):
            lo, hi = max(0, i - ctx_lines), min(len(lines), i + ctx_lines + 1)
            const_hits.append(f"  L{lo + 1}-{hi}: " + " | ".join(l.strip()[:140] for l in lines[lo:hi]))
    hits.extend(const_hits[:max_hits])
    for i, ln in enumerate(lines):
        if any(k in ln for k in keywords):
            lo, hi = max(0, i - ctx_lines), min(len(lines), i + ctx_lines + 1)
            hits.append(f"  L{lo + 1}-{hi}: " + " | ".join(l.strip()[:140] for l in lines[lo:hi]))
    body = "\n".join(hits[:max_hits * 2]) if hits else f"(目标中无 {keywords} 关键词, 请勿臆造相关修改)"
    return f"## {target} 头部 (前12行):\n{header}\n## 关键符号命中:\n{body}"


def build_user_prompt(hist: dict, targets: list = None) -> str:
    """用户轮: 附上目标文件真实源码摘录, 要求基于磁盘事实提议。

    targets: 本轮目标域 (meta_config.target_priority, 路径列表)。决定注入哪些
      文件摘录与输出 schema — FP-MC-009: 此前硬编码 rules+physics (S15 physics
      时代), S16 切换 reward/bridge 后 LLM 无源码可依, 顽固提议 physics 被白名单
      全拒 (S16 第三轮 ROUND1 实证 0 候选)。
    """
    # 每个 layer 的关键符号 (与 variants.py 规则工厂对齐)
    layer_keywords = {
        "rules": ("priority:", "description:", "When", "edge", "danger", "FLANK", "CLOSE"),
        "mapping": ("ACTION", "FORWARD", "TURN", "SPIN", "mapping", "abdl"),
        "physics": ("GRIP_DECAY", "momentum", "TIMESTEP", "MAX_LINEAR_SPEED", "MAX_ANGULAR_RATE", "decay"),
        "reward": ("reward", "win", "survive", "penalty", "opponent", "distance", "EDGE_"),
        "gate": ("win_rate", "threshold", "0.6", "episodes", "score"),
    }
    # 目标域 -> layer 名 (按 targets 顺序, 最多 2 个文件) —
    # FP-MC-011: 按 targets 顺序而非 HARNESS_FILES 顺序, 保证 schema 层枚举
    # 与目标优先级一致 (reward 优先于 mapping, LLM 会聚焦 reward 常量锚点)
    layer_of = {p: l for l, p in HARNESS_FILES.items()}
    keep_layers = [layer_of[t] for t in (targets or []) if t in layer_of][:2]
    if not keep_layers:  # targets 为空/无匹配 -> 回退旧行为 (rules+physics)
        keep_layers = ["rules", "physics"]
    snippets = []
    for layer, fname in HARNESS_FILES.items():
        if layer not in keep_layers:
            continue
        ctx = 3 if fname.endswith(".abdl") else 2  # abdl 规则声明行长
        snippets.append(_code_snippet(fname, layer_keywords.get(layer, ()), ctx_lines=ctx))
    layer_enum = "|".join(keep_layers)
    contract = (
        "现在输出严格 JSON (无其他文字, 不要输出代码块标记, 不要输出任何解释):\n"
        f'{{"variants": [{{"id": "ca_<layer>_<seq>", "layer": "{layer_enum}", '
        '"target_file": "目标文件路径", '
        '"diff": [{"anchor": "行内精确短串, 如常量名+等号, 从摘录逐字符复制", '
        '"value": "新数值, 如 0.10"}], '
        '"hypothesis": "一句话因果假说", "evidence": ["依据"], '
        '"confidence": 0.0到1.0, "reasoning": "为什么这个数值调整会提升"}]}\n'
        "若无法确认任何有效改进, 输出 {\"variants\": []} (诚实优于编造)。"
    )
    return (
        f"任务: 针对以下 {len(snippets)} 个 Harness 文件, 基于真实源码摘录提议 1-3 个候选变体。\n"
        f"文件列表 (必须从其中选择 target_file): {', '.join(p for l, p in HARNESS_FILES.items() if l in keep_layers)}\n"
        "规则: anchor 必须从摘录逐字符复制 (禁止改写/补全); value 是建议的新数值 "
        "(代码会自动把 anchor 所在行的数字替换为 value, 你无需给出完整行)。\n"
        "锚点策略 (FP-MC-011/012): 优先选择文件顶部的参数常量行 (如 NAME = 0.08) 作为 anchor — "
        "常量名在文件中唯一, 定位可靠; 若目标文件无唯一常量 (多角色共用逻辑), 可选用"
        "函数内条件行 (如 dist < 0.20) — 该 anchor 将替换文件中的全部出现 (统一调整语义); "
        "避免选择函数体内重复出现的行 (如多角色共用的 "
        "params.get(...) 调用, 同一行可能出现多次)。\n"
        f"目标优先级: 按以下顺序优先探索 {', '.join(keep_layers)} 层.\n\n"
        + "\n\n".join(snippets)
        + "\n\n" + contract
    )


# --------------------------------------------------------------------------
# Ollama 调用 (OpenAI 兼容)
# --------------------------------------------------------------------------
class LLMTimeoutError(RuntimeError):
    """Ollama 调用超时/网络失败 — 提议器降级信号 (FP-MC-006)."""


def call_ollama(system: str, user: str, model: str = PROPOSER_MODEL,
                temperature: float = 0.3) -> dict:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,  # P2-V4: meta_config 门裁决可动态调整 (降 0.1 提结构遵循度)
        "stream": False,
        "max_tokens": OLLAMA_MAX_TOKENS,
        "options": {"num_ctx": OLLAMA_NUM_CTX},
    }
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (TimeoutError, OSError) as e:
        # FP-MC-006: 未捕获时 outer_loop 整体崩溃 (S16 ROUND1 实证); 包装为降级信号
        raise LLMTimeoutError(
            f"Ollama 调用失败/超时 ({OLLAMA_TIMEOUT_S}s): {e}") from e
    dur = time.time() - t0
    usage = data.get("usage", {})
    return {
        "text": data["choices"][0]["message"]["content"],
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "duration_s": dur,
    }


# --------------------------------------------------------------------------
# 输出解析 + 幻觉防御 (diff 精确串匹配校验)
# --------------------------------------------------------------------------
def _extract_json_object(text: str) -> dict:
    """从 LLM 输出中平衡提取第一个完整 JSON 对象 (容忍代码块/杂文包裹)。

    用 json.JSONDecoder.raw_decode 替代脆弱正则: 正确处理嵌套括号,
    不吞入尾部杂文。返回 dict 或 None。
    """
    dec = json.JSONDecoder()
    i = text.find("{")
    while i != -1:
        try:
            obj, _ = dec.raw_decode(text, i)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        i = text.find("{", i + 1)
    return None


def parse_variants(text: str) -> list:
    """从 LLM 输出提取 variants 数组 (平衡解析, 容忍包裹)。"""
    obj = _extract_json_object(text)
    if not obj:
        return []
    return obj.get("variants", []) if isinstance(obj, dict) else []


def _find_anchor_line(text: str, anchor: str):
    """行级模糊定位 (形态 C): anchor 精确子串优先, 失败则前缀逐步放宽找行。

    7b 会微妙改写 anchor (如 0.06 写成 "0.06"), 精确匹配太脆弱。
    定位到行后, 行内数字替换仍由确定性代码完成 — diff 保持 100% 精确。
    返回 (行文本) 或 None。
    """
    for key in (anchor, anchor[:40], anchor[:30], anchor[:20], anchor[:10]):
        if len(key) < 6:
            break
        for line in text.splitlines():
            if key in line:
                return line
    return None


def _auto_target(anchor: str) -> str:
    """自动定位 anchor 所属文件: 在五文件中找 anchor 唯一匹配 (count>=1) 的目标。

    LLM 输出的 target_file 不可靠 (7b 顽固错配实证), 代码侧以 anchor 为准反查。
    返回目标文件路径, 找不到返回 ""。
    """
    for layer, fname in HARNESS_FILES.items():
        t = _read_text(os.path.join(REPO_ROOT, fname))
        if t and anchor in t:
            return fname
    return ""


def _cross_file_hint(anchor: str, target: str) -> str:
    """智能反馈: anchor 在 target 中未命中时, 扫描其他 4 文件提示正确归属 (重试受益)。"""
    for other_layer, other_file in HARNESS_FILES.items():
        if other_file == target:
            continue
        p = os.path.join(REPO_ROOT, other_file)
        t = _read_text(p)
        if t and t.count(anchor) > 0:
            return f"; 提示: {anchor[:40]!r} 存在于 {other_file} (layer={other_layer})"
    return ""


def resolve_diff(variant: dict, allowed_targets: list = None) -> tuple:
    """结构化 diff 解析 + 幻觉防御 (MHA 重构 v3: 混合架构)。

    LLM 输出三种 diff 形态, 均在此收敛为精确 (old, new) 对:
      C. {anchor, value} (首选): anchor 是行内精确短串 (常量名+等号, 从摘录复制,
         容易); value 是 LLM 建议的新数值。代码侧定位 anchor 所在行, 用正则
         替换行内首个数字为 value — **LLM 只做数值决策, diff 由确定性代码构造**,
         100% 精确 (MetaAgent 工具元学习思想)。
      A. {anchor, new, expected}: anchor 定位所在整行为 old, new 替换整行。
      B. {old, new, expected} (旧格式): old 必须精确匹配, 兼容保留。

    allowed_targets: 本轮目标域白名单 (S16 起, 来自 meta_config.target_priority)。
      非空时强制 LLM 候选只能落在白名单文件内 — 防止检索历史(physics)主导提议
      越界到已饱和领域 (S16 ROUND1/2 实证: 提示词约束被 anchor 反查绕过)。

    返回 (valid, detail, diff_out)。校验失败丢弃候选 (绝不带病入环)。
    """
    target = variant.get("target_file", "")
    if target not in HARNESS_FILES.values():
        return False, f"target_file 不在五文件清单: {target}", []
    if allowed_targets and target not in allowed_targets:
        return False, (f"target_file 不在本轮目标域: {target} "
                       f"(allowed={allowed_targets})"), []
    layer = variant.get("layer", "")
    if layer and layer in HARNESS_FILES and HARNESS_FILES[layer] != target:
        return False, (f"layer={layer} 与 target_file 错配: {HARNESS_FILES[layer]} != {target}"
                       f" (anchor 可能来自错误文件)"), []
    path = os.path.join(REPO_ROOT, target)
    text = _read_text(path)
    if text is None:
        return False, f"无法读取目标文件: {path}", []

    diffs = variant.get("diff", [])
    if not diffs:
        return False, "diff 为空", []
    resolved = []
    for i, d in enumerate(diffs):
        expected = int(d.get("expected", 1))
        if "value" in d and d.get("anchor"):
            # 形态 C: anchor + 新数值 -> 行级模糊定位 + 行内数字替换
            anchor = d["anchor"]
            value = str(d.get("value", "")).strip()
            if len(anchor) < 3 or not value:
                return False, f"diff[{i}] anchor/value 缺失", []
            cnt = text.count(anchor)
            # FP-MC-012: 重复 anchor 全替换自适应 — bridge 层 3 角色共用逻辑
            # (dist < 0.20 等) 导致唯一性拒绝死循环 (S16 ROUND3 实证);
            # 当 LLM 默认 expected=1 但 anchor 出现 N>1 次, 接受 N 处全替换
            # (统一调整语义, 提示词已声明此行为)
            if cnt > 1 and expected == 1:
                expected = cnt
                d["expected"] = expected
            if cnt != expected:
                # 终极降熵: target_file 以 anchor 为准自动纠正 (7b 顽固错配实证)
                auto = _auto_target(anchor)
                if auto:
                    if allowed_targets and auto not in allowed_targets:
                        return False, (f"anchor {anchor[:40]!r} 反查落点 {auto} 不在本轮目标域 "
                                       f"(allowed={allowed_targets})"), []
                    target = auto
                    layer = next((k for k, v in HARNESS_FILES.items() if v == auto), layer)
                    path = os.path.join(REPO_ROOT, target)
                    text = _read_text(path)
                    cnt = text.count(anchor) if text else 0
                    if cnt == expected:
                        variant["target_file"] = target
                        variant["layer"] = layer
                    else:
                        hint = _cross_file_hint(anchor, target)
                        return False, (f"diff[{i}] anchor {anchor[:40]!r} 在 {target} 匹配 {cnt} 次 "
                                       f"(期望 {expected}){hint}"), []
                else:
                    hint = _cross_file_hint(anchor, target)
                    return False, (f"diff[{i}] anchor {anchor[:40]!r} 在 {target} 匹配 {cnt} 次 "
                                   f"(期望 {expected}){hint}"), []
            # 行级定位 (精确子串或前缀放宽), 行内数字替换
            line = _find_anchor_line(text, anchor)
            if line is None:
                return False, f"diff[{i}] anchor {anchor[:40]!r} 无法定位到任何行", []
            m = re.search(r"[-+]?\d+\.?\d*", line)
            if not m:
                return False, f"diff[{i}] 定位行内无数字: {line[:60]!r}", []
            new_line = line[:m.start()] + value + line[m.end():]
            if len(line) < 4 or len(new_line) < 4:
                return False, f"diff[{i}] 行过短", []
            # Sprint 20 P1: 恒 False 模式拦截 (生成层第一道防线, 运行时另有 apply_precheck)
            af = detect_always_false(line, new_line)
            if af:
                return False, f"diff[{i}] 恒 False 模式: {af}", []
            resolved.append({"old": line, "new": new_line, "expected": expected})
            continue
        if d.get("old"):
            # 形态 B: 直接给 old
            old = d["old"]
            if len(old) < 4:
                return False, f"diff[{i}] old 串过短", []
            cnt = text.count(old)
            # FP-MC-013: 形态 B 对称自适应 — old 为精确串, 磁盘实际匹配 cnt 处
            # 就替换 cnt 处, LLM 声明的 expected 仅作意图参考 (S16 ROUND4 实证:
            # LLM 从重试提示得知 anchor 出现 3 次, 但生成的带上下文 old 行实际
            # 只匹配 1 处; 若按声明次数拒绝则重试 3 次全败, 整轮作废浪费 900s)
            if cnt == 0:
                return False, f"diff[{i}] old 匹配 0 次", []
            if expected != cnt:
                expected = cnt
                d["expected"] = expected
            new = d.get("new", old)
            # Sprint 20 P1: 恒 False 模式拦截 (生成层)
            af = detect_always_false(old, new)
            if af:
                return False, f"diff[{i}] 恒 False 模式: {af}", []
            resolved.append({"old": old, "new": new, "expected": expected})
            continue
        # 形态 A: anchor -> 定位所在整行
        anchor = d.get("anchor", "")
        if not anchor or len(anchor) < 4:
            return False, f"diff[{i}] 需 anchor 或 value 形态", []
        cnt = text.count(anchor)
        if cnt != expected:
            return False, f"diff[{i}] anchor {anchor[:50]!r} 匹配 {cnt} 次 (期望 {expected})", []
        pos = text.find(anchor)
        line_start = text.rfind("\n", 0, pos) + 1
        line_end = text.find("\n", pos)
        if line_end == -1:
            line_end = len(text)
        old_line = text[line_start:line_end]  # anchor 所在整行 (磁盘原文)
        new = d.get("new", old_line)
        if len(old_line) < 4 or len(new) < 4:
            return False, f"diff[{i}] 解析出的行过短", []
        # Sprint 20 P1: 恒 False 模式拦截 (生成层)
        af = detect_always_false(old_line, new)
        if af:
            return False, f"diff[{i}] 恒 False 模式: {af}", []
        resolved.append({"old": old_line, "new": new, "expected": expected})
    variant["diff"] = resolved
    return True, "ok", resolved


def to_variant(v: dict, seq: int) -> Variant:
    """LLM 候选 -> variants.Variant (血缘/元认知元数据注入)。"""
    layer = v.get("layer", "rules")
    return Variant(
        id=v.get("id") or f"ca_{layer}_{seq}",
        layer=layer,
        target_file=v.get("target_file", HARNESS_FILES.get(layer, "")),
        diff=v.get("diff", []),
        hypothesis=v.get("hypothesis", ""),
        evidence=v.get("evidence", []) or ["code_agent(LLM 提议)"],
        bloodline=f"code_agent({PROPOSER_MODEL}) {v.get('reasoning', '')[:60]}",
        parent="code_agent",
        source="code_agent_proposer",
        provenance="LLM 编码代理提议 (MHA-ARCH v1.0)",
        lineage_ctx={
            "confidence": v.get("confidence"),
            "reasoning": v.get("reasoning", ""),
            "model": PROPOSER_MODEL,
        },
    )


# --------------------------------------------------------------------------
# 元认知: 假设检验 + 会话记录 (P0-V2)
# --------------------------------------------------------------------------
def load_hypotheses() -> list:
    if not os.path.exists(HYPOTHESES_LOG):
        return []
    out = []
    with open(HYPOTHESES_LOG, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


def record_hypothesis(variant: Variant, outcome: str, score: dict) -> None:
    """假设检验: 候选评估后配对 假设->结果, 供下次提议注入。"""
    os.makedirs(EXPERIENCE_DIR, exist_ok=True)
    with open(HYPOTHESES_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": time.strftime("%Y%m%d_%H%M%S"),
            "variant_id": variant.id,
            "layer": variant.layer,
            "hypothesis": variant.hypothesis,
            "outcome": outcome,          # confirmed | rejected
            "score": score,
            "confidence": variant.lineage_ctx.get("confidence"),
        }, ensure_ascii=False) + "\n")


def record_session(sr: SessionResult) -> None:
    os.makedirs(EXPERIENCE_DIR, exist_ok=True)
    with open(SESSIONS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(sr), ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------
# 编码代理模式 (P0 对齐: Proposer 自主推理, 2026-08-07)
# 环境引导 (Bootstrapping) + 受限只读工具 (read_file / list_dir / git_status)
# --------------------------------------------------------------------------
AGENT_TOOLS_DOC = """工具契约 (编码代理, 可选): 你可在输出候选前请求读取文件获取完整源码。
格式: {"tool": "read_file", "path": "<相对 REPO_ROOT 路径>", "reason": "<为何读>"}
工具: read_file (只读白名单) / list_dir / git_status。无需读取则直接输出候选 JSON 数组。
"""


def environment_snapshot() -> str:
    """收集沙箱环境快照 (精简版, 控制 prompt 体积防 num_ctx 超限)。

    对齐 Meta-Harness 环境引导: 节省代理 ls/which 类探索轮次。
    2026-08-07: 压缩至 ~300 chars — agent 模式 prompt = 血缘 3137 + 快照 300 +
    工具契约 200 ≈ 3650 tokens < num_ctx 4096 (原版 4200 tokens 超限致 timeout)。
    P1-2 (Sprint 9): 结构化为 build_environment_snapshot() 供版本化落盘,
    本函数保持 ≤400 chars 注入预算。
    """
    snap = build_environment_snapshot()
    lines = ["环境快照:",
             f"- REPO_ROOT={snap['repo_root']} Python={snap['python']} "
             f"Ollama={snap['model']}"]
    if snap.get("git_head"):
        lines.append(f"- Git HEAD={snap['git_head']}")
    ok = [os.path.basename(p) for p in snap.get("harness_files_ready", [])]
    lines.append(f"- Harness 文件 ({len(ok)}/5 就绪): {', '.join(ok)}")
    lines.append("- 血缘: pareto_frontier.md / failure_analysis.md / hypotheses.jsonl "
                 "(meta_harness/)")
    return "\n".join(lines)


def build_environment_snapshot() -> dict:
    """P1-2: 结构化环境快照 (对齐 Terminal-Bench 2.0 快照注入格式).

    含工作目录/文件列表(大小+mtime)/Git HEAD/可用工具/磁盘状态。
    版本化存储至 candidates/<candidate_id>/snapshot.json (每次提议前捕获)。
    """
    snap = {
        "repo_root": REPO_ROOT,
        "python": sys.version.split()[0],
        "model": PROPOSER_MODEL,
        "git_head": "",
        "harness_files_ready": [],
        "files": {},          # {相对路径: {size, mtime}}
        "tools": [],
        "disk_free_gb": None,
        "ts": time.strftime("%Y%m%d_%H%M%S"),
    }
    try:
        import subprocess
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, cwd=REPO_ROOT, timeout=8)
        if head.returncode == 0:
            snap["git_head"] = head.stdout.strip()
    except Exception:
        pass
    for layer, rel in HARNESS_FILES.items():
        abs_p = os.path.join(REPO_ROOT, rel)
        if os.path.exists(abs_p):
            st = os.stat(abs_p)
            snap["harness_files_ready"].append(rel)
            snap["files"][rel] = {"size": st.st_size, "mtime": round(st.st_mtime, 1)}
    for tool in ("python3", "git", "ollama", "wsl"):
        import shutil
        if shutil.which(tool):
            snap["tools"].append(tool)
    try:
        import shutil
        du = shutil.disk_usage(REPO_ROOT)
        snap["disk_free_gb"] = round(du.free / 1024**3, 1)
    except Exception:
        pass
    return snap


def save_candidate_workspace(candidate_id: str, snap: dict,
                             variants_out: list) -> str:
    """P1-2: 候选工作空间隔离 (Filesystem Run Store).

    创建 candidates/<candidate_id>/, 存储:
        snapshot.json  (环境引导快照)
        proposal.md    (提议输出: 候选 id/假说/证据/血缘)
        diff.patch     (差异记录)
    gate_result.json 由 outer_loop 评估后回写。
    返回工作空间绝对路径。
    """
    ws = os.path.join(META_HARNESS_DIR, "candidates", candidate_id)
    os.makedirs(ws, exist_ok=True)
    with open(os.path.join(ws, "snapshot.json"), "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2)
    lines = [f"# 候选工作空间 {candidate_id}", "",
             f"捕获时间: {snap['ts']}  环境: {snap['python']} @ {snap.get('git_head') or 'n/a'}", ""]
    for v in variants_out:
        vd = v if isinstance(v, dict) else v.to_dict()
        lines.append(f"## {vd.get('id', '?')} [{vd.get('layer', '?')}]")
        lines.append(f"- target: {vd.get('target_file', '?')}")
        lines.append(f"- 假说: {vd.get('hypothesis', '?')}")
        lines.append(f"- 证据: {', '.join(vd.get('evidence') or []) or 'n/a'}")
        lines.append(f"- 血缘: {vd.get('bloodline', 'n/a')}")
        lines.append("")
    with open(os.path.join(ws, "proposal.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    diff_lines = []
    for v in variants_out:
        vd = v if isinstance(v, dict) else v.to_dict()
        for i, pair in enumerate(vd.get("diff") or []):
            diff_lines.append(f"--- {vd.get('id', '?')} diff[{i}] "
                              f"({vd.get('target_file', '?')})")
            diff_lines.append(f"- old: {pair.get('old', '')[:120]!r}")
            diff_lines.append(f"+ new: {pair.get('new', '')[:120]!r}")
            diff_lines.append("")
    with open(os.path.join(ws, "diff.patch"), "w", encoding="utf-8") as f:
        f.write("\n".join(diff_lines))
    return ws


# 写作用域白名单 (domain_spec.md §1 五文件 + 血缘/经验文件):
# 候选写入仅允许落在 Harness 五文件; 血缘/经验只读。
ALLOWED_WRITE_PATHS = set(HARNESS_FILES.values())


def _agent_read_file(rel_path: str) -> str:
    """只读工具: 读取 Harness/血缘文件 (白名单外拒绝)。"""
    allowed = set(HARNESS_FILES.values()) | {
        "governance/meta_harness/pareto_frontier.md",
        "governance/meta_harness/failure_analysis.md",
        "governance/meta_harness/experience/hypotheses.jsonl",
        "governance/meta_harness/experience/sessions.jsonl",
    }
    norm = rel_path.replace("\\", "/")
    if norm not in allowed:
        return f"拒绝: {norm} 不在只读白名单。允许: {sorted(allowed)[:4]} ..."
    abs_p = os.path.join(REPO_ROOT, norm)
    if not os.path.exists(abs_p):
        return f"文件不存在: {norm}"
    text = _read_text(abs_p)
    return f"--- {norm} ({len(text)} chars) ---\n{text[:2500]}"


def _agent_list_dir(rel_path: str) -> str:
    """只读工具: 列出目录 (仅 simulation/ 与 meta_harness/)。"""
    base = os.path.join(REPO_ROOT, rel_path)
    if not os.path.isdir(base):
        return f"目录不存在: {rel_path}"
    names = sorted(os.listdir(base))
    return f"--- {rel_path}/ ({len(names)} 项) ---\n" + "\n".join(names[:40])


def _agent_git_status() -> str:
    """只读工具: 工作树变更状态。"""
    import subprocess
    try:
        r = subprocess.run(["git", "status", "--short"],
                           capture_output=True, text=True, cwd=REPO_ROOT, timeout=15)
        out = r.stdout.strip() or "(工作树干净)"
        return f"--- git status ---\n{out[:1500]}"
    except Exception as e:
        return f"git_status 失败: {e}"


def _run_agent_tool(req: dict) -> str:
    """执行工具请求, 返回结果文本。"""
    tool = (req.get("tool") or "").lower()
    if tool == "read_file":
        return _agent_read_file(req.get("path", ""))
    if tool == "list_dir":
        return _agent_list_dir(req.get("path", "simulation"))
    if tool == "git_status":
        return _agent_git_status()
    return f"未知工具: {tool} (可用: read_file / list_dir / git_status)"


# --------------------------------------------------------------------------
# 主入口
# --------------------------------------------------------------------------
def _build_retrieval_query(hist: dict) -> str:
    """构建语义检索查询: 物理参数层聚焦 (P1-V3)。

    2026-08-07 修复: 原查询含"规则引擎"词, 把检索引向 simulation_rules.abdl 规则块,
    注入后 LLM 被带偏提议 abdl 锚点 (11 次匹配) 导致 ROUND 2/3 全部无效。
    改为 physics 参数导向, 命中 lightweight_env.py 的调参经验。
    """
    last = hist["candidates"][-1] if hist["candidates"] else {}
    defect_ids = list(hist["defects"].keys())[:5]
    return (f"BottleSumo 物理参数调优 抓地衰减 grip decay 边缘稳定性 "
            f"层={last.get('layer', 'physics')} 最近候选={last.get('id', '?')} "
            f"活跃缺陷={','.join(defect_ids) if defect_ids else '无'}")


def propose(model: str = PROPOSER_MODEL, max_variants: int = MAX_VARIANTS,
            retriever: str = None, meta_config: dict = None,
            agent: bool = False,
            mcp_context: str = None) -> list:
    """编码代理提议: 读血缘 -> [语义检索] -> [MCP 增强上下文] -> [编码代理工具轮] -> LLM 生成 -> 校验。

    retriever: "bge-m3" 启用 P1-V3 语义检索 (semantic_retriever), 检索结果注入
    build_system_prompt 的 retrieved_experience 字段; None 为 P0 基线行为。
    meta_config: P2-V4 门裁决配置 (temperature / retrieval_threshold /
    target_priority), 由 outer_loop --meta-config 启用后传入; None 为默认。
    agent: 编码代理模式 (P0 对齐) — 环境引导快照注入系统提示 + 1 次受限只读
    工具轮 (read_file/list_dir/git_status), LLM 自主决定读取文件获取完整源码后
    生成候选; False 为既有行为 (零回归)。
    mcp_context: Sprint 11 — 经 MCP 协议获取的增强上下文注入文本 (元认知/
    环境引导/语义检索), 由 outer_loop 默认启用 (--no-mcp-integration 禁用); None 为基线。
    """
    mc = meta_config or {}
    # FP-MC-008: targets 必须在 propose 作用域定义 (此前误用 build_system_prompt
    # 局部变量致 NameError); 白名单=本轮目标域, resolve_diff 强制执行
    targets = mc.get("target_priority") or ["simulation/lightweight_env.py"]
    hist = load_history()
    # P1-1: 会话级推理链采集 (检索 -> 工具轮 -> LLM 尝试 -> 校验反馈)
    chain: list = []
    tool_calls: list = []
    _llm_calls: list = []
    # P1-2: 写作用域违规记录 (越权 target_file) + 候选工作空间
    _scope_violations: list = []
    _workspace_path: str = ""
    retrieved = None
    if retriever == "bge-m3":
        from semantic_retriever import format_experience, retrieve
        t0 = time.time()
        min_score = mc.get("retrieval_threshold", 0.45)
        hits = retrieve(_build_retrieval_query(hist), top_k=3, min_score=min_score)
        # 2026-08-07 修复: 过滤含规则语法 (sensor(/TIMESTEP/.abdl) 的块 —
        # 这类文本注入会把 LLM 带偏到 abdl 规则文件, 产生 anchor 不唯一的无效候选。
        hits = [h for h in hits
                if "sensor(" not in h["text"] and "TIMESTEP" not in h["text"]
                and ".abdl" not in h["text"]]
        # FP-MC-010: 领域迁移时按目标域过滤检索 hits (physics 经验对
        # reward/bridge 探索有害 — 会复制已饱和领域的 anchor 模式)
        if targets != ["simulation/lightweight_env.py"]:
            hits = [h for h in hits if any(t in h["text"] for t in targets)]
        retrieved = format_experience(hits)
        chain.append({
            "step": "retrieve",
            "engine": retriever,
            "query": _build_retrieval_query(hist)[:200],
            "threshold": min_score,
            "hits": len(hits),
            "duration_s": round(time.time() - t0, 2),
        })
        print(f"[code_agent] 语义检索 {len(hits)} 命中 (阈值 {min_score}, 过滤规则语法后), "
              f"检索时延 {time.time() - t0:.1f}s", file=sys.stderr)
    # FP-MC-010: 领域迁移时抑制 MCP hyps 注入 — MCP 上下文的 top_hypotheses
    # 全是 physics 历史假设, 注入即主导 LLM 复制旧领域模式 (S16 实证)
    mcp_for_prompt = mcp_context if targets == ["simulation/lightweight_env.py"] else None
    # 编码代理模式: 环境引导 (Bootstrapping) 注入
    if agent:
        env_txt = environment_snapshot()
        system = (build_system_prompt(hist, retrieved=retrieved,
                                      target_priority=mc.get("target_priority"),
                                      mcp_context=mcp_for_prompt)
                  + "\n\n" + env_txt + "\n\n" + AGENT_TOOLS_DOC)
    else:
        system = build_system_prompt(hist, retrieved=retrieved,
                                     target_priority=mc.get("target_priority"),
                                     mcp_context=mcp_for_prompt)
    user = build_user_prompt(hist, targets)

    # 编码代理工具轮 (最多 1 轮): LLM 可先请求读取文件获取完整源码
    if agent:
        t0 = time.time()
        raw1 = call_ollama(system, user, model,
                           temperature=mc.get("temperature", 0.3))
        txt1 = (raw1.get("text") or "").strip()
        tool_req = None
        if txt1.startswith("{"):
            try:
                maybe = json.loads(txt1)
                if isinstance(maybe, dict) and "tool" in maybe:
                    tool_req = maybe
            except json.JSONDecodeError:
                pass
        if tool_req:
            t_tool = time.time()
            tool_result = _run_agent_tool(tool_req)
            tool_calls.append({
                "tool": tool_req.get("tool"),
                "path": tool_req.get("path", ""),
                "reason": tool_req.get("reason", ""),
                "result_excerpt": (tool_result or "")[:200],
                "duration_s": round(time.time() - t_tool, 2),
            })
            chain.append({
                "step": "tool_call",
                "tool": tool_req.get("tool"),
                "path": tool_req.get("path", ""),
            })
            print(f"[code_agent:agent] 工具轮: {tool_req.get('tool')} "
                  f"{tool_req.get('path', '')} ({time.time() - t0:.0f}s), 反馈中...",
                  file=sys.stderr)
            user = (f"工具执行结果:\n{tool_result}\n\n"
                    "请基于该文件真实内容生成候选 (old 串必须逐字符匹配磁盘)。\n\n"
                    + build_user_prompt(hist, targets))
        # 非工具请求 (LLM 直接输出候选或辅助文本): user 保持原样, 候选由标准重试循环生成
        print(f"[code_agent:agent] 环境引导 + 工具轮时延 {time.time() - t0:.1f}s",
              file=sys.stderr)

    # 提议-验证-反馈重试循环 (编码代理 vs 规则模板的本质区别):
    # LLM 首次提议可能产生幻觉 diff, 被校验器拒绝后, 将拒绝原因反馈给它
    # 令其基于真实源码修正 (最多 MAX_RETRIES 次)。
    MAX_RETRIES = 2
    parsed_all, reject_msgs = [], []
    sr = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            raw = call_ollama(system, user, model,
                              temperature=mc.get("temperature", 0.3))
        except LLMTimeoutError as e:
            # FP-MC-006: 超时降级 — 首次重试 (模型已加载), 再失败返回空候选
            # (outer_loop 走 best-is-None 分支, 不中断整个循环)
            print(f"[code_agent] LLM 调用超时 (attempt {attempt + 1}): {e}", file=sys.stderr)
            if attempt < MAX_RETRIES:
                print("[code_agent] 模型冷启动后重试一次", file=sys.stderr)
                continue
            return []
        if sr is None:
            sr = SessionResult(model=model, ts=time.strftime("%Y%m%d_%H%M%S"),
                               session_id=f"{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}")
        sr.prompt_tokens += raw["prompt_tokens"]
        sr.completion_tokens += raw["completion_tokens"]
        sr.duration_s += raw["duration_s"]
        _llm_calls.append({
            "attempt": attempt + 1,
            "prompt_tokens": raw["prompt_tokens"],
            "completion_tokens": raw["completion_tokens"],
            "duration_s": round(raw["duration_s"], 2),
        })

        parsed = parse_variants(raw["text"])
        parsed_all += parsed
        # 本轮的拒绝原因 (仅统计当轮候选, 用于反馈)
        local_rejects = []
        for v in parsed[:max_variants]:
            ok, detail, _ = resolve_diff(v, targets)
            if not ok:
                local_rejects.append(detail)
                # P1-2: 写作用域强制 — 越权 target_file 记为 scope-violation
                tf = (v.get("target_file") or "").replace("\\", "/")
                if tf and tf not in ALLOWED_WRITE_PATHS:
                    _scope_violations.append({
                        "candidate": v.get("id", "?"),
                        "target_file": tf,
                        "reason": detail[:150],
                        "ts": time.strftime("%H:%M:%S"),
                    })
        if not local_rejects or not parsed:
            break  # 有候选全过校验 或 无候选 (诚实输出)
        reject_msgs += local_rejects
        chain.append({
            "step": "retry_feedback",
            "attempt": attempt + 1,
            "rejected": len(local_rejects),
            "reasons": [m[:150] for m in local_rejects[:3]],
        })
        print(f"[code_agent] 重试 {attempt + 1}/{MAX_RETRIES}: 上一轮 {len(local_rejects)} 个候选被拒 "
              f"(原因: {'; '.join(m[:90] for m in local_rejects[:3])}), 反馈中...", file=sys.stderr)
        user = (
            "你上一轮的候选被校验器拒绝, 原因如下 (diff.old 必须与磁盘精确匹配):\n"
            + "\n".join(f"  - {m[:150]}" for m in local_rejects[:3])
            + "\n\n请基于下方真实源码摘录修正 old 串 (逐字符复制), 只输出能通过校验的候选。"
            + "\n\n" + build_user_prompt(hist, targets)
        )

    sr.n_variants_raw = len(parsed_all)

    out, used_ids = [], set()
    for v in parsed_all[:max_variants * (MAX_RETRIES + 1)]:
        ok, detail, _ = resolve_diff(v, targets)
        if not ok:
            print(f"[code_agent] 丢弃无效候选 {v.get('id', '?')} "
                  f"(target={v.get('target_file', '?')}): {detail}", file=sys.stderr)
            continue
        vv = to_variant(v, len(out) + 1)
        if vv.id in used_ids:
            vv.id = f"{vv.id}_{len(out) + 1}"
        used_ids.add(vv.id)
        out.append(vv)
        if len(out) >= max_variants:
            break

    sr.n_variants_valid = len(out)
    # P1-1: 组装官方 SessionResult 契约字段 (token_usage 累计 / tool_calls / 推理链)
    sr.token_usage = {
        "prompt_tokens": sr.prompt_tokens,
        "completion_tokens": sr.completion_tokens,
        "total_tokens": sr.prompt_tokens + sr.completion_tokens,
    }
    sr.tool_calls = tool_calls
    # P1-2: 环境引导快照版本化存储 + 候选工作空间隔离 (每次提议后落盘)
    _snap = build_environment_snapshot()
    try:
        _workspace_path = save_candidate_workspace(
            sr.session_id, _snap, [v.to_dict() if hasattr(v, "to_dict") else v for v in out])
        for v in out:
            v.workspace = _workspace_path
    except Exception as _e:
        print(f"[code_agent] 候选工作空间写入失败: {_e}", file=sys.stderr)
        _workspace_path = ""
    _snap = None  # 避免大 dict 常驻
    sr.reasoning_chain = chain + [
        {"step": "llm_calls", "calls": _llm_calls,
         "total_prompt": sr.prompt_tokens,
         "total_completion": sr.completion_tokens,
         "total_duration_s": round(sr.duration_s, 2)},
        {"step": "mcp_context", "enabled": bool(mcp_context),
         "injected_chars": len(mcp_context) if mcp_context else 0},
        {"step": "scope_violations", "count": len(_scope_violations),
         "violations": _scope_violations[:5],
         "policy": "allowed_write_paths = Harness 五文件"},
        {"step": "workspace", "path": _workspace_path,
         "snapshot_ts": time.strftime("%Y%m%d_%H%M%S")},
        {"step": "final", "variants_raw": sr.n_variants_raw,
         "variants_valid": sr.n_variants_valid},
    ]
    record_session(sr)
    return out


def self_test() -> int:
    """离线自检: 血缘加载 + 解析 + 校验 (无 LLM 调用)。"""
    hist = load_history()
    assert "candidates" in hist and "pareto" in hist and "defects" in hist
    sys_prompt = build_system_prompt(hist)
    assert "variants" in sys_prompt and "hard 约束" in sys_prompt or "硬约束" in sys_prompt
    # 解析器: 代码块包裹 + 裸 JSON 两种形态
    sample = '{"variants": [{"id": "ca_rules_1", "layer": "rules", "target_file": "x", "diff": []}]}'
    assert len(parse_variants(sample)) == 1
    sample2 = "```json\n{\"variants\": [{\"id\": \"ca_rules_2\"}]}\n```"
    assert parse_variants(sample2)[0]["id"] == "ca_rules_2"
    # 校验器: 空 diff / 非法 target / anchor 不匹配必须拒绝
    ok, detail, _ = resolve_diff({"target_file": "/etc/passwd", "diff": [{"anchor": "x", "new": "y", "expected": 1}]})
    assert not ok and "五文件清单" in detail
    ok, detail, _ = resolve_diff({"target_file": "simulation/lightweight_env.py", "diff": []})
    assert not ok
    # anchor 形态 A: 用真实文件里的串解析整行
    ok, detail, out = resolve_diff({
        "target_file": "simulation/lightweight_env.py",
        "diff": [{"anchor": "GRIP_DECAY", "new": "GRIP_DECAY = 0.10", "expected": 1}]})
    if ok:
        assert out and out[0]["old"].startswith("GRIP_DECAY") or "GRIP_DECAY" in out[0]["old"]
        print(f"[self-test] anchor-A 解析 PASS: old={out[0]['old'][:50]!r}")
    else:
        print(f"[self-test] anchor-A 未命中 (GRIP_DECAY 匹配非 1 次): {detail}")
    # value 形态 C: anchor+value -> 行内数字替换
    ok, detail, out = resolve_diff({
        "target_file": "simulation/lightweight_env.py",
        "diff": [{"anchor": "GRIP_DECAY = ", "value": "0.10"}]})
    if ok:
        print(f"[self-test] value-C 解析 PASS: {out[0]['old'][:40]!r} -> {out[0]['new'][:40]!r}")
    else:
        print(f"[self-test] value-C 未命中: {detail}")
    print(f"[self-test] PASS 血缘={len(hist['candidates'])}条 假设历史={hist['n_hypotheses']}条")
    return 0


def main():
    ap = argparse.ArgumentParser(description="编码代理 Proposer (MHA-ARCH v1.0)")
    ap.add_argument("--probe", action="store_true", help="实测一轮 (调用本地 Ollama)")
    ap.add_argument("--json", metavar="OUT", help="候选输出到 JSON 文件")
    ap.add_argument("--self-test", action="store_true", help="离线自检 (无 LLM)")
    ap.add_argument("--model", default=PROPOSER_MODEL)
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    if args.probe or args.json:
        t0 = time.time()
        variants = propose(model=args.model)
        print(f"[code_agent] {len(variants)} 有效候选 ({time.time() - t0:.1f}s)")
        for v in variants:
            print(f"  {v.id}: {v.hypothesis[:80]} conf={v.lineage_ctx.get('confidence')}")
        if args.json:
            with open(args.json, "w", encoding="utf-8") as f:
                json.dump([v.to_dict() for v in variants], f, ensure_ascii=False, indent=2)
            print(f"[code_agent] 已写 {args.json}")
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())

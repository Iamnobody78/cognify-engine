#!/usr/bin/env python3
"""BottleSumo Meta-Harness 外环编排器 (P1, 永续优化器 v1.0).

实现 Stanford IRIS Lab Meta-Harness 的 Evolution Engine 职责:
    snapshot_harness -> propose_variants -> evaluate_candidate
    -> update_pareto -> promote_best / rollback -> self-reflection

五步循环 (meta_prompts/meta_harness_perpetual_optimizer_v1.md §2):
    ① 快照 5 个 Harness 文件 -> variants/_snapshots/<ts>/
    ② 生成 3 个变体 (variants.py: 规则/映射/物理 各 1)
    ③ 评估 (evaluator_v9.py, 确定性种子, 每轮 >= 1 次 GUI 目视验证标记)
    ④ Pareto 更新 (score >= 当前最优 -> 保留; 否则回滚)
    ⑤ 自反思 (追加 failure_analysis.md)

终止 (meta-prompt §3): HALT/STOP/暂停优化/结束本次循环 (控制文件),
    MAX_ITERATIONS (--iterations N), 探索饱和 (连续 3 轮低于最优 + 无新缺陷类别)。

用法:
    # 一轮 (3 候选, 当前工作树为基线)
    python3 governance/meta_harness/outer_loop.py --iterations 1

    # 全新基线: 先把 5 个 Harness 文件恢复到 HEAD, 再跑 N 轮
    python3 governance/meta_harness/outer_loop.py --iterations 3 --fresh

    # 自动回滚模式: 任何 score < 当前最优 的变体立即回滚
    python3 governance/meta_harness/outer_loop.py --iterations 2 --baseline

    # 控制文件终止 (任意时刻写入 HALT 即停)
    python3 governance/meta_harness/outer_loop.py --iterations 10 --control control.txt
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
VARIANTS_DIR = os.path.join(REPO_ROOT, "governance", "meta_harness", "variants")
SNAPSHOT_ROOT = os.path.join(VARIANTS_DIR, "_snapshots")
# 2026-08-06 归属迁移: P1 血缘文件迁至 meta_harness/ (与引擎同目录),
# 避免命中工作区根被 AST Guard 内容污染的旧文件 (跨项目污染修复)。
META_HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
PARETO_FILE = os.path.join(META_HARNESS_DIR, "pareto_frontier.md")
FAILURE_FILE = os.path.join(META_HARNESS_DIR, "failure_analysis.md")

HARNESS_FILES = {
    "rules":   "governance/meta_language/simulation_rules.abdl",
    "mapping": "core/meta_language/abdl_action_bridge.py",
    "physics": "simulation/lightweight_env.py",
    "reward":  "simulation/reward_functions.py",
    "gate":    "simulation/v9_gate_evaluator.py",
    "action_map": "simulation/wheel_to_discrete.py",
}
# Sprint 30 M2.2: 拓扑变更有效性预检 (S29 候选 C no-op 教训编码)
from evaluator_diff_test import topology_precheck_report
THRESHOLD = 0.6          # V9 门
EVAL_EPISODES = 10       # 5 对手 x 2 局, 确定性种子

# 终止词 (meta-prompt §3)
HALT_WORDS = ("HALT", "STOP", "暂停优化", "结束本次循环")

# 运行环境检测: Windows python 需经 wsl 调用 gate (Windows venv 无 numpy);
# 若 outer_loop 本身已在 WSL 内运行 (子进程直接 python3), 则不套 wsl。
def _is_wsl() -> bool:
    return os.path.exists("/mnt/c") or os.environ.get("WSL_DISTRO_NAME")

PYTHON = "python3" if _is_wsl() else "wsl"
EVAL_CMD = (
    "cd {repo} && python3 governance/meta_harness/evaluator_v9.py "
    "--episodes {episodes} --tag {tag} --json {out}{diff_baseline}{layer_flag}"
)
# Sprint 18: 差分门禁基线信号文件 (快照状态评估产物, evaluator_v9 --diff-baseline 消费)
DIFF_BASELINE_FILE = "baseline_signal.json"

# --------------------------------------------------------------------------
# A4: --vision-insight auto (PM 2026-08-06 裁决: A3+A4 合并交付)
# EVAI-V1R Interpret/Execute: MCP 失败 -> 自动触发视觉洞察 -> confidence 门控
# --------------------------------------------------------------------------
VISION_TRIGGER_ERRORS = ("element_not_found", "target_unreachable")
VISION_INSIGHT_URL = os.environ.get("VISION_INSIGHT_URL", "http://127.0.0.1:8766/insight")
VISION_FRAMES_ROOT = os.path.join(REPO_ROOT, "docs", "vision_frames")
VISION_CONFIDENCE_GATE = 0.6   # PM 裁决: confidence < 0.6 丢弃洞察, 防模型编造
# PM 超时策略 (2026-08-06 A4_7B_COMPARE 批准): 60s -> 90s 默认 / 120s 容错
# 依据: 7b 热推理实测 74-84s <= 90s (3/3 通过门控 confidence=0.65)
VISION_TIMEOUT_S = 90
VISION_CAPTURE_TIMEOUT_S = 90  # vision_probe 帧抓取上限


def _run_eval(cmd: str) -> "subprocess.CompletedProcess":
    """在正确运行时环境中执行评估命令。

    encoding=utf-8: 修复 Windows 侧 text=True 用 cp950 解码 wsl 中文输出的崩溃
    (既有缺陷, ROUND 1-11 在 WSL 内跑未触发; Windows 直跑时必崩)。
    """
    if _is_wsl():
        # 已在 WSL: 直接 bash -c
        return subprocess.run(["bash", "-c", cmd], capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=3600)
    # Windows: 经 wsl 桥接
    return subprocess.run(["wsl", "-e", "bash", "-c", cmd],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=3600)


def _to_wsl_path(p: str) -> str:
    """Windows 绝对路径 -> WSL /mnt/<letter>/... (A4 从 Windows 侧跑 gate 评估用)。

    既有 EVAL_CMD 假定 REPO_ROOT 为 WSL 路径 (ROUND 1-11 在 WSL 内运行);
    Windows 直跑 outer_loop 时必须转换, 否则 bash 双引号内反斜杠被吞。
    """
    m = re.match(r"^([A-Za-z]):\\(.*)$", p)
    if m:
        return "/mnt/{}/{}".format(m.group(1).lower(),
                                   m.group(2).replace("\\", "/"))
    return p.replace("\\", "/")


def log(msg: str):
    print(f"[outer_loop {time.strftime('%H:%M:%S')}] {msg}", flush=True)


# --------------------------------------------------------------------------
# ① 快照
# --------------------------------------------------------------------------
def snapshot_harness(ts: str) -> str:
    snap_dir = os.path.join(SNAPSHOT_ROOT, ts)
    os.makedirs(snap_dir, exist_ok=True)
    for layer, rel in HARNESS_FILES.items():
        src = os.path.join(REPO_ROOT, rel)
        dst = os.path.join(snap_dir, os.path.basename(rel))
        if os.path.exists(src):
            shutil.copy2(src, dst)
        else:
            log(f"WARN snapshot: {rel} 不存在 (skip)")
    log(f"快照 -> {snap_dir}")
    return snap_dir


def restore_harness(snap_dir: str, layers=None):
    """从快照恢复指定层文件。"""
    layers = layers or HARNESS_FILES.keys()
    for layer in layers:
        rel = HARNESS_FILES[layer]
        src = os.path.join(snap_dir, os.path.basename(rel))
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(REPO_ROOT, rel))
    log(f"恢复 Harness (快照 {os.path.basename(snap_dir)})")


# --------------------------------------------------------------------------
# ② 变体应用/回滚
# --------------------------------------------------------------------------
def apply_precheck(variant: dict) -> tuple:
    """Sprint 19: apply 前 dry-run 预检 (PM 任务 3)。

    与 apply_variant 内部校验同语义, 但不写入文件。返回:
      (True, "")                                  预检通过
      (False, "锚点缺失: old 出现 0 次 (期望 1) -> ...")  预检失败 (可记录 apply_precheck_failed)
    作用: 候选 apply 失败可观察 — run_round 记录原因到 meta_decisions.jsonl,
    且不消耗评估预算 (FAIL 候选直接跳过, 不再进 evaluate_candidate)。
    """
    targets = [(variant["target_file"], variant["diff"])]
    for rel, pairs in (variant.get("extra_files") or {}).items():
        targets.append((HARNESS_FILES[rel] if rel in HARNESS_FILES else rel, pairs))
    allowed = set(HARNESS_FILES.values())
    for rel, _ in targets:
        norm = rel.replace("\\", "/")
        if norm not in allowed:
            return False, f"作用域越界: {norm} 不在写白名单"
    for rel, pairs in targets:
        path = os.path.join(REPO_ROOT, rel)
        if not os.path.exists(path):
            return False, f"目标文件缺失: {rel}"
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        for pair in pairs:
            old, new = pair.get("old", ""), pair.get("new", "")
            # Sprint 20 P1: 恒 False 模式检测 (运行时第二道防线, 先于锚点计数拦截)
            try:
                from variants import detect_always_false
                af_reason = detect_always_false(old, new)
                if af_reason:
                    return False, f"恒 False 模式: {af_reason}"
            except ImportError:  # 防御: 异常环境不阻断预检主流程
                pass
            expected = pair.get("expected", 1)
            n = text.count(old)
            if n != expected:
                return False, f"锚点计数 {n}!={expected} -> {old!r}"
    return True, ""


def apply_variant(variant: dict) -> bool:
    """应用变体 diff 到工作树; 每个 old 串必须恰好出现 1 次。

    组合变体 (extra_files) 可同时修改多个 Harness 文件 (如 ROUND 4
    mh_combined_002 = physics 动量 + rules FLANK 角度)。先全量校验再逐文件写入,
    避免部分应用 (原子性)。extra_files 的 key 为 layer 名 (如 "rules")。
    """
    targets = [(variant["target_file"], variant["diff"])]
    for rel, pairs in (variant.get("extra_files") or {}).items():
        targets.append((HARNESS_FILES[rel] if rel in HARNESS_FILES else rel, pairs))
    # P1-2: 写作用域强制 — 应用侧运行时校验 (生成侧 resolve_diff 已拦一道,
    # 此处为防御纵深, 防规则轨/外部注入绕过白名单)
    allowed = set(HARNESS_FILES.values())
    for rel, _ in targets:
        norm = rel.replace("\\", "/")
        if norm not in allowed:
            log(f"SCOPE-VIOLATION {variant['id']}: 目标 {norm} 不在写作用域白名单, 拒绝应用")
            return False
    # 第一遍: 校验所有文件所有 diff old 计数 (不写入)
    plans = []
    for rel, pairs in targets:
        path = os.path.join(REPO_ROOT, rel)
        if not os.path.exists(path):
            log(f"FAIL {variant['id']}: {rel} 不存在")
            return False
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        for pair in pairs:
            old, new = pair["old"], pair["new"]
            expected = pair.get("expected", 1)
            n = text.count(old)
            if n != expected:
                log(f"FAIL {variant['id']}: diff old 出现 {n} 次 (期望 {expected}) -> {old!r}")
                return False
        plans.append((path, text, pairs))
    # 第二遍: 写入
    for path, text, pairs in plans:
        for pair in pairs:
            text = text.replace(pair["old"], pair["new"])
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
    for rel, _ in targets:
        log(f"应用 {variant['id']} [{variant['layer']}] -> {rel}")
    return True


# --------------------------------------------------------------------------
# ③ 评估 (WSL evaluator_v9.py)
# --------------------------------------------------------------------------
def evaluate_candidate(variant: dict, workdir: str, ts: str, tag: str = None,
                       diff_baseline: str = None) -> dict:
    out = os.path.join(workdir, f"{variant['id']}_report.json")
    # Windows 直跑时 repo/out 必须转 WSL /mnt/<drive>/ 路径, 否则 bash cd 立即失败
    # (既有缺陷: ROUND 1-11 在 WSL 内跑未触发; Sprint 8 Windows 侧集成暴露)
    if _is_wsl():
        repo_cmd, out_cmd = REPO_ROOT, out
    else:
        repo_cmd, out_cmd = _to_wsl_path(REPO_ROOT), _to_wsl_path(out)
    # Sprint 18: 差分门禁 — 传基线信号文件时 evaluator_v9 内嵌 diff_verdict 判定,
    # 报告携带 diff_test 字段 (PASSED/REGRESSION/SUSPICIOUS/INCONCLUSIVE)
    # Sprint 24 M2: 注入候选所属层 (layer), evaluator_v9 启用多信号融合判定
    diff_flag = ""
    layer_flag = ""
    if diff_baseline:
        base_cmd = diff_baseline if _is_wsl() else _to_wsl_path(diff_baseline)
        diff_flag = f" --diff-baseline {base_cmd}"
        layer = variant.get("layer")
        if layer in ("rules", "mapping", "physics"):
            layer_flag = f" --layer {layer}"
    cmd = EVAL_CMD.format(repo=repo_cmd, episodes=EVAL_EPISODES,
                          tag=tag or variant["id"], out=out_cmd,
                          diff_baseline=diff_flag, layer_flag=layer_flag)
    t0 = time.monotonic()
    proc = _run_eval(cmd)
    wall = time.monotonic() - t0
    if proc.returncode not in (0, 1):
        log(f"EVAL ERROR {variant['id']}: exit {proc.returncode}")
        log(f"  stderr: {proc.stderr[-500:]}")
        return {"score": None, "passed": False, "error": proc.stderr[-500:],
                "cost": {"wall_s": round(wall, 1), "total_steps": None, "episodes": 0}}
    try:
        with open(out, "r", encoding="utf-8") as f:
            report = json.load(f)
    except (OSError, json.JSONDecodeError):
        report = {}
    return {
        "score": report.get("score"),
        "passed": bool(report.get("passed")),
        "cost": report.get("cost", {}),
        "trajectory": report.get("trajectory", {}),
        "wall_s": round(wall, 1),
        "gate_exit": proc.returncode,
        # Sprint 18: 差分门禁判定 (evaluator_v9 内嵌, 仅传 --diff-baseline 时存在)
        "diff_test": report.get("diff_test"),
    }


def _gen_baseline_signal(snapshot_dir: str, ts: str, args) -> str:
    """Sprint 18: 在快照状态 (未应用任何候选 diff) 评估一次, 生成差分基线信号文件。

    返回基线信号文件绝对路径; 评估失败时返回空串 (门禁降级为放行, 不阻断流程)。
    """
    # 伪变体: 不 apply, 直接评估当前工作树 (= 快照状态 = 差分测试的 baseline)
    fake = {"id": "baseline", "target_file": HARNESS_FILES["rules"],
            "diff": [{"old": "", "new": "", "expected": 0}]}
    _orig_apply = apply_variant
    globals()["apply_variant"] = lambda v: True
    try:
        base_res = evaluate_candidate(fake, snapshot_dir, ts, tag="baseline")
    finally:
        globals()["apply_variant"] = _orig_apply
    if base_res.get("score") is None:
        log("DIFF-GATE WARN: 基线评估失败, 本轮门禁降级为放行 (不阻断)")
        return ""
    # 从 MH 报告提取 gate 原始 episode_results (含行为指纹) 重组为基线信号
    eps = (base_res.get("trajectory") or {}).get("episode_results") or []
    if not eps:
        log("DIFF-GATE WARN: 基线评估无 episode_results, 门禁降级为放行")
        return ""
    try:
        from evaluator_diff_test import extract_signal
        signal = extract_signal({
            "winrate": base_res.get("score"),
            "total_episodes": len(eps),
            "episode_results": eps,
        })
    except Exception as e:  # pragma: no cover - 防御性
        log(f"DIFF-GATE WARN: 基线信号提取失败 {e}, 门禁降级为放行")
        return ""
    sig_path = os.path.join(snapshot_dir, DIFF_BASELINE_FILE)
    with open(sig_path, "w", encoding="utf-8") as f:
        json.dump({"mode": "baseline", "signal": signal,
                   "generated_at": ts, "episodes": EVAL_EPISODES},
                  f, ensure_ascii=False)
    log(f"DIFF-GATE: 基线信号就绪 winrate={signal.get('winrate')} "
        f"steps={signal.get('avg_steps')} episodes={len(eps)}")
    return sig_path


def _record_diff_decision(vdict: dict, result: dict, ts: str,
                          verdict: str, blocked: bool):
    """Sprint 18: 差分门禁裁决写入 meta_decisions.jsonl (diff_verdict/diff_blocked)。"""
    try:
        from meta_config import record_decision
        record_decision({
            "type": "diff_gate",
            "ts": ts,
            "variant_id": vdict["id"],
            "layer": vdict.get("layer"),
            "score": result.get("score"),
            "steps": (result.get("cost") or {}).get("total_steps"),
            "diff_verdict": verdict,
            "diff_blocked": blocked,
            "reason": (result.get("diff_test") or {}).get("reason", ""),
        })
    except Exception as e:  # pragma: no cover - 记录失败不阻断主流程
        log(f"DIFF-GATE WARN: meta_decisions 记录失败: {e}")


def _record_apply_precheck(vdict: dict, ts: str, reason: str):
    """Sprint 19: apply 预检失败写入 meta_decisions.jsonl (apply_precheck_failed)。

    PM 验收: meta_decisions.jsonl 含 apply_precheck_failed 记录 (后续追溯候选
    生成层缺陷 — 锚点缺失/多匹配/作用域越界)。reason 与 apply_precheck 返回值一致,
    确保"预检失败原因"可被后续诊断直接消费。
    """
    try:
        from meta_config import record_decision
        record_decision({
            "type": "apply_precheck_failed",
            "ts": ts,
            "variant_id": vdict["id"],
            "layer": vdict.get("layer"),
            "score": None,
            "steps": None,
            "reason": reason,
        })
    except Exception as e:  # pragma: no cover - 记录失败不阻断主流程
        log(f"PRECHECK WARN: meta_decisions 记录失败: {e}")


def _record_topo_precheck(vdict: dict, ts: str, reason: str):
    """Sprint 30 M2.2: 拓扑变更有效性预检失败写入 meta_decisions.jsonl。

    S29 教训 (候选 C): priority 300->350 未跨越邻居规则 -> 结构性 no-op。
    预检拦截的候选不消耗评估预算, 原因可追溯 (topo_precheck_failed)。
    """
    try:
        from meta_config import record_decision
        record_decision({
            "type": "topo_precheck_failed",
            "ts": ts,
            "variant_id": vdict["id"],
            "layer": vdict.get("layer"),
            "score": None,
            "steps": None,
            "reason": reason,
        })
    except Exception as e:  # pragma: no cover - 记录失败不阻断主流程
        log(f"TOPO-PRECHECK WARN: meta_decisions 记录失败: {e}")


# --------------------------------------------------------------------------
# ④ Pareto 更新
# --------------------------------------------------------------------------
def update_pareto(variant: dict, result: dict, ts: str):
    """把本轮结果追加到 pareto_frontier.md 的 TASK-005d 表。"""
    if not os.path.exists(PARETO_FILE):
        log("WARN pareto_frontier.md 不存在, 跳过写入")
        return
    with open(PARETO_FILE, "r", encoding="utf-8") as f:
        text = f.read()
    score = result.get("score")
    score_s = f"{score:.1f}" if score is not None else "?"
    passed_s = "PASS" if result.get("passed") else "FAIL"
    steps = (result.get("cost") or {}).get("total_steps")
    steps_s = str(steps) if steps is not None else "?"
    row = (f"| {variant['id']} (v={variant['layer']}, 血缘 {variant.get('parent', '?')}) "
           f"| 质量 {score_s} ({passed_s}) "
           f"| {steps_s} 步 "
           f"| 待裁决 ({ts}) |")
    # 插到 TASK-005d 表尾 (表以 "| 变体 | 质量/效率 | 日期 |" 为头, 找到最后一行后插入)
    marker = "TASK-005d Pareto"
    start = text.find(marker)
    if start < 0:
        log("WARN 未找到 TASK-005d Pareto 表, 追加到文件尾")
        text += f"\n{row}\n"
    else:
        # 找到表头后的第一个空行或非表格行, 在其前插入
        body = text[start:]
        lines = body.split("\n")
        insert_at = len(lines)
        for i, line in enumerate(lines):
            if i >= 2 and not line.strip().startswith("|"):
                insert_at = i
                break
        lines.insert(insert_at, row)
        text = text[:start] + "\n".join(lines)
    with open(PARETO_FILE, "w", encoding="utf-8") as f:
        f.write(text)
    log(f"Pareto 更新: {row}")


# --------------------------------------------------------------------------
# ⑤b 潜伏分数注册 (PM ROUND 9 架构指令: latent_score)
# --------------------------------------------------------------------------
def append_latent(variant: dict, result: dict, ts: str):
    """把"若以当前基线评估, 该变体会得多少分"写入 pareto_frontier.md 潜伏注册表。

    PM 架构指令: 潜伏变体早期识别 — 不需要等到新前沿出现才重新评估历史变体。
    每轮 auto-sweep / 每次 re-qualification sweep 的**非采纳候选**都记录于此。
    """
    if not os.path.exists(PARETO_FILE):
        log("WARN pareto_frontier.md 不存在, 跳过潜伏记录")
        return
    with open(PARETO_FILE, "r", encoding="utf-8") as f:
        text = f.read()
    score = result.get("score")
    score_s = f"{score:.1f}" if score is not None else "?"
    passed_s = "PASS" if result.get("passed") else "FAIL"
    steps = (result.get("cost") or {}).get("total_steps")
    steps_s = str(steps) if steps is not None else "?"
    row = (f"| {variant['id']} (v={variant['layer']}, 血缘 {variant.get('parent', '?')}) "
           f"| {score_s} ({passed_s}) | {steps_s} 步 | latent @ {ts} |")
    marker = "## 潜伏变体注册表 (latent_score)"
    if marker in text:
        # 追加到潜伏表尾 (第一个非表格行之前)
        body = text[text.find(marker):]
        lines = body.split("\n")
        insert_at = len(lines)
        for i, line in enumerate(lines):
            if i >= 3 and not line.strip().startswith("|"):
                insert_at = i
                break
        lines.insert(insert_at, row)
        text = text[:text.find(marker)] + "\n".join(lines)
    else:
        text += (f"\n## 潜伏变体注册表 (latent_score)\n"
                 f"记录「若以当前基线评估, 历史/未采纳变体会得多少分」 — 潜伏变体早期识别 "
                 f"(PM ROUND 9 架构指令, 配合 --auto-sweep)\n"
                 f"| 变体 | 质量 | 步数 | 评估基线 (ts) |\n"
                 f"|---|---|---|---|\n"
                 f"{row}\n")
    with open(PARETO_FILE, "w", encoding="utf-8") as f:
        f.write(text)
    log(f"潜伏分数: {row}")


# --------------------------------------------------------------------------
# ⑤ 自反思
# --------------------------------------------------------------------------
def append_reflection(variant: dict, result: dict, ts: str):
    """把本轮因果记录追加到 failure_analysis.md 的 BottleSumo 段。"""
    if not os.path.exists(FAILURE_FILE):
        log("WARN failure_analysis.md 不存在, 跳过自反思")
        return
    with open(FAILURE_FILE, "r", encoding="utf-8") as f:
        text = f.read()
    score = result.get("score")
    score_s = f"{score:.1f}" if score is not None else "?"
    entry = (
        f"\n### Meta-Harness 轮次记录 ({ts}) — {variant['id']}\n"
        f"- 假说: {variant['hypothesis']}\n"
        f"- 证据链: {', '.join(variant['evidence'])} | 血缘: {variant['bloodline']}\n"
        f"- 结果: score={score_s} passed={result.get('passed')} "
        f"(wall {result.get('wall_s')}s, steps {result.get('cost', {}).get('total_steps')})\n"
    )
    # 插到 "BottleSumo TASK-005d" 段内、文件已有的第一个 "## " 新段之前
    marker = "BottleSumo TASK-005d"
    start = text.find(marker)
    if start < 0:
        text += entry
    else:
        tail = text[start:]
        next_section = tail.find("\n## ", 10)
        if next_section < 0:
            text += entry
        else:
            pos = start + next_section
            text = text[:pos] + entry + text[pos:]
    with open(FAILURE_FILE, "w", encoding="utf-8") as f:
        f.write(text)
    log(f"自反思已追加 ({variant['id']})")


# --------------------------------------------------------------------------
# 终止检测
# --------------------------------------------------------------------------
def check_halt(control_file: str = None) -> bool:
    if control_file and os.path.exists(control_file):
        with open(control_file, "r", encoding="utf-8") as f:
            content = f.read().strip().upper()
        if content:
            return any(w.upper() in content for w in HALT_WORDS)
    return False


def finalize_pareto_status(ts: str, kept_ids: list):
    """把本轮 "待裁决 (ts)" 行更新为 帕累托前沿 / 被支配 (由 kept_ids 裁决)。"""
    if not os.path.exists(PARETO_FILE):
        return
    with open(PARETO_FILE, "r", encoding="utf-8") as f:
        text = f.read()
    marker = f"待裁决 ({ts})"
    if marker not in text:
        return
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if marker in line:
            if any(kid in line for kid in kept_ids):
                lines[i] = line.replace(f"| 待裁决 ({ts}) |", "| 帕累托前沿 |")
            else:
                lines[i] = line.replace(f"| 待裁决 ({ts}) |", "| 被支配 |")
    with open(PARETO_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    log(f"Pareto 状态裁决: {kept_ids or '无保留'} ({ts})")


# --------------------------------------------------------------------------
# 单轮主流程
# --------------------------------------------------------------------------
def run_round(round_no: int, ts: str, snapshot_dir: str, args) -> tuple:
    """执行一轮: 快照已由调用方完成; 生成 3 变体 -> 逐个应用/评估/恢复。

    Sprint 8 (MHA): --proposer code_agent 时改用本地 LLM 编码代理提议
    (code_agent_proposer.propose), 候选与规则模板同构 (Variant), 下游
    apply/evaluate/pareto 流程零改动。默认 rule 保持既有行为 (红线#3)。

    返回 (best_variant, best_result, kept_ids)
    """
    import variants

    proposer = getattr(args, "proposer", "rule")
    if proposer == "code_agent":
        import code_agent_proposer as cap
        log(f"=== ROUND {round_no} (ts={ts}) [proposer=code_agent] ===")
        mcp_txt = None
        if getattr(args, "mcp_integration", False):
            # Sprint 11: 经 MCP 协议调用三服务器构建增强上下文 (容错降级)
            import mcp_client
            try:
                ctx = mcp_client.build_mcp_context(
                    query=f"round {round_no}: 寻找提升门分数与效率的改进",
                    )
                mcp_txt = mcp_client.format_mcp_context(ctx)
                log(f"  [MCP] 增强上下文注入 {len(mcp_txt)} chars "
                    f"(env={bool(ctx['env_snapshot'])}, "
                    f"meta={bool(ctx['meta_config'])}, "
                    f"hyps={len(ctx['top_hypotheses'] or [])}, "
                    f"retrieved={bool(ctx['retrieved'])})")
            except Exception as e:
                log(f"  [MCP] 集成降级: {e} (继续基线流程)")
        candidates = cap.propose(model=args.proposer_model or cap.PROPOSER_MODEL,
                                 retriever=getattr(args, "retriever", None),
                                 meta_config=getattr(args, "meta_config_cfg", None),
                                 agent=getattr(args, "agent", False),
                                 mcp_context=mcp_txt)
        if not candidates:
            log("code_agent: 无有效候选 (LLM 提议全被校验拒绝或空), 跳过本轮")
            return None, None, []
    else:
        log(f"=== ROUND {round_no} (ts={ts}) ===")
        # Sprint 25 A1: max_per_layer 1->3 — S22 后每层多种子, S25 动态锚点
        # 修复后全部有效 (mapping seed_1/2 + physics seed_1/2/3); rules 层在
        # _seed_variants/_gen 内排除 (RULES CLOSED), 此处不必过滤。
        candidates = variants.generate_variants(max_per_layer=3, round_no=args.round or 1)
    if len(candidates) != 5:
        log(f"WARN 仅生成 {len(candidates)} 个候选 (期望 5: mapping×2 + physics×3, rules 排除)")
    if not candidates:
        log("FATAL: 无候选变体, 跳过本轮")
        return None, None, []

    results = []
    # Sprint 18: 差分门禁 (默认启用, --no-diff-gate 禁用) — 快照状态评估生成基线信号
    diff_gate_on = not getattr(args, "no_diff_gate", False)
    baseline_signal = None
    if diff_gate_on:
        baseline_signal = _gen_baseline_signal(snapshot_dir, ts, args)
    for v in candidates:
        if check_halt(args.control):
            log("检测到终止词, 提前停止")
            break
        vdict = v.to_dict()
        # Sprint 19: apply 前 dry-run 预检 — 失败记录 apply_precheck_failed
        # (原因可追溯: 锚点计数不匹配/作用域越界/目标缺失), 不消耗评估预算
        pc_ok, pc_reason = apply_precheck(vdict)
        if not pc_ok:
            _record_apply_precheck(vdict, ts, pc_reason)
            results.append((v, {"score": None, "passed": False, "precheck": pc_reason}, False))
            log(f"  PRECHECK-FAIL {vdict['id']} [{vdict['layer']}]: {pc_reason}")
            continue
        # Sprint 30 M2.2: 拓扑变更有效性预检 — 优先级重排未跨越邻居规则时,
        # resolve_top() 胜者集合不变 -> 结构性 no-op (S29 候选 C 同构),
        # 预检拦截不消耗评估预算 (仅 rules 层含 ABDL priority 语义)
        if vdict["layer"] == "rules":
            tp_ok, tp_reason = topology_precheck_report(vdict.get("diff") or [])
            if not tp_ok:
                _record_topo_precheck(vdict, ts, tp_reason)
                results.append((v, {"score": None, "passed": False,
                                    "precheck": tp_reason}, False))
                log(f"  TOPO-PRECHECK-FAIL {vdict['id']} [rules]: {tp_reason}")
                continue
        if not apply_variant(vdict):
            results.append((v, {"score": None, "passed": False}, False))
            continue
        # 评估 (tag 含轮次标签; Sprint 18: 传基线信号以触发差分门禁判定)
        tag = vdict["id"]
        if getattr(args, "tag", None):
            tag = f"{args.tag}_{vdict['id']}"
        result = evaluate_candidate(vdict, snapshot_dir, ts, tag=tag,
                                    diff_baseline=baseline_signal)
        # 恢复工作树到快照 (评估用隔离基线; 组合变体需恢复全部涉及层)
        layers = [vdict["layer"] if vdict["layer"] != "combined" else "physics"]
        for extra_layer in (vdict.get("extra_files") or {}).keys():
            layers.append(extra_layer)
        restore_harness(snapshot_dir, layers=layers)
        # Sprint 18: 差分门禁判定 (Pareto 保留前强制质量门, FP-MC-014/015 对策)
        #   PASSED -> 进入 Pareto 候选; REGRESSION -> 拒收; SUSPICIOUS -> 转人工
        #   (记录 meta_decisions.jsonl); INCONCLUSIVE -> 不入 Pareto (no-op)
        dt = result.get("diff_test") or {}
        diff_verdict = dt.get("verdict")
        if diff_gate_on and diff_verdict:
            blocked = diff_verdict in ("REGRESSION", "SUSPICIOUS", "INCONCLUSIVE")
            _record_diff_decision(vdict, result, ts, diff_verdict, blocked)
            if blocked:
                log(f"  DIFF-GATE BLOCKED {vdict['id']}: {diff_verdict} — "
                    f"{dt.get('reason', '')}")
                results.append((v, result, False))
                continue
            log(f"  DIFF-GATE PASSED {vdict['id']}: {dt.get('reason', '')}")
        results.append((v, result, True))
        log(f"  {vdict['id']} [{vdict['layer']}] -> "
            f"score={result.get('score')} passed={result.get('passed')} "
            f"steps={result.get('cost', {}).get('total_steps')}")

        # P1-2: 候选工作空间 gate_result.json 回写 (Filesystem Run Store 闭环)
        _ws = getattr(v, "workspace", "") or ""
        if _ws and os.path.isdir(_ws):
            try:
                with open(os.path.join(_ws, "gate_result.json"), "w",
                          encoding="utf-8") as _gf:
                    json.dump({"variant_id": vdict["id"],
                               "score": result.get("score"),
                               "passed": result.get("passed"),
                               "steps": (result.get("cost") or {}).get("total_steps"),
                               "gate_exit": result.get("gate_exit"),
                               "ts": time.strftime("%Y%m%d_%H%M%S")},
                              _gf, ensure_ascii=False, indent=2)
            except Exception as _e:
                log(f"  [P1-2] gate_result 回写失败: {_e}")

        # P0-V2 元认知闭环 (仅 code_agent 提议器): 假设->结果配对, 供下次提议注入
        if proposer == "code_agent":
            score = result.get("score")
            steps = (result.get("cost") or {}).get("total_steps")
            outcome = ("confirmed" if (score is not None and score >= 1.0 and not result.get("gate_exit"))
                       else "rejected")
            cap.record_hypothesis(v, outcome, {"winrate": score, "steps": steps})
            log(f"  [meta] 假设检验: {vdict['id']} -> {outcome}")

        # 突破性早期停止 (PM 裁决): 组合变体低于上一前沿 -> 立即停止后续对照评估
        # 每轮对照表: {round: (组合变体 id, 上一前沿步数)}
        _bt = {3: ("mh_combined_001", 290), 4: ("mh_combined_002", 288),
               5: ("mh_combined_003", 288), 6: ("mh_combined_004", 262),
               7: ("mh_combined_005", 259)}
        if (args.round in _bt and vdict["id"] == _bt[args.round][0]
                and (result.get("cost") or {}).get("total_steps") is not None
                and result["cost"]["total_steps"] < _bt[args.round][1]):
            log(f"BREAKTHROUGH: {vdict['id']} 步数 {result['cost']['total_steps']} < "
                f"{_bt[args.round][1]}, 已找到更强前沿, 停止后续对照评估 (PM 指令)")
            break

    # 选择最优 (Pareto 序: 质量优先, 同质量比步数)
    best = None
    for v, r, applied in results:
        if not applied or r.get("score") is None:
            continue
        r_steps = r.get("cost", {}).get("total_steps") or 10**9
        if best is None:
            best = (v, r)
            continue
        b_v, b_r = best
        b_steps = b_r.get("cost", {}).get("total_steps") or 10**9
        if r["score"] > b_r["score"] or (
            abs(r["score"] - b_r["score"]) < 1e-9 and r_steps < b_steps
        ):
            best = (v, r)
    return best, results, [r for _, r, applied in results if applied]


# --------------------------------------------------------------------------
# re-qualification sweep (ROUND 6-A 方法论教训: 跨基线交互增益)
# --------------------------------------------------------------------------
def run_sweep(args) -> int:
    """在改进基线下重扫变体注册表: 磁盘 diff 仍可应用的变体逐个重评估。

    动机 (ROUND 6-A): mh_mapping_001 在旧基线 (371) 被支配, 新基线 (286) 下
    262 步成为新前沿 — 线性逐轮保留会漏掉跨基线交互收益。物理轴已达 1.0
    硬上限, 相关变体由磁盘自适应守卫自动跳过。"""
    import variants as V

    log("=== RE-QUALIFICATION SWEEP (跨基线交互增益重扫) ===")
    ts = time.strftime("%Y%m%d_%H%M%S")
    snapshot_dir = snapshot_harness(ts)
    # 基线评估 (空 diff 伪变体复用 evaluate_candidate)
    fake = {"id": "sweep_baseline", "target_file": HARNESS_FILES["rules"],
            "diff": [{"old": "", "new": "", "expected": 0}]}
    _orig_apply = apply_variant

    def _noop_apply(v):
        return True

    globals()["apply_variant"] = _noop_apply
    try:
        base_res = evaluate_candidate(fake, snapshot_dir, ts, tag="sweep_baseline")
    finally:
        globals()["apply_variant"] = _orig_apply
    base_steps = (base_res.get("cost") or {}).get("total_steps")
    log(f"SWEEP 基线: {base_steps} 步 (score={base_res.get('score')})")

    # 收集注册表变体 (各轮计划, 按 target+diff 去重; 磁盘自适应跳过不匹配者)
    registry = {}
    seen = set()
    for n in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10):
        for v in V.generate_variants(max_per_layer=1, round_no=n):
            key = (v.target_file, tuple(sorted(p["old"] for p in v.diff)))
            if key not in seen:
                seen.add(key)
                registry[v.id] = v
    log(f"SWEEP 注册表: {len(registry)} 个候选 -> {sorted(registry)}")

    beats = []
    for v in registry.values():
        vdict = v.to_dict()
        if not apply_variant(vdict):
            log(f"SWEEP 跳过 {vdict['id']} (diff 不再匹配磁盘 — 已并入基线或被取代)")
            continue
        result = evaluate_candidate(vdict, snapshot_dir, ts,
                                    tag=f"sweep_{vdict['id']}")
        layers = [vdict["layer"] if vdict["layer"] != "combined" else "physics"]
        for extra_layer in (vdict.get("extra_files") or {}).keys():
            layers.append(extra_layer)
        restore_harness(snapshot_dir, layers=layers)
        steps = (result.get("cost") or {}).get("total_steps")
        score = result.get("score")
        log(f"  SWEEP {vdict['id']} [{vdict['layer']}] -> score={score} steps={steps}")
        if (steps is not None and score is not None and score >= THRESHOLD - 1e-9
                and steps < base_steps):
            beats.append((vdict["id"], vdict["layer"], steps, score))
            update_pareto(vdict, result, ts)
            append_reflection(vdict, result, ts)
        else:
            # PM ROUND 9 架构指令: 非采纳候选记录 latent_score (潜伏注册表)
            append_latent(vdict, result, ts)
    if beats:
        beats.sort(key=lambda x: x[2])
        best_id, best_layer, best_steps, best_score = beats[0]
        log(f"SWEEP BEAT: {best_id} = {best_steps} 步 < 基线 {base_steps} — 保留到工作树")
        apply_variant(registry[best_id].to_dict())
    else:
        log(f"SWEEP: 无变体击败基线 {base_steps} 步 — 注册表在当前基线下全部失效或被支配")
    return 0


# --------------------------------------------------------------------------
# TASK-005f 视觉干跑 (PM ROUND 11 裁决: RULES 引擎 CLOSED, 视觉通路验证)
# EVAI v1.0 R-I-C-E 四步法 — 本干跑仅验证 "Recognize" 阶段:
#   轻量环境状态 -> 合成相机帧 -> Rerun Web Viewer (:9090)
# --------------------------------------------------------------------------
VISION_PROBE_CMD = (
    "cd {repo} && python3 governance/meta_harness/vision_probe.py "
    "--profile {profile} --steps {steps} --hold {hold}"
)

def run_vision_probe(profile: str) -> int:
    """TASK-005f 干跑: 合成相机帧叠加到 :9090 (治理回归基线).

    连接现有 rerun --serve-web (:9876 gRPC / :9090 Web Viewer, 与 visualizer.py
    --web 同一画布)。不新建服务器、不生成规则候选。EVAI R-I-C-E:
      Recognize   — 感知张量 (edge 四向热区 + 对手向量) 叠加到帧上
      Interpret   — opp_dist/opp_angle 上下文 (TextLog)
      Command     — 本轮不选择新动作 (脚本策略仅演示视觉通路)
      Execute     — 帧差异由 Web Viewer 目视验证 (:9090 首帧)
    """
    log(f"=== TASK-005f VISION PROBE (EVAI R-I-C-E Recognize 干跑, profile={profile}) ===")
    ts = time.strftime("%Y%m%d_%H%M%S")
    cmd = VISION_PROBE_CMD.format(repo=REPO_ROOT, profile=profile,
                                  steps=30, hold=8)
    proc = _run_eval(cmd)
    out = (proc.stdout or "") + (proc.stderr or "")
    for line in out.splitlines():
        log(line)
    if proc.returncode != 0:
        log(f"VISION-PROBE 失败 rc={proc.returncode}")
        return proc.returncode
    # Execute 阶段: 帧差异验证 — Web Viewer :9090 必须仍在服务 (治理回归基线)
    log("VISION-PROBE 完成: 合成相机帧已推送 :9876 -> Web Viewer :9090")
    return 0

# --------------------------------------------------------------------------
# ④ A4: --vision-insight auto (PM 2026-08-06 裁决: A3+A4 合并交付)
# EVAI-V1R Interpret/Execute: MCP 失败 -> 自动触发视觉洞察 -> confidence 门控
# --------------------------------------------------------------------------
def _vision_capture_frame(out_dir: str, tag: str):
    """抓取一帧 (vision_probe --no-rerun 纯落盘), 返回最新 PNG 绝对路径或 None。

    异步语义: 调用方在后台线程执行; 本函数自身 90s 硬超时。
    """
    probe = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vision_probe.py")
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"   # Windows cp950 下中文 print 防崩
    cmd = [sys.executable, probe, "--profile", "aggressive",
           "--steps", "2", "--hold", "0",
           "--no-rerun", "--save-frames", out_dir, "--tag", tag]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=90,
                              env=env, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        log(f"VISION capture 超时 ({VISION_CAPTURE_TIMEOUT_S}s), 回退无视觉")
        return None
    if proc.returncode != 0:
        log(f"VISION capture 失败 rc={proc.returncode}: {(proc.stderr or '')[-200:]}")
        return None
    pngs = sorted(glob.glob(os.path.join(out_dir, "**", "*.png"), recursive=True))
    return pngs[-1] if pngs else None


def _vision_insight_from_frame(frame_path: str, out_dir: str, timeout: int,
                               model: str = None):
    """POST 帧 -> vision_proxy /insight -> 标准化 vision_insight JSON (含 confidence)。

    PM 超时裁决: 推理 > timeout (默认 60s) 抛异常 -> 调用方回退无视觉。
    model: 可选 — 请求级模型覆盖 (A4_7B_COMPARE 实验, 无需重启服务)。
    """
    import urllib.request
    payload = {
        "image": frame_path,
        "frame_name": os.path.basename(frame_path),
        "out_dir": out_dir,
    }
    if model:
        payload["model"] = model
    req = urllib.request.Request(VISION_INSIGHT_URL,
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def maybe_vision_insight(signal: str, out_dir: str, tag: str,
                         timeout: int = VISION_TIMEOUT_S,
                         model: str = None) -> dict:
    """A4 auto 模式核心: 仅当 MCP 失败信号命中触发集才调用视觉。

    返回:
      {"_drop": None, "confidence": float, "insight": dict}  -> 通过门控, 可注入 observation.vision
      {"_drop": reason, ...}                                  -> 丢弃 (capture_failed / insight_error /
                                                                  confidence_gate / timeout / no_trigger)

    约束 (PM): 视觉不修改动作选择逻辑 — 本函数只产出 observation 数据。
    """
    if signal not in VISION_TRIGGER_ERRORS:
        return {"_drop": "no_trigger", "signal": signal}   # auto 默认不调用视觉
    log(f"VISION-TRIGGER: MCP 信号 '{signal}' -> 自动触发视觉洞察 (EVAI Interpret/Execute)")

    def _work():
        frame = _vision_capture_frame(out_dir, tag)
        if not frame:
            return {"_drop": "capture_failed"}
        # insight 与帧同目录 (PM: 写入帧同目录 insight_<frame>.json; 各触发子目录独立不覆盖)
        frame_dir = os.path.dirname(frame)
        try:
            insight = _vision_insight_from_frame(frame, frame_dir, timeout, model)
        except Exception as e:
            log(f"VISION WARN: /insight 失败: {e} — 回退无视觉")
            return {"_drop": f"insight_error:{type(e).__name__}"}
        conf = insight.get("confidence", 0.0)
        if conf < VISION_CONFIDENCE_GATE:
            log(f"VISION WARN: confidence={conf} < 门控 {VISION_CONFIDENCE_GATE} — "
                f"丢弃该帧洞察 (防模型编造, PM 裁决)")
            return {"_drop": "confidence_gate", "confidence": conf, "insight": insight}
        log(f"VISION OK: confidence={conf} >= {VISION_CONFIDENCE_GATE} — "
            f"注入 observation.vision (不修改动作选择)")
        return {"_drop": None, "confidence": conf, "insight": insight}

    # 异步执行 (PM: 不阻塞 outer_loop 评估吞吐量) + 超时保护 (PM: >60s 放弃)
    with ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(_work)
        try:
            return fut.result(timeout=VISION_TIMEOUT_S + VISION_CAPTURE_TIMEOUT_S + 10)
        except Exception:
            log(f"VISION WARN: 视觉链路 > {VISION_TIMEOUT_S + VISION_CAPTURE_TIMEOUT_S}s — "
                f"放弃该帧洞察 (无视觉回退)")
            return {"_drop": "timeout"}


def run_vision_insight_auto(args) -> int:
    """A4 验收: gate 评估(门分数不变) + MCP 失败自动触发视觉 + confidence 门控。

    流程:
      1) 基线 gate 评估 (v9_gate_evaluator.py, episodes=args.episodes)
      2) 故障注入 N 次 MCP 失败信号 (element_not_found / target_unreachable 交替)
         -> 每次自动触发视觉通路 (抓帧 -> /insight -> confidence 门控)
      3) 复跑 gate 评估 -> 分数必须与基线一致 (视觉不触碰规则层)
      4) git diff 验证 5 个 Harness 文件零修改 (G3CA 工具优先铁证)

    产物: docs/vision_frames/<TAG>_<ts>/ (帧 PNG + insight_*.json + gate 报告)
    """
    ts = time.strftime("%Y%m%d_%H%M%S")
    tag = args.tag or "A4_VERIFY"
    timeout = args.timeout
    model = args.model
    base_dir = os.path.join(VISION_FRAMES_ROOT, f"{tag}_{ts}")
    os.makedirs(base_dir, exist_ok=True)
    log(f"=== A4 vision-insight auto 验收 (tag={tag}, episodes={args.episodes}, "
        f"fault_inject={args.vision_fault_inject}, model={model or 'default'}, "
        f"timeout={timeout}s) ===")

    # 1) 基线 gate 评估 (Windows 直跑时 repo/out 需转 WSL 路径, 见 _to_wsl_path)
    gate_out = os.path.join(base_dir, "gate_baseline.json")
    cmd = EVAL_CMD.format(repo=_to_wsl_path(REPO_ROOT), episodes=args.episodes,
                          tag=f"{tag}_gate", out=_to_wsl_path(gate_out))
    log("A4 [1/4] 基线: v9_gate_evaluator.py (规则层, 无视觉)")
    proc = _run_eval(cmd)
    base = {}
    try:
        with open(gate_out, "r", encoding="utf-8") as f:
            base = json.load(f)
    except (OSError, json.JSONDecodeError):
        log(f"A4 基线 gate 报告不可读 rc={proc.returncode}: {(proc.stderr or '')[-300:]}")
    base_score = base.get("score")
    base_steps = (base.get("cost") or {}).get("total_steps")
    log(f"A4 基线: score={base_score} steps={base_steps}")

    # 2) 故障注入 -> 自动触发视觉 (auto 模式语义验证)
    n = args.vision_fault_inject
    log(f"A4 [2/4] 故障注入: {n} 次 MCP 失败信号 -> 自动触发视觉洞察")
    signals = (["element_not_found", "target_unreachable"]
               * (n // 2 + 1))[:n]
    drops, keeps = [], 0
    for i, sig in enumerate(signals):
        res = maybe_vision_insight(sig, base_dir, f"A4F{i}", timeout=timeout, model=model)
        if res.get("_drop") is None:
            keeps += 1
        else:
            drops.append((res["_drop"], sig))

    # 3) 复跑 gate 评估 (门分数不变验证)
    gate_out2 = os.path.join(base_dir, "gate_post.json")
    cmd2 = EVAL_CMD.format(repo=_to_wsl_path(REPO_ROOT), episodes=args.episodes,
                           tag=f"{tag}_gate_post", out=_to_wsl_path(gate_out2))
    log("A4 [3/4] 复跑: v9_gate_evaluator.py (视觉活动后)")
    proc2 = _run_eval(cmd2)
    post = {}
    try:
        with open(gate_out2, "r", encoding="utf-8") as f:
            post = json.load(f)
    except (OSError, json.JSONDecodeError):
        log(f"A4 复跑 gate 报告不可读 rc={proc2.returncode}: {(proc2.stderr or '')[-300:]}")
    post_score = post.get("score")
    unchanged = (base_score is not None and base_score == post_score)

    # 4) Harness 零修改验证 (视觉绝不触碰规则层)
    diff = subprocess.run(
        ["git", "-C", REPO_ROOT, "diff", "--stat", "--", *list(HARNESS_FILES.values())],
        capture_output=True, text=True)
    harness_dirty = bool(diff.stdout.strip())
    if harness_dirty:
        log(f"A4 !! Harness 被修改: {diff.stdout}")
    else:
        log("A4 [4/4] Harness diff: 零修改 (视觉未触碰规则层, G3CA 工具优先 ✓)")

    # 5) Phase B (PM 2026-08-06 批准): _apply_vision_softening 单元矩阵
    #    tag == PHASE_B_ACCEPT 时追加; 3 轮复现稳定 + 门分数/步数对比。
    softening_pass = True
    if tag == "PHASE_B_ACCEPT":
        try:
            sys.path.insert(0, REPO_ROOT)
            from governance.meta_harness.phase_b_accept import run_softening_matrix
            log("A4 [5/5] Phase B: _apply_vision_softening 单元矩阵 (3 轮)")
            sm = run_softening_matrix(base_dir, rounds=3)
            softening_pass = sm.get("all_pass", False)
            log(f"A4 Phase B 软化矩阵: all_pass={softening_pass} "
                f"(rounds={sm.get('rounds')}, cases={sm.get('total_cases')})")
        except Exception as e:
            log(f"A4 Phase B 软化矩阵失败: {e}")
            softening_pass = False

    # 汇总
    ins = sorted(glob.glob(os.path.join(base_dir, "**", "insight_*.json"), recursive=True))
    log(f"A4 汇总: gate score 基线={base_score} 复跑={post_score} "
        f"{'一致 ✓ (门分数不变)' if unchanged else '!! 不一致'}")
    log(f"A4 汇总: 洞察 keeps={keeps}, drops={drops}")
    log(f"A4 汇总: 洞察文件={len(ins)} -> {base_dir}")
    if not harness_dirty and unchanged and softening_pass:
        log("A4 验收 PASS: 自动触发 ✓ 洞察落盘 ✓ 门分数不变 ✓ 软化矩阵 ✓")
        return 0
    log("A4 验收 FAIL")
    return 1

# --------------------------------------------------------------------------
# 主入口
# --------------------------------------------------------------------------
def main() -> int:
    # Windows cp950 控制台修复: 强制 UTF-8 (argparse help/中文日志)
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="BottleSumo Meta-Harness 外环编排器 (P1)")
    ap.add_argument("--iterations", type=int, default=1, help="循环轮数 (MAX_ITERATIONS)")
    ap.add_argument("--fresh", action="store_true",
                    help="先把 5 个 Harness 文件恢复到 git HEAD, 再开始")
    ap.add_argument("--baseline", nargs="?", const=True, type=int, default=None,
                    help="自动回滚: 无参数=步数反弹即回滚; --baseline N=步数 > N 时回滚")
    ap.add_argument("--control", default=None, help="控制文件路径 (写入 HALT 即终止)")
    ap.add_argument("--tag", default=None, help="轮次标签 (如 ROUND2), 写入评估与日志")
    ap.add_argument("--no-diff-gate", action="store_true",
                    help="Sprint 18: 禁用差分门禁 (默认启用 — 候选 diff 应用后自动 "
                         "baseline->diff 对比; REGRESSION 拒收 / SUSPICIOUS 转人工 / "
                         "INCONCLUSIVE 不入 Pareto, 仅 PASSED 进入保留流程)")
    ap.add_argument("--round", type=int, default=None,
                    help="变体计划: 1=规则/映射/物理各1; 2=物理二分(0.875/0.90)+Circler规则; "
                         "3=正交组合+对照(0.95/12°); 4=精细化搜索(14°+0.89 双文件微扰); "
                         "5=动量0.95+角度13°阶梯延续; 6=动量1.0硬上限+角度12°平台边缘; "
                         "7=新正交轴延续+平台期外探针; 8=角度下探 (PM 裁决 2A)")
    ap.add_argument("--sweep", action="store_true",
                    help="re-qualification sweep: 重扫变体注册表 (ROUND 6-A 方法论)")
    ap.add_argument("--auto-sweep", action="store_true",
                    help="PM ROUND 9 架构指令: 每轮迭代末尾轻量重扫本轮未采用候选, 记录 latent_score "
                         "(潜伏变体早期识别, 无需等待新前沿)")
    ap.add_argument("--clamp", action="store_true",
                    help="MFHS v1.0 D4 边界自限: 超物理边界候选 (动量>1.0, 角度<5°) 自动裁剪到边界值")
    ap.add_argument("--vision-probe", nargs="?", const="aggressive", default=None,
                    metavar="PROFILE",
                    help="TASK-005f 视觉干跑 (EVAI v1.0 R-I-C-E): 将 lightweight_env 合成相机帧"
                         "叠加到 Rerun Web Viewer (:9090). PROFILE ∈ {aggressive, circler, defensive}"
                         "(默认 aggressive). RULES 引擎已关闭 — 本标志不生成任何规则候选, 仅验证视觉通路.")
    ap.add_argument("--vision-insight", choices=["auto", "off"], default=None,
                    help="A4 (PM 2026-08-06): auto=仅当 MCP 工具失败(element_not_found/"
                         "target_unreachable)时自动触发视觉洞察; observation-only — 洞察注入 "
                         "observation.vision, 不修改动作选择; confidence<0.6 丢弃(WARN); "
                         "推理>60s 放弃回退无视觉 (默认不调用视觉)")
    ap.add_argument("--episodes", type=int, default=EVAL_EPISODES,
                    help="A4 验收评估局数 (默认 {})".format(EVAL_EPISODES))
    ap.add_argument("--vision-fault-inject", type=int, default=3,
                    help="A4 验收: 注入 N 次合成 MCP 失败信号演示自动触发 (默认 3)")
    ap.add_argument("--model", default=None,
                    help="A4 对比实验: 请求级覆盖视觉模型 (如 qwen2.5vl:7b), "
                         "默认用 vision_proxy 当前模型")
    ap.add_argument("--timeout", type=int, default=VISION_TIMEOUT_S,
                    help="A4 视觉推理超时 (默认 {}s — PM 2026-08-06 批准 90s, 7b 热实测 74-84s; "
                         "容错上限 120s)".format(VISION_TIMEOUT_S))
    # Sprint 8 (MHA 增强): 提议器选择 — rule=规则模板 (既有默认, 零行为变化),
    # code_agent=本地 LLM 编码代理 (MHA-ARCH P0-V1, 斯坦福原版核心复刻)
    ap.add_argument("--proposer", choices=["rule", "code_agent"], default="rule",
                    help="Sprint 8 MHA: 候选生成器 (默认 rule=既有规则模板; "
                         "code_agent=本地 Ollama 编码代理)")
    ap.add_argument("--proposer-model", default=None,
                    help="code_agent 提议器模型 (默认 qwen2.5:7b, 见 PROPOSER_MODEL)")
    ap.add_argument("--retriever", choices=["bge-m3"], default=None,
                    help="P1-V3 语义检索: bge-m3 检索历史经验 (failure/pareto/hypotheses) "
                         "注入编码代理系统提示 (默认 None=P0 基线行为)")
    ap.add_argument("--meta-config", action="store_true",
                    help="P2-V4 自指改进: 连续 2 轮无效候选时自动调整提议器参数 "
                         "(温度降 0.1 / 检索阈值提 0.05 / 目标文件优先级切换), "
                         "裁决历史写入 meta_decisions.jsonl")
    ap.add_argument("--agent", action="store_true",
                    help="P0 对齐 (编码代理自主推理): 环境引导快照注入系统提示 + "
                         "1 次受限只读工具轮 (read_file/list_dir/git_status), "
                         "LLM 自主决定读取文件获取完整源码后生成候选; "
                         "默认 False = 既有行为 (零回归)")
    ap.add_argument("--no-mcp-integration", dest="mcp_integration",
                    action="store_false", default=True,
                    help="Sprint 11 (MCP 实际集成): 默认启用 — 经 MCP 协议调用三服务器 "
                         "(meta_cognition/semantic_retrieval/environment_bootstrap) "
                         "构建增强上下文注入 code_agent 提议; "
                         "加 --no-mcp-integration 显式禁用 (回归基准)")
    ap.add_argument("--symbolic-verify", action="store_true",
                    help="Sprint 35 T1 (Z3 符号验证): 预检链启用第四层防护 — "
                         "对每个候选 diff 验证联合覆盖包含关系 (S32 单维投影盲区), "
                         "新增联合空洞 -> SYMBOLIC_PROOF_FAIL 拦截")
    ap.add_argument("--meta-bootstrap", action="store_true",
                    help="META-BOOTSTRAP v1.0 (元能力自举器): 与 --assess/--evolve 组合 — "
                         "A.S.C.E.N.D. 五维评估与元能力改进 (见 meta_prompts/meta_bootstrap_v1.md)")
    ap.add_argument("--assess", action="store_true",
                    help="meta-bootstrap Phase A: 生成 meta_capability_scorecard.md")
    ap.add_argument("--evolve", action="store_true",
                    help="meta-bootstrap Phase S-D: 选择改进项 -> 实施 -> 验证 -> 固化 -> 记录")
    ap.add_argument("--honest", action="store_true",
                    help="HONEST-BOUNDARY v1.0: 四维边界扫描与声明 (boundary_scan.py)")
    ap.add_argument("--meta-architect", action="store_true",
                    help="META-ARCHITECT v1.0: 导出系统架构描述 (meta_architect.py)")
    ap.add_argument("--export", action="store_true",
                    help="meta-architect: 执行导出 (markdown/json/mermaid)")
    ap.add_argument("--task", default=None,
                    help="honest: 任务描述 (记录于 boundary_manifest)")
    ap.add_argument("--meta-kb", action="store_true",
                    help="META-KB v1.0: 元教育知识库迁移流水线 (meta_kb.py, R.E.A.D. 四步法) — "
                         "需 --url; 生成 migration_report/sync_status")
    ap.add_argument("--url", default=None,
                    help="meta-kb/meta-edu: 目标链接 (Notion 等)")
    ap.add_argument("--meta-edu", action="store_true",
                    help="MEF-OS v1.0: 元教育闭环 (MCE 编译 -> VCE 扫描 -> CEE 推演 -> TRACE 归档) — "
                         "对指定 URL/任务执行认知编译循环")
    args = ap.parse_args()

    # META-BOOTSTRAP 分发 (元能力自举优先于领域运行; 不触碰 P1 主链路)
    if args.meta_bootstrap:
        import meta_bootstrap
        if args.assess:
            return meta_bootstrap.assess(args.tag)
        if args.evolve:
            return meta_bootstrap.evolve(max(1, args.iterations), args.tag)
        print("--meta-bootstrap 需要 --assess 或 --evolve")
        return 2
    # HONEST-BOUNDARY 分发 (诚实边界扫描/声明)
    if args.honest:
        import sys as _sys
        _sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "trace"))
        import boundary_scan
        return boundary_scan.cmd_report(args.tag)
    # META-ARCHITECT 分发 (元架构导出)
    if args.meta_architect:
        import meta_architect
        if args.export:
            return meta_architect.export(args.tag)
        print("--meta-architect 需要 --export")
        return 2
    # META-KB 分发 (元教育知识库迁移, R.E.A.D. 四步法)
    if args.meta_kb:
        import meta_kb
        if args.url:
            return meta_kb.main_args(args.url, args.tag)
        if args.tag and not args.url:
            # 无 URL: 仅输出同步状态
            return meta_kb.main_status()
        print("--meta-kb 需要 --url (如 --url \"https://app.notion.com/p/xxx\")")
        return 2
    # META-EDU 分发 (MEF-OS 元教育闭环: MCE -> VCE -> CEE -> TRACE)
    if args.meta_edu:
        import meta_edu
        return meta_edu.run_loop(args.url, args.tag)

    # 从 --tag 自动推断轮次计划 (PM 命令: --tag ROUND2)
    if args.round is None and args.tag:
        t = args.tag.upper()
        for n in ("2", "3", "4", "5", "6", "7", "8", "9", "10"):
            if f"ROUND{n}" in t:
                args.round = int(n)
                break
    if args.round is None:
        args.round = 1
    log(f"变体计划: ROUND {args.round} (tag={args.tag or 'none'})")

    if args.fresh:
        log("--fresh: 恢复 5 个 Harness 文件到 HEAD")
        files = [os.path.join(REPO_ROOT, rel) for rel in HARNESS_FILES.values()]
        subprocess.run(["git", "-C", REPO_ROOT, "checkout", "--", *files],
                       check=False)

    # 读取当前最优 (variants.py 的血缘解析)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import variants
    pareto = variants.load_pareto()
    current_best = pareto.get("current_best", "1.0")
    log(f"当前 Pareto 最优: {current_best}")

    # 基线效率: 在未改动的 Harness 上跑一次确定性评估, 作为效率轴参照
    if args.fresh:
        log("--fresh: 基线评估 (效率轴参照)")
        bs = variants.generate_variants(max_per_layer=1)
        # 直接跑 gate: 构造一个空 diff 的伪变体以复用 evaluate_candidate
        ts0 = time.strftime("%Y%m%d_%H%M%S")
        snap0 = snapshot_harness(ts0)
        fake = {"id": "baseline", "target_file": HARNESS_FILES["rules"],
                "diff": [{"old": "", "new": "", "expected": 0}]}
        # expected=0 表示不替换任何内容; apply_variant 需处理
        _orig_apply = apply_variant

        def _noop_apply(v):
            return True
        globals()["apply_variant"] = _noop_apply
        try:
            base_res = evaluate_candidate(fake, snap0, ts0)
        finally:
            globals()["apply_variant"] = _orig_apply
        args._baseline_steps = (base_res.get("cost") or {}).get("total_steps")
        log(f"基线效率: {args._baseline_steps} 步 (score={base_res.get('score')})")

    if args.sweep:
        return run_sweep(args)

    # TASK-005f 视觉干跑 (PM ROUND 11 裁决): EVAI R-I-C-E Recognize 阶段验证
    # RULES 引擎已宣告 CLOSED (214 步前沿) — 本路径不触碰任何规则候选, 仅验证视觉通路
    if args.vision_probe:
        return run_vision_probe(args.vision_probe)

    # A4: vision-insight auto 模式 (PM 2026-08-06 裁决: A3+A4 合并交付)
    # auto = 默认不调用视觉; 仅当 MCP 工具失败时自动触发; observation-only, 不改动作选择
    if args.vision_insight == "auto":
        return run_vision_insight_auto(args)

    saturated_rounds = 0
    all_kept = []
    sub_1_0_streak = 0      # PM ROUND2 硬停止: 连续 2 变体 score < 1.0 -> 冻结物理层
    step_bounce = 0         # PM ROUND2 硬停止: 步数反弹 > 370 -> 回滚至 0.85

    # P2-V4 自指改进: meta_config 门裁决 (连续 2 轮无效 -> 自动调整提议器参数)
    meta_cfg = None
    round_outcomes = []
    if args.meta_config:
        from meta_config import evaluate_round, load_meta_config
        meta_cfg = load_meta_config()
        log(f"P2-V4 meta_config 启用: temp={meta_cfg['temperature']} "
            f"retrieval_threshold={meta_cfg['retrieval_threshold']} "
            f"target_priority={meta_cfg['target_priority']}")
        args.meta_config_cfg = meta_cfg

    # Sprint 15 (MAA-ARCH + FSCL-ARCH): 元认知监控/Gap Function/CellLearner
    # C1: MetaMonitor 检测 stagnation/loop_detected/latency_anomaly
    # C2: Gap Function delta -> continue/adjust/switch_strategy
    # C3: CellLearner 触发器 -> 规则沉淀 + 参数自适应
    from cell_learner import CellLearner
    from gap_function import compute_delta, respond
    from meta_monitor import MetaMonitor

    meta_monitor = MetaMonitor()
    cell_learner = CellLearner()
    log("MAA-ARCH MetaMonitor + GapFunction + FSCL CellLearner 已初始化 (Sprint 15)")
    args._round_wall_s = None

    for round_no in range(1, args.iterations + 1):
        if check_halt(args.control):
            log("终止词触发, 停止")
            break
        if args.round >= 2 and sub_1_0_streak >= 2:
            log("PM 硬停止: 连续 2 变体 score < 1.0, 冻结物理层探索 (仅观察模式)")
            break
        ts = time.strftime("%Y%m%d_%H%M%S")
        _round_t0 = time.monotonic()   # Sprint 15: 轮计时 (latency_anomaly 触发器)
        snapshot_dir = snapshot_harness(ts)

        best, results, applied = run_round(round_no, ts, snapshot_dir, args)
        args._round_wall_s = time.monotonic() - _round_t0
        if best is None:
            log(f"ROUND {round_no}: 无有效结果")
            saturated_rounds += 1
            # Sprint 15: 无结果轮也送入 MetaMonitor (MAA-ARCH: 不忽略任何信号)
            if meta_monitor is not None:
                triggers = meta_monitor.analyze_iteration(
                    round_no=round_no,
                    variant_id=None,
                    score=None,
                    steps=None,
                    wall_s=args._round_wall_s,
                    kept=False,
                )
                if triggers:
                    log(f"META MONITOR: 触发器 {[t['trigger'] for t in triggers]} "
                        f"@ 轮 {round_no} (无结果)")
                if cell_learner is not None:
                    new_rules = cell_learner.learn_from_triggers(triggers)
                    if new_rules:
                        log(f"CELL LEARN: 沉淀 {len(new_rules)} 条规则")
            if meta_cfg:
                round_outcomes.append({"variant": None, "score": None, "steps": None})
                dec = evaluate_round(round_outcomes, meta_cfg)
                if dec:
                    a = dec["adjustments"]
                    log(f"P2-V4 门裁决触发 (连续2轮无效): temp {a['temperature']['from']}->{a['temperature']['to']} "
                        f"| threshold {a['retrieval_threshold']['from']}->{a['retrieval_threshold']['to']} "
                        f"| target {a['target_priority']['to']}")
                    args.meta_config_cfg = meta_cfg
            if saturated_rounds >= 3:
                log("探索饱和 (3 轮无有效结果), 停止")
                break
            continue

        v, r = best
        vdict = v.to_dict()

        # P2-V4: 记录本轮结果并检查门裁决 (连续 2 轮无效 -> 触发参数调整)
        if meta_cfg:
            round_outcomes.append({
                "variant": vdict.get("id"),
                "score": r.get("score"),
                "steps": r.get("cost", {}).get("total_steps"),
            })
            dec = evaluate_round(round_outcomes, meta_cfg)
            if dec:
                a = dec["adjustments"]
                log(f"P2-V4 门裁决触发 (连续2轮无效): temp {a['temperature']['from']}->{a['temperature']['to']} "
                    f"| threshold {a['retrieval_threshold']['from']}->{a['retrieval_threshold']['to']} "
                    f"| target {a['target_priority']['to']}")
                args.meta_config_cfg = meta_cfg

        # Pareto 更新 + 自反思 (所有被评估的候选都记录, 含失败 — 失败也是知识)
        for cand, res, app in results:
            if app:
                update_pareto(cand.to_dict(), res, ts)
                append_reflection(cand.to_dict(), res, ts)

        # PM ROUND 3 硬停止条件: 步数反弹 > 370
        cand_steps = r.get("cost", {}).get("total_steps")
        if cand_steps and cand_steps > 370 and args.round >= 2:
            step_bounce += 1
            log(f"PM 硬停止信号: {vdict['id']} 步数 {cand_steps} > 370, 自动回滚至 0.85")
            restore_harness(snapshot_dir)
            if step_bounce >= 2:
                log("步数反弹 2 次, 冻结物理层, 回滚基线")
                break

        # 组合变体协同效应日志 (诚实报告: 不预设乘法假设, ROUND 3 实证为弱加性)
        # 对照表: {组合变体 id: 上一前沿步数}
        _syn = {"mh_combined_001": 290, "mh_combined_002": 288, "mh_combined_003": 288,
                "mh_combined_004": 286}
        if vdict["id"] in _syn and cand_steps:
            prev = _syn[vdict["id"]]
            delta = cand_steps - prev
            if delta > 0:
                log(f"SYNERGY: {vdict['id']} 步数 {cand_steps} > 上一前沿 {prev} (+{delta}) — "
                    f"负协同, 触发归因分析")
            elif delta < 0:
                log(f"SYNERGY: {vdict['id']} 步数 {cand_steps} < 上一前沿 {prev} ({delta}) — "
                    f"正增益, 保留候选 (注: 实测为加性贡献, 非乘法放大)")
            else:
                log(f"SYNERGY: {vdict['id']} 步数 {cand_steps} = 上一前沿 {prev} — 持平")
        # 物理梯度延续日志: 动量变体步数 vs 360 参照; 1.0 为硬上限
        if v.layer == "physics" and cand_steps:
            m_new = re.search(r"TIMESTEP \* (\d+(?:\.\d+)?)", vdict["diff"][0]["new"])
            new_coef = float(m_new.group(1)) if m_new else 0.0
            if new_coef >= 1.0:
                log(f"PHYSICS CAP: {vdict['id']} 步数 {cand_steps} 在动量硬上限 1.0 处 — "
                    f"动量轴已穷尽, 若边际 <1% 则触发 TASK-005f 视觉解冻评估条件 (PM 裁决 2)")
            elif cand_steps < 360:
                log(f"PHYSICS TREND: {vdict['id']} 步数 {cand_steps} < 360 — "
                    f"动量单调延续, 建议后续向 1.0 推进 (硬上限)")
            else:
                log(f"PHYSICS PEAK: {vdict['id']} 步数 {cand_steps} >= 360 — "
                    f"0.90 附近存在收益拐点, 物理梯度应停止")

        # 连续 < 1.0 计数 (物理层)
        if args.round >= 2 and v.layer == "physics" and (r.get("score") or 0.0) < 1.0 - 1e-9:
            sub_1_0_streak += 1
        elif v.layer != "physics":
            sub_1_0_streak = 0

        score = r.get("score") or 0.0
        # 当前最优从血缘解析 (如 "**1.0 (10/10)**" 或 "1.0"), 剥离 markdown
        best_raw = str(current_best).replace("*", "").strip().split()[0] if current_best else "0"
        try:
            baseline_score = float(best_raw)
        except ValueError:
            baseline_score = 0.0
        baseline_steps = getattr(args, "_baseline_steps", None) or 10**9
        steps = r.get("cost", {}).get("total_steps") or 10**9

        # Pareto 提升判定 (质量轴 + 效率轴):
        #   质量更高 -> 保留;  质量持平但步数更少 -> 保留 (效率 Pareto 前沿)
        quality_beat = score > baseline_score + 1e-9
        efficiency_beat = (abs(score - baseline_score) < 1e-9) and (steps < baseline_steps)
        if (quality_beat or efficiency_beat) and score >= THRESHOLD - 1e-9:
            tag = "质量提升" if quality_beat else "效率提升(同质量更少步)"
            log(f"ROUND {round_no}: {vdict['id']} {tag} "
                f"(score {score} vs {baseline_score}, steps {steps} vs {baseline_steps}), 保留")
            apply_variant(vdict)  # 重新应用最优变体到工作树
            all_kept.append(vdict["id"])
            current_best = f"{score:.1f} ({vdict['id']}, {steps}步)"
            saturated_rounds = 0
            finalize_pareto_status(ts, all_kept)
        else:
            if args.baseline:
                log(f"ROUND {round_no}: {vdict['id']} score={score} < 基线 "
                    f"{baseline_score}, --baseline 自动回滚")
                restore_harness(snapshot_dir)
            else:
                log(f"ROUND {round_no}: {vdict['id']} score={score} 未超基线 "
                    f"{baseline_score}, 不保留 (工作树已恢复)")
            saturated_rounds += 1
            finalize_pareto_status(ts, all_kept)

        # ---- MAA-ARCH Phase M/A/R: 元认知监控 + Gap Function 响应 (Sprint 15) ----
        # 每轮末尾: MetaMonitor 检测触发器 -> GapFunction 策略路由 -> CellLearner 学习
        if meta_monitor is not None:
            wall_s = getattr(args, "_round_wall_s", None)
            kept = (quality_beat or efficiency_beat) and score >= THRESHOLD - 1e-9
            triggers = meta_monitor.analyze_iteration(
                round_no=round_no,
                variant_id=vdict["id"],
                score=score,
                steps=steps if steps != 10**9 else None,
                wall_s=wall_s,
                kept=kept,
            )
            if triggers:
                trigger_names = [t["trigger"] for t in triggers]
                log(f"META MONITOR: 触发器 {trigger_names} @ 轮 {round_no}")
                # Gap Function: delta -> 策略 (仅非 kept 轮, 单轮至多 1 次调整)
                if not kept and meta_cfg is not None:
                    delta = compute_delta(score, steps if steps != 10**9 else None)
                    decision = respond(delta, meta_cfg)
                    if decision:
                        log(f"GAP FUNCTION: delta={delta['magnitude']} -> "
                            f"{decision['strategy']} ({decision['action']})")
                # CellLearner: 触发器 -> 规则沉淀 + 参数自适应
                if cell_learner is not None:
                    new_rules = cell_learner.learn_from_triggers(triggers)
                    if new_rules:
                        log(f"CELL LEARN: 沉淀 {len(new_rules)} 条规则")
                    if meta_cfg is not None:
                        cell_learner.adapt_params(meta_cfg, triggers)

        # 饱和终止: 3 轮连续低于 Pareto 最优 且 无新缺陷类别 (简化: 以胜率无提升为准)
        if saturated_rounds >= 3:
            log("探索饱和 (连续 3 轮无 Pareto 提升), 停止")
            break

        # PM ROUND 9 架构指令: --auto-sweep — 每轮末尾轻量重扫未采用候选, 记录 latent_score
        # (潜伏变体早期识别: 不需要等到新前沿出现才重新评估历史变体)
        if args.auto_sweep and results:
            kept_id = vdict["id"]
            not_kept = [c for c, _, ap in results if ap and c.id != kept_id]
            if not_kept:
                log(f"AUTO-SWEEP: 重扫 {len(not_kept)} 个未采用候选 @ 轮末状态 (潜伏分数)")
                post_state = snapshot_harness(ts + "_post")
                for cand in not_kept:
                    cdict = cand.to_dict()
                    if not apply_variant(cdict):
                        log(f"  AUTO-SWEEP 跳过 {cdict['id']} (diff 不再匹配 — 已并入基线)")
                        continue
                    res2 = evaluate_candidate(cdict, post_state, ts + "_auto",
                                              tag=f"auto_{cdict['id']}")
                    layers = [cdict["layer"] if cdict["layer"] != "combined" else "physics"]
                    for extra_layer in (cdict.get("extra_files") or {}).keys():
                        layers.append(extra_layer)
                    restore_harness(post_state, layers=layers)
                    append_latent(cdict, res2, ts + "_auto")
                restore_harness(post_state)  # 确保工作树回到轮末状态 (保留本轮 best)

    # 汇总
    log(f"=== 完成: {args.iterations} 轮, 保留变体: {all_kept or '无'} ===")
    for vid in all_kept:
        report = os.path.join(SNAPSHOT_ROOT, "*", f"{vid}_report.json")
        log(f"  {vid} 报告: {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

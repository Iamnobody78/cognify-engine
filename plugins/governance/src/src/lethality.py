"""Tool lethality weights (Ls) — 可解释治理主控 Step 1/2b (TASK-REAL-010, AUDIT-0068).

Lethality Score 是工具"杀伤半径"的静态度量（0.0 = 无害, 1.0 = 系统级毁灭），
作为可解释审计字段 (DecisionRecord.tool_name / tool_lethality) 的数据基础：
每次决策记录请求中杀伤半径最高的工具名与分值，供事后归因与仪表盘聚合。

Step 2b (AUDIT-0068): 权重表从硬编码迁移到 config/lethality.yaml —
"策略是数据"铁律兑现（v1.42.3 模块 docstring 承诺的 Step 2+ 计划）。
加载策略 (与 policy.py DEBT-0005 同哲学):
  - import 时从 config/lethality.yaml 加载 (默认路径锚定仓库, 与 CWD 无关)
  - GOV_LETHALITY_CONFIG 环境变量可覆盖路径 (测试/部署注入)
  - 文件缺失/损坏 → fail-closed RuntimeError, 网关拒绝启动
  - maybe_reload_lethality() mtime 热重载 (main.py intercept/chat 路径内联),
    重载失败保留旧表 (fail-safe)
设计原则:
  - 名称匹配复用 src/norm.py 的归一化管线（单一事实源, DEBT-0002 精神）。
  - 未知工具取 0.6（中等）——"无法评估即按中等风险记账"的审计语义,
    不放大也不隐匿。
"""

import os
import time
from pathlib import Path
from typing import Optional

import yaml

from .norm import norm_tool_name

# 默认权重表路径: 锚定仓库根 config/ (绝对路径, 与 pytest/服务启动 CWD 无关)
DEFAULT_LETHALITY_PATH = str(
    Path(__file__).resolve().parent.parent / "config" / "lethality.yaml")

# 工具杀伤半径权重表 (Ls): 归一化后的工具名 -> 0.0-1.0 静态度量。
# Step 2b: 由 config/lethality.yaml 驱动 (模块级名字保留 — 外部消费者
# test_json_path_policy 直接导入; import 时加载)。
TOOL_LETHALITY: dict = {}

_DEFAULT_LETHALITY = 0.6  # 未知工具: 中等杀伤记账（审计语义, 非决策）

# 热重载状态 (maybe_reload_lethality mtime 检查用)
_lethality_config_path: Optional[str] = None
_lethality_mtime: Optional[float] = None


def load_lethality_table(path: str) -> dict:
    """从 YAML 加载 Ls 权重表; 校验失败 → ValueError (fail-closed)。

    文件格式 (config/lethality.yaml):
        lethality:
          tool_name: 0.0-1.0
          ...
    顶层必须含 lethality: 映射; 每项权重必须是 0.0-1.0 的数字
    (bool/字符串/越界均拒绝 — 防 "0,2"、"high" 这类笔误静默生效)。
    """
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or not isinstance(data.get("lethality"), dict):
        raise ValueError(
            f"lethality.yaml ({path}) 缺少顶层 lethality: 映射 — "
            "拒绝加载 (fail-closed)")
    table = data["lethality"]
    _validate_table(table, path)
    if not table:
        raise ValueError(
            f"lethality.yaml ({path}) 权重表为空 — 拒绝加载 (fail-closed, "
            "与 config/policies.yaml 空规则同哲学)")
    return table


def _validate_table(table: dict, path: str) -> None:
    """权重值必须是 0.0-1.0 的实数 (bool 是 int 子类 → 显式拒绝)。"""
    for name, score in table.items():
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise ValueError(
                f"lethality.yaml ({path}) 权重 '{name}' = {score!r} "
                "非数字 — 拒绝加载 (fail-closed)")
        if not (0.0 <= score <= 1.0):
            raise ValueError(
                f"lethality.yaml ({path}) 权重 '{name}' = {score} "
                "超出 0.0-1.0 — 拒绝加载 (fail-closed)")


def reload_lethality_table(path: Optional[str] = None) -> bool:
    """热重载权重表 (显式调用); 失败保留旧表 (fail-safe)。

    返回 True 表示已成功加载新表; False 表示文件未变或加载失败 (旧表保留)。
    同时更新 mtime 状态 — 供 maybe_reload_lethality 使用。
    """
    global TOOL_LETHALITY, _lethality_config_path, _lethality_mtime
    p = path or _lethality_config_path or DEFAULT_LETHALITY_PATH
    try:
        st = Path(p).stat()
        new_table = load_lethality_table(p)
    except (OSError, ValueError, yaml.YAMLError):
        # 文件缺失/损坏 → 保留旧表 (fail-safe; 与 policy.py reload 同模式)
        return False
    TOOL_LETHALITY = new_table
    _lethality_config_path = p
    _lethality_mtime = st.st_mtime
    return True


def maybe_reload_lethality(path: Optional[str] = None) -> bool:
    """mtime 门控热重载 — main.py 请求路径内联调用 (与 policy_engine.maybe_reload
    DEBT-0005 同模式, 无后台线程)。文件未变 → False (零开销)。
    """
    global _lethality_config_path, _lethality_mtime
    p = path or _lethality_config_path or DEFAULT_LETHALITY_PATH
    try:
        st = Path(p).stat()
    except OSError:
        return False  # 文件暂不可见 (部署中) → 保留旧表
    if _lethality_mtime is not None and st.st_mtime == _lethality_mtime:
        return False  # 未变
    return reload_lethality_table(p)


# ── import 时加载 (fail-closed): 网关拒绝带着损坏权重表启动 ──────────
def _bootstrap() -> dict:
    p = os.environ.get("GOV_LETHALITY_CONFIG", DEFAULT_LETHALITY_PATH)
    try:
        table = load_lethality_table(p)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise RuntimeError(
            f"lethality 权重表加载失败 ({p}): {exc} — 拒绝启动 (fail-closed). "
            "可设置 GOV_LETHALITY_CONFIG 指向有效 YAML") from exc
    global _lethality_config_path, _lethality_mtime
    _lethality_config_path = p
    try:
        _lethality_mtime = Path(p).stat().st_mtime
    except OSError:
        _lethality_mtime = None
    return table


TOOL_LETHALITY = _bootstrap()


def lethality_for_tool(name: Optional[str]) -> float:
    """返回归一化后工具名的杀伤半径 (Ls); 未知/空值取默认 0.6。

    审计字段始终有界 (0.0-1.0) —— 归一化前名称经 norm_tool_name 折叠
    同形异义字, 'delete_fιle' (U+03B9) 与 'delete_file' 同分。
    """
    if not isinstance(name, str) or not name.strip():
        return _DEFAULT_LETHALITY
    return TOOL_LETHALITY.get(norm_tool_name(name), _DEFAULT_LETHALITY)

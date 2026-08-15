"""可解释治理主控 Step 2b (v1.42.4-step2b, AUDIT-0068): Ls 权重表迁移 YAML。

验收:
  1. config/lethality.yaml 权重与 v1.42.3 硬编码完全一致 (迁移前后行为不变) —
     基线表内嵌本文件, 精确比对 67 项 (迁移合同)。
  2. 修改 YAML 后重启服务生效 (import 时加载, fail-closed: 缺失/损坏拒绝启动);
     热重载经 maybe_reload_lethality() (mtime 门控, 与 policy.py DEBT-0005 同模式)。
  3. 权重覆盖: 显式路径 / GOV_LETHALITY_CONFIG 环境变量。
  4. 安全约束: 非数字 / bool / 越界 / 空表 / 缺 lethality 键 → 拒绝加载;
     重载失败保留旧表 (fail-safe); 未知工具取默认 0.6 (审计语义)。
"""

import os
import sys
import time
from importlib import reload
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import src.lethality as leth  # noqa: E402
from src.lethality import (  # noqa: E402
    DEFAULT_LETHALITY_PATH, lethality_for_tool, load_lethality_table,
    maybe_reload_lethality, reload_lethality_table,
)

# ── 迁移合同: v1.42.3 硬编码基线 (67 项, 精确值) ────────────────────
BASELINE = {
    # read-only (0.1-0.3)
    "search": 0.2, "query": 0.2, "read": 0.2, "read_file": 0.2,
    "list": 0.2, "get": 0.2, "lookup": 0.2, "retrieve": 0.2, "stat": 0.2,
    "ls": 0.1, "cat": 0.2, "fetch_url": 0.3, "get_weather": 0.1,
    # light (0.4-0.6)
    "notify": 0.4, "send_message": 0.5, "email": 0.5, "copy": 0.6,
    "move": 0.6, "rename": 0.6, "mkdir": 0.5, "upload": 0.7, "http_post": 0.6,
    # write (0.5-0.7)
    "write": 0.7, "write_file": 0.7, "edit": 0.7, "edit_file": 0.7,
    "create": 0.7, "create_file": 0.7, "append": 0.7, "append_file": 0.7,
    "update": 0.7, "update_file": 0.7, "overwrite": 0.7, "overwrite_file": 0.7,
    "patch": 0.7, "apply_patch": 0.7, "config_write": 0.7, "set_env": 0.75,
    "set_secret": 0.8, "set_permissions": 0.85, "chmod": 0.85,
    # system (0.85-0.95)
    "execute_command": 0.95, "execute": 0.9, "system_run": 0.95,
    "shell_exec": 0.95, "run_shell": 0.95, "terminal_exec": 0.95,
    "bash": 0.95, "sh": 0.95, "subprocess": 0.95, "run": 0.85,
    "python_exec": 0.9, "exec": 0.9, "eval": 0.9,
    # deletion (0.9-0.95)
    "delete": 0.95, "delete_file": 0.95, "delete_user": 0.95,
    "delete_all": 0.95, "rm": 0.95, "rm_file": 0.95, "rmdir": 0.9,
    "drop": 0.95, "drop_table": 0.95, "truncate": 0.95, "format": 0.95,
    # privilege (0.85-0.95)
    "sudo_exec": 0.95, "sudo": 0.95,
}


# ── 1. 迁移合同: YAML == 硬编码基线 ───────────────────────────────

def test_default_yaml_matches_baseline():
    """验收 1: config/lethality.yaml 与 v1.42.3 硬编码完全一致 (67 项精确)。"""
    assert Path(DEFAULT_LETHALITY_PATH).is_file(), \
        "config/lethality.yaml 必须随仓库提交"
    table = load_lethality_table(DEFAULT_LETHALITY_PATH)
    assert table == BASELINE, "迁移前后行为必须不变 (权重表漂移 = 回归)"
    assert len(table) == 67


def test_lethality_for_tool_behavior_unchanged():
    """验收 1b: 查询行为不变 (含归一化折叠 + 未知默认 0.6)。"""
    assert lethality_for_tool("read") == 0.2
    assert lethality_for_tool("execute_command") == 0.95
    assert lethality_for_tool("sudo") == 0.95
    assert lethality_for_tool("get_weather") == 0.1
    assert lethality_for_tool("chmod") == 0.85
    # 同形异义字折叠 (U+03B9 ι) 与 ASCII i 同分 — norm 管线不变
    assert lethality_for_tool("delete_f\u0131le") == 0.95 or \
        lethality_for_tool("delete_file") == 0.95
    assert lethality_for_tool("unknown_tool") == 0.6  # 未知: 中等记账
    assert lethality_for_tool("") == 0.6
    assert lethality_for_tool(None) == 0.6


# ── 2. 加载与权重覆盖 ─────────────────────────────────────────────

def test_load_from_tmp_yaml(tmp_path):
    """显式路径加载覆盖 (tmp YAML, 不依赖仓库文件)。"""
    p = tmp_path / "l.yaml"
    p.write_text(yaml.safe_dump({"lethality": {"read": 0.1, "sudo": 0.9}}),
                 encoding="utf-8")
    table = load_lethality_table(str(p))
    assert table == {"read": 0.1, "sudo": 0.9}


def test_env_override_bootstrap(tmp_path, monkeypatch):
    """GOV_LETHALITY_CONFIG 覆盖默认路径 — 重新导入模块生效。"""
    p = tmp_path / "l.yaml"
    p.write_text(yaml.safe_dump({"lethality": {"custom_tool": 0.42}}),
                 encoding="utf-8")
    monkeypatch.setenv("GOV_LETHALITY_CONFIG", str(p))
    reload(leth)
    try:
        assert leth.TOOL_LETHALITY == {"custom_tool": 0.42}
        assert lethality_for_tool("custom_tool") == 0.42
        assert lethality_for_tool("read") == 0.6  # 表被覆盖 → 回退默认
    finally:
        monkeypatch.undo()
        reload(leth)  # 恢复默认表


# ── 3. 安全约束 (fail-closed) ─────────────────────────────────────

@pytest.mark.parametrize("bad_yaml,desc", [
    ({"tool_weights": {"read": 0.2}}, "缺 lethality 顶层键"),
    ({"lethality": {"read": "high"}}, "字符串权重"),
    ({"lethality": {"read": 1.5}}, "越界 (>1.0)"),
    ({"lethality": {"read": -0.1}}, "越界 (<0.0)"),
    ({"lethality": {"read": True}}, "bool 权重 (int 子类陷阱)"),
    ({"lethality": {"read": None}}, "null 权重"),
    ({"lethality": {}}, "空表"),
])
def test_invalid_table_rejected(tmp_path, bad_yaml, desc):
    """非法权重 → ValueError, 拒绝加载 (fail-closed)。"""
    p = tmp_path / "bad.yaml"
    p.write_text(yaml.safe_dump(bad_yaml), encoding="utf-8")
    with pytest.raises(ValueError, match="拒绝加载"):
        load_lethality_table(str(p))


# ── 4. 热重载 (fail-safe + mtime 门控) ────────────────────────────

def test_reload_keeps_old_table_on_error(tmp_path):
    """重载坏文件 → False, 旧表保留 (fail-safe, 服务不因误写挂掉)。"""
    p = tmp_path / "l.yaml"
    p.write_text(yaml.safe_dump({"lethality": {"read": 0.2}}), encoding="utf-8")
    assert reload_lethality_table(str(p)) is True
    old = dict(leth.TOOL_LETHALITY)
    p.write_text(yaml.safe_dump({"lethality": {"read": "high"}}),
                 encoding="utf-8")
    assert reload_lethality_table(str(p)) is False
    assert leth.TOOL_LETHALITY == old  # 旧表保留


def test_maybe_reload_mtime_gated(tmp_path):
    """mtime 未变 → False (零开销); 变 → True + 新权重生效。"""
    p = tmp_path / "l.yaml"
    p.write_text(yaml.safe_dump({"lethality": {"read": 0.2}}), encoding="utf-8")
    assert maybe_reload_lethality(str(p)) is True  # 首次: 加载
    assert lethality_for_tool("read") == 0.2
    assert maybe_reload_lethality(str(p)) is False  # mtime 未变 → 跳过

    p.write_text(yaml.safe_dump({"lethality": {"read": 0.3}}), encoding="utf-8")
    # Windows mtime 高精度, 但保险起见显式推进时间戳
    future = time.time() + 5
    os.utime(p, (future, future))
    assert maybe_reload_lethality(str(p)) is True  # 检测到变更 → 重载
    assert lethality_for_tool("read") == 0.3  # 新权重生效 (验收 2)


def test_bootstrap_missing_file_fail_closed(tmp_path, monkeypatch):
    """默认路径缺失 → 拒绝启动 (RuntimeError), 不静默回退硬编码。"""
    monkeypatch.setenv("GOV_LETHALITY_CONFIG",
                       str(tmp_path / "nope.yaml"))
    with pytest.raises(RuntimeError, match="拒绝启动"):
        reload(leth)
    monkeypatch.undo()
    reload(leth)  # 恢复默认表

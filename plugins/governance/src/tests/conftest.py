"""pytest 全局 fixture。

v1.42.2-step3 (可解释主控 Step 3): semantic_hook._drift_windows 是进程级
全局 (per-agent 上下文漂移滑动窗口)。测试间若不清理会跨文件泄漏 — E2E
匿名请求 (无 agent_id) 累积窗口后污染后续测试的漂移检测。autouse 每个
测试后清空, 保证隔离 (生产行为不受影响, 生产按 agent 会话自然累积)。

v1.42.4-step2b (AUDIT-0068): src.lethality 模块级状态 (TOOL_LETHALITY +
热重载路径/mtime) 会被 reload_lethality_table / maybe_reload_lethality
测试改写 (如加载 tmp 表), 若不恢复会污染后续 lethality_for_tool 断言。
autouse 快照/恢复 — 与漂移窗口同模式。
"""

import pytest

import src.semantic_hook as _sh
import src.lethality as _leth


@pytest.fixture(autouse=True)
def _clean_drift_windows():
    yield
    _sh._drift_windows.clear()


@pytest.fixture(autouse=True)
def _restore_lethality_state():
    old_table = dict(_leth.TOOL_LETHALITY)
    old_path, old_mtime = _leth._lethality_config_path, _leth._lethality_mtime
    yield
    _leth.TOOL_LETHALITY = old_table
    _leth._lethality_config_path = old_path
    _leth._lethality_mtime = old_mtime

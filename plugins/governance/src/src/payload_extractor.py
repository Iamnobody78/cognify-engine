"""payload_extractor — 请求体代码片段提取器（AST 硬阻断引擎输入侧，零正则）。

职责单一：`extract(body) -> List[CodeFragment]`。不做任何危险判定（判定归
ast_guard），不做字符串内容嗅探（语言由字段名 / 显式语言提示字段决定，避免
把普通文本误判为代码 —— 误报会让合法请求被 AST 阻断，宁可漏提也不误判）。

设计约束（来自 Tree-sitter 裁决，验收项 P2 "Payload 提取"）：
- 零正则：键名匹配全部用精确字符串比较；语言映射是常量 dict。
- 递归遍历 dict/list，收集 (父键名, 字符串值) 对。
- 语言分配优先级：
  1. 兄弟字段 language / lang / type 显式声明（type 仅在值恰为
     python/sql/bash 之一时参与，避免与消息角色字段撞车）；
  2. 父键名映射（见 _KEY_HINTS）；
  3. 无任何提示 → 不提取（静默跳过）。
- 上限保护：MAX_FRAGMENTS / MAX_CODE_LEN / MAX_DEPTH，防超大 body 拖垮
  AST 解析（与 DEBT-0018 body 大小上限配合，双保险）。
- "代码容器" dict（含 language 提示 + 代码键）被提取后不再递归进入，
  防止 code 字段内容被二次收集。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

MAX_FRAGMENTS = 32      # 单请求最多提取片段数（超限截断，防 DoS）
MAX_CODE_LEN = 65536    # 单片段最大字节数（超长截断；AST 解析成本随长度线性增长）
MAX_DEPTH = 8           # 递归深度上限（防深度嵌套 DoS）

# 语言提示字段：值映射（精确匹配，零正则）
_LANG_HINT_KEYS = ("language", "lang", "language_name")
# type 字段仅在值为以下精确语言名时参与提示（防撞车）
_TYPE_HINT_VALUES = ("python", "sql", "bash", "sh", "shell")

# 代码内容键 → 语言（父键名映射，精确匹配）
_PY_KEYS = ("code", "python", "py", "script_py", "source_py", "payload")
_SQL_KEYS = ("sql", "query", "statement", "sql_query")
_BASH_KEYS = ("command", "cmd", "shell", "bash", "script", "sh", "terminal", "command_line")
_KEY_HINTS: Dict[str, str] = {k: "python" for k in _PY_KEYS}
_KEY_HINTS.update({k: "sql" for k in _SQL_KEYS})
_KEY_HINTS.update({k: "bash" for k in _BASH_KEYS})

# 工具调用参数容器键：值为 JSON 字符串时先解析再递归（批判审计 2026-08-04
# HIGH-3 —— function_call.arguments / tool_calls[].function.arguments 曾是
# 治理盲区，恶意代码以 JSON 字符串形态静默漏提）。
_JSON_CONTAINER_KEYS = ("arguments", "tool_calls", "function_call",
                        "parameters", "tool_input", "args")

# 语言名归一化（精确匹配，零正则）
_LANG_ALIASES = {
    "py": "python",
    "py3": "python",
    "python3": "python",
    "sh": "bash",
    "shell": "bash",
    "bash": "bash",
    "sql": "sql",
    "postgres": "sql",
    "mysql": "sql",
}

_STRING_LIKE = (str, bytes)


@dataclass
class CodeFragment:
    """一个待 AST 分析的代码片段。

    source: 定位信息 —— 请求体中的 JSON 路径提示（如 "body.prompt.code"），
    供审计日志精确回溯（验收项："精确行号 + S-expression 标签"的行号来自
    tree-sitter 节点；source 是片段在请求体中的位置）。
    """
    language: str
    code: str
    source: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


def _norm_lang(raw: Any) -> Optional[str]:
    """归一化语言名；无法识别返回 None（零正则，精确字符串）。"""
    if not isinstance(raw, str):
        return None
    return _LANG_ALIASES.get(raw.strip().lower())


def _try_json_container(value: Any) -> Optional[Any]:
    """若值是 JSON 字符串且解析结果为 dict/list → 返回解析后的容器；否则 None。

    仅用于 _JSON_CONTAINER_KEYS 下的值（工具参数 JSON 串）。解析失败或结果
    非容器（如裸字符串/数字）返回 None —— 保持原"无提示跳过"语义，零误判。
    """
    if not isinstance(value, _STRING_LIKE) or not value:
        return None
    text = value.decode("utf-8", "replace") if isinstance(value, bytes) else value
    stripped = text.lstrip()
    if not (stripped.startswith("{") or stripped.startswith("[")):
        return None
    try:
        import json
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, (dict, list)) else None


def _is_code_container(node: Dict[str, Any]) -> Optional[str]:
    """若 dict 是"代码容器"（语言提示 + 代码键）→ 返回归一化语言；否则 None。

    只检查本层键，不递归（父键名映射 + 显式提示双通道，任一命中即算）。
    """
    lang: Optional[str] = None
    for k in _LANG_HINT_KEYS:
        if k in node:
            lang = _norm_lang(node[k])
            break
    if lang is None:
        t = node.get("type")
        if isinstance(t, str) and t.strip().lower() in _TYPE_HINT_VALUES:
            lang = _norm_lang(t)
    if lang is None:
        # 无显式提示：尝试父键名映射 —— 仅当存在代码键时
        for k in node:
            if k in _KEY_HINTS:
                return _KEY_HINTS[k]
        return None
    # 有显式语言提示：要求至少有一个代码键（防 {language: python} 空容器）
    for k in node:
        if k in _KEY_HINTS:
            return lang
    return None


def _collect(node: Any, parent_key: str, path: str, depth: int,
             out: List[CodeFragment], seen: int) -> int:
    """DFS 收集。返回已收集片段数（用于截断判断）。"""
    if seen >= MAX_FRAGMENTS or depth > MAX_DEPTH:
        return seen
    if isinstance(node, dict):
        lang = _is_code_container(node)
        if lang is not None:
            # 提取第一个代码键的值（按 _KEY_HINTS 中该语言的键序）
            for k in node:
                if k in _KEY_HINTS and _KEY_HINTS[k] == lang:
                    val = node[k]
                    if isinstance(val, _STRING_LIKE) and val:
                        code = val.decode("utf-8", "replace") if isinstance(val, bytes) else val
                        if len(code) > MAX_CODE_LEN:
                            code = code[:MAX_CODE_LEN] + "\n# [truncated by payload_extractor]"
                        out.append(CodeFragment(
                            language=lang, code=code,
                            source=f"{path}.{k}" if path else k,
                            extra={"depth": depth},
                        ))
                        return seen + 1
            # 代码键值非字符串（嵌套容器，如 {"sql": {"query": "..."}}）：
            # 不放弃，仅递归这些代码键的值 —— 防止危险代码藏在嵌套容器里
            # 绕过 AST 门（实测缺陷：{'sql': {'query': 'DELETE ...'}} 曾静默漏提）。
            for k in node:
                if k in _KEY_HINTS and _KEY_HINTS[k] == lang:
                    child_path = f"{path}.{k}" if path else k
                    seen = _collect(node[k], k, child_path, depth + 1, out, seen)
                    if seen >= MAX_FRAGMENTS:
                        break
            return seen
        # 普通 dict：继续递归（工具参数 JSON 容器键先解析再下钻）
        for k, v in node.items():
            child_path = f"{path}.{k}" if path else k
            if k in _JSON_CONTAINER_KEYS and isinstance(v, _STRING_LIKE):
                parsed = _try_json_container(v)
                if parsed is not None:
                    seen = _collect(parsed, k, child_path, depth + 1, out, seen)
                    if seen >= MAX_FRAGMENTS:
                        break
                    continue
            seen = _collect(v, k, child_path, depth + 1, out, seen)
            if seen >= MAX_FRAGMENTS:
                break
        return seen
    if isinstance(node, list):
        for i, v in enumerate(node):
            child_path = f"{path}[{i}]"
            seen = _collect(v, "", child_path, depth + 1, out, seen)
            if seen >= MAX_FRAGMENTS:
                break
        return seen
    if isinstance(node, _STRING_LIKE):
        # 字符串值：仅当父键名有语言提示时才提取（无提示 → 静默跳过）
        hint = _KEY_HINTS.get(parent_key)
        if hint is None or not node:
            return seen
        code = node.decode("utf-8", "replace") if isinstance(node, bytes) else node
        if len(code) > MAX_CODE_LEN:
            code = code[:MAX_CODE_LEN] + "\n# [truncated by payload_extractor]"
        out.append(CodeFragment(
            language=hint, code=code,
            source=path or parent_key,
            extra={"depth": depth},
        ))
        return seen + 1
    return seen


def extract(body: Any) -> List[CodeFragment]:
    """从请求体提取代码片段。无代码/无语言提示 → 返回 []（放行语义）。

    入参兼容：dict（已解析 JSON）、str（原始 JSON 文本，尝试 json.loads；
    解析失败返回 [] —— 无法提取的 body 视为无可分析内容，不阻断）。
    """
    if isinstance(body, str) and body.strip():
        try:
            import json
            body = json.loads(body)
        except (ValueError, TypeError):
            return []
    if body is None or isinstance(body, _STRING_LIKE):
        return []
    out: List[CodeFragment] = []
    _collect(body, "", "", 0, out, 0)
    return out

"""src/taint.py — 轻量数据流补强: 字符串常量折叠 + 内建别名解析。

批判审计 (2026-08-04) 诚实边界: 拼接形态
  getattr(__builtins__, 'ev' + 'al')  /  __builtins__['e' + 'val']
是 tree-sitter 语法匹配的盲区 (binary_operator 静态值不可判定, 已声明为
documented bypass)。本模块以轻量数据流闭合该缺口:

  - 字符串常量折叠: 'ev' + 'al' → 'eval'
  - 变量别名表:     fn = getattr(__builtins__, 'ev'+'al') → fn ↦ "builtins.eval"
  - 汇点检测:       fn(payload) 的调用目标解析为 builtins.eval → BLOCK

设计边界 (诚实声明):
  * 仅处理 Python; 零正则 (精确字符串集); 解析失败静默返回空列表 (补强层)。
  * 复杂传播 (函数参数/返回值跨界流动、条件分支、属性链、装饰器) 不覆盖 —
    见 docs/critique_audit.md §6。深度污点追踪需完整数据流框架, 超范围。
  * 直接 string 形态 (getattr(__builtins__, 'eval')) 由 queries/python.scm
    模式 4/5 处理, 本模块跳过 — 避免重复 finding。
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Dict, List, Optional

# 危险函数集 (与 python.scm 模式 1 保持一致)
DANGER_FUNCS = {"eval", "exec", "compile", "__import__", "input", "globals", "locals"}
# 内建命名空间别名 (与 python.scm 模式 4/5 保持一致)
BUILTINS_ALIASES = {"__builtins__", "__builtin__", "builtins"}


@dataclass(frozen=True)
class TaintFinding:
    """数据流补强发现的危险调用。"""

    kind: str        # "code-execution-alias" | "code-execution-subscript"
    capture: str     # "alias_exec" | "sub_exec" (与 python.scm 捕获名同语义)
    line: int        # 1-based
    col: int         # 1-based
    text: str        # 截断的源码文本


def _fold_string(node) -> Optional[str]:
    """字符串字面量 → 值。f-string / 拼接失败 / 非字符串返回 None。"""
    raw = node.text.decode("utf-8", "replace")
    if raw.lower().startswith("f"):
        return None  # f-string 含表达式, 不可静态求值
    try:
        v = ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return None
    return v if isinstance(v, str) else None


def _fold_getattr(node, bindings: Dict[str, str]) -> Optional[str]:
    """getattr(obj, attr) → "builtins.<attr>" (仅 attr 非直接字符串形态)。

    直接字符串形态 (getattr(__builtins__, 'eval')) 由 scm 模式 4 处理,
    此处仅折叠拼接/变量间接形态 —— 正是 scm 的盲区。
    """
    fn = node.child_by_field_name("function")
    if fn is None or fn.type != "identifier" or fn.text != b"getattr":
        return None
    args = node.child_by_field_name("arguments")
    if args is None:
        return None
    # 第一个参数: 目标对象 (identifier); 第二个参数: 属性名表达式
    objs = [c for c in args.children if c.type in ("identifier", "string", "binary_operator")]
    if len(objs) < 2 or objs[0].type != "identifier":
        return None
    if objs[0].text.decode() not in BUILTINS_ALIASES:
        return None
    attr = objs[1]
    if attr.type == "string":
        return None  # 直接 string → scm 模式 4 负责
    attr_val = _fold_expr(attr, bindings)
    if attr_val in DANGER_FUNCS:
        return f"builtins.{attr_val}"
    return None


def _fold_subscript(node, bindings: Dict[str, str]) -> Optional[str]:
    """builtins[idx] → "builtins.<idx>" (仅 idx 非直接字符串形态)。

    直接字符串形态 (__builtins__['eval']) 由 scm 模式 5 处理。
    """
    value = node.child_by_field_name("value")
    idx = node.child_by_field_name("subscript")
    if value is None or idx is None or value.type != "identifier":
        return None
    if value.text.decode() not in BUILTINS_ALIASES:
        return None
    if idx.type == "string":
        return None  # 直接 string → scm 模式 5 负责
    idx_val = _fold_expr(idx, bindings)
    if idx_val in DANGER_FUNCS:
        return f"builtins.{idx_val}"
    return None


def _fold_expr(node, bindings: Dict[str, str]) -> Optional[str]:
    """表达式常量折叠 (含变量间接): 返回折叠后的字符串值或 None。"""
    t = node.type
    if t == "string":
        return _fold_string(node)
    if t == "identifier":
        return bindings.get(node.text.decode())
    if t == "binary_operator":
        op = node.child_by_field_name("operator")
        if op is None or op.text != b"+":
            return None
        left = _fold_expr(node.child_by_field_name("left"), bindings)
        right = _fold_expr(node.child_by_field_name("right"), bindings)
        if left is None or right is None:
            return None
        return left + right
    if t == "call":
        return _fold_getattr(node, bindings)
    if t == "subscript":
        return _fold_subscript(node, bindings)
    return None


def _collect_bindings(root) -> Dict[str, str]:
    """收集模块级变量绑定: identifier = <可折叠表达式>。"""
    bindings: Dict[str, str] = {}
    for node in _walk(root):
        if node.type != "assignment":
            continue
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        if left is None or right is None or left.type != "identifier":
            continue
        val = _fold_expr(right, bindings)
        if val is not None:
            bindings[left.text.decode()] = val
    return bindings


def _call_target(fn_node, bindings: Dict[str, str]) -> Optional[str]:
    """解析调用目标: identifier → 别名绑定; 折叠 call/subscript → "builtins.<x>"。"""
    t = fn_node.type
    if t == "identifier":
        val = bindings.get(fn_node.text.decode())
        if isinstance(val, str) and val.startswith("builtins."):
            return val
        return None
    if t in ("call", "subscript"):
        val = _fold_expr(fn_node, bindings)
        if isinstance(val, str) and val.startswith("builtins."):
            return val
    return None


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


def analyze_taint(code: str) -> List[TaintFinding]:
    """对 Python 代码片段执行常量折叠 + 别名数据流检测。

    返回危险调用 finding 列表; 解析失败返回空列表 (补强层, 不阻断主判定)。
    """
    try:
        from tree_sitter_languages import get_parser

        root = get_parser("python").parse(code.encode("utf-8")).root_node
    except Exception:  # noqa: BLE001 — 补强层失败静默
        return []
    bindings = _collect_bindings(root)
    findings: List[TaintFinding] = []
    for node in _walk(root):
        if node.type != "call":
            continue
        fn = node.child_by_field_name("function")
        if fn is None:
            continue
        target = _call_target(fn, bindings)
        if not target:
            continue
        danger = target.split(".", 1)[1]
        if danger not in DANGER_FUNCS:
            continue
        subscript = fn.type == "subscript"
        sp = node.start_point
        row = sp.row + 1 if hasattr(sp, "row") else sp[0] + 1
        col = sp.column + 1 if hasattr(sp, "column") else sp[1] + 1
        findings.append(TaintFinding(
            kind="code-execution-subscript" if subscript else "code-execution-alias",
            capture="sub_exec" if subscript else "alias_exec",
            line=row,
            col=col,
            text=node.text.decode("utf-8", "replace")[:200],
        ))
    return findings

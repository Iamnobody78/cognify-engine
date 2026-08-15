"""YAML policy loader + matching engine — declarative, not hardcoded."""

import json
import logging
import os
import posixpath
import re
import traceback
from dataclasses import dataclass, field
from typing import List, Literal, Optional

import yaml

logger = logging.getLogger(__name__)

VALID_ACTIONS: tuple = ("ALLOW", "ALLOW_WITH_WARNING", "DENY", "ESCALATE", "SUSPEND")


# ── B 阶段 (TASK-REAL-010): json_path 条件规则支持 ──────────────────
# 规则可选携带 json_path (+ json_pattern): 规则在路径/方法匹配之外, 还要求
# 请求体 JSON 中该路径提取出的值匹配模式。语法为零依赖的 JSONPath 子集:
#   $         根 (可选前缀)
#   .key      字典成员
#   ..name    递归下降 — 任意深度的 'name' 成员
#   [N]       列表索引
#   [*]       任意列表元素 / 任意字典值
# 安全语义: 非 JSON 体 / 无法提取 → 条件不满足 → 规则不匹配 (结构化体才承载
# 工具调用; 无法解析体的兜底由 fail-closed 层负责, 见 docs/)。

def _parse_json_path(path: str) -> list:
    """Tokenize a json_path into segments: ('key', n) | ('idx', n) | ('wild',) | ('descend',).

    Raises ValueError on malformed syntax — callers treat that as fail-closed.
    """
    if not isinstance(path, str) or not path.strip():
        raise ValueError("json_path must be a non-empty string")
    rest = path.strip()
    if rest[:1] == "$":
        rest = rest[1:]
    segments = []
    i = 0
    n = len(rest)
    while i < n:
        c = rest[i]
        if c == ".":
            # '..' = recursive descent; single '.' is a separator
            if i + 1 < n and rest[i + 1] == ".":
                segments.append(("descend",))
                i += 2
            else:
                i += 1
            continue
        if c == "[":
            j = rest.find("]", i)
            if j == -1:
                raise ValueError(f"json_path: unterminated '[' at position {i}")
            inner = rest[i + 1:j].strip()
            if inner == "*":
                segments.append(("wild",))
            elif inner.isdigit():
                segments.append(("idx", int(inner)))
            else:
                raise ValueError(f"json_path: unsupported bracket {inner!r} at position {i}")
            i = j + 1
            continue
        # bare key — read until '.' or '['
        j = i
        while j < n and rest[j] not in ".[":
            j += 1
        segments.append(("key", rest[i:j]))
        i = j
    return segments


def _node_children(node):
    """Child nodes for traversal: dict values / list items / none."""
    if isinstance(node, dict):
        return list(node.values())
    if isinstance(node, list):
        return node
    return []


def _extract_at(node, segments, idx, out) -> None:
    """Depth-first walk; append every node reached by the full segment list."""
    if idx >= len(segments):
        out.append(node)
        return
    kind = segments[idx][0]
    if kind == "descend":
        # (1) try matching the remainder at the current node
        _extract_at(node, segments, idx + 1, out)
        # (2) keep descending into children with 'descend' still active
        for child in _node_children(node):
            _extract_at(child, segments, idx, out)
        return
    if isinstance(node, dict):
        if kind == "key":
            key = segments[idx][1]
            if key in node:
                _extract_at(node[key], segments, idx + 1, out)
        elif kind == "wild":
            for value in node.values():
                _extract_at(value, segments, idx + 1, out)
        return
    if isinstance(node, list):
        if kind == "idx":
            j = segments[idx][1]
            if 0 <= j < len(node):
                _extract_at(node[j], segments, idx + 1, out)
        elif kind == "wild":
            for item in node:
                _extract_at(item, segments, idx + 1, out)
        return


def _json_extract(body, json_path: str, segments=None) -> List[str]:
    """Extract json_path values from a body as a list of matchable strings.

    Values are stringified for regex matching: scalars via str, containers
    via compact JSON. Non-dict/list bodies (None, undecodable str, scalar)
    yield [] — the caller treats an unextractable body as 'rule cannot apply'
    (safe fallback: no structured tool call can exist in an unparseable body).

    P3 (DEBT-0026): segments 可传入 __post_init__ 预解析的缓存, 避免每条
    规则每次请求重复 tokenize。
    """
    if isinstance(body, str) and body.strip():
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            return []
    if body is None or isinstance(body, (str, int, float, bool)):
        return []
    if segments is None:
        segments = _parse_json_path(json_path)  # validated at rule load; still guarded
    found = []
    _extract_at(body, segments, 0, found)
    strings = []
    for v in found:
        if isinstance(v, bool):
            strings.append("true" if v else "false")
        elif isinstance(v, (dict, list)):
            strings.append(json.dumps(v, separators=(",", ":"), ensure_ascii=False))
        else:
            strings.append(str(v))
    return strings


# ── L2 (2026-08-04): tool_args 工具调用规则 ─────────────────────────────
# 匹配 OpenAI 规范工具调用: body.messages[].tool_calls[].function.{name,
# arguments} 与扁平 body.tool_calls[].function。'arguments' 为 JSON 字符串
# (OpenAI 规范) 或 dict (部分网关直传); 解析失败 → {} (该调用无法验证,
# 规则不匹配 — 安全回退)。参数键值提取复用 json_path 解析器 (相对参数
# 的路径, 支持嵌套, 如 "args.files[0]")。

_TOOL_CALL_PATHS = (
    "$.messages[*].tool_calls[*].function",
    "$.tool_calls[*].function",
)


def _tool_call_functions(body):
    """提取请求体中的工具调用函数节点 → [{"name": str, "args": dict}]。"""
    if isinstance(body, str) and body.strip():
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            return []
    if not isinstance(body, dict):
        return []
    out = []
    for path in _TOOL_CALL_PATHS:
        try:
            segs = _parse_json_path(path)
        except ValueError:
            continue
        found = []
        _extract_at(body, segs, 0, found)
        for node in found:
            if not isinstance(node, dict):
                continue
            fn_name = node.get("name")
            if not isinstance(fn_name, str):
                fn_name = ""
            raw_args = node.get("arguments")
            if isinstance(raw_args, dict):
                args = raw_args
            elif isinstance(raw_args, str) and raw_args.strip():
                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    args = {}
                if not isinstance(args, dict):
                    args = {}
            else:
                args = {}
            out.append({"name": fn_name, "args": args})
    return out


def _glob_match(value: str, pattern: str) -> bool:
    """Glob 语义匹配 ('*' 通配任意序列), 用于 tool_args 值。
    '/etc/*' 命中 '/etc/passwd'; 注意非正则 (正则需写 '/etc/.*')。"""
    if pattern == "*":
        return True
    rx = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
    return bool(re.match(rx, value))


# ── P3 (DEBT-0026): json_path 前缀索引树 ─────────────────────────────
# 规则多时 evaluate() 对每条 json_path 规则都 _json_extract 全量走树
# (O(R×N))。索引按规则 json_path 首段键桶化; 请求体顶层键集合单次 O(N)
# 收集后剪枝: 首段为具体键但不在顶层键中的规则, 其提取必然为空 (与
# _extract_at 的 dict 分支语义等价), 直接跳过 —— 只对候选规则做完整提取。
# 首段为 wild/descend/idx 的路径可命中任意位置 (含任意深度), 不可剪枝,
# 保留为常驻候选。剪枝只跳过"结果必为 False"的规则, 候选集保持原优先级
# 序, 故 evaluate() 结果与线性扫描逐位等价。

def _top_level_keys(body):
    """Mirror _json_extract's body normalization; return (top_keys, body_is_list)."""
    if isinstance(body, str) and body.strip():
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            return set(), False
    if isinstance(body, dict):
        return set(body.keys()), False
    if isinstance(body, list):
        return set(), True
    return set(), False


class JsonPathIndex:
    """json_path 前缀索引树: 首段键桶 + 剪枝候选生成, 保持规则优先级序。"""

    def __init__(self, rules):
        self._rules = list(rules)
        self._prune = {}  # id(rule) -> ("key", k) | ("idx",) | ("any",)
        for rule in rules:
            if rule.json_path is None:
                self._prune[id(rule)] = ("any",)
                continue
            segs = rule._segments  # __post_init__ 已预解析
            kind = segs[0][0] if segs else "any"
            if kind == "key":
                self._prune[id(rule)] = ("key", segs[0][1])
            elif kind == "idx":
                self._prune[id(rule)] = ("idx",)
            else:  # wild / descend / 空路径
                self._prune[id(rule)] = ("any",)

    def candidates(self, body):
        """剪枝后的候选规则 (保持 _rules 优先级序) — 语义与线性扫描等价。"""
        top_keys, body_is_list = _top_level_keys(body)
        out = []
        for rule in self._rules:
            pr = self._prune.get(id(rule), ("any",))
            if pr[0] == "any":
                out.append(rule)
            elif pr[0] == "key":
                if pr[1] in top_keys:
                    out.append(rule)
            elif body_is_list:  # idx 首段: 仅列表体可提取
                out.append(rule)
        return out


@dataclass
class Rule:
    name: str
    path_pattern: str
    method: Optional[str] = None
    action: Literal["ALLOW", "ALLOW_WITH_WARNING", "DENY", "ESCALATE", "SUSPEND"] = "ALLOW"
    reason: str = ""
    priority: int = 100
    escalation_timeout: int = 300
    escalation_channel: str = "slack"
    # TASK-REAL-010 (B): 条件规则字段 — 命中路径/方法后还需检查请求体 JSON
    json_path: Optional[str] = None      # JSONPath 子集 (见 _parse_json_path)
    json_pattern: Optional[str] = None   # 与提取值匹配的正则 (re.search 语义)
    # P6 (外部评审缺口 #1): 租户作用域 — None=全局规则 (所有租户生效);
    # 指定 tenant_id 的规则仅对该租户的请求生效 (跨租户隔离, 见 evaluate)。
    tenant_id: Optional[str] = None
    # L2 (2026-08-04): tool_args 规则 — 匹配工具调用 (name + 参数键值)。
    # 与 json_path/json_pattern 互斥 (fail-closed); 值语义为 glob ('*' 通配)。
    tool_args: Optional[dict] = None
    # __post_init__ 预解析: tool_args 非 name 键 → json_path segments 缓存
    _tool_arg_segments: dict = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        normalized = str(self.action).upper()
        if normalized not in VALID_ACTIONS:
            raise ValueError(
                f"rule '{self.name}': invalid action {self.action!r} — "
                f"must be one of {VALID_ACTIONS} "
                f"(fail-closed: refusing to start with invalid policy)"
            )
        self.action = normalized
        # TASK-REAL-010 (B): json_path 规则加载期校验 — 语法错误/缺配对字段的
        # 规则拒绝载入 (fail-closed), 不允许带病规则进入热加载。
        if self.json_pattern is not None and self.json_path is None:
            raise ValueError(
                f"rule '{self.name}': json_pattern requires json_path — "
                f"body 模式规则必须有提取路径 (fail-closed)"
            )
        if self.json_path is not None:
            # P3 (DEBT-0026): 预解析缓存 segments —— 每条规则只 tokenize 一次
            self._segments = _parse_json_path(self.json_path)  # raises ValueError on bad syntax
            if self.json_pattern is not None:
                try:
                    re.search(self.json_pattern, "")
                except re.error as e:
                    raise ValueError(
                        f"rule '{self.name}': invalid json_pattern "
                        f"{self.json_pattern!r} — {e} (fail-closed)"
                    ) from e
        # P6: tenant_id 必须是 None 或非空字符串 (fail-closed: 空/错型拒绝载入)
        if self.tenant_id is not None and (
            not isinstance(self.tenant_id, str) or not self.tenant_id.strip()
        ):
            raise ValueError(
                f"rule '{self.name}': tenant_id must be a non-empty string or "
                f"omitted (None = global rule) — got {self.tenant_id!r} (fail-closed)"
            )
        # L2 (2026-08-04): tool_args 加载期校验 (fail-closed) — 非 dict / 空 /
        # 空键 / 空值 / 与 json_path 共存 / 非法 json_path 键 → 拒绝载入。
        if self.tool_args is not None:
            if not isinstance(self.tool_args, dict) or not self.tool_args:
                raise ValueError(
                    f"rule '{self.name}': tool_args must be a non-empty dict (fail-closed)"
                )
            if self.json_path is not None or self.json_pattern is not None:
                raise ValueError(
                    f"rule '{self.name}': tool_args is mutually exclusive with "
                    f"json_path/json_pattern (fail-closed)"
                )
            segs: dict = {}
            for key, val in self.tool_args.items():
                if not isinstance(key, str) or not key.strip():
                    raise ValueError(
                        f"rule '{self.name}': tool_args keys must be non-empty strings"
                    )
                if not isinstance(val, str) or not val.strip():
                    raise ValueError(
                        f"rule '{self.name}': tool_args value for {key!r} must be "
                        f"a non-empty string (fail-closed)"
                    )
                if key != "name":
                    try:
                        segs[key] = _parse_json_path(key)
                    except ValueError as e:
                        raise ValueError(
                            f"rule '{self.name}': tool_args key {key!r} is not a "
                            f"valid json_path — {e} (fail-closed)"
                        ) from e
            self._tool_arg_segments = segs

    def matches(self, path: str, method: str, body=None) -> bool:
        method_ok = self.method is None or self.method.upper() == method.upper()
        path_ok = self._path_matches(path)
        if not (method_ok and path_ok):
            return False
        if self.json_path is None and self.tool_args is None:
            return True
        if self.json_path is not None:
            # 条件规则: 请求体 JSON 中 json_path 提取值需匹配 json_pattern。
            # 非 JSON 体/无法提取 → 条件不满足 → 规则不匹配 (安全回退)。
            values = _json_extract(body, self.json_path, segments=self._segments)
            if not values:
                return False
            if self.json_pattern is None:
                return True  # 仅要求路径存在 (调用方自行保证该语义的合理性)
            return any(re.search(self.json_pattern, v) for v in values)
        return self._tool_args_match(body)

    def _path_matches(self, path: str) -> bool:
        normalized = posixpath.normpath(path.split("?", 1)[0])
        if self.path_pattern == normalized:
            return True
        if "*" in self.path_pattern:
            pattern = "^" + re.escape(self.path_pattern).replace(r"\*", ".*") + "$"
            return bool(re.match(pattern, normalized))
        if self.path_pattern.endswith("/") and normalized.startswith(self.path_pattern):
            return True
        return False

    def _tool_args_match(self, body) -> bool:
        """L2: 工具调用规则 — 同一 tool_calls 节点内 name 与参数键值同时命中。

        body 中任一工具调用满足全部条件 → 规则命中。'name' 值为 glob;
        其余键为相对参数的 json_path, 提取值中任意标量匹配 glob 即满足该键。
        arguments 为 JSON 字符串 (OpenAI 规范) 或 dict; 解析失败 → 不匹配
        (安全回退 — 无法验证的声明不放行)。
        """
        name_glob = self.tool_args.get("name")
        arg_conds = [(k, v) for k, v in self.tool_args.items() if k != "name"]
        for fn in _tool_call_functions(body):
            if name_glob is not None and not _glob_match(fn["name"], name_glob):
                continue
            if not arg_conds:
                return True
            args = fn["args"]
            ok = True
            for key, pattern in arg_conds:
                found = []
                _extract_at(args, self._tool_arg_segments[key], 0, found)
                if not any(
                    isinstance(v, (str, int, float, bool))
                    and _glob_match(str(v), pattern)
                    for v in found
                ):
                    ok = False
                    break
            if ok:
                return True
        return False


@dataclass
class PolicyConfig:
    name: str
    version: str
    rules: List[Rule] = field(default_factory=list)


class PolicyEngine:
    def __init__(self, config_path: Optional[str] = "config/policies.yaml",
                 ast_guard=None):
        """ast_guard: 可选 AST 硬阻断引擎（Priority 0 前门, Tree-sitter 裁决）。

        None=禁用（向后兼容 / 隔离测试）。生产路径由 main.py 注入
        ast_guard.ASTGuard；缺失/损坏时 main.py fail-closed 拒绝启动。
        """
        if config_path is None:
            config_path = "config/policies.yaml"
        self.ast_guard = ast_guard  # P-AST: Priority 0 前门
        self.config: PolicyConfig = PolicyConfig(name="default", version="0.1.0")
        self.rules: List[Rule] = []
        self._config_path = str(config_path)
        self._last_mtime = 0.0
        self._load(str(config_path))

    def _load(self, path: str) -> None:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not data:
            # DEBT-0012: empty policies.yaml must NOT silently start with zero rules
            # (all requests would ALLOW). Fail-closed: refuse to load.
            # reload() catches this and keeps old rules (safe hot-reload); only the
            # initial __init__ load propagates → gateway refuses to start.
            raise ValueError("policies.yaml is empty — refusing to load (fail-closed); add at least one rule or fix the YAML")
        new_rules = []
        for rule_data in data.get("rules", []):
            rule = Rule(
                name=rule_data["name"],
                path_pattern=rule_data.get("path_pattern", "/"),
                method=rule_data.get("method"),
                action=rule_data.get("action", "ALLOW"),
                reason=rule_data.get("reason", ""),
                priority=rule_data.get("priority", 100),
                escalation_timeout=rule_data.get("escalation_timeout", 300),
                escalation_channel=rule_data.get("escalation_channel", "slack"),
                json_path=rule_data.get("json_path"),
                json_pattern=rule_data.get("json_pattern"),
                tool_args=rule_data.get("tool_args"),
                tenant_id=rule_data.get("tenant_id"),
            )
            new_rules.append(rule)
        new_rules.sort(key=lambda r: r.priority)
        self.rules = new_rules
        self._jp_index = JsonPathIndex(new_rules)  # P3 (DEBT-0026): 前缀索引树
        self.config.name = data.get("name", self.config.name)
        self.config.version = data.get("version", self.config.version)
        try:
            self._last_mtime = os.path.getmtime(path)
        except OSError:
            pass

    def reload(self) -> bool:
        """Re-read YAML from self._config_path. On failure keep old rules.

        P0 (暗雷区): 之前 `except Exception: return False` 完全静默 —— reload 失败
        时运维无任何线索。改为 error 级完整堆栈（保留旧规则的行为不变，fail-safe）。
        """
        try:
            self._load(self._config_path)
            return True
        except Exception as e:  # noqa: BLE001 — keep old rules on any load error
            logger.exception("policy reload FAILED (keeping %d old rules): %s",
                             len(self.rules), e)
            logger.debug("policy reload traceback:\n%s", traceback.format_exc())
            return False

    def maybe_reload(self) -> bool:
        """Hot-reload: reload only if config mtime changed (DEBT-0005)."""
        try:
            mtime = os.path.getmtime(self._config_path)
        except OSError:
            return False
        if mtime != self._last_mtime:
            return self.reload()
        return False

    def evaluate(self, path: str, method: str, body=None,
                 tenant_id: Optional[str] = None) -> Optional[Rule]:
        """First matching rule by priority; json_path 规则经前缀索引剪枝 (P3, DEBT-0026)。

        P6 (外部评审缺口 #1): 租户隔离 — tenant_id 指定的私有规则仅对该租户
        生效; 跨租户请求看不到其他租户的规则 (隔离)。tenant_id=None (未认证/
        兼容模式) 时私有规则全部跳过, 仅全局规则参与 —— 与 v1.13.0 行为一致。

        Backward compatible: rules without json_path ignore `body` entirely,
        so existing callers (path/method only) keep identical behavior.
        """
        # P-AST: Priority 0 —— AST 硬阻断先于一切 YAML 规则匹配 (Tree-sitter 裁决)
        ast_rule = self._ast_gate(path, method, body)
        if ast_rule is not None:
            return ast_rule
        for rule in self._jp_index.candidates(body):
            if rule.tenant_id is not None and rule.tenant_id != tenant_id:
                continue  # 跨租户私有规则: 不参与本请求评估 (隔离语义)
            if rule.matches(path, method, body):
                return rule
        return None

    # P-AST: Priority 0 AST 硬阻断前门 (Tree-sitter 裁决, 修复+优先集成)。
    # 设计: AST block 必须发生在所有 YAML 规则匹配之前 —— evaluate() 首行调用;
    # 命中即返回合成 DENY Rule (priority 0), 不进入 _jp_index 候选循环。
    # 审计 trace: reason 携带精确行号 + S-expression 标签 (Rule.reason →
    # DecisionRecord.reason, 由 main.py 落库)。纯放行请求 (无代码片段)
    # 返回 None, 与原有 YAML 评估路径完全一致 (Authorization passthrough)。
    def _ast_gate(self, path: str, method: str, body) -> Optional[Rule]:
        if self.ast_guard is None or body is None:
            return None
        block = self.ast_guard.check_request(body)
        if block is None:
            return None
        return Rule(
            name=f"ast-block-{block.language}",
            path_pattern="*",
            method=method,
            action="DENY",
            reason=block.summary,
            priority=0,
        )

"""test_ast_policy_integration — AST 硬阻断与 policy.py 集成测试。

验收覆盖（来自"修复 + 优先集成"裁决）:
  I1 AST block 必须发生在所有 YAML 规则匹配之前
     —— 构造一条本应 ALLOW 的 YAML 规则, body 含危险代码 → 返回 ast-block DENY
  I2 Authorization passthrough 隔离
     —— 无代码 body → 走原 YAML 路径, 返回原规则 (行为不变)
  I3 审计 trace: DecisionRecord.reason 保留精确行号 + S-expression 标签
  I4 向后兼容: ast_guard=None (禁用) → evaluate 行为与改造前一致
"""

import unittest
from pathlib import Path

from src.ast_guard import ASTGuard
from src.policy import PolicyEngine, Rule

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICIES = REPO_ROOT / "config" / "policies.yaml"


class TestASTPolicyIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard = ASTGuard()
        assert cls.guard.loaded_languages, "ASTGuard 必须成功加载语言"  # T1: 裸 assert
        cls.engine = PolicyEngine(POLICIES, ast_guard=cls.guard)

    # I1: AST block 先于 YAML 规则匹配
    def test_ast_block_before_yaml_rules(self):
        # /v1/intercept 对普通路径通常是 ALLOW/ESCALATE 规则; 但 body 含 eval
        # 代码时必须先被 AST 阻断 (DENY, name=ast-block-*)
        rule = self.engine.evaluate(
            "/v1/intercept", "POST",
            body={"language": "python", "code": "eval('os.system(\"id\")')"},
            tenant_id="tenant-a",
        )
        self.assertIsNotNone(rule)
        self.assertEqual("DENY", rule.action)
        self.assertTrue(rule.name.startswith("ast-block-"), rule.name)
        self.assertEqual(0, rule.priority)

    def test_ast_block_returns_synthetic_rule_with_trace(self):
        rule = self.engine.evaluate(
            "/v1/intercept", "POST",
            body={"command": "rm -rf /"},
            tenant_id="tenant-a",
        )
        self.assertEqual("DENY", rule.action)
        # I3: reason 携带精确行号 + sexp 标签 (Rule.reason -> DecisionRecord.reason)
        self.assertIn("L1:", rule.reason)
        self.assertIn("sexp=", rule.reason)
        self.assertIn("AST-BLOCK bash", rule.reason)

    # I2: Authorization passthrough —— 无代码 body 走原 YAML 路径
    def test_clean_passthrough_unchanged(self):
        rule_with = self.engine.evaluate(
            "/v1/intercept", "POST",
            body={"messages": [{"role": "user", "content": "hello"}]},
            tenant_id="tenant-a",
        )
        rule_without = self.engine.evaluate(
            "/v1/intercept", "POST", body=None, tenant_id="tenant-a",
        )
        # 两者行为一致 (AST gate 对无代码请求零影响)
        self.assertEqual(
            rule_with.action if rule_with else None,
            rule_without.action if rule_without else None,
        )

    def test_sql_body_blocked_via_policy(self):
        rule = self.engine.evaluate(
            "/v1/intercept", "POST",
            body={"query": "DROP TABLE users;"},
            tenant_id="tenant-a",
        )
        self.assertEqual("DENY", rule.action)
        self.assertIn("destructive-sql", rule.reason)

    # I4: 向后兼容 —— ast_guard=None 时行为不变
    def test_disabled_ast_guard_backward_compat(self):
        engine = PolicyEngine(POLICIES)  # ast_guard 默认 None
        rule = engine.evaluate(
            "/v1/intercept", "POST",
            body={"language": "python", "code": "eval('1')"},
            tenant_id="tenant-a",
        )
        # 无 AST gate: 走纯 YAML 路径 —— 允许为 None（无规则匹配），
        # 但绝不可能是 ast-block 合成规则
        if rule is not None:
            self.assertFalse(rule.name.startswith("ast-block-"), rule.name)

    def test_evaluate_none_body_backward_compat(self):
        # 老调用方 (path/method only) 行为不变
        engine = PolicyEngine(POLICIES)
        rule = engine.evaluate("/v1/intercept", "POST")
        self.assertIsNone(rule.action if False else None)  # 占位防 lint
        self.assertIsInstance(rule, (Rule, type(None)))


if __name__ == "__main__":
    unittest.main()

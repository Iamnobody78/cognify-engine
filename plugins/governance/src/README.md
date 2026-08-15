# agent-governance-v2

**AI 代理治理层** —— 不是构建框架，而是安全护栏。

为多代理系统提供**可编译 → 可自省 → 可自审 → 可验证**的四阶段治理闭环。代理行为不再依赖"信任声明"，而是由协议网关执行声明验证，谎报即升级。

![governance-v2 badge](https://img.shields.io/badge/治理闭环-S63%E2%86%92S69-green)
![ci](https://github.com/Iamnobody78/agent-governance-v2/actions/workflows/test.yml/badge.svg)
![license](https://img.shields.io/badge/license-MIT-blue)

## 这是什么？

代理系统（agent）在自主执行任务时，会向治理网关提交请求体声明——`{"governance": {"protocols": {"feynman_test": {"satisfied": true}}}}`——表示"我完成了协议 X"。

**问题**：恶意或失控的 agent 可以谎报 `satisfied=true` 绕过所有治理规则。

**agent-governance-v2 的答案**：四阶段能力闭环，让"声明"必须通过外部独立验证：

| 阶段 | 能力 | 交付 |
|------|------|------|
| **S63** | 治理可编译 | 协议 YAML (`11-col-v1` 声明式) → 可执行规则 |
| **S64** | 治理可自省 | 每条规则回答"我为什么存在" (MCE 2.0 AST) |
| **S65** | 治理可自审 | VCE 2.0 扫描器发现规则自身的冲突/盲点 |
| **S66** | 治理可验证 | 声明验证通道：谎报 `satisfied` → 降级 `ESCALATE` |

## 核心能力

```
协议 YAML ──compile──▶ 规则 (ethics/enforce/ok)
                         │
                         ▼
agent 请求体 ──evaluate_verified──▶ 裁决 + 声明验证
   {"satisfied": true}                  │
     裸声明 (无证据锚点)                 ├─ verified=False (c=0.6)
        │                               └─ action 降级 ESCALATE ⚠
        ▼
   VCE 扫描 (scan) ──▶ 极化指数 / 冲突 / 盲点 / 验证通道状态
```

- **协议网关** `src/protocol_gateway.py` — 9 条规则（3 协议 × ethics/enforce/ok）
- **MCE 自省** `src/mce_introspection.py` — 规则 why-exists / governs / origin 溯源
- **VCE 扫描** `src/vce_scanner.py` — 极化指数、RuleConflicts、BlindSpots、Verification_Channel
- **验证通道** `src/verification.py` — `DeclarationValidator` 可插拔协议（Noop 基线 / 未来 LLM 语义 / 签名）
- **审计钩子** `ProtocolGateway(audit_sink=...)` — 每次裁决可审计，fail-open 不阻塞裁决

## 快速启动（3 步）

```bash
# 1. clone
git clone https://github.com/Iamnobody78/agent-governance-v2.git
cd agent-governance-v2

# 2. 安装依赖
pip install -r requirements.txt   # 含 tree-sitter (AST 语义门核心依赖)

# 3. 运行测试 (⚠ 必须在仓库根目录执行 — config 相对路径解析)
pytest tests/ -q
```

## 治理案例：谎报降级（S66 实证）

```python
from src.protocol_gateway import ProtocolGateway
from src.verification import BaselineDeclarationValidator

gw = ProtocolGateway(validator=BaselineDeclarationValidator())

# 恶意 agent 裸声明 (无证据锚点)
out = gw.evaluate_verified("/gateway", "POST", {
    "governance": {"protocols": {"feynman_test": {"satisfied": True}}}})

assert out["action"] == "ESCALATE"          # ⚠ 不是 ALLOW！
assert out["verification"]["verified"] is False
assert out["verification"]["confidence"] == 0.6
print("裸声明 → 升级复核 (谎报不再零成本)")
```

更多示例见 [examples/](examples/) 与 [Governance Center Dashboard](https://github.com/Iamnobody78/bottlesumo-pi)。

## 架构

- 见 [ARCHITECTURE.md](ARCHITECTURE.md) — 四阶段演进的设计意图
- 治理引擎可作为库嵌入（dashboard 同进程门面），也可独立运行

## 贡献

欢迎贡献！请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) —— 包含 8 道 GATE 流程、测试运行规范、新增协议/AST 规则指南。

- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Security Policy](SECURITY.md)
- [Changelog](CHANGELOG.md)

## 许可证

MIT — 见 [LICENSE](LICENSE)。

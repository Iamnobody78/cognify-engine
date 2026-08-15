# META_CAPABILITIES.md — 元能力自检清单与诚实声明（P11）

> 原则：**诚实声明，可验证证据**。每一项都标注真实状态（✅ 已具备 / ⚠️ 部分具备）
> 并给出可复核的证据路径。**绝不声称不具备的能力**（架构开篇原则）。
>
> 自检时间：2026-08-03 · 快照 v1.20.0 · AUDIT-0040

## 自检清单

| 元能力 | 定义 | 当前状态 | 证据（可复核） |
|--------|------|----------|----------------|
| **自审计** | 代码能审计自身 | ✅ 已具备 | `src/critic/` 五批判者 + GATE 8（`python -m src.critic.runner`，5/5 PASS） |
| **自修复** | 根据审计报告自动修正 | ✅ 已具备 | `src/agent_tools/self_heal.py`（`validate_candidate` 防御性修复，`deployable=False` 才触发——修正必须经人类合并） |
| **自追踪** | 代码能追溯自身因果链 | ✅ 已具备 | `src/storage.py::get_trace()`（`GET /v1/trace/{trace_id}` 返回决策因果链） |
| **自认证** | 代码能签名自身 | ✅ 已具备 | `src/certification/`（ED25519 sign/verify，fail-closed，见 [CERTIFICATION.md](CERTIFICATION.md)） |
| **自生成** | 代码能生成代码 | ✅ 已具备（P11 补全） | `src/codegen/`（YAML 策略 → Python 匹配函数，编译式生成）+ `tests/test_codegen.py` 38 测试（含 16 项与运行时 PolicyEngine 的等价性测试）+ `policy_sync.py --generate` 漂移自愈 |
| **自修改** | 代码能修改自身 | ⚠️ 部分具备 | `agent_tools` 生成修正建议 + codegen 重写生成物；**修改合并需人类确认**（诚实边界：无自主提交权限） |
| **自部署** | 代码能部署自身 | ⚠️ 部分具备 | CI 自动化（GATE 1-8）自动验证；**推送需人类触发**（诚实边界：无自主 push） |

## "自生成"的诚实边界（P11 补全声明）

`src/codegen/generator.py` 是**编译式生成器**（约 100 行），不是 LLM 任意代码合成：

- **做什么**：把 `config/policies.yaml` 的声明式规则（path glob + json_path 正则）
  编译为可执行匹配函数模块 `src/codegen/_generated_matches.py`（每条规则一个
  `match_<name>()` + 主入口 `match_any()`）。
- **不做什么**：不生成业务逻辑、不替换运行时启发式
  （`src/danger.py` 的 DANGEROUS_PREFIXES / DANGEROUS_TOOL_NAMES 仍是运行时的
  第一道闸）、不生成 README/文档。
- **正确性保证**（非声称）：
  1. 确定性 + 幂等（同输入同输出；`tests/test_codegen.py::test_regeneration_is_idempotent`）；
  2. **运行时等价性**（`TestRuntimeEquivalence` 16 项：生成 `match_any` 结果 ==
     `PolicyEngine.rules[].matches` 结果——语义复刻自 `src/policy.py::_path_matches`
     与 `_json_rule_matches` 的三种分支）；
  3. 漂移自愈（`policy_sync.py` 默认检测生成物过时 → exit 1；`--generate` 自动重写）。

## "部分具备"的诚实边界（不补全的理由）

- **自修改 ⚠️**：系统能产出修正建议与重写产物，但**不拥有自主提交/合并权限**——
  人类在环（human-in-the-loop）是有意设计（裁决门），不是缺陷。补全"自主修改"
  会破坏本仓库的治理流程（AUDIT 链要求每次变更经裁决）。
- **自部署 ⚠️**：CI 能自动验证，但推送由人类触发——同上，防止无人值守的
  自动发布风险。

## 元能力之间的依赖（供 P12 自举运行时参考）

```
自追踪 ──→ 自审计 ──→ 自修复（建议）──→ 自修改（人类合并）──→ 自部署（人类推送）
   │                                          ↑
   └──→ 自生成（P11 补全：策略→代码）─────────┘
   └──→ 自认证（对任何产物签名，防伪造）
```

P12 若要实现"自举运行时"，前置依赖为：自生成（✅ 已备）+ 自认证（✅ 已备）
+ 自修改（⚠️ 需人类裁决——P12 设计必须定义"哪些修改可自动、哪些必须裁决"）。

## 验证命令

```bash
# 自生成证据
python -m pytest tests/test_codegen.py -q        # 38 passed（含运行时等价性）
python scripts/policy_sync.py                     # exit 0 = 生成物无漂移
python scripts/policy_sync.py --generate         # 漂移时自动重写（自愈演示）

# 其余能力证据
python -m src.critic.runner                       # 自审计：GATE 8 5/5 PASS
python -m pytest tests/test_certification.py -q  # 自认证：9 passed
```

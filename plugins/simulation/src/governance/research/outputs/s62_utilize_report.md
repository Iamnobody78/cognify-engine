# S.A.M.U.E.L. Utilize Report — Notion 资产 → 代码变更

**Sprint**: 62 | **日期**: 2026-08-10
**R-gate**: experiment phase PASS (2/2)

---

## 1. 代码变更清单

### A1: 协议表 → YAML 规范编译器 (N1 人機協作協議)

| 变更 | 文件 | 说明 |
|------|------|------|
| `compile_protocols()` | `governance/protocols/protocol_compiler.py` | 11 列协议表 → 每模块 YAML（含全部必需字段）|
| `verify_yaml()` | 同上 | yaml.safe_load + 必需字段完整性检查 |
| `demo_records()` | 同上 | 3 个协议模块演示（费曼测试/熵值去噪/逻辑链检查）|
| CLI | 同上 | `--input` / `--output-dir` |

### A2: .aionui 记忆库脚手架生成器 (N3 记忆库设计)

| 变更 | 文件 | 说明 |
|------|------|------|
| `scaffold()` | `governance/memory_scaffold.py` | 5 目录 + README + manifest.json 生成 |
| `verify()` | 同上 | 完整性断言（目录/文件/JSON 合法性）|
| dry-run 模式 | 同上 | 只打印计划不写盘（安全）|
| CLI | 同上 | `--target` / `--dry-run` |

### 引擎扩展 (研究引擎泛化能力验证)

| 变更 | 文件 | 说明 |
|------|------|------|
| `phase_survey_notion()` | `research_orchestrator.py` | Notion 输入 → papers-schema 归一化 → R-gate |
| `--input-type notion` | 同上 | CLI 泛化（arxiv | notion）|

## 2. 单元测试（`governance/tests/test_s62_notion_r1.py` — 7/7 PASS）

| 测试 | 验证点 |
|------|--------|
| `test_compiler_requires_all_11_fields` | 缺字段报 ValueError |
| `test_compiler_writes_valid_yaml` | 3 协议 YAML 全验证 |
| `test_compiler_yaml_roundtrip` | YAML 读回字段完整 |
| `test_scaffold_dry_run_writes_nothing` | dry-run 不写盘 |
| `test_scaffold_full_generation_and_verify` | 5/5 目录 + 16/16 文件 |
| `test_scaffold_manifest_valid_json` | manifest JSON 合法 |
| `test_scaffold_has_expected_dirs` | 5 目录齐全 |

## 3. 设计决策

- **A1 字段集**: 11 列 + 模块名 = 12 必需字段（页面实际 12 字段）
- **A2 verify 计数**: manifest.json 必须计入 files_ok（首版漏计 → 永远 15/16，测试暴露修复）
- **输入路径**: 用户摘要模式（CSR 墙）→ 编译 JSON → orchestrator；诚实标注来源

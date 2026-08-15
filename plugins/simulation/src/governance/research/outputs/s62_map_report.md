# S.A.M.U.E.L. Map Report — Notion 资产 → 工程文件映射

**Sprint**: 62 | **日期**: 2026-08-10
**输入**: `s62_assess_report.md`（A1 协议编译 + A2 记忆库脚手架）

---

## 1. 映射矩阵

### A1: 协议表 → YAML 规范编译器 (N1)

| 维度 | 映射 |
|------|------|
| **目标文件** | `governance/protocols/protocol_compiler.py` + `governance/protocols/schema/*.yaml` |
| **输入** | 11 列协议表（JSON 或 markdown 表格）|
| **输出** | 每个协议模块 → YAML 规范（含 trigger/action/ethics/frequency 字段）|
| **验证** | 编译出的 YAML 可被 `pyyaml` 解析 + 协议字段完整性检查（11 列必需字段）|
| **风险** | 低——纯数据转换 |

### A2: .aionui 记忆库脚手架生成器 (N3)

| 维度 | 映射 |
|------|------|
| **目标文件** | `governance/memory_scaffold.py`（生成 tools/config/context/sessions/templates + README + manifest.json）|
| **设计** | dry-run 模式（只打印结构）+ 实跑模式（生成到目标目录）|
| **验证** | 生成后目录结构断言 + manifest.json JSON 合法性 + README 存在 |
| **风险** | 低——纯文件生成；dry-run 防误写 |

## 2. 接入点审计

| 现有体系 | A1 影响 | A2 影响 |
|---------|---------|---------|
| governance/research/ | 无（协议是独立模块）| 无 |
| .aionui/meta_prompts/ | 无 | 无（生成到 governance/memory/ 演示）|
| FS-GOVERN | 协议 YAML 受治理 | 生成物可被治理扫描 |

## 3. 验收标准

| 标准 | A1 | A2 |
|------|----|----|
| 可运行 | compiler 接受 11 列 JSON → YAML | scaffold dry-run + 实跑 |
| 语法正确 | YAML 可解析 | manifest JSON 合法 |
| 完整性 | 11 必需字段全覆盖 | 5 目录 + README + manifest |
| 测试 | 单测 ≥ 4 | 单测 ≥ 4 |

## 4. 结论

两个 P0 资产映射到明确的文件与验证标准。进入 Utilize 阶段。

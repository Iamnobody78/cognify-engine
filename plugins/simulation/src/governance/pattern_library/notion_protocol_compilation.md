---
name: notion_protocol_compilation
type: research-derived-pattern
symptom_keywords:
  - notion protocol table
  - declarative governance
  - YAML schema
  - 11-column protocol
  - 协议表
  - 声明式治理
parameters:
  trigger: "从协议文档（Notion 11 列表格等）提取可执行治理规范"
  symptom: "协议以文档表格存在，无法被程序引用/验证"
  diagnostic: "表格列含可执行字段（触发条件/操作频率/伦理边界）"
  fix:
    - "定义必需字段集（11 列 + 模块名 = 12 字段）"
    - "每模块编译为 YAML：compile_protocols(records, out_dir) → per-module .yaml"
    - "verify_yaml: yaml.safe_load + 必需字段完整性断言"
    - "缺字段必须 raise ValueError（不静默跳过）"
  counters: "字段缺失静默通过 → 治理规则不完整；manifest 等元数据文件在 verify 中易漏计"
validation:
  metrics: "3/3 协议 YAML 可解析 + 字段完整；单测 7/7"
  sessions: "governance/protocols/protocol_compiler.py + test_s62_notion_r1.py"
  date: "2026-08-10 (Sprint 62)"
  status: "validated"
notes: "来源 notion:N1 人機協作協議; 协议表的可执行字段（trigger/action/ethics/frequency）使其天然可编译为声明式治理规范"

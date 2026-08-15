---
name: memory_scaffold_generation
type: research-derived-pattern
symptom_keywords:
  - memory directory blueprint
  - scaffold generator
  - session recovery
  - context persistence
  - 记忆库
  - 脚手架
  - 会话恢复
parameters:
  trigger: "有目录蓝图（如 .aionui/ 五目录方案）需落地为可执行脚手架"
  symptom: "目录方案以文档存在，无生成器、无完整性验证"
  diagnostic: "蓝图定义明确目录/文件/模板"
  fix:
    - "SCAFFOLD dict 声明目录→文件→模板内容（单一事实源）"
    - "scaffold(target, dry_run) 生成；dry-run 只打印不写盘"
    - "verify(target) 完整性断言：目录数 + 文件数（含 manifest.json！）+ JSON 合法性"
    - "verify 的 files_total 必须与生成清单同源（SCAFFOLD + ROOT_FILES），防漏计"
  counters: "verify 漏计 manifest.json → 永远 15/16 假失败；dry-run 缺失 → 误写盘"
validation:
  metrics: "5/5 目录 + 16/16 文件 + manifest valid；单测 7/7"
  sessions: "governance/memory_scaffold.py + test_s62_notion_r1.py"
  date: "2026-08-10 (Sprint 62)"
  status: "validated"
notes: "来源 notion:N3 Aionui 记忆库设计; 解决'新对话上下文丢失'痛点 — 会话恢复机制（current_state + decision_log 读取）"

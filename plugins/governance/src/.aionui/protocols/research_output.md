# 研究产出落盘协议 (research_output.md)

> 版本: v1.0 · 2026-08-04 · P0 修复（研究产出必须落盘才能进审计/蒸馏/记忆回路）

## 动机

P2 自激活实测暴露上游缺失：gpt-researcher 的完整报告（含 APA 引用）只经 stdout JSON
返回 MCP，**从未落盘** → Critic 审计对象不存在、知识蒸馏无法消费、记忆入库无从谈起。
本协议强制所有研究产出持久化，形成
`研究 → 产出(落盘) → 审计 → 蒸馏 → 记忆` 完整闭环。

## 路径约定

| 项 | 约定 |
|----|------|
| 目录 | `<repo-root>/research_outputs/`（可被 `RESEARCH_OUTPUT_DIR` 环境变量覆盖） |
| 文件名 | `{query_slug}.md`；同 slug 已存在 → 追加 `-2`/`-3` 序号，**绝不覆盖** |
| query_slug | 查询词小写 + 非 `[a-z0-9]` → 连字符，压缩连续连字符，截断 60 字符，空 → `research` |
| 编码 | UTF-8（无 BOM） |

示例：`What is AI governance?` → `research_outputs/what-is-ai-governance.md`

## 数据流

```
research_mcp_server.py  (tools/call run_research)
        │ subprocess (.venv-research python)
        ▼
p2_research_runner.py
        │ 1. 研究成功 → persist_report(): 写 research_outputs/{slug}.md
        │ 2. stdout 单行 JSON (契约不变, 新增字段):
        │    {"ok":true, "report":"...", "sources":N,
        │     "report_path":"<绝对路径|空>", "persist_error":"<原因|空>"}
        ▼
research_mcp_server.py
        │ report_path/persist_error 透传到 tools/call 结果 JSON
        ▼
客户端 (AI 会话 / 脚本)
        │ report_path → Critic 审计 / knowledge_distill / memory 入库
```

## 契约规则

1. **stdout JSON 向后兼容**：`report`/`sources`/`query`/`report_type` 原样保留；
   `report_path`/`persist_error` 为新增补充字段。旧客户端忽略新字段不受影响。
2. **best-effort 落盘**：持久化失败**不阻断**研究结果返回 —
   `report_path=""` + `persist_error=<原因>` 如实上报，由调用方决定处置（如重试或告警）。
3. **持久化成功**：`report_path` 为绝对路径，文件内容与 `report` 字段字节一致。
4. **空报告不落盘**：`report` 空白 → `report_path=""`, `persist_error="报告为空, 跳过落盘"`。
5. **审计回路**：Critic 审计的输入必须是 `report_path` 指向的文件，而非 stdout JSON
   中的 report 字符串（后者仅作传输载体，不承诺保留）。

## 索引更新

- `research_outputs/` 目录自身即索引（文件名=查询 slug，mtime=生成时间）。
- 落盘后如需入知识库：`knowledge_distill.py --root research_outputs/`（文件需带
  frontmatter；见 knowledge/ 协议对 reference 型文件的包装约定）。
- 入记忆：经 Critic 审计通过后，用 `write_memory.py` 写入 `memory/`。

## 边界与诚实声明

- 本协议只保证**落盘存在**，不保证报告**质量**（质量由 Critic 审计判定）。
- `persist_error` 不抛异常、不置 `ok=false` — 这是有意设计：研究本身成功，
  落盘问题应被**可见地**上报而非静默吞掉或阻断全流程。
- 目录未加入 git（运行时产物）；如需版本化报告，复制到 `docs/research/` 再提交。

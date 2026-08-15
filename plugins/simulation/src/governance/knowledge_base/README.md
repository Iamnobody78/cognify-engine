# 元教育知识库 (Meta-Education Knowledge Base)

> 状态：ACTIVE · AFFiNE-import-ready · 自托管主权在 `bottlesumo_pi/governance/knowledge_base/`
> 维护协议：META-KB v1.0（R.E.A.D. 四步法）· 内容源诚实声明见各页面元数据

## 知识库结构

```
knowledge_base/
├── MMCE/                  # 元模型控制工程 (Notion 链接内容迁移)
├── CVE-S/                 # 认知操作系统协议栈 (MCE 2.0 + VCE 2.0 + CEE)
├── Sprint_Reports/        # Sprint 报告归档 (索引 → docs/msan/)
├── Failure_Patterns/      # 失败模式库 (FP-RL / FP-MSAN / FP-NEG)
├── Engineering_Rules/     # 工程规则库 (索引 → engineering_rules.md)
└── Architecture/          # 架构描述 (索引 → meta_harness/architecture_export/)
```

## 导入 AFFiNE（两种方式）

方式一：Web 界面
1. 打开 AFFiNE（自托管实例或 app.affine.pro）
2. Import → Markdown → 上传本目录
3. 自动解析并重建文档结构

方式二：API（需 workspace token 后启用）
```python
# 见 meta_kb.py --import-affine 子命令（配置 AFFINE_API/AFFINE_TOKEN 后可用）
```

## 与既有协议联动
| 协议 | 联动 |
| :--- | :--- |
| META-EDU | 本库存储 MCE/VCE/CEE 协议实现 |
| TRACE-AGENT | 本库存储可追溯决策记录索引 |
| META-ARCHITECT | Architecture/ 引用其导出 |
| HONEST-BOUNDARY | 每个页面含"内容源/数据边界"元数据 |

## 数据边界声明 (HONEST-BOUNDARY)
- Notion 链接 `app.notion.com/p/*` 需要工作区登录 + JS 渲染，**无法程序化抓取**（实证：HTTP 200 但页面为 JS 壳，0 CJK 内容字符）
- 内容源 = PM 消息全文（已含 MMCE 完整梳理 + 全部协议文本），迁移自该已审阅摘要
- 任何后续直接抓取尝试必须重新验证

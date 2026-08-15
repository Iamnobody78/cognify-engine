# Notion 网站内容提取 — 2026-08-10

## 状态：✅ 成功提取（PM 提供 notion.site 公开链接后）

PM 提供了 `exciting-fireplant-e07.notion.site` 的 8 个公开页面链接后，
通过 **Notion 公开数据 API**（`/api/v3/loadCachedPageChunk` + `/api/v3/queryCollection`）
成功提取 **218 行**结构化内容，无需浏览器、无需登录。

## 关键 API 用法（可复用的技术配方）

```python
# 1. loadCachedPageChunk 获取页面结构（view_ids + collection_id）
POST /api/v3/loadCachedPageChunk
{"pageId": "<dashed-uuid>", "limit": 100, "cursor": {"stack": []}, "chunkNumber": 0, "verticalColumns": false}

# 2. queryCollection 获取数据库行数据
POST /api/v3/queryCollection
{
  "collectionView": {"id": "<view_id>", "spaceId": "<space_id>"},
  "collectionViewBlock": {"id": "<dashed-page-id>", "spaceId": "<space_id>"},  # ← 必须 dashed 格式！
  "clientType": "notion_app", "userTimeZone": "Asia/Shanghai",
  "isFullScreen": false, "isMobile": false
}
```

**坑点**：
- `collectionViewBlock` 必须用**带连字符的 dashed UUID**（页面 block id 本身）
- 不能传 `source`/`query` 字段（会 400 ReducerlessQueryMissingRecordError）
- 反爬只在浏览器 JS 层；API 端点 urllib 直连可通
- spaceId: `d4622db6-0a61-8171-9b78-000325aae69d`

## 8 个页面清单

| # | 页面 | 行数 | 内容 |
|---|------|------|------|
| 01 | 10-META | 50 | Velxio/Renode 仿真评估等 |
| 02 | META-KB | 50 | **人机协作协议库（13列）** ← 核心 |
| 03 | MMCE | 23 | Agent 自我迭代+净化系统 |
| 04 | MEF-OS | 50 | 元模型控制工程 OS |
| 05 | LINK-LEARN | 3 | 认知模型病理学 prompts |
| 06 | Anti-Drift | 8 | NLP/语义扩展/语境构建工程 |
| 07 | Diamond | 17 | 批判性思维工程、奥坎姆剃刀 |
| 08 | 5-Prompts | 17 | 认知战分析 prompts |

## 02-META-KB 人机协作协议库（50 条，最有价值）

13 列 schema：協議模組/觸發情境/核心目的/實作策略/自我檢核／倫理邊界/預期產出-判斷指標/層級/分類/人機協作指令（提示詞模板）/元認知提問（AI 自問）/來源對應/人機協作指令（自然語言）

代表性模块：
- **L0-L9 认知层级协议**（认知作业系统层级）
- **CVE-S 三螺旋内核**：MCE 2.0 元模型控制 / VCE 2.0 价值控制 / CEE 2.0 认知演化
- **高维引擎序列**：7元/14元/21元/28元变量耦合引擎
- **协作总则**：元认知优先/模型显性化/多视角并行/分层回应
- **认知模型病理学**：强迫性过度拟合、模型解离与多重人格防御

## 数据文件

- `notion_all_content.json` — 全部 218 行原始结构化数据
- `notion_all_content.md` — Markdown 版
- `notion_kb_protocols.json` — 50 条协议模块（提炼后）
- `notion_site_results.json` / `notion_page*.html` — 验证产物

## 对 META-KB 的影响

PM 的 Notion 网站是 META-KB 的**权威来源**，与本地知识库的差距：
1. 本地 `meta_harness/` 有 MEF-OS/MMCE/anti-drift，但**缺 L0-L9 层级协议细节**
2. 本地缺 **14/21/28元变量引擎** 与 **CVE-S 三螺旋闭环** 的完整定义
3. 提示词模板列（人机協作指令）是本地知识库没有的**可直接用资产**

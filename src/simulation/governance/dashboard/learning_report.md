# SEED-ROUND-1 学习报告 (learning_report.md)

> **Phase D: Deploy & Learn** 输出 | SEFS-ARCH v1.0 | 2026-08-05
> 任务：MCP 服务器监控仪表板（React + FastAPI + SQLAlchemy）

---

## 1. 部署状态

| 项 | 结果 |
| :--- | :--- |
| 后端启动 | ✅ uvicorn 8010 端口，7/7 API 端点 200 OK |
| 数据装载 | ✅ seed.py: usage=52 hypotheses=43（与源 jsonl 精确匹配） |
| 前端构建 | ✅ vite build 成功（dist 产出，仅 chunk size 警告） |
| 生产形态 | ✅ docker-compose.yml（postgres + backend + frontend/nginx），环境具备 PG 时可用 |
| 端到端验证 | ✅ 健康聚合/延迟分布/假设命中率与原始 jsonl 交叉校验一致 |

## 2. 持续学习：持久行为规则（追加至 engineering_rules.md）

| 规则 ID | 规则 | 来源 |
| :--- | :--- | :--- |
| RULE-FS-001 | **jsonl 数据字段必须先侦察再解析**：加载前用脚本统计字段类型/ts 格式/枚举值分布，再写 ETL。本循环 hypotheses 的 `score` 实为 dict（`{'winrate':..,'steps':..}`）、`ts` 为 `YYYYMMDD_HHMMSS` 非 ISO——若先解析会 100% 失败 | SEED-1 失败#1 |
| RULE-FS-002 | **SQLite 内存库测试必须共享连接（StaticPool）**：`:memory:` 默认每连接独立，多线程/多请求会看到空表 | SEED-1 失败#2 |
| RULE-FS-003 | **pytest conftest 不参与模块导入**：测试文件不得 `from conftest import ...`；共享常量放 fixture 或独立 helpers 模块 | SEED-1 失败#3 |
| RULE-FS-004 | **后端聚合精度 ≥ 6 位小数**：`round(x, 4)` 产生 ~2e-5 误差会挂掉严格容差断言；success_rate 用 6 位 | SEED-1 失败#4 |
| RULE-FS-005 | **失败分类记录**（规格缺失/设计缺陷/实现错误/测试遗漏）：本循环 4 次失败全部为「实现错误-数据格式假设」与「测试基础设施」，无规格缺陷 → 说明 Phase S 规格覆盖良好 | SEED-1 回顾 |

## 3. 失败模式归档（failure_patterns.md 更新）

| 模式 | 表现 | 对策 |
| :--- | :--- | :--- |
| FP-FS-001 数据格式假设 | 假设 ts 是 ISO、score 是数值，实际是自定义格式/dict | 先侦察（见 RULE-FS-001） |
| FP-FS-002 内存库连接隔离 | SQLite :memory: 每连接独立，测试偶发空表 | StaticPool 共享连接 |
| FP-FS-003 测试基础设施陷阱 | conftest 导入、sessionmaker.remove() 不存在 | fixture 化 + db.close() |

## 4. 可复用资产

- **ETL seed.py**：`python seed.py [--usage PATH] [--hyp PATH] [--db-url URL]`，幂等（TRUNCATE 重灌）
- **API 契约**：6 端点 + OpenAPI 自动文档（/docs）
- **前端组件**：HealthCards / LatencyTable / UsageTimeline / HypothesisPanel（可复用为治理门户基础）

## 5. 待办（下轮 SEED）

- [ ] PostgreSQL 实际部署验证（需 Docker daemon 或本机 PG）
- [ ] 前端单测（F-01/F-02，本轮因时间未执行——环境允许时补齐）
- [ ] 实时刷新（WebSocket/polling）使仪表板真正"实时"

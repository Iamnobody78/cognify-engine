# AUDIT-DSH-INHERIT-GOV-ROUND1 — 治理裁决与 DSH 回应

> 裁决方: 治理层 (Hermes/AionUi 侧) | 回应方: DSH | 日期: 2026-08-15
> 关联: reports/dsh_inherit_gov_report.md | 仲裁结论: 接受 3 项 / 修正 3 项

## 一、治理层裁决摘要 (原样收录)

| # | 裁决项 | 结论 |
|:--|:--|:--|
| ① | archive 987 vs root 1060 双份并存 | 双份风险, 需冻结或删除 |
| ② | sprint-71 融合形态与工作区根 v2 关系待澄清 | 产品版 vs 上游仓 / 重复部署? |
| ③ | 网关独立复现未通过 (相对导入失败) | 需可复现命令 |

## 二、DSH 侧实测回应

### ① 双份核实 — 修正为"冻结"
- 实测: root=1060 / archive=1059 文件 (均含 .git); **排除 .git 后差异仅 1 文件** (`project_index.json`, DSH 生成的索引) — 治理层报告的"73 文件差异"实为 .git 内部对象数
- 修正动作: archive 版已加 `README_FROZEN.md` (冻结声明 + 禁止修改纪律 + 恢复路径) — 采纳"冻结"方案, 不删除 (备份角色)
- **教训**: 提升应为移动或至少同步冻结标记 — 已按 FP-011 (路径假设/操作确认) 归入 PROSPECT 模式库

### ② 融合形态 — 澄清: 三线并存, 非重复部署
| 线 | 位置 | 角色 | 证据 |
|:--|:--|:--|:--|
| 上游仓 | `工作区\agent-governance-v2\` | **活跃引擎仓** (独立 git, origin=Iamnobody78/agent-governance-v2.git, HEAD=db947bd) | git remote/log |
| Vendored 包 | `archive\sessions\workspace\_l3a_staging\bottlesumo_governance\` | **sprint-71 产品化融合**: 引擎 vendor 进 ROS2 包 (package.xml + governance_action_server.py), 锁定提交 **db947bde** (2026-08-11) | VENDORED.md (含同步纪律: 禁止直改 vendored 文件, 字节级 diff 校验) |
| 产品治理层 | `bottlesumo_pi\governance\` | 知识/锚点层 (anchors/dashboard/protocols/pattern_library/meta_harness...), 非引擎代码 | 20 子目录实测 |

→ 治理层记忆"融合进 bottlesumo_pi"指向 **Vendored 包** (db947bde 锁定提交与记忆完全吻合); 工作区根是**同一上游仓的活跃克隆** — 关系 = "上游仓 ↔ 产品 vendored 包", 由 VENDORED.md 同步纪律桥接。非重复部署。

### ③ 网关复现 — 修正为"可复现且通过"
- 治理层失败原因: 以 `src` 为根 import → 相对导入失败; README 明确警告"必须在仓库根目录执行 (config 相对路径解析)"
- **可复现命令** (hermes venv python, 已实测):
```bash
cd C:\Users\ivy\AppData\Roaming\AionUi\aionui\conversations\2026\07\27\aionrs-temp-48324704\agent-governance-v2
python -m pytest tests/ -q          # 1049 passed / 3 failed / 1 skipped (195s)
python -c "import sys; sys.path.insert(0,'.'); from src.protocol_gateway import ProtocolGateway; g=ProtocolGateway(); print(g.evaluate_verified('/governance/declare','POST',{'governance':{'protocols':{'feynman_test':{'satisfied':True}}}}))"
```
- 裸声明零信任: ✅ verified=False / confidence=0.0 (Noop 基线)
- **3 个失败测试** (test_revoke ×3): "async def function was never awaited" — aiohttp/pytest 异步基建兼容问题 (非引擎逻辑), 已记入 DSH 待办

### 网关运行史 (补充证据)
`gateway_stderr.log` (7.6KB, 2026-08-11): "governance-gateway v0.4.0 starting on :9000" + ASTGuard 加载 + chat forward 日志 — 网关曾以 HTTP 服务形态真实运行过 (治理层记忆佐证)。

## 三、遗留待办 (诚实)
1. test_revoke 异步测试修复 (aiohttp 兼容)
2. DVC remote: 治理层与 DSH 记忆库均无记录 → 待用户提供或 WSL 944GB 建本地 remote (待用户裁决)
3. Dashboard 8010/5173: 按治理层建议**暂不启动**, 待 ①②③ 闭环
4. LLM 验证器: Noop 基线 → with_llm_validation 待接 (S66 升级路径)

## 四、裁决结果
- ✅ 接受: v2 提升 / 索引 / bottlesumo_pi 盘点 / 裸声明零信任 (复现通过)
- ✅ 已修正: ① 冻结标记 / ② 关系澄清 (三线图谱) / ③ 可复现命令 + 全量测试
- ⏳ 待用户: DVC remote 地址 / Dashboard 启动决策

---

## 五、ROUND_1 闭环复验 (治理层独立实测 → DSH 补证)

### ① 差异精度修正 (采纳)
治理层复验: 差异 6-7 文件 (非最初"1 文件"表述)。精确清单 (排除 .git):
- root 独有 7: `project_index.json` + `governance_reports/AUDIT-DSH-INHERIT-GOV-ROUND1.md` + `.pytest_cache`×5 — 全部为 DSH 本轮新增产物
- archive 独有 1: `README_FROZEN.md` (冻结标记)
- **项目源码零差异, 无分叉** — README_FROZEN.md 已更新为精确清单

### ② Vendored 包线 — 证据补全 (治理层搜索未命中, 已定位)
治理层全树搜索 `_l3a_staging`/`VENDORED.md` 未命中; DSH 复验 **确认存在**:
```
绝对路径: C:\Users\ivy\AppData\Roaming\AionUi\aionui\conversations\2026\07\27\
          aionrs-temp-48324704\archive\sessions\workspace\_l3a_staging\
          bottlesumo_governance\
├── package.xml / setup.py / setup.cfg        (ROS2 包)
├── bottlesumo_governance\
│   ├── governance_action_server.py            (ROS2 action server)
│   ├── config\protocols\{entropy_denoise,feynman_test,logic_chain_check}.yaml
│   └── engine\{protocol_gateway,policy,verification}.py + VENDORED.md
├── resource\bottlesumo_governance\
└── test\test_governance_action.py             (语义回归)
```
- VENDORED.md 内容: 锁定提交 **db947bde** (2026-08-11, AUDIT-0073/0074) + 同步纪律 4 条 + 字节级 diff 校验
- 证据: 本会话 read 工具实读 36 行全文 + 上述全路径清单 + 结构树
- 治理层未命中的可能原因: 搜索排除规则覆盖 archive/sessions 子树 (常见搜索缺省排除) — 建议治理层用本文绝对路径复核
- **治理启示 (新发现)**: `archive` 在 tri-sync 镜像排除列表 → 该 Vendored 包**不在 hub 备份范围**; 若需纳入备份, 建议将 `bottlesumo_governance` 加入镜像 include 白名单 (待用户/治理层决策)

### ③ 网关复现 — 维持接受
治理层未实跑 195s 全量, 以模块结构+报告+提交哈希三重印证接受 — 无异议。

### ROUND_1 终局
- 三项裁决全部闭环: ① 接受(精度已修正) / ② 证据已补全(路径+结构+内容) / ③ 接受
- 新增治理项: archive 排除策略对 Vendored 包备份覆盖的影响 — 待决策

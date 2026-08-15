# Security Policy

## 支持的版本

| 版本 | 支持状态 |
|---|---|
| main (v2.0.0 起) | ✅ 积极维护 |
| v1.x | ❌ 已归档（仅安全通知） |

## 报告漏洞

**本仓库是"AI 代理治理"的旗舰演示**——治理绕过/谎报/审计绕过类漏洞具有最高优先级。

### 处理流程

1. **不要**开公开 issue（治理绕过细节是敏感信息）
2. 向治理引擎仓库报告：`https://github.com/Iamnobody78/agent-governance-v2/security/advisories`
3. 或通过仓库 Discussions 私信维护者（见 MAINTAINERS.md）
4. 预期响应：**48 小时内确认**，修复版本发布前不公开细节

### 严重性分级

| 级别 | 定义 | 响应时间 |
|---|---|---|
| Critical | 治理绕过（谎报直通 / 审计篡改 / 策略越权部署） | ≤48h |
| High | 未授权策略变更 / 敏感数据泄露 | ≤72h |
| Medium | 裁决不一致（非安全） | ≤1 周 |
| Low | 文档 / 日志问题 | 按迭代节奏 |

## 安全护栏（内置机制）

- **声明验证通道**（S66）：裸 `satisfied=true` → `ESCALATE`（c=0.6），谎报不可零成本
- **部署回滚**：策略热部署带 `.bak` 快照，失败自动回滚
- **路径遍历防护**：`_safe_protocol_name` 正则 `[a-z_][a-z0-9_]*`
- **Schema fail-closed**：协议缺必填字段 → 加载失败，绝不静默放行
- **审计 fail-open**：审计失败不阻塞裁决，但事件本身可观测

## 依赖安全

- Dependabot 每日扫描（`.github/dependabot.yml`）
- CI 固定 tree-sitter 0.21.3（与 tree-sitter-languages 1.5.0 兼容）
- 旗舰主体 140GB 仿真资产在 WSL 侧，不进 git 历史

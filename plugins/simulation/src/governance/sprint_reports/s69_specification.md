# Sprint 69 Specification — 策略编辑器 + 开源治理资产 + CI/CD

- **日期**: 2026-08-10
- **分支**: `feature/s69_cd_github`（自 main 0d9240c = S68 合并 + spring68-closed）
- **PM 指令**: 策略编辑器（P0）+ 开源文档（P0 前置）+ CI/CD 基础设施（CD-GITHUB v1.0）
- **元提示词**: `governance/meta_prompts/CD-GITHUB_v1.md`（C.I.G.O. 四阶段循环）

---

## 1. 范围

### Track 1 — 策略编辑器（P0）
- 后端：`GET /policies/{protocol}/source`、`POST /policies/validate`（零副作用）、`POST /policies/deploy`（422 on invalid + `.bak` 回滚）
- 引擎：`_safe_protocol_name` 路径遍历防护、`validate_protocol`（YAML + 11-col-v1 schema + 临时目录预编译）、`deploy_protocol`（写入+重建网关+快照）
- 前端：PolicyEditorView.jsx（选择器 + YAML 编辑器 + 校验显示 + 部署结果）
- 测试：TestPolicyEditor 9 用例 → 后端 28/28

### Track 2 — 开源治理文档（P0 前置，PM 反复强调）
- agent-governance-v2：README/ARCHITECTURE/CHANGELOG/MAINTAINERS/CONTRIBUTING(基线 450→1042)/YAML issue 表单/PR 模板/examples（feynman 谎报、ethics DENY、VCE 扫描）
- bottlesumo_pi：README（双层定位）/ARCHITECTURE/CONTRIBUTING/LICENSE/SECURITY/CHANGELOG/MAINTAINERS/CODE_OF_CONDUCT/docs(mkdocs)

### Track 3 — CI/CD 基础设施
- `ci.yml`：core 轻量测试（26/26）+ dashboard backend（28/28，双 repo checkout）+ frontend vite build + 汇总门
- `e2e.yml`：Playwright 周扫；`docs.yml`：mkdocs → GitHub Pages；`release.yml`：tag → sdist + frontend bundle
- `codeql.yml` + `stale.yml` + `dependabot.yml`（P1 提前）

### Track 4 — E2E 验证 + GitHub 元数据
- `e2e/e2e_policy_editor.py`：真实 HTTP 全链路 9/9 PASS
- 实测：deploy 写入真实 config 且生成 `.bak` 备份（回滚机制真实工作）

### Track 5 — ⚠️ 重大结构修复（新增）
- 发现：bottlesumo_pi 从未是独立 git 仓库——会话根目录即仓库，`push -u origin main` 推送了整个会话根（`.aionui/` 元数据 64 文件、`msan_data/` 162 文件、harness 工作文件）至 GitHub
- 修复：bottlesumo_pi 目录内重建独立仓库（read-tree 提取子树 + 精确 add + gitignore 7 轮迭代），force push 替换污染历史，删除污染分支

## 2. 验收标准

| AC | 判据 | 结果 |
|----|------|------|
| AC1 | 策略编辑器 validate/deploy/source 三端点可用 | ✅ 28/28 + E2E 9/9 |
| AC2 | 开源资产 P0 清单完整（双仓库） | ✅ 27 文件 |
| AC3 | CI 四件套 + 3 补充 workflow 可运行 | ✅ 本地复刻验证 |
| AC4 | 仓库无会话元数据污染、140GB 不入 git | ✅ force push 修复 |
| AC5 | 后端测试 28/28（CWD=backend + 双 repo 布局） | ✅ 实测 |
| AC6 | 主仓库轻量测试 26/26（纯 Python） | ✅ 实测 |

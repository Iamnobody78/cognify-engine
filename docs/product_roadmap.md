# 产品化路线图 (PRODUCT-ROADMAP v1.0)

| 优先级 | 任务 | 状态 |
|:---|:---|:---|
| P0 | 公开认知服务 API (CVE-S as Service) | ✅ 已完成 (`cognify serve` /mce /vce /cee) |
| P1 | 文档站点 (GitHub Pages) | ✅ 已完成 (本站点) |
| P1 | 外部治理网关 (/governance/evaluate) | ✅ 已完成 |
| P2 | PyPI 发布 + 一键安装 | 🟡 pyproject 就绪, 上传待 PyPI token (请示点) |
| P3 | 插件市场/注册表 | ✅ 仓库自托管注册表 + search/install |

## 验收证据

- P0: `/mce` 返回结构化 JSON (MCE 检测/外化/并行模型)
- P1: 本站点可访问 + `/governance/evaluate` 返回五层裁决
- P3: `cognify plugin search` 返回远程注册表列表

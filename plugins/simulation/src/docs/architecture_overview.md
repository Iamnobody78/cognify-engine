# 架构总纲 (architecture_overview)

> 📌 **权威版本**：[仓库根 `architecture_overview.md`](https://github.com/Iamnobody78/bottlesumo-pi/blob/main/architecture_overview.md)
> 本页为 mkdocs 站点指针页，解决根文档在 GitHub Pages 404 问题（缺陷 D1）。
> 内容同步由 CI 检查（C5: `docs.yml` ARCHITECTURE.md sync check）保障。

## 快速摘要

- **定位**：BottleSumo 旗舰版 v11.11 IndustrialGrade 架构总纲
- **九层架构**：物理层 → 电气层 → 固件层 → 内核层 → 仿真层 → 治理层 → 认知层 → 自我进化层 → 合规层
- **治理闭环**：S63 可编译 → S64 可自省 → S65 可自审 → S66 可验证 → S67-S69 产品化
- **协议模型**：11-col-v1 声明式 YAML（12 必填字段，schema fail-closed）

## 层间关系

完整内容（含各层接口契约、数据流、版本演进历史）请阅读仓库根的权威文档。
此处仅保留导航摘要，避免双源漂移 —— **修改请改根文件，本站自动跟随**（链接直达）。

# AionUi 使用指南 — Cognify Engine 助手 (SELF-ADAPT v1.0)

## 启用

1. **重启 AionUi**（技能与助手注册在启动时加载）
2. 在助手列表中选择 **Cognify Engine**

## 对话示例

| 你说 | 助手执行 |
|------|----------|
| "运行治理评估" + 输入 | `cognify gov --evaluate <输入>` → 五层裁决 |
| "启动认知编译" + 输入 | `cognify cognitive --mce <输入>` → MCE 模型识别 |
| "查看三方同步" | `cognify sync` → 守护/镜像/心跳状态 |
| "查看元能力" | `cognify meta --status` → 25 维状态 |
| "债务扫描" | `cognify debt scan` → 债务库存 |
| "书同文车同轨" | `cognify unity --status` → 统一验证 |

## 能力文件

- 技能: `AppData\Roaming\AionUi\aionui\skills\cognify\SKILL.md`
- 注册: skills 表 (cognify) + assistants 表 (Cognify Engine)

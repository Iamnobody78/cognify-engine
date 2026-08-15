# DSH 使用指南 — Cognify Profile (SELF-ADAPT v1.0)

## 启用

```bash
dsh --profile cognify
```

## 能力

| 命令 | 功能 |
|------|------|
| `cognify gov --evaluate <输入>` | 治理裁决 |
| `cognify cognitive --mce <输入>` | 认知编译 |
| `cognify sync` | 三方同步 |
| `cognify meta --status` | 元能力 |
| `cognify debt scan` | 债务 |
| `cognify unity --status` | 统一验证 |
| `cognify serve` | 认知服务 API (:8080) |
| `cognify plugin list` | 插件平台 |

## 配置位置

- Profile: `~/.dsh/profiles/cognify/` (package.json + cordis.yml + patch + README)
- 元提示词: PERPETUAL-ITERATE / CROSS-LEARN-SYNC / PRODUCT-ROADMAP / SELF-ADAPT / UNIFY-ENGINE

## 说明

- 当前 GUI 会话 (:3080) 运行中; 新会话以 `--profile cognify` 启动即生效。

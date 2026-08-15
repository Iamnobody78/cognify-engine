# 认证层（P8）— ED25519 签名 / 验证指南

> 认证层为治理声明提供**防伪造**地基：任何"某某治理声明 / 快照 / 审计结论"
> 若附 ED25519 签名，则可独立验证其来源与完整性。无签名 = 无证明资格。
> 实现：`src/certification/`（sign.py / verify.py），依赖 `cryptography>=42.0`。
>
> **兼容性边界（2026-08-03 元批判核查后明确）**：本项目签名体系为**项目内闭环**——
> ED25519 与 Git 的 GPG/SSH 签名体系**不兼容**，`git commit -S` 无法使用本项目密钥，
> GitHub 界面不会显示"已验证"签名徽章。本层保证：仓库内文件签名后未被篡改
> （verify 往返校验），**不**提供 GitHub 层级提交签名审计。需要 Git 层签名请另行
> 配置 GPG 或 SSH signing key（与本层互不干扰）。

## 1. 快速使用（CLI）

```bash
# 1) 签名一个文件（首次运行自动生成密钥对并落盘，私钥 chmod 600）
python -m src.certification.sign --file docs/architecture.md
#    → 输出一行 base64 签名（88 字符）

# 2) 验证签名（任何人可用公钥复核）
python -m src.certification.verify --file docs/architecture.md --signature "<上一步输出的签名>"
#    → 输出 OK（exit 0）或 FAILED（exit 1）
```

参数：

| 命令 | 参数 | 默认 | 说明 |
|------|------|------|------|
| sign | `--file` | 必填 | 待签名文件路径 |
| sign | `--private-key` | `~/.governance/private_key.pem` | 私钥路径（不存在则自动生成 PKCS8 PEM） |
| verify | `--file` | 必填 | 待验证文件路径 |
| verify | `--signature` | 必填 | base64 签名串 |
| verify | `--public-key` | `~/.governance/public_key.pem` | 公钥路径 |

## 2. 密钥管理

- 首次 `sign` 自动生成 ED25519 密钥对：私钥 `private_key.pem`（chmod 600）、
  公钥 `public_key.pem`（可分发）。
- **私钥绝不入仓库**（`.gitignore` 已排除 `~/.governance`）；CI 使用一次性自动
  生成的密钥对做自检（GATE 5），不持久化。
- 吊销/轮换：删除或替换 `~/.governance/` 下密钥文件即可；旧签名随之失效。

## 3. 程序化使用（Python API）

```python
from src.certification.sign import sign_file
from src.certification.verify import verify_signature

sig = sign_file("docs/architecture.md")          # -> str (base64)
assert verify_signature("docs/architecture.md", sig) is True  # fail-closed
```

失败语义（fail-closed）：坏 base64 / 坏密钥 / 签名不匹配均返回 `False`，
**绝不**在验证失败时返回成功。

## 4. 在 CI 中验证（GATE 5）

```bash
SIG=$(python -m src.certification.sign --file CONTRIBUTING.md 2>/dev/null | tail -1)
test -n "$SIG" || exit 1
python -m src.certification.verify --file CONTRIBUTING.md --signature "$SIG"
```

见 `.github/workflows/ci.yml` 的 "GATE 5" step（每次 push 自动执行）。

## 5. 与治理流程的关系

| 场景 | 用法 |
|------|------|
| 快照发布 | `sign` 快照文件，签名存入 audit_log 对应条目 |
| 自举证明协议（P12 候选） | 每轮自举输出附带 ED25519 签名证书，链式验证进化真实性 |
| 多 Agent 可迁移性声明 | 外部 Agent 对"我的治理结论"签名，网关侧用公钥复核 |

## 6. 测试覆盖（tests/test_certification.py, 9 tests）

- 签名-验证往返一致；篡改文件 → False；篡改签名 → False；坏 base64 → False；
  坏公钥 → False；密钥自动生成与重载；CLI 端到端（sign→verify OK）。

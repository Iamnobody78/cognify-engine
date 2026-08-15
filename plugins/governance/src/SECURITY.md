# 安全策略

## 支持版本

我们承诺为以下版本提供安全更新：

| 版本 | 支持 |
|------|------|
| v1.x | ✅ 积极维护 |
| < v1.0 | ❌ 不再支持 |

## 报告漏洞

如果你发现安全漏洞，请**不要**创建公开 Issue。请通过以下方式私下报告：

1. 使用 [GitHub 安全咨询](https://github.com/Iamnobody78/agent-governance-v2/security/advisories/new) 提交
2. 或发送邮件至 agent@agent-governance.ai

我们承诺在 24 小时内回复，并在 7 天内提供初步评估。

## 披露政策

- 我们将在确认漏洞后 30 天内发布补丁
- 我们将在发布补丁后公开披露漏洞细节
- 我们将感谢漏洞发现者（除非匿名）

## 安全更新

安全补丁将发布为紧急版本（`vX.Y.Z+security`），并在 `SECURITY.md` 中记录。

## 已披露安全事件

- 2026-08-03: P10 私钥误提交事件——通过 `git reset --soft` 重写历史彻底清除（`aionrs` 会话记录）；`.keys/` 已加入 .gitignore 防止复发；AUDIT 链永久记录

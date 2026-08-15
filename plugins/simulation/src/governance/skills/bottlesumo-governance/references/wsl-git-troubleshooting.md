# WSL Git 调试速查（2026-08-13 实战提炼）

> 来源：HONESTY-PERMANENT 493274c 上推过程中的 v0-v5 迭代实证。
> 权威仓库路径：`~/bottlesumo-pi-clone`（**不是** `~/bottlesumo_pi`，后者是遗留 ROS 副本无 .git）。

## 问题：git push 超时/认证失败

1. **测连通性**：`curl -sI https://github.com` → 200 表示网络通，问题在认证层
2. **测认证**：`GIT_TERMINAL_PROMPT=0 git push origin main` → 报 `could not read Username` 即缺凭据
3. **检查凭据落位**：
   ```bash
   export HOME=/home/ivy   # 关键！WSL HOME 可能被 Windows 污染（HOME=C:Usersivy）
   git config --global --show-origin --list | grep credential
   sed -E 's#(https://[^:]+:)[^@]+@#\1***MASKED***@#' ~/.git-credentials
   ```
4. **修复凭据**（用脚本文件写，避免内联 printf 转义）：
   ```bash
   printf 'https://oauth2:%s@github.com' "$TOKEN" > ~/.git-credentials
   echo "" >> ~/.git-credentials
   chmod 600 ~/.git-credentials
   git config --global credential.helper store
   ```
5. **验证匹配**：
   ```bash
   printf 'protocol=https\nhost=github.com\n\n' | git credential-store get
   ```
6. **受保护分支**：push 报 `GH006: Changes must be made through a pull request` → 建 feature 分支推送 → gh CLI 创建 PR

## 关键发现（本次迭代）

- **WSL 侧无需安装 gh**：Windows 侧 gh 已登录（Iamnobody78），token 经 `$env:WSLENV=GH_TOKEN_IN` 传入 WSL，不进命令行
- **credential-store 格式错误是根因**：内联 `printf "...\n"` 经 PowerShell→WSL 转义后 `\n` 变成字面 `n` → 主机名变 `github.comn` → store 永远匹配失败 → 401 挂起
- **ls-remote 成功 ≠ 认证 OK**：公开仓库匿名可读，必须用需写权限的操作（push）实测认证
- **HOME 污染是副发现**：`HOME=C:Usersivy` 导致 `~` 解析错误，但不是 push 失败根因
- **PowerShell→WSL 引号/转义是事故高发区**：复杂命令一律写脚本文件（Write 到会话目录 → `/mnt/c/...` 路径执行），避免内联

## 跨 AI 转述警示（元幻觉实证）

- 网页版 DeepSeek 的"自动报告"将**计划叙述为已完成**（✅ 标记+文件路径+commit hash 均为想象）
- 接收方必须执行 L1 核查（实测验证）后才能接受声称
- 协议强制：声称 → 验证 → 写入记忆/仓库，三步缺一不可

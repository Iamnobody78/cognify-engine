#!/usr/bin/env bash
# ============================================================
# github_auto_setup.sh — 双仓库 GitHub 生态配置（DUAL-ECO GAP-6.10）
# 修正版（相对 PM 初稿）:
#   1. has_discussions 在 REST API 不存在 → 改用 GraphQL mutation
#   2. 分支保护生效后直写 main 被 409 拒 → CODEOWNERS 走 PR 流程
# 用法:
#   export GH_TOKEN=ghp_xxx   # 需 repo + admin 权限
#   ./scripts/github_auto_setup.sh
# ============================================================
set -euo pipefail

REPOS=("Iamnobody78/bottlesumo-pi" "Iamnobody78/agent-governance-v2")

for repo in "${REPOS[@]}"; do
  echo "========== $repo =========="
  owner="${repo%%/*}"; name="${repo##*/}"

  # 1. Issues（REST）
  gh api -X PATCH "repos/$repo" -F has_issues=true >/dev/null
  echo "✅ Issues enabled"

  # 2. Discussions（GraphQL——REST 无 has_discussions 字段）
  node_id="$(gh api "repos/$repo" --jq .node_id)"
  gh api graphql -f query='mutation($id: ID!) { updateRepository(input: {repositoryId: $id, hasDiscussionsEnabled: true}) { repository { hasDiscussionsEnabled } } }' -F id="$node_id" >/dev/null
  echo "✅ Discussions enabled (GraphQL)"

  # 3. 分支保护（main: 1 review + enforce_admins + strict + 禁 force push）
  body='{"required_status_checks":{"strict":true,"contexts":[]},"enforce_admins":true,"required_pull_request_reviews":{"required_approving_review_count":1},"restrictions":null}'
  tmp="$(mktemp)"; printf '%s' "$body" > "$tmp"
  gh api -X PUT "repos/$repo/branches/main/protection" --input "$tmp" >/dev/null
  rm -f "$tmp"
  echo "✅ Branch protection (main): 1 review + enforce_admins + strict + no-force-push"

  # 4. CODEOWNERS——分支保护生效后不能直写 main，走 PR（需人工审批）
  gh api "repos/$repo/contents/.github/CODEOWNERS" >/dev/null 2>&1 && { echo "⏩ CODEOWNERS exists"; continue; }
  echo "⚠️ CODEOWNERS 需走 PR 流程（main 已受保护，直写被 409 拒绝）:"
  echo "   git checkout -b chore/codeowners-github-eco && echo '* @Iamnobody78' > .github/CODEOWNERS"
  echo "   git add .github/CODEOWNERS && git commit -m 'chore: CODEOWNERS' && git push -u origin chore/codeowners-github-eco"
  echo "   gh pr create --base main --head chore/codeowners-github-eco --title 'chore: CODEOWNERS'"
  echo "   → 需 PM review 合并（self-review 禁止）"
done
echo "🎉 配置完成（CODEOWNERS 部分按提示走 PR）"

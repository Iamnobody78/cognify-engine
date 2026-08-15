#!/usr/bin/env python3
"""GitHub 仓库搜索 — github_search.py (零依赖, 直连 GitHub Search API).

Token 来源优先级: --token > 环境变量 GITHUB_TOKEN/GH_TOKEN > gh auth token (CLI)。
无 token 也可用 (未认证 60 次/时); 认证后 5000 次/时。

用法:
  python scripts/github_search.py "agent governance" [--max-results 10]
  python scripts/github_search.py "tree-sitter AST analyzer" --json --sort stars

退出码: 0 成功; 2 用法/网络错误 (可注入 http_get 供测试 mock, 不触网).
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

API_URL = "https://api.github.com/search/repositories"


def _reconfigure():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _http_get(url: str, timeout: float = 20, headers: dict | None = None) -> str:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def get_token(explicit: str | None = None) -> str | None:
    """Token 来源: --token > env > gh CLI。找不到返回 None (未认证模式)。"""
    if explicit:
        return explicit
    for var in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(var):
            return os.environ[var]
    try:
        out = subprocess.run(["gh", "auth", "token"], capture_output=True,
                             text=True, timeout=10, encoding="utf-8")
        token = out.stdout.strip()
        if token and out.returncode == 0:
            return token
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def search_repos(query: str, max_results: int = 10, sort: str = "stars",
                 token: str | None = None, timeout: float = 20,
                 http_get=None) -> list[dict]:
    """GitHub 仓库检索, 返回 [{full_name, stars, language, description, html_url, updated}]。"""
    fetcher = http_get or _http_get
    q = urllib.parse.quote(query)
    url = (f"{API_URL}?q={q}&sort={sort}&order=desc&per_page={max_results}")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "agent-governance-v2"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    raw = fetcher(url, timeout, headers)
    data = json.loads(raw)
    repos = []
    for item in data.get("items", []):
        repos.append({
            "full_name": item.get("full_name", ""),
            "stars": item.get("stargazers_count", 0),
            "language": item.get("language") or "",
            "description": (item.get("description") or "").strip(),
            "html_url": item.get("html_url", ""),
            "updated": (item.get("updated_at") or "")[:10],
        })
    return repos


def _fmt_table(repos: list[dict]) -> str:
    lines = []
    for i, r in enumerate(repos, 1):
        desc = r["description"][:70] if r["description"] else "-"
        lines.append(f"{i:2}. {r['full_name']} ⭐{r['stars']} [{r['language'] or '?'}]")
        lines.append(f"    {desc}")
        lines.append(f"    {r['html_url']} · updated {r['updated']}")
    return "\n".join(lines) if lines else "(无结果)"


def main(argv=None) -> int:
    _reconfigure()
    ap = argparse.ArgumentParser(description="GitHub 仓库搜索 (零依赖)")
    ap.add_argument("query", help="检索意图, 如 \"agent governance\"")
    ap.add_argument("--max-results", type=int, default=10, help="结果条数 (默认 10)")
    ap.add_argument("--sort", default="stars", help="排序字段: stars/updated (默认 stars)")
    ap.add_argument("--token", default=None, help="GitHub Token (默认 env/gh CLI)")
    ap.add_argument("--json", action="store_true", help="JSON 结构化输出")
    ap.add_argument("--timeout", type=float, default=20, help="网络超时秒数 (默认 20)")
    args = ap.parse_args(argv)

    token = get_token(args.token)
    mode = "认证" if token else "未认证(60次/时)"
    try:
        repos = search_repos(args.query, args.max_results, args.sort,
                             token, args.timeout)
    except urllib.error.HTTPError as e:
        print(f"ERROR: GitHub API HTTP {e.code}: {e.reason} "
              f"(token {'无效' if token else '缺失, 需 GITHUB_TOKEN'})", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"ERROR: GitHub 搜索失败: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(repos, ensure_ascii=False, indent=2))
    else:
        print(f"🐙 GitHub: {len(repos)} 个仓库 ({mode}, query: {args.query})")
        print(_fmt_table(repos))
    return 0


if __name__ == "__main__":
    sys.exit(main())

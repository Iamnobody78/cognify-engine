#!/usr/bin/env python3
"""学术论文搜索 — academic_search.py (零依赖, 直连 arXiv API).

arXiv 公开 API, 无需 key。输出结构化结果 (标题/作者/日期/链接/摘要)。

用法:
  python scripts/academic_search.py "agent governance" [--max-results 10]
  python scripts/academic_search.py "tree-sitter AST" --json
  python scripts/academic_search.py "prompt caching" --max-results 3 --timeout 30

退出码: 0 成功; 2 用法/网络错误 (可注入 http_get 供测试 mock, 不触网).
"""

import argparse
import json
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

API_URL = "http://export.arxiv.org/api/query"
NS = {"atom": "http://www.w3.org/2005/Atom"}
MAX_ABSTRACT = 400  # 表格模式摘要截断


def _reconfigure():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _http_get(url: str, timeout: float = 20) -> str:
    """真实网络获取 (测试时以注入 fetcher 替换)。"""
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def search_papers(query: str, max_results: int = 10, timeout: float = 20,
                  http_get=None) -> list[dict]:
    """arXiv 检索, 返回论文列表 [{title, authors, published, url, abstract}]。"""
    fetcher = http_get or _http_get
    q = urllib.parse.quote(query)
    url = (f"{API_URL}?search_query=all:{q}&max_results={max_results}"
           f"&sortBy=relevance&sortOrder=descending")
    xml = fetcher(url, timeout)
    root = ET.fromstring(xml)
    papers = []
    for entry in root.findall("atom:entry", NS):
        title = entry.findtext("atom:title", default="", namespaces=NS).strip()
        summary = entry.findtext("atom:summary", default="", namespaces=NS).strip()
        published = entry.findtext("atom:published", default="", namespaces=NS).strip()[:10]
        url = entry.findtext("atom:id", default="", namespaces=NS).strip()
        authors = [a.findtext("atom:name", default="", namespaces=NS).strip()
                   for a in entry.findall("atom:author", NS)]
        papers.append({
            "title": title,
            "authors": authors,
            "published": published,
            "url": url,
            "abstract": summary,
        })
    return papers


def _fmt_table(papers: list[dict]) -> str:
    lines = []
    for i, p in enumerate(papers, 1):
        authors = ", ".join(p["authors"])[:60] or "-"
        title = p["title"][:70]
        lines.append(f"{i:2}. {title}")
        lines.append(f"    {authors} · {p['published']} · {p['url']}")
        if p["abstract"]:
            lines.append(f"    {p['abstract'][:MAX_ABSTRACT]}")
    return "\n".join(lines) if lines else "(无结果)"


def main(argv=None) -> int:
    _reconfigure()
    ap = argparse.ArgumentParser(description="arXiv 学术论文搜索 (零依赖)")
    ap.add_argument("query", help="检索关键词, 如 \"agent governance\"")
    ap.add_argument("--max-results", type=int, default=10, help="结果条数 (默认 10)")
    ap.add_argument("--json", action="store_true", help="JSON 结构化输出")
    ap.add_argument("--timeout", type=float, default=20, help="网络超时秒数 (默认 20)")
    args = ap.parse_args(argv)

    try:
        papers = search_papers(args.query, args.max_results, args.timeout)
    except Exception as e:
        print(f"ERROR: 学术搜索失败: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(papers, ensure_ascii=False, indent=2))
    else:
        print(f"📚 arXiv: {len(papers)} 篇论文 (query: {args.query})")
        print(_fmt_table(papers))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""RES-AGENT: arXiv paper retriever (R0.1).

S.A.M.U.E.L. Phase S (Survey) — 真实 arXiv API 检索, 不依赖本地缓存。
输出统一 schema 的 papers list, 供后续 phase (pattern extraction / synthesis) 消费。

Run: python3 governance/research/paper_retriever.py --query "VLA tactile manipulation" --max 5
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
}


def fetch_arxiv(query: str, max_results: int = 5, timeout: float = 20.0) -> list:
    """Query arXiv API. Returns list of dicts:
    {id, title, authors, summary, published, updated, primary_category, links}"""
    url = (
        "https://export.arxiv.org/api/query?"
        + urllib.parse.urlencode(
            {"search_query": query, "max_results": max_results, "sortBy": "relevance"}
        )
    )
    req = urllib.request.Request(url, headers={"User-Agent": "RES-AGENT/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        xml_data = resp.read().decode("utf-8")

    root = ET.fromstring(xml_data)
    papers = []
    for entry in root.findall("atom:entry", NS):
        paper = {
            "id": entry.findtext("atom:id", "", NS).strip(),
            "title": " ".join(entry.findtext("atom:title", "", NS).split()),
            "authors": [
                a.findtext("atom:name", "", NS).strip()
                for a in entry.findall("atom:author", NS)
            ],
            "summary": " ".join(entry.findtext("atom:summary", "", NS).split()),
            "published": entry.findtext("atom:published", "", NS).strip(),
            "updated": entry.findtext("atom:updated", "", NS).strip(),
            "primary_category": entry.findtext("arxiv:primary_category", None, NS)
            if entry.find("arxiv:primary_category", NS) is not None
            else "",
            "links": [l.attrib.get("href") for l in entry.findall("atom:link", NS)],
        }
        papers.append(paper)
    return papers


def save(papers: list, out_path: str) -> str:
    payload = {
        "query": None,
        "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "count": len(papers),
        "papers": papers,
    }
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True)
    ap.add_argument("--max", type=int, default=5)
    ap.add_argument("--out", default="governance/research/outputs/research_papers_list.json")
    args = ap.parse_args()

    print(f"[paper_retriever] query='{args.query}' max={args.max}")
    t0 = time.time()
    try:
        papers = fetch_arxiv(args.query, args.max)
    except Exception as e:
        print(f"[paper_retriever] FAIL: {e}")
        sys.exit(1)
    path = save(papers, args.out)
    print(f"[paper_retriever] retrieved {len(papers)} papers in {time.time()-t0:.1f}s -> {path}")
    for p in papers:
        print(f"  - [{p['primary_category']}] {p['title']} ({p['published'][:10]})")


if __name__ == "__main__":
    main()

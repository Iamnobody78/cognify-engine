#!/usr/bin/env python3
"""Phase 0/1: 记忆检索 — memory_query.py (零依赖, 纯标准库).

Phase 0 结构化: 按 type / 日期范围 / 关键词组合查询 aionrs 记忆目录.
Phase 1 语义: --embed 用 Ollama nomic-embed-text 嵌入查询词, 对
memory_index.pkl 中的记忆向量做余弦相似度, 返回 top K. 索引缺失或
Ollama 不可用时输出警告并降级到结构化检索 (可选增强, 非硬依赖).

日期来源优先级: MEMORY.md 索引分组日期 > frontmatter date 字段 > mtime.
type 为 frontmatter 真实值 (project/user/feedback/reference), 非语义类.
keyword 对全文 (name+description+body) 大小写不敏感.

用法:
  python scripts/memory_query.py --type project
  python scripts/memory_query.py --since 2026-08-01 --until 2026-08-31
  python scripts/memory_query.py --keyword sql --type project
  python scripts/memory_query.py --embed "策略演化" --top 5
  python scripts/memory_query.py --embed --keyword "策略演化"
"""

import argparse
import json
import os
import pathlib
import pickle
import re
import sys
import urllib.request
from datetime import datetime

DEFAULT_ROOT = pathlib.Path(
    os.environ.get(
        "AIONRS_MEMORY_ROOT",
        r"C:\Users\ivy\AppData\Roaming\aionrs\projects"
        r"\C--Users-ivy-AppData-Roaming-AionUi-aionui-conversations"
        r"-2026-07-27-aionrs-temp-48324704\memory",
    )
)
_FM = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_GROUP = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s*$")
_INDEX = re.compile(r"^-\s+([\w.\-]+\.md)\s*\|")


def parse_frontmatter(text):
    """返回 (fields: dict, body: str)。frontmatter 缺失时 fields 为空 dict。"""
    m = _FM.match(text)
    if not m:
        return {}, text
    fields = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fields[k.strip()] = v.strip()
    return fields, text[m.end():]


def index_dates(root):
    """解析 MEMORY.md 的 '## 日期' 分组: {filename: 日期}。"""
    idx = root / "MEMORY.md"
    if not idx.exists():
        return {}
    result, current = {}, None
    for line in idx.read_text(encoding="utf-8").splitlines():
        g = _GROUP.match(line)
        if g:
            current = g.group(1)
            continue
        m = _INDEX.match(line)
        if m and current:
            result[m.group(1)] = current
    return result


def collect(root):
    """返回 [{name, path, type, date, date_src, description, body}]。"""
    idx_dates = index_dates(root)
    entries = []
    for p in sorted(root.glob("*.md")):
        if p.name == "MEMORY.md":
            continue
        fields, body = parse_frontmatter(p.read_text(encoding="utf-8"))
        d, src = idx_dates.get(p.name), "index"
        if not d and fields.get("date"):
            d, src = fields["date"], "frontmatter"
        if not d:
            d, src = datetime.fromtimestamp(p.stat().st_mtime).date().isoformat(), "mtime"
        entries.append({
            "name": fields.get("name", p.stem), "path": p,
            "type": fields.get("type", ""), "date": d, "date_src": src,
            "description": fields.get("description", ""), "body": body,
        })
    return entries


def match(e, a):
    if a.type and e["type"] != a.type:
        return False
    if a.since and e["date"] < a.since:
        return False
    if a.until and e["date"] > a.until:
        return False
    if a.keyword:
        hay = f'{e["name"]}\n{e["description"]}\n{e["body"]}'.lower()
        if a.keyword.lower() not in hay:
            return False
    return True


# ---------- Phase 1: 语义检索 (Ollama, 可选增强) ----------

def embed(prompt: str, model: str = None, timeout: float = 30.0):
    """调用 Ollama /api/embeddings, 返回向量 list; 失败返回 None.

    OLLAMA_URL / EMBED_MODEL 均调用时读取 (非 import 冻结), 便于测试注入。
    """
    url = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
    model = model or os.environ.get("EMBED_MODEL", "nomic-embed-text")
    body = json.dumps({"model": model, "prompt": prompt}).encode()
    req = urllib.request.Request(
        url + "/api/embeddings", data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("embedding")
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def cosine(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def load_index(root: pathlib.Path, index_path=None):
    """加载 memory_index.pkl, 返回 {"model": str, "files": {name: {...}}}.

    兼容两种格式: 新版 {"model", "files"} 包装 / 旧版裸 {name: {...}}。
    索引缺失/损坏返回 None (调用方降级)。路径默认 <root>/memory_index.pkl。
    """
    path = pathlib.Path(index_path) if index_path else root / "memory_index.pkl"
    if not path.exists():
        return None
    try:
        with open(path, "rb") as f:
            data = pickle.load(f)
    except (pickle.UnpicklingError, EOFError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if "files" in data and "model" in data:  # 新版
        return data
    return {"model": "unknown-legacy", "files": data}  # 旧版裸 dict


def _rrf_rank(scores, k=60):
    """按分数降序返回 {name: rank}。

    competition ranking: 并列分数取相同 rank (1, 2, 2, 4)。这是 RRF
    的关键——若并列被赋予不同 rank, 语义/关键词侧的全零并列会被
    稳定排序扭曲, 破坏融合结果 (kw 全 0 时应退化为纯语义排序)。
    """
    order = sorted(scores, key=lambda t: t[1], reverse=True)
    ranks = {}
    prev_score, prev_rank = None, 0
    for i, (name, score) in enumerate(order, 1):
        if score == prev_score:
            ranks[name] = prev_rank
        else:
            ranks[name] = i
            prev_score, prev_rank = score, i
    return ranks


def semantic_search(root: pathlib.Path, prompt: str, top: int, index_path=None):
    """返回 (hits, degraded_reason)。hits=[(score, name, meta)] 降序.

    混合检索用 RRF (Reciprocal Rank Fusion, k=60) 融合两条排名:
      1) 余弦相似度排名 (语义)
      2) 查询词 2-gram 命中率排名 (关键词精确性)
    RRF 融合排名而非分数, 避免加权融合对分数量纲的敏感; 关键词全无命中
    时 kw 排名并列, RRF 自然退化为纯语义排序。

    degraded_reason 非 None 表示降级: "no_index" / "embed_failed" /
    "model_mismatch" (索引模型与当前 EMBED_MODEL 不一致)。
    """
    index = load_index(root, index_path)
    if index is None:
        return None, "no_index"
    cur = os.environ.get("EMBED_MODEL", "nomic-embed-text")
    if index["model"] != "unknown-legacy" and index["model"] != cur:
        return None, f"model_mismatch ({index['model']} != {cur})"
    qvec = embed(prompt)
    if qvec is None:
        return None, "embed_failed"
    grams = [prompt[i:i + 2] for i in range(len(prompt) - 1)]
    files = index["files"]
    sem_scores, kw_scores = [], []
    for name, v in files.items():
        meta = v.get("meta", {})
        sem_scores.append((name, cosine(qvec, v["vector"])))
        if grams:
            hay = f'{meta.get("name", "")}\n{meta.get("description", "")}'.lower()
            kw = sum(1 for g in grams if g in hay) / len(grams)
        else:
            kw = 0.0
        kw_scores.append((name, kw))
    sem_rank = _rrf_rank(sem_scores)
    kw_rank = _rrf_rank(kw_scores)
    fused = {}
    for name in files:
        fused[name] = 1.0 / (60 + sem_rank[name]) + 1.0 / (60 + kw_rank[name])
    scored = sorted(
        ((fused[name], name, files[name].get("meta", {})) for name in fused),
        key=lambda t: t[0], reverse=True,
    )
    return scored[:top], None


def main(argv=None):
    # Windows 控制台 cp950 无法编码 CJK 记忆内容 → 强制 UTF-8 输出
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="结构化记忆检索 (Phase 0)")
    ap.add_argument("--root", default=str(DEFAULT_ROOT), help="记忆目录")
    ap.add_argument("--type", help="frontmatter type 精确匹配")
    ap.add_argument("--since", help="起始日期 YYYY-MM-DD (含)")
    ap.add_argument("--until", help="结束日期 YYYY-MM-DD (含)")
    ap.add_argument("--keyword", help="全文大小写不敏感关键词")
    ap.add_argument("query", nargs="?", default=None,
                    help="语义查询词 (配合 --embed; 等价于 --keyword 语义用法)")
    ap.add_argument("--format", choices=["table", "plain"], default="table")
    ap.add_argument("--embed", action="store_true", help="启用语义检索 (Ollama, 可选)")
    ap.add_argument("--top", type=int, default=5, help="语义检索返回条数 (默认 5)")
    ap.add_argument("--index", default=None, help="向量索引路径 (默认 <root>/memory_index.pkl)")
    args = ap.parse_args(argv)

    root = pathlib.Path(args.root)
    if not root.is_dir():
        print(f"ERROR: 记忆目录不存在: {root}", file=sys.stderr)
        return 2

    # ---- Phase 1 语义分支 ----
    if args.embed:
        prompt = args.query or args.keyword or ""
        if not prompt:
            print("ERROR: --embed 需要查询词 (位置参数或 --keyword)", file=sys.stderr)
            return 2
        hits, reason = semantic_search(root, prompt, args.top, args.index)
        if reason == "embed_failed":
            print("WARN: Ollama 不可用, 降级到结构化检索", file=sys.stderr)
        elif reason == "no_index":
            print("WARN: 索引不存在, 降级到结构化检索 (先运行 vectorize_memory.py)", file=sys.stderr)
        elif reason and reason.startswith("model_mismatch"):
            print(f"WARN: 索引模型与当前不一致, 请重新运行 vectorize_memory.py; "
                  f"已降级到结构化检索 ({reason})", file=sys.stderr)
        else:
            if args.format == "plain":
                for score, name, meta in hits:
                    print(f"{score:.3f}  {meta.get('date', '?')}  {meta.get('type', '')}  {name}")
                    print(f"    {meta.get('description', '')}")
            else:
                print("| score | date | type | name | description |")
                print("|-------|------|------|------|-------------|")
                for score, name, meta in hits:
                    desc = meta.get("description", "").replace("|", "\\|")
                    print(f"| {score:.3f} | {meta.get('date', '?')} | {meta.get('type', '')} | {name} | {desc} |")
            print(f"\n共 {len(hits)} 条语义命中")
            return 0
        # 降级: 落入下方结构化逻辑

    try:
        since = args.since or None
        until = args.until or None
        for v in (since, until):
            if v:
                datetime.strptime(v, "%Y-%m-%d")  # 验证格式, 非法则抛 ValueError
    except ValueError:
        print("ERROR: 日期格式须为 YYYY-MM-DD", file=sys.stderr)
        return 2

    ns = argparse.Namespace(type=args.type, since=since, until=until, keyword=args.keyword)
    hits = [e for e in collect(root) if match(e, ns)]
    if not hits:
        print("(无匹配记忆条目)")
        return 0

    if args.format == "plain":
        for e in hits:
            src = "" if e["date_src"] == "index" else f" [{e['date_src']}]"
            print(f"{e['date']}{src}  {e['type']:9}  {e['name']}")
            print(f"    {e['description']}")
    else:
        print("| date | type | name | description |")
        print("|------|------|------|-------------|")
        for e in hits:
            src = "" if e["date_src"] == "index" else f" ({e['date_src']})"
            desc = e["description"].replace("|", "\\|")
            print(f"| {e['date']}{src} | {e['type']} | {e['name']} | {desc} |")
    print(f"\n共 {len(hits)} 条记忆")
    return 0


if __name__ == "__main__":
    sys.exit(main())

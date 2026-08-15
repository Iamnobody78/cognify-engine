# -*- coding: utf-8 -*-
"""semantic_retriever.py — P1-V3 语义检索 (bge-m3)

为编码代理提议器提供历史经验检索: 在生成候选前, 根据当前目标文件/问题描述,
检索三源血缘 (failure_analysis.md / pareto_frontier.md / hypotheses.jsonl),
将结果注入系统提示 (retrieved_experience 字段)。

- 嵌入模型: Ollama bge-m3:latest (/api/embed, 1024 维)
- 切块: failure_analysis 按 '### ' 轮次记录, pareto 按 '> **' 附注, hypotheses 按行
- 缓存: _cache/semantic_index.json (按源文件 mtime 失效), 避免每轮重复嵌入
"""
import json
import os
import re
import time
import urllib.request

META_DIR = os.path.dirname(os.path.abspath(__file__))
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = "bge-m3:latest"
CACHE_PATH = os.path.join(META_DIR, "_cache", "semantic_index.json")
TIMEOUT_S = 120
EMBED_BATCH = 8  # 分批嵌入: 避免单请求超时 (bge-m3 CPU 推理 ~1-3s/块)

SOURCES = {
    "failure_analysis": os.path.join(META_DIR, "failure_analysis.md"),
    "pareto_frontier": os.path.join(META_DIR, "pareto_frontier.md"),
    "hypotheses": os.path.join(META_DIR, "experience", "hypotheses.jsonl"),
}


# --------------------------------------------------------------------------
# 分块
# --------------------------------------------------------------------------
def chunk_failure(text: str) -> list:
    """按 '### Meta-Harness 轮次记录' 标题切块。

    精简策略: 因果推理块 (含"为什么"深层知识) 全保留 + 最近 MAX_RECENT 个轮次记录
    (按时间戳排序取最新, 信息增量集中在最近记录)。
    """
    MAX_RECENT = 12
    parts = re.split(r"(?m)^### ", text)
    causal, records = [], []
    for p in parts[1:]:
        title, _, body = p.partition("\n")
        block = {"id": title.strip()[:60], "text": ("### " + title.strip() + "\n" + body).strip()}
        if "因果推理" in block["id"]:
            causal.append(block)
        else:
            records.append(block)
    # 按时间戳 (YYYYMMDD_HHMMSS) 排序取最新
    def ts(b):
        m = re.search(r"(\d{8}_\d{6})", b["id"])
        return m.group(1) if m else ""
    records.sort(key=ts, reverse=True)
    return causal + records[:MAX_RECENT]


def chunk_pareto(text: str) -> list:
    """按 '> **' 附注切块, 每块 = 一条决策记录 (附注/潜伏/轮次归档)。"""
    parts = re.split(r"(?m)^> \*\*", text)
    out = []
    for p in parts[1:]:
        title, _, body = p.partition("**")
        out.append({"id": title.strip()[:60], "text": ("> **" + title.strip() + "**" + body).strip()})
    return out


def chunk_hypotheses(text: str) -> list:
    """hypotheses.jsonl 按行切块, 每块 = 一个假设-结果配对。"""
    out = []
    for i, line in enumerate(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        out.append({
            "id": f"hyp_{i + 1} ({rec.get('variant_id', '?')})",
            "text": json.dumps(rec, ensure_ascii=False)[:400],
        })
    return out


def _read_text(path: str) -> str:
    for enc in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, FileNotFoundError):
            continue
    return ""


def chunk_sources() -> list:
    """返回 [{source, id, text}, ...] 全部语义块。"""
    chunks = []
    for src, path in SOURCES.items():
        text = _read_text(path)
        if not text:
            continue
        if src == "failure_analysis":
            blocks = chunk_failure(text)
        elif src == "pareto_frontier":
            blocks = chunk_pareto(text)
        else:
            blocks = chunk_hypotheses(text)
        for b in blocks:
            b["source"] = src
            chunks.append(b)
    return chunks


# --------------------------------------------------------------------------
# 嵌入 (Ollama /api/embed)
# --------------------------------------------------------------------------
def embed_texts(texts: list, model: str = EMBED_MODEL) -> list:
    """批量嵌入 (分批 EMBED_BATCH), 返回与输入等长的向量列表。"""
    out = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i:i + EMBED_BATCH]
        payload = {"model": model, "input": batch}
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/embed",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        out.extend(data["embeddings"])
    return out


def _mtime_key() -> dict:
    """源文件 mtime 快照, 用于缓存失效。"""
    return {src: (os.path.getmtime(p) if os.path.exists(p) else 0)
            for src, p in SOURCES.items()}


def build_index(force: bool = False) -> dict:
    """构建/加载向量索引。

    缓存策略: 缓存文件存在即用 (不按 mtime 自动失效) — 避免每轮迭代追加
    pareto/failure 后触发 274s 级重建; 仅在 force=True (显式 --rebuild) 时重建。
    返回 {"chunks": [...], "embeddings": [[...]], "mtime": {...}}
    """
    if not force and os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                idx = json.load(f)
            if idx.get("model") == EMBED_MODEL and idx.get("embeddings"):
                return idx
        except (json.JSONDecodeError, KeyError):
            pass
    chunks = chunk_sources()
    texts = [c["text"][:800] for c in chunks]  # 截断: 附注块可能超长
    t0 = time.time()
    embeddings = embed_texts(texts) if texts else []
    print(f"[semantic_retriever] 嵌入 {len(texts)} 块 ({EMBED_MODEL}), {time.time() - t0:.1f}s",
          file=os.sys.stderr)
    idx = {"model": EMBED_MODEL, "mtime": _mtime_key(), "chunks": chunks, "embeddings": embeddings}
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False)
    return idx


def cosine_sim(a: list, b: list) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb + 1e-9)


def retrieve(query: str, top_k: int = 3, min_score: float = 0.0,
             force_rebuild: bool = False) -> list:
    """检索与查询最相似的历史经验块。返回 [{source, id, text, score}, ...]

    min_score: P2-V4 meta_config 门裁决可动态提高的相似度下限 —
    低于阈值的命中视为不可靠 (检索结果更严格)。
    """
    idx = build_index(force=force_rebuild)
    chunks, embeddings = idx["chunks"], idx["embeddings"]
    if not chunks or not query.strip():
        return []
    qv = embed_texts([query])[0]
    scored = []
    for c, ev in zip(chunks, embeddings):
        if not ev:
            continue
        s = cosine_sim(qv, ev)
        if s >= min_score:
            scored.append((s, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [{"source": c["source"], "id": c["id"], "text": c["text"][:600],
             "score": round(s, 4)} for s, c in scored[:top_k]]


def format_experience(hits: list, max_chars: int = 400) -> str:
    """检索结果 -> 注入系统提示的文本 (标注来源文件与条目)。

    max_chars 默认 400: 中文 ≈ 1 token/char, 400 chars ≈ 400 tokens —
    控制 7b CPU 预填充时延 (实测 >900 chars 注入导致 OLLAMA_TIMEOUT 超时)。
    """
    if not hits:
        return "(无检索命中)"
    lines = []
    used = 0
    for h in hits:
        block = f"- [{h['source']} | {h['id']}] (相似度 {h['score']}): {h['text'][:150]}"
        if used + len(block) > max_chars:
            block = block[:max_chars - used] + "..."
        lines.append(block)
        used += len(block)
        if used >= max_chars:
            break
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "规则引擎调优 抓地衰减 边缘区"
    hits = retrieve(q)
    print(format_experience(hits))

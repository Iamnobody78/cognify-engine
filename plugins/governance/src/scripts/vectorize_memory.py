#!/usr/bin/env python3
"""Phase 1: 记忆向量化 — vectorize_memory.py (零依赖, 复用 memory_query).

读取记忆目录全部 .md → Ollama nomic-embed-text 嵌入 → memory_index.pkl.
- 增量更新: 仅处理 mtime 变化的文件 (索引内记录 mtime_ns)
- 删除的文件从索引移除
- 嵌入内容: name + description + body (截断至 MAX_CHARS 防超长)
- 索引结构: {filename: {"vector": [...], "mtime_ns": int, "meta": {...}}}

退出码: 0=成功/无变更; 1=Ollama 不可用 (输出警告, 不生成/不更新索引).

用法:
  python scripts/vectorize_memory.py
  python scripts/vectorize_memory.py --root <memdir>
"""

import argparse
import os
import pathlib
import pickle
import sys

from memory_query import DEFAULT_ROOT, collect, embed

MAX_CHARS = 512 * 2  # ~512 token; bge-m3 长文本耗时线性增长 (8s@2048ch), 1024ch 平衡质量/速度
INDEX_NAME = "memory_index.pkl"


def build_prompt(entry) -> str:
    parts = [entry["name"], entry["description"], entry["body"]]
    return "\n".join(p for p in parts if p)[:MAX_CHARS]


def load_existing(index_path: pathlib.Path):
    """加载索引, 返回 (files_dict, model_str)。损坏/缺失时 files={}。"""
    if not index_path.exists():
        return {}, None
    try:
        with open(index_path, "rb") as f:
            data = pickle.load(f)
    except (pickle.UnpicklingError, EOFError, ValueError):
        return {}, None
    if not isinstance(data, dict):
        return {}, None
    if "files" in data:  # 新版包装
        return data["files"], data.get("model")
    return data, None  # 旧版裸 dict


def current_model():
    return os.environ.get("EMBED_MODEL", "nomic-embed-text")


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="记忆向量化 (Phase 1)")
    ap.add_argument("--root", default=str(DEFAULT_ROOT), help="记忆目录")
    ap.add_argument("--output", default=None, help="索引输出路径 (默认 <root>/memory_index.pkl)")
    args = ap.parse_args(argv)

    root = pathlib.Path(args.root)
    if not root.is_dir():
        print(f"ERROR: 记忆目录不存在: {root}", file=sys.stderr)
        return 1
    index_path = pathlib.Path(args.output) if args.output else root / INDEX_NAME

    entries = [e for e in collect(root)]
    existing, old_model = load_existing(index_path)
    model = current_model()

    # 模型变更/旧版无模型记录 → 强制全量重建 (不同模型向量不可比)
    if existing and old_model != model:
        print(f"索引模型不匹配: {old_model or 'unknown-legacy'} -> {model}, 强制全量重建")
        existing = {}

    # 增量: 找出 mtime 变化的文件
    changed = []
    known_names = set()
    for e in entries:
        name = e["path"].name
        known_names.add(name)
        mtime_ns = e["path"].stat().st_mtime_ns
        if existing.get(name, {}).get("mtime_ns") != mtime_ns:
            changed.append(e)
    # 移除已删除文件
    for name in list(existing):
        if name not in known_names:
            del existing[name]
            print(f"移除: {name} (文件已删除)")

    if not changed:
        print(f"无变更 ({len(entries)} 个文件, 索引已最新)")
        return 0

    print(f"待嵌入: {len(changed)} 个文件 (共 {len(entries)} 个, 模型={model})...")
    probe = embed(build_prompt(changed[0]))
    if probe is None:
        print(f"WARN: Ollama 不可用, 未生成索引 (可先运行: ollama pull {model})",
              file=sys.stderr)
        return 1

    for i, e in enumerate(changed, 1):
        name = e["path"].name
        vec = embed(build_prompt(e))
        if vec is None:
            print(f"WARN: {name} 嵌入失败, 跳过", file=sys.stderr)
            continue
        existing[name] = {
            "vector": vec,
            "mtime_ns": e["path"].stat().st_mtime_ns,
            "meta": {
                "name": e["name"],
                "type": e["type"],
                "date": e["date"],
                "description": e["description"],
            },
        }
        print(f"[{i}/{len(changed)}] {name} ({len(vec)} dims)")
    with open(index_path, "wb") as f:
        pickle.dump({"model": model, "files": existing}, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"索引已写入: {index_path} ({len(existing)} 个文件, 模型={model})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

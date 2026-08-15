#!/usr/bin/env python3
"""学习捕获 — write_memory.py (零依赖, 纯标准库).

在代理执行任务、分析、决策过程中, 将关键事件固化为持久化记忆。
每次写入自动同步更新 MEMORY.md 索引 (写入即索引, 防遗忘工程原则)。

事件类型:
  decision  决策记录  — 决策内容、理由、上下文
  lesson    失败教训  — 失败原因、修复方案、避免方法
  insight   新发现    — 发现内容、证据、应用场景
  session   会话摘要  — 会话关键事项、待办、结论

用法:
  python scripts/write_memory.py --type lesson --title "AST规则变更后须跑回归" \
      --content "变更 python.scm 后 test_ast_guard_bypass.py 出现误报..." \
      --tags "ast,regression" --session "2026-08-04"
  python scripts/write_memory.py --json batch.json        # 批量导入
  python scripts/write_memory.py --type insight --title "x" --content "y" --dry-run

写入格式 (与 memory_query.py 解析兼容):
  memory/<type>-YYYY-MM-DD-<slug>.md
  ---
  name: ...
  description: ...
  type: lesson
  tags: [...]
  date: YYYY-MM-DD
  session: ...
  ---
  body...

MEMORY.md 索引: 追加到对应 "## YYYY-MM-DD" 分组下 (无分组则新建)。
"""

import argparse
import json
import os
import pathlib
import re
import sys
from datetime import datetime

DEFAULT_ROOT = pathlib.Path(
    os.environ.get(
        "AIONRS_MEMORY_ROOT",
        r"C:\Users\ivy\AppData\Roaming\aionrs\projects"
        r"\C--Users-ivy-AppData-Roaming-AionUi-aionui-conversations"
        r"-2026-07-27-aionrs-temp-48324704\memory",
    )
)
TYPES = ("decision", "lesson", "insight", "session")
_GROUP = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s*$")
_SLUG = re.compile(r"[^\w\-]+")


def _slugify(title, max_len=40):
    """标题 → 文件名 slug: 小写、非 [\w-] 替换为 -, 截断。"""
    s = _SLUG.sub("-", title.lower()).strip("-")
    return s[:max_len].rstrip("-") or "untitled"


def _frontmatter(entry):
    """生成 frontmatter 文本。tags 列表按 yaml 数组序列化。"""
    tags = entry.get("tags", [])
    tag_str = ", ".join(tags) if tags else ""
    return (
        "---\n"
        f"name: {entry['title']}\n"
        f"description: {entry.get('description', '')}\n"
        f"type: {entry['type']}\n"
        f"tags: [{tag_str}]\n"
        f"date: {entry['date']}\n"
        f"session: {entry.get('session', '')}\n"
        "---\n\n"
    )


def _read_memory_index(root):
    """读 MEMORY.md, 返回 (行列表, 组位置: {date: 行号})。不存在返回 (None, {})."""
    idx = root / "MEMORY.md"
    if not idx.exists():
        return None, {}
    lines = idx.read_text(encoding="utf-8").splitlines()
    groups = {}
    for i, line in enumerate(lines):
        m = _GROUP.match(line)
        if m:
            groups[m.group(1)] = i
    return lines, groups


def _update_index(root, entry, fname):
    """MEMORY.md 索引追加: - fname | description | type | 摘要。写入即索引。"""
    lines, groups = _read_memory_index(root)
    date = entry["date"]
    summary = (entry.get("description") or entry["title"]).replace("|", "/")
    line = f"- {fname} | {summary} | {entry['type']} | {entry.get('session', '')}"
    if lines is None:
        root.mkdir(parents=True, exist_ok=True)
        lines = ["# Project Memory Index", "", f"## {date}", f"- {line}"]
        (root / "MEMORY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return
    if date in groups:
        lines.insert(groups[date] + 1, f"- {line}")
    else:
        lines.extend(["", f"## {date}", f"- {line}"])
    (root / "MEMORY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _existing_entry(root, entry):
    """去重: 同 type + 同 title 已存在 → 返回已存在文件名 (供合并决策)。"""
    date = entry["date"]
    for f in root.glob(f"{entry['type']}-*.md"):
        text = f.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^name:\s*(.+)$", text, re.M)
        if m and m.group(1).strip() == entry["title"]:
            return f.name
    return None


def write_memory(entry, root=None, dedupe=True, dry_run=False):
    """写入单条记忆。返回 (status, fname)。status: written/skipped_dup/dry_run/error。"""
    root = pathlib.Path(root) if root else DEFAULT_ROOT
    entry = dict(entry)
    entry.setdefault("type", "insight")
    entry.setdefault("date", datetime.now().strftime("%Y-%m-%d"))
    entry.setdefault("tags", [])
    entry.setdefault("session", "")
    entry.setdefault("description", "")
    if entry["type"] not in TYPES:
        return "error", f"未知 type: {entry['type']} (可选 {TYPES})"
    if not entry.get("title"):
        return "error", "title 必填"

    dup = _existing_entry(root, entry) if dedupe else None
    if dup:
        return "skipped_dup", dup

    fname = f"{entry['type']}-{entry['date']}-{_slugify(entry['title'])}.md"
    if dry_run:
        return "dry_run", fname
    root.mkdir(parents=True, exist_ok=True)
    body = entry.get("content", "")
    # 文件名冲突 (--no-dedupe 同题同日期): 追加序号, 绝不覆盖已有文件
    stem, suffix = fname[:-3], ".md"
    counter = 2
    while (root / fname).exists():
        fname = f"{stem}-{counter}{suffix}"
        counter += 1
    (root / fname).write_text(_frontmatter(entry) + body + "\n", encoding="utf-8")
    _update_index(root, entry, fname)
    return "written", fname


def main(argv=None):
    ap = argparse.ArgumentParser(description="学习捕获: 写入记忆 + 同步索引")
    ap.add_argument("--type", default="insight",
                    help=f"事件类型: {', '.join(TYPES)} (write_memory 内部再校验, 返回 rc=1)")
    ap.add_argument("--title", default="")
    ap.add_argument("--content", default="")
    ap.add_argument("--description", default="")
    ap.add_argument("--tags", default="")
    ap.add_argument("--session", default="")
    ap.add_argument("--date", default="")
    ap.add_argument("--json", help="批量导入 JSON 文件 (列表 of entries)")
    ap.add_argument("--root", default=str(DEFAULT_ROOT), help="记忆根目录 (测试隔离)")
    ap.add_argument("--no-dedupe", action="store_true", help="跳过同 title 去重")
    ap.add_argument("--dry-run", action="store_true", help="只打印将写入的文件名")
    args = ap.parse_args(argv)

    root = pathlib.Path(args.root)
    if args.json:
        with open(args.json, encoding="utf-8") as fh:
            entries = json.load(fh)
    else:
        entries = [{
            "type": args.type,
            "title": args.title,
            "content": args.content,
            "description": args.description,
            "tags": [t.strip() for t in args.tags.split(",") if t.strip()],
            "session": args.session,
            "date": args.date or "",
        }]

    results = []
    for e in entries:
        status, info = write_memory(e, root=root, dedupe=not args.no_dedupe,
                                    dry_run=args.dry_run)
        results.append((status, info))
        flag = {"written": "✅", "skipped_dup": "⏭️  dup", "dry_run": "🔍", "error": "❌"}[status]
        print(f"{flag} [{e.get('type', '?')}] {e.get('title', '?')} → {info}")
    bad = [r for r in results if r[0] == "error"]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Phase 2: 会话上下文持久化 — session_summarize.py (零依赖, 复用 memory_query).

两个子命令:

recover  (会话启动时调用, 5 秒预算内)
    读取 MEMORY.md 索引 + 记忆目录, 按日期降序取最近 N 个记忆文件,
    输出 "已恢复上下文: {总数} 记忆文件, 最近会话 {日期}" + 概览列表。
    无 Ollama/索引依赖, 纯文件系统操作, 秒级完成。

summarize  (会话结束时调用)
    将对话概要/关键决策/待办事项写入 memory/session_YYYY-MM-DD.md。
    同日多会话自动追加时间后缀 (session_YYYY-MM-DD_HHMM.md), 不覆盖。
    长文本建议用 --*-file 传入 (避免 Windows 命令行长度/编码问题)。

退出码: 0=成功; 2=用法错误或记忆目录不存在 (与 memory_query 一致).

用法:
  python scripts/session_summarize.py recover
  python scripts/session_summarize.py recover --root <memdir> --limit 3
  python scripts/session_summarize.py summarize --title "Phase 2 完成" \
      --summary "..." --decisions "..." --todos "..."
  python scripts/session_summarize.py summarize --summary-file summary.txt
"""

import argparse
import datetime
import pathlib
import sys

from memory_query import DEFAULT_ROOT, collect

DESC_MAX = 120  # recover 概览中描述截断长度


def _reconfigure():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def recover(root: pathlib.Path, limit: int = 5) -> int:
    """打印恢复摘要, 返回退出码。"""
    entries = collect(root)
    total = len(entries)
    if total == 0:
        print("📚 已恢复上下文: 0 记忆文件 (记忆目录为空)")
        return 0
    entries.sort(key=lambda e: (e["date"], e["name"]), reverse=True)
    latest = max(e["date"] for e in entries)
    print(f"📚 已恢复上下文: {total} 记忆文件, 最近会话 {latest}")
    print("─" * 64)
    for e in entries[:limit]:
        desc = e["description"].replace("\n", " ")
        if len(desc) > DESC_MAX:
            desc = desc[:DESC_MAX] + "…"
        print(f"{e['date']}  {e['type'] or '-':9}  {e['path'].name}")
        print(f"    {desc}")
    if total > limit:
        print(f"… 其余 {total - limit} 条记忆可用 memory_query.py 检索")
    return 0


def _load_file(path: str) -> str:
    """读取内容文件 (UTF-8), 失败抛 OSError 由调用方处理。"""
    return pathlib.Path(path).read_text(encoding="utf-8").rstrip("\n")


def summarize(root: pathlib.Path, title: str, summary: str,
              decisions: str, todos: str, date: str, time: str) -> int:
    """写入 session_YYYY-MM-DD[,_HHMM].md, 返回退出码。"""
    # 同日多会话: 基础名已存在 → 追加时间后缀, 仍冲突再 +_N
    base = root / f"session_{date}.md"
    if not base.exists():
        path = base
    else:
        stem = f"session_{date}_{time}"
        path = root / f"{stem}.md"
        n = 1
        while path.exists():
            path = root / f"{stem}_{n}.md"
            n += 1
    body = (
        f"---\nname: {path.stem}\ndescription: 会话记录 — {title}\n"
        f"type: session\ndate: {date}\n---\n\n"
        f"# 📝 会话记录 {date}\n\n"
        f"## 对话概要\n\n{summary or '(无)'}\n\n"
        f"## 关键决策\n\n{decisions or '(无)'}\n\n"
        f"## 待办事项\n\n{todos or '(无)'}\n"
    )
    path.write_text(body, encoding="utf-8")
    print(f"✅ 会话记录已写入: {path.name}")
    return 0


def main(argv=None) -> int:
    _reconfigure()
    # --root 主/子解析器双挂: 主解析器给默认值; 子解析器 default=SUPPRESS,
    # 避免子命令解析时用默认值覆盖主解析器已解析的 --root (argparse 经典坑)
    main_common = argparse.ArgumentParser(add_help=False)
    main_common.add_argument("--root", default=str(DEFAULT_ROOT), help="记忆目录")
    sub_common = argparse.ArgumentParser(add_help=False)
    sub_common.add_argument("--root", default=argparse.SUPPRESS, help=argparse.SUPPRESS)

    ap = argparse.ArgumentParser(description="会话上下文持久化 (Phase 2)", parents=[main_common])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_rec = sub.add_parser("recover", parents=[sub_common], help="会话启动恢复摘要")
    p_rec.add_argument("--limit", type=int, default=5, help="概览条数 (默认 5)")

    p_sum = sub.add_parser("summarize", parents=[sub_common], help="会话结束写入 session 文件")
    p_sum.add_argument("--title", default="会话记录", help="会话标题")
    p_sum.add_argument("--summary", default="", help="对话概要 (或 --summary-file)")
    p_sum.add_argument("--decisions", default="", help="关键决策 (或 --decisions-file)")
    p_sum.add_argument("--todos", default="", help="待办事项 (或 --todos-file)")
    p_sum.add_argument("--summary-file", default=None, help="概要内容文件 (UTF-8)")
    p_sum.add_argument("--decisions-file", default=None, help="决策内容文件 (UTF-8)")
    p_sum.add_argument("--todos-file", default=None, help="待办内容文件 (UTF-8)")
    p_sum.add_argument("--date", default=None, help="会话日期 YYYY-MM-DD (默认今天)")
    p_sum.add_argument("--time", default=None, help="会话时间 HHMM (默认现在, 同日多会话后缀)")
    args = ap.parse_args(argv)

    root = pathlib.Path(args.root)
    if not root.is_dir():
        print(f"ERROR: 记忆目录不存在: {root}", file=sys.stderr)
        return 2

    if args.cmd == "recover":
        return recover(root, args.limit)

    # ---- summarize ----
    contents = {"summary": args.summary, "decisions": args.decisions, "todos": args.todos}
    for field, flag in (("summary", args.summary_file), ("decisions", args.decisions_file),
                        ("todos", args.todos_file)):
        if flag:
            try:
                contents[field] = _load_file(flag)
            except OSError as e:
                print(f"ERROR: 读取 {flag} 失败: {e}", file=sys.stderr)
                return 2
    summary, decisions, todos = contents["summary"], contents["decisions"], contents["todos"]
    if not any((summary, decisions, todos)):
        print("ERROR: 无可写入内容 (需 --summary/--decisions/--todos 或对应 --*-file)",
              file=sys.stderr)
        return 2
    date = args.date or datetime.date.today().isoformat()
    try:
        datetime.date.fromisoformat(date)
    except ValueError:
        print("ERROR: 日期格式须为 YYYY-MM-DD", file=sys.stderr)
        return 2
    time = args.time or datetime.datetime.now().strftime("%H%M")
    return summarize(root, args.title, summary, decisions, todos, date, time)


if __name__ == "__main__":
    sys.exit(main())

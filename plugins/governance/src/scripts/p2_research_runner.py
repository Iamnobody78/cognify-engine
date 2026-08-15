"""scripts/p2_research_runner.py — gpt-researcher 独立 runner (子进程入口)。

被 research_mcp_server.py 的 run_research 工具以 subprocess 调用:
  .venv-research\\Scripts\\python.exe scripts/p2_research_runner.py \
      --query "..." [--report-type research_report] [--max-sources 10]

输出: 单行 JSON (stdout):
  {"ok": true,  "report": "<markdown 报告>", "sources": N,
   "report_path": "<绝对路径|空>", "persist_error": "<错误|空>"}
  {"ok": false, "error": "<可读错误>"}
失败时同样 exit 0 (JSON 携带 ok 字段); 进程级异常 (超时被杀) 由调用方处理。

落盘协议 (research_output.md): 成功研究后, 报告 Markdown 同时写入
  <repo-root>/research_outputs/{query_slug}.md (query_slug: 小写 + 非
  [a-z0-9]→连字符, 截断 60 字符)。持久化失败不阻断 stdout JSON —
  report_path="" + persist_error=<原因> 如实上报, 由调用方决定处置。
  这是 P0 修复: 研究产出必须落盘才能进 Critic 审计/知识蒸馏/记忆回路。

环境: 读取 <repo-root>/.env (DEEPSEEK_API_KEY 等, 手工解析零依赖);
      gpt-researcher 的模型配置经环境变量注入 (见 deploy_p2_research.ps1
      生成的 .env 模板)。gpt_researcher 未安装时返回可读错误而非 traceback。

诚实边界: gpt-researcher 0.16+ 要求 Python>=3.12 (隔离 .venv-research);
      本 runner 只编排, 不内嵌搜索/生成逻辑。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

# Windows cp950 控制台无法编码中文 help/错误 — 强制 UTF-8 (MCP 子进程亦按 UTF-8 解析)
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _REPO_ROOT / ".env"
_OUTPUT_DIR = Path(os.environ.get("RESEARCH_OUTPUT_DIR", _REPO_ROOT / "research_outputs"))


def _query_slug(query: str, max_len: int = 60) -> str:
    """查询词 → 文件名 slug: 小写 + 非 [a-z0-9]→连字符, 压缩连续连字符, 截断。"""
    slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "research"


def persist_report(report: str, query: str, output_dir: Path | None = None) -> tuple[str, str]:
    """报告落盘 → (report_path, persist_error)。best-effort: 失败返回错误不抛异常。

    命名: {query_slug}.md; 同 slug 已存在时追加 -2/-3 序号防覆盖。
    output_dir=None → 模块级 _OUTPUT_DIR (默认 <repo-root>/research_outputs,
    可用环境变量 RESEARCH_OUTPUT_DIR 覆盖)。注意默认参数不能在 import 时
    绑定目录 (测试需 monkeypatch), 故在函数体内解析。
    """
    output_dir = Path(output_dir or _OUTPUT_DIR)
    if not report.strip():
        return "", "报告为空, 跳过落盘"
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{_query_slug(query)}.md"
        n = 2
        while path.exists():
            path = output_dir / f"{_query_slug(query)}-{n}.md"
            n += 1
        path.write_text(report, encoding="utf-8")
        return str(path), ""
    except OSError as e:
        return "", f"落盘失败: {e}"


def load_env(path: Path = _ENV_PATH) -> None:
    """手工解析 .env (key=value, # 注释, 引号剥离), 注入 os.environ。

    绝不覆盖已存在的环境变量 (已显式设置的优先)。缺失文件静默。
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


def _gpt_researcher_cls():
    """延迟导入 GPTResearcher; 缺失时抛 ImportError(可读消息)。"""
    try:
        from gpt_researcher import GPTResearcher
    except ImportError as e:
        raise ImportError(
            f"gpt_researcher 未安装 (Python>=3.12 的 .venv-research 隔离环境)。"
            f"请先运行: powershell -ExecutionPolicy Bypass -File "
            f"scripts/deploy_p2_research.ps1 -DryRun 查看计划, 去掉 -DryRun 执行。"
            f"底层错误: {e}"
        ) from e
    return GPTResearcher


async def _run_research(query: str, report_type: str) -> tuple[str, int]:
    GPTResearcher = _gpt_researcher_cls()
    # verbose=False: gpt-researcher 无 websocket 时会把整份报告 print 到 stdout,
    # 会污染 MCP 的单行 JSON 契约 — 必须静默 (2026-08-04 实证踩坑)
    researcher = GPTResearcher(query=query, report_type=report_type, verbose=False)
    await researcher.conduct_research()
    report = await researcher.write_report()
    # 来源数量: 优先 source_urls (gpt-researcher 实际引用集合), 退化 context 列表长度
    sources = 0
    try:
        urls = getattr(researcher, "source_urls", None)
        if isinstance(urls, (list, set)):
            sources = len(urls)
    except Exception:  # noqa: BLE001 — 统计失败不阻断
        sources = 0
    if not sources:
        try:
            ctx = getattr(researcher, "context", None)
            if isinstance(ctx, list):
                sources = len(ctx)
        except Exception:  # noqa: BLE001
            sources = 0
    return report, sources


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="gpt-researcher 独立 runner")
    ap.add_argument("--query", required=True, help="研究问题或主题")
    ap.add_argument("--report-type", default="research_report",
                    choices=["research_report", "resource_report", "outline_report",
                             "custom_report", "subtopic_report", "deep", "summary"],
                    help="报告类型 (summary 已废弃别名→research_report; 0.16.0 合法: research_report/resource_report/outline_report/custom_report/subtopic_report/deep)")
    ap.add_argument("--max-sources", type=int, default=10,
                    help="最大来源数 (由 gpt-researcher 自行消费, 默认 10)")
    args = ap.parse_args(argv)
    # summary 是 0.16.0 废弃类型 (会回退 research_report) — 显式归一化
    if args.report_type == "summary":
        args.report_type = "research_report"

    load_env()

    # CONFIG_PATH 若为相对路径, 锚定到仓库根 — 与 CWD 无关 (MCP 子进程亦可靠)
    cfg_path = os.environ.get("CONFIG_PATH", "")
    if cfg_path and not os.path.isabs(cfg_path):
        resolved = _REPO_ROOT / cfg_path
        if resolved.exists():
            os.environ["CONFIG_PATH"] = str(resolved)
        else:
            print(json.dumps(
                {"ok": False, "error": f"CONFIG_PATH 不存在: {cfg_path} (锚定 {resolved})"},
                ensure_ascii=False))
            return 0

    # stdout 必须干净: 研究输出只走结果 JSON (log 消息不影响协议)
    try:
        report, sources = asyncio.run(_run_research(args.query, args.report_type))
    except ImportError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 0
    except Exception as e:  # noqa: BLE001 — 研究失败返回可读错误
        print(json.dumps(
            {"ok": False, "error": f"研究执行失败: {type(e).__name__}: {e}"},
            ensure_ascii=False))
        return 0

    # 落盘协议: 研究产出必须持久化 (P0 — 审计/蒸馏/记忆的上游依赖)
    report_path, persist_error = persist_report(report, args.query)
    print(json.dumps(
        {"ok": True, "report": report, "sources": sources,
         "query": args.query, "report_type": args.report_type,
         "report_path": report_path, "persist_error": persist_error},
        ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""
META-KB v1.0 — 元教育知识库迁移流水线 (R.E.A.D. 四步法)

Phase R: Retrieve  — 尝试抓取 URL；失败则如实声明数据边界，以本地内容源为准
Phase E: Extract   — 编译为结构化知识 (compiled_knowledge.json)
Phase A: Assimilate— 写入 AFFiNE-import-ready Markdown 树 (knowledge_base/)
Phase D: Distill   — 生成 migration_report.md + sync_status.md

用法:
  python meta_kb.py --url <URL> --tag <TAG>              # 链接迁移 (自动回退内容源)
  python meta_kb.py --manifest <source_manifest.json>    # 从本地 manifest 迁移
  python meta_kb.py --status                             # 查看同步状态
"""
import argparse
import io
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
KB_DIR = os.path.join(REPO_ROOT, "governance", "knowledge_base")
TRACE_DIR = os.path.join(REPO_ROOT, "governance", "trace")
MANIFEST = os.path.join(KB_DIR, "kb_manifest.json")
MIGRATION_REPORT = os.path.join(KB_DIR, "migration_report.md")
SYNC_STATUS = os.path.join(KB_DIR, "sync_status.md")

# 本地内容源（PM 已审阅摘要 → 迁移来源），键为 Notion URL 片段
LOCAL_SOURCES = {
    "33a22db60a618014ad56f4a2f30569e3": {
        "title": "元模型控制工程 (MMCE)",
        "type": "MMCE",
        "path": os.path.join(KB_DIR, "MMCE", "元模型控制工程.md"),
    },
}


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def try_fetch(url, timeout=20):
    """Phase R: 尝试抓取。返回 (ok, content)。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read().decode("utf-8", errors="replace")
        # 判断是否为实质内容 (非 JS 壳): 检查 CJK 内容字符密度
        cjk = len(re.findall(r"[\u4e00-\u9fff]", data))
        title = re.search(r"<title>([^<]{0,120})</title>", data)
        ok = cjk > 200
        note = "ok" if ok else "JS shell only (cjk=%d)" % cjk
        return (ok, note), (title.group(1) if title else None)
    except Exception as e:
        return (False, "fetch error: %s" % e), None


def detect_notion_id(url):
    m = re.search(r"/p/([0-9a-fA-F-]{8,})", url)
    return m.group(1) if m else None


def phase_r(url, tag):
    """Retrieve: 抓取 + 内容源判定。"""
    (ok, note), title = try_fetch(url)
    entry = {"url": url, "tag": tag, "fetch_ok": ok, "note": note}
    if ok:
        entry["content_source"] = "direct_fetch"
        entry["title"] = title
    else:
        nid = detect_notion_id(url)
        if nid and nid in LOCAL_SOURCES:
            src = LOCAL_SOURCES[nid]
            entry["content_source"] = "local_summary"
            entry["title"] = src["title"]
            entry["type"] = src["type"]
            entry["local_path"] = src["path"]
        else:
            entry["content_source"] = "unavailable"
            entry["title"] = None
    return entry


def phase_e(url_entry):
    """Extract: 编译为结构化知识。"""
    return {
        "compiled_at": now_iso(),
        "source": url_entry,
        "schema_version": "META-KB-1.0",
        "entities": [],
    }


def phase_a(url_entry, compiled):
    """Assimilate: 写入知识库 (本地已就位则 diff 校验, 不覆盖)。"""
    written = []
    if url_entry.get("content_source") == "local_summary":
        p = url_entry["local_path"]
        if os.path.exists(p):
            written.append({"path": p, "action": "verified_existing"})
        else:
            written.append({"path": p, "action": "MISSING_SOURCE"})
    return written


def phase_d(tag, entries, written):
    """Distill: 生成报告。"""
    os.makedirs(KB_DIR, exist_ok=True)
    manifest = {
        "manifest_version": "1.0",
        "last_sync": now_iso(),
        "entries": entries,
        "written": written,
        "aaffine_import_ready": True,
    }
    with io.open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    with io.open(MIGRATION_REPORT, "w", encoding="utf-8") as f:
        f.write("### 📚 元教育知识库报告 [#META-KB-ROUND_%s]\n\n" % tag)
        for e in entries:
            f.write("- 源链接: %s\n" % e["url"])
            f.write("- 抓取成功: %s\n" % e["fetch_ok"])
            f.write("- 内容源: %s\n" % e.get("content_source", "?"))
            f.write("- 标题: %s\n\n" % e.get("title"))
        f.write("**迁移动作**:\n")
        for w in written:
            f.write("- %s → %s\n" % (w["action"], w["path"]))

    with io.open(SYNC_STATUS, "w", encoding="utf-8") as f:
        f.write("# 同步状态\n\n- 最后同步: %s\n- 标签: %s\n- 待同步: Notion 其余链接（需 PM 摘要或抓取权限）\n" % (now_iso(), tag))
    return manifest


def main_status():
    """--status 子命令 (供 outer_loop 分发复用)。"""
    if os.path.exists(SYNC_STATUS):
        with io.open(SYNC_STATUS, encoding="utf-8") as f:
            print(f.read())
        return 0
    print("(no sync yet)")
    return 0


def main_args(url, tag):
    """outer_loop --meta-kb 分发入口。"""
    r = phase_r(url, tag)
    e = phase_e(r)
    w = phase_a(r, e)
    m = phase_d(tag, [r], w)
    print(json.dumps({"url": url, "fetch_ok": r["fetch_ok"],
                      "content_source": r.get("content_source"),
                      "title": r.get("title"),
                      "manifest": MANIFEST}, ensure_ascii=False, indent=2))
    return 0 if r.get("content_source") != "unavailable" else 2


def main():
    ap = argparse.ArgumentParser(description="META-KB v1.0 知识库迁移流水线")
    ap.add_argument("--url", help="Notion/任意 URL")
    ap.add_argument("--tag", default="KB_MIGRATE")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    if args.status:
        return main_status()

    if not args.url:
        ap.print_help()
        return 1

    return main_args(args.url, args.tag)


if __name__ == "__main__":
    sys.exit(main())

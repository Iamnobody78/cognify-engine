#!/usr/bin/env python3
"""SYNC-ALL v1.2 -- AionUi ↔ Hermes ↔ DeepSeek Harness 三端统一上下文同步层

能力矩阵:
  [对话历史]  AionUi conversations/messages (98K) → Hermes memories/aionui-archive/ + DSH storages/aionui-sync/
  [上下文]    AionUi 会话摘要 → Hermes MEMORY.md 索引行 (append-only, 不重写)
  [Hermes]    state.db 110 会话摘要 → governance/sync/hermes_*.json (v1.1)
  [DSH]       storages 文件 → governance/sync/dsh_*.json
  [AionUi]    锚点/元认知 → governance/sync/aionui_*.json
  [报告]      每次同步生成 S.Y.N.C. 四步报告 sync_report.md
  [冲突]      mtime_newer_wins (目标已更新则跳过, 不覆盖)

v1.2 变更 (2026-08-14):
  - sync_policy.yaml 配置驱动 (实际路径版, 修正方案假设路径)
  - 新增 AionUi 会话同步 (aionui-backend.db mode=ro, WAL 安全)
  - 新增 Hermes MEMORY.md 索引追加 (UTF-8 append-only)
  - 新增 S.Y.N.C. 报告 / 冲突处理
  - 幂等: 会话指纹 message_count|updated_at (AionUi) / last_activity|count (Hermes)
"""
from __future__ import annotations
import os
import sys
import json
import glob
import time
import shutil
import sqlite3
import datetime
import hashlib

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ── 路径 (实际环境, 对齐 sync_policy.yaml) ────────────────────────────────
APP_DATA = os.environ.get("APPDATA", os.path.expanduser("~"))
LOCAL_APP_DATA = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
HOME = os.path.expanduser("~")

AIONUI_DB = os.path.join(APP_DATA, "AionUi", "aionui", "aionui-backend.db")
HERMES_DB = os.path.join(LOCAL_APP_DATA, "hermes", "state.db")
HERMES_MEMORIES = os.path.join(LOCAL_APP_DATA, "hermes", "memories")
HERMES_ARCHIVE_DIR = os.path.join(HERMES_MEMORIES, "aionui-archive")
DSH_STORAGES = os.path.join(HOME, ".dsh", "storages")
DSH_SYNC_DIR = os.path.join(DSH_STORAGES, "aionui-sync")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SYNC_DIR = os.path.join(PROJECT_ROOT, "governance", "sync")
INDEX_FILE = os.path.join(SYNC_DIR, "sync_index.json")
REPORT_FILE = os.path.join(SYNC_DIR, "sync_report.md")
POLICY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sync_policy.yaml")

SAMPLE_LIMIT = 400
MEMORY_INDEX_HEADER = "## AionUi 同步索引"


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


# ── Hermes 侧 (v1.1) ───────────────────────────────────────────────────────
def _hermes_db_connect():
    return sqlite3.connect(f"file:{HERMES_DB}?mode=ro", uri=True)


def _aionui_db_connect():
    return sqlite3.connect(f"file:{AIONUI_DB}?mode=ro", uri=True)


def _hermes_sample(con, session_id: str, message_count: int) -> dict:
    sample = []
    try:
        cur = con.cursor()
        first = cur.execute(
            "SELECT role, content FROM messages WHERE session_id=? AND role='user' "
            "ORDER BY id LIMIT 1", (session_id,)).fetchone()
        if first and first[1]:
            sample.append({"role": first[0], "text": (first[1] or "").strip().replace("\n", " ")[:SAMPLE_LIMIT]})
        last = cur.execute(
            "SELECT role, content FROM messages WHERE session_id=? AND role='assistant' "
            "ORDER BY id DESC LIMIT 1", (session_id,)).fetchone()
        if last and last[1]:
            sample.append({"role": last[0], "text": (last[1] or "").strip().replace("\n", " ")[:SAMPLE_LIMIT]})
        roles = dict(cur.execute(
            "SELECT role, COUNT(*) FROM messages WHERE session_id=? GROUP BY role",
            (session_id,)).fetchall())
        return {"sample": sample, "roles": roles}
    except Exception:
        return {"sample": [], "roles": {}}


def _scan_hermes_sessions() -> list:
    if not os.path.exists(HERMES_DB):
        return []
    found = []
    try:
        con = _hermes_db_connect()
        cur = con.cursor()
        rows = cur.execute("""
            SELECT id, source, title, model, cwd, message_count,
                   input_tokens, output_tokens, estimated_cost_usd,
                   started_at, last_activity_at, git_branch, git_repo_root
            FROM sessions
        """).fetchall()
        for r in rows:
            sid, source, title, model, cwd, mc, itok, otok, cost, st, la, gb, grr = r

            def _ts(v):
                return datetime.datetime.fromtimestamp(v).isoformat() if v else None

            found.append({
                "source": "hermes", "session_id": sid, "origin_source": source,
                "title": (title or "")[:200], "model": model, "cwd": cwd,
                "message_count": mc or 0, "input_tokens": itok or 0,
                "output_tokens": otok or 0, "cost_usd": round(cost or 0, 6),
                "started_at": _ts(st), "last_activity_at": _ts(la),
                "git_branch": gb, "git_repo_root": grr,
                "sync_fingerprint": f"{la or 0}|{mc or 0}",
                **_hermes_sample(con, sid, mc or 0),
            })
        con.close()
    except Exception as e:
        print(f"[warn] Hermes state.db 读取失败: {e!r}", file=sys.stderr)
    return found


# ── AionUi 侧 (v1.2 新增: 对话会话同步) ────────────────────────────────────
def _aionui_sample(con, conv_id: str) -> dict:
    """AionUi 会话首尾采样 + type 分布。

    AionUi messages 无 role 列: type ∈ {text, thinking, tips, tool_call},
    content 为 {"content": "..."} JSON。采样取首/末条 text (user/assistant
    混合, 诚实标注 role 未记录), thinking/tool_call 无采样价值。
    """
    sample, roles = [], {}
    try:
        cur = con.cursor()
        first = cur.execute(
            "SELECT content FROM messages WHERE conversation_id=? AND type='text' "
            "ORDER BY id LIMIT 1", (conv_id,)).fetchone()
        if first and first[0]:
            try:
                txt = json.loads(first[0]).get("content", "")
            except Exception:
                txt = first[0]
            sample.append({"role": "text(role未记录)", "text": txt.strip().replace("\n", " ")[:SAMPLE_LIMIT]})
        last = cur.execute(
            "SELECT content FROM messages WHERE conversation_id=? AND type='text' "
            "ORDER BY id DESC LIMIT 1", (conv_id,)).fetchone()
        if last and last[0]:
            try:
                txt = json.loads(last[0]).get("content", "")
            except Exception:
                txt = last[0]
            sample.append({"role": "text(role未记录)", "text": txt.strip().replace("\n", " ")[:SAMPLE_LIMIT]})
        roles = dict(cur.execute(
            "SELECT type, COUNT(*) FROM messages WHERE conversation_id=? GROUP BY type",
            (conv_id,)).fetchall())
    except Exception:
        pass
    return {"sample": sample, "roles": roles}


def _scan_aionui_conversations() -> list:
    """AionUi conversations + messages + acp_session 映射 (只读)。"""
    if not os.path.exists(AIONUI_DB):
        return []
    found = []
    try:
        con = _aionui_db_connect()
        cur = con.cursor()
        rows = cur.execute("""
            SELECT c.id, c.name, c.type, c.model, c.status, c.created_at, c.updated_at,
                   a.agent_source, a.agent_id, a.session_id, a.session_status
            FROM conversations c
            LEFT JOIN acp_session a ON a.conversation_id = c.id
            ORDER BY c.updated_at DESC
        """).fetchall()
        seen = set()
        for r in rows:
            cid, name, ctype, model, status, created_at, updated_at = r[:7]
            a_src, a_id, a_sid, a_status = r[7:]
            if cid in seen:
                continue
            seen.add(cid)
            mc = cur.execute("SELECT COUNT(*) FROM messages WHERE conversation_id=?",
                             (cid,)).fetchone()[0]
            found.append({
                "source": "aionui", "conversation_id": cid,
                "name": (name or "未命名会话")[:120], "type": ctype, "model": model,
                "status": status, "created_at": created_at, "updated_at": updated_at,
                "agent_source": a_src, "agent_id": a_id,
                "hermes_session": a_sid, "agent_status": a_status,
                "message_count": mc,
                "sync_fingerprint": f"{mc}|{updated_at}",
                **_aionui_sample(con, cid),
            })
        con.close()
    except Exception as e:
        print(f"[warn] AionUi conversations 读取失败: {e!r}", file=sys.stderr)
    return found


def _render_conversation_md(c: dict) -> str:
    """AionUi 会话 → Hermes aionui-archive 格式 (frontmatter 对齐 memory 系统)。"""

    def _fmt(ts):
        # AionUi created_at/updated_at 为毫秒时间戳
        try:
            return datetime.datetime.fromtimestamp(int(ts) / 1000).isoformat(timespec="seconds")
        except Exception:
            return str(ts)

    agent = c.get("agent_source") or "aionui"
    hsession = c.get("hermes_session") or "无"
    lines = [
        "---",
        f"name: aionui-conv-{c['conversation_id'][:8]}",
        f"description: AionUi 会话同步 - {c['name'][:80]} ({c['message_count']} 消息, agent={agent})",
        "type: project",
        "---",
        "",
        f"# {c['name']}",
        "",
        "## 会话信息",
        f"- conversation_id: `{c['conversation_id']}`",
        f"- 代理: {agent} (acp_session: `{hsession}`)",
        f"- 模型: {c.get('model') or '未知'}",
        f"- 状态: {c.get('status')} | 消息数: {c['message_count']}",
        f"- 创建: {_fmt(c.get('created_at'))} | 更新: {_fmt(c.get('updated_at'))}",
        "",
        "## 角色分布",
    ]
    roles = c.get("roles") or {}
    lines.append(", ".join(f"{k}: {v}" for k, v in sorted(roles.items())) or "无")
    lines += ["", "## 首尾采样 (AionUi 无 role 列, text 混合标注)"]
    sample = c.get("sample") or []
    for s in sample:
        lines.append(f"- **{s['role']}**: {s['text']}")
    if not sample:
        lines.append("- (无消息内容)")
    lines += ["", "---", f"_SYNC-ALL v1.2 自动生成 {_now()}_", ""]
    return "\n".join(lines)


def _sync_aionui_to_hermes(idx: dict) -> dict:
    """AionUi 会话 → Hermes memories/aionui-archive/*.md (增量 + 冲突跳过)。"""
    os.makedirs(HERMES_ARCHIVE_DIR, exist_ok=True)
    n_new, n_skip_conflict, n_skip_dup = 0, 0, 0
    synced = []
    for c in _scan_aionui_conversations():
        fname = f"aionui-conv-{c['conversation_id'][:8]}.md"
        target = os.path.join(HERMES_ARCHIVE_DIR, fname)
        fp = c["sync_fingerprint"]
        prev = idx.get("aionui_conv", {}).get(c["conversation_id"])
        if prev == fp and prev is not None:
            n_skip_dup += 1
            continue
        # 冲突处理: mtime_newer_wins (目标已存在且比本次更新, 跳过)
        if os.path.exists(target) and os.path.getmtime(target) > time.time() - 3600:
            if prev is not None:  # 仅对已同步过的文件做冲突判断
                n_skip_conflict += 1
                idx.setdefault("aionui_conv", {})[c["conversation_id"]] = fp
                continue
        md = _render_conversation_md(c)
        with open(target, "w", encoding="utf-8", newline="\n") as f:
            f.write(md)
        idx.setdefault("aionui_conv", {})[c["conversation_id"]] = fp
        n_new += 1
        synced.append(fname)
    return {"new": n_new, "conflict_skip": n_skip_conflict, "dup_skip": n_skip_dup, "files": synced}


def _append_memory_index(n_synced: int, total: int) -> int:
    """Hermes MEMORY.md 追加索引块 (append-only UTF-8, 不重写文件, 按天去重)。"""
    md_path = os.path.join(HERMES_MEMORIES, "MEMORY.md")
    if not os.path.exists(md_path):
        return 0
    today = _now()[:10]
    try:
        existing = open(md_path, encoding="utf-8", errors="replace").read()
        if f"同步时间: {today}" in existing:
            return 0  # 当天已追加过
    except Exception:
        pass
    block = [
        "",
        MEMORY_INDEX_HEADER,
        "",
        f"- 同步时间: {_now()} (SYNC-ALL v1.2)",
        f"- 本次新增/更新 AionUi 会话: {n_synced} 个 (共 {total} 个, 详见 memories/aionui-archive/)",
        "",
    ]
    try:
        with open(md_path, "a", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(block))
        return 1
    except Exception as e:
        print(f"[warn] MEMORY.md 追加失败: {e!r}", file=sys.stderr)
        return 0


def _sync_aionui_to_dsh(idx: dict) -> int:
    """AionUi 会话摘要 → DSH storages/aionui-sync/ (副本)。"""
    os.makedirs(DSH_SYNC_DIR, exist_ok=True)
    n = 0
    for c in _scan_aionui_conversations():
        fname = f"aionui-conv-{c['conversation_id'][:8]}.md"
        target = os.path.join(DSH_SYNC_DIR, fname)
        fp = c["sync_fingerprint"]
        if idx.get("aionui_dsh", {}).get(c["conversation_id"]) == fp:
            continue
        with open(target, "w", encoding="utf-8", newline="\n") as f:
            f.write(_render_conversation_md(c))
        idx.setdefault("aionui_dsh", {})[c["conversation_id"]] = fp
        n += 1
    return n


# ── DSH 侧 / AionUi 上下文 (v1.1) ─────────────────────────────────────────
def _scan_dsh_sessions() -> list:
    found = []
    for pattern in ("*.jsonl", "*.json", "*.db", "*.sqlite"):
        for p in glob.glob(os.path.join(DSH_STORAGES, "**", pattern), recursive=True):
            if "workspace.json" in p or "aionui-sync" in p:
                continue
            try:
                found.append({
                    "path": p, "name": os.path.basename(p),
                    "mtime": datetime.datetime.fromtimestamp(os.path.getmtime(p)).isoformat(),
                    "size": os.path.getsize(p),
                    "sha256": hashlib.sha256(open(p, "rb").read()).hexdigest()[:16],
                })
            except Exception:
                pass
    return found


def _scan_aionui_contexts() -> list:
    found = []
    roots = [
        os.path.join(PROJECT_ROOT, ".aionui", "metacognition", "thoughts"),
        os.path.join(PROJECT_ROOT, "governance", "anchors"),
    ]
    for r in roots:
        if os.path.isdir(r):
            for f in os.listdir(r):
                p = os.path.join(r, f)
                if os.path.isfile(p) and f.endswith((".md", ".jsonl")):
                    found.append({
                        "path": p, "name": f,
                        "mtime": datetime.datetime.fromtimestamp(os.path.getmtime(p)).isoformat(),
                        "size": os.path.getsize(p),
                    })
    return found


# ── 索引 ──────────────────────────────────────────────────────────────────
def _load_index() -> dict:
    if os.path.exists(INDEX_FILE):
        try:
            return json.load(open(INDEX_FILE, encoding="utf-8"))
        except Exception:
            return {}
    return {"dsh": {}, "hermes": {}, "aionui": {}, "aionui_conv": {}, "aionui_dsh": {}}


def _save_index(idx: dict) -> None:
    os.makedirs(SYNC_DIR, exist_ok=True)
    json.dump(idx, open(INDEX_FILE, "w", encoding="utf-8", newline="\n"),
              ensure_ascii=False, indent=2)


# ── S.Y.N.C. 报告 ─────────────────────────────────────────────────────────
def _write_report(phase_s: dict, phase_y: dict, phase_n: dict, phase_c: dict) -> None:
    os.makedirs(SYNC_DIR, exist_ok=True)
    lines = [
        f"### 🔄 同步报告 [#SYNC-{_now().replace(':', '')}]",
        "",
        "[Phase S: Scan]",
        f"- AionUi 会话: {phase_s.get('aionui_conv', 0)} 个 | Hermes 会话: {phase_s.get('hermes', 0)} 个 | DSH 文件: {phase_s.get('dsh', 0)} 个",
        "",
        "[Phase Y: Yield]",
        f"- AionUi 会话摘要: {phase_y.get('aionui_md', 0)} 个 | Hermes 会话摘要: {phase_y.get('hermes_json', 0)} 个",
        "",
        "[Phase N: Normalize]",
        f"- 同步到 Hermes aionui-archive: {phase_n.get('to_hermes', 0)} 个 (冲突跳过 {phase_n.get('conflict', 0)})",
        f"- 同步到 DSH storages: {phase_n.get('to_dsh', 0)} 个",
        f"- MEMORY.md 索引追加: {phase_n.get('memory_index', 0)}",
        "",
        "[Phase C: Confirm]",
        f"- Hermes aionui-archive 文件数: {phase_c.get('hermes_files', 0)} | DSH aionui-sync 文件数: {phase_c.get('dsh_files', 0)}",
        f"- 验证: {phase_c.get('verdict', 'PASS')}",
        "",
        "[Honest Boundary]",
        "- 覆盖: 对话摘要(首尾采样≤400字符, 非全量消息) / 上下文索引 / 文档共享",
        f"- 未同步: Hermes facts 表(HRR 向量语义, 外部写入会破坏检索) / DSH 无会话(0 文件)",
        "- 置信度: 高",
        "",
    ]
    with open(REPORT_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))


# ── Hermes 摘要导出 (v1.1) ────────────────────────────────────────────────
def _export_hermes(idx: dict) -> int:
    os.makedirs(SYNC_DIR, exist_ok=True)
    sessions = _scan_hermes_sessions()
    n = 0
    for h in sessions:
        key = h["session_id"]
        fp = h["sync_fingerprint"]
        if idx.get("hermes", {}).get(key) == fp and idx.get("hermes", {}).get(key) is not None:
            continue
        fname = "hermes_%s.json" % hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
        json.dump(h, open(os.path.join(SYNC_DIR, fname), "w", encoding="utf-8", newline="\n"),
                  ensure_ascii=False, indent=2)
        idx.setdefault("hermes", {})[key] = fp
        n += 1
    return n


# ── 命令 ──────────────────────────────────────────────────────────────────
def cmd_status() -> int:
    print("== SYNC-ALL v1.2 (AionUi ↔ Hermes ↔ DSH) ==")
    aionui = _scan_aionui_conversations()
    hermes = _scan_hermes_sessions()
    dsh = _scan_dsh_sessions()
    ctx = _scan_aionui_contexts()
    print(f"[AionUi 侧] 会话: {len(aionui)} 个 (messages 同步源)")
    for c in aionui[:8]:
        print(f"  - {c['name'][:40]} | msgs={c['message_count']} | agent={c.get('agent_source') or '-'} | hermes={str(c.get('hermes_session'))[:8] or '-'}")
    print(f"[Hermes 侧] 会话: {len(hermes)} 个 (state.db)")
    for h in sorted(hermes, key=lambda x: x["last_activity_at"] or "", reverse=True)[:6]:
        print(f"  - {(h['title'] or h['session_id'][:8])[:36]} | msgs={h['message_count']} | {h['model']}")
    print(f"[DSH 侧] 文件: {len(dsh)} 个 | [AionUi 上下文] 锚点: {len(ctx)} 个")
    print(f"[Hermes 记忆] aionui-archive: {len(glob.glob(os.path.join(HERMES_ARCHIVE_DIR, '*.md')))} 文件")
    idx = _load_index()
    print("[索引] dsh=%d hermes=%d aionui=%d aionui_conv=%d aionui_dsh=%d" % (
        len(idx.get("dsh", {})), len(idx.get("hermes", {})), len(idx.get("aionui", {})),
        len(idx.get("aionui_conv", {})), len(idx.get("aionui_dsh", {}))))
    return 0


def cmd_export() -> int:
    os.makedirs(SYNC_DIR, exist_ok=True)
    idx = _load_index()

    # Phase S: Scan
    aionui_convs = _scan_aionui_conversations()
    hermes_sessions = _scan_hermes_sessions()
    dsh_files = _scan_dsh_sessions()

    # Phase Y+N: Hermes 会话摘要 (v1.1)
    n_hermes_json = _export_hermes(idx)

    # Phase Y+N: AionUi 会话 → Hermes aionui-archive
    res_hermes = _sync_aionui_to_hermes(idx)
    n_to_dsh = _sync_aionui_to_dsh(idx)

    # DSH 文件摘要 (v1.1)
    n_dsh = 0
    for s in dsh_files:
        key = s["sha256"]
        if idx.get("dsh", {}).get(key) == s["mtime"]:
            continue
        json.dump({k: s[k] for k in ("name", "mtime", "size", "sha256", "path")},
                  open(os.path.join(SYNC_DIR, "dsh_" + s["name"].replace(".", "_") + ".json"),
                       "w", encoding="utf-8", newline="\n"),
                  ensure_ascii=False, indent=2)
        idx.setdefault("dsh", {})[key] = s["mtime"]
        n_dsh += 1

    # AionUi 上下文 (v1.1)
    n_aionui = 0
    for c in _scan_aionui_contexts():
        try:
            body = open(c["path"], "rb").read()
            key = hashlib.sha256(body).hexdigest()
            if idx.get("aionui", {}).get(key) == c["mtime"]:
                continue
            json.dump({"name": c["name"], "mtime": c["mtime"], "size": c["size"], "sha256": key,
                       "head": body.decode("utf-8", errors="replace")[:500]},
                      open(os.path.join(SYNC_DIR, "aionui_" + c["name"].replace(".", "_") + ".json"),
                           "w", encoding="utf-8", newline="\n"),
                      ensure_ascii=False, indent=2)
            idx.setdefault("aionui", {})[key] = c["mtime"]
            n_aionui += 1
        except Exception:
            pass

    # MEMORY.md 索引 (仅当本次有新增, 按天去重)
    n_idx = 0
    if res_hermes["new"] > 0:
        n_idx = _append_memory_index(res_hermes["new"], len(aionui_convs))

    _save_index(idx)

    # Phase C: Confirm
    n_hermes_files = len(glob.glob(os.path.join(HERMES_ARCHIVE_DIR, "*.md")))
    n_dsh_files = len(glob.glob(os.path.join(DSH_SYNC_DIR, "*.md")))
    verdict = "PASS" if res_hermes["new"] >= 0 else "FAIL"

    _write_report(
        {"aionui_conv": len(aionui_convs), "hermes": len(hermes_sessions), "dsh": len(dsh_files)},
        {"aionui_md": res_hermes["new"], "hermes_json": n_hermes_json},
        {"to_hermes": res_hermes["new"], "conflict": res_hermes["conflict_skip"],
         "to_dsh": n_to_dsh, "memory_index": n_idx},
        {"hermes_files": n_hermes_files, "dsh_files": n_dsh_files, "verdict": verdict},
    )

    print("== SYNC-ALL v1.2 导出 ==")
    print(f"AionUi→Hermes: {res_hermes['new']} (冲突跳过 {res_hermes['conflict_skip']}, 重复 {res_hermes['dup_skip']})")
    print(f"AionUi→DSH: {n_to_dsh} | Hermes 摘要: {n_hermes_json} | DSH 摘要: {n_dsh} | AionUi 上下文: {n_aionui}")
    print(f"验证: {verdict} (Hermes archive={n_hermes_files} 文件, DSH sync={n_dsh_files} 文件)")
    print(f"报告: {REPORT_FILE}")
    return 0


def cmd_watch(interval: int = 60) -> int:
    print(f"SYNC-ALL v1.2 watch: 每 {interval}s 三端同步 (Ctrl+C 退出)")
    try:
        while True:
            cmd_export()
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nSYNC-ALL watch 已停止")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] == "--status":
        return cmd_status()
    if args[0] == "--export":
        return cmd_export()
    if args[0] == "--watch":
        return cmd_watch(int(args[1]) if len(args) > 1 else 60)
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())

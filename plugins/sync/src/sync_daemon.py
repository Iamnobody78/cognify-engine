#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TRI-SYNC-DAEMON v1.0 — Hermes / AionUi / DSH 三方同步守护进程
=============================================================
职责 (D1-D6):
  D1 对话同步   : AionUi conversations/  <-> hub/conversations (双向, 时间戳优先)
  D2 记忆同步   : Hermes memories/       ->  hub/memory        (单向, Hermes 权威)
  D3 状态同步   : hub/state/state.json    (三方心跳 + 游标 + 统计)
  D4 冲突解决   : 时间戳优先 + 按类权威源; 败者快照进 backup/conflicts/
  D5 心跳监控   : 每 tick 探测三方可达性, 写 state/heartbeat.json
  D6 自愈恢复   : 目标离线时操作入队 queues/pending/, 恢复后重放

纯标准库实现 (Python >= 3.8, Windows/Linux 通用)。
用法:
  python sync_daemon.py --once            # 单轮同步 (验证用)
  python sync_daemon.py --daemon          # 常驻循环 (默认)
  python sync_daemon.py --interval 60     # 覆盖轮询间隔
  python sync_daemon.py --config <path>   # 指定配置
"""

import argparse
import faulthandler
import hashlib
import json
import logging
import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

VERSION = "1.0.0"
DEFAULT_CONFIG = Path(__file__).resolve().parent / "sync_config.yaml"


# ---------------------------------------------------------------- utils
def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def ts_stamp():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def fast_key(path):
    st = path.stat()
    return (st.st_size, int(st.st_mtime_ns))


def load_config(path):
    if yaml is None:
        raise RuntimeError("PyYAML 不可用, 无法解析配置")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class Logger:
    """双通道日志: 人类可读 sync.log + 结构化 sync_log.jsonl"""

    def __init__(self, log_dir: Path, max_bytes=512_000):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "sync.log"
        self.jsonl = self.log_dir / "sync_log.jsonl"
        self.conflicts = self.log_dir / "conflicts.jsonl"
        self.max_bytes = max_bytes
        self._log = logging.getLogger("trisync")
        self._log.setLevel(logging.INFO)
        if not self._log.handlers:
            h = logging.FileHandler(self.log_file, encoding="utf-8")
            h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            self._log.addHandler(h)

    def info(self, msg):
        self._log.info(msg)

    def error(self, msg):
        self._log.error(msg)

    def rotate(self):
        if self.log_file.exists() and self.log_file.stat().st_size > self.max_bytes:
            try:
                self.log_file.rename(self.log_file.with_suffix(".log.old"))
            except OSError:
                pass

    def event(self, **kw):
        rec = {"ts": now_iso(), **kw}
        try:
            with open(self.jsonl, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError as e:
            self.error(f"write sync_log.jsonl failed: {e}")

    def conflict(self, **kw):
        rec = {"ts": now_iso(), **kw}
        try:
            with open(self.conflicts, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError as e:
            self.error(f"write conflicts.jsonl failed: {e}")


# ---------------------------------------------------------------- state
class SyncState:
    def __init__(self, state_dir: Path):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.state_dir / "state.json"
        self.lock_path = self.state_dir / "daemon.lock"
        self.heartbeat = self.state_dir / "heartbeat.json"
        self.big_files = self.state_dir / "big_files.json"
        self.data = {
            "version": VERSION,
            "created": now_iso(),
            "last_run": None,
            "cursors": {},
            "stats": {"total_ticks": 0, "copied": 0, "conflicts": 0, "errors": 0},
        }
        self._load()

    def _load(self):
        try:
            if self.path.exists():
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
        except (OSError, json.JSONDecodeError):
            pass

    def save(self):
        self.data["last_run"] = now_iso()
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def cursor(self, cls):
        return self.data["cursors"].setdefault(cls, {})

    def acquire_lock(self):
        pid = os.getpid()
        if self.lock_path.exists():
            try:
                old = json.loads(self.lock_path.read_text(encoding="utf-8"))
                if self._pid_alive(old.get("pid")):
                    print(f"已有守护实例运行 (PID {old['pid']}), 退出", file=sys.stderr)
                    sys.exit(2)
            except (OSError, json.JSONDecodeError):
                pass
        self.lock_path.write_text(
            json.dumps({"pid": pid, "started": now_iso()}), encoding="utf-8"
        )
        try:
            (self.lock_path.parent / "daemon.pid").write_text(
                str(pid), encoding="utf-8")
        except OSError:
            pass

    @staticmethod
    def _pid_alive(pid):
        if not pid:
            return False
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if not h:
                return False
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        except Exception:
            return False

    def release_lock(self):
        try:
            self.lock_path.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------- sync engine
class TriSyncEngine:
    def __init__(self, cfg, log: Logger, state: SyncState):
        self.cfg = cfg
        self.log = log
        self.state = state
        self.sync = cfg["sync"]
        self.hub = Path(cfg["hub"]["root"])
        self.backup_root = Path(cfg["backup"]["conflict_dir"])
        self.authority = cfg["authority"]
        self.excludes = set(cfg["exclude"])
        self.max_mb = float(self.sync.get("max_file_mb", 10))
        self.last_db_backup = 0.0

    # ---- helpers
    def _excluded(self, rel: str, name: str) -> bool:
        for pat in self.excludes:
            if pat == name:
                return True
            if pat.startswith("*") and name.endswith(pat[1:]):
                return True
            if "/" + pat + "/" in "/" + rel + "/":
                return True
        return False

    def _too_big(self, path: Path) -> bool:
        if self.max_mb <= 0:
            return False
        try:
            return path.stat().st_size > self.max_mb * 1024 * 1024
        except OSError:
            return True

    def _conflict(self, cls, rel, src, dst, src_key, dst_key, cursor_key):
        """时间戳优先 + 权威源覆盖。返回 (winner_path, loser_path)。"""
        authority = self.authority.get(cls, "timestamp")
        if authority != "timestamp":
            winner = src if authority == self._class_source(cls) else dst
            loser = dst if winner == src else src
            return winner, loser
        # timestamp 策略: mtime 新者胜; 平局取 src
        if src_key[1] >= dst_key[1]:
            return src, dst
        return dst, src

    @staticmethod
    def _class_source(cls):
        return {"memory": "hermes", "config": "dsh", "sessions": "dsh",
                "workspace": "aionui", "conversations": "timestamp",
                "registry": "timestamp"}.get(cls, "timestamp")

    def _stash_loser(self, cls, rel, loser: Path):
        dest = self.backup_root / cls / ts_stamp() / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(loser, dest)
        self.log.conflict(class_name=cls, relpath=rel, loser=str(loser),
                          stashed=str(dest))

    def _copy(self, src: Path, dst: Path):
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".tri-tmp")
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)

    def _mirror_one(self, cls, src: Path, dst_root: Path, rel: str,
                    cursor, two_way: bool, stats):
        """同步单个文件 src -> dst_root/rel, 处理冲突。返回是否复制。"""
        dst = dst_root / rel
        src_key = fast_key(src)
        dst_exists = dst.exists()
        dst_key = fast_key(dst) if dst_exists else None
        ck = cursor.get(rel)

        # 完全一致 (含 cursor 记录) -> 跳过
        if dst_exists and ck and dst_key == tuple(ck["key"]) and src_key == tuple(ck["key"]):
            return False
        if dst_exists and dst_key == src_key:
            cursor[rel] = {"key": list(src_key), "hash": None}
            return False

        # 双向且双方都在 cursor 之后被改 -> 冲突
        if two_way and dst_exists and ck and dst_key != tuple(ck["key"]) \
                and src_key != tuple(ck["key"]) and dst_key != src_key:
            winner, loser = self._conflict(cls, rel, src, dst, src_key, dst_key, ck)
            self._stash_loser(cls, rel, loser)
            if winner == src:
                self._copy(src, dst)
            else:
                self._copy(dst, src)
            self.state.data["stats"]["conflicts"] += 1
            stats["conflicts"] += 1
            cursor[rel] = {"key": list(fast_key(winner)), "hash": None}
            return True

        if dst_exists and dst_key == src_key:
            cursor[rel] = {"key": list(src_key), "hash": None}
            return False

        # 内容级对比: 仅当 size 相同且 mtime 不同时哈希
        need_hash = dst_exists and dst_key[0] == src_key[0] and dst_key[1] != src_key[1]
        if need_hash:
            try:
                if sha256_file(src) == sha256_file(dst):
                    cursor[rel] = {"key": list(src_key), "hash": None}
                    return False
            except OSError as e:
                self.log.error(f"hash fail {rel}: {e}")

        if dst_exists and dst_key[1] > src_key[1] and two_way:
            # dst 更新 -> 反向推回 src (双向)
            self._copy(dst, src)
            cursor[rel] = {"key": list(dst_key), "hash": None}
            stats["pushed"] += 1
            return True

        self._copy(src, dst)
        cursor[rel] = {"key": list(src_key), "hash": None}
        stats["copied"] += 1
        return True

    @staticmethod
    def _is_reparse(p: Path) -> bool:
        """Windows junction/symlink 探测 (reparse point), 避免 os.walk 穿透导致
        递归镜像/重复物化。Python 3.11 无 os.path.isjunction, 用 st_file_attributes。"""
        try:
            st = p.stat(follow_symlinks=False)
            return bool(getattr(st, "st_file_attributes", 0) & 0x400)
        except OSError:
            return True

    def mirror_dir(self, cls, src_root: Path, dst_root: Path,
                   two_way=False, stats=None, walk_root=None):
        """增量镜像目录。返回 stats dict。"""
        if stats is None:
            stats = {"copied": 0, "pushed": 0, "removed": 0, "conflicts": 0,
                     "skipped_big": 0}
        if not src_root.exists():
            return stats
        src_root, dst_root = Path(src_root), Path(dst_root)
        dst_root.mkdir(parents=True, exist_ok=True)
        cursor = self.state.cursor(cls)
        seen = set()

        for dirpath, dirnames, filenames in os.walk(src_root):
            dirpath_p = Path(dirpath)
            rel_dir = dirpath_p.relative_to(src_root).as_posix()
            pruned = []
            for d in dirnames:
                if self._excluded(rel_dir + "/" + d, d):
                    continue
                if self._is_reparse(dirpath_p / d):
                    continue  # 不穿透 junction/symlink
                pruned.append(d)
            dirnames[:] = pruned
            for name in filenames:
                rel = (rel_dir + "/" + name) if rel_dir != "." else name
                if self._excluded(rel, name):
                    continue
                fp = dirpath_p / name
                seen.add(rel)
                if self._too_big(fp):
                    stats["skipped_big"] += 1
                    self._note_big_file(cls, rel, fp)
                    continue
                try:
                    self._mirror_one(cls, fp, dst_root, rel, cursor, two_way, stats)
                except OSError as e:
                    self.state.data["stats"]["errors"] += 1
                    stats.setdefault("errors", 0)
                    stats["errors"] += 1
                    self.log.error(f"mirror fail {cls}/{rel}: {e}")

        # 删除清理: 仅清理我们 track 过的文件
        for rel in list(cursor.keys()):
            if rel not in seen:
                d = dst_root / rel
                if not d.exists():
                    cursor.pop(rel, None)
                    continue
                changed = tuple(cursor[rel].get("key", [])) != fast_key(d)
                if two_way and changed:
                    # hub 侧被改过 -> 冲突存档后删除 (以 AionUi 侧删除为准)
                    self._stash_loser(cls, rel, d)
                    self.state.data["stats"]["conflicts"] += 1
                    stats["conflicts"] += 1
                    self.log.conflict(class_name=cls, relpath=rel,
                                      reason="deleted-on-source-but-changed-on-dst",
                                      stashed=str(d))
                d.unlink(missing_ok=True)
                cursor.pop(rel, None)
                stats["removed"] += 1
        return stats

    def _note_big_file(self, cls, rel, fp):
        try:
            big = {}
            if self.state.big_files.exists():
                big = json.loads(self.state.big_files.read_text(encoding="utf-8"))
            big.setdefault(cls, {})[rel] = {
                "size": fp.stat().st_size, "seen": now_iso()}
            self.state.big_files.write_text(
                json.dumps(big, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    # ---- 数据类任务
    def task_conversations(self, src):
        stats = self.mirror_dir("conversations", src, self.hub / "conversations",
                                two_way=True)
        self.log.event(class_name="conversations", action="mirror",
                       copied=stats["copied"], pushed=stats.get("pushed", 0),
                       removed=stats["removed"], conflicts=stats["conflicts"],
                       skipped_big=stats["skipped_big"])
        return stats

    def task_memory(self, memories):
        stats = self.mirror_dir("memory", memories, self.hub / "memory",
                                two_way=False)  # Hermes 权威, 单向分发
        self.log.event(class_name="memory", action="distribute",
                       copied=stats["copied"], removed=stats["removed"])
        return stats

    def task_sessions(self, sessions):
        stats = self.mirror_dir("sessions", sessions, self.hub / "sessions",
                                two_way=False)  # DSH 权威, 只读镜像 (zstd blob)
        self.log.event(class_name="sessions", action="mirror",
                       copied=stats["copied"], removed=stats["removed"],
                       skipped_big=stats["skipped_big"])
        return stats

    def task_config(self, src):
        """DSH 配置权威 -> hub/config; Hermes/AionUi 配置只读镜像。"""
        stats = {"copied": 0, "pushed": 0, "removed": 0, "conflicts": 0,
                 "skipped_big": 0}
        pairs = [
            ("dsh_settings", Path(src["dsh"]["settings"]),
             self.hub / "config" / "dsh" / "settings.yaml"),
            ("dsh_workspace", Path(src["dsh"]["workspace_json"]),
             self.hub / "config" / "dsh" / "workspace.json"),
            ("hermes_config", Path(src["hermes"]["config"]),
             self.hub / "config" / "hermes" / "config.yaml"),
        ]
        for name, sp, dp in pairs:
            if not sp.exists():
                continue
            try:
                if not dp.exists() or fast_key(sp) != fast_key(dp):
                    self._copy(sp, dp)
                    stats["copied"] += 1
            except OSError as e:
                self.state.data["stats"]["errors"] += 1
                self.log.error(f"config sync fail {name}: {e}")
        # AionUi meta_prompts 目录镜像
        mp_src = Path(src["aionui"]["meta_prompts"])
        if mp_src.is_dir():
            m = self.mirror_dir("config", mp_src,
                                self.hub / "config" / "aionui" / "meta_prompts",
                                two_way=False)
            stats["copied"] += m["copied"]
        self.log.event(class_name="config", action="distribute", **stats)
        return stats

    def task_registry(self, src):
        """AionUi 对话投影注册表 (DSH storages/aionui-sync) <-> hub/registry"""
        stats = self.mirror_dir("registry", Path(src["dsh"]["registry"]),
                                self.hub / "registry", two_way=True)
        self.log.event(class_name="registry", action="mirror",
                       copied=stats["copied"], pushed=stats.get("pushed", 0),
                       removed=stats["removed"])
        return stats

    def task_workspace(self, ws_path):
        """工作区镜像: AionUi 会话目录 (=DSH 共享 cwd) -> hub/workspace (单向备份镜像)"""
        stats = self.mirror_dir("workspace", Path(ws_path),
                                self.hub / "workspace", two_way=False)
        self.log.event(class_name="workspace", action="mirror",
                       copied=stats["copied"], removed=stats["removed"],
                       skipped_big=stats["skipped_big"])
        return stats

    def task_db_backup(self, aionui_db: Path):
        """aionui-backend.db 增量快照 (sqlite3 backup API, 锁安全)。"""
        if not aionui_db.exists():
            return None
        now = time.time()
        if now - self.last_db_backup < float(self.cfg["backup"]["db_interval"]):
            return None
        snapshots = sorted(self.backup_root.parent.glob("aionui-backend.db.*.bak"))
        if snapshots and aionui_db.stat().st_mtime <= snapshots[-1].stat().st_mtime:
            self.last_db_backup = now  # 无变化, 不重复快照
            return None
        self.last_db_backup = now
        dest = self.backup_root.parent / f"aionui-backend.db.{ts_stamp()}.bak"
        try:
            src = sqlite3.connect(str(aionui_db), timeout=10)
            dst = sqlite3.connect(str(dest))
            with dst:
                src.backup(dst)
            dst.close()
            src.close()
            self.log.event(class_name="db_backup", action="snapshot",
                           size=dest.stat().st_size)
        except Exception as e:
            self.state.data["stats"]["errors"] += 1
            self.log.error(f"db backup fail: {e}")
            try:
                dest.unlink(missing_ok=True)
            except OSError:
                pass
        keep = int(self.cfg["backup"].get("keep", 24))
        snaps = sorted(self.backup_root.parent.glob("aionui-backend.db.*.bak"))
        for old in snaps[:-keep] if keep > 0 else []:
            try:
                old.unlink()
                self.log.info(f"prune backup {old.name}")
            except OSError:
                pass
        return dest

    # ---- 心跳与队列
    def heartbeat(self, src):
        hb = {}
        for name, s in src.items():
            root = Path(s["root"])
            alive = root.exists()
            hb[name] = {
                "label": s["label"], "role": s["role"], "alive": alive,
                "seen": now_iso() if alive else None, "root": str(root),
            }
        try:
            self.state.heartbeat.write_text(
                json.dumps(hb, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as e:
            self.log.error(f"heartbeat write fail: {e}")
        return hb

    def replay_queue(self, src):
        """重放离线期间积压的操作。"""
        qdir = Path(self.cfg["hub"]["queues"]) / "pending"
        done = Path(self.cfg["hub"]["queues"]) / "done"
        done.mkdir(parents=True, exist_ok=True)
        if not qdir.exists():
            return 0
        n = 0
        for qf in sorted(qdir.glob("*.json")):
            try:
                op = json.loads(qf.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            dst = Path(op.get("dst", ""))
            srcp = Path(op.get("src", ""))
            ok = False
            if op.get("op") == "copy" and dst.exists() and srcp.exists():
                try:
                    self._copy(srcp, dst)
                    ok = True
                except OSError:
                    ok = False
            if ok:
                qf.rename(done / qf.name)
                n += 1
                self.log.event(class_name="queue", action="replayed", op=qf.name)
            else:
                self.log.event(class_name="queue", action="stalled", op=qf.name)
        return n

    def enqueue(self, op):
        qdir = Path(self.cfg["hub"]["queues"]) / "pending"
        qdir.mkdir(parents=True, exist_ok=True)
        qf = qdir / f"{ts_stamp()}-{op.get('class','op')}-{abs(hash(op.get('dst','')))}.json"
        try:
            qf.write_text(json.dumps(op, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    # ---- MCP 统一注册表
    def task_mcp(self, src):
        """聚合三方 MCP 配置 -> hub/config/mcp_registry.json (只读聚合, 不改任何活配置)。"""
        reg = {"generated": now_iso(), "sources": {}, "servers": {}}
        # AionUi 平台级注册表
        sj = Path(src["aionui"]["mcp_servers_json"])
        if sj.exists():
            try:
                data = json.loads(sj.read_text(encoding="utf-8"))
                reg["sources"]["aionui_platform"] = {
                    "path": str(sj), "version": data.get("version"),
                    "last_updated": data.get("last_updated")}
                for k, v in (data.get("servers") or {}).items():
                    cap = v.get("capabilities") or {}
                    reg["servers"]["aionui:" + k] = {
                        "name": v.get("name"), "status": v.get("status"),
                        "category": v.get("category"),
                        "tools": len(cap.get("tools", [])),
                        "transport": (v.get("transport") or {}).get("type", "?")}
            except Exception as e:
                self.log.error(f"mcp registry aionui parse fail: {e}")
        # AionUi 工具级 (matlab 等)
        ty = Path(src["aionui"]["tools_mcp_yaml"])
        if ty.exists() and yaml:
            try:
                data = yaml.safe_load(ty.read_text(encoding="utf-8"))
                for k, v in ((data or {}).get("mcpServers") or {}).items():
                    reg["servers"]["aionui-tools:" + k] = {
                        "name": k, "status": "disabled" if v.get("disabled") else "active",
                        "transport": "stdio"}
            except Exception as e:
                self.log.error(f"mcp registry tools parse fail: {e}")
        # Hermes config.yaml mcp 段 (键为 mcp_servers)
        hc = Path(src["hermes"]["config"])
        if hc.exists() and yaml:
            try:
                data = yaml.safe_load(hc.read_text(encoding="utf-8")) or {}
                mcp = data.get("mcp") or data.get("mcp_servers") or {}
                servers = mcp.get("servers") if isinstance(mcp, dict) and isinstance(mcp.get("servers"), dict) else mcp
                if isinstance(servers, dict):
                    for k, v in servers.items():
                        if isinstance(v, dict) and not k.startswith("_"):
                            reg["servers"]["hermes:" + k] = {
                                "name": k, "status": "configured",
                                "command": v.get("command") or v.get("cmd") or "?"}
            except Exception as e:
                self.log.error(f"mcp registry hermes parse fail: {e}")
        # DSH profile 扫描
        prof = Path(src["dsh"]["profiles"])
        mentions = 0
        if prof.exists():
            for f in prof.glob("*/cordis*.yml"):
                try:
                    mentions += f.read_text(encoding="utf-8").lower().count("mcp")
                except OSError:
                    pass
        reg["sources"]["dsh"] = {
            "profiles": str(prof), "mcp_mentions": mentions,
            "note": "dsh-mcp-client 已安装但未挂载到 profile (TRIAD 报告)"}
        dest = self.hub / "config" / "mcp_registry.json"
        tmp = dest.with_suffix(".tmp")
        tmp.write_text(json.dumps(reg, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        os.replace(tmp, dest)
        self.log.event(class_name="mcp", action="registry",
                       servers=len(reg["servers"]))
        return {"copied": 1, "pushed": 0, "removed": 0, "conflicts": 0,
                "skipped_big": 0}

    # ---- 告警 (心跳状态跃迁 + 错误增长)
    def _check_alerts(self, hb):
        alerts = []
        prev = self.state.data.get("alerts_prev", {})
        for name, h in hb.items():
            was = prev.get(name)
            if was is not None and was != h["alive"]:
                alerts.append({"ts": now_iso(), "level": "WARN", "system": name,
                               "event": "offline" if not h["alive"] else "recovered",
                               "detail": f"{h['label']} "
                                         f"{'离线' if not h['alive'] else '恢复'}"})
        if hb and not all(h["alive"] for h in hb.values()):
            alerts.append({"ts": now_iso(), "level": "WARN", "system": "triad",
                           "event": "degraded", "detail": "存在离线系统"})
        errs = self.state.data["stats"]["errors"]
        if errs > 0 and errs > self.state.data.get("alerts_err_seen", 0):
            alerts.append({"ts": now_iso(), "level": "WARN", "system": "daemon",
                           "event": "errors_increased",
                           "detail": f"累计错误 {errs} (见 logs/sync.log)"})
            self.state.data["alerts_err_seen"] = errs
        if alerts:
            try:
                ap = Path(self.cfg["hub"]["state"]) / "alerts.jsonl"
                with open(ap, "a", encoding="utf-8") as f:
                    for a in alerts:
                        f.write(json.dumps(a, ensure_ascii=False) + "\n")
            except OSError as e:
                self.log.error(f"alerts write fail: {e}")
        self.state.data["alerts_prev"] = {k: v["alive"] for k, v in hb.items()}

    # ---- 主循环
    def run_once(self):
        t0 = time.time()
        src = self.cfg["sources"]
        self.state.data["stats"]["total_ticks"] += 1
        hb = self.heartbeat(src)
        agg = {"copied": 0, "pushed": 0}

        aionui_alive = hb["aionui"]["alive"]
        hermes_alive = hb["hermes"]["alive"]
        dsh_alive = hb["dsh"]["alive"]

        if hermes_alive:
            st = self.task_memory(Path(src["hermes"]["memories"]))
            agg["copied"] += st["copied"]
        else:
            self.log.error("Hermes 离线, 记忆分发跳过")
        if dsh_alive:
            st = self.task_sessions(Path(src["dsh"]["sessions"]))
            agg["copied"] += st["copied"]
            st = self.task_registry(src)
            agg["copied"] += st["copied"]
        else:
            self.log.error("DSH 离线, 会话/注册表镜像跳过")
        if aionui_alive:
            st = self.task_conversations(Path(src["aionui"]["conversations"]))
            agg["copied"] += st["copied"] + st.get("pushed", 0)
            st = self.task_workspace(self.sync["workspace"])
            agg["copied"] += st["copied"]
        else:
            self.log.error("AionUi 离线, 对话/工作区镜像跳过")
        # 配置分发 (任一系统离线也继续其它同步 — 红线3)
        try:
            st = self.task_config(src)
            agg["copied"] += st["copied"]
        except Exception as e:
            self.state.data["stats"]["errors"] += 1
            self.log.error(f"config task fail: {e}")
        try:
            st = self.task_mcp(src)
            agg["copied"] += st["copied"]
        except Exception as e:
            self.state.data["stats"]["errors"] += 1
            self.log.error(f"mcp task fail: {e}")

        self._check_alerts(hb)

        if self.cfg["backup"]["enabled"]:
            try:
                self.task_db_backup(Path(src["aionui"]["db"]))
            except Exception as e:
                self.state.data["stats"]["errors"] += 1
                self.log.error(f"backup task fail: {e}")

        self.state.data["stats"]["copied"] += agg["copied"]

        self.replay_queue(src)
        self.state.save()
        self.log.rotate()
        self.log.event(action="tick", duration_ms=int((time.time() - t0) * 1000),
                       heartbeat={k: v["alive"] for k, v in hb.items()})
        return self.state.data["stats"]

    def run_loop(self, interval=None):
        interval = interval or int(self.sync.get("interval", 30))
        self.log.info(f"TRI-SYNC-DAEMON v{VERSION} 启动, interval={interval}s, "
                      f"pid={os.getpid()}")
        while True:
            try:
                self.run_once()
            except Exception as e:
                self.state.data["stats"]["errors"] += 1
                self.log.error(f"tick 异常: {e}", exc_info=True)
            time.sleep(interval)


# ---------------------------------------------------------------- CLI
def main():
    faulthandler.enable()
    ap = argparse.ArgumentParser(description="TRI-SYNC-DAEMON v1.0")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    ap.add_argument("--once", action="store_true", help="单轮同步后退出")
    ap.add_argument("--daemon", action="store_true", help="常驻循环 (默认)")
    ap.add_argument("--interval", type=int, default=None)
    args = ap.parse_args()

    cfg = load_config(args.config)
    log = Logger(Path(cfg["hub"]["logs"]))
    # 原生崩溃 (AV/segfault) 时把 Python 栈转储到 fault.log
    try:
        faulthandler.enable(
            open(Path(cfg["hub"]["logs"]) / "fault.log", "a", encoding="utf-8"))
    except (OSError, ValueError):
        pass

    def _fatal_hook(et, ev, tb):
        try:
            import traceback
            fatal = Path(cfg["hub"]["logs"]) / "fatal.log"
            with open(fatal, "a", encoding="utf-8") as f:
                f.write(f"\n[{now_iso()}] FATAL {et.__name__}: {ev}\n")
                traceback.print_exception(et, ev, tb, file=f)
        except Exception:
            pass
        sys.__excepthook__(et, ev, tb)

    sys.excepthook = _fatal_hook

    state = SyncState(Path(cfg["hub"]["state"]))
    state.acquire_lock()

    eng = TriSyncEngine(cfg, log, state)
    try:
        if args.once:
            stats = eng.run_once()
            print(json.dumps(stats, ensure_ascii=False, indent=2))
        else:
            eng.run_loop(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        state.release_lock()


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
PERMANENT-ANCHOR v1.1 —— A.N.C.H.O.R. 六步锚定引擎（鲁棒化版）

对齐: meta_prompts/PERMANENT-ANCHOR_v1.0.md
锚点文件: governance/anchors/{ANCHORS,BOUNDARY,REDLINES}.md
机制: Assemble(仅首次签名) / Normalize+Observe(校验注入) / Checkpoint(定期)
      Halt(变更阻断) / Recover(恢复) / Update(显式重签名, 合法变更流程)

v1.1 鲁棒化修复 (2026-08-14):
  D1 防篡改真生效: 旧版每次运行无条件重新签名+覆盖 backup, 篡改会被"洗白"。
     现在 assemble() 仅在无 manifest 时首次签名; 重签名必须显式 --update "原因"。
  D5 信任根: anchor_state.json 记录 manifest_sha256, verify() 同时校验 manifest
     自身未被替换(跨会话一致性, A5)。
  D4 A2 启动强制: --startup 模式, verify FAIL → exit code 2 阻断会话启动。
  D3 解耦: render_report 不再硬编码层数/V42 板, 改为引用锚点文件本身。
  D2 cp950: stdout 强制 utf-8。
  backup 历史: 每次签名保留时间戳快照, update 后可回滚到旧版本。

CLI:
  python permanent_anchor.py                     # verify+checkpoint+report, FAIL→exit 2
  python permanent_anchor.py --update "原因"      # 显式重签名(合法变更流程)
  python permanent_anchor.py --startup            # A2: 启动强制验证, FAIL→exit 2
  python permanent_anchor.py --verify             # 仅校验
  python permanent_anchor.py --recover            # 显式从 backup/ 恢复(确认篡改后)
  python permanent_anchor.py --self-test          # 篡改检测端到端演练(改→FAIL→恢复→PASS)

设计原则:
  1. 只读真实锚点文件, SHA-256 检测篡改, 不臆造校验结果
  2. Halt: verify 失败即阻断, 记录 BLOCKED_ATTEMPT, 不静默放行
  3. Recover: 从 backup/ 恢复最新有效版本, 记录证据链
  4. 签名不可自动重做: 合法变更必须显式 --update, 否则视为篡改
"""
import os
import sys
import json
import hashlib
import shutil
import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")  # D2: Windows cp950 修复
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ANCHOR_DIR = os.path.normpath(os.path.join(HERE, "..", "anchors"))
BACKUP_DIR = os.path.join(ANCHOR_DIR, "backup")
MANIFEST = os.path.join(ANCHOR_DIR, "anchor_manifest.json")
STATE_FILE = os.path.join(ANCHOR_DIR, "anchor_state.json")
CHECKPOINT_LOG = os.path.join(ANCHOR_DIR, "checkpoint_log.jsonl")
RECOVERY_LOG = os.path.join(ANCHOR_DIR, "recovery_log.jsonl")
BLOCK_LOG = os.path.join(ANCHOR_DIR, "blocked_attempts.jsonl")
UPDATE_LOG = os.path.join(ANCHOR_DIR, "update_log.jsonl")

ANCHOR_FILES = ["ANCHORS.md", "BOUNDARY.md", "REDLINES.md"]


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _now():
    return datetime.datetime.now().isoformat()


def _load_manifest():
    """读取 manifest。损坏(解析失败)与缺失区分返回, 避免误报"未签名"。"""
    if not os.path.exists(MANIFEST):
        return {"_corrupt": False, "_missing": True}
    try:
        data = json.load(open(MANIFEST, encoding="utf-8"))
        return data if isinstance(data, dict) else {"_corrupt": True, "_missing": False}
    except Exception as e:
        return {"_corrupt": True, "_missing": False, "_error": str(e)}


def _save_manifest(manifest):
    # newline="\n" 强制 LF: Windows 文本模式会把 \n→\r\n, 致本地/仓库字节不一致
    json.dump(manifest, open(MANIFEST, "w", encoding="utf-8", newline="\n"),
              ensure_ascii=False, indent=2)


def _load_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        return json.load(open(STATE_FILE, encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state):
    json.dump(state, open(STATE_FILE, "w", encoding="utf-8", newline="\n"),
              ensure_ascii=False, indent=2)


def _append_log(path, entry):
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _manifest_sha256():
    """manifest 自身哈希, 作为信任根存于 state。"""
    if not os.path.exists(MANIFEST):
        return None
    return _sha256(MANIFEST)


def _backup_with_history(name):
    """将当前锚点文件保存为时间戳快照 + 最新 .bak。"""
    src = os.path.join(ANCHOR_DIR, name)
    if not os.path.exists(src):
        return
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(src, os.path.join(BACKUP_DIR, "%s.%s.bak" % (name, ts)))
    shutil.copy2(src, os.path.join(BACKUP_DIR, name + ".bak"))


# ── Phase A: Assemble (仅首次签名) ────────────────────────────────────────
def assemble(force=False):
    """首次组装签名。已有 manifest 时拒绝自动重签(D1 防篡改)。

    V1 漏洞修复: 若 backup/ 存在历史快照但 manifest 缺失, 判定为"删除绕过",
    拒绝自动重签 —— 必须 --recover(确认篡改) 或人工裁决。
    """
    os.makedirs(ANCHOR_DIR, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    has_history = any(f.endswith(".bak") for f in os.listdir(BACKUP_DIR)) if os.path.isdir(BACKUP_DIR) else False
    if os.path.exists(MANIFEST) and not force:
        return {"status": "EXISTS",
                "detail": "manifest 已存在, 拒绝自动重签; 合法变更请用 --update '原因'"}
    if not os.path.exists(MANIFEST) and has_history and not force:
        return {"status": "EXISTS",
                "detail": "manifest 缺失但 backup/ 有历史快照 —— 疑似删除绕过, 拒绝自动重签; 请 --recover 或人工确认"}
    manifest = {}
    for name in ANCHOR_FILES:
        p = os.path.join(ANCHOR_DIR, name)
        if not os.path.exists(p):
            return {"status": "FAIL", "missing": name}
        manifest[name] = {
            "sha256": _sha256(p),
            "size": os.path.getsize(p),
            "assembled_at": _now(),
        }
    _save_manifest(manifest)
    for name in ANCHOR_FILES:
        _backup_with_history(name)
    return {"status": "OK", "manifest": manifest}


# ── Phase N/O: Normalize + Observe (校验注入) ─────────────────────────────
def verify():
    """校验锚点 + manifest 自身完整性(信任根, D5)。"""
    manifest = _load_manifest()
    if manifest.get("_missing"):
        return {"status": "FAIL", "reason": "无 manifest, 需先 assemble", "files": {}, "mismatch": ["manifest(缺失)"]}
    if manifest.get("_corrupt"):
        return {"status": "FAIL", "reason": "manifest 损坏(JSON 解析失败): %s" % manifest.get("_error", "?"),
                "files": {}, "mismatch": ["manifest(损坏)"]}
    result = {"status": "PASS", "files": {}, "mismatch": []}
    # D5: manifest 自身哈希 vs state 信任根
    state = _load_state()
    trust_root = state.get("manifest_sha256")
    cur_mh = _manifest_sha256()
    if trust_root and cur_mh and cur_mh != trust_root:
        result["status"] = "FAIL"
        result["mismatch"].append("anchor_manifest.json (manifest 自身被替换)")
        result["manifest_trust"] = False
    else:
        result["manifest_trust"] = True
    for name in ANCHOR_FILES:
        p = os.path.join(ANCHOR_DIR, name)
        if not os.path.exists(p):
            result["status"] = "FAIL"
            result["mismatch"].append(name + " (缺失)")
            result["files"][name] = {"hash": None, "match": False}
            continue
        cur = _sha256(p)
        exp = manifest.get(name, {}).get("sha256")
        ok = (cur == exp)
        result["files"][name] = {"hash": cur[:16] + "...", "match": ok}
        if not ok:
            result["status"] = "FAIL"
            result["mismatch"].append(name)
    return result


# ── Phase C: Checkpoint ───────────────────────────────────────────────────
def checkpoint():
    v = verify()
    entry = {"ts": _now(), "verify": v["status"], "mismatch": v["mismatch"]}
    _append_log(CHECKPOINT_LOG, entry)
    return entry


# ── Phase H: Halt (变更阻断, verify 失败时调用) ────────────────────────────
def halt(verify_result):
    if verify_result["status"] == "PASS":
        return {"status": "NO_HALT", "detail": "锚点完整, 无需阻断"}
    entry = {
        "ts": _now(),
        "action": "BLOCKED_ATTEMPT",
        "mismatch": verify_result["mismatch"],
    }
    _append_log(BLOCK_LOG, entry)
    return {"status": "BLOCKED", "detail": "锚点签名不匹配, 已阻断并记录",
            "mismatch": verify_result["mismatch"]}


# ── Phase R: Recover ──────────────────────────────────────────────────────
def recover():
    manifest = _load_manifest()
    recovered = []
    for name in ANCHOR_FILES:
        p = os.path.join(ANCHOR_DIR, name)
        bak = os.path.join(BACKUP_DIR, name + ".bak")
        if not os.path.exists(bak):
            continue
        if os.path.exists(p) and _sha256(p) == manifest.get(name, {}).get("sha256"):
            continue  # 当前文件完整, 无需恢复
        shutil.copy2(bak, p)
        recovered.append(name)
    entry = {"ts": _now(), "recovered": recovered, "status": "OK" if recovered else "NOOP"}
    _append_log(RECOVERY_LOG, entry)
    return entry


# ── Phase U: Update (显式重签名, 合法变更流程 A4) ─────────────────────────
def update(reason):
    """合法变更流程: 备份历史 → 重签 → 刷新信任根 → 审计日志。

    --update 是唯一允许改变锚点签名的路径; 默认 run() 永远不重签。
    """
    if not reason or not reason.strip():
        return {"status": "FAIL", "detail": "--update 必须提供原因, 禁止无理由重签名"}
    missing = [n for n in ANCHOR_FILES
               if not os.path.exists(os.path.join(ANCHOR_DIR, n))]
    if missing:
        return {"status": "FAIL", "missing": missing}
    asm = assemble(force=True)
    if asm["status"] != "OK":
        return asm
    # 刷新信任根
    state = _load_state()
    state["manifest_sha256"] = _manifest_sha256()
    state["last_update_at"] = _now()
    state["last_update_reason"] = reason.strip()
    _save_state(state)
    entry = {"ts": _now(), "reason": reason.strip(),
             "files": {n: asm["manifest"][n]["sha256"][:16] + "..." for n in ANCHOR_FILES}}
    _append_log(UPDATE_LOG, entry)
    return {"status": "OK", "detail": "已显式重签名", "reason": reason.strip(),
            "manifest": asm["manifest"]}


# ── 报告渲染 (D3: 不硬编码内容, 引用锚点文件) ─────────────────────────────
def render_report(round_n, asm, ver, cp, hal, rec):
    L = []
    L.append("### ⚓ 锚定报告 [#ANCHOR-ROUND_%d]" % round_n)
    L.append("")
    L.append("[Phase A: Assemble]")
    if asm["status"] == "OK":
        for name in ANCHOR_FILES:
            h = asm["manifest"][name]["sha256"][:16]
            L.append("- %s : sha256=%s..." % (name, h))
    elif asm["status"] == "EXISTS":
        L.append("- 已签名, 未重签 (防篡改: 合法变更须 --update)")
    else:
        L.append("- 失败: 缺失 %s" % asm.get("missing", "?"))
    L.append("")
    L.append("[Phase N/O: Normalize+Observe]")
    L.append("- 校验状态: %s" % ver["status"])
    L.append("- manifest 信任根: %s" % ("MATCH" if ver.get("manifest_trust") else "MISMATCH/未建立"))
    for name in ANCHOR_FILES:
        f = ver["files"].get(name, {})
        L.append("  - %s : %s" % (name, "MATCH" if f.get("match") else "MISMATCH/缺失"))
    L.append("")
    L.append("[Phase C: Checkpoint]")
    L.append("- 校验结果: %s" % cp["verify"])
    L.append("")
    L.append("[Phase H: Halt]")
    L.append("- 阻断状态: %s" % hal["status"])
    if hal["status"] == "BLOCKED":
        L.append("  - %s" % hal["detail"])
    L.append("")
    L.append("[Phase R: Recover]")
    if rec.get("note"):
        L.append("- %s" % rec["note"])
    else:
        L.append("- 恢复: %s" % (rec["recovered"] if rec["recovered"] else "无需恢复"))
    L.append("")
    L.append("[Honest Boundary (内容以锚点文件为准, 引擎不臆造)]")
    L.append("- 锚点全文: governance/anchors/ANCHORS.md (治理栈/优先级契约/CVE-S/双环)")
    L.append("- 边界声明: governance/anchors/BOUNDARY.md")
    L.append("- 强制红线: governance/anchors/REDLINES.md")
    L.append("- 局限: 本引擎做文件级完整性校验; 启动强制加载须经 --startup (exit 2 阻断)")
    return "\n".join(L) + "\n"


# ── 主流程 ────────────────────────────────────────────────────────────────
def run():
    """默认流程: verify + checkpoint + halt + report。

    注意: verify FAIL 时【不】自动 recover —— 篡改与合法编辑无法自动区分,
    自动恢复会静默回滚合法编辑(旧版 bug)。阻断后由人裁决:
      - 合法变更 → --update "原因"
      - 确认篡改 → --recover
    """
    state_path = STATE_FILE
    round_n = _load_state().get("round", 0) + 1

    asm = assemble()  # 已有 manifest 时返回 EXISTS, 不重签
    ver = verify()
    cp = checkpoint()
    hal = halt(ver)
    rec = {"recovered": [], "note": "不自动恢复, 由人裁决(--update/--recover)"}

    report = render_report(round_n, asm, ver, cp, hal, rec)
    report_path = os.path.join(ANCHOR_DIR, "anchor_report.md")
    open(report_path, "w", encoding="utf-8", newline="\n").write(report)

    state = _load_state()
    state["round"] = round_n
    state["ts"] = _now()
    if not state.get("manifest_sha256"):
        state["manifest_sha256"] = _manifest_sha256()
    _save_state(state)

    print(report)
    print("[OK] 锚点报告: %s" % report_path)
    return 0 if ver["status"] == "PASS" else 2


def startup_check():
    """A2: 启动强制验证。FAIL → exit 2 阻断会话启动; PASS → 记录启动时间。"""
    ver = verify()
    hal = halt(ver)
    state = _load_state()
    state["last_startup_check_at"] = _now()
    state["last_startup_check_verify"] = ver["status"]
    _save_state(state)
    if ver["status"] == "PASS":
        print("[ANCHOR-STARTUP] PASS 锚点完整, 允许启动 (ts=%s)" % state["last_startup_check_at"])
        return 0
    print("[ANCHOR-STARTUP] BLOCKED: %s" % hal["detail"])
    print("[ANCHOR-STARTUP] 违反红线#7/#8: 锚点未验证, 禁止启动会话")
    return 2


def self_test():
    """端到端篡改检测演练: 篡改 → FAIL → 恢复 → PASS。

    注意: 自检【不】写任何审计日志(checkpoint/recovery/blocked),
    避免自检事件污染真实事件链(诚实性: 测试≠真实事件)。
    """
    print("== PERMANENT-ANCHOR 自检 (篡改检测演练) ==")
    v0 = verify()
    if v0["status"] != "PASS":
        print("FAIL: 自检前锚点应完整, 实际 %s" % v0["status"])
        return 1
    target = os.path.join(ANCHOR_DIR, "ANCHORS.md")
    # 二进制读取, 写回也走二进制, 避免 Windows 文本模式 \n→\r\n 污染(D3 鲁棒化)
    with open(target, "rb") as f:
        orig_bytes = f.read()
    with open(target, "ab") as f:
        f.write(b"\n<!-- tamper-test -->\n")
    v1 = verify()  # verify 本身不写日志
    tamper_detected = (v1["status"] == "FAIL" and "ANCHORS.md" in v1["mismatch"])
    print("篡改后 verify: %s (期望 FAIL, 检测到=%s)" % (v1["status"], tamper_detected))
    if not tamper_detected:
        with open(target, "wb") as f:
            f.write(orig_bytes)
        print("FAIL: 篡改未被检测到!")
        return 1
    # 恢复走字节级还原, 不调用 recover()(避免写 recovery_log)
    with open(target, "wb") as f:
        f.write(orig_bytes)
    v2 = verify()
    print("恢复后 verify: %s (期望 PASS)" % v2["status"])
    print("self-test: %s" % ("PASS" if v2["status"] == "PASS" else "FAIL"))
    return 0 if v2["status"] == "PASS" else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--update":
        reason = " ".join(args[1:])
        r = update(reason)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        sys.exit(0 if r["status"] == "OK" else 2)
    elif args and args[0] == "--startup":
        sys.exit(startup_check())
    elif args and args[0] == "--verify":
        r = verify()
        print(json.dumps({"status": r["status"], "mismatch": r["mismatch"],
                          "files": r["files"]}, ensure_ascii=False, indent=2))
        sys.exit(0 if r["status"] == "PASS" else 2)
    elif args and args[0] == "--recover":
        r = recover()
        print(json.dumps(r, ensure_ascii=False, indent=2))
        sys.exit(0 if r["recovered"] else 0)  # 无论是否恢复都返回 0, 由 verify 兜底
    elif args and args[0] == "--self-test":
        sys.exit(self_test())
    elif args and args[0] in ("-h", "--help"):
        print(__doc__)
    else:
        sys.exit(run())

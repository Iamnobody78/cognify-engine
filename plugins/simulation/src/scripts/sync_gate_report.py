"""sync_gate_report.py — 统一 V9 gate 报告双副本。

Canonical 源: 工作区根 .aionui/meta_governance/ (v9_gate_evaluator.py 写入处)
镜像目标: bottlesumo_pi/.aionui/meta_governance/ (项目本地副本)

用法: 每次运行 v9_gate_evaluator.py 后执行本脚本 (或由 CI 串联)。
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent            # bottlesumo_pi/scripts
PROJECT = HERE.parent                             # bottlesumo_pi
ROOT_AIONUI = PROJECT.parent / ".aionui"          # workspace root .aionui (canonical)
LOCAL_AIONUI = PROJECT / ".aionui"                # project-local mirror

SUBDIRS = ["meta_governance/gate", "meta_governance/plateau", "meta_governance/evolution"]


def sync() -> int:
    n = 0
    for sub in SUBDIRS:
        src = ROOT_AIONUI / sub
        dst = LOCAL_AIONUI / sub
        if not src.exists():
            print(f"[skip] {sub}: no canonical source")
            continue
        dst.mkdir(parents=True, exist_ok=True)
        for f in sorted(src.glob("*.json")):
            data = json.loads(f.read_text(encoding="utf-8"))
            out = dst / f.name
            out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"[sync] {sub}/{f.name}")
            n += 1
    return n


if __name__ == "__main__":
    total = sync()
    print(f"DONE ({total} files synced to bottlesumo_pi/.aionui)")

"""sensor — P12 感知层: 扫描工作区信号。

复用 L3/L5 既有事实源，输出统一信号字典:
  - git_status: 未提交/未推送变更（subprocess git）
  - codegen_drift: src/codegen/_generated_matches.py vs config/policies.yaml
    （复刻 policy_sync GATE 7 的判定，但只读不写）
  - tests: 最近一次全量回归结果（可选执行）
  - critic_report: .aionui/critic_report.md 中的未关闭建议
  - debt_registry: debt_registry.md 中的活跃债务（非 ✅/已关闭）

纯感知，无副作用（不修改任何文件）。
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# 默认路径（与仓库根目录对齐; 与 generator CLI 默认一致）
CODEGEN_POLICY_REL = "config/policies.yaml"
CODEGEN_OUT_REL = "src/codegen/_generated_matches.py"
DEFAULT_CRITIC_REPORT = ".aionui/critic_report.md"
DEFAULT_DEBT_REGISTRY = "debt_registry.md"


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """subprocess 运行 git（只读命令）。"""
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
    )


def git_status(repo_root: str | Path) -> dict:
    """返回 {dirty: bool, changed: [str], staged: [str], unpushed: int}。"""
    root = Path(repo_root)
    status = _run_git(["status", "--porcelain"], root)
    lines = [ln for ln in (status.stdout or "").splitlines() if ln.strip()]
    changed = []
    staged = []
    for ln in lines:
        if not ln.strip():
            continue
        code, path = ln[:2], ln[3:].strip()
        if path.startswith('"') and path.endswith('"'):
            try:
                path = path.encode().decode("unicode_escape")
            except (UnicodeDecodeError, UnicodeEncodeError):
                # quoted git path failed to unescape — keep raw (AUDIT-0047)
                pass
        if "M" in code or "?" in code:
            changed.append(path)
        if code.startswith("A") or code.startswith("M") or code.startswith("R"):
            staged.append(path)
    # 未推送提交数（仅在有 upstream 时可用）
    ahead = _run_git(["rev-list", "--count", "@{upstream}..HEAD"], root)
    unpushed = 0
    if ahead.returncode == 0 and ahead.stdout.strip().isdigit():
        unpushed = int(ahead.stdout.strip())
    return {
        "dirty": bool(changed) or bool(staged),
        "changed": sorted(set(changed)),
        "staged": sorted(set(staged)),
        "unpushed": unpushed,
    }


def codegen_drift(repo_root: str | Path) -> dict:
    """检测 codegen 产物漂移: 复刻 GATE 7 判定（只读）。

    返回 {"drift": bool, "generated": str|None, "policy": str|None,
          "reason": str}
    """
    root = Path(repo_root)
    gen = root / CODEGEN_OUT_REL
    pol = root / CODEGEN_POLICY_REL
    if not gen.exists():
        return {"drift": True, "generated": str(gen), "policy": str(pol),
                "reason": "生成物缺失"}
    if not pol.exists():
        return {"drift": False, "generated": str(gen), "policy": str(pol),
                "reason": "策略源缺失（跳过漂移判定）"}
    # 只读判定: 生成到临时文件，与已提交产物逐字节比较（不污染工作区）
    import tempfile

    from src.codegen.generator import generate

    committed = gen.read_bytes() if gen.exists() else b""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_out = Path(tmp) / "_generated_matches.py"
        generate(pol, tmp_out)
        regenerated = tmp_out.read_bytes()
    # 字节比较前统一换行符: 历史提交产物可能含 CRLF (Windows 时代生成),
    # 生成器现已固定输出 LF —— 漂移判定只应反映内容差异, 而非换行符载体差异
    def _normalize(b: bytes) -> bytes:
        return b.replace(b"\r\n", b"\n")

    drift = _normalize(regenerated) != _normalize(committed)
    return {
        "drift": drift,
        "generated": str(gen),
        "policy": str(pol),
        "reason": "漂移（临时产物与提交产物字节不一致）" if drift else "一致",
    }


def scan_tests(repo_root: str | Path, run: bool = False,
               tests_dir: str = "tests") -> dict:
    """测试状态: 默认只读扫描已有 pytest 缓存; run=True 时执行全量回归。"""
    root = Path(repo_root)
    if not run:
        cache = root / ".pytest_cache" / "v" / "cache" / "lastfailed"
        last_failed = []
        if cache.exists():
            text = cache.read_text(encoding="utf-8", errors="replace")
            last_failed = [ln.strip().strip('"') for ln in text.splitlines()
                           if ln.strip() and not ln.strip().startswith("{")]
        return {"executed": False, "last_failed": last_failed,
                "had_failures": bool(last_failed), "summary": "读缓存"}
    from src.meta_harness.sandbox import run_pytest_regression

    result = run_pytest_regression(tests_dir)
    return {"executed": True, "last_failed": [], "had_failures": not result["tests_passed"],
            "summary": result["summary"]}


def _parse_markdown_items(path: Path) -> list[dict]:
    """粗粒度解析 markdown 中的条目行（- [ ] / - [x] / 数字编号）。"""
    if not path.exists():
        return []
    items = []
    for i, ln in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        s = ln.strip()
        if not s:
            continue
        m = re.match(r"^- \[( |x)\] (.+)$", s)
        if m:
            items.append({"line": i, "done": m.group(1) == "x", "text": m.group(2)})
        elif re.match(r"^[-*] ", s):
            items.append({"line": i, "done": False, "text": s[2:]})
    return items


def critic_report(repo_root: str | Path) -> dict:
    """扫描 critic 报告中的未关闭建议（只读）。"""
    root = Path(repo_root)
    report = root / DEFAULT_CRITIC_REPORT
    items = _parse_markdown_items(report)
    open_items = [it for it in items if not it["done"]]
    return {"report": str(report), "exists": report.exists(),
            "open_items": open_items, "open_count": len(open_items)}


def debt_registry(repo_root: str | Path) -> dict:
    """扫描债务登记表中的活跃债务（未标记 ✅ / REJECTED / CLOSED）。"""
    root = Path(repo_root)
    reg = root / DEFAULT_DEBT_REGISTRY
    if not reg.exists():
        return {"registry": str(reg), "exists": False, "active": [], "active_count": 0}
    active = []
    for i, ln in enumerate(reg.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        if "✅" in s or "REJECTED" in s or "CLOSED" in s:
            continue
        m = re.match(r"^[-*] DEBT-\d+", s)
        if m:
            active.append({"line": i, "text": s})
    return {"registry": str(reg), "exists": True, "active": active,
            "active_count": len(active)}


def collect_signals(repo_root: str | Path, run_tests: bool = False,
                    tests_dir: str = "tests") -> dict:
    """聚合全部感知信号（P12 感知阶段的唯一入口）。"""
    return {
        "repo_root": str(Path(repo_root).resolve()),
        "git": git_status(repo_root),
        "codegen": codegen_drift(repo_root),
        "tests": scan_tests(repo_root, run=run_tests, tests_dir=tests_dir),
        "critic": critic_report(repo_root),
        "debt": debt_registry(repo_root),
    }

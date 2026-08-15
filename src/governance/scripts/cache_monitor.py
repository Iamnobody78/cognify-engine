#!/usr/bin/env python3
"""DeepSeek API 缓存命中率监控 — cache_monitor.py (零依赖).

三个子命令:

record  追加一条缓存用量记录 (JSONL): --hit/--miss 或 --response <api响应.json>
report  聚合 JSONL → 总/分 tag 命中率 + 阈值告警; 退出码: 0 健康 / 1 警告 / 2 紧急
diff    对比两个请求 JSON 的 messages 前缀, 定位缓存断裂点 (排查动态内容污染)

阈值 (对齐 .aionui/protocols/cache_optimization.md):
    ≥95% 健康; 80-95% 警告; <80% 紧急

用法:
  python scripts/cache_monitor.py record --hit 4500 --miss 500 --tag chat
  python scripts/cache_monitor.py record --response resp.json
  python scripts/cache_monitor.py report [--window 24] [--threshold 0.95]
  python scripts/cache_monitor.py diff --base req1.json --next req2.json
"""

import argparse
import datetime
import json
import pathlib
import sys

DEFAULT_LOG = "cache_monitor.jsonl"  # CWD 相对, --log 覆盖
HEALTH = 0.95
WARN = 0.80


def _reconfigure():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _load_usage(response_path: pathlib.Path) -> tuple:
    """从 OpenAI 兼容响应 JSON 提取 (hit, miss)。utf-8-sig 兼容 Windows BOM。"""
    data = json.loads(response_path.read_text(encoding="utf-8-sig"))
    usage = data.get("usage", {}) if isinstance(data, dict) else {}
    hit = usage.get("prompt_cache_hit_tokens", 0) or 0
    miss = usage.get("prompt_cache_miss_tokens", 0) or 0
    return int(hit), int(miss)


def record(log_path: pathlib.Path, hit: int, miss: int, tag: str = "") -> int:
    """追加一条记录, 返回退出码。"""
    if hit < 0 or miss < 0:
        print("ERROR: hit/miss 不能为负", file=sys.stderr)
        return 2
    rec = {
        "ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hit": hit,
        "miss": miss,
        "tag": tag,
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"✅ 已记录: hit={hit} miss={miss} tag={tag or '-'} → {log_path.name}")
    return 0


def _load_records(log_path: pathlib.Path) -> list:
    if not log_path.exists():
        return []
    recs = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            recs.append(rec)
        except json.JSONDecodeError:
            continue  # 跳过损坏行, 不阻断聚合
    return recs


def _rate(recs: list) -> float | None:
    hit = sum(r.get("hit", 0) for r in recs)
    miss = sum(r.get("miss", 0) for r in recs)
    return hit / (hit + miss) if (hit + miss) else None


def report(log_path: pathlib.Path, window_hours: float, threshold: float) -> int:
    """聚合 + 告警, 返回退出码 0/1/2。"""
    recs = _load_records(log_path)
    if window_hours:
        # UTC ISO 时间戳可直接字典序比较 (同格式固定宽度)
        cutoff = (datetime.datetime.now(datetime.timezone.utc)
                  - datetime.timedelta(hours=window_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        recs = [r for r in recs if r.get("ts", "") >= cutoff]
    if not recs:
        print("⚠️  无记录 (cache_monitor.jsonl 为空) — 先用 record 落盘")
        return 1
    overall = _rate(recs)
    print(f"📊 缓存命中率报告 ({len(recs)} 条记录"
          + (f", 窗口 {window_hours}h" if window_hours else "") + ")")
    print(f"    总命中率: {overall*100:.1f}%  (阈值 ≥{threshold*100:.0f}%)")
    tags = {}
    for r in recs:
        tags.setdefault(r.get("tag") or "-", []).append(r)
    for tag in sorted(tags):
        tr = _rate(tags[tag])
        if tr is not None:
            print(f"    [{tag}] {tr*100:.1f}%")
    if overall is None:
        return 1
    if overall >= threshold:
        print("✅ 健康")
        return 0
    if overall >= WARN:
        print("⚠️  警告: 命中率低于阈值 — 检查 system prompt/工具序/时间戳动态内容")
        return 1
    print("🔴 紧急: 命中率 < 80% — 冻结 system prompt 与工具定义, 立即排查前缀变更")
    return 2


def _norm_msg(m: dict) -> str:
    """消息规范化: 提取 role+content 的稳定表示 (忽略工具调用细节差异)。"""
    role = m.get("role", "?")
    content = m.get("content", "")
    if isinstance(content, list):  # 多模态数组 → 只取 text 段, 截断
        text = " ".join(c.get("text", "") for c in content
                        if isinstance(c, dict) and c.get("type") == "text")
        content = text[:200]
    return f"{role}:{content}"


def diff(base_path: pathlib.Path, next_path: pathlib.Path, show: int = 3) -> int:
    """找两个请求 messages 的最长公共前缀, 输出首个断裂点 (缓存失效位置)。"""
    try:
        b = json.loads(base_path.read_text(encoding="utf-8-sig"))
        n = json.loads(next_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: 读取请求 JSON 失败: {e}", file=sys.stderr)
        return 2
    b_msgs = b.get("messages", []) if isinstance(b, dict) else []
    n_msgs = n.get("messages", []) if isinstance(n, dict) else []
    common = 0
    for bm, nm in zip(b_msgs, n_msgs):
        if _norm_msg(bm) != _norm_msg(nm):
            break
        common += 1
    total = min(len(b_msgs), len(n_msgs))
    if common == total and len(b_msgs) == len(n_msgs):
        print(f"✅ 两请求 messages 前缀完全一致 ({common} 条) — 应命中缓存")
        return 0
    if common == 0:
        print("🔴 无公共前缀 — 整个缓存前缀失效 (system prompt 或首条消息已变化)")
    else:
        print(f"⚠️  公共前缀 {common}/{total} 条, 断裂于第 {common+1} 条:")
    for i in range(common, min(common + show, total)):
        bm, nm = b_msgs[i], n_msgs[i]
        if _norm_msg(bm) == _norm_msg(nm):
            print(f"  [{i}] 相同: {_norm_msg(nm)[:80]}")
        else:
            print(f"  [{i}] base: {_norm_msg(bm)[:80]}")
            print(f"  [{i}] next: {_norm_msg(nm)[:80]}  ← 差异点")
    return 1 if common < total else 0


def main(argv=None) -> int:
    _reconfigure()
    # --log 主/子解析器双挂: 主解析器给默认值; 子解析器 SUPPRESS 防覆盖
    # (经验教训: 只挂主解析器 → 子命令后的 --log 不被识别; 只挂子解析器 → 前置顺序失败)
    main_common = argparse.ArgumentParser(add_help=False)
    main_common.add_argument("--log", default=DEFAULT_LOG, help="JSONL 记录文件 (默认 cache_monitor.jsonl)")
    sub_common = argparse.ArgumentParser(add_help=False)
    sub_common.add_argument("--log", default=argparse.SUPPRESS, help=argparse.SUPPRESS)

    ap = argparse.ArgumentParser(description="DeepSeek 缓存命中率监控", parents=[main_common])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_rec = sub.add_parser("record", parents=[sub_common], help="追加一条缓存用量记录")
    p_rec.add_argument("--hit", type=int, default=0, help="prompt_cache_hit_tokens")
    p_rec.add_argument("--miss", type=int, default=0, help="prompt_cache_miss_tokens")
    p_rec.add_argument("--response", default=None, help="API 响应 JSON 文件 (自动提取 hit/miss)")
    p_rec.add_argument("--tag", default="", help="场景标签 (如 chat/judge/batch)")

    p_rep = sub.add_parser("report", parents=[sub_common], help="聚合命中率 + 阈值告警")
    p_rep.add_argument("--window", type=float, default=0, help="只看最近 N 小时 (0=全部)")
    p_rep.add_argument("--threshold", type=float, default=HEALTH, help="健康阈值 (默认 0.95)")

    p_diff = sub.add_parser("diff", parents=[sub_common], help="对比两个请求的前缀断裂点")
    p_diff.add_argument("--base", required=True, help="基准请求 JSON")
    p_diff.add_argument("--next", required=True, help="后续请求 JSON")
    p_diff.add_argument("--show", type=int, default=3, help="断裂点后显示条数 (默认 3)")
    args = ap.parse_args(argv)

    log_path = pathlib.Path(args.log)
    if args.cmd == "record":
        if args.response:
            try:
                hit, miss = _load_usage(pathlib.Path(args.response))
            except (OSError, json.JSONDecodeError) as e:
                print(f"ERROR: 解析响应失败: {e}", file=sys.stderr)
                return 2
        else:
            hit, miss = args.hit, args.miss
        if hit == 0 and miss == 0:
            print("ERROR: 需 --hit/--miss 或 --response 提供非零用量", file=sys.stderr)
            return 2
        return record(log_path, hit, miss, args.tag)
    if args.cmd == "report":
        return report(log_path, args.window, args.threshold)
    return diff(pathlib.Path(args.base), pathlib.Path(args.next), args.show)


if __name__ == "__main__":
    sys.exit(main())

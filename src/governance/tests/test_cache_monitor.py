"""DeepSeek 缓存监控 cache_monitor.py 单元测试 (tmp_path 假日志, 不触碰真实文件)."""

import datetime
import json
import os
import pathlib
import subprocess
import sys

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT))
import cache_monitor as cm


def _rec_line(hit: int, miss: int, tag: str = "", ts: str | None = None) -> str:
    rec = {"ts": ts or "2026-08-04T10:00:00Z", "hit": hit, "miss": miss, "tag": tag}
    return json.dumps(rec, ensure_ascii=False)


# ---------- record ----------

def test_record_appends_jsonl(tmp_path, capsys):
    log = tmp_path / "cm.jsonl"
    assert cm.main(["record", "--log", str(log), "--hit", "4500", "--miss", "500",
                    "--tag", "chat"]) == 0
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["hit"] == 4500 and rec["miss"] == 500 and rec["tag"] == "chat"
    assert rec["ts"].endswith("Z")
    assert "已记录" in capsys.readouterr().out


def test_record_from_response(tmp_path):
    log = tmp_path / "cm.jsonl"
    resp = tmp_path / "resp.json"
    resp.write_text(json.dumps({"usage": {"prompt_tokens": 8,
                                          "prompt_cache_hit_tokens": 5,
                                          "prompt_cache_miss_tokens": 3}}),
                    encoding="utf-8")
    assert cm.main(["record", "--log", str(log), "--response", str(resp)]) == 0
    rec = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert rec["hit"] == 5 and rec["miss"] == 3


def test_record_from_response_with_bom(tmp_path):
    """Windows PS Set-Content -Encoding UTF8 写 BOM → utf-8-sig 兼容 (教训固化)."""
    log = tmp_path / "cm.jsonl"
    resp = tmp_path / "resp.json"
    resp.write_bytes(b"\xef\xbb\xbf" + json.dumps(
        {"usage": {"prompt_cache_hit_tokens": 7, "prompt_cache_miss_tokens": 3}}
    ).encode("utf-8"))
    assert cm.main(["record", "--log", str(log), "--response", str(resp)]) == 0
    rec = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert rec["hit"] == 7 and rec["miss"] == 3


def test_record_negative_rejected(tmp_path, capsys):
    log = tmp_path / "cm.jsonl"
    assert cm.main(["record", "--log", str(log), "--hit", "-1", "--miss", "1"]) == 2
    assert "不能为负" in capsys.readouterr().err
    assert not log.exists()


def test_record_zero_zero_rejected(tmp_path, capsys):
    log = tmp_path / "cm.jsonl"
    assert cm.main(["record", "--log", str(log)]) == 2
    assert "非零用量" in capsys.readouterr().err


def test_record_bad_response_file(tmp_path, capsys):
    log = tmp_path / "cm.jsonl"
    assert cm.main(["record", "--log", str(log), "--response", str(tmp_path / "nope.json")]) == 2
    assert "解析响应失败" in capsys.readouterr().err


# ---------- report ----------

def test_report_healthy(tmp_path, capsys):
    log = tmp_path / "cm.jsonl"
    log.write_text(_rec_line(97, 3) + "\n" + _rec_line(190, 10) + "\n", encoding="utf-8")
    assert cm.main(["report", "--log", str(log)]) == 0
    out = capsys.readouterr().out
    assert "总命中率" in out and "95.7%" in out  # 287/300
    assert "✅ 健康" in out


def test_report_warn(tmp_path, capsys):
    log = tmp_path / "cm.jsonl"
    log.write_text(_rec_line(85, 15) + "\n", encoding="utf-8")  # 85%
    assert cm.main(["report", "--log", str(log)]) == 1
    assert "⚠️" in capsys.readouterr().out


def test_report_critical(tmp_path, capsys):
    log = tmp_path / "cm.jsonl"
    log.write_text(_rec_line(70, 30) + "\n", encoding="utf-8")  # 70%
    assert cm.main(["report", "--log", str(log)]) == 2
    assert "🔴 紧急" in capsys.readouterr().out


def test_report_empty(tmp_path, capsys):
    log = tmp_path / "cm.jsonl"
    assert cm.main(["report", "--log", str(log)]) == 1
    assert "无记录" in capsys.readouterr().out


def test_report_window_filters_old(tmp_path, capsys):
    log = tmp_path / "cm.jsonl"
    old = "2026-07-01T00:00:00Z"
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:00:00Z")
    log.write_text(_rec_line(50, 50, ts=old) + "\n" + _rec_line(95, 5, ts=now) + "\n",
                   encoding="utf-8")
    assert cm.main(["report", "--log", str(log), "--window", "24"]) == 0
    out = capsys.readouterr().out
    assert "95.0%" in out  # 旧记录被窗口排除


def test_report_per_tag_and_bad_lines(tmp_path, capsys):
    log = tmp_path / "cm.jsonl"
    log.write_text(_rec_line(100, 0, tag="b") + "\n"
                   + "not-json{{{\n"           # 损坏行 → 跳过
                   + _rec_line(90, 10, tag="a") + "\n", encoding="utf-8")
    assert cm.main(["report", "--log", str(log)]) == 0  # 总 190/200 = 95.0% → 健康
    out = capsys.readouterr().out
    assert "[a] 90.0%" in out and "[b] 100.0%" in out
    assert "2 条记录" in out  # 损坏行不计入


# ---------- diff ----------

def test_diff_identical(tmp_path, capsys):
    base = tmp_path / "b.json"
    nxt = tmp_path / "n.json"
    msgs = [{"role": "system", "content": "S"}, {"role": "user", "content": "Q"}]
    base.write_text(json.dumps({"messages": msgs}), encoding="utf-8")
    nxt.write_text(json.dumps({"messages": msgs}), encoding="utf-8")
    assert cm.main(["diff", "--base", str(base), "--next", str(nxt)]) == 0
    assert "完全一致 (2 条)" in capsys.readouterr().out


def test_diff_divergence(tmp_path, capsys):
    base = tmp_path / "b.json"
    nxt = tmp_path / "n.json"
    base.write_text(json.dumps({"messages": [{"role": "system", "content": "S"},
                                             {"role": "user", "content": "A"},
                                             {"role": "user", "content": "B"}]}),
                    encoding="utf-8")
    nxt.write_text(json.dumps({"messages": [{"role": "system", "content": "S"},
                                            {"role": "user", "content": "A"},
                                            {"role": "user", "content": "C"}]}),
                   encoding="utf-8")
    assert cm.main(["diff", "--base", str(base), "--next", str(nxt)]) == 1
    out = capsys.readouterr().out
    assert "公共前缀 2/3 条, 断裂于第 3 条" in out
    assert "user:B" in out and "user:C" in out and "差异点" in out


def test_diff_no_common(tmp_path, capsys):
    base = tmp_path / "b.json"
    nxt = tmp_path / "n.json"
    base.write_text(json.dumps({"messages": [{"role": "system", "content": "S1"}]}),
                    encoding="utf-8")
    nxt.write_text(json.dumps({"messages": [{"role": "system", "content": "S2"}]}),
                   encoding="utf-8")
    assert cm.main(["diff", "--base", str(base), "--next", str(nxt)]) == 1
    assert "无公共前缀" in capsys.readouterr().out


def test_diff_bad_file(tmp_path, capsys):
    assert cm.main(["diff", "--base", str(tmp_path / "nope.json"),
                    "--next", str(tmp_path / "nope.json")]) == 2
    assert "读取请求 JSON 失败" in capsys.readouterr().err


# ---------- CLI 冒烟 (subprocess, 验证编码与入口) ----------

def _run(root: pathlib.Path, *args):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, str(SCRIPT / "cache_monitor.py"), "--log", str(root), *args],
        capture_output=True, text=True, encoding="utf-8", env=env,
    )


def test_cli_record_report_subprocess(tmp_path):
    r1 = _run(tmp_path / "cm.jsonl", "record", "--hit", "95", "--miss", "5", "--tag", "cli")
    assert r1.returncode == 0
    assert "✅" in r1.stdout  # UTF-8 编码正常
    r2 = _run(tmp_path / "cm.jsonl", "report")
    assert r2.returncode == 0  # 95% → 健康
    assert "95.0%" in r2.stdout

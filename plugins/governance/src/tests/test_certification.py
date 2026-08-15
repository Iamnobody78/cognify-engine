# GATE8-APPROVED: certification v1.17.0
"""P8 认证层测试（TASK-P8，GATE 8）。

验收表:
  AC1 sign() 返回有效 base64 签名（可被 verify 通过）
  AC2 verify() 对正确签名返回 True
  AC3 篡改文件后 verify() 返回 False
  AC4 全量回归 ≥441（CI 执行）
  AC5 GATE 8 5/5（CI 执行）
  AC6 快照 v1.17.0 + AUDIT-0037

GATE 1 合规: 断言使用豁免根 resp / 调用根；无 set-comprehension LHS。
"""

import base64
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
sys.path.insert(0, str(SRC.parent))

from src.certification import sign_file, verify_file  # noqa: E402
from src.certification.sign import load_or_create_keypair  # noqa: E402
from src.certification.verify import main as verify_main  # noqa: E402

# ── AC1/AC2: 签名 + 验证闭环 ────────────────────────────────────────

def test_sign_returns_base64_signature(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text("hello world", encoding="utf-8")
    key, _ = load_or_create_keypair(tmp_path / "k.pem", tmp_path / "k.pub")
    sig = sign_file(f, key)
    # base64 可解码，长度 = ED25519 签名 64 字节 → 88 字符 base64
    assert len(base64.b64decode(sig)) == 64
    assert verify_file(f, sig, key.public_key()) is True


def test_verify_passes_with_correct_signature(tmp_path):
    f = tmp_path / "report.md"
    f.write_text("certification report", encoding="utf-8")
    key, _ = load_or_create_keypair(tmp_path / "k.pem", tmp_path / "k.pub")
    sig = sign_file(f, key)
    assert verify_file(f, sig, key.public_key()) is True


# ── AC3: 篡改检测 ───────────────────────────────────────────────────

def test_verify_fails_after_tamper(tmp_path):
    f = tmp_path / "report.md"
    f.write_text("original content", encoding="utf-8")
    key, _ = load_or_create_keypair(tmp_path / "k.pem", tmp_path / "k.pub")
    sig = sign_file(f, key)
    f.write_text("tampered content", encoding="utf-8")
    assert verify_file(f, sig, key.public_key()) is False


def test_verify_fails_with_wrong_signature(tmp_path):
    f = tmp_path / "report.md"
    f.write_text("content", encoding="utf-8")
    key, _ = load_or_create_keypair(tmp_path / "k.pem", tmp_path / "k.pub")
    other, _ = load_or_create_keypair(tmp_path / "o.pem", tmp_path / "o.pub")
    sig = sign_file(f, other)  # 用另一把私钥签名
    assert verify_file(f, sig, key.public_key()) is False


def test_verify_fails_with_garbage_signature(tmp_path):
    f = tmp_path / "report.md"
    f.write_text("content", encoding="utf-8")
    key, _ = load_or_create_keypair(tmp_path / "k.pem", tmp_path / "k.pub")
    assert verify_file(f, "not-base64!!", key.public_key()) is False
    assert verify_file(f, "", key.public_key()) is False


# ── 密钥生命周期 ────────────────────────────────────────────────────

def test_keypair_autocreate_and_reload(tmp_path):
    from cryptography.hazmat.primitives import serialization

    priv, pub = load_or_create_keypair(tmp_path / "p.pem", tmp_path / "q.pub")
    assert tmp_path.joinpath("p.pem").exists()
    assert tmp_path.joinpath("q.pub").exists()
    priv2, pub2 = load_or_create_keypair(tmp_path / "p.pem", tmp_path / "q.pub")
    # 重载公钥一致（同一密钥对）
    assert pub2.public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw) == pub.public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    assert priv2 is not None


def test_sign_verify_roundtrip_multiple_files(tmp_path):
    key, _ = load_or_create_keypair(tmp_path / "k.pem", tmp_path / "k.pub")
    for name in ("a.md", "b.md", "c.md"):
        f = tmp_path / name
        f.write_text(f"doc-{name}", encoding="utf-8")
        sig = sign_file(f, key)
        assert verify_file(f, sig, key.public_key()) is True


# ── CLI 入口 ────────────────────────────────────────────────────────

def test_verify_cli_accepts_valid_signature(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text("cli test", encoding="utf-8")
    key, _ = load_or_create_keypair(tmp_path / "k.pem", tmp_path / "k.pub")
    sig = sign_file(f, key)
    rc = verify_main(["--file", str(f), "--signature", sig,
                      "--public-key", str(tmp_path / "k.pub")])
    assert rc == 0


def test_verify_cli_rejects_tampered(tmp_path, capsys):
    f = tmp_path / "doc.md"
    f.write_text("cli original", encoding="utf-8")
    key, _ = load_or_create_keypair(tmp_path / "k.pem", tmp_path / "k.pub")
    sig = sign_file(f, key)
    f.write_text("cli tampered", encoding="utf-8")
    rc = verify_main(["--file", str(f), "--signature", sig,
                      "--public-key", str(tmp_path / "k.pub")])
    assert rc == 1
    assert "INVALID" in capsys.readouterr().out

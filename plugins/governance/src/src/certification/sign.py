"""ED25519 签名生成（私钥 → 文件签名）。

CLI: python -m src.certification.sign --file <path> [--private-key <pem>]
输出: base64 签名（stdout 单行）。首次运行自动生成密钥对。
"""

from __future__ import annotations

import argparse
import base64
import os
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

# 默认密钥目录: <repo>/.keys/（仓库内，随 Git 忽略；生产可换路径）
DEFAULT_KEY_DIR = Path(__file__).resolve().parent.parent.parent / ".keys"
DEFAULT_PRIVATE = DEFAULT_KEY_DIR / "ed25519_private.pem"
DEFAULT_PUBLIC = DEFAULT_KEY_DIR / "ed25519_public.pem"


def load_or_create_keypair(
    private_path: str | Path = DEFAULT_PRIVATE,
    public_path: str | Path = DEFAULT_PUBLIC,
) -> tuple[ed25519.Ed25519PrivateKey, ed25519.Ed25519PublicKey]:
    """加载私钥；不存在则生成并落盘（PEM 无加密，权限 600）。"""
    priv = Path(private_path)
    pub = Path(public_path)
    if priv.exists():
        key = serialization.load_pem_private_key(priv.read_bytes(), password=None)
        assert isinstance(key, ed25519.Ed25519PrivateKey)  # 类型窄化
        return key, key.public_key()
    priv.parent.mkdir(parents=True, exist_ok=True)
    key = ed25519.Ed25519PrivateKey.generate()
    priv.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    pub.write_bytes(key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    try:
        os.chmod(priv, 0o600)
    except OSError:
        pass  # Windows chmod 受限，忽略
    return key, key.public_key()


def sign_file(
    file_path: str | Path,
    private_key: ed25519.Ed25519PrivateKey | None = None,
) -> str:
    """对文件内容做 ED25519 签名，返回 base64 签名串。"""
    if private_key is None:
        private_key, _ = load_or_create_keypair()
    data = Path(file_path).read_bytes()
    sig = private_key.sign(data)
    return base64.b64encode(sig).decode("ascii")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cert-sign", description="ED25519 签名")
    ap.add_argument("--file", required=True, help="待签名文件路径")
    ap.add_argument("--private-key", default=str(DEFAULT_PRIVATE),
                    help="私钥 PEM 路径（默认 .keys/ed25519_private.pem）")
    args = ap.parse_args(argv)
    key, _ = load_or_create_keypair(args.private_key)
    sig = sign_file(args.file, key)
    print(sig)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

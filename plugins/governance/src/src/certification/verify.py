"""ED25519 签名验证（公钥 + 文件 + 签名 → True/False）。

CLI: python -m src.certification.verify --file <path> --signature <sig>
      [--public-key <pem>]
exit 0 = 验证通过；exit 1 = 验证失败或参数错误（fail-closed）。
"""

from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from .sign import DEFAULT_PUBLIC


def load_public_key(
    public_path: str | Path = DEFAULT_PUBLIC,
) -> ed25519.Ed25519PublicKey:
    """加载公钥 PEM；文件缺失 → 抛 FileNotFoundError（fail-closed）。"""
    key = serialization.load_pem_public_key(Path(public_path).read_bytes())
    assert isinstance(key, ed25519.Ed25519PublicKey)  # 类型窄化
    return key


def verify_file(
    file_path: str | Path,
    signature: str,
    public_key: ed25519.Ed25519PublicKey | None = None,
) -> bool:
    """验证文件签名。任何异常（坏 base64/坏密钥/签名不匹配）→ False。"""
    if public_key is None:
        public_key = load_public_key()
    try:
        sig = base64.b64decode(signature.encode("ascii"), validate=True)
    except (ValueError, TypeError):
        return False
    try:
        public_key.verify(sig, Path(file_path).read_bytes())
        return True
    except InvalidSignature:
        return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cert-verify", description="ED25519 验证")
    ap.add_argument("--file", required=True, help="待验证文件路径")
    ap.add_argument("--signature", required=True, help="base64 签名串")
    ap.add_argument("--public-key", default=str(DEFAULT_PUBLIC),
                    help="公钥 PEM 路径（默认 .keys/ed25519_public.pem）")
    args = ap.parse_args(argv)
    try:
        ok = verify_file(args.file, args.signature,
                         public_key=load_public_key(args.public_key))
    except FileNotFoundError:
        print(f"ERROR: public key not found: {args.public_key}", file=sys.stderr)
        return 1
    print("OK" if ok else "INVALID")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

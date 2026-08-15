"""P8 认证层: ED25519 签名生成与验证（防伪造证明协议地基）。

sign/verify 模块 + CLI 入口。密钥管理:
- 私钥: PEM 文件（默认 ~/.agent-governance/ed25519_private.pem）
- 公钥: PEM 文件（默认与私钥同目录 ed25519_public.pem）
- 无密钥时自动生成并落盘（首次运行引导）。
"""

from .sign import sign_file, load_or_create_keypair, main as sign_main
from .verify import verify_file, load_public_key, main as verify_main

__all__ = [
    "sign_file",
    "verify_file",
    "load_or_create_keypair",
    "load_public_key",
    "sign_main",
    "verify_main",
]

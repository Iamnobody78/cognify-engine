"""认证与授权 (ARCH-ROUND 2 / GAP-3.1): JWT + 角色访问控制。

角色层级: viewer(只读) < auditor(审计+验证) < admin(策略部署+用户管理)

- JWT: HS256/RS256 (GOV_AUTH_ALGORITHM 白名单校验, 见 S2), 从 GOV_AUTH_SECRET 读取
- 访问令牌: 短时效 (默认 12h, GOV_AUTH_TTL_HOURS)
- 刷新令牌 (S2): 长时效 (默认 7d, GOV_AUTH_REFRESH_TTL_HOURS), token_type=refresh,
  仅可用于 /auth/refresh 换发新令牌对 — 不可充当访问令牌
- 密钥轮换 (S2): GOV_AUTH_SECRETS (逗号分隔旧密钥) 用于解码期内旧令牌,
  签发始终使用当前 GOV_AUTH_SECRET
- 密码: passlib bcrypt
- 与 agent-governance-v2 租户打通: 见 docs/architecture/authz.md §5
  （共享 GOV_AUTH_SECRET + 角色映射表, 打通实现列 P1）
"""
import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from database import get_session_factory
from models import User

# ---- 配置 ----
DEV_SECRET = "dev-only-secret-change-me-0123456789abcdef"  # 生产必须设置 GOV_AUTH_SECRET
SECRET = os.getenv("GOV_AUTH_SECRET", DEV_SECRET)
if SECRET == DEV_SECRET:
    logging.getLogger("governance.auth").warning(
        "GOV_AUTH_SECRET 未设置——使用开发默认值, 生产环境必须配置!"
    )
TOKEN_TTL_HOURS = int(os.getenv("GOV_AUTH_TTL_HOURS", "12"))
# S2: 刷新令牌时效 (默认 7 天)
REFRESH_TOKEN_TTL_HOURS = int(os.getenv("GOV_AUTH_REFRESH_TTL_HOURS", "168"))
# S2: 算法白名单 — 防止配置回退到弱算法 (fail-closed 配置校验)
ALGORITHM = os.getenv("GOV_AUTH_ALGORITHM", "HS256")
_ALLOWED_ALGORITHMS = {"HS256", "RS256"}
if ALGORITHM not in _ALLOWED_ALGORITHMS:
    raise RuntimeError(
        f"GOV_AUTH_ALGORITHM={ALGORITHM!r} 不在白名单 {sorted(_ALLOWED_ALGORITHMS)} — "
        f"拒绝启动 (S2 配置校验)"
    )
# S2: 密钥轮换窗口 — 旧密钥仅用于解码验证, 签发始终用当前 SECRET
_LEGACY_SECRETS = [
    s for s in os.getenv("GOV_AUTH_SECRETS", "").split(",") if s
]
if _LEGACY_SECRETS:
    logging.getLogger("governance.auth").info(
        "检测到 %d 个轮换期旧密钥 (GOV_AUTH_SECRETS) — 仅用于解码",
        len(_LEGACY_SECRETS),
    )

# 角色等级（数字越大权限越高）
ROLE_LEVEL = {"viewer": 1, "auditor": 2, "admin": 3}

bearer_scheme = HTTPBearer(auto_error=False)

# ---- 密码 (bcrypt 原生 API; passlib 1.7.4 与 bcrypt>=4.1 不兼容, 弃用) ----
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False

# ---- JWT ----
def create_token(user: User, ttl_hours: Optional[int] = None,
                 token_type: str = "access") -> str:
    """签发 JWT。token_type: access(短时效) / refresh(长时效, 仅换发用)。"""
    payload = {
        "sub": user.username,
        "role": user.role,
        "type": token_type,
        "jti": uuid.uuid4().hex,  # 令牌唯一 ID — 轮换/审计追踪用 (S2)
        "exp": datetime.utcnow() + timedelta(hours=ttl_hours or TOKEN_TTL_HOURS),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)

def create_refresh_token(user: User) -> str:
    """S2: 签发刷新令牌 (长时效, 仅 /auth/refresh 可消费)。"""
    return create_token(user, ttl_hours=REFRESH_TOKEN_TTL_HOURS,
                        token_type="refresh")

def decode_token(token: str,
                 expected_type: Optional[str] = "access") -> Optional[dict]:
    """解码并校验 JWT。

    S2 增强:
      - 默认期望类型 access — refresh 令牌被误用为访问令牌时直接拒绝
      - 轮换窗口内旧密钥 (GOV_AUTH_SECRETS) 可解码, 但签发始终用新密钥
    """
    for secret in (SECRET, *_LEGACY_SECRETS):
        try:
            payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        except jwt.PyJWTError:
            continue
        if expected_type is not None and payload.get("type") != expected_type:
            return None  # 类型不匹配 → 视为无效 (防 refresh 冒充 access)
        return payload
    return None

# ---- 依赖注入 ----
def get_db():
    """FastAPI 依赖: 会话（与既有 get_session_factory 通道一致）。"""
    factory = get_session_factory()
    db = factory()
    try:
        yield db
    finally:
        db.close()

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """从 Bearer token 解析当前用户；无效/缺失 → 401。

    仅接受 access 类型令牌 (decode_token 默认 expected_type="access",
    S2: refresh 令牌不得充当访问凭据)。
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少认证凭据 (Authorization: Bearer <token>)",
        )
    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="token 无效或已过期"
        )
    user = db.query(User).filter(User.username == payload.get("sub")).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在"
        )
    return user

def require_role(min_role: str):
    """角色门控依赖工厂: min_role 为 viewer/auditor/admin。"""
    def _checker(user: User = Depends(get_current_user)) -> User:
        if ROLE_LEVEL.get(user.role, 0) < ROLE_LEVEL.get(min_role, 99):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足: 需要 {min_role} 角色 (当前: {user.role})",
            )
        return user
    return _checker

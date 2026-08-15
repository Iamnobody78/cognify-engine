"""ARCH-ROUND 2 / GAP-3.1: RBAC 认证与角色矩阵测试。

覆盖:
- 未认证 → 401
- 登录成功/失败
- /me 当前用户
- 角色矩阵: viewer 可读不可部署; auditor 可验证不可部署; admin 可部署
- 用户管理仅 admin
"""
import pytest
from fastapi.testclient import TestClient

from main import app

AUTH = {"username": "admin", "password": "admin123"}


@pytest.fixture(scope="module")
def client():
    """module 级 client: startup seed admin + 登录。"""
    with TestClient(app) as c:
        r = c.post("/api/auth/login", json=AUTH)
        assert r.status_code == 200, f"admin login failed: {r.text}"
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


def _login(c: TestClient, username: str, password: str) -> str:
    r = c.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _fresh_client() -> TestClient:
    """无认证头的干净 client（同 app, 不触发重复 seed）。"""
    c = TestClient(app)
    return c


# ── 认证基础 ──────────────────────────────────────────────

def test_unauthenticated_gets_401():
    """人类端点未带 token → 401。"""
    with TestClient(app) as c:
        r = c.get("/api/governance/agents")
        assert r.status_code == 401


def test_login_success(client):
    r = client.post("/api/auth/login", json=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert "token" in data and data["user"]["role"] == "admin"


def test_login_wrong_password(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_me_returns_current_user(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["username"] == "admin"


def test_invalid_token_401():
    with TestClient(app) as c:
        c.headers.update({"Authorization": "Bearer not.a.jwt"})
        assert c.get("/api/governance/agents").status_code == 401


# ── 角色矩阵 ──────────────────────────────────────────────

def _mk_role_user(client, role: str, username: str) -> str:
    """创建角色用户（幂等: 已存在先删——测试写真实 db, 重复运行不 409）。"""
    client.delete(f"/api/auth/users/{username}")  # 404 忽略
    r = client.post("/api/auth/users",
                    json={"username": username, "password": "pw12345", "role": role})
    assert r.status_code == 201, r.text
    return _login(client, username, "pw12345")


def test_viewer_can_read_but_not_deploy(client):
    token = _mk_role_user(client, "viewer", "rbac_viewer")
    with TestClient(app) as c:
        c.headers.update({"Authorization": f"Bearer {token}"})
        assert c.get("/api/governance/agents").status_code == 200
        assert c.get("/api/governance/audit").status_code == 200
        # viewer 部署 → 403
        r = c.post("/api/governance/policies/deploy",
                   json={"protocol": "x_demo", "yaml": "schema_version: 11-col-v1\n"})
        assert r.status_code == 403


def test_auditor_can_validate_but_not_deploy(client):
    token = _mk_role_user(client, "auditor", "rbac_auditor")
    with TestClient(app) as c:
        c.headers.update({"Authorization": f"Bearer {token}"})
        assert c.get("/api/governance/vce/history").status_code == 200
        r = c.post("/api/governance/policies/deploy",
                   json={"protocol": "x_demo", "yaml": "schema_version: 11-col-v1\n"})
        assert r.status_code == 403


def test_admin_can_deploy(client):
    """admin 部署请求可到达 engine（无效协议 → 非 403, 而是 4xx 引擎语义错误）。"""
    r = client.post("/api/governance/policies/deploy",
                    json={"protocol": "x_does_not_exist_anywhere",
                          "yaml": "schema_version: 11-col-v1\nprotocol:\n  name: x_demo\n"})
    assert r.status_code != 403  # 权限已通过; 失败在引擎语义层


def test_user_management_admin_only(client):
    token = _mk_role_user(client, "viewer", "rbac_lowly")
    with TestClient(app) as c:
        c.headers.update({"Authorization": f"Bearer {token}"})
        assert c.get("/api/auth/users").status_code == 403
        r = c.post("/api/auth/users",
                   json={"username": "hacker", "password": "x1234567", "role": "admin"})
        assert r.status_code == 403

# ── S2: 刷新令牌 (refresh token rotation) ─────────────────────────

def test_login_returns_token_pair():
    """S2: 登录返回 access + refresh 令牌对。"""
    with TestClient(app) as c:
        r = c.post("/api/auth/login", json=AUTH)
        assert r.status_code == 200
        data = r.json()
        assert "token" in data and "refresh_token" in data

def test_refresh_exchanges_for_new_pair():
    """S2: refresh 令牌 → 换发全新令牌对 (rotation)。"""
    with TestClient(app) as c:
        login = c.post("/api/auth/login", json=AUTH).json()
        r = c.post("/api/auth/refresh",
                   json={"refresh_token": login["refresh_token"]})
        assert r.status_code == 200
        data = r.json()
        assert data["token"] != login["token"]
        assert data["refresh_token"] != login["refresh_token"]
        assert data["user"]["username"] == "admin"

def test_refresh_token_cannot_be_used_as_access():
    """S2: refresh 令牌冒充访问令牌 → 401 (类型门禁)。"""
    with TestClient(app) as c:
        login = c.post("/api/auth/login", json=AUTH).json()
        c.headers.update({"Authorization": f"Bearer {login['refresh_token']}"})
        assert c.get("/api/auth/me").status_code == 401

def test_refresh_with_access_token_rejected():
    """S2: access 令牌不能用于 /refresh 端点。"""
    with TestClient(app) as c:
        login = c.post("/api/auth/login", json=AUTH).json()
        r = c.post("/api/auth/refresh",
                   json={"refresh_token": login["token"]})
        assert r.status_code == 401

def test_refresh_with_garbage_token_rejected():
    with TestClient(app) as c:
        r = c.post("/api/auth/refresh", json={"refresh_token": "garbage"})
        assert r.status_code == 401


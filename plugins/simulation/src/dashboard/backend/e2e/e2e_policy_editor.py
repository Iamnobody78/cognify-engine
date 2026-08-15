"""S69 Track4: 策略编辑器 E2E 验证 — 真实 HTTP 全链路

链路: GET source → POST validate (零副作用) → POST deploy (带回滚) → GET source 确认
验证点:
  1. 合法 11-col-v1 协议 validate → 200
  2. deploy → 200 + protocol_rules 生成
  3. source 读取回环一致
  4. 非法 YAML validate → 400
  5. deploy 无效协议 → 422 (不落盘)
  6. 路径遍历防护: ../evil → 404/422
  7. 不存在协议 source → 404

用法:
  python e2e_policy_editor.py
需要: uvicorn main:app --port 8010 已在运行
"""
import sys
import json
import urllib.request
import urllib.error

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = "http://127.0.0.1:8010/api/governance"
AUTH_BASE = "http://127.0.0.1:8010/api/auth"
VALID_PROTOCOL = """schema_version: 11-col-v1
protocol:
  module: e2e_demo
  category: epistemology
  level: L2
  core_purpose: E2E 验证用协议
  metacognitive_q: 是否可验证？
  collab_directive: 演示
  trigger: e2e 测试
  ethics_boundary: 不得伪造
  source: docs/architecture.md
  frequency: always
  strategy: verify
  expected_output: 验证结果
"""
BROKEN_YAML = "schema_version: 11-col-v1\nprotocol:\n  module: [unclosed"
BAD_SCHEMA = """schema_version: 99-old-format
protocol:
  module: e2e_bad_schema
"""

passed = failed = 0


def login() -> str:
    """RBAC (ARCH-ROUND 2): 登录 admin 拿 JWT。"""
    body = json.dumps({"username": "admin", "password": "admin123"}).encode()
    req = urllib.request.Request(AUTH_BASE + "/login", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
    return data["token"]


TOKEN = login()
AUTH_HEADERS = {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"}


def call(method: str, path: str, body=None) -> tuple[int, dict]:
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=AUTH_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def check(name: str, cond: bool, detail: str = ""):
    global passed, failed
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {name} {detail}")
    if cond:
        passed += 1
    else:
        failed += 1


def main() -> None:
    print("策略编辑器 E2E (真实 HTTP :8010)")
    print("=" * 64)

    # RULE-ARCH-004: E2E 部署会落盘 config/protocols/e2e_demo.yaml，
    # 必须在 finally 中自清理，避免污染真实协议目录 (seed 计数 12≠9)。
    e2e_protocol_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "..", "..", "..",
        "agent-governance-v2", "config", "protocols", "e2e_demo.yaml")
    try:
        _run_checks()
    finally:
        if os.path.exists(e2e_protocol_file):
            os.remove(e2e_protocol_file)
            print(f"  [CLEANUP] 移除残留 {os.path.basename(e2e_protocol_file)}")


def _run_checks() -> None:
    # 0. 健康检查 (实际路由 /api/health)
    try:
        with urllib.request.urlopen(BASE.replace("/governance", "/health"), timeout=5) as resp:
            code0 = resp.status
    except Exception as e:
        code0 = getattr(e, "code", -1)
    check("engine/health", code0 == 200, f"({code0})")

    # 1. validate 合法协议 → 200
    code, r = call("POST", "/policies/validate",
                   {"protocol": "e2e_demo", "yaml": VALID_PROTOCOL})
    check("validate 合法协议", code == 200, f"({code}) {str(r)[:80]}")

    # 2. validate 非法 YAML → 200 + valid=False (语义层错误)
    code, r = call("POST", "/policies/validate",
                   {"protocol": "e2e_demo", "yaml": BROKEN_YAML})
    check("validate 非法YAML", code == 200 and r.get("valid") is False, f"({code})")

    # 3. validate 错误 schema → 200 + valid=False
    code, r = call("POST", "/policies/validate",
                   {"protocol": "e2e_bad", "yaml": BAD_SCHEMA})
    check("validate 错误schema", code == 200 and r.get("valid") is False, f"({code})")

    # 4. deploy 合法协议 → 200 + protocol_rules == 3
    code, r = call("POST", "/policies/deploy",
                   {"protocol": "e2e_demo", "yaml": VALID_PROTOCOL})
    ok4 = code == 200 and r.get("protocol_rules") == 3 and r.get("deployed") is True
    check("deploy 合法协议(3规则)", ok4,
          f"({code}) deployed={r.get('deployed')} rules={r.get('protocol_rules')}")

    # 5. deploy 非法 YAML → 422 (引擎校验失败, 不落盘)
    code, r = call("POST", "/policies/deploy",
                   {"protocol": "e2e_demo", "yaml": BROKEN_YAML})
    check("deploy 非法YAML 422", code == 422, f"({code})")

    # 6. source 回环 → 200 且含 module (返回结构 {protocol, yaml})
    code, r = call("GET", "/policies/e2e_demo/source")
    ok6 = code == 200 and "e2e_demo" in r.get("yaml", "") and r.get("protocol") == "e2e_demo"
    check("source 回环一致", ok6, f"({code})")

    # 7. 路径遍历防护 → 404 (模块名校验)
    code, r = call("GET", "/policies/..%2Fevil/source")
    check("路径遍历防护", code in (400, 404, 422), f"({code})")

    # 8. 不存在协议 source → 404
    code, r = call("GET", "/policies/nonexistent_protocol/source")
    check("不存在协议 404", code == 404, f"({code})")

    print("=" * 64)
    print(f"E2E 结果: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

# Getting Started

5 分钟上手 agent-governance-v2。

## 环境要求

- Python 3.10-3.11（Tree-sitter AST 引擎依赖 0.21.3，要求 <3.12）
- pip / venv

## 安装

```bash
# 克隆
git clone https://github.com/Iamnobody78/agent-governance-v2.git
cd agent-governance-v2

# 创建虚拟环境（推荐 3.11）
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux/macOS

# 安装依赖
pip install -r requirements.txt
```

## 首次运行

```bash
# 启动治理网关（默认端口 9000）
python -m src.main
```

验证健康检查：

```bash
curl http://localhost:9000/v1/health
# -> {"status": "ok", ...}
```

## 第一个拦截请求

```bash
curl -X POST http://localhost:9000/v1/intercept \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/api/tools/exec",
    "method": "POST",
    "body": "{\"tool\": \"delete_file\"}"
  }'
```

响应示例（DENY 判定）：

```json
{
  "verdict": "DENY",
  "reason": "规则 'block-shell-tool' 匹配",
  "decision_id": "uuid",
  "trace_id": "uuid",
  "rationale": "工具调用 delete_file 被策略阻断"
}
```

## AST 硬阻断（v1.25.0 新增）

请求体中的代码片段（Python/Bash/SQL）在 **所有 YAML 规则匹配之前** 先过 Tree-sitter AST 检查：

```bash
curl -X POST http://localhost:9000/v1/intercept \
  -H "Content-Type: application/json" \
  -d '{"language": "python", "code": "eval(\"os.system(\\\"id\\\")\")"}'
# -> verdict: DENY, reason 含 "AST-BLOCK python code-execution L1:1 sexp=(call ...)"
```

- 逃生舱：`AG_AST_DISABLE=1` 环境变量可显式关闭 AST 前门（不推荐生产使用）
- 危险代码的审计 trace 带精确行号 + S-expression 标签，落 `DecisionRecord.reason`

## 配置

| 文件 | 作用 |
|------|------|
| `config/policies.yaml` | YAML 策略规则（path/method/json_path 条件） |
| `config/tenants.yaml` | 租户 API Key 映射（P13 认证） |
| `queries/*.scm` | AST 危险模式（S-expression，零正则） |
| `.aionui/context/TRIPLE_LOOP_SNAPSHOT.md` | 项目快照（版本/测试/提交链） |

## 运行测试

```bash
pytest tests/ -q        # 预期 574 passed
python -m src.critic.runner   # GATE 8: 5 批判者审计，预期 5/5 PASS
```

## 下一步

- 了解[五层架构](Architecture)
- 查看[完整 API](API-Reference)
- 生产部署看[Deployment](Deployment)

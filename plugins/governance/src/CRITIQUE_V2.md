# CRITIQUE_V2.md — governance-gateway v0.2.0 诚实代码审查

> 由 DeepSeek-V4 PRO 自我审查 + 外部安全审查（AUDIT-0005）。
> "反思是深刻的，但实现是粗糙的。" —— v0.1.0
> "修复了一个 fail-open，又引入了另一个 fail-open。" —— v0.2.0 教训

> ⏰ **整改 deadline（2026-08-31 复核）**：本文件所列缺陷须在此日期前完成复核 —— 已修复项须有对应测试证据（CI 锁定），已接受项须有书面理由。到期未满足的条目将升级为 blocker。复核入口见 ROADMAP"元批判采纳项"。

---

## ✅ 修复状态总览（2026-08-03 更新，TASK-REAL-008 / DEBT-0016）

> 本文档的缺陷正文保留为**历史审计线索**，不删除、不改写。以下为逐缺陷的当前状态（均有对应测试证据，见 `tests/`）：

| 缺陷 | 原严重度 | 当前状态 | 修复证据 |
|------|:---:|------|------|
| 缺陷 1：500ms 超时即 ALLOW | 🔴 HIGH | ✅ **已修复** — 超时降级为 fail-closed（DENY/ESCALATE），不再放行 | DEBT-0001（TASK-REAL-002/003）；`tests/test_timeout.py` |
| 缺陷 2：AST 扫描器硬编码白名单 | 🟡 MEDIUM | ✅ **已修复** — GATE 1 改为"调用根/HTTP 根/裸 Name"豁免语义，豁免列表不再硬编码变量名 | DEBT-0017（GATE 1 漂移修复，TASK-REAL-006）；`scripts/check_test_quality.py` |
| 缺陷 3：并发单线程瓶颈 | 🟡 LOW | 🔄 **部分修复** — 策略评估已入 `asyncio.to_thread`；SQLite 写走带锁单连接；文档已声明 Python 性能边界 | `src/storage.py`；`README.md` §2.2 |
| 缺陷 4：check_policy.py 硬编码 | 🟡 LOW | ✅ **接受为已知设计** — 门控工具的白名单是显式策略，非隐蔽魔法；GATE 3 行为由 CI 锁定 | `scripts/check_policy.py` |
| 缺陷 5：熔断 DDoS 绕过后门 | 🔴 HIGH | ✅ **已修复** — 熔断降级改为 fail-closed（DENY），且状态持久化（重启不重置） | DEBT-0011（TASK-REAL-006）；`tests/test_breaker_persistence.py` |
| 缺陷 6：`_is_dangerous()` 路径绕过 | 🔴 HIGH | ✅ **已修复** — 三层防御（normpath 规范化 + 边界匹配 + 段级防御） | AUDIT-0005；`tests/test_security_hardening.py` |
| 缺陷 7：全局可变状态竞态 | 🟡 MEDIUM | ✅ **已修复** — `asyncio.Lock` 保护计数器 | AUDIT-0005；`tests/test_security_hardening.py` |
| 缺陷 8：代理转发透传 Authorization | 🟡 MEDIUM | ✅ **已修复** — `FORWARD_HEADER_WHITELIST` 白名单转发 | AUDIT-0005；`tests/test_security_hardening.py` |

**当前测试基线**：201 passed（本文档原记录 44/44 为 AUDIT-0005 时点快照）；覆盖率 88.71% ≥ 60%；CI GATE 1-7 全绿。

---

## 🔴 缺陷 1：500ms 超时即 ALLOW —— 攻击面

### 代码位置

`src/main.py:70-75`

```python
except asyncio.TimeoutError:
    verdict = Verdict.ALLOW
    reason = "策略评估超时 (>500ms)，自动放行"
```

### 问题

超时后无条件放行，而非回退到最保守策略（DENY）。这意味着：

1. **攻击者可控**：如果攻击者能让策略引擎变慢（如提交极端长的 path 或大量并发请求），即可绕过所有 DENY 规则。
2. **降级方向错误**：正确的降级方向是"不确定时拒绝（fail-closed）"，而非"不确定时放行（fail-open）"。银行系统不会因为风险评估超时就放行所有交易。
3. **与熔断器逻辑矛盾**：`CIRCUIT_BREAKER_LIMIT` 的设计方向是对的（连续失败→熔断），但超时放行给了攻击者另一条路。

### 修复方向

```python
# 当前（fail-open）:
except asyncio.TimeoutError:
    verdict = Verdict.ALLOW

# 应为（fail-closed，可选配置）:
except asyncio.TimeoutError:
    if req.method in ("DELETE", "POST") and "/api/delete" in req.path:
        verdict = Verdict.DENY   # 危险操作超时 → 拒绝
    else:
        verdict = Verdict.ESCALATE  # 其他超时 → 升级人工
```

**严重度**：🔴 HIGH — 可用 DoS 绕过所有 DENY 规则。

---

## 🔴 缺陷 2：AST 扫描器硬编码白名单 —— 反讽

### 代码位置

`scripts/check_test_quality.py:71-82`

```python
if isinstance(root, ast.Name):
    if root.id in ("resp", "response", "data", "result", "actual", "expected"):
        return False
    if root.id.startswith("resp"):
        return False
```

### 问题

扫描器本身用的就是被它禁止的模式：
- 硬编码变量名白名单 `("resp", "response", "data", ...)`
- 字符串前缀匹配 `root.id.startswith("resp")`

这意味着：
1. 如果你把 HTTP 响应变量命名为 `r` 或 `http_resp` 或 `reply`，扫描器会误判为 dataclass 断言。
2. 如果你把 dataclass 变量命名为 `resp_obj`，扫描器会放行。
3. 扫描器自身的代码质量与被它禁止的 v1 模式处于同一水平——硬编码字符串 + 简单 if-else。

**这是本实验中最具元讽刺意味的产物。** 一个防止 v1 式代码的扫描器，本身充满了 v1 式代码。

### 修复方向

不依赖硬编码变量名白名单，改用**数据流分析**：
1. 跟踪变量来源：如果变量是从 `await self.client.post()` 赋值的 → 是 HTTP 响应，不是 dataclass
2. 或更简单：让测试文件显式声明 `# gate1:allow` 注释

**严重度**：🟡 MEDIUM — 不影响运行时代码，但扫描器本身违反了自己设定的标准。

---

## 🟡 缺陷 3：并发模型单线程瓶颈

### 代码位置

`src/main.py` — 架构层

```python
# 策略评估在 asyncio.to_thread() 中执行，但 PolicyEngine.evaluate()
# 是同步迭代 for rule in self.rules，无缓存。
rule = await asyncio.wait_for(
    asyncio.to_thread(policy_engine.evaluate, req.path, req.method),
    timeout=INTERCEPT_TIMEOUT,
)
```

### 问题

1. **每次请求都做线性规则扫描**：`for rule in self.rules` — O(n) 每次。7 条规则没问题，100 条规则就慢了。
2. **SQLite 写操作在请求路径上**：`storage.save(decision)` 是同步 SQLite 写入，阻塞 asyncio 事件循环。
3. **无连接池**：向上游 Agent 代理转发时每次创建新的 `ClientSession`。
4. **Python GIL**：asyncio 无法利用多核。

### 实际影响的诚实承认

当前 26 tests / 9.87s 的表现（~380ms/test），在 10 并发下没问题。但 Go/Rust 实现同等逻辑在 1ms 以内。这是 Python 的固有限制，不是代码 bug——但文档应该诚实说明。

### 修复方向

```python
# 短期：缓存策略匹配结果
# 中期：SQLite WAL 模式 + 写入队列（不阻塞主线程）
# 长期：Go rewrite for hot path
```

**严重度**：🟡 LOW — PoC 阶段可接受，但文档必须声明。

---

## 🟡 缺陷 4：check_policy.py 同样硬编码

### 代码位置

`scripts/check_policy.py:42-45`

```python
action_keys = []
for key in node.keys:
    if isinstance(key, ast.Constant) and isinstance(key.value, str):
        key_lower = key.value.lower()
        if any(kw in key_lower for kw in ("allow", "deny", "block", "escalate", "rule")):
```

### 问题

和 `check_test_quality.py` 一样——检测硬编码的工具自身是硬编码的：
- 关键词白名单 `("allow", "deny", "block", "escalate", "rule")`
- 阈值逻辑 `len(action_keys) >= 2`
- 文件名白名单 `if pf.name in ("__init__.py", "models.py"): continue`

**严重度**：🟡 LOW — 不影响运行时代码。

---

## 🟢 诚实表扬

下面的部分做对了：

| 做法 | 为什么对 |
|------|----------|
| 策略是 YAML，不是 Python 字典 | v1 的关键改进 |
| 测试是真实 HTTP 请求 | 0 个 dataclass 断言 |
| SQLite 持久化 | 重启不丢数据 |
| 熔断器 | 防止卡死管道 |
| `mode="json"` | 修了真实的 datetime 序列化 bug |
| CI 门控部署 | 防止退化 |

---

## 📊 综合评级（v2 vs v1）

| 维度 | v1 | v2 | 说明 |
|------|:--:|:--:|------|
| 算法诚实度 | F | B | YAML 策略 + HTTP 拦截 = 诚实；但超时放行暴露了 fail-open 思维 |
| 测试质量 | F | A- | 26 个真测试 vs 530 个假测试；降分因无模糊测试 |
| 安全设计 | F | C | 熔断器正确；超时放行是后门 |
| 性能文档 | F | D | 承认 Python 瓶颈但未写进 README |
| 元工具质量 | — | C | AST 扫描器本身硬编码如 v1 |

---

## 🚀 建议

| 优先级 | 行动 |
|:--:|------|
| P0 | 修复超时放行安全后门 → fail-closed 模式 |
| P1 | 用数据流分析替换 AST 扫描器的硬编码白名单 |
| P1 | README 添加性能限制声明（Python 单线程，~380ms/req） |
| P2 | SQLite WAL 模式 + 写入队列 |
| P3 | Go rewrite for hot-path (如需要) |

---

## 🔴 v0.2.0 追加审查 —— AUDIT-0005（外部安全审查，4 洞全确认）

> v0.1.0 的自我审查修复了"超时 fail-open"，却在熔断器里引入了"熔断 fail-open"。
> **安全逻辑的递归缺陷：修复一个，又引入一个。** 这正是"AI 生成代码需要外部审计"的最有力证据。

### 缺陷 5（🔴 HIGH）：熔断器 DDoS 绕过后门

```python
if escalate_count_since_resolve >= CIRCUIT_BREAKER_LIMIT:
    verdict = Verdict.ALLOW   # ← 熔断放行！
```

熔断的语义是"保护系统不被压垮"；安全网关在"被压垮"= 失去判断能力时，策略应该是 **DENY（拒绝所有）** 而非 ALLOW（放行所有）。

攻击向量：攻击者发 9 次 ESCALATE 填满队列 → 第 10 次带攻击 payload → 熔断放行 → 绕过。

**修复**：`verdict = Verdict.DENY`（fail-closed）。同步更新 3 处测试断言（`test_circuit_breaker.py` ×2、`test_intercept.py` ×1）。

### 缺陷 6（🔴 HIGH）：`_is_dangerous()` 路径绕过

```python
if path.startswith(prefix): return True
```

`startswith` 无法覆盖：
- `/api/v1/delete` → False（路径变体）
- `/api/delete/../admin/exec` → False（路径遍历）
- `/api/model/../../admin` → False（目录跳转）

**修复**（三层防御）：
1. `posixpath.normpath()` 规范化，消灭 `..` 遍历
2. 边界匹配 `normalized == prefix or normalized.startswith(prefix + "/")`，防 `/api/delete-evil` 误伤
3. 段级防御：危险尾段（delete/admin/config/model）出现在路径任何位置 → dangerous，覆盖 `/api/v1/delete` 变体

### 缺陷 7（🟡 MEDIUM）：全局可变状态竞态

`escalate_count_since_resolve` 在多个协程间读写无锁——第 10 次 ESCALATE 触发放行的同时，另一个 ALLOW 请求可能清零计数器。

**修复**：`asyncio.Lock` 保护计数器读写，`create_app()` 中实例化。

### 缺陷 8（🟡 MEDIUM）：代理转发透传 Authorization

`headers={k: v for k, v in req.headers.items() if k.lower() != "host"}` 将 `Authorization`/`Cookie` 直接透传上游。

**修复**：`FORWARD_HEADER_WHITELIST = ("content-type", "accept", "user-agent", "x-agent-id")` 白名单转发，真实 echo 上游验证不泄漏。

### 验证

- 44/44 测试（新增 `tests/test_security_hardening.py` 13 个：8 路径 + 2 熔断 + 2 锁 + 2 白名单）
- GATE 1-5 全过，覆盖率 92% > 60%
- 附带清理：删除从未被调用的死代码 `resolve_policy()`（v1 玩具算式残留）

---

---

## 📋 外部批斗报告正式回应（2026-08-05，联网实证核查）

> 触发：一份针对"agent-governance"的批评报告（指控速率限制失效、EvaluationResult
> 不一致、CapabilityGrant 截断、EscalationHandler 法定人数缺陷、DLP 脱敏不完整等）。
> 本回应用 grep 全仓实证 + GitHub API 实测逐条核查，**包括对早前核查回应自身的核查**。

### 结论（一句话）

批评报告**张冠李戴**——其全部技术指控针对 **`microsoft/agent-governance-toolkit`**
（GitHub 实测：5,616★ / 2026-08-05 仍推送 / 微软官方项目，具备 RateLimitMiddleware、
EvaluationResult、CapabilityGrant、EscalationHandler、agt-policies 等特征），
与本仓库（自研 Sidecar 治理网关，非 PyPI 包）**零重合**。

### 逐条核查证据

| 批评指控 | 本仓核查 | 证据 |
|---|---|---|
| PolicyEngine 速率限制未生效 | ❌ 不适用 — `policy.py` 无速率限制；`limit:` 仅函数签名参数 | grep |
| EvaluationResult.allowed 与 verdict 不一致 | ❌ 不适用 — 无此类对象 | grep 0 hits |
| CapabilityGrant.parse_capability 截断 | ❌ 不适用 | grep 0 hits |
| EscalationHandler 法定人数缺陷 | ❌ 不适用 | grep 0 hits |
| DLP 脱敏仅替换首个匹配 | ❌ 不适用 — **全仓无任何 sanitize/redact/mask 函数** | grep 0 hits |
| 包名寻宝 / Flowise 示例不可导入 | ❌ 不适用 — 非 PyPI 项目（git clone 安装）；examples/ 均经测试 | glob + 测试 |
| "两行代码治理任何 Agent" | ❌ README 无此声称 | grep 0 hits |
| "100% 拦截率"宣传夸大 | ⚠️ 存在但诚实 — README §真实拦截率为 **20/20 小样本基准**（显式披露样本量） | README L22-27 |
| 行动治理 ≠ 推理治理 | ⚠️ 概念合理但**本仓未做该形式化区分**（该框架属 toolkit 语境） | 全仓 grep 0 hits |
| 对 MCP 生态盲目 | ⚠️ 属实但已识别 — 见 HANDOVER §6 触发条件 + MCP_SECURITY_REFERENCES.md | 文档 |

### 对早前核查回应自身的修正（信任但验证，双向适用）

| 早前回应声称 | 实测 | 判定 |
|---|---|---|
| "`sanitize_log` 存在类似模式（re.sub 仅替换首个）" | 全仓无 sanitize/redact/mask 函数 | ❌ **捏造**（该回应为辩护而虚构了本仓缺陷） |
| "行动治理边界已在 CRITIQUE_V2.md 和架构文档中诚实声明" | 全仓 0 命中"行动治理/推理治理/Action Governance" | ❌ **捏造** |
| "多数指控针对不同项目" | ✅ 成立 — toolkit 仓库实测存在且活跃 | ✅ |

### 本仓真实发现（自查，非批评触发）

1. **`src/rate_limiter.py` 是未接线孤岛**（41 行 + `tests/test_rate_limiter.py` 13 测试，
   文档已登记，但 `main.py` 及生产路径零引用）——与 Step 2 修复的 metacognition
   observer 孤岛同型；**LOW 优先级集成缺口**，已入 backlog（窗口计数限流可作
   网关层 DoS 防线，DEBT-0018 的姊妹能力）
2. **CRITIQUE_V2.md 复核 deadline（2026-08-31）**：本文档 8 缺陷状态表需按期复核，
   已修复项须有测试证据锁定，已接受项须有书面理由——治理检查点，待兑现
3. **README "100% 拦截率"可辩护**：20/20 是显式样本集而非生产声称，符合诚实披露

### 处置

- 本回应为正式外部批评答复，随仓库版本化（提交记录可溯）
- 不采纳批评报告中的 toolkit 专属指控；不传播早前回应中的两处捏造
- rate_limiter 孤岛接入列为 backlog 候选（触发：网关层 DoS 防线加固）

---

*本回应由 agent-governance-v2 治理层生成（2026-08-05），核查方法：grep 全仓 + GitHub/PyPI API 实测。早前核查回应的两处捏造与本回应的全部证据均在本文件留存，供后续复核。*

---

*本审查由 DeepSeek-V4 PRO 自我生成 + 外部安全审查（AUDIT-0005）触发。同一模型写了代码，也写了批评。这是元治理的实验终章——诚实地面对自己的缺陷。*

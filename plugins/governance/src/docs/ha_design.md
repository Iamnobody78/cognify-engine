# HA 设计文档（Phase HA · v1.16.0）

> 目标：为三循环治理引擎解决**单点运行**问题——审计链、快照、降级路径
> 当前缺多实例协调能力。本 Phase 交付 **L1 进程内降级矩阵 + L2 跨进程
> 协调（文件锁 + 租约）+ L3 审计链防分裂**，零新基础设施（不引入
> Redis/PostgreSQL——`storage.py` 深度耦合 SQLite 特有语法，迁移不可无缝）。

## 1. 问题定义

| 单点 | 风险 | 影响 |
|------|------|------|
| `storage.py` SQLite 单文件写 | 主实例崩溃 → 写缓冲/审计链中断 | 决策丢失窗口 |
| 无多实例协调 | 两个网关实例同时写 → 审计链分裂 | 因果链失真 |
| 降级仅限 P2 缓冲 | 无只读模式、无故障接管 | 服务不可用 |

## 2. 三层高可用方案

### L1 进程内降级（已具备，扩展为矩阵）

P2 已有：写缓冲批量提交 + WAL + fallback 磁盘日志 + 重试上限。本 Phase
在 `docs/ha_design.md` 固化矩阵，不做代码改动（避免回归 431 基线）：

| 故障 | 现行为 | 降级 |
|------|--------|------|
| SQLite 写失败（sqlite3.Error） | 缓冲累积 → 超上限转 fallback | 不丢记录 |
| fallback 写失败（OSError） | 记录丢失 + 日志 | 唯一不可解（磁盘不可用） |
| 进程崩溃 | WAL 保证最后提交不损坏 | 租约过期 → 副本接管 |

### L2 跨进程协调（本 Phase 新增：`src/ha/`）

**单写者模型**：决策记录统一由"主实例"写入，副本只读 + 租约监视。
避免分布式锁的复杂度——治理引擎是低频写（决策/审计），锁竞争极小。

```
┌─ 主实例 ──────────────────┐        ┌─ 副本实例（只读）──────────┐
│ Lease: acquire() → 持有    │        │ Lease: is_active() 轮询    │
│ FileLock: 保护租约文件     │        │ 非主 → 拒绝写（NotPrimary）│
│ save() → SQLite 写         │        │ get_recent()/get_trace()   │
└────────────────────────────┘        └────────────────────────────┘
        │ 主崩溃（租约过期 5s）              │ 检测到过期
        ▼                                   ▼
   FailoverCoordinator.recover()      try_acquire_primary() → 接管
```

**租约机制**（`lease.py`）：
- 租约文件：`<state_dir>/ha.lease.json`，内容 `{owner_id, expires_at, updated_at}`
- 获取：`FileLock` 保护下写 owner+expires（互斥临界区）
- 续约：`renew()` 刷新 expires_at（默认 5s TTL，主实例每 2s 续约）
- 过期检测：`is_active()` 比较时钟（容差 1s，防时钟抖动误判）
- 崩溃恢复：主进程崩溃 → OS 释放 FileLock → 但 lease 文件仍显示 owner →
  副本发现 expires_at 已过 → `FileLock` 可获取 → 写新 owner 接管

**文件锁**（`file_lock.py`）：
- Windows: `msvcrt.locking(fd, LK_NBLCK, 1)` 非阻塞尝试 + 重试退避
- POSIX: `fcntl.flock(fd, LOCK_EX | LOCK_NB)`
- 语义：**短临界区**——仅保护租约文件的读写原子性，绝不长期持有

### L3 审计链防分裂（本 Phase 新增：`src/ha/failover.py`）

- `decisions.id` 已有 PRIMARY KEY → 天然防重复写
- 主实例写入前校验 `parent_span_id` 存在（防孤儿节点）——由 `save()` 上层
  治理逻辑保证，HA 层通过 `NotPrimaryError` 拦截非主写
- 故障接管后：新主读旧库 → `_migrate()` 幂等 → 续写，审计链连续

## 3. 故障转移时序（failover.py）

```
t0    主 acquire → owner=primary-A, expires=t0+5s
t0+2  主 renew → expires=t0+7s（每 2s 续约）
t0+5  主崩溃（无 renew）
t0+6  副本B 轮询 is_active() → False（expires=t0+7s 未到？→ 容差 1s）
t0+8  副本B try_acquire_primary() → FileLock 可获取 → owner=primary-B
t0+8  副本B 从此可写；原主若复活 → 检测 owner 非己 → 自动降级只读
```

**脑裂防护**：FileLock（OS 级互斥）+ 租约（时间戳活性）双重判定——
`try_acquire_primary()` 成功 = 两者皆可 → 不可能双主同时写。

## 4. API 契约（src/ha/）

```python
# file_lock.py
class FileLock:                       # 上下文管理器
    def __init__(self, path: Path, timeout: float = 1.0, retry_interval: float = 0.05): ...
    def acquire(self) -> bool: ...    # False = 超时未获锁
    def release(self) -> None: ...
    def __enter__(self) -> "FileLock": ...
    def __exit__(self, *exc) -> None: ...

# lease.py
class Lease:
    def __init__(self, state_dir: Path, owner_id: str, ttl: float = 5.0,
                 renew_interval: float = 2.0): ...
    def try_acquire(self) -> bool: ...      # False = 已有活跃持有者
    def renew(self) -> bool: ...            # False = 已失去（owner 被抢）
    def is_active(self) -> bool: ...        # 当前 owner == 自己且未过期
    def current_owner(self) -> str | None: ...
    def release(self) -> None: ...
    @property
    def lease_path(self) -> Path: ...

# failover.py
class FailoverCoordinator:
    def __init__(self, lease: Lease, storage=None): ...
    def try_become_primary(self) -> bool: ...
    def is_primary(self) -> bool: ...
    def renew_primary(self) -> bool: ...
    def guard_write(self) -> None: ...      # 非主写 → raise NotPrimaryError
    def recover(self) -> str | None: ...    # 检测主过期 → 接管 → 返回新主 id

class NotPrimaryError(RuntimeError): ...
```

## 5. 验收

| # | 验收项 | 验证 |
|---|--------|------|
| HA-1 | FileLock 互斥（并发 acquire 仅一个成功） | test_ha.py |
| HA-2 | Lease 过期 → 副本接管 | test_ha.py |
| HA-3 | guard_write 非主写被拦截 | test_ha.py |
| HA-4 | 接管后 storage 续写零数据丢失 | test_ha.py（save 后 count 一致） |
| HA-5 | 431 全量回归 + GATE 8 5/5 | pytest + critic runner |
| HA-6 | 快照 v1.16.0 + 审计 AUDIT-0036 | 提交链 |

## 6. 明确不做（防蔓延）

- ❌ PostgreSQL 迁移（storage.py SQLite 强耦合，另立专项评估）
- ❌ Redis/etcd 分布式锁（单写者模型下无必要）
- ❌ 多活写（审计链一致性优先于可用性）
- ❌ 网络故障检测（本 Phase 仅进程级/本机级；跨机 HA 另立专项）

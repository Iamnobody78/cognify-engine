# Tester Report — TASK-REAL-002 (DEBT-0001 + DEBT-0008)

**Status**: ✅ COMPLETE — **R3 协调者兜底执行**（Tester 子代理 token 截断，0 writes；测试按 Tester 契约由 Coordinator 落盘并经 MCP 提交）

## Channel discipline
- 测试文件经 MCP write_file 落盘 + file_info 自证：
  tests/test_circuit_breaker.py **6458B**（重写，6 测试）· tests/test_storage_degraded.py **4749B**（新建，5 测试）
- 发现：sqlite3.Connection.execute 只读属性不可 patch.object → 改用 FakeConn 替换连接（测试设计修正）

## 测试清单
### tests/test_circuit_breaker.py（DEBT-0001，6 测试，重写自旧 4 测试）
| 测试 | 验证 |
|:--|:--|
| test_continuous_burst_still_trips | 10 次连续 ESCALATE → 第 10 次 403 DENY（保留旧语义） |
| test_trip_starts_cooldown | trip 后立即再发 → 403 DENY（**新契约核心**：旧代码允许立即重新累计） |
| test_cooldown_expires_and_recovers | 冷却过期后 → 202 ESCALATE（时间衰减恢复，非永久 stay-open） |
| test_distributed_trigger_accumulates | 9 次间隔 400s 的慢速触发 + 第 10 次 → **403 trip**（**替代旧 test_decay 的 202**——分散触发不可绕过） |
| test_allow_resets_counter | ALLOW 后计数归零（保留） |
| test_tripped_until_reset_on_allow | ALLOW 清除 breaker_tripped_until → 立即恢复 202 |

### tests/test_storage_degraded.py（DEBT-0008，5 测试，新建）
| 测试 | 验证 |
|:--|:--|
| test_save_success | 正常路径返回 id，pending==0 |
| test_save_failure_buffers_in_memory | 写失败不抛异常，返回 id，pending==1 |
| test_pending_entry_has_cached_at | 缓存条目含 ISO 时间戳 _cached_at |
| test_flush_pending_success | _init() 恢复连接后 flush==1，持久化可查 |
| test_flush_keeps_failed_entries | 仍失败时 flush==0，条目保留 |

## 测试优先裁决记录
- test_security_hardening.test_after_trip_counter_resets（旧: trip 后立即 202）与 DEBT-0001 新契约冲突 → 更新为"冷却期 DENY → 过期后 202"（测试以新契约为准）
- 旧 test_circuit_breaker.test_decay_prevents_breaker_trip_after_300s（旧: 间隔>300s 不累计→202）被 test_distributed_trigger_accumulates（新: 累计→403）**替换**——语义反转记录在案

## 验证
- 定向 pytest = **11 passed**（6+5）
- 全量回归 = **159 passed**

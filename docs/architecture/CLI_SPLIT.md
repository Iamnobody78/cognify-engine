# CLI 拆分设计 (v2.3.0) — cli/cognify.py 上帝模块渐进式拆分

> 状态: 已规划 (Sprint 66 收尾) | 目标版本: v2.3.0 | 原则: 渐进式, 零回归

## 问题

`cli/cognify.py` 当前 53KB, 承载 20+ 命令职责 (status/cert/plugin/benchmark/
self-validate/iterate/evolve/meta-call/meta-deploy/bootstrap/...), 违反单一职责。

## 目标结构

```
cli/
├── __init__.py
├── main.py                 # 仅入口路由 (~50 行)
└── commands/
    ├── __init__.py
    ├── status.py           # status
    ├── cert.py             # cert
    ├── plugin.py           # plugin
    ├── benchmark.py        # benchmark (+ full)
    ├── self_validate.py    # self-validate
    ├── iterate.py          # iterate
    ├── evolve.py           # evolve
    ├── meta_call.py        # meta-call
    ├── meta_deploy.py      # meta-deploy
    ├── meta_dev.py         # generate-status/bootstrap/self-analyze/audit-debt/debt-auto-create
    ├── dashboard.py        # generate-dashboard
    └── debt.py             # debt
```

## 拆分策略 (渐进式, 零回归)

1. **Phase 1 (骨架)**: 创建 `cli/commands/` + `__init__.py`, main.py 路由表
   (cmd → module.func 映射), 行为与 if-chain 完全等价
2. **Phase 2 (迁移)**: 按依赖度从低到高迁移命令:
   generate-dashboard → bootstrap → meta-call → iterate → evolve →
   benchmark → self-validate → meta-deploy → debt → plugin → cert → status
3. **Phase 3 (收敛)**: cli/cognify.py 瘦身为纯入口 (兼容旧路径), 删除重复逻辑

## 验收标准

- [ ] 所有现有命令行为不变 (每个命令前后输出 diff 一致)
- [ ] `python -m pytest tests/` 全绿 (当前 10 tests)
- [ ] `cognify cert` 30 维检查通过
- [ ] 新增命令可逐步加入 commands/, 无需改路由主体
- [ ] git 历史可逆 (每阶段独立提交, 失败可回滚)

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 导入路径变化破坏现有调用 | 保留 cli/cognify.py 兼容入口 (薄路由) |
| 大迁移引入回归 | 每阶段独立提交 + pytest + 命令冒烟清单 |
| 与 daemon 壳的耦合 | daemon/*.py 只调 CLI 命令名, 不依赖内部结构 |

## 完成定义

cli/cognify.py ≤ 200 行 (纯路由), commands/ 每文件 ≤ 300 行, pytest 全绿。

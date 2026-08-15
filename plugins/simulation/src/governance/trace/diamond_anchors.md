# 金刚石层（L0：不可触碰的锚点）

> 状态：HARD CONSTRAINT · 任何修改触及此处立即硬拦截并要求人类介入
> 存储形式：纯文本语义化约束（自然语言 + 数学逻辑），不存储任何可执行代码

## 5 条核心原则

| # | 原则 | 语义化约束 | 数学表达 |
| :--- | :--- | :--- | :--- |
| P1 | 主权不可让渡 | 最终仲裁权永远属于人类；代理的任何修改均可被人类否决 | `∃ H: ∀p ∈ proposals, H(p) ∈ {approve, reject}` |
| P2 | 认知必须可追溯 | 每个决策必须有证据链（commit hash + manifest + decision_log） | `∀d ∈ decisions: ∃e = evidence(d), e ≠ ∅` |
| P3 | 决策必须可回滚 | 任何变更必须有对应回滚方案（git revert / 版本快照） | `∀c ∈ changes: ∃r = rollback(c), r ∈ history` |
| P4 | 边界必须诚实声明 | 数据/模型/工具/认知四维边界透明 | `∀o ∈ outputs: boundary_statement(o) ≠ ∅` |
| P5 | 递归有界 | 递归层数 ≤ 3，锚点不可触碰，递归终止于人类 | `∀r ∈ recursion: depth(r) ≤ 3` |

## 递归边界

| 递归层级 | 内容 | 谁可修改 | 看门狗校验 |
| :--- | :--- | :--- | :--- |
| L0 | 锚点层（本文件） | ❌ 不可修改 | 硬拦截 |
| L1 | CVE-S 协议规则（MCE/VCE/CEE 实现） | ✅ 代理可提议修改 | 三闸门 |
| L2 | 工程规则库（engineering_rules.md） | ✅ 代理可自动修改 | 两闸门 |
| L3 | 知识库内容（knowledge_base/） | ✅ 代理可自动修改 | TRACE 记录 |

## 递归终止触发器

1. **硬停止**：修改被拒绝（触及 L0 时自动触发）
2. **降级**：若必须修改锚点层（如人类发现的缺陷），人类直接修改，代理不参与
3. **记录**：所有递归尝试被记录到 `governance/meta_evolution/meta_interventions.log`，作为审计证据

## 审计命令

```
python governance/trace/anti_drift_watchdog.py --check <target_file>   # 检查目标是否触及锚点
python governance/trace/anti_drift_watchdog.py --propose <proposal.json>  # 三闸门评估修改提案
python governance/trace/anti_drift_watchdog.py --history               # 查看修改历史
python governance/trace/anti_drift_watchdog.py --self-audit            # 元元监控报告
```

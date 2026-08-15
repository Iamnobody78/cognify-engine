# EVOLVE-SAFE v1.0 学术与工程支撑矩阵

> 按「论文 — 源码库 — 基准与数据库」三维度组织，为 D1-D7 七大安全进化维度提供三重支撑。
> 来源：用户提供（2026-08-13）。用途：安全进化护栏的学术锚点对齐，支撑治理栈安全层。

---

## 一、核心论文

| 维度 | 论文 | 出处 | 核心贡献 |
|:---|:---|:---|:---|
| D1 误进化检测 | Your Agent May Misevolve | ICLR 2026 | 揭示代理自我进化会"看起来更强、实际更弱"的误进化现象；提供误进化检测方法 |
| D2 对齐倾覆防御 | Alignment Tipping Process | — | 对齐度在进化过程中不是渐变而是"倾覆"（tipping）；需持续监测对齐度突变 |
| D3 反思质量 | Reflection-Bench | ICML 2025 | 独立度量代理自我反思质量；区分"真实认知"与"为过评估的表演" |
| D4 元智能体 | MetaAgent | arXiv:2508.00271, 2025 | 元智能体监督子代理的工具元学习；从最小工作流干中学 |
| D4 元智能体 | AIDE² | — | 自主智能体设计（Automated Agent Design）；元智能体自动设计/评估子代理 |
| D7 递归评估基准 | SWE-bench | — | 软件工程代理基准；递归评估的可靠度量 |

---

## 二、源码库

| 源码库 | 核心能力 | 维度支撑 |
|:---|:---|:---|
| MAREF | 多代理可靠性评估框架 | D1/D5 |
| SESG | 安全进化守护框架 | D1/D2 |
| CORD | 认知保留/灾难性遗忘防御 | D6 |
| ATP | 对齐倾覆防御协议 | D2 |
| coevolution-kernel | 共进化内核（攻击者-防御者博弈） | D2/D4 |
| meta-agent-challenge | 元智能体挑战基准 | D4/D7 |

---

## 三、基准与数据库

| 基准 | 核心用途 | 维度支撑 |
|:---|:---|:---|
| MAC | 多代理协作/攻击面评估 | D5 |
| Gaia2 | 通用代理能力（含安全边界）评估 | D1/D7 |
| ALE-Bench Lite | 自主 LLM 工程基准（轻量） | D7 |
| SWE-bench | 软件工程代理递归评估 | D7 |
| Reflection-Bench | 反思质量独立度量 | D3 |

---

## 四、EVOLVE-SAFE D1-D7 ↔ 学术对齐表

| 维度 | 核心论文 | 源码库 | 基准/数据库 |
|:---|:---|:---|:---|
| D1 误进化检测 | Your Agent May Misevolve (ICLR 2026) | SESG、MAREF | Gaia2 |
| D2 对齐倾覆防御 | Alignment Tipping Process | ATP、coevolution-kernel | — |
| D3 反思质量 | Reflection-Bench (ICML 2025) | — | Reflection-Bench |
| D4 元智能体 | MetaAgent、AIDE² | coevolution-kernel | meta-agent-challenge |
| D5 互操作性 | — | MAREF | MAC |
| D6 认知保留 | — | CORD | — |
| D7 递归评估基准 | SWE-bench | meta-agent-challenge | ALE-Bench Lite、SWE-bench |

---

## 五、总结

安全进化不是"进化之后补安全"，而是**进化本身必须在安全约束内发生**。该领域的核心洞察是：自我进化代理会"误进化"（ICLR 2026）、对齐会"倾覆"（Alignment Tipping Process）、反思会"表演"（Reflection-Bench）——因此安全必须是**进化循环的内建属性**（G.A.P.S. 五阶段），而非外部补丁。五条红线（R1-R5）把学术洞察转化为可执行、可度量的硬停止条件，使"安全进化"从概念落地为**可工程化、可审计、可递归验证的系统性护栏**。

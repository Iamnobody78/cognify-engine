# BottleSumo 旗舰版 — 系统架构概览

> **版本**: v11.11-IndustrialGrade | **日期**: 2026-07-31 | **状态**: 工具固化 + 熵断路器 + 评估者硬化(3层) + 四深水区(错误分类/回归/锁/因果)

---

## 架构总览 (9层 + Layer 0 执行宪法)

```
┌──────────────────────────────────────────────────────────────────────┐
│  Layer 0: 工作流层 (Workflow) — 执行宪法                           │
│  Universal Protocol: Understand → Design → Execute → Verify → Record │
│  Quality Gates: Gate 1 (设计通过) → Gate 2 (自审查) → Gate 3 (用户) │
├──────────────────────────────────────────────────────────────────────┤
│  Layer 1: Agent 治理层 (.aionui/)                                    │
│  核心指令 · 技能 · 热力学 · 元认知 · 债务 · 学习 · MCP平台记忆     │
├──────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────┬───────────────────────────────────┤ │
│  │  Layer 2-8: 硬件—物理        │  Layer 9: 软件研发               │ │
│  │  ┌──────────────────────────┐│  ┌───────────────────────────────┐│ │
│  │  │ Layer 8: AI 平台层       ││  │ 需求 → 设计 → 实现 → 测试    ││ │
│  │  │ Layer 7: 感知层(CV)      ││  │ → 文档                       ││ │
│  │  │ Layer 6: 决策层(DQN)     ││  │                               ││ │
│  │  │ Layer 5: 控制层(FreeRTOS)││  │ 软件质量门控:                 ││ │
│  │  │ Layer 4: 传感层(I2C/SPI) ││  │ ruff → mypy → pytest → 60%   ││ │
│  │  │ Layer 3: 驱动层(PWM)     ││  └───────────────────────────────┘│ │
│  │  │ Layer 2: 物理层(PCB/CAD) ││                                    │ │
│  │  └──────────────────────────┘│                                    │ │
│  └──────────────────────────────┴───────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────┤
│  Layer 10: 工具链层 (14层工具链)                                    │
│  PlatformIO + ARM GCC · KiCad · FreeCAD · Renode · Gazebo · PyTorch │
└──────────────────────────────────────────────────────────────────────┘
```

> ⚠️ **审计发现**: Python/config.py 使用 7→21 维度, C/dqn_weights.h 使用 16→11 维度 — 不一致。详见 `reports/decoupling_audit_v10.md`。

---

## Layer 0: 工作流层 (执行宪法) 🆕

### 通用执行协议 (Universal Protocol)

所有任务必须按以下5阶段执行，轻量任务可走快速通道。

| 阶段 | 名称 | 动作 | 输出 |
|:----:|------|------|------|
| **P1** | **Understand** | 任务重述 → 范围确认 → 依赖检查 → 知识加载 | 任务理解文档 (≤10行) |
| **P2** | **Design** | 2-3个方案 → 优缺点分析 → 选择理由 → 验收标准 | 方案选择文档 (≤20行) |
| **P3** | **Execute** | 分步实施 → 每步验证 → 增量提交 | 执行日志 |
| **P4** | **Verify** | 自测试 → 编译检查 → 回归检查 → 自审查报告 | 审查矩阵 |
| **P5** | **Record** | 更新 entropy.log → 更新 status → MCP 记忆同步 → 文档更新 | 更新记录 |

### 快速通道 (Lite Protocol)

简单任务（单次问答、信息查询、格式修正）可走 P1→P3→P5 三步即可，跳过 P2 设计和 P4 审查。

### 按任务类型的工作流变体

| 任务类型 | P2 设计 | P3 执行 | P4 验证 |
|----------|----------|----------|----------|
| **代码实现** | API设计 → 函数签名 → 实现计划 | TDD：先测试 → 再实现 | 单元测试 → 集成测试 |
| **硬件设计** | 原理图草案 → 器件选型 → 评审 | 原理图 → 布局 → 布线 → DRC | ERC → DRC → 制造检查 |
| **算法优化** | 基线 → 改进方案 → 预期收益 | 实现 → 基准测试 | A/B 对比 → 统计分析 |
| **架构决策** | 选项生成 → 权衡矩阵 → 推荐 | 决策文档 → 影响分析 | 实施计划 → 回滚方案 |
| **文档更新** | 变更点识别 → 影响范围 | 文档修改 → 交叉引用 | 一致性检查 → 链接验证 |
| **解耦重构** 🆕 | 扫描 → 优先级排序 → 方案提案 | 增量执行(逐模块) → 每步验证 | radon + pylint + pytest 回归 |

### 质量门控 (Quality Gates)

```
Gate 1: 方案通过 ──→ Gate 2: 自审查通过 ──→ Gate 3: 用户确认
    │                    │                      │
    ├─ 必须回答：        ├─ 7项检查是否全✅?    ├─ 重大变更触发
    │  "方案是否被批准？"│   ruff + mypy +      │  架构/硬件/算法变更
    │  否 → 回到设计     │   pytest + doc        │  否 → 调整或放弃
```

### MCP 记忆同步 (Phase 5 Record 必选动作) 🆕 v1.3 增强

```
每次优化/决策完成后，写入 MCP 工具写入平台记忆:
├── memory_create_entity(type="optimization-result|design-decision|bug-fix|pattern-discovered|lesson-learned", ...)
├── memory_add_observation(entity_id, observation) — 追加观测
└── memory_search(query="关键词") — 验证写入成功

会话启动时自动检索:
├── memory_search(query="bottlesumo") — 语义搜索
└── memory_list(type=...) ×4 — 加载各类型实体

知识类型映射:
├── 架构决策 → design-decision
├── 优化成果 → optimization-result
├── Bug修复 → bug-fix
├── 可复用模式 → pattern-discovered
└── 经验教训 → lesson-learned
```

---

## Layer 1: Agent 治理层

### 核心文件

| 文件 | 职责 |
|------|------|
| `core_instruction.md` | 核心行为规则 (不可变) |
| `solid/will/architecture_overview.md` | 本文件 |
| `solid/will/toolchain_will.md` | 工具链宪法 |
| `skills/bottlesumo-unified/SKILL.md` | 统一技能入口 |
| `debt/debt_registry.yaml` | 技术债务追踪 |
| `thermodynamics/entropy.log` | 操作审计日志 |
| `context/current_status.md` | 项目状态快照 |
| `learning/MEMORY.md` | 知识索引 |

### MCP 平台工具集

所有 Agent 自动继承 4 台 MCP 服务器（详见 `.aionui/mcp/servers.json`）：

| 服务器 | 工具数 | 状态 |
|--------|:-----:|:----:|
| chrome-devtools | 32 | ✅ |
| Platform Filesystem | 9 | ✅ |
| Platform Fetch (Python自研) | 2 | ✅ |
| Platform Memory (Python自研) | 7 | ✅ |

---

## Layer 9: 软件研发层 🆕

### 子层 1: 需求与设计 (Requirements & Design)

| 步骤 | 说明 |
|------|------|
| 功能需求文档 | 从用户描述提取，功能边界明确 |
| 接口设计 | 函数签名、类设计、配置文件变更 |
| 数据流设计 | 模块间依赖关系图 |
| 验收标准 | 可量化的完成条件 |

### 子层 2: 编码与实现 (Coding & Implementation)

| 规范 | 工具/标准 |
|------|-----------|
| 代码风格 | PEP8 (Python) / LLVM (C) |
| 模块化 | 单一职责、可测试、松耦合 |
| 错误处理 | 显式异常、结构化日志 |
| 性能 | O(n) 标注复杂度，关注热路径 |

### 子层 3: 测试与验证 (Testing & Validation)

| 类型 | 工具 | 门控 |
|------|------|:----:|
| Lint | `ruff check --fix` | **0 error** |
| 格式 | `ruff format` | **强制通过** |
| 类型 | `mypy` (Python 适用) | **强制通过** |
| 单元测试 | `pytest` | **通过 + ≥60%覆盖** |
| 集成测试 | `pytest` markers | **关键路径必须覆盖** |
| 回归测试 | CI 自动 | **PR 触发** |

### 子层 4: 文档与维护 (Documentation & Maintenance)

| 类型 | 标准 |
|------|------|
| Docstring | Google style: Args/Returns/Raises |
| API 文档 | 关键模块自动生成 |
| README | 新功能必须更新 |
| 变更日志 | 每次修改记录到 entropy.log |
| 架构文档 | 模块变更同步更新本文件 |

### 软件文档规范

```python
def function_name(param1: int, param2: str) -> bool:
    """
    函数功能描述（一句话）

    Args:
        param1: 描述
        param2: 描述

    Returns:
        描述

    Raises:
        ValueError: 何时抛出
    """
```

**所有新代码必须遵循上述规范。不满足规范的代码视为未完成。**

### 子层 5: 软件开发工具集 (Software Toolset) 🆕

**目的**: 为软件研发提供自动化基础设施，Agent 可在任务中自主调用。

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  子层 5: 软件开发工具集 (Software Toolset)                                │
│  ───────────────────────────────────────────────────────────────────────── │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │  本地自动化 (pre-commit)                                             │ │
│  │  ├── ruff check (lint) .................... 每次 commit 自动触发      │ │
│  │  ├── ruff format (格式化) ................. 每次 commit 自动触发      │ │
│  │  ├── mypy (类型检查) ...................... 每次 commit 自动触发      │ │
│  │  ├── bandit (安全扫描) .................... 每次 commit 自动触发      │ │
│  │  └── pytest (单元测试) .................... push 前自动触发            │ │
│  └───────────────────────────────────────────────��───────────────────────┘ │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │  远程自动化 (GitHub Actions CI)                                      │ │
│  │  ├── Lint & Format .................... Push/PR 触发                 │ │
│  │  ├── mypy 类型检查 .................... Push/PR 触发                 │ │
│  │  ├── Firmware Build ................... Push/PR 触发                 │ │
│  │  ├── pytest 单元测试 .................. Push/PR 触发                  │ │
│  │  ├── 覆盖率报告 (≥60%) ................ PR 触发                      │ │
│  │  └── 发布打包 ......................... Tag 触发                     │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │  开发工具链                                                            │ │
│  │  ├── 代码编辑: VS Code (WSL Remote) / Cursor                         │ │
│  │  ├── 版本控制: Git + GitHub                                          │ │
│  │  ├── 依赖管理: uv / pip + pyproject.toml 统一管理                     │ │
│  │  ├── 调试: pdb / logging                                             │ │
│  │  └── 文档生成: pdoc / Sphinx (CI 自动)                               │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │  Agent 调用接口                                                       │ │
│  │  ├── 编写代码 → 自动触发 pre-commit (ruff + mypy)                    │ │
│  │  ├── 提交代码 → CI 自动运行 (lint + test + build)                    │ │
│  │  ├── 查看结果 → 读取 CI 报告 / pre-commit 输出                       │ │
│  │  └── 修复问题 → 返回代码修改 → 重新提交                               │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

| 类别 | 工具 | 用途 | 自动化集成方式 |
|------|------|------|---------------|
| **代码编辑** | VS Code (WSL Remote) / Cursor | 代码编写、编辑 | 由 Agent 调用 `code` 命令 |
| **版本控制** | Git | 提交、分支、PR | 预提交钩子 + CI |
| **CI/CD** | GitHub Actions | 自动构建、测试、部署 | 工作流文件 (`.github/workflows/ci.yml`) |
| **代码质量** | ruff (lint + format) | 代码检查、格式化 | pre-commit + CI |
| **类型检查** | mypy | Python 类型验证 | pre-commit + CI |
| **安全扫描** | bandit | Python 漏洞检测 | pre-commit + CI |
| **单元测试** | pytest | 测试驱动开发 | pre-push + CI (≥60%覆盖) |
| **依赖管理** | uv / pip + `pyproject.toml` | 依赖锁定、版本管理 | 统一由 `pyproject.toml` 管理 |
| **调试** | pdb / logging | 运行时调试 | 代码内置日志 |
| **解耦分析** 🆕 | radon / pylint / vulture / pydeps / import-linter | 圈复杂度 + 耦合度 + 死代码 + 依赖图 | pre-commit + CI |
| **文档生成** | pdoc / Sphinx (可选) | API 文档自动生成 | CI 触发 |

---

## Layer 8: AI 平台层

> **评估日期**: 2026-07-27 | **完整报告**: `reports/platform_decision_report.md`

### 已接入

| 平台 | 状态 | 用途 | 费用 |
|------|:----:|------|:---:|
| **SenseCraft AI** | ✅ 已接入 | YOLO 模型优化 → NCNN/INT8 量化, Pi 端加速 | 免费 |

### 观察中 (观察期 2 周)

| 平台 | 状态 | 用途 | 阻塞条件 |
|------|:----:|------|----------|
| **Embedder** | ⚠️ 观察 | 数据手册 → STM32 驱动代码生成 | 需注册试用, 验证准确率 |
| **CodeFusion Studio 2.0** | ⚠️ 观察 | 模型性能分析, 功耗监控 | 需验证 STM32 兼容性 |

### 已拒绝

| 平台 | 理由 |
|------|------|
| AutoEmbed | 端到端黑箱, 与 PlatformIO 管线冲突 |
| MPLAB AI | Microchip 生态, STM32 零兼容 |
| DevHard AI | 课程绑定模型不透明 |

### SenseCraft AI 工作流

```
yolo26n.pt (PyTorch, FP32, ~12MB)
  │  → 上传到 https://sensecraft.seeed.cc
  │  → 选择目标: Raspberry Pi 4B
  │  → 优化: INT8 量化 + NCNN 加速
  ▼
yolo26n_optimized/ (NCNN, INT8, ~3MB)
  │  → 复制到 vision/
  │  → vision_node.py 配置 backend="ncnn"
  ▼
Pi 4B 推理: 25-30 FPS (vs 8-12 FPS PyTorch)
```

### 性能基准

```bash
# 运行对比测试
python tools/benchmark_yolo_pi.py --model vision/yolo26n.pt --backend all --json
```

| 后端 | 帧率 (预估 Pi 4B) | 模型大小 |
|------|:---:|:---:|
| PyTorch | 8-12 FPS | 12 MB |
| ONNX Runtime | 12-18 FPS | 12 MB |
| OpenCV DNN | 15-20 FPS | 12 MB |
| **NCNN (SenseCraft)** 🏆 | **25-30 FPS** | **3 MB** |

---

## Layer 7: 感知层 (Vision)

### 组件

| 组件 | 文件 | 行数 | 状态 |
|------|------|:---:|:----:|
| AdaptiveCalibrator | `vision/calibrator.py` | 259 | ✅ |
| BottleDetector (YOLO+HSV) | `vision/detector.py` | 295 | ✅ |
| SemanticAnalyzer | `vision/semantic.py` | 280 | ✅ |
| VisionUART / VisionPacket | `vision/communication.py` | 230 | ✅ |
| VisionNode (主循环) | `vision/vision_node.py` | 395 | ✅ |
| Module Init | `vision/__init__.py` | 35 | ✅ |

### 数据流

```
Camera (640×480@30fps)
  │
  ▼
AdaptiveCalibrator.apply()
  ├─ CLAHE (clip_limit from calibration)
  ├─ Gamma correction (from calibration)
  └─ → Preprocessed frame
        │
        ▼
BottleDetector.detect()
  ├─ YOLO26n (primary): class 0=bottle, class 1=robot
  └─ HSV background subtraction (fallback)
        │
        ▼
SemanticAnalyzer.update()
  ├─ Trajectory tracking (60-frame buffer)
  ├─ Contact detection (IoU overlap)
  ├─ Push classification (active/passive/accidental)
  └─ → ContactAssessment
        │
        ▼
VisionUART.send(VisionPacket)
  │ Header: 0xCC | opp_x/y | bottle_x/y | bottle_pose | contact | push_type | distance | CRC8
  │ 10 bytes @ ~30Hz
  ▼
STM32F407 UART3 RX → 11-dim observation expansion
```

### 通信协议

| Byte | Field | Range | Description |
|:----:|-------|:-----:|-------------|
| 0 | Header | 0xCC | Packet start marker |
| 1 | opp_x | 0-255 | Opponent center X (normalized) |
| 2 | opp_y | 0-255 | Opponent center Y (normalized) |
| 3 | bottle_x | 0-255 | Our bottle center X |
| 4 | bottle_y | 0-255 | Our bottle center Y |
| 5 | bottle_pose | 0-15 | Bottle rotation (16 discrete) |
| 6 | contact | 0/1 | Contact flag |
| 7 | push_type | 0-4 | PushTypeUART enum |
| 8 | distance | 0-255 | Normalized distance |
| 9 | CRC8 | 0-255 | Error detection |

---

## Layer 6: 决策层

### DQN 模型

| 模型 | 架构 | 参数量 | 胜率 | 部署 |
|------|------|:-----:|:----:|:----:|
| V10 BayesOpt | 7→128→128→128→21 | 36,757 | 98.9% | 仿真 |
| Nano Student | 7→16→16→21 | 757 | 92.5% | 候选 |
| V11 CV-Aware | 11→128→128→128→21 | 38,000± | — | 规划中 |

### 11 维观测向量 (CV 扩展后)

| Dim | 名称 | 来源 | 范围 |
|:---:|------|------|:---:|
| 0 | 前端 ToF 距离 | F103 SPI | 0-2000mm |
| 1 | 左前 ToF 距离 | F103 SPI | 0-2000mm |
| 2 | 右前 ToF 距离 | F103 SPI | 0-2000mm |
| 3 | 左侧 ToF 距离 | F103 SPI | 0-2000mm |
| 4 | 右侧 ToF 距离 | F103 SPI | 0-2000mm |
| 5 | IMU 角速度 Z | F103 SPI | -2000~2000°/s |
| 6 | IMU 加速度 X | F103 SPI | -4~4g |
| 7 | 🆕 对手X (视觉) | Pi UART | 0-1 norm |
| 8 | 🆕 对手Y (视觉) | Pi UART | 0-1 norm |
| 9 | 🆕 接触状态 | Pi UART | 0/1 |
| 10 | 🆕 距离 (视觉) | Pi UART | 0-1 norm |

---

## Layer 5: 控制层

### FreeRTOS 任务

| 任务 | 优先级 | 周期 | 功能 |
|------|:------:|:----:|------|
| DecisionTask | 3 | 20ms | DQN推理 / 规则引擎 |
| ControlTask | 4 | 5ms | PID速度控制 |
| SensorTask | 2 | 10ms | SPI读取传感器 |
| VisionTask 🆕 | 2 | 33ms | UART3读取视觉包 |
| SafetyTask | 5 | 1ms | 边缘检测 + 紧急停止 |

---

## Layer 4: 传感层

### F103 Aux MCU

- VL53L4CD ×7: I2C 地址复用 (TCA9548A)
- MPU6050: I2C, 200Hz
- DRV2605L ×2: I2C, 触觉反馈
- SPI Bridge: F103↔F407, 500kHz

---

## Layer 3-2: 驱动层 & 物理层

### 驱动

- DRV8833 ×2: PWM 20kHz, 4通道
- N20 200rpm ×4: 编码器反馈
- WS2812B ×16: SPI DMA驱动

### 物理规格 (CTEA Advanced Group)

- 总重: <2kg
- 尺寸: 250×250×300mm (含 bottle)
- 电池: 2S 18650 (7.4V nominal)
- 底盘: PETG 3D打印

---

## 工具链

| 工具 | 版本 | 用途 |
|------|------|------|
| Python | 3.12 | 仿真/训练/视觉 |
| OpenCV | 4.13 | 图像处理 |
| Ultralytics | 8.4 | YOLO26n 推理 |
| PyTorch | 2.13 | DQN 训练 |
| ARM GCC | 14.2.1 | 固件编译 |
| PlatformIO | 6.1 | 固件构建系统 |
| KiCad | 8.0 | PCB 设计 |
| FreeCAD | 1.0 | 3D 建模 |
| Renode | 1.15 | 固件仿真 |
| PySerial | 3.5 | UART 通信 |
| ruff | — | Python lint/format (Layer 9) |
| mypy | — | Python 类型检查 (Layer 9) |
| pytest | — | Python 测试 (Layer 9) |
| radon 🆕 | — | 圈复杂度/可维护性分析 (Layer 9) |
| pylint 🆕 | — | 代码质量评分 + 耦合检测 (Layer 9) |
| vulture 🆕 | — | 死代码检测 (Layer 9) |
| pydeps 🆕 | — | 模块依赖图 (Layer 9) |

> 完整清单见 `tools/installed.md` (auto-generated by `tool_version_manager.py`)

---

## 项目目录结构

```
bottlesumo_pi/
├── vision/                    # CV 感知层
│   ├── __init__.py
│   ├── calibrator.py          # 自适应标定
│   ├── detector.py            # YOLO+HSV检测
│   ├── semantic.py            # 语义分析 (推搡判定)
│   ├── communication.py       # UART 协议
│   └── vision_node.py         # 主循环
├── firmware/
│   └── stm32_mcu/
│       ├── src/
│       │   ├── main_rule_fallback.c
│       │   ├── spi_protocol.h
│       │   └── ...
│       └── platformio.ini
├── simulation/
│   ├── lightweight_env.py
│   ├── wheel_to_discrete.py
│   └── evaluation/
├── models/
│   ├── v10_bayesopt_dqn.pt
│   └── nano_student.pt
├── tools/
│   ├── tool_version_manager.py  # 依赖扫描器
│   ├── install_cv_deps.sh       # 自动安装脚本
│   └── installed.md             # 工具清单
├── cad/
├── reports/
│   └── failure_analysis.md
└── tests/
    ├── test_vision/
    ├── test_simulation/
    └── test_firmware/
```

---

## 关键风险

| 风险 | 等级 | 缓解措施 |
|------|:----:|----------|
| YOLO26n Pi 4B 推理延迟 | 🟡 | HSV 回退、帧率自适应 |
| 未知道场颜色 | 🟡 | AdaptiveCalibrator 90帧学习 |
| UART 丢包 | 🟢 | CRC8校验 + 丢帧插值 |
| F407 SPI+UART 并发 | 🟡 | FreeRTOS 独立任务 + DMA |
| F103 RAM 不足 | 🔴 | Nano模型压缩 + 蒸馏 |
| 测试覆盖率低 | 🟡 | Layer 9 软件质量门控强制要求 |

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v11.11 | 2026-07-31 | [工业级基础设施] 工具固化引擎(10次阈值→编译为.py) + 熵断路器(连续3次Δ<0.01→熔断) + 评估者硬化(硬断言/双盲/入库门控) + 四深水区(错误分类器/回归自扩增/并发锁/因果图谱) — 14文件 |
| v11.7 | 2026-07-31 | [验证架构] 5层验证金字塔 (语法→一致性→集成→投影→消融), 12消融实验 (ABL-001~012), 10元架构设计规则 (ARCH-001~010), validate_consistency.py + run_ablation.py |
| v11.6 | 2026-07-31 | [价值防线] 退火调度器 (temperature_scheduler.py 80行), 价值对齐审计 (value_alignment_auditor.py 8公理), 契约自愈+动态信任梯度占位 |
| v11.5 | 2026-07-31 | [闭环进化] Badcase 自动回流 (5捕获信号), 探索控制 (停滞检测+温度调控), 记忆GC策略, 计算ROI策略 |
| v11.4 | 2026-07-30 | [投影闭环+元状态] Shadow Loop全流程 (IDLE→OBSERVE→PROPOSE→EVALUATE→COMMIT/ROLLBACK), Golden评测阵, Godelian熔断钩子, 状态快照+结晶化 |
| v11.3 | 2026-07-30 | [元组织+元分析] 5角色/8决策域/5应激模式, 4可信度因子/5偏差/6盲点, 标准化分析报告模板 |
| v11.2 | 2026-07-30 | [元哲学+元模型] Layer -1 哲学基础 (7存在论/6知识可信度层级/5价值层级/7方法论), Layer 0 模型分类/生命周期/关系/评估 |
| v11.1 | 2026-07-30 | [高阶元能力] 元物件动态Schema引擎, 元数据血缘追踪, 元性能自监控, 元安全威胁感知, 元架构资源对账 |
| v11.0 | 2026-07-30 | [元系统] 自我身份描述, 生存条件检测, 完整性校验, 自愈策略库, 终止计划 |
| v10.9 | 2026-07-29 | [全维度元能力] 10维度: 监控/依赖/测试/决策/设计/知识/学习/演化/风险/变更, 全栈元反思完成 |
| v10.4 | 2026-07-28 | 🆕 架构自解耦协议 (Self-Decoupling Protocol): 6步流程 (扫描→排序→提案→执行→验证→回滚), 5个解耦工具集成, CI 质量门控 |
| v10.3 | 2026-07-28 | 🆕 MCP记忆桥整合 (Phase 5增强: 知识类型映射+验证+启动检索), core_instruction.md v1.3 FinalIntegration |
| v10.3 | 2026-07-27 | 🆕 Layer 9 子层 5: 软件开发工具集 (pre-commit + CI + Agent调用接口), pre-commit 扩展 mypy/pytest, CI 扩展类型检查+覆盖率 |
| v10.2 | 2026-07-27 | 🆕 Layer 0 工作流层 (Universal Protocol + Quality Gates), Layer 9 软件研发层 (4子层), MCP 平台记忆桥接 |
| v10.1 | 2026-07-27 | AI 平台评估: SenseCraft ✅, Embedder ⚠️, 其余拒绝 |
| v10.0 | 2026-07-27 | P0 解耦: core/hal/ + obs_action_config.yaml SSOT + spi_protocol.h vision扩展 |

---

*维护者: BottleSumo Governance Agent | 随架构演化自动同步*
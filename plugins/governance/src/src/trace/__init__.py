"""src.trace — MH-1 完整执行轨迹捕获（Meta-Harness 文件系统真相层）。

原则（斯坦福 Meta-Harness）:
  - 冻结模型，进化 harness: 轨迹是 harness 进化的唯一反馈
  - 完整执行轨迹: 每步落盘（manifest.json + steps/NNN_*.json + artifacts/），
    进程崩溃不丢失; 最多 10M token 反馈预算 → token_estimate 裁剪
  - 文件系统是唯一真实来源: 轨迹即文件，任何工具可读

组成:
  store.TraceStore    文件系统持久化（create/append_step/add_artifact/finalize/load/list）
  capture.TraceCapture 上下文管理器（异常自动标记 failed）
  capture.capture_run  函数包装（记录返回值/异常）
  capture.traced       装饰器（@traced(store) 自动捕获）
"""

from .store import SCHEMA_VERSION, Trace, TraceStep, TraceStore, token_estimate
from .capture import TraceCapture, capture, capture_run, traced

MH1_VERSION = "1.0.0"

__all__ = [
    "SCHEMA_VERSION", "Trace", "TraceStep", "TraceStore", "token_estimate",
    "TraceCapture", "capture", "capture_run", "traced", "MH1_VERSION",
]

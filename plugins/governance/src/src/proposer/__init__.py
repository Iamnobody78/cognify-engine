"""src.proposer — MH-2 提议器（文件系统变异算子）。

原则（斯坦福 Meta-Harness）:
  - 提议者 = 变异算子: 读取历史轨迹（reader）→ 生成完整候选 harness
    （writer, candidates/{candidate_id}/src/）
  - 完整候选而非补丁: 候选持有可独立运行的完整文件树
  - 血缘可溯: candidate.json 记录 parent_trace_id（变异来源）
  - 文件系统唯一真相: candidates/ 即候选库（.gitignore 忽略）

组成:
  reader.TraceReader   只读检索（read/list/search/grep/cat + 10M token 预算）
  writer.CandidateWriter 候选写入（create/write_source/write_tree/import_trace_artifacts/finalize）
"""

from .reader import TraceReader
from .writer import CANDIDATES_REL, Candidate, CandidateWriter

MH2_VERSION = "1.0.0"

__all__ = ["TraceReader", "CandidateWriter", "Candidate", "CANDIDATES_REL",
           "MH2_VERSION"]

"""InstrumentBench 判分器内核。

模块布局（v0.1 目标）：

- ``snapshot.py``  数据契约（已就绪）
- ``evaluator.py`` 流式评估器：build_evaluator / reset_episode / update / finalize（挂主线 T4 判分器交付实现）
- ``batch.py``     离线批量判卷：evaluate_episode / evaluate_batch（同上）

硬约束：本包禁止 import torch / omni / pxr / isaacsim（纯 CPU、可离线、可单测）；
评估器只消费 :class:`judge.snapshot.EnvSnapshot`，不感知任何仿真框架。
"""
from judge.snapshot import CSV_COLUMNS, EnvSnapshot, EpisodeResult, FAIL_CODES, MetricEvidence

__all__ = [
    "EnvSnapshot",
    "EpisodeResult",
    "MetricEvidence",
    "CSV_COLUMNS",
    "FAIL_CODES",
]

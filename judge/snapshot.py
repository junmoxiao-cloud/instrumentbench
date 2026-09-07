"""InstrumentBench 判分器数据契约（EnvSnapshot / EpisodeResult）。

本模块是"判分器与仿真解耦"的边界层：

- sim 侧适配器把 USD/PhysX 状态读成 :class:`EnvSnapshot` 喂给评估器；
- 评估器只消费 EnvSnapshot，产出 :class:`EpisodeResult`；
- EpisodeResult 是所有下游（CSV 报告 / JSON 管线 / RAFT 奖励 / 人工复核）的唯一数据源。

硬约束：本模块只允许标准库，禁止 import torch / omni / pxr / isaacsim
（纯 CPU、可离线回放、可在无仿真的进程中单测）。
"""
from __future__ import annotations

import datetime
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

# ---------------------------------------------------------------------------
# 失败码（与 docs/failure-taxonomy.md 保持一致；修改必须同步文档并递增 schema 版本）
# ---------------------------------------------------------------------------

SUCCESS_REASON = "success"

FAIL_CODES: dict[str, str] = {
    "F0": "sensor_or_judge_error",      # 传感器/判分器异常（工具故障）
    "F1": "grasp_failed",               # 抓取失败（掉落/倾斜超限，粘滞）
    "F2": "placement_off_target",       # 放置偏移（曾进入成功区域但保持不足）
    "F3": "device_state_not_met",       # 设备状态未达成
    "F4": "timeout_or_interrupted",     # 流程中断/超时（兜底）
}

FAIL_CLASSES: dict[str, str] = {
    "F0": "工具故障（不计入任务统计，修复后重跑）",
    "F1": "抓取失败",
    "F2": "放置偏移",
    "F3": "设备状态未达成",
    "F4": "流程中断/超时",
}

# CSV 输出列：前四列为稳定契约（调用方按列名引用），扩展列只许追加不许插入/改名
CSV_COLUMNS: tuple[str, ...] = (
    "task_id",            # 任务 ID
    "episode_id",         # 全局唯一；重复判分覆盖而非追加（幂等由调用方保证）
    "success",            # 0/1
    "fail_reason",        # success | F0..F4
    "fail_class",         # 可读大类（报告用）
    "criterion_version",  # 判据版本（可追溯）
    "elapsed_s",          # episode 时长
    "judged_at",          # 判分时刻（UTC ISO8601）
)


# ---------------------------------------------------------------------------
# 输入侧：状态快照
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EnvSnapshot:
    """单个仿真步的状态快照（判分所需最小集）。

    结构：``sources[source_name][metric_name] = float | None``

    填充约定由任务 YAML 的 ``metrics_sources.kind`` 决定，sim 侧适配器负责：

    - ``rigid_pose``  → ``{"x": ..., "y": ..., "z": ..., "tilt_deg": ...}``
      （世界系；tilt 为相对 episode 开局基线的倾角，度）
    - ``joint_angle`` → ``{"joint_angle_deg": ...}``
      （适配器按 YAML 声明的 ``unit`` 换算成度后填充）
    - ``bbox_circle`` → 作为 ``target_source`` 被引用，**reset 时**由适配器解析：
      ``{"center_x": ..., "center_y": ..., "radius": ...}``

    指标缺失（传感器/读取失败）时，对应键必须**存在且值为 None**——
    这是 F0（工具故障）判定的依据；整个键缺失视为适配器 bug。
    """

    t: float  # 仿真时间戳（秒，episode 内单调递增）
    sources: Mapping[str, Mapping[str, float | None]]

    def metric(self, source: str, name: str) -> float | None:
        """读取某 source 的某指标；source 或键缺失视为适配器 bug（调用方应显式判 F0 之前保证结构）。"""
        try:
            return self.sources[source][name]
        except KeyError:
            return None


# ---------------------------------------------------------------------------
# 输出侧：判分结果
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MetricEvidence:
    """单条判据的终局证据（自证：实际值 vs 阈值，人工复核无需回放）。

    ``actual``/``passed`` 为 None 表示该指标缺失（对应 F0）。
    """

    metric: str
    op: str          # ">", ">=", "<", "<=", "==", "in_range"
    spec: str        # 人读阈值描述，如 "> -46.0" / "in [0.63, 0.73]" / "auto r=0.05"
    actual: float | None
    passed: bool | None


@dataclass
class EpisodeResult:
    """一条 episode 的判分终局结果（所有下游的唯一数据源）。"""

    task_id: str
    episode_id: str
    success: bool
    fail_reason: str                       # "success" | F0..F4（见 FAIL_CODES）
    fail_class: str                        # 可读大类（报告用）
    metrics: list[MetricEvidence]          # 终局证据集
    per_step_success: list[bool]           # 逐帧"处于成功区域"标记（RAFT reward_classifier 的标签源）
    hold_s_achieved: float                 # 实际最长连续保持时长（秒）
    criterion_version: int                 # 判据版本，任何报告可追溯
    elapsed_s: float                       # episode 时长（秒）
    judged_at: str = field(                # 判分时刻（UTC ISO8601）
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    )

    # ---- 输出契约：CSV（人看/报告引用）与 JSON（机器消费）同源同版本 ----

    def csv_row(self) -> dict[str, Any]:
        """按 CSV_COLUMNS 顺序输出一行；success 编码为 0/1。"""
        return {
            "task_id": self.task_id,
            "episode_id": self.episode_id,
            "success": int(self.success),
            "fail_reason": self.fail_reason,
            "fail_class": self.fail_class,
            "criterion_version": self.criterion_version,
            "elapsed_s": round(self.elapsed_s, 3),
            "judged_at": self.judged_at,
        }

    def to_json_dict(self) -> dict[str, Any]:
        """全量结构化输出（含证据与逐帧标记），供训练管线 / 增广报告 / RAFT 消费。"""
        return asdict(self)

    def fail_class_label(self) -> str:
        """失败码 → 可读大类；成功或未知码返回空串。"""
        return FAIL_CLASSES.get(self.fail_reason, "")

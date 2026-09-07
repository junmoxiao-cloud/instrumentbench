"""判分器行为契约测试：13 个合成轨迹用例（不启动任何仿真）。

运行方式::

    pytest tests/ -v

当前状态：`judge.evaluator` 尚未实现（挂主线 T4 判分器交付），整个模块
importorskip 跳过；实现落地后本文件应**全部转绿**——转绿即代表判据语义
（hold_timer / latch / sticky / F0–F4 / 边界）与 docs/judge-schema.md 一致。

对 evaluator 实现者的接口要求（契约）：

    build_evaluator(config: dict | os.PathLike) -> evaluator 实例
    instance.reset_episode(snapshot: EnvSnapshot) -> None    # 捕获基线、解析 bbox_circle 目标
    instance.update(snapshot: EnvSnapshot, dt_s: float) -> None  # 每步 O(1)
    instance.finalize() -> EpisodeResult                     # O(1) 汇总

    # config 为 dict 时语义与同结构 YAML 文件完全一致（schema 见 docs/judge-schema.md）
"""
from __future__ import annotations

import pytest

# judge.evaluator 挂主线 T4 交付实现；实现前整个模块跳过，落地后自动启用
evaluator = pytest.importorskip(
    "judge.evaluator",
    reason="judge.evaluator 将随主线 T4 判分器交付实现；本文件是用例契约，实现后应全绿",
)

from cases import CASES, DT  # noqa: E402  (conftest.py 已处理 sys.path)


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_evaluator_case(case):
    ev = evaluator.build_evaluator(case["config"])
    steps = case["steps"]

    ev.reset_episode(steps[0])
    for snap in steps:
        ev.update(snap, DT)
    result = ev.finalize()

    assert result.success == case["expect"]["success"], (
        f"[{case['name']}] success={result.success}, fail_reason={result.fail_reason}, "
        f"evidence={result.metrics}"
    )
    assert result.fail_reason == case["expect"]["fail_reason"], (
        f"[{case['name']}] expected fail_reason={case['expect']['fail_reason']}, "
        f"got {result.fail_reason}"
    )
    # 架构契约：逐帧标记与输入帧数一致；成功时 fail_reason 固定为 "success"
    assert len(result.per_step_success) == len(steps)
    if result.success:
        assert result.fail_reason == "success"
    # 证据自证契约：终局必须携带至少一条 MetricEvidence（实际值 vs 阈值）
    assert len(result.metrics) >= 1
    # 版本可追溯契约
    assert result.criterion_version == case["config"]["criterion_version"]

"""合成轨迹用例集 —— 不启动任何仿真，手工构造 EnvSnapshot 序列穷举判据语义。

本文件是 evaluator 的**行为契约**：
- 每个用例 = （评估器配置 dict, EnvSnapshot 序列, 期望终局）；
- 用例命名即语义，T4 实现者对照 docs/judge-schema.md §6（语义细则）实现；
- 全部用例基于两个标准任务配置：place_tube_on_balance（放置类）与
  close_centrifuge_lid（关节角类），数值与 schema §9 示例一致。

帧数语义（dt=0.1s，均经手工核对）：
- place 任务 hold_s=1.0 → 需连续 ≥10 帧在区（其中进入区域的首帧若
  z_step_delta > 0.002 不计入，故"到达后静止 N 帧"的有效保持 = (N-1)*dt）；
- obj_z_step_delta 为相邻帧 z 变化量的绝对值；
- obj_tilt_deg 由适配器按"相对开局基线"填充，合成轨迹直接给出增量值。
"""
from __future__ import annotations

from judge.snapshot import EnvSnapshot

DT = 0.1

# bbox_circle source 在 reset 时由适配器解析好的目标区域几何（合成轨迹直接给定）
_BALANCE = {"balance_plate": {"center_x": 0.5, "center_y": 0.0, "radius": 0.05}}


def _tube(x: float, y: float, z: float, tilt_deg: float = 0.0, missing: bool = False) -> dict:
    """构造一个 tube + balance_plate 的 sources dict。missing=True 时 tube 指标全部 None（模拟读取失败）。"""
    if missing:
        return {"tube": {"x": None, "y": None, "z": None, "tilt_deg": None}, **_BALANCE}
    return {"tube": {"x": x, "y": y, "z": z, "tilt_deg": tilt_deg}, **_BALANCE}


def _lid(angle_deg: float, missing: bool = False) -> dict:
    if missing:
        return {"lid_revolute": {"joint_angle_deg": None}}
    return {"lid_revolute": {"joint_angle_deg": angle_deg}}


def _traj(*sources_steps: dict) -> list[EnvSnapshot]:
    return [EnvSnapshot(t=i * DT, sources=s) for i, s in enumerate(sources_steps)]


# ---------------------------------------------------------------------------
# 标准任务配置（与 docs/judge-schema.md §9 示例一致；latch 参数化用于 A/B 对照）
# ---------------------------------------------------------------------------

def place_config(latch: bool) -> dict:
    return {
        "task_id": "place_tube_on_balance",
        "language_instruction": "place the tube on the balance",
        "criterion_version": 1,
        "timeout_s": 2.5,
        "criterion": {
            "hold_s": 1.0,
            "latch": latch,
            "conditions": [
                {"metric": "xy_distance_to_target", "source": "tube",
                 "target_source": "balance_plate", "op": "<=", "value": "auto",
                 "target_radius_scale": 1.0},
                {"metric": "obj_z", "source": "tube", "op": "in_range",
                 "min": 0.63, "max": 0.73},
                {"metric": "obj_z_step_delta", "source": "tube", "op": "<=", "value": 0.002},
            ],
        },
        "metrics_sources": {
            "tube": {"kind": "rigid_pose", "prim_path": "/World/tube", "unit": "m"},
            "balance_plate": {"kind": "bbox_circle", "prim_path": "/World/plate", "unit": "m"},
        },
        "failure_rules": [
            {"id": "F0", "when": "metric_missing"},
            {"id": "F1", "sticky": True, "conditions_any": [
                {"metric": "obj_z", "source": "tube", "op": "<", "value": 0.20},
                {"metric": "obj_tilt_deg", "source": "tube", "op": ">", "value": 35.0,
                 "ref": "initial"},
            ]},
            {"id": "F2", "when": "entered_region_without_hold"},
            {"id": "F4", "default": True},
        ],
    }


LID_CONFIG = {
    "task_id": "close_centrifuge_lid",
    "language_instruction": "close the centrifuge lid",
    "criterion_version": 1,
    "timeout_s": 2.0,
    "criterion": {
        "hold_s": 0.25,
        "latch": True,
        "conditions": [
            {"metric": "joint_angle_deg", "source": "lid_revolute", "op": ">", "value": -46.0},
        ],
    },
    "metrics_sources": {
        "lid_revolute": {"kind": "joint_angle", "prim_path": "/World/lid", "unit": "deg"},
    },
    "failure_rules": [
        {"id": "F0", "when": "metric_missing"},
        {"id": "F3", "default": True},
    ],
}


# ---------------------------------------------------------------------------
# 轨迹构造
# ---------------------------------------------------------------------------

def _approach_then_hold(hold_frames: int) -> list[dict]:
    """从远处接近到盘上 (0.5, 0, 0.68) 并静止 hold_frames 帧（首帧 delta 超差不计入保持）。"""
    steps = [_tube(0.20, 0.0, 0.80), _tube(0.35, 0.0, 0.76), _tube(0.44, 0.0, 0.72),
             _tube(0.50, 0.0, 0.68)]
    steps += [_tube(0.50, 0.0, 0.68) for _ in range(hold_frames)]
    return steps


def _golden() -> list[dict]:
    # 到达后静止 16 帧 → 有效保持 15 帧 = 1.5s >= 1.0s
    return _approach_then_hold(16)


def _hold_one_frame_short() -> list[dict]:
    # 有效保持 9 帧 = 0.9s < 1.0s，随后移出直至超时
    steps = _approach_then_hold(10)          # 步 3..12 含到达帧，有效 9 帧
    steps += [_tube(0.70, 0.0, 0.68) for _ in range(10)]
    return steps


def _boundary_equal() -> list[dict]:
    # z 恰好等于区间上界 0.73（闭区间 → 在区内），到达后静止 16 帧
    steps = [_tube(0.20, 0.0, 0.80), _tube(0.44, 0.0, 0.75), _tube(0.50, 0.0, 0.73)]
    steps += [_tube(0.50, 0.0, 0.73) for _ in range(16)]
    return steps


def _hold_then_lift() -> list[dict]:
    # 在区保持 1.3s（>1.0 达标），随后抬起离开区域直至结束 —— latch 语义对照轨迹
    steps = _approach_then_hold(13)
    steps += [_tube(0.50, 0.0, 0.85) for _ in range(3)]
    return steps


def _hold_too_short() -> list[dict]:
    # 在区仅 0.4s 后移出，直至超时
    steps = _approach_then_hold(5)
    steps += [_tube(0.65, 0.0, 0.68) for _ in range(15)]
    return steps


def _mid_air_drop() -> list[dict]:
    # 接近途中跌破高度线 0.20 → 粘滞 F1，此后不再恢复
    return [_tube(0.20, 0.0, 0.80), _tube(0.30, 0.0, 0.60), _tube(0.30, 0.0, 0.15),
            _tube(0.30, 0.0, 0.15)] + [_tube(0.30, 0.0, 0.15) for _ in range(18)]


def _tilt_over() -> list[dict]:
    # 途中倾角增量超 35° → 粘滞 F1
    steps = [_tube(0.20, 0.0, 0.80, 0.0), _tube(0.44, 0.0, 0.78, 10.0),
             _tube(0.46, 0.0, 0.80, 40.0)]
    steps += [_tube(0.46, 0.0, 0.80, 40.0) for _ in range(18)]
    return steps


def _never_approach() -> list[dict]:
    # 全程远离目标区域 → F4 兜底
    return [_tube(0.10, 0.10, 0.30) for _ in range(25)]


def _jitter() -> list[dict]:
    # 高频进出：每 3 帧切换在区/出区，单段连续保持最长 0.3s < 1.0s → F2
    steps: list[dict] = []
    for i in range(25):
        steps.append(_tube(0.50, 0.0, 0.68) if (i // 3) % 2 == 0 else _tube(0.62, 0.0, 0.68))
    return steps


def _metric_missing() -> list[dict]:
    # 中途指标读取失败 → F0（工具故障，优先级最高）
    return [_tube(0.20, 0.0, 0.80), _tube(0.35, 0.0, 0.76), _tube(0.44, 0.0, 0.72),
            _tube(0, 0, 0, missing=True), _tube(0, 0, 0, missing=True),
            _tube(0, 0, 0, missing=True)]


def _lid_never_meets() -> list[dict]:
    # 关节角全程 -60（< -46 阈值）→ F3
    return [_lid(-60.0) for _ in range(20)]


def _lid_golden() -> list[dict]:
    # 关闭到位：-60 → -40（> -46 进入成功区域）并保持 0.5s >= 0.25s → success
    return [_lid(-60.0), _lid(-60.0), _lid(-60.0), _lid(-40.0),
            _lid(-40.0), _lid(-40.0), _lid(-40.0), _lid(-40.0)]


# ---------------------------------------------------------------------------
# 用例注册表：(name, config, steps, expected{success, fail_reason})
# ---------------------------------------------------------------------------

CASES: list[dict] = [
    {"name": "golden_success",          "config": place_config(latch=True),
     "steps": _golden(),                "expect": {"success": True,  "fail_reason": "success"}},
    {"name": "boundary_equal_in_range", "config": place_config(latch=True),
     "steps": _boundary_equal(),        "expect": {"success": True,  "fail_reason": "success"}},
    {"name": "latch_true_locked_after_lift", "config": place_config(latch=True),
     "steps": _hold_then_lift(),        "expect": {"success": True,  "fail_reason": "success"}},
    {"name": "latch_false_lift_breaks_success", "config": place_config(latch=False),
     "steps": _hold_then_lift(),        "expect": {"success": False, "fail_reason": "F2"}},
    {"name": "hold_one_frame_short",    "config": place_config(latch=True),
     "steps": _hold_one_frame_short(),  "expect": {"success": False, "fail_reason": "F2"}},
    {"name": "hold_too_short",          "config": place_config(latch=True),
     "steps": _hold_too_short(),        "expect": {"success": False, "fail_reason": "F2"}},
    {"name": "mid_air_drop_sticky",     "config": place_config(latch=True),
     "steps": _mid_air_drop(),          "expect": {"success": False, "fail_reason": "F1"}},
    {"name": "tilt_over_sticky",        "config": place_config(latch=True),
     "steps": _tilt_over(),             "expect": {"success": False, "fail_reason": "F1"}},
    {"name": "never_approach_timeout",  "config": place_config(latch=True),
     "steps": _never_approach(),        "expect": {"success": False, "fail_reason": "F4"}},
    {"name": "jitter_never_holds",      "config": place_config(latch=True),
     "steps": _jitter(),                "expect": {"success": False, "fail_reason": "F2"}},
    {"name": "metric_missing_is_F0",    "config": place_config(latch=True),
     "steps": _metric_missing(),        "expect": {"success": False, "fail_reason": "F0"}},
    {"name": "lid_never_meets_F3",      "config": LID_CONFIG,
     "steps": _lid_never_meets(),       "expect": {"success": False, "fail_reason": "F3"}},
    {"name": "lid_golden_success",      "config": LID_CONFIG,
     "steps": _lid_golden(),            "expect": {"success": True,  "fail_reason": "success"}},
]

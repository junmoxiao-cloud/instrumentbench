# 判分器 YAML Schema 规范（v0.1-draft）

> **状态：草稿。** 字段名在 v0.1 发布评审后冻结，此后任何字段变更视为 API 破坏性变更。
> 本文档定义 InstrumentBench 声明式判分器的任务判据配置格式。设计目标：**判分逻辑全部内建于通用评估器，任务差异只体现在 YAML——新增任务 = 新增一个 YAML 文件，不改代码。**
> 本文档为中文草稿；公开发布前译英或提供双语。

---

## 1. 设计原则

1. **判据即配置**：阈值比较、计时器、优先级判定全部内建于评估器；任务差异只出现在 YAML；
2. **判分器与仿真解耦**：评估器只吃状态快照（`EnvSnapshot`，plain dict / dataclass），不感知 USD、渲染或任何仿真框架——因此纯 CPU、可离线回放、可在无仿真的进程中单测；
3. **判据单一权威**：实时采集反馈、增广过滤、训练奖励三个场景共用**同一份 YAML、同一个 `criterion_version`**；禁止任何"按调用方放宽"的分支（如"增广时把保持时长调松"）；
4. **证据自证**：每次判分输出"实际值 vs 阈值"证据，人工复核无需回放视频；
5. **可版本追溯**：判据任何改动必须递增 `criterion_version` 并触发受影响数据集全量重判。

---

## 2. 顶层字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `task_id` | str | ✅ | 全局唯一任务 ID（snake_case） |
| `language_instruction` | str | ✅ | 自然语言任务指令（与训练数据中的指令一致） |
| `criterion_version` | int | ✅ | 判据版本号，从 1 起；任何阈值/条件/语义改动必须递增（见 §7） |
| `timeout_s` | float | ✅ | episode 超时（秒）。由外层采集/评测循环执行截断，评估器内部不处理超时 |
| `criterion` | map | ✅ | 成功判据主体（见 §3） |
| `metrics_sources` | map | ✅ | 指标来源声明（见 §4） |
| `failure_rules` | list | ✅ | 有序失败规则，先命中先归类（见 §5） |
| `stages` | list | ✖ | 多阶段扩展，v0.2 预留（见 §8）；v0.1 仅支持单阶段 |

---

## 3. criterion：成功判据

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `hold_s` | float | ✅ | 需**连续**保持在成功区域的时长（秒） |
| `latch` | bool | ✅ | 收尾语义：`true` 达标即锁存 / `false` 终局判定（见 §6.2，两种语义对同一轨迹可能给出相反结论，必须显式选择） |
| `conditions` | list | ✅ | 原子条件列表，**全部 AND 组合**构成"成功区域" |

### 3.1 原子条件（atomic condition）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `metric` | str | ✅ | 指标名；须能由 `metrics_sources` 中声明的 source 提供（显式声明或派生，见 §4.2） |
| `source` | str | ✅ | 指标来源键（对应 `metrics_sources` 中的一个键） |
| `op` | str | ✅ | 比较符：`>` / `>=` / `<` / `<=` / `==` / `in_range` |
| `value` | float | ◑ | 阈值（`in_range` 以外的 op 必填；特殊值 `auto` 见下） |
| `min` / `max` | float | ◑ | `in_range` 时的区间边界（**闭区间**） |
| `ref` | str | ✖ | `"initial"`：以 episode 开局捕获的基线为参照，判**增量**而非绝对值（见 §6.3） |
| `target_source` | str | ✖ | 参照另一对象的 source（如"到天平托盘中心的 XY 距离"） |
| `target_radius_scale` | float | ✖ | 随 `target_source` 使用：成功半径 = 目标包围盒短边 × 该系数；`value: auto` 时必填。目标区域几何在 `reset_episode` 时解析一次并缓存 |

**`value: auto`**：仅用于"到目标中心距离"类条件，半径由评估器在开局解析目标包围盒自动计算，避免手写绝对坐标。

---

## 4. metrics_sources：指标来源

### 4.1 声明字段

每个键 = 一个 source 名，评估器经 sim 侧适配器按此读取状态；评估器本体不解析场景结构。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `kind` | str | ✅ | `rigid_pose`（刚体位姿）/ `joint_angle`（关节角）/ `bbox_circle`（包围盒目标区域） |
| `prim_path` | str | ✅ | 场景中该对象的路径。由 sim 适配器解析；判分器本体不读取、不校验其存在性 |
| `unit` | str | ✅ | `deg` / `rad` / `m` 等。**必须显式声明，不隐式假设** |

### 4.2 指标派生规则

评估器从声明的 kind 自动派生指标，无需额外声明：

| kind | 提供的指标 |
|---|---|
| `rigid_pose` | `obj_x` / `obj_y` / `obj_z`（世界系位置）；`obj_tilt_deg`（相对开局基线的倾角）；`obj_z_step_delta`（相邻帧 z 变化量，逐步稳定判据）；`xy_distance_to_target`（随 `target_source` 使用） |
| `joint_angle` | `joint_angle_deg`（关节角，按 `unit` 换算） |
| `bbox_circle` | 不直接提供指标；作为 `target_source` 被引用，开局解析圆心与半径 |

> 单位约定：位置类指标一律米（m）；角度类指标在 `unit: deg` 时为度、`rad` 时为弧度；`obj_z_step_delta` 为"米/帧"。坐标系一律世界系（相对基线的增量同样在世界系下计算）。

---

## 5. failure_rules：失败规则

**规则列表按序判定，先命中先归类**；全表**恰有一条** `default: true` 兜底规则。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | str | ✅ | 失败码（F0–F4，见表） |
| `sticky` | bool | ✖ | **粘滞**：过程中一旦触发即置位，此后无论轨迹如何整条判死（如"先掉落后捡回"不算成功） |
| `when` | str | ◑ | 特殊触发条件：`metric_missing`（指标源不可读）/ `entered_region_without_hold`（曾进入成功区域但保持不足） |
| `conditions_any` | list | ◑ | OR 组合的原子条件列表（与 §3.1 同构，任一满足即触发） |
| `default` | bool | ✖ | 兜底规则：以上全部未命中时归类于此（全表恰一条） |

### 5.1 统一失败码表（摘要；详表见 docs/failure-taxonomy.md）

| 码 | 含义 | 典型触发 |
|---|---|---|
| `F0` | 传感器/判分器异常 | 指标源不可读。**工具故障**：必须修复后重跑，不得计入判分一致率统计 |
| `F1` | 抓取失败 | 掉落（跌破高度线）/ 倾斜超限；通常 `sticky: true` |
| `F2` | 放置偏移 | 曾进入成功区域但保持不足 |
| `F3` | 设备状态未达成 | 关节/门状态全程未过阈值 |
| `F4` | 流程中断/超时 | 兜底：从未接近目标或超时 |

### 5.2 终局汇总优先级（固定，不可配置）

```
1. F0        指标缺失/不可读（工具故障优先暴露）
2. sticky    粘滞失败标志已置位（灾难性失败不可恢复）
3. success   hold_timer 达标（按 latch 语义）
4. 失败规则链  按列表顺序逐条判定
5. 兜底      default: true 规则
```

每条失败输出必须携带**证据指标**（实际值 vs 阈值，如实际保持时长 vs 要求时长、实际最小高度 vs 高度线），使人工复核无需回放。

---

## 6. 语义细则（写 YAML 前必读）

### 6.1 hold_timer 数据流

```
每个仿真步:
    in_region = 所有原子条件当前值均满足           # 成功区域布尔判定（AND）
    if in_region: hold_timer += dt
    else:         hold_timer = 0                  # 离开区域即清零（非暂停）
    if hold_timer >= hold_s: 成功（按 latch 语义收尾）
```

**清零语义**：在区时长分段累计不等于连续保持——"分两段各 1 秒"不满足 `hold_s: 1.0`。这是防"擦过阈值即成功"假阳性的代价；标定阈值时需有意识权衡。

### 6.2 latch 两种收尾语义

| `latch` | 语义 | 适用场景 | 反例（不适用时） |
|---|---|---|---|
| `true` | **立即锁存**：达标瞬间置成功，此后状态恶化不翻盘 | 盖子/门开合类——到位后的小回弹不否决成功 | 举起又放下类任务 |
| `false` | **终局判定**：仅在 episode 结束时检查计时器——最后一段连续在区时长必须足够 | 放置/称重类——举起又放下算失败 | 有回弹的铰链类任务 |

同一轨迹在两种语义下结论可能相反。**不写 `latch` 字段视为 schema 错误**（拒绝加载），防止隐式假设。

### 6.3 相对基线（`ref: initial`）

- 基线在 `reset_episode` 时捕获（episode 开局第一步的位姿/角度），时机固定，不可配置；
- 判**增量**而非绝对坐标 → 场景摆放漂移不影响判据（抗噪关键设计）；
- 例：`metric: joint_angle_deg, op: ">", value: 30, ref: initial` 表示"相对开局角度增大 30° 以上"。

### 6.4 边界与单位

- `op` 为标准数学语义（`>` 严格大于）；`in_range` 为**闭区间** `[min, max]`；
- 恰好等于阈值的结果由 op 语义唯一确定，评估器不做任何 epsilon 容差——需要容差时用 `ref` 增量或调整阈值显式表达；
- 单位与坐标系在 `metrics_sources` 写死；仿真侧适配器负责按声明换算，评估器不猜。

---

## 7. 版本化规则

1. `criterion_version` 从 1 起整数递增；
2. **改任何阈值、条件、latch、失败规则 = 必须递增**——包括"看起来很小"的改动；
3. 递增后必须对**受影响数据集全量重判**，禁止只重判分歧条目（防过拟合单条）；
4. 每次判分输出回写 `criterion_version`，任何报告/数据集可追溯到当时的判据版本；
5. 保留判据演化记录：`{version, 关键阈值, 一致率, 日期}` 每轮一条。

---

## 8. stages 多阶段扩展（v0.2 预留）

跨设备任务（≥2 台设备）按阶段串行多个 criterion，整体成功 = 按序全部达成；失败码 F4（流程中断）自然映射到"卡在第几阶段"。

- v0.1 **不解析** `stages`；为该键名保留顶层位置，出现时告警不报错；
- v0.2 起启用，字段设计届时评审冻结。

---

## 9. 完整示例

> 以下数值**仅为格式示意占位**，真实阈值来自设备校准与采集标定。

### 9.1 关节角类：关离心机盖

```yaml
task_id: close_centrifuge_lid
language_instruction: "close the centrifuge lid"
criterion_version: 1
timeout_s: 10.0

criterion:
  hold_s: 0.25          # 过阈值且保持 >= 0.25s
  latch: true           # 达标即锁存：到位后的小回弹不翻盘
  conditions:
    - metric: joint_angle_deg
      source: lid_revolute
      op: ">"
      value: -46.0

metrics_sources:
  lid_revolute:
    kind: joint_angle
    prim_path: /World/Centrifuge/models/Centrifuge_top/RevoluteJoint
    unit: deg

failure_rules:
  - id: F0
    when: metric_missing          # 指标源不可读 → 工具故障，单独计数
  - id: F3
    default: true                 # 兜底：到超时关节角从未过阈值
```

### 9.2 放置类：管子放天平托盘

```yaml
task_id: place_tube_on_balance
language_instruction: "place the tube on the balance"
criterion_version: 1
timeout_s: 10.0

criterion:
  hold_s: 1.0
  latch: true
  conditions:
    - metric: xy_distance_to_target     # 到目标中心 XY 距离 <= 成功半径
      source: tube
      target_source: balance_plate
      op: "<="
      value: auto                       # 半径 = 托盘包围盒短边 × scale，开局解析一次
      target_radius_scale: 0.5
    - metric: obj_z                     # 高度区间（落在托盘面上）
      source: tube
      op: in_range
      min: 0.63
      max: 0.73
    - metric: obj_z_step_delta          # 稳定判据：相邻帧高度变化量 <= 容差
      source: tube
      op: "<="
      value: 0.002

metrics_sources:
  tube:
    kind: rigid_pose
    prim_path: /World/Centrifuge_tube
    unit: m
  balance_plate:
    kind: bbox_circle                   # 开局解析圆心与半径并缓存
    prim_path: /World/Electronic_Balance/root/ROOT/Plate
    unit: m

failure_rules:
  - id: F0
    when: metric_missing
  - id: F1                              # 粘滞：掉落/倾斜，一旦发生整条判死
    sticky: true
    conditions_any:
      - metric: obj_z
        source: tube
        op: "<"
        value: 0.20
      - metric: obj_tilt_deg
        source: tube
        op: ">"
        value: 35.0
        ref: initial
  - id: F2                              # 曾进入成功区域但保持不足
    when: entered_region_without_hold
  - id: F4                              # 兜底：从未接近目标
    default: true
```

---

## 10. 新增任务自查清单

- [ ] 未改判分器代码，只新增了 YAML？
- [ ] 每个指标的单位（`unit`）与坐标系已显式声明？
- [ ] `latch` 已显式选择并符合任务直觉（锁存 vs 终局）？
- [ ] 失败规则**恰一条** `default: true` 兜底？规则间互斥可判定？
- [ ] 灾难性失败（掉落/倾斜）已设 `sticky: true`？
- [ ] `criterion_version` 从 1 起，阈值有标定依据（设备校准/采集分布）？
- [ ] 合成轨迹自测通过：黄金成功 / 保持不足 / 中途掉落 / 边界恰好等于阈值 / 抖动分段保持 / 指标缺失（F0），各至少一例？

---

## 附录 A：判据原子形态速查

| 模式 | 表达方式 | 适用场景 |
|---|---|---|
| 关节角过阈值 + 方向 | `joint_angle_deg` + `>` / `<`（可配 `ref: initial`） | 盖/门开合、按钮行程 |
| 高度增量 | `obj_z` + `ref: initial` | 抬起/放下判定 |
| 到目标 XY 距离 + 高度区间 | `xy_distance_to_target`（`value: auto`）+ `obj_z` `in_range` | 放置类 |
| 逐步稳定 | `obj_z_step_delta` <= 容差 | 称重、读数等待 |
| 坐标区间组合 | 多个 `in_range` 条件 AND | 入槽、入盒 |
| 双轴位移组合 | `obj_x` / `obj_y` 各自增量条件 AND | 推、拨类动作 |

> 上述模式为本项目独立实现的经验归纳，未引用任何第三方代码。

## 变更记录

| 版本 | 日期 | 说明 |
|---|---|---|
| v0.1-draft | 2026-09-06 | 初稿：顶层字段 / 原子条件 / 指标派生 / 失败码 F0–F4 / hold_timer 与 latch 语义 / 版本化规则 / 两示例 / 自查清单。字段名待 v0.1 发布评审冻结 |

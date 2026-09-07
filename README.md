# InstrumentBench

> 以**设备状态为一等公民**的跨设备实验室操作基准（私有开发仓）。

任务 = 多台仪器间的完整流程（开门 → 取皿 → 称重 → 放回）；判分 = 声明式 YAML（阈值 + 保持时长 + 统一失败分类 F0–F4）；仿真与真实部署共用同一判据口径。

> 定名说明：InstrumentBench（2026-09-06 GitHub/全网重名检索通过；检索记录见内部规划《评测基准开源_文档规划》§七）。备选名 LabStage。

## 当前状态（预热阶段）

- [x] 仓库初始化（LICENSE / .gitignore / 目录骨架）
- [x] [docs/judge-schema.md](docs/judge-schema.md) v0.1-draft（字段名待评审冻结）
- [x] [judge/snapshot.py](judge/snapshot.py) 数据契约：EnvSnapshot / EpisodeResult / F0–F4 码表 / CSV 列契约
- [x] [tests/](tests/cases.py) 合成轨迹用例 ×13（黄金成功/边界/latch A-B/粘滞/抖动/F0/F3…；evaluator 落地前自动 skip，落地后应全绿）
- [x] [docs/failure-taxonomy.md](docs/failure-taxonomy.md) 失败码表详表（判定条件/证据指标/优先级/标注对应）
- [x] [docs/task-spec.md](docs/task-spec.md) 新增任务三步指南 + 判据标定方法 + 常见坑
- [ ] judge/evaluator.py + batch.py（挂主线 T4 判分器交付实现，测试即验收）
- [ ] tasks/ 示例任务 YAML ×2（随 evaluator 一起入库）
- [ ] v0.1 发布（README 定稿 + 5 分钟快速开始 + 录屏）

## 版本规划

| 版本 | 内容 | 触发点（= 主线验收点） |
|---|---|---|
| v0.1 | 判分器内核 + schema + 2 示例任务 + tests | T4 判分器交付验收后 |
| v0.2 | 任务套件 + 场景/资产 + 评测协议 | 阶段 3 尾（T3+T5 交付后） |
| v1.0 | 基线 + 排行榜 + 失败分析报表 | 阶段 4 / T6 后 |

## 硬原则

1. **只翻译主线已有产出，不做新功能**——每一份开源产物必须对应一份已完成的主线交付；
2. **发布点 = 主线验收点**——不提前（未验收不透支信誉），不拖后（错过窗口）；
3. **判据单一权威**——评估 = 增广过滤 = 训练奖励，共用同一 YAML、同一 `criterion_version`；禁止任何"按调用方放宽"。

## License

代码 MIT；文档 CC BY 4.0；USD 设备资产单独声明（授权确认中）。

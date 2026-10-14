# Matrix Account｜统一的 OKX 永续合约策略系统

Matrix Account（原 Unified Jarvis）把主流币和山寨币、多头和空头放入同一账户的市场权限、候选评估、风险与退出框架。系统先判断 BTC 主导的市场阶段，再决定四个策略分支可以主动交易、仅试探或等待，最后通过确定性代码完成仓位计算与执行。

本仓库保存 **v1.3.2** 的源码、测试与运维文档。它接续已结束独立实验的 [Hermes Mi](https://github.com/Immutable1407/Jarvis-maincoin-private) 和 [Jarvis v4 Hunter](https://github.com/Immutable1407/Jarvis-trading-system-private)，用于在统一资金和约束下验证四类机会。

## 版本与范围

| 项目 | 值 |
| --- | --- |
| 代码版本 | `1.3.2` |
| 策略标签 | `matrix_v1_3_2_exit_execution_repair` |
| 主流币范围 | BTC、ETH、SOL、BNB 的 USDT 永续合约 |
| 山寨扫描 | OKX USDT-SWAP 行情池，默认按成交量排序选取最多 120 个非主流币标的 |
| 账户配置 | 专用 OKX profile `jarvis-unified-100u` |
| 原运行目录 | `/root/jarvis-unified` |
| 实时决策 | Python；LLM 不进入入场或退出链路 |

`AGENTS.md` 记录 v1.3.2 当时为运行系统，早期迁移说明记录约 220 USDT 的启动资金。这些是历史部署信息，不代表当前账户余额、持仓或任务运行状态。profile 名称沿用早期命名，也不是当前资金限制。

## 四个策略分支

|  | 主流币 | 山寨币 |
| --- | --- | --- |
| 多头 | `maincoin_long` | `alt_long` |
| 空头 | `maincoin_short` | `alt_short` |

每个分支拥有独立权限与仓位计数，同时受账户、主流币/山寨币两类容量和市场阶段上限约束。四个分支不会在所有环境中同时开放。

Router 识别 `btc_impulse`、`btc_compression_ema99`、`btc_range_alt_dispersion`、`risk_off_alt_decay`、`crash` 和 `no_edge`。例如，正向 BTC impulse 侧重多头；弱市侧重空头；压缩与分化环境允许有限试探；crash 与无明确优势时停止新开仓。

## 执行流程

```text
账户验证与成交同步
  → 主流币 K 线、山寨行情池与市场宽度
  → BTC-led Market Phase Router
  → 四分支权限与候选生成
  → 山寨 K 线复核，复核后重新筛选
  → 分支 / 类别容量、亏损保护、冷却与数量量化
  → 市价入场、attached SL、保护单确认
  → Guardian 保本、减仓、锁盈与退出
  → 成交、决策、退出动作和日报归因
```

主流币候选包含趋势交易，以及压缩或分化阶段的 BTC/ETH 区间边缘机会。山寨行情初筛只生成 preliminary 候选，必须经过 K 线重新评分，才能进入有效订单计划。候选选择按分支组织，减少高波动山寨候选长期占用计划评估窗口的问题。

候选还带有 `strategy_lane` 与 `exit_style`，区分主流趋势、主流区间、山寨趋势和快速试探。存在候选、获得市场权限与生成可执行计划是三个不同步骤。

## 冷路径上下文

`context.py` 通过外部 `okx-profile` 和 `onchainos` 工具采集情绪、新闻、smartmoney 与链上能力信息，再用规则生成评分调整、风险倍率或事件否决。

这些上下文不能直接触发订单。缺失或过期时使用明确的降级修正；采集失败记录 degradation。当前实现是规则解析与上下文能力检查，不能等同于完整链上分析模型或 LLM 交易代理。

## v1.3.2 参数基线

| 参数 | 默认值与含义 |
| --- | --- |
| 全局仓位上限 | 6，仍受 Router 阶段上限限制 |
| 单分支仓位上限 | 3 |
| 主流币 / 山寨币类别上限 | 各 3，另保留 1 个主流币容量位置 |
| 保证金配置上限 | 权益的 75%，订单计划还受 Router 风险 ceiling 限制 |
| 单笔风险预算 | `min(1 USDT, 权益 × 0.6%)`，再应用上下文风险倍率 |
| 亏损停止新开仓 | UTC 当日和滚动 24h 的已实现费后亏损分别达到 6 USDT |
| 杠杆 | 默认 5 倍，配置硬上限 10 倍 |
| 有效候选分数 | 至少 70 |
| 每周期订单数量 | 最多 1 |
| 止损后同币冷却 | 6 小时 |
| 山寨窄止损仓位 | 止损距离小于 1.2% 时，名义金额上限 60 USDT |

参数是配置基线，不能脱离 Router、合约规格和候选门控解释为实际账户暴露或最大损失保证。完整默认值见 [`jarvis_unified/config.py`](jarvis_unified/config.py)，仓位计划见 [`risk_execution.py`](jarvis_unified/risk_execution.py)。

## 退出与执行修补

Guardian 以初始止损距离定义 R，记录每一代持仓的状态，按默认阈值执行：

| 条件 | 动作 |
| --- | --- |
| `+1R` | 移动止损至保本 |
| `+1.5R` | 一次性减仓 50% |
| `+2R` | 将止损推进至至少锁定 `+0.5R` |
| `+3R` | 全平剩余仓位 |
| 满足 MFE 回吐或时间条件 | 触发相应退出规则 |

止损价格和订单数量按 tick / lot 步长量化。入场后检查交易所保护单；无法确认时写入 `live_order_unconfirmed_sl`，并返回保护确认失败。该检查负责暴露异常，不自动保证平仓或补建止损。

v1.3.2 修复 entry 和 Guardian 减仓订单的 tag 错误：使用 `jarvisv132`，遇到特定 `51000 Parameter tag error` 时无 tag 重试一次。Guardian 实盘动作的成功与失败都进入决策账本，healthcheck 会报告 `guardian_action_failed`。详见 [发布说明](docs/V1_3_2_EXIT_EXECUTION_REPAIR_RELEASE.md)。

成交同步失败时，交易周期在候选评估前停止，不用陈旧账本继续开新仓。成交归因结合订单 ID、分支、车道、方向和退出角色；没有明确匹配的内容仍需保留未知或启发式归因状态。

## 仓库结构

```text
jarvis_unified/
├── config.py              # 版本与默认参数
├── market_data.py         # K 线统计、行情池与合约规格缓存
├── context.py             # 冷路径上下文
├── router.py              # 市场阶段与四分支权限
├── candidates.py          # 候选、区间策略与 K 线复核
├── risk_execution.py      # 风险、订单计划与执行
├── ledger_guardian.py     # 成交同步和持仓退出状态机
├── healthcheck.py         # 账户、状态与保护连续性检查
└── reports.py             # 管理摘要与分支归因
scripts/unified/           # 命令行运行入口
scripts/secret_scan.py     # 归档检查
tests/test_unified_core.py # 核心回归
templates/env.example      # 环境变量示例
docs/                     # 发布记录与运行手册
```

## 代码检查与运行准备

代码使用 `tomllib` 和 `datetime.UTC`，需要 **Python 3.11 或更新版本**。核心模块使用标准库；仓库没有提供完整生产环境安装器。

在仓库根目录检查源码和回归：

```bash
export PYTHONPATH="$PWD"
python3 -m compileall -q jarvis_unified scripts/unified tests
python3 -m unittest discover -s tests -v
```

连接运行环境需要额外准备 `/root/.okx/config.toml` 中的专用 profile、符合预期的账户 UID/mainUid 和账户级别。冷路径还依赖 `/usr/local/bin/okx-profile` 与 `onchainos`。这些配置、工具与生产调度 wrapper 未随仓库提交。

准备完成后，可以分别运行账户检查、上下文采集和交易演练：

```bash
python3 scripts/unified/unified_account_check.py
python3 scripts/unified/unified_collect_context.py
JARVIS_UNIFIED_DRY_RUN=1 python3 scripts/unified/unified_live_cycle.py
```

dry-run 不提交交易订单，但仍读取行情与账户、同步成交并写入本地运行记录。运行数据位于 `data/runtime/`，报告位于 `reports/`。

## 运维入口与权限

| 脚本 | 用途 |
| --- | --- |
| `unified_account_check.py` | 账户身份与基础状态 |
| `unified_collect_context.py` | 冷路径上下文采集 |
| `unified_live_cycle.py` | 交易周期，支持显式 dry-run |
| `unified_guardian.py` | 默认评估保护与退出动作；实盘动作需额外开关 |
| `unified_healthcheck.py` | 账户、快照、上下文和保护链路检查 |
| `unified_combined_daily_brief.py` | 刷新诊断并生成 Matrix 管理摘要 |

交易写操作需要账户校验通过并显式开启 `JARVIS_UNIFIED_LIVE_TRADING=true`。Guardian 实盘执行还需要 `JARVIS_UNIFIED_GUARDIAN_LIVE=1`。调度周期、退出运维与异常处理见 [Runbook](docs/RUNBOOK.md)。

## 版本脉络与验证边界

v0.x 建立统一账户执行、Guardian 与健康检查；v1.0 建立四分支矩阵；v1.1 修补归因、冷却和价格精度；v1.2 提升受控采样容量并加入保护单确认；v1.3 补齐类别容量和主流区间路径，再修补滚动亏损保护及退出执行。

策略意图可阅读 [通俗说明](docs/MATRIX_STRATEGY_PLAIN_LANGUAGE.md)，具体实现以源码与对应发布记录为准。未实现的自动转账、pyramiding 和无约束高频 rotation 不属于当前功能。

测试和历史链路验收证明的是覆盖场景中的行为，不能代替长期收益评估。本仓库不含完整生产成交账本；最近成交查询也不等于完整历史回补。凭证、账户快照、成交、ledger、生产报告和调度器私有状态不进入版本库。

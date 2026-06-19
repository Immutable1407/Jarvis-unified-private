# Matrix Account v1.3.1｜Jarvis 矩阵账户 OKX 永续全市场策略

> 私有仓库归档：Matrix Account（原 Unified Jarvis）是 Sir 的统一 OKX 永续合约策略系统。Mi 主流币账户与 v4 山寨账户已完成历史实验收尾，资金转入本账户后，系统目标从“100U 生存验证”升级为“用约 220U 正式验证 2×2 全市场策略矩阵”。

## 1. 系统目标

Matrix Account 不再是 Mi + v4 的拼接，而是一个 BTC-led Market Phase Router 之下的 2×2 策略矩阵：

```text
BTC-led 市场阶段判断
  → 四袖套权限：maincoin_long / maincoin_short / alt_long / alt_short
  → OKX 冷路径情绪/聪明钱/链上上下文修正评分与风险
  → 候选生成 + 主流币 range lane + 山寨 candle-rescore
  → family capacity / 风险预算 / 合约规格 / 订单执行 / attached SL
  → guardian 保本 / 部分止盈 / 锁盈 / MFE giveback / time stop / 全平
  → fill/decision/phase/lane 归因
  → 日报 / 周报 / 小版本迭代
```

核心目标：

- 统一资金调度，不再让主流币和山寨策略各自割裂；
- 同时验证主流多、主流空、山寨多、山寨空四类机会；
- 补齐主流币仓位与震荡策略，避免系统退化成山寨单腿账户；
- 在真实 220U 级别资金下收集足够样本；
- 保持 LLM 退出热路径，所有实时下单和退出由确定性代码完成；
- 用 OKX 账户权益、fills、guardian 动作和完整归因驱动下一轮进化。

## 2. 当前版本

- 当前版本：`v1.3.1`
- 策略标签：`matrix_v1_3_1_loss_logic_repair`
- 账户：OKX profile `jarvis-unified-100u`，UID `851731612504386465`，mainUid `621655308511150593`
- 发布说明：`docs/V1_0_0_MATRIX_RELEASE.md`、`docs/V1_1_0_MATRIX_HYGIENE_RELEASE.md`、`docs/V1_1_1_TICK_SAFE_STOPS_RELEASE.md`、`docs/V1_2_0_CONTROLLED_GROWTH_RELEASE.md`、`docs/V1_3_0_STRUCTURAL_COMPLETION_RELEASE.md`、`docs/V1_3_1_LOSS_LOGIC_REPAIR_RELEASE.md`
- 通俗策略说明：`docs/MATRIX_STRATEGY_PLAIN_LANGUAGE.md`

v1.3.1 loss-logic repair upgrade：

- 保持 v1.3.0 风险参数与 2×2 Matrix 架构，不做 panic stop / 不加仓回本；
- 新增 `rolling_24h_loss_halt_usdt=6.0`，近 24h 已实现亏损触发停止新开仓；
- fill sync 从 decisions/order id 回填 `fill_role` / `order_role` / `strategy_lane` / `exit_style` / `sleeve`，并对未知成交启发式标注；
- live cycle 在 candle-rescore 后重新 sleeve-aware selection，避免 confirmed 高分候选被 stale seed 顺序压住；
- 对山寨 tight-stop (`stop_pct < 1.2%`) 增加 `tight_stop_notional_cap_usdt=60`，避免窄止损放大名义仓位与手续费；
- 新增 `candidate_diagnostics.maincoin_starvation_reason`，明确 maincoin 是 router wait、无候选还是被计划窗口挤出；
- fill sync 失败时 live cycle fail closed，不允许使用陈旧 ledger 继续开新仓。

v1.3.0 structural-completion upgrade：

- 风险参数不激进推进：仍为最多 6 仓、每袖套最多 3 仓、单笔风险 1.0U、日亏损 halt 6.0U、最大保证金使用 75%；
- 新增 maincoin/alt family cap：主流币最多 3 仓、山寨最多 3 仓，并保留 1 个主流币 reserved slot；
- 新增 BTC/ETH 主流币 range lane，仅在 `btc_compression_ema99` / `btc_range_alt_dispersion` 且 router 方向允许时在区间边缘生成候选；
- Candidate 增加 `strategy_lane` / `exit_style`，区分 `maincoin_trend`、`maincoin_range`、`alt_trend`、`alt_fast_probe`；
- live cycle 改为 sleeve-aware candidate selection，避免山寨高波动 score 永久挤出主流币候选；
- guardian 增加 `max_r_multiple` / `opened_ts`，支持 MFE giveback、time stop 和同币同向重开 generation reset；
- 保留 post-order protective stop confirmation 和 opportunity-block logging。

v1.2.0 controlled-growth upgrade：

- 将账户从生存采样提升到受控增长：最多 6 仓、每袖套最多 3 仓、单笔风险 1.0U、日亏损 halt 6.0U、最大保证金使用 75%；
- 山寨 universe 扩到 120，live candle-rescore top N 扩到 16；
- 修复 guardian 独立 stop move payload，改用 OKX `slTriggerPx/slOrdPx`，避免 50015；
- live entry 后新增 post-order protective stop confirmation，无法确认保护单时记录 `live_order_unconfirmed_sl`；
- 新增 `opportunity_blocks.jsonl`，记录高分候选被 sleeve cap/cooldown/duplicate 拦截，用于判断 cap 是救命还是错失收益；
- 仍保留 `max_orders_per_cycle=1`、score 70、6h cooldown，不进入 full-speed/turbo。

## 3. 账户与安全边界

生产 OKX profile：

```bash
okx-profile --profile jarvis-unified-100u ...
```

写操作必须满足：

- profile 指向矩阵账户；
- UID/mainUid 符合预期；
- 环境变量 `JARVIS_UNIFIED_LIVE_TRADING=true` 显式开启；
- guardian live 退出动作还需要 `JARVIS_UNIFIED_GUARDIAN_LIVE=1`；
- Router 权限、候选确认、family capacity、风险预算、合约规格、重复币种、袖套仓位、日亏损保护全部通过。

本仓库不保存 OKX API key、Hermes `.env`、Feishu webhook、模型 key、runtime fills/ledgers/snapshots/reports。

## 4. 已实现功能范围

已实现：

- OKX profile 读取与 UID guard；
- OKX public/private REST client；
- 主流币 candles、OKX 全 USDT-SWAP ticker、funding、OI、instrument specs；
- OKX cold context：news/sentiment、smartmoney、OnchainOS slot（失败时 fail loud）；
- Market Phase Router：`btc_impulse`、`btc_compression_ema99`、`btc_range_alt_dispersion`、`risk_off_alt_decay`、`crash`、`no_edge`；
- 2×2 sleeves：主流多、主流空、山寨多、山寨空；
- candidate engine：主流币趋势、多/空 range、山寨多/空 seed scan、山寨 candle-rescore、lane/exit_style 标注；
- risk/execution：ctVal/lotSz/minSz、family capacity、风险金额、保证金上限、杠杆、market order、attached SL；
- guardian：未保护仓位检测、R 倍数评估、breakeven、TP1 50%、锁 `+0.5R`、MFE giveback、time stop、`+3R` 全平；
- healthcheck：UID、冷路径新鲜度、live-cycle/guardian 快照新鲜度、未保护仓位、风险参数 sanity；
- ledger：fills sync、decision log、router snapshot、cold context snapshot、guardian TP 状态、opportunity block；
- Matrix daily brief：矩阵账户每日管理摘要脚本。

暂不使用：Surf、OpenNews、LLM 实时决策、自动转账、pyramiding、无约束高频 rotation。

## 5. v1.3.1 参数

- `max_total_positions = 6`：全账户最多 6 个合约仓位；
- `max_positions_per_sleeve = 3`：每个袖套最多 3 仓，受 Router phase max_positions 进一步限制；
- `max_maincoin_positions_total = 3`；
- `max_alt_positions_total = 3`；
- `maincoin_reserved_slots = 1`；
- `max_margin_usage_pct = 0.75`：账户最大保证金使用上限，同时受 Router phase risk ceiling 限制；
- `single_trade_risk_usdt = 1.00`：单笔风险预算，另受权益百分比上限约束；
- `daily_realized_loss_halt_usdt = 6.00`：UTC 当日已实现亏损触发停止新开仓；
- `rolling_24h_loss_halt_usdt = 6.00`：近 24h 已实现亏损触发停止新开仓；
- `leverage_default = 5`，`leverage_hard_cap = 10`；
- `min_live_candidate_score = 70`；
- `max_same_symbol_positions = 1`；
- `alt_universe_limit = 120`；
- `candle_rescore_top_n = 16`；
- `max_orders_per_cycle = 1`；
- `stopout_cooldown_hours = 6`；
- `tight_stop_threshold_pct = 0.012`；
- `tight_stop_notional_cap_usdt = 60.0`。

## 6. 本地验证

```bash
cd /root/jarvis-unified
export PYTHONPATH=/root/jarvis-unified
python3 -m compileall -q jarvis_unified scripts/unified tests
python3 -m unittest discover -s tests -v
python3 scripts/unified/unified_account_check.py
python3 scripts/unified/unified_collect_context.py
JARVIS_UNIFIED_DRY_RUN=1 python3 scripts/unified/unified_live_cycle.py
python3 scripts/unified/unified_guardian.py
python3 scripts/unified/unified_healthcheck.py
```

## 7. 运行脚本

```text
scripts/unified/unified_account_check.py
scripts/unified/unified_collect_context.py
scripts/unified/unified_live_cycle.py
scripts/unified/unified_guardian.py
scripts/unified/unified_healthcheck.py
scripts/unified/unified_combined_daily_brief.py
```

Hermes cron wrapper 在生产机 `/root/.hermes/scripts/`，本仓库只归档核心代码，不归档 Hermes runtime state。

## 8. 迭代节奏

v1.3.1 正式上线后，默认观察 24–72 小时：

- 主流币 range lane 是否真正进入 plans 并产生样本；
- family capacity 是否阻止山寨占满全局仓位；
- alt lane / exit_style 是否能区分 trend loss 与 fast/probe loss；
- guardian MFE giveback/time stop 是否减少“浮盈可见、历史亏损”的回吐模式；
- 手续费/滑点是否吞噬 1.0U 风险预算；
- fill/decision/opportunity-block 归因是否足够支持 v1.3.x 后续调参。

这是私有代码归档仓库，不是密钥仓库。即使是 private repo，也不能提交任何交易账户密钥或 runtime 私有数据。

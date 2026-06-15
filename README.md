# Matrix Account v1.1.1｜Jarvis 矩阵账户 OKX 永续全市场策略

> 私有仓库归档：Matrix Account（原 Unified Jarvis）是 Sir 的统一 OKX 永续合约策略系统。Mi 主流币账户与 v4 山寨账户已完成历史实验收尾，资金转入本账户后，系统目标从“100U 生存验证”升级为“用约 220U 正式验证 2×2 全市场策略矩阵”。

## 1. 系统目标

Matrix Account 不再是 Mi + v4 的拼接，而是一个 BTC-led Market Phase Router 之下的 2×2 策略矩阵：

```text
BTC-led 市场阶段判断
  → 四袖套权限：maincoin_long / maincoin_short / alt_long / alt_short
  → OKX 冷路径情绪/聪明钱/链上上下文修正评分与风险
  → 候选生成 + 山寨 candle-rescore
  → 风险预算 / 合约规格 / 订单执行 / attached SL
  → guardian 保本 / 部分止盈 / 锁盈 / 全平
  → fill/decision/phase 归因
  → 日报 / 周报 / 小版本迭代
```

核心目标：

- 统一资金调度，不再让主流币和山寨策略各自割裂；
- 同时验证主流多、主流空、山寨多、山寨空四类机会；
- 在真实 220U 级别资金下收集足够样本；
- 保持 LLM 退出热路径，所有实时下单和退出由确定性代码完成；
- 用 OKX 账户权益、fills、guardian 动作和完整归因驱动下一轮进化。

## 2. 当前版本

- 当前版本：`v1.1.1`
- 策略标签：`matrix_v1_1_1_tick_safe_stops`
- 账户：OKX profile `jarvis-unified-100u`，UID `851731612504386465`，mainUid `621655308511150593`
- 发布说明：`docs/V1_0_0_MATRIX_RELEASE.md`、`docs/V1_1_0_MATRIX_HYGIENE_RELEASE.md`

v1.1.1 hotfix：

- 修复 OKX `Parameter slTriggerPx error`：entry attached SL 不再 `round(stop_px, 8)`，改为按 `tickSz` 量化并用十进制字符串传参。
- Guardian breakeven / lock-profit stop move 同步按 `tickSz` 量化。
- 本次不放大风险、不提高杠杆、不降低分数门槛。

v1.1.0 关键变化：

- 沿用 v1.0.0 的 220U 级别采样参数：最多 5 仓、默认 5x、硬上限 10x、单笔风险 0.75U、日亏损 halt 4.5U、最大保证金使用 65%；
- 保持四袖套矩阵：`maincoin_long` / `maincoin_short` / `alt_long` / `alt_short`，Router 对四个袖套分别输出权限；
- 山寨 seed 扫描口径统一为前 100 行，但 live 前仍必须 candle-rescore；
- fills 去重升级为 UID+tradeId，降低跨账户历史污染风险；
- 新增 stopout/负 realized fill 后同币 6h 冷却，减少止损后 churn；
- 日报前刷新 dry-run live snapshot + healthcheck，并输出近 7 日 sleeve PnL 归因；
- 日报口径切换为“矩阵账户”，旧 Mi/v4 只作为归档历史。

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
- Router 权限、候选确认、风险预算、合约规格、重复币种、袖套仓位、日亏损保护全部通过。

本仓库不保存 OKX API key、Hermes `.env`、Feishu webhook、模型 key、runtime fills/ledgers/snapshots/reports。

## 4. 已实现功能范围

已实现：

- OKX profile 读取与 UID guard；
- OKX public/private REST client；
- 主流币 candles、OKX 全 USDT-SWAP ticker、funding、OI、instrument specs；
- OKX cold context：news/sentiment、smartmoney、OnchainOS slot（失败时 fail loud）；
- Market Phase Router：`btc_impulse`、`btc_compression_ema99`、`btc_range_alt_dispersion`、`risk_off_alt_decay`、`crash`、`no_edge`；
- 2×2 sleeves：主流多、主流空、山寨多、山寨空；
- candidate engine：主流币多/空候选、山寨多/空 seed scan、山寨 candle-rescore；
- risk/execution：ctVal/lotSz/minSz、风险金额、保证金上限、杠杆、market order、attached SL；
- guardian：未保护仓位检测、R 倍数评估、breakeven、TP1 50%、锁 `+0.5R`、`+3R` 全平；
- healthcheck：UID、冷路径新鲜度、live-cycle/guardian 快照新鲜度、未保护仓位、风险参数 sanity；
- ledger：fills sync、decision log、router snapshot、cold context snapshot、guardian TP 状态；
- Matrix daily brief：矩阵账户每日管理摘要脚本。

暂不使用：Surf、OpenNews、LLM 实时决策、自动转账、pyramiding、无约束高频 rotation。

## 5. v1.1.0 参数

- `max_total_positions = 5`：全账户最多 5 个合约仓位；
- `max_positions_per_sleeve = 2`：每个袖套最多 2 仓，防止单方向吞掉所有资金；
- `max_margin_usage_pct = 0.65`：账户最大保证金使用上限，同时受 Router phase risk ceiling 限制；
- `single_trade_risk_usdt = 0.75`：单笔风险预算，另受权益 0.6% 上限约束；
- `daily_realized_loss_halt_usdt = 4.50`：当日已实现亏损触发停止新开仓；
- `leverage_default = 5`，`leverage_hard_cap = 10`；
- `min_live_candidate_score = 70`；
- `max_same_symbol_positions = 1`；
- `alt_universe_limit = 100`；
- `stopout_cooldown_hours = 6`。

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

v1.1.0 正式上线后，默认观察 1–2 天：

- Router 是否正确切换四袖套权限；
- 哪个袖套先贡献真实成交样本；
- 手续费/滑点是否吞噬 0.75U 风险预算；
- guardian 是否按 R 倍数执行；
- fill/decision 归因是否足够支持 v1.1.1 / v1.2.0 调参。

这是私有代码归档仓库，不是密钥仓库。即使是 private repo，也不能提交任何交易账户密钥或 runtime 私有数据。

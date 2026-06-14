# Unified Jarvis v0.2.0｜统一加密交易策略系统

> 私有仓库归档：Unified Jarvis 是 Sir 的新一代 OKX 合约交易实验系统，用一个独立 100U 子账户验证「Market Phase Router + OKX 冷路径上下文 + 多袖套 light-live 执行 + guardian 主动退出管理」的统一策略方向。

## 1. 系统目标

Unified Jarvis 不是把旧的主流币策略和山寨币策略简单拼接，而是重新建立一个统一市场阶段路由器：

```text
BTC-led 市场阶段判断
  → maincoin / alt-long / alt-short / cash 权限分配
  → OKX 冷路径情绪/聪明钱/链上上下文修正评分
  → 轻量实盘执行
  → guardian 保本 / 部分止盈 / 锁盈 / 全平
  → fill/decision 归因
  → 两天一轮迭代
```

核心目标：

- 用统一账户验证资金调度是否优于分散账户；
- 让主流币、山寨多头、山寨空头不再各自为政；
- 从第一版开始纳入 OKX 体系内的情绪、聪明钱、链上上下文；
- 保持 LLM 退出热路径，所有实时下单和退出由确定性代码完成；
- 以真实账户权益变化、guardian 退出质量和完整归因为短周期迭代依据。

## 2. 当前版本

- 当前版本：`v0.2.0`
- 策略标签：`unified_v0_2_0_guardian_tp_breakeven_lock`
- 账户：OKX profile `jarvis-unified-100u`，UID `851731612504386465`，mainUid `621655308511150593`
- v0.2.0 新增：guardian R 倍数退出管理，已实盘验证 HMSTR short `>3R` reduce-only 全平。

## 3. 账户与安全边界

运行账户由本机 `~/.okx/config.toml` 的 OKX profile 提供。生产环境使用：

```bash
okx-profile --profile jarvis-unified-100u ...
```

代码内包含 UID / mainUid guard。任何写操作前必须满足：

- profile 指向 Unified 子账户；
- UID 与 mainUid 符合预期；
- 账户为合约可用模式；
- 环境变量 `JARVIS_UNIFIED_LIVE_TRADING=true` 显式开启；
- guardian live 退出动作还需要 `JARVIS_UNIFIED_GUARDIAN_LIVE=1`。

本仓库不保存：

- OKX API key / secret / passphrase；
- `.okx/config.toml`；
- Hermes `.env`；
- 实盘 fills / ledgers / reports / runtime snapshots；
- 飞书 webhook 或任何模型 API key。

## 4. 已实现功能范围

已实现：

- OKX profile 读取与 UID guard；
- OKX public/private REST client；
- market data：主流币 candles、OKX 全 USDT-SWAP ticker、funding、OI、instrument specs；
- cold context：OKX news/sentiment、OKX smartmoney、OKX/OnchainOS context slot；
- Market Phase Router：`btc_impulse`、`btc_compression_ema99`、`btc_range_alt_dispersion`、`risk_off_alt_decay`、`crash`、`no_edge`；
- sleeves：`maincoin`、`alt_long`、`alt_short`、`cash`；
- candidate engine：主流币候选、山寨多头/空头 seed scan、山寨 candle-rescore；
- risk/execution：合约规格、ctVal/lotSz/minSz、风险金额、保证金上限、杠杆、market order、attach SL；
- guardian：未保护仓位检测、R 倍数评估、breakeven、TP1 50%、锁 `+0.5R`、`+3R` 全平；
- ledger：fills sync、decision log、router snapshot、cold context snapshot、guardian TP 状态；
- combined daily brief：三策略每日合并简报脚本。

暂不使用：

- Surf；
- OpenNews；
- LLM 实时决策；
- 自动转账；
- pyramiding；
- 高频 rotation；
- 无约束多 sleeve 同时高强度暴露。

## 5. 冷路径上下文原则

冷路径每 4 小时更新一次：

```text
OKX sentiment / news
OKX smartmoney
OKX/OnchainOS context slot
```

它只允许影响：

- router confidence；
- sleeve permission；
- candidate score；
- total risk multiplier；
- event veto / cooldown。

它不能直接触发订单。数据过期或失败时必须 fail loud degradation，不能伪造 neutral。

## 6. Guardian 退出策略

v0.2.0 guardian 对每个有保护 SL 的 live position 计算 R 倍数：

- `+0.8R`：止损推到 breakeven；
- `+1.5R`：reduce-only 市价平 50%，只触发一次；
- `+2.0R`：止损锁至少 `+0.5R`；
- `+3.0R`：reduce-only 全平，优先级高于同周期 TP1/移动止损。

状态文件为 `data/runtime/state/guardian_tp_state.json`，仅保存在 live runtime，不进入 GitHub。

## 7. 本地验证

```bash
cd /root/jarvis-unified
export PYTHONPATH=/root/jarvis-unified
python3 -m compileall -q jarvis_unified scripts/unified tests
python3 -m unittest discover -s tests -v
python3 scripts/unified/unified_account_check.py
python3 scripts/unified/unified_collect_context.py
JARVIS_UNIFIED_DRY_RUN=1 python3 scripts/unified/unified_live_cycle.py
python3 scripts/unified/unified_guardian.py  # 默认 dry-run
```

## 8. 运行脚本

项目脚本：

```text
scripts/unified/unified_account_check.py
scripts/unified/unified_collect_context.py
scripts/unified/unified_live_cycle.py
scripts/unified/unified_guardian.py
scripts/unified/unified_combined_daily_brief.py
```

Hermes cron wrapper 在生产机 `/root/.hermes/scripts/`，本仓库只归档核心代码，不归档 Hermes runtime state。

## 9. 迭代节奏

当前 v0.2.0 仍是 light-live：小仓位、低保证金占用、强 UID guard、主动 guardian 退出。默认观察周期为 2 天：

- 看账户权益涨跌；
- 看 router 是否识别正确市场阶段；
- 看 cold context 是否提供增量；
- 看候选与实际成交是否一致；
- 看手续费/滑点是否吞噬收益；
- 看 guardian 是否按 R 倍数执行保本、TP1、锁盈和全平；
- 看 fill/exit 归因是否足够支持下一轮调参。

优先后续方向：独立 healthcheck、fill/lifecycle 归因、日报增强、candidate 质量控制和 router replay。

## 10. 仓库安全说明

这是私有代码归档仓库，不是密钥仓库。即使是 private repo，也不能提交任何交易账户密钥或 runtime 私有数据。

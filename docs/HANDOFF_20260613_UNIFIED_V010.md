# Unified Jarvis v0.1.0 会话交接摘要｜2026-06-13

## 本阶段完成

- 解决 OKX CLI 配置文件缺失与 profile 隔离问题。
- 建立 `~/.okx/config.toml` 多 profile 管理方式，并通过 `okx-profile` wrapper 避免 Hermes 进程内 `OKX_*` 环境变量覆盖 profile。
- 验证 Unified 子账户合约权限、账户模式、持仓模式与 SWAP 可用性。
- 创建 `/root/jarvis-unified`，完成 Unified Jarvis v0.1.0 light-live 骨架。
- 部署 live cycle、guardian、cold context、combined daily brief cron。
- 首次实盘链路已打通：router → candidate → candle-rescore → risk sizing → leverage → order → exchange-side SL → guardian audit。
- 新建并推送 private GitHub archive：`Immutable1407/Jarvis-unified-private`。

## 当前系统形态

Unified Jarvis v0.1.0 的核心是 Market Phase Router：

```text
OKX market data + BTC-led regime
  → market_phase
  → sleeve permission: maincoin / alt_long / alt_short / cash
  → OKX cold context modifiers
  → candidate engine
  → unified risk / execution
  → guardian / ledger / attribution
```

v0.1.0 已包含：

- OKX REST client；
- instrument cache 与合约规格 sizing；
- cold context：OKX sentiment/news、OKX smartmoney、OnchainOS degradation slot；
- router：btc impulse / compression / range dispersion / risk-off / crash / no-edge；
- maincoin、alt-long、alt-short、cash sleeves；
- 山寨 seed scan + candle-rescore；
- light-live execution；
- guardian audit；
- fill/decision ledger；
- 三策略合并日报脚本。

## 风控红线

- 私有仓库也不是密钥仓库，禁止提交任何 API key、passphrase、webhook、runtime data。
- 任何实盘写操作必须通过 UID/mainUid guard。
- `JARVIS_UNIFIED_LIVE_TRADING=true` 是实盘写入开关。
- 冷路径 context 不得直接触发交易。
- 山寨 seed-only 候选不得跳过 candle-rescore。
- v0.1.0 不启用自动转账、不启用 pyramiding、不启用 LLM hot-path。

## 已部署 cron

- Unified live cycle：每 15 分钟，local。
- Unified guardian：每 5 分钟，local。
- Unified OKX cold context：每 4 小时，local。
- Jarvis daily combined strategy board brief：每日 21:00 UTC+8，Feishu。

旧的单独 Mi/v4 日报已暂停，BTC-AHR999 定投与周日周结保留。

## GitHub 状态

- Remote: `git@github.com-jarvis:Immutable1407/Jarvis-unified-private.git`
- Initial release tag: `v0.1.0`
- Initial commit: `3161a1d`
- Sanitized export path: `/root/jarvis-unified-github-export`
- Remote verify clone: `/root/jarvis-unified-github-verify-clone`
- Local and remote secret scan both require zero findings.

## 下一轮两天复盘重点

1. Router 是否正确识别 BTC range / risk-off / impulse。
2. Cold context 是否对 sleeve permission 与 risk multiplier 提供真实增量。
3. 首批实盘订单的 MFE、MAE、fee drag、SL 行为是否符合设计。
4. Guardian 是否持续发现并验证 exchange-side SL。
5. Unified 与 Hermes Mi / Jarvis v4 的资金使用效率是否改善。
6. OnchainOS degradation 是否需要在 v0.1.1 优先修复。
7. 是否需要添加 no-MFE exit、breakeven、trailing 或 time-stop。

## 常用命令

```bash
cd /root/jarvis-unified
export PYTHONPATH=/root/jarvis-unified
python3 -m unittest discover -s tests -v
JARVIS_UNIFIED_DRY_RUN=1 python3 scripts/unified/unified_live_cycle.py
python3 scripts/unified/unified_guardian.py
```

推送归档时：

```bash
cd /root/jarvis-unified-github-export
python3 scripts/secret_scan.py .
git push origin main
git push origin --tags
```

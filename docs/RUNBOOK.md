# Matrix Account v1.2.0 Runbook

## 安全启动

1. 确认 OKX profile：`jarvis-unified-100u`。
2. 运行账户检查并确认 UID/mainUid guard 通过。
3. 先跑一次 cold context collector。
4. 运行 dry-run live cycle。
5. 只有实盘 live cycle 部署时设置：`JARVIS_UNIFIED_LIVE_TRADING=true`。
6. Guardian 默认 dry-run；允许 guardian 执行 reduce-only TP/锁盈/全平时，还需要 `JARVIS_UNIFIED_GUARDIAN_LIVE=1`。

## Cron 建议

- live cycle：每 15 分钟，local。
- guardian：每 5 分钟，local。
- cold context：每 4 小时，local。
- healthcheck：每 120 分钟，local；异常时输出 JSON。
- combined daily brief：每日 21:00 UTC+8，Feishu。

## Guardian 运维

只读/演练：

```bash
cd /root/jarvis-unified
export PYTHONPATH=/root/jarvis-unified
python3 scripts/unified/unified_guardian.py
```

实盘保护退出：

```bash
cd /root/jarvis-unified
export PYTHONPATH=/root/jarvis-unified
export JARVIS_UNIFIED_LIVE_TRADING=true
export JARVIS_UNIFIED_GUARDIAN_LIVE=1
python3 scripts/unified/unified_guardian.py
```

v1.2.0 guardian 策略：`+1.0R` 保本，`+1.5R` TP1 50%，`+2R` 锁 `+0.5R`，`+3R` reduce-only 全平。状态保存在 runtime `data/runtime/state/guardian_tp_state.json`。独立 move-stop 使用 OKX `slTriggerPx/slOrdPx` protective stop payload；不要退回 generic `triggerPx/orderPx`。

## Healthcheck 运维

```bash
cd /root/jarvis-unified
export PYTHONPATH=/root/jarvis-unified
python3 scripts/unified/unified_healthcheck.py
```

检查项：UID/mainUid、cold context 新鲜度、live-cycle/guardian 快照新鲜度、未保护仓位、风险参数 sanity。

## 事故处理

- UID mismatch：立即停止所有写操作。
- guardian 异常：暂停 live cycle，先确认仓位与 SL/algo。
- 持仓无保护 algo：暂停 live cycle，手动确认 OKX 侧保护，必要时补 SL 或平仓。
- cold context 失败：热路径继续运行，但 risk multiplier 应降级。
- 日亏损达到阈值：暂停新开仓，只保留 guardian。
- guardian 已触发 full close 后：运行 `sync_fills()`，再确认 positions 为空且 algo_count 为 0。

## 推送归档

归档只能从 sanitized export repo 推送：

```bash
cd /root/jarvis-unified-github-export
python3 scripts/secret_scan.py .
git status --short
git push origin main
git push origin --tags
```

推送后必须 fresh clone 到 `/root/jarvis-unified-github-verify-clone` 并重新运行 secret scan 与测试。

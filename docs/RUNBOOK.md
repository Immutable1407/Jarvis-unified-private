# Unified Jarvis v0.1.0 Runbook

## 安全启动

1. 确认 OKX profile：`jarvis-unified-100u`。
2. 确认 UID guard 通过。
3. 冷路径 context 先跑一次。
4. dry-run live cycle。
5. 只有实盘部署时设置：`JARVIS_UNIFIED_LIVE_TRADING=true`。

## Cron 建议

- live cycle：每 15 分钟，local；
- guardian：每 5 分钟，local；
- cold context：每 4 小时，local；
- combined daily brief：每日 21:00 UTC+8，Feishu。

## 事故处理

- UID mismatch：立即停止所有写操作；
- guardian 异常：暂停 live cycle，先确认仓位与 SL；
- cold context 失败：热路径继续运行，但 risk multiplier 应降级；
- 日亏损达到阈值：暂停新开仓，只保留 guardian。

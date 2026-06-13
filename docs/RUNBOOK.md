# Unified Jarvis v0.1.0 Runbook

## 安全启动

1. 确认 OKX profile：`jarvis-unified-100u`。
2. 运行账户检查并确认 UID/mainUid guard 通过。
3. 先跑一次 cold context collector。
4. 运行 dry-run live cycle。
5. 只有实盘部署时设置：`JARVIS_UNIFIED_LIVE_TRADING=true`。

## Cron 建议

- live cycle：每 15 分钟，local。
- guardian：每 5 分钟，local。
- cold context：每 4 小时，local。
- combined daily brief：每日 21:00 UTC+8，Feishu。

## 事故处理

- UID mismatch：立即停止所有写操作。
- guardian 异常：暂停 live cycle，先确认仓位与 SL/algo。
- cold context 失败：热路径继续运行，但 risk multiplier 应降级。
- 日亏损达到阈值：暂停新开仓，只保留 guardian。

## 推送归档

归档只能从 sanitized export repo 推送：

```bash
cd /root/jarvis-unified-github-export
python3 scripts/secret_scan.py .
git status --short
git push origin main
git push origin --tags
```

推送后必须 fresh clone 到 `/root/jarvis-unified-github-verify-clone` 并重新运行 secret scan。

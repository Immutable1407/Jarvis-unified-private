# Matrix Account v1.3.1 — Loss Logic Repair

## Release intent

v1.3.1 is a controlled repair release after the v1.3.0 near-10U loss/logic debate. It does **not** panic-stop the Matrix strategy, increase risk, or chase losses. It keeps the v1.3.0 2×2 structure and risk budget while repairing the parts that made losses hard to attribute or allowed recent loss windows to keep planning new entries.

## Changes

1. **Rolling 24h loss halt**
   - Adds `rolling_24h_loss_halt_enabled=True` and `rolling_24h_loss_halt_usdt=6.0`.
   - `build_plan()` now blocks new entries with `rolling_24h_loss_halt` when the current UID's last-24h net realized PnL breaches the limit.
   - UTC-day daily halt remains as a separate guard.

2. **Fill/order/lane attribution**
   - New fills persist `ordId`, `clOrdId`, `tag`, `order_role`, `fill_role`, `sleeve`, `strategy_lane`, `exit_style`, and `decision_kind`.
   - `sync_fills()` joins OKX fills back to `decisions.jsonl` by order IDs when possible.
   - Unknown fills are classified conservatively by OKX hedge-mode `posSide + side + fillPnl`.

3. **Candle-rescore reselection**
   - After preliminary alt candidates are candle-rescored, live cycle reruns sleeve-aware selection.
   - This prevents confirmed/high-score candidates from staying behind stale preliminary seed order.

4. **Tight-stop notional cap**
   - Alt candidates with `stop_pct < 1.2%` are capped at `60U` notional.
   - This prevents very tight stops from expanding notional size and fee/noise exposure.

5. **Maincoin starvation diagnostics**
   - Live cycle emits `candidate_diagnostics.maincoin_starvation_reason`.
   - This distinguishes router permission wait from true maincoin candidate starvation.

6. **Fill-sync fail-closed**
   - If live fill sync fails, live cycle now returns `fill_sync_failed_fail_closed` before market snapshot/candidate planning/execution.
   - New orders are not allowed from stale local fills when loss-halt depends on recent realized PnL.

## Risk stance

Unchanged from v1.3.0:

- `max_total_positions = 6`
- `max_positions_per_sleeve = 3`
- `single_trade_risk_usdt = 1.0`
- `daily_realized_loss_halt_usdt = 6.0`
- `max_orders_per_cycle = 1`
- `max_alt_positions_total = 3`
- `maincoin_reserved_slots = 1`

New guard:

- `rolling_24h_loss_halt_usdt = 6.0`

## Verification

Commands run on live tree:

```bash
cd /root/jarvis-unified
export PYTHONPATH=/root/jarvis-unified
python3 -m compileall -q jarvis_unified scripts/unified tests
python3 -m unittest discover -s tests -v
python3 scripts/unified/unified_account_check.py
python3 scripts/unified/unified_healthcheck.py
JARVIS_UNIFIED_DRY_RUN=1 python3 scripts/unified/unified_live_cycle.py
python3 scripts/unified/unified_guardian.py
```

Result:

- Unit tests: 42 tests OK.
- Account check: OK, UID `851731612504386465`.
- Healthcheck: OK, 3 open positions, 3 protective algos, no issues.
- Dry-run/live wrapper: v1.3.1 active; new entries blocked by `rolling_24h_loss_halt`.

## Deployment note

Production Hermes wrappers were smoke-tested. Guardian live wrapper produced no action results; live-cycle wrapper did not open new orders because rolling 24h loss halt blocked plans.

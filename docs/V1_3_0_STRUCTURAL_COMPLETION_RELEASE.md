# Matrix Account v1.3.0 — Structural Completion + Alt Logic Repair

Date: 2026-06-18

## Release intent

v1.3.0 completes the Matrix account structure without increasing risk parameters. It keeps v1.2.0 controlled-growth limits but repairs the two strategic weaknesses observed in live trading:

1. The system was still walking on the altcoin leg while maincoin capacity/range logic was underdeveloped.
2. The active altcoin leg generated float profits but did not consistently convert them into realized profits or clean lane-level attribution.

## Risk posture

Unchanged from v1.2.0:

- `max_total_positions = 6`
- `max_positions_per_sleeve = 3`
- `single_trade_risk_usdt = 1.00`
- `daily_realized_loss_halt_usdt = 6.00`
- `max_orders_per_cycle = 1`

New structural constraints:

- `max_maincoin_positions_total = 3`
- `max_alt_positions_total = 3`
- `maincoin_reserved_slots = 1`

## Main changes

### 1. Maincoin / alt capacity split

`risk_execution.build_plan()` now evaluates family-level budgets before the global cap:

- maincoin family cap;
- alt family cap;
- reserved maincoin slot protection;
- then hard global max-position cap.

This prevents high-beta alt candidates from monopolizing all Matrix slots.

### 2. Maincoin range lane

`candidates.maincoin_range_candidates()` adds a conservative BTC/ETH range strategy for:

- `btc_compression_ema99`
- `btc_range_alt_dispersion`

The lane only generates candidates near MA20 range edges and respects router directional permissions. It does not grid, martingale, average down, or open from the middle of the range.

### 3. Alt lane classification

`Candidate` now carries:

- `strategy_lane`
- `exit_style`

Current lanes include:

- `maincoin_trend`
- `maincoin_range`
- `alt_trend`
- `alt_fast_probe`

Alt long is no longer implicitly treated as a trend lane outside risk-on. Alt short remains trend-capable in risk-off but needs candle follow-through before live readiness.

### 4. Sleeve-aware candidate selection

`live_cycle._select_candidates()` interleaves sleeves instead of pure global score sorting. This ensures maincoin candidates enter the planning window instead of being starved by volatile alt scores. Alt preliminary candidates still require candle rescore and remain blocked by `build_plan()` until confirmed.

### 5. Guardian MFE/time-state protection

Guardian keeps the existing v1.2.0 R thresholds, but now records:

- `opened_ts`
- `max_r_multiple`

New logic:

- MFE giveback full-close candidate when a position previously achieved meaningful R and gives most of it back.
- Time stop candidate when a position has no follow-through after the configured holding window.
- Generation reset when the same `instId:posSide` is closed and reopened with a materially different entry price, preventing stale `opened_ts/max_r/initial_stop` from contaminating a new position.

## Verification

Commands run in `/root/jarvis-unified`:

```bash
export PYTHONPATH=/root/jarvis-unified
python3 -m compileall -q jarvis_unified scripts/unified tests
python3 -m unittest discover -s tests -v
python3 scripts/unified/unified_account_check.py
JARVIS_UNIFIED_DRY_RUN=1 python3 scripts/unified/unified_live_cycle.py
python3 scripts/unified/unified_guardian.py
python3 scripts/unified/unified_healthcheck.py
```

Observed results:

- Compile: OK
- Unit tests: 37/37 OK
- Account check: OK, UID `851731612504386465`
- Dry-run live cycle: OK, v1.3.0 snapshot emitted
- Guardian dry-run: OK, all 3 positions protected
- Healthcheck: OK, issues=[]

## Deployment notes

Live cycle was paused during code edits and should be resumed after verification. Guardian remains enabled. High-frequency output remains local-only.

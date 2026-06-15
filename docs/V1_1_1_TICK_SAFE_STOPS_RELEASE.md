# Matrix Account v1.1.1 — Tick-Safe Stops Hotfix

Date: 2026-06-15

## Executive verdict

v1.1.1 is a targeted live-execution hotfix for OKX stop trigger price formatting/precision.

The strategy was not fully idle from overly strict thresholds: when BTC impulse and alt breadth improved, Matrix generated live-ready `alt_long` plans, but the exchange rejected attached stop-loss parameters on micro-price contracts with `Parameter slTriggerPx error`.

## Root cause

- Entry `build_plan()` computed stop prices with Python float math.
- `execute_plan()` sent attached SL as `str(round(plan.stop_px, 8))`.
- Micro-price contracts such as SATS/BONK can require more precise OKX `tickSz` alignment than 8 decimals.
- Rounding to 8 decimals could change or truncate the valid trigger price, causing OKX rejection.

## Fix

- Added `q_up()` Decimal helper.
- Entry attached stops now read instrument `tickSz` and quantize:
  - long protective stop: floor/down to tick;
  - short protective stop: ceil/up to tick.
- `ExecutionPlan` now carries `stop_px_str`, a normal decimal string for OKX payloads.
- `execute_plan()` no longer uses `round(stop_px, 8)` for attached SL.
- Guardian breakeven / lock-profit stop moves are also tick-quantized.
- Size strings on affected paths avoid Decimal scientific notation.

## Version

- `CFG.version = 1.1.1`
- `CFG.strategy_tag = matrix_v1_1_1_tick_safe_stops`

## Verification

Commands run on live tree:

```bash
cd /root/jarvis-unified
export PYTHONPATH=/root/jarvis-unified
python3 -m compileall -q jarvis_unified scripts/unified tests
python3 -m unittest discover -s tests -v
python3 scripts/unified/unified_account_check.py
JARVIS_UNIFIED_DRY_RUN=1 python3 scripts/unified/unified_live_cycle.py
python3 scripts/unified/unified_healthcheck.py
```

Results:

- 24 unit tests passed.
- Account UID guard passed for UID `851731612504386465`.
- Dry-run live cycle completed under v1.1.1.
- Healthcheck returned `ok=true` and no issues.
- Post-change audit found no remaining production `round(stop_px, 8)` path.

## Residual risk

The OKX client write methods still trust upstream callers for tick-safe stop inputs. Current Matrix entry and guardian paths are covered, but future write paths should use a centralized stop builder or require pre-quantized stop strings.

# Unified Jarvis v0.3.0 — Complete Light-Live Router Push

## Scope

v0.3.0 responds to Sir's direction to push the unified strategy closer to the full planned system while keeping the unified account around 100U for 1–2 days of live observation. This is a controlled aggressiveness and closed-loop completeness release, not a 200U+ capital migration release.

## What changed

### 1. Parameter release from over-conservative v0.2.0

- `max_total_positions`: 2 → 3
- `max_positions_per_sleeve`: 1 → 2
- `max_margin_usage_pct`: 0.35 → 0.45
- `single_trade_risk_usdt`: 0.30 → 0.45
- `daily_realized_loss_halt_usdt`: 1.50 → 2.20
- `leverage_default`: 3 → 4
- `leverage_hard_cap`: 6 → 8
- new `min_live_candidate_score = 72.0`
- new `max_same_symbol_positions = 1`

Interpretation: data collection speed is increased, but not by removing the account survival rails. The system can sample more than one sleeve/candidate in a live phase while still capping daily loss and duplicate-symbol concentration.

### 2. Router phase capacity increased

- `btc_impulse`: risk ceiling 0.42, max positions 3
- `risk_off_alt_decay`: risk ceiling 0.32, max positions 2
- `btc_range_alt_dispersion`: risk ceiling 0.30, max positions 2
- `btc_compression_ema99`: still defensive, max positions 1
- `crash`: risk ceiling 0, no new entries

### 3. Added execution guardrails for the wider parameters

- Duplicate live symbol blocks a new entry: `duplicate_symbol_position`.
- Per-sleeve position cap blocks over-concentration: `sleeve_position_cap_reached`.
- Candle-rescored candidates still need to clear `min_live_candidate_score`.
- Existing UID guard, daily loss halt, ctVal/lotSz/minSz sizing, attached SL, and guardian exits remain active.

### 4. Added independent healthcheck

New files:

- `jarvis_unified/healthcheck.py`
- `scripts/unified/unified_healthcheck.py`

Healthcheck verifies:

- account UID/mainUid guard
- cold-context freshness
- live-cycle snapshot freshness
- guardian snapshot freshness
- open positions have protective stop algos
- risk parameters are within allowed sanity bounds

This closes a key missing loop: after increasing live sampling speed, the system now has a separate read-only watchdog for stale context, stale cycles, and unprotected positions.

### 5. Daily combined brief upgraded

`reports.py` now references the active `CFG.version` and includes healthcheck status when available.

## Non-goals

- No automatic transfer of Mi/v4 funds into Unified.
- No LLM in hot path.
- No pyramiding or high-frequency rotation.
- No removal of daily loss or SL/guardian rails.

## Verification

Required verification before deployment:

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

Live deployment resumes the existing live-cycle and guardian cron jobs after verification. A new local-only healthcheck cron should run every 120 minutes.

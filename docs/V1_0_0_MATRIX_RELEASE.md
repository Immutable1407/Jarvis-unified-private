# Matrix Account v1.0.0 — Full-Market 2×2 Router Release

Date: 2026-06-15
Account: OKX Unified / Matrix subaccount `uid=851731612504386465`, label `Combination`

## Release intent

Sir has transferred the independent Mi maincoin and v4 altcoin balances into the Unified account. Unified is now renamed operationally to the **Matrix Account（矩阵账户）** and becomes the single OKX perpetual full-market strategy system.

The goal changes from “prove the 100U system can survive” to “aggressively validate the 2×2 full-market matrix while keeping hard kill-switch style risk boundaries”.

## 2×2 matrix

The router now treats four sleeves as first-class execution lanes:

1. `maincoin_long` — BTC/ETH/SOL/BNB trend/impulse longs.
2. `maincoin_short` — BTC/ETH/SOL/BNB weak-structure shorts.
3. `alt_long` — OKX altcoin momentum/dispersion longs.
4. `alt_short` — OKX altcoin weak-market/risk-off shorts.

Router outputs sleeve permissions; it does not create orders. Candidate scoring, candle-rescore, risk sizing, UID guard, duplicate-symbol guard, per-sleeve caps, daily-loss halt, order sizing, attached stop-loss, guardian, and healthcheck remain downstream gates.

## Parameter release for ~220U capital

v0.3.0 was light-live around 100U. v1.0.0 opens parameters for the now-funded Matrix account:

- Max total positions: `3 → 5`
- Max positions per sleeve: `2` retained, now applied to each of the four directional sleeves
- Max margin usage ceiling: `45% → 65%` of account equity, additionally capped by router phase risk ceiling
- Single trade risk budget: `0.45U → 0.75U`, also capped by `0.6%` of equity
- Daily realized loss halt: `2.20U → 4.50U`
- Default leverage: `4x → 5x`
- Hard leverage cap: `8x → 10x`
- Live candidate score threshold: `72 → 70`
- Alt scan width: `60 → 100` seed rows, still candle-rescored before live readiness

## Router phase capacity

- `btc_impulse`: maincoin_long and alt_long primary, risk ceiling `0.55`, max positions `5`.
- `risk_off_alt_decay`: alt_short primary and maincoin_short probe, risk ceiling `0.42`, max positions `4`.
- `btc_range_alt_dispersion`: alt_long and alt_short probes, directional maincoin probe depending on breadth, risk ceiling `0.40`, max positions `4`.
- `btc_compression_ema99`: all sleeves probe-only where breadth supports it, risk ceiling `0.32`, max positions `3`.
- `crash`: no new entries.
- `no_edge`: no new entries.

Cold context modifiers can reduce or slightly bias score/risk; they still cannot create a live direction or bypass router permissions.

## Safety invariants retained

- UID/mainUid guard before private account actions.
- No LLM in live order path.
- Seed-only alt candidates remain preliminary until candle-rescore confirms.
- Duplicate live symbol blocked (`max_same_symbol_positions=1`).
- Per-sleeve cap prevents all capacity being consumed by one branch.
- Daily realized loss halt is account-scoped by UID.
- Position guardian remains responsible for stop protection, breakeven, TP1, lock-profit, and full close.
- Healthcheck independently verifies account, snapshots, cold context, protection, and risk bounds.

## Verification run

Executed from `/root/jarvis-unified`:

```bash
export PYTHONPATH=/root/jarvis-unified
python3 -m compileall -q jarvis_unified scripts/unified tests
python3 -m unittest discover -s tests -v
python3 scripts/unified/unified_account_check.py
python3 scripts/unified/unified_collect_context.py
JARVIS_UNIFIED_DRY_RUN=1 python3 scripts/unified/unified_live_cycle.py
python3 scripts/unified/unified_guardian.py
python3 scripts/unified/unified_healthcheck.py
```

Result at deployment check:

- Account check: OK, uid `851731612504386465`, balance about `221.77U`, no positions.
- Unit tests: 15/15 OK.
- Dry live cycle: version `1.0.0`, phase `no_edge`, no order candidate, no live write.
- Guardian: OK, zero positions, zero algos.
- Healthcheck: OK, zero issues.

## Operational note

The old Mi and v4 accounts are now archived experiments. Their crons are paused and their repos receive final archive commits. Daily and weekly reporting should focus on Matrix v1.0.0 only.

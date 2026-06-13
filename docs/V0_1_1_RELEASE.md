# Unified Jarvis v0.1.1 — Router Risk Cap + Account-Scoped Ledger Guardrails

Date: 2026-06-13

## Scope

Patch release over v0.1.0 live-light bootstrap. No live order-path expansion; no leverage or global position increase.

## Fixes

1. **Router risk ceiling is enforced in execution planning**
   - `build_plan()` now caps max margin by `min(CFG.max_margin_usage_pct, decision.total_risk_ceiling)`.
   - If router ceiling is zero, planning fails closed with `router_risk_ceiling_zero`.
   - This prevents Market Phase Router risk output from being merely observational.

2. **Fills and daily loss halt are account-scoped**
   - `sync_fills()` verifies account and persists `uid`, `mainUid`, profile, and strategy tag on every fill row.
   - `daily_realized_pnl()` ignores rows with a different UID, preventing cross-account ledger pollution from triggering or masking daily-loss halts.
   - Decision ledger records include expected UID/mainUid.

3. **Guardian flags unprotected live positions**
   - `guardian_check()` now fails-observable with `unprotected_position` when an open position has no matching protective algo.
   - v0.1.1 still does not move stops automatically; it improves detection rather than adding hidden execution behavior.

## Verification

```bash
python3 -m compileall -q jarvis_unified scripts/unified tests
python3 -m unittest discover -s tests -v
python3 scripts/unified/unified_account_check.py
python3 scripts/unified/unified_collect_context.py
JARVIS_UNIFIED_DRY_RUN=1 python3 scripts/unified/unified_live_cycle.py
python3 scripts/unified/unified_guardian.py
```

Observed: 6 tests passed. Account check OK. Dry-run live cycle did not execute and reported no live-ready candidate / max positions. Guardian saw current protected position and returned `issues=[]`.

## Residual observation

`unified_collect_context.py` still records `onchainos_signal_chains` degradation with OKX API `50114 Invalid Authority`; current modifiers remain usable, but cold context permissions should be revisited if Sir wants OKX on-chain signal-chain data active.
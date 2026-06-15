# Matrix Account v1.1.0 — Hygiene, Cooldown, and Attribution Release

Date: 2026-06-15

## Purpose

v1.1.0 is a targeted operational-hardening release after the Matrix Account audit. It does not expand leverage, risk per trade, or maximum positions. It fixes configuration drift, reduces historical-data contamination risk, adds post-stopout churn control, and improves daily attribution.

## Changes

1. **Version and tag**
   - `CFG.version = 1.1.0`
   - `CFG.strategy_tag = matrix_v1_1_0_matrix_hygiene_attribution`

2. **Alt universe width**
   - `alt_universe_limit = 100`
   - `snapshot_market()` now uses the config value instead of hardcoded 80.
   - `alt_candidates()` already scans `uni[:100]`; v1.1.0 makes live data and docs consistent.

3. **Fill ledger contamination defense**
   - `sync_fills()` dedupes by `uid:tradeId`, not bare `tradeId`.
   - New fills continue to persist UID/mainUid/profile/strategy_tag.

4. **Stopout cooldown**
   - Negative realized fill PnL creates a 6h symbol cooldown in `data/runtime/state/stopout_cooldowns.json`.
   - `build_plan()` blocks new entries for symbols under active cooldown.
   - This is intentionally fail-closed for churn control and does not affect existing guardian exits.

5. **Daily report refresh and attribution**
   - `combined_brief()` refreshes live cycle in dry-run mode and healthcheck before reading snapshots.
   - Daily brief includes near-7-day sleeve PnL / fees / raw fill counts.

6. **Cron context**
   - Weekly Matrix summary should load `jarvis-matrix-trading`, not historical `jarvis-altcoin-trading`.

## Risk impact

- No additional capital exposure.
- No hot-path LLM.
- No change to max positions, leverage, or single-trade risk.
- New cooldown may reduce trade frequency after losses, which is intentional.

## Verification

Required commands before deployment:

```bash
cd /root/jarvis-unified
export PYTHONPATH=/root/jarvis-unified
python3 -m compileall -q jarvis_unified scripts/unified tests
python3 -m unittest discover -s tests -v
python3 scripts/unified/unified_account_check.py
JARVIS_UNIFIED_DRY_RUN=1 python3 scripts/unified/unified_live_cycle.py
python3 scripts/unified/unified_guardian.py
python3 scripts/unified/unified_healthcheck.py
```

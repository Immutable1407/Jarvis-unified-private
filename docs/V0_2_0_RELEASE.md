# Unified Jarvis v0.2.0 — Guardian TP / breakeven / lock-profit

## Scope

Minor release that upgrades the guardian from protection audit-only to local position protection management. No LLM is used in the hot path and no new live entry path was added.

## Guardian policy

For each protected live SWAP position, guardian computes `R` from:

- `entry_px`: OKX position average/open entry price.
- `initial_stop_px`: first persisted stop for that `instId:posSide` (or the current protective algo stop on first sight).
- Current price: position `markPx` when available.

Actions are one-way improvements only:

- `+0.8R`: move stop loss to breakeven.
- `+1.5R`: reduce-only market close of 50% once (`TP1`).
- `+2.0R`: move stop to lock at least `+0.5R`.
- `+3.0R`: reduce-only market full close once. When this threshold is reached before lower milestones have executed, guardian prioritizes full close only to avoid sending overlapping partial/full reduce-only orders in the same cycle.

TP/SL state is persisted in `data/runtime/state/guardian_tp_state.json` so TP1/full-close do not repeat. Dry-run evaluation does not mark actions as completed.

## Safety guarantees

- OKX UID/mainUid guard remains enforced through `client.assert_account()`.
- OKX write paths still require `JARVIS_UNIFIED_LIVE_TRADING=true`.
- Guardian defaults to dry-run from `scripts/unified/unified_guardian.py`.
- Live guardian protective writes require both:
  - `JARVIS_UNIFIED_GUARDIAN_LIVE=1`
  - `JARVIS_UNIFIED_LIVE_TRADING=true`
- Partial and full closes use reduce-only market orders.
- Stop replacement places the improved reduce-only stop first, then cancels the older/worse stop only after the replacement is accepted. Duplicate protection is preferable to a temporary no-stop window.
- Position sizing for TP/full close is quantized with OKX `lotSz` and checked against `minSz`.

## Configuration

Added config fields:

- `guardian_tp_state_file`
- `guardian_be_r`
- `guardian_tp1_r`
- `guardian_tp1_fraction`
- `guardian_lock_r`
- `guardian_lock_profit_r`
- `guardian_full_close_r`

Version/tag updated to:

- `version = 0.2.0`
- `strategy_tag = unified_v0_2_0_guardian_tp_breakeven_lock`

## Verification

Safe verification commands only:

```bash
cd /root/jarvis-unified
export PYTHONPATH=/root/jarvis-unified
python3 -m compileall -q jarvis_unified scripts/unified tests
python3 -m unittest discover -s tests -v
```

Do not run live entry scripts for this release. Do not run live guardian writes unless explicitly approved.

# Matrix Account v1.2.0 — Controlled Growth Upgrade

Release date: 2026-06-16

## Executive summary

v1.2.0 is the first controlled-growth release after the v1.1.1 tick-safe stop hotfix. It does **not** switch the system to full-speed/turbo mode. It implements the first four steps of the growth path:

1. fix and regression-test guardian stop-move payloads;
2. add post-order protective stop confirmation after live entries;
3. record high-score opportunity blocks for later opportunity-loss analysis;
4. open a controlled-growth parameter profile.

The release is designed to increase capacity without removing the core survival rails.

## Version identity

- `CFG.version = 1.2.0`
- `CFG.strategy_tag = matrix_v1_2_0_controlled_growth`
- `CFG.growth_mode = controlled_growth`

## Controlled-growth parameters

- `max_total_positions = 6`
- `max_positions_per_sleeve = 3`
- `max_margin_usage_pct = 0.75`
- `single_trade_risk_usdt = 1.00`
- `daily_realized_loss_halt_usdt = 6.00`
- `leverage_default = 5`
- `leverage_hard_cap = 10`
- `min_live_candidate_score = 70.0`
- `alt_universe_limit = 120`
- `candle_rescore_top_n = 16`
- `max_orders_per_cycle = 1`
- `stopout_cooldown_hours = 6`

Router phase caps were also moved one step wider:

- `risk_off_alt_decay`: max positions 4 → 5, risk ceiling 0.42 → 0.50 before cold-context multiplier.
- `btc_impulse`: max positions 5 → 6, risk ceiling 0.55 → 0.62 before cold-context multiplier.
- `btc_range_alt_dispersion`: max positions 4 → 5, risk ceiling 0.40 → 0.45 before cold-context multiplier.

## Guardian stop-move fix

`OKXClient.place_stop_algo()` now uses OKX protective stop fields:

- `slTriggerPx`
- `slOrdPx = -1`
- `slTriggerPxType = mark`

This replaces the generic `triggerPx/orderPx` payload that can be rejected by OKX with `50015: Either parameter tpTriggerPx or slTriggerPx is required`.

The release keeps the existing safety ordering: place the improved reduce-only stop first, then cancel the older stop only after replacement success.

## Post-order SL confirmation

After a live entry order returns `code=0`, `execute_plan()` now calls `confirm_protective_stop()`:

- reads pending algo stops;
- checks for a matching instrument and position side;
- accepts OKX-normalized stop prices only when the matched protective stop is close to the expected stop price; stale/wildly different stops do not satisfy confirmation;
- records `protection_confirmed=true/false` in the live-order decision.

If the order is placed but no protective stop can be confirmed, the decision kind becomes `live_order_unconfirmed_sl` and the result carries `reason=post_order_sl_confirm_failed`. This is fail-loud: it does not pretend the entry is safely protected.

## Opportunity-loss logging

`live_cycle.py` now records high-score blocked candidates to:

```text
data/runtime/ledgers/opportunity_blocks.jsonl
```

Recorded cases require `score >= opportunity_block_min_score` and blockers such as:

- `sleeve_position_cap_reached`
- `duplicate_symbol_position`
- `stopout_cooldown_until_*`
- `preliminary_candidate_needs_candle_confirm`

These rows are analytics only. They are intended to answer whether sleeve caps/cooldowns are saving the account or causing missed returns.

## Safety boundaries retained

- No LLM in the hot order path.
- Alt seed candidates still require candle-rescore before live execution.
- `min_live_candidate_score` remains 70.
- `max_orders_per_cycle` remains 1 for this first controlled-growth release.
- Stopout cooldown remains 6h.
- Same-symbol duplicate guard remains active.
- Live writes still require UID/mainUid guard and `JARVIS_UNIFIED_LIVE_TRADING=true`.
- Guardian live actions still require `JARVIS_UNIFIED_GUARDIAN_LIVE=1` plus the global live env.

## Verification

Required verification for this release:

```bash
cd /root/jarvis-unified
export PYTHONPATH=/root/jarvis-unified
python3 -m compileall -q jarvis_unified scripts/unified tests
python3 -m unittest discover -s tests -v
python3 scripts/unified/unified_account_check.py
python3 scripts/unified/unified_collect_context.py
JARVIS_UNIFIED_DRY_RUN=1 python3 scripts/unified/unified_live_cycle.py
python3 scripts/unified/unified_guardian.py
python3 scripts/unified/unified_healthcheck.py
```

Regression coverage added:

- controlled-growth config identity and parameters;
- alt candidate engine honors configured universe width;
- guardian stop algo payload uses `slTriggerPx/slOrdPx`;
- post-order SL confirmation records unconfirmed protection loudly and rejects stale wrong-price stops;
- opportunity-block ledger records high-score sleeve-cap blocks.

## Known residual risks

- `max_orders_per_cycle` remains 1 deliberately; multi-order cycles should wait for more positive expectancy evidence.
- The system still needs a stronger combination-level total stop-risk aggregator before full-speed growth.
- Opportunity-block rows need 24–72h of data before using them to justify further sleeve-cap expansion.
- OnchainOS may still degrade with `Invalid Authority`; cold context is score/risk modifier only, not a trigger.

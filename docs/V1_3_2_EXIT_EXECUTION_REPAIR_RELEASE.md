# Matrix Account v1.3.2 — Exit Execution Repair

## Release intent

v1.3.2 is an emergency entry/exit-path repair after live evidence showed OKX orders being repeatedly rejected with `51000 Parameter tag error`, including profitable positions reaching guardian full-close thresholds while reduce-only close orders failed.

This release does **not** increase risk, change entry logic, or chase losses. It fixes the deterministic guardian exit execution layer so floating profit can be converted into realized profit according to the existing R-based exit rules.

## Root cause

Guardian correctly evaluated OFC short as above `3R` and emitted `full_close_3r`, but the reduce-only market close carried `tag="jarvis_v131"`. OKX rejected the order with:

```text
sCode=51000
sMsg=Parameter tag error
```

The position remained open even though the exit condition was repeatedly true. Healthcheck also stayed green because it checked protective stops, but did not escalate failed guardian action results.

## Changes

1. **Live entry / guardian close tag repair**
   - Entry orders and guardian reduce-only closes use `tag="jarvisv132"`.
   - If OKX still returns a tag-related `51000`, Jarvis retries once without any tag.
   - The fallback preserves attached-SL entry semantics and reduce-only close semantics; only nonessential metadata is removed.

2. **Guardian action ledgering**
   - Live guardian actions now append `guardian_action` rows to `data/runtime/ledgers/decisions.jsonl`.
   - Both success and failure are persisted with action label, result payload, UID, and mainUid.

3. **Healthcheck fails loud on exit-action failure**
   - `run_healthcheck()` now inspects `guardian_latest.action_results`.
   - Any live guardian action with `ok=false` becomes `guardian_action_failed`.
   - This prevents the system from looking healthy when full-close/TP execution is failing.

4. **Regression tests**
   - Added `test_v132_entry_order_retries_without_tag_on_okx_tag_error`.
   - Added `test_v132_guardian_reduce_only_retries_without_tag_on_okx_tag_error`.
   - Added `test_v132_healthcheck_flags_guardian_action_failure`.

## Live verification

After tests passed, the live guardian wrapper was run once with explicit live authorization.

Result:

- Action: `full_close_3r` on `OFC-USDT-SWAP short`.
- Size: `9` contracts.
- Order side: `buy`, reduce-only market.
- OKX result: `code=0`, order placed.
- Order id: `3670164490707410944`.
- Order tag: `jarvisv132`.
- Fills synced: 2 new fills.
- OFC final close realized:
  - `fillPnl = +3.5745 U`
  - fees `-0.009828 U`
  - net `+3.564672 U`
- Post-close account check: `open_positions = 0`, `frozenBal = 0`, `upl = 0`.
- Healthcheck: OK, no issues.

## Verification commands

```bash
cd /root/jarvis-unified
export PYTHONPATH=/root/jarvis-unified JARVIS_UNIFIED_TESTING=1
python3 -m compileall -q jarvis_unified scripts/unified tests
python3 -m unittest discover -s tests -v  # 45 tests OK

export PYTHONPATH=/root/jarvis-unified
python3 scripts/unified/unified_account_check.py
python3 scripts/unified/unified_guardian.py
python3 scripts/unified/unified_healthcheck.py
JARVIS_UNIFIED_DRY_RUN=1 python3 scripts/unified/unified_live_cycle.py
/root/.hermes/scripts/jarvis_unified_guardian.sh
python3 - <<'PY'
from jarvis_unified.ledger_guardian import sync_fills
import json
print(json.dumps(sync_fills(), ensure_ascii=False, indent=2))
PY
python3 scripts/unified/unified_account_check.py
python3 scripts/unified/unified_healthcheck.py
```

## Risk stance

Unchanged from v1.3.1/v1.3.0:

- `max_total_positions = 6`
- `max_positions_per_sleeve = 3`
- `single_trade_risk_usdt = 1.0`
- `daily_realized_loss_halt_usdt = 6.0`
- `rolling_24h_loss_halt_usdt = 6.0`
- `max_orders_per_cycle = 1`
- `tight_stop_notional_cap_usdt = 60.0`

v1.3.2 is an execution-safety patch, not a strategy expansion.

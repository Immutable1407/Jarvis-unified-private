from __future__ import annotations
import json, time
from dataclasses import asdict
from .config import CFG, ensure_dirs
from .okx_client import OKXClient
from .market_data import snapshot_market, InstrumentCache
from .context import load_cold_context
from .router import decide, save_router_snapshot
from .candidates import all_candidates, promote_with_candles
from .risk_execution import build_plan, execute_plan
from .ledger_guardian import sync_fills

def run_live_cycle(dry_run: bool = False) -> dict:
    ensure_dirs(); client=OKXClient(); acct=client.assert_account()
    InstrumentCache().load(client)
    sync=sync_fills(client)
    market=snapshot_market(client)
    ctx=load_cold_context()
    decision=decide(market, ctx)
    save_router_snapshot(decision, market)
    raw_cands=all_candidates(market, decision)
    # Promote only the top few preliminary alt candidates by fresh candle rescore to control API cost.
    cands=[]
    for c in raw_cands[:12]:
        try:
            cands.append(promote_with_candles(client, c))
        except Exception as exc:
            c.reason.append(f"candle_rescore_error:{type(exc).__name__}"); cands.append(c)
    cands=sorted(cands, key=lambda x:x.score, reverse=True)
    bal=client.balance(); pos=client.positions()
    plans=[]; executed=None
    for cand in cands[:10]:
        plan=build_plan(client, cand, bal, pos, decision)
        plans.append(asdict(plan))
        if plan.ok:
            executed=execute_plan(client, plan, dry_run=dry_run)
            break
    if executed is None:
        executed={"executed": False, "reason": "no_live_ready_candidate", "plans_checked": len(plans)}
    out={"ts": time.time(), "version": CFG.version, "account": {"uid": acct.get("uid"), "label": acct.get("label")}, "sync": sync, "router": asdict(decision), "candidate_count": len(cands), "top_candidates": [asdict(c) for c in cands[:8]], "plans": plans[:8], "execution": executed}
    (CFG.data_dir/"state"/"live_cycle_latest.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out

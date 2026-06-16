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


def _record_opportunity_blocks(plans: list[dict], decision: object) -> dict:
    """Persist high-quality candidates blocked by risk/cap gates for later opportunity-loss review."""
    ensure_dirs()
    min_score = float(getattr(CFG, "opportunity_block_min_score", 85.0))
    interesting = {"sleeve_position_cap_reached", "duplicate_symbol_position", "preliminary_candidate_needs_candle_confirm"}
    rows=[]
    for plan in plans:
        if plan.get("ok"):
            continue
        cand = plan.get("candidate") or {}
        reason = str(plan.get("reason") or "")
        score = float(cand.get("score") or 0)
        if score < min_score:
            continue
        if not (reason.startswith("stopout_cooldown_until_") or reason in interesting):
            continue
        row = {
            "ts": time.time(),
            "version": CFG.version,
            "strategy_tag": CFG.strategy_tag,
            "uid": CFG.expected_uid,
            "kind": "opportunity_block",
            "reason": reason,
            "candidate": cand,
            "router_phase": getattr(decision, "market_phase", ""),
            "sleeve_permissions": getattr(decision, "sleeve_permissions", {}),
        }
        rows.append(row)
    if rows:
        path = CFG.data_dir / "ledgers" / "opportunity_blocks.jsonl"
        with path.open("a", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return {"recorded": len(rows), "min_score": min_score, "reasons": {r["reason"]: sum(1 for x in rows if x["reason"] == r["reason"]) for r in rows}}

def run_live_cycle(dry_run: bool = False, *, sync_fills_enabled: bool = True, record_decisions: bool = True) -> dict:
    ensure_dirs(); client=OKXClient(); acct=client.assert_account()
    InstrumentCache().load(client)
    sync=sync_fills(client) if sync_fills_enabled else {"ok": True, "skipped": "sync_fills_disabled"}
    market=snapshot_market(client)
    ctx=load_cold_context()
    decision=decide(market, ctx)
    save_router_snapshot(decision, market)
    raw_cands=all_candidates(market, decision)
    # Promote only the top few preliminary alt candidates by fresh candle rescore to control API cost.
    cands=[]
    rescore_n = int(getattr(CFG, "candle_rescore_top_n", 12))
    for c in raw_cands[:rescore_n]:
        try:
            cands.append(promote_with_candles(client, c))
        except Exception as exc:
            c.reason.append(f"candle_rescore_error:{type(exc).__name__}"); cands.append(c)
    cands=sorted(cands, key=lambda x:x.score, reverse=True)
    bal=client.balance(); pos=client.positions()
    plans=[]; executions=[]
    max_orders = max(1, int(getattr(CFG, "max_orders_per_cycle", 1)))
    for cand in cands[:10]:
        plan=build_plan(client, cand, bal, pos, decision)
        plans.append(asdict(plan))
        if plan.ok and len(executions) < max_orders:
            executions.append(execute_plan(client, plan, dry_run=dry_run, record=record_decisions))
            if not dry_run:
                pos=client.positions()
            if len(executions) >= max_orders:
                break
    opportunity_blocks = _record_opportunity_blocks(plans, decision) if record_decisions else {"recorded": 0, "skipped": "record_decisions_disabled"}
    executed = executions[0] if len(executions) == 1 else ({"executed": False, "reason": "no_live_ready_candidate", "plans_checked": len(plans)} if not executions else {"executed": True, "count": len(executions), "results": executions})
    out={"ts": time.time(), "version": CFG.version, "strategy_tag": CFG.strategy_tag, "growth_mode": getattr(CFG, "growth_mode", "unknown"), "account": {"uid": acct.get("uid"), "label": acct.get("label")}, "sync": sync, "router": asdict(decision), "candidate_count": len(cands), "top_candidates": [asdict(c) for c in cands[:8]], "plans": plans[:8], "opportunity_blocks": opportunity_blocks, "execution": executed}
    (CFG.data_dir/"state"/"live_cycle_latest.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out

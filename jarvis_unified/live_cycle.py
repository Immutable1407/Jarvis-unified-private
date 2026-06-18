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


def _sleeve_order(decision: object) -> list[str]:
    phase = getattr(decision, "market_phase", "")
    if phase in {"risk_off_alt_decay", "crash"}:
        return ["maincoin_short", "alt_short", "maincoin_long", "alt_long"]
    if phase == "btc_impulse":
        return ["maincoin_long", "alt_long", "maincoin_short", "alt_short"]
    return ["maincoin_long", "maincoin_short", "alt_long", "alt_short"]


def _select_candidates(raw_cands: list, decision: object) -> list:
    if getattr(CFG, "live_selection_mode", "sleeve_interleave") != "sleeve_interleave":
        return sorted(raw_cands, key=lambda x: x.score, reverse=True)
    per_sleeve = max(1, int(getattr(CFG, "max_candidates_per_sleeve_per_cycle", 3)))
    buckets = {s: [] for s in getattr(CFG, "sleeve_names", ("maincoin_long", "maincoin_short", "alt_long", "alt_short"))}
    for c in sorted(raw_cands, key=lambda x: x.score, reverse=True):
        buckets.setdefault(c.sleeve, []).append(c)
    selected=[]
    for sleeve in _sleeve_order(decision):
        selected.extend(buckets.get(sleeve, [])[:per_sleeve])
    seen=set(); out=[]
    for c in selected:
        key=(c.inst_id, c.side)
        if key in seen:
            continue
        seen.add(key); out.append(c)
    # Append overflow by score for diagnostics only; plan loop still caps at top 10.
    for c in sorted(raw_cands, key=lambda x: x.score, reverse=True):
        key=(c.inst_id, c.side)
        if key not in seen:
            seen.add(key); out.append(c)
    return out


def _candidate_diagnostics(raw_all: list, selected: list, decision: object) -> dict:
    sleeves = {}
    for c in raw_all:
        row = sleeves.setdefault(c.sleeve, {"raw": 0, "selected": 0, "top_score": 0.0})
        row["raw"] += 1
        row["top_score"] = max(row["top_score"], float(c.score))
    for c in selected:
        row = sleeves.setdefault(c.sleeve, {"raw": 0, "selected": 0, "top_score": 0.0})
        row["selected"] += 1
    main_raw = sum(v.get("raw", 0) for k, v in sleeves.items() if str(k).startswith("maincoin"))
    perms = getattr(decision, "sleeve_permissions", {}) or {}
    reason = "maincoin_candidates_present" if main_raw else "maincoin_absent"
    if not main_raw and perms.get("maincoin_long") == "wait" and perms.get("maincoin_short") == "wait":
        reason = "maincoin_router_permissions_wait"
    return {"sleeves": sleeves, "maincoin_raw_candidates": main_raw, "maincoin_starvation_reason": reason, "permissions": perms}

def run_live_cycle(dry_run: bool = False, *, sync_fills_enabled: bool = True, record_decisions: bool = True) -> dict:
    ensure_dirs(); client=OKXClient(); acct=client.assert_account()
    sync=sync_fills(client) if sync_fills_enabled else {"ok": True, "skipped": "sync_fills_disabled"}
    if sync_fills_enabled and sync.get("ok") is not True:
        out={"ts": time.time(), "version": CFG.version, "strategy_tag": CFG.strategy_tag, "growth_mode": getattr(CFG, "growth_mode", "unknown"), "account": {"uid": acct.get("uid"), "label": acct.get("label")}, "sync": sync, "router": {}, "candidate_count": 0, "candidate_diagnostics": {"fail_closed": "fill_sync_failed"}, "top_candidates": [], "plans": [], "opportunity_blocks": {"recorded": 0, "skipped": "fill_sync_failed"}, "execution": {"executed": False, "reason": "fill_sync_failed_fail_closed"}}
        (CFG.data_dir/"state"/"live_cycle_latest.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        return out
    InstrumentCache().load(client)
    market=snapshot_market(client)
    ctx=load_cold_context()
    decision=decide(market, ctx)
    save_router_snapshot(decision, market)
    all_raw=all_candidates(market, decision)
    raw_cands=_select_candidates(all_raw, decision)
    # Promote sleeve-aware selected preliminary alt candidates by fresh candle rescore to control API cost without starving maincoin lanes.
    cands=[]
    rescore_n = int(getattr(CFG, "candle_rescore_top_n", 12))
    promoted = 0
    for c in raw_cands:
        if c.preliminary and promoted < rescore_n:
            try:
                cands.append(promote_with_candles(client, c)); promoted += 1
            except Exception as exc:
                c.reason.append(f"candle_rescore_error:{type(exc).__name__}"); cands.append(c); promoted += 1
        else:
            cands.append(c)
    # v1.3.1: candle rescore changes score/preliminary status; re-run sleeve-aware selection so final live-ready candidates are not stuck behind stale seed ordering.
    cands=_select_candidates(cands, decision)
    diagnostics=_candidate_diagnostics(all_raw, cands, decision)
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
    out={"ts": time.time(), "version": CFG.version, "strategy_tag": CFG.strategy_tag, "growth_mode": getattr(CFG, "growth_mode", "unknown"), "account": {"uid": acct.get("uid"), "label": acct.get("label")}, "sync": sync, "router": asdict(decision), "candidate_count": len(cands), "candidate_diagnostics": diagnostics, "top_candidates": [asdict(c) for c in cands[:8]], "plans": plans[:8], "opportunity_blocks": opportunity_blocks, "execution": executed}
    (CFG.data_dir/"state"/"live_cycle_latest.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out

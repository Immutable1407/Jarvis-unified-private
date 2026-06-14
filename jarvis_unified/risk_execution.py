from __future__ import annotations
import json, time
from dataclasses import dataclass, asdict
from decimal import Decimal
from typing import Any
from .config import CFG, ensure_dirs
from .okx_client import d, q_down, OKXClient
from .market_data import InstrumentCache
from .candidates import Candidate

@dataclass
class ExecutionPlan:
    ok: bool
    reason: str
    candidate: dict[str, Any] | None = None
    inst_id: str = ""
    side: str = ""
    pos_side: str = ""
    order_side: str = ""
    entry_px: float = 0.0
    stop_px: float = 0.0
    stop_pct: float = 0.0
    notional_usdt: float = 0.0
    margin_usdt: float = 0.0
    sz: str = "0"
    leverage: int = CFG.leverage_default


def equity_usdt(balance_resp: dict[str, Any]) -> float:
    if balance_resp.get("code") != "0": return 0.0
    data=(balance_resp.get("data") or [{}])[0]
    for detail in data.get("details", []):
        if detail.get("ccy") == "USDT":
            return float(detail.get("eq") or data.get("totalEq") or 0)
    return float(data.get("totalEq") or 0)

def open_positions_count(pos_resp: dict[str, Any]) -> int:
    if pos_resp.get("code") != "0": return 999
    return sum(1 for p in pos_resp.get("data", []) if abs(float(p.get("pos") or 0)) > 0)

def has_duplicate_symbol(pos_resp: dict[str, Any], inst_id: str) -> bool:
    if pos_resp.get("code") != "0":
        return True
    return any(p.get("instId") == inst_id and abs(float(p.get("pos") or 0)) > 0 for p in pos_resp.get("data", []))

def sleeve_for_position(pos: dict[str, Any]) -> str:
    inst = pos.get("instId", "")
    if inst in CFG.allowed_maincoins:
        return "maincoin"
    pos_side = pos.get("posSide") or ("long" if float(pos.get("pos") or 0) > 0 else "short")
    return "alt_long" if pos_side == "long" else "alt_short"

def sleeve_positions_count(pos_resp: dict[str, Any], sleeve: str) -> int:
    if pos_resp.get("code") != "0":
        return 999
    return sum(1 for p in pos_resp.get("data", []) if abs(float(p.get("pos") or 0)) > 0 and sleeve_for_position(p) == sleeve)

def daily_realized_pnl() -> float:
    path=CFG.data_dir/"ledgers"/"fills.jsonl"
    if not path.exists(): return 0.0
    # local ledger net field for today only; account-scoped so another profile's
    # fills cannot trigger or mask the unified subaccount daily-loss halt.
    import datetime as dt
    today=dt.datetime.now(dt.UTC).strftime("%Y-%m-%d")
    total=0.0
    for line in path.read_text().splitlines():
        try: r=json.loads(line)
        except Exception: continue
        uid = str(r.get("uid") or "")
        if uid and uid != str(CFG.expected_uid):
            continue
        if str(r.get("date")) == today:
            total += float(r.get("net_pnl",0) or 0)
    return total

def build_plan(client: OKXClient, cand: Candidate, balance: dict[str, Any], positions: dict[str, Any], decision: Any) -> ExecutionPlan:
    if open_positions_count(positions) >= min(CFG.max_total_positions, decision.max_positions):
        return ExecutionPlan(False, "max_positions_reached")
    if has_duplicate_symbol(positions, cand.inst_id):
        return ExecutionPlan(False, "duplicate_symbol_position", asdict(cand))
    if sleeve_positions_count(positions, cand.sleeve) >= CFG.max_positions_per_sleeve:
        return ExecutionPlan(False, "sleeve_position_cap_reached", asdict(cand))
    if daily_realized_pnl() <= -abs(CFG.daily_realized_loss_halt_usdt):
        return ExecutionPlan(False, "daily_loss_halt")
    eq=equity_usdt(balance)
    if eq <= 0: return ExecutionPlan(False, "no_equity")
    if cand.preliminary:
        # v0.1.0 seed-only alts are not live-ready until candle rescore module promotes them.
        return ExecutionPlan(False, "preliminary_candidate_needs_candle_confirm", asdict(cand))
    if cand.score < CFG.min_live_candidate_score:
        return ExecutionPlan(False, "score_below_live_threshold", asdict(cand))
    phase_cap = max(0.0, min(float(CFG.max_margin_usage_pct), float(getattr(decision, "total_risk_ceiling", CFG.max_margin_usage_pct) or 0.0)))
    if phase_cap <= 0:
        return ExecutionPlan(False, "router_risk_ceiling_zero", asdict(cand))
    risk_usdt=min(CFG.single_trade_risk_usdt, eq*0.004) * float(decision.context_modifiers.get("total_risk_multiplier",1.0))
    stop_pct=max(CFG.min_stop_pct, min(CFG.max_stop_pct, cand.stop_pct))
    notional=risk_usdt/stop_pct
    max_margin=eq*phase_cap
    lev=min(CFG.leverage_default, CFG.leverage_hard_cap)
    margin=min(max_margin, notional/lev)
    notional=margin*lev
    cache=InstrumentCache(); inst=cache.get(cand.inst_id, client)
    ctval=d(inst.get("ctVal", "1")); lot=d(inst.get("lotSz", "1")); minsz=d(inst.get("minSz", lot))
    price=d(cand.last)
    sz=q_down(d(notional)/(ctval*price), lot)
    if sz < minsz:
        return ExecutionPlan(False, f"size_below_min sz={sz} minSz={minsz}", asdict(cand))
    pos_side="long" if cand.side=="long" else "short"
    order_side="buy" if cand.side=="long" else "sell"
    stop_px = float(price * (Decimal("1")-d(stop_pct))) if cand.side=="long" else float(price*(Decimal("1")+d(stop_pct)))
    return ExecutionPlan(True, "ok", asdict(cand), cand.inst_id, cand.side, pos_side, order_side, float(price), stop_px, stop_pct, float(notional), float(margin), str(sz.normalize()), lev)

def record_decision(kind: str, payload: dict[str, Any]) -> None:
    ensure_dirs(); p=CFG.data_dir/"ledgers"/"decisions.jsonl"
    payload={"ts": time.time(), "kind": kind, "uid": CFG.expected_uid, "mainUid": CFG.expected_main_uid, **payload}
    with p.open("a", encoding="utf-8") as f: f.write(json.dumps(payload, ensure_ascii=False)+"\n")

def execute_plan(client: OKXClient, plan: ExecutionPlan, dry_run: bool = True) -> dict[str, Any]:
    if not plan.ok:
        out={"executed": False, "reason": plan.reason, "plan": asdict(plan)}; record_decision("blocked", out); return out
    if dry_run:
        out={"executed": False, "dry_run": True, "plan": asdict(plan)}; record_decision("dry_run", out); return out
    client.assert_account()
    lev=client.set_leverage(plan.inst_id, plan.leverage, plan.pos_side)
    if lev.get("code") != "0":
        out={"executed": False, "reason":"set_leverage_failed", "response": lev, "plan": asdict(plan)}; record_decision("error", out); return out
    resp=client.place_market(plan.inst_id, plan.order_side, plan.pos_side, plan.sz, sl_px=str(round(plan.stop_px, 8)))
    out={"executed": resp.get("code") == "0", "response": resp, "plan": asdict(plan)}
    record_decision("live_order" if out["executed"] else "order_error", out)
    return out

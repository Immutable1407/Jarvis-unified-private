from __future__ import annotations
import json, time
from dataclasses import dataclass, asdict
from decimal import Decimal
from typing import Any
from .config import CFG, ensure_dirs
from .okx_client import d, q_down, q_up, OKXClient
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
    stop_px_str: str = ""


def fmt_dec(x: Decimal) -> str:
    return format(x.normalize(), "f")

def quantize_stop_price(price: Decimal, tick_sz: Decimal, side: str) -> Decimal:
    # For a protective long stop below entry, round toward safety/down.
    # For a protective short stop above entry, round toward safety/up.
    return q_down(price, tick_sz) if side == "long" else q_up(price, tick_sz)

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
    pos_side = pos.get("posSide") or ("long" if float(pos.get("pos") or 0) > 0 else "short")
    if inst in CFG.allowed_maincoins:
        return "maincoin_long" if pos_side == "long" else "maincoin_short"
    return "alt_long" if pos_side == "long" else "alt_short"

def sleeve_positions_count(pos_resp: dict[str, Any], sleeve: str) -> int:
    if pos_resp.get("code") != "0":
        return 999
    return sum(1 for p in pos_resp.get("data", []) if abs(float(p.get("pos") or 0)) > 0 and sleeve_for_position(p) == sleeve)


def family_for_sleeve(sleeve: str) -> str:
    return "maincoin" if str(sleeve).startswith("maincoin") else "alt"


def family_positions_count(pos_resp: dict[str, Any], family: str) -> int:
    if pos_resp.get("code") != "0":
        return 999
    return sum(1 for p in pos_resp.get("data", []) if abs(float(p.get("pos") or 0)) > 0 and family_for_sleeve(sleeve_for_position(p)) == family)


def family_budget_reason(pos_resp: dict[str, Any], cand: Candidate, decision: Any) -> str | None:
    """v1.3.0 family cap/reserve check.

    Keeps Matrix capacity from being consumed entirely by high-beta alts while
    preserving the existing global max-position and per-sleeve caps.
    """
    total_open = open_positions_count(pos_resp)
    hard_cap = min(int(getattr(CFG, "max_total_positions", 6)), int(getattr(decision, "max_positions", 6) or 0))
    family = family_for_sleeve(cand.sleeve)
    if family == "maincoin":
        if family_positions_count(pos_resp, "maincoin") >= int(getattr(CFG, "max_maincoin_positions_total", 3)):
            return "maincoin_family_cap_reached"
        return None
    alt_count = family_positions_count(pos_resp, "alt")
    if alt_count >= int(getattr(CFG, "max_alt_positions_total", 3)):
        return "alt_family_cap_reached"
    reserve = int(getattr(CFG, "maincoin_reserved_slots", 0))
    main_count = family_positions_count(pos_resp, "maincoin")
    if reserve > 0 and main_count < reserve and total_open >= max(0, hard_cap - (reserve - main_count)):
        return "maincoin_reserved_slot_protected"
    return None


def stopout_cooldown_path() -> Any:
    return CFG.data_dir / "state" / "stopout_cooldowns.json"

def load_stopout_cooldowns(now: float | None = None) -> dict[str, Any]:
    now = time.time() if now is None else now
    p = stopout_cooldown_path()
    if not p.exists():
        return {"version": CFG.version, "symbols": {}}
    try:
        raw = json.loads(p.read_text())
        if not isinstance(raw, dict) or not isinstance(raw.get("symbols", {}), dict):
            raise ValueError("invalid cooldown state shape")
    except Exception as exc:
        return {"version": CFG.version, "symbols": {}, "state_error": f"{type(exc).__name__}: {exc}"}
    syms = raw.get("symbols", {})
    active = {k:v for k,v in syms.items() if float(v.get("until_ts", 0) or 0) > now}
    return {"version": raw.get("version", CFG.version), "updated_ts": raw.get("updated_ts"), "symbols": active}

def cooldown_active(inst_id: str, now: float | None = None) -> dict[str, Any] | None:
    state = load_stopout_cooldowns(now)
    if state.get("state_error"):
        return {"state_error": state["state_error"], "until_ts": 0}
    return state.get("symbols", {}).get(inst_id)

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
        if uid != str(CFG.expected_uid):
            continue
        if str(r.get("date")) == today:
            total += float(r.get("net_pnl",0) or 0)
    return total

def build_plan(client: OKXClient, cand: Candidate, balance: dict[str, Any], positions: dict[str, Any], decision: Any) -> ExecutionPlan:
    if has_duplicate_symbol(positions, cand.inst_id):
        return ExecutionPlan(False, "duplicate_symbol_position", asdict(cand))
    cd = cooldown_active(cand.inst_id)
    if cd:
        if cd.get("state_error"):
            return ExecutionPlan(False, "stopout_cooldown_state_unreadable_fail_closed", asdict(cand))
        return ExecutionPlan(False, f"stopout_cooldown_until_{int(float(cd.get('until_ts', 0) or 0))}", asdict(cand))
    if sleeve_positions_count(positions, cand.sleeve) >= CFG.max_positions_per_sleeve:
        return ExecutionPlan(False, "sleeve_position_cap_reached", asdict(cand))
    if cand.preliminary:
        # v1.1.0 seed-only alts are not live-ready until candle rescore module promotes them.
        return ExecutionPlan(False, "preliminary_candidate_needs_candle_confirm", asdict(cand))
    if cand.score < CFG.min_live_candidate_score:
        return ExecutionPlan(False, "score_below_live_threshold", asdict(cand))
    fam_reason = family_budget_reason(positions, cand, decision)
    if fam_reason:
        return ExecutionPlan(False, fam_reason, asdict(cand))
    if open_positions_count(positions) >= min(CFG.max_total_positions, decision.max_positions):
        return ExecutionPlan(False, "max_positions_reached", asdict(cand))
    if daily_realized_pnl() <= -abs(CFG.daily_realized_loss_halt_usdt):
        return ExecutionPlan(False, "daily_loss_halt")
    eq=equity_usdt(balance)
    if eq <= 0: return ExecutionPlan(False, "no_equity")
    phase_cap = max(0.0, min(float(CFG.max_margin_usage_pct), float(getattr(decision, "total_risk_ceiling", CFG.max_margin_usage_pct) or 0.0)))
    if phase_cap <= 0:
        return ExecutionPlan(False, "router_risk_ceiling_zero", asdict(cand))
    risk_usdt=min(CFG.single_trade_risk_usdt, eq*0.006) * float(decision.context_modifiers.get("total_risk_multiplier",1.0))
    stop_pct=max(CFG.min_stop_pct, min(CFG.max_stop_pct, cand.stop_pct))
    notional=risk_usdt/stop_pct
    max_margin=eq*phase_cap
    lev=min(CFG.leverage_default, CFG.leverage_hard_cap)
    margin=min(max_margin, notional/lev)
    notional=margin*lev
    cache=InstrumentCache(); inst=cache.get(cand.inst_id, client)
    ctval=d(inst.get("ctVal", "1")); lot=d(inst.get("lotSz", "1")); minsz=d(inst.get("minSz", lot)); tick=d(inst.get("tickSz", "0.00000001"))
    price=d(cand.last)
    sz=q_down(d(notional)/(ctval*price), lot)
    if sz < minsz:
        return ExecutionPlan(False, f"size_below_min sz={sz} minSz={minsz}", asdict(cand))
    pos_side="long" if cand.side=="long" else "short"
    order_side="buy" if cand.side=="long" else "sell"
    raw_stop = price * (Decimal("1")-d(stop_pct)) if cand.side=="long" else price*(Decimal("1")+d(stop_pct))
    stop_dec = quantize_stop_price(raw_stop, tick, cand.side)
    stop_px_str = fmt_dec(stop_dec)
    return ExecutionPlan(True, "ok", asdict(cand), cand.inst_id, cand.side, pos_side, order_side, float(price), float(stop_dec), stop_pct, float(notional), float(margin), fmt_dec(sz), lev, stop_px_str)

def record_decision(kind: str, payload: dict[str, Any]) -> None:
    ensure_dirs(); p=CFG.data_dir/"ledgers"/"decisions.jsonl"
    payload={"ts": time.time(), "kind": kind, "uid": CFG.expected_uid, "mainUid": CFG.expected_main_uid, **payload}
    with p.open("a", encoding="utf-8") as f: f.write(json.dumps(payload, ensure_ascii=False)+"\n")

def _algo_stop_px(a: dict[str, Any]) -> Decimal | None:
    for k in ("slTriggerPx", "triggerPx", "moveTriggerPx"):
        if a.get(k) not in (None, "", "0", 0):
            return d(a[k])
    return None


def confirm_protective_stop(client: OKXClient, inst_id: str, pos_side: str, expected_stop_px: str, *, attempts: int | None = None, delay_sec: float | None = None) -> dict[str, Any]:
    """Confirm a live protective stop exists after entry.

    This is a post-order safety check only. It never places/cancels orders; if
    confirmation fails, callers must fail loud so guardian/healthcheck can stop
    new risk until protection is verified.
    """
    attempts = int(attempts if attempts is not None else getattr(CFG, "post_order_sl_confirm_attempts", 3))
    delay_sec = float(delay_sec if delay_sec is not None else getattr(CFG, "post_order_sl_confirm_delay_sec", 1.0))
    expected = d(expected_stop_px)
    last_resp: dict[str, Any] | None = None
    matches: list[dict[str, Any]] = []
    for i in range(max(1, attempts)):
        if i > 0 and delay_sec > 0:
            time.sleep(delay_sec)
        resp = client.algo_orders()
        last_resp = resp
        if resp.get("code") not in {"0", "207"}:
            continue
        for row in resp.get("data", []) or []:
            if row.get("instId") != inst_id:
                continue
            row_side = row.get("posSide") or row.get("pos_side") or ""
            if row_side not in ("", pos_side):
                continue
            stop_px = _algo_stop_px(row)
            if stop_px is None:
                continue
            matches.append(row)
            tolerance = max(abs(expected) * Decimal("0.005"), Decimal("0.000000000001"))
            # OKX may normalize at exchange precision, but a wildly different
            # stale stop must not satisfy post-order protection confirmation.
            if abs(stop_px - expected) <= tolerance:
                return {"ok": True, "attempt": i + 1, "expected_stop_px": str(expected), "matched_stop_px": str(stop_px), "matched_algo": row}
    return {"ok": False, "attempts": max(1, attempts), "expected_stop_px": str(expected), "matches": matches, "last_response": last_resp}


def execute_plan(client: OKXClient, plan: ExecutionPlan, dry_run: bool = True, record: bool = True) -> dict[str, Any]:
    if not plan.ok:
        out={"executed": False, "reason": plan.reason, "plan": asdict(plan)};
        if record: record_decision("blocked", out)
        return out
    if dry_run:
        out={"executed": False, "dry_run": True, "plan": asdict(plan)};
        if record: record_decision("dry_run", out)
        return out
    client.assert_account()
    lev=client.set_leverage(plan.inst_id, plan.leverage, plan.pos_side)
    if lev.get("code") != "0":
        out={"executed": False, "reason":"set_leverage_failed", "response": lev, "plan": asdict(plan)}; record_decision("error", out); return out
    resp=client.place_market(plan.inst_id, plan.order_side, plan.pos_side, plan.sz, sl_px=plan.stop_px_str or fmt_dec(d(plan.stop_px)))
    order_ok = resp.get("code") == "0"
    sl_confirm = None
    if order_ok:
        sl_confirm = confirm_protective_stop(client, plan.inst_id, plan.pos_side, plan.stop_px_str or fmt_dec(d(plan.stop_px)))
    out={"executed": order_ok, "response": resp, "post_order_sl_confirm": sl_confirm, "protection_confirmed": bool(sl_confirm and sl_confirm.get("ok")), "plan": asdict(plan)}
    if order_ok and not out["protection_confirmed"]:
        out["reason"] = "post_order_sl_confirm_failed"
    kind = "live_order" if order_ok and out["protection_confirmed"] else ("live_order_unconfirmed_sl" if order_ok else "order_error")
    record_decision(kind, out)
    return out

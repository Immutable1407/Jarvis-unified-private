from __future__ import annotations
import json, time, datetime as dt
from decimal import Decimal
from typing import Any
from .config import CFG, ensure_dirs
from .market_data import InstrumentCache
from .okx_client import OKXClient, d, q_down, q_up


def _fill_key(uid: str, trade_id: str | None) -> str:
    return f"{uid}:{trade_id or ''}"

def _cooldown_path():
    return CFG.data_dir / "state" / "stopout_cooldowns.json"

def _load_cooldowns(now: float | None = None) -> dict[str, Any]:
    now = time.time() if now is None else now
    p = _cooldown_path()
    if not p.exists():
        return {"version": CFG.version, "symbols": {}}
    try:
        raw = json.loads(p.read_text())
        if not isinstance(raw, dict) or not isinstance(raw.get("symbols", {}), dict):
            raise ValueError("invalid cooldown state shape")
    except Exception:
        return {"version": CFG.version, "symbols": {}}
    syms = raw.get("symbols", {})
    active = {k:v for k,v in syms.items() if float(v.get("until_ts", 0) or 0) > now}
    return {"version": raw.get("version", CFG.version), "updated_ts": raw.get("updated_ts"), "symbols": active}

def _save_cooldowns(raw: dict[str, Any]) -> None:
    raw["version"] = CFG.version
    raw["updated_ts"] = time.time()
    _cooldown_path().write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

def _update_stopout_cooldown_from_fill(rec: dict[str, Any], cooldowns: dict[str, Any], *, from_fill_ts: bool = False) -> bool:
    pnl = float(rec.get("fillPnl") or 0)
    inst = rec.get("instId")
    if not inst or pnl >= 0:
        return False
    base_ts = time.time()
    if from_fill_ts:
        try:
            raw_ts = float(rec.get("ts") or 0)
            base_ts = raw_ts / 1000 if raw_ts > 1e12 else raw_ts
        except Exception:
            base_ts = time.time()
    until = base_ts + float(getattr(CFG, "stopout_cooldown_hours", 6)) * 3600
    if until <= time.time():
        return False
    syms = cooldowns.setdefault("symbols", {})
    prev = syms.get(inst, {})
    if float(prev.get("until_ts", 0) or 0) >= until:
        return False
    syms[inst] = {
        "until_ts": until,
        "reason": "negative_realized_fill",
        "last_tradeId": rec.get("tradeId"),
        "last_fillPnl": pnl,
        "posSide": rec.get("posSide"),
        "side": rec.get("side"),
    }
    return True

def rebuild_stopout_cooldowns_from_ledger(now: float | None = None) -> dict[str, Any]:
    now = time.time() if now is None else now
    path = CFG.data_dir / "ledgers" / "fills.jsonl"
    cooldowns = {"version": CFG.version, "symbols": {}}
    before = 0
    if path.exists():
        for line in path.read_text().splitlines():
            try: rec = json.loads(line)
            except Exception: continue
            uid = str(rec.get("uid") or "")
            if uid != str(CFG.expected_uid):
                continue
            _update_stopout_cooldown_from_fill(rec, cooldowns, from_fill_ts=True)
    after = len(cooldowns.get("symbols", {}))
    if after or before:
        _save_cooldowns(cooldowns)
    return {"active_symbols": after, "added_or_extended": max(0, after-before), "path": str(_cooldown_path())}

def sync_fills(client: OKXClient | None = None) -> dict:
    ensure_dirs(); client = client or OKXClient()
    acct = client.assert_account()
    r=client.fills(100)
    if r.get("code") != "0": return {"ok": False, "error": r}
    path=CFG.data_dir/"ledgers"/"fills.jsonl"
    uid = str(acct.get("uid") or CFG.expected_uid)
    seen=set()
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                old=json.loads(line); seen.add(_fill_key(str(old.get("uid") or ""), old.get("tradeId")))
            except Exception: pass
    cooldowns=_load_cooldowns()
    cooldown_updates=0
    new=0
    with path.open("a", encoding="utf-8") as f:
        for x in r.get("data", []):
            tid=x.get("tradeId") or x.get("billId")
            if _fill_key(uid, tid) in seen: continue
            ts=int(x.get("ts") or time.time()*1000)
            date=dt.datetime.fromtimestamp(ts/1000, dt.UTC).strftime("%Y-%m-%d")
            fee=float(x.get("fee") or 0); pnl=float(x.get("fillPnl") or 0)
            rec={"date": date, "tradeId": tid, "ts": ts, "uid": acct.get("uid"), "mainUid": acct.get("mainUid"), "profile": CFG.okx_profile, "strategy_tag": CFG.strategy_tag, "instId": x.get("instId"), "side": x.get("side"), "posSide": x.get("posSide"), "fillSz": x.get("fillSz"), "fillPx": x.get("fillPx"), "fee": fee, "fillPnl": pnl, "net_pnl": pnl+fee, "raw": x}
            if _update_stopout_cooldown_from_fill(rec, cooldowns): cooldown_updates += 1
            f.write(json.dumps(rec, ensure_ascii=False)+"\n"); new+=1
    if cooldown_updates:
        _save_cooldowns(cooldowns)
    rebuild = rebuild_stopout_cooldowns_from_ledger()
    return {"ok": True, "new": new, "total_seen": len(seen)+new, "dedupe": "uid_tradeId", "cooldown_updates": cooldown_updates, "cooldown_rebuild": rebuild}


def _state_path():
    return CFG.data_dir / "state" / getattr(CFG, "guardian_tp_state_file", "guardian_tp_state.json")


def _load_state() -> dict[str, Any]:
    p = _state_path()
    if not p.exists(): return {"version": getattr(CFG, "version", "0.3.0"), "positions": {}}
    try:
        raw = json.loads(p.read_text())
        raw.setdefault("positions", {})
        return raw
    except Exception:
        return {"version": getattr(CFG, "version", "0.3.0"), "positions": {}}


def _save_state(state: dict[str, Any]) -> None:
    state["version"] = getattr(CFG, "version", "0.3.0")
    state["updated_ts"] = time.time()
    _state_path().write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _pos_side(p: dict[str, Any]) -> str:
    if p.get("posSide") in {"long", "short"}: return p["posSide"]
    return "long" if d(p.get("pos") or 0) > 0 else "short"


def _close_side(pos_side: str) -> str:
    return "sell" if pos_side == "long" else "buy"


def _current_px(p: dict[str, Any]) -> Decimal:
    for k in ("markPx", "last", "idxPx", "avgPx"):
        if p.get(k) not in (None, "", "0", 0):
            return d(p[k])
    return Decimal("0")


def _entry_px(p: dict[str, Any]) -> Decimal:
    for k in ("avgPx", "openAvgPx", "entryPx"):
        if p.get(k) not in (None, "", "0", 0):
            return d(p[k])
    return Decimal("0")


def _algo_stop_px(a: dict[str, Any]) -> Decimal | None:
    for k in ("slTriggerPx", "triggerPx", "moveTriggerPx"):
        if a.get(k) not in (None, "", "0", 0):
            return d(a[k])
    return None


def _matching_algos(algo_rows: list[dict[str, Any]], inst: str, pos_side: str) -> list[dict[str, Any]]:
    return [a for a in algo_rows if a.get("instId") == inst and (a.get("posSide") in (None, "", pos_side) or a.get("posSide") == pos_side)]


def _is_better_stop(pos_side: str, new_stop: Decimal, old_stop: Decimal | None) -> bool:
    if old_stop is None: return True
    return new_stop > old_stop if pos_side == "long" else new_stop < old_stop


def _r_multiple(pos_side: str, entry: Decimal, initial_stop: Decimal, current: Decimal) -> Decimal | None:
    risk = abs(entry - initial_stop)
    if risk <= 0 or current <= 0: return None
    favorable = current - entry if pos_side == "long" else entry - current
    return favorable / risk


def _stop_at_r(pos_side: str, entry: Decimal, initial_stop: Decimal, lock_r: Decimal) -> Decimal:
    risk = abs(entry - initial_stop)
    return entry + risk * lock_r if pos_side == "long" else entry - risk * lock_r


def _quantize_stop_price(px: Decimal, inst: dict[str, Any], pos_side: str) -> Decimal:
    tick = d(inst.get("tickSz", "0.00000001"))
    return q_down(px, tick) if pos_side == "long" else q_up(px, tick)

def _fmt_dec(x: Decimal) -> str:
    return format(x.normalize(), "f")


def _quantize_size(inst: dict[str, Any], raw_sz: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    lot = d(inst.get("lotSz", "1")); minsz = d(inst.get("minSz", lot))
    return q_down(raw_sz, lot), lot, minsz


def _position_key(inst: str, pos_side: str) -> str:
    return f"{inst}:{pos_side}"


def evaluate_guardian_actions(p: dict[str, Any], algo_rows: list[dict[str, Any]], state_rec: dict[str, Any], inst: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Pure guardian state machine. Returns (updated_state_rec, evaluation)."""
    inst_id = p.get("instId", "")
    pos_side = _pos_side(p)
    pos_sz = abs(d(p.get("pos") or 0))
    current = _current_px(p)
    entry = d(state_rec.get("entry_px") or 0) or _entry_px(p)
    algos = _matching_algos(algo_rows, inst_id, pos_side)
    current_stop = None
    stop_algo = None
    for a in algos:
        sp = _algo_stop_px(a)
        if sp is not None:
            if current_stop is None or _is_better_stop(pos_side, sp, current_stop):
                current_stop, stop_algo = sp, a
    initial_stop = d(state_rec.get("initial_stop_px") or 0) if state_rec.get("initial_stop_px") else current_stop
    if not state_rec:
        state_rec = {}
    state_rec.update({"instId": inst_id, "posSide": pos_side, "entry_px": _fmt_dec(entry) if entry else "0", "last_pos": _fmt_dec(pos_sz)})
    if initial_stop is not None:
        state_rec.setdefault("initial_stop_px", _fmt_dec(initial_stop))
    if current_stop is not None:
        state_rec["last_stop_px"] = _fmt_dec(current_stop)
    r_mult = _r_multiple(pos_side, entry, initial_stop, current) if initial_stop is not None else None
    actions=[]
    if r_mult is not None:
        if r_mult >= d(CFG.guardian_full_close_r) and not state_rec.get("full_close_done"):
            close_sz, lot, minsz = _quantize_size(inst, pos_sz)
            if close_sz >= minsz:
                actions.append({"type": "full_close", "label": "full_close_3r", "sz": _fmt_dec(close_sz), "side": _close_side(pos_side), "reduce_only": True})
        if not actions:
            # Emit at most one stop-move per cycle: choose the highest applicable
            # protective stop.  Placing both BE and lock stops in the same cycle
            # creates unnecessary duplicate/cancel churn.
            stop_action = None
            if r_mult >= d(CFG.guardian_lock_r) and not state_rec.get("lock_done"):
                lock_stop = _quantize_stop_price(_stop_at_r(pos_side, entry, initial_stop, d(CFG.guardian_lock_profit_r)), inst, pos_side)
                if _is_better_stop(pos_side, lock_stop, current_stop):
                    stop_action = {"type": "move_stop", "label": "lock_0_5r", "stop_px": _fmt_dec(lock_stop)}
            elif r_mult >= d(CFG.guardian_be_r) and not state_rec.get("be_done"):
                be_stop = _quantize_stop_price(entry, inst, pos_side)
                if _is_better_stop(pos_side, be_stop, current_stop):
                    stop_action = {"type": "move_stop", "label": "breakeven", "stop_px": _fmt_dec(be_stop)}
            if stop_action:
                actions.append(stop_action)
            if r_mult >= d(CFG.guardian_tp1_r) and not state_rec.get("tp1_done"):
                tp_sz, lot, minsz = _quantize_size(inst, pos_sz * d(CFG.guardian_tp1_fraction))
                if tp_sz >= minsz and tp_sz < pos_sz:
                    actions.append({"type": "partial_close", "label": "tp1_50pct", "sz": _fmt_dec(tp_sz), "side": _close_side(pos_side), "reduce_only": True})
    eval_out = {"instId": inst_id, "posSide": pos_side, "entry_px": _fmt_dec(entry) if entry else "0", "current_px": _fmt_dec(current), "initial_stop_px": _fmt_dec(initial_stop) if initial_stop is not None else None, "current_stop_px": _fmt_dec(current_stop) if current_stop is not None else None, "r_multiple": float(r_mult) if r_mult is not None else None, "actions": actions, "stop_algo": stop_algo or {}}
    return state_rec, eval_out


def _apply_action(client: OKXClient, p: dict[str, Any], eval_out: dict[str, Any], action: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    inst_id = p.get("instId", ""); pos_side = _pos_side(p); side = _close_side(pos_side); pos_sz = _fmt_dec(abs(d(p.get("pos") or 0)))
    if dry_run:
        return {"dry_run": True, "action": action}
    if action["type"] == "move_stop":
        # Safety-first ordering: place the improved reduce-only stop first, then
        # cancel the older/worse stop only after the replacement is accepted. A
        # duplicate protective stop is preferable to a temporary no-stop window.
        algo_id = (eval_out.get("stop_algo") or {}).get("algoId")
        place_resp = client.place_stop_algo(inst_id, side, pos_side, pos_sz, action["stop_px"])
        cancel_resp = None
        if place_resp.get("code") == "0" and algo_id:
            cancel_resp = client.cancel_algo_order(inst_id, algo_id)
        return {"place": place_resp, "cancel": cancel_resp, "ok": place_resp.get("code") == "0"}
    if action["type"] in {"partial_close", "full_close"}:
        resp = client.place_reduce_only_market(inst_id, action["side"], pos_side, action["sz"])
        return {"order": resp, "ok": resp.get("code") == "0"}
    return {"ok": False, "error": "unknown_action", "action": action}


def guardian_check(client: OKXClient | None = None, dry_run: bool = True) -> dict:
    ensure_dirs(); client=client or OKXClient(); client.assert_account()
    pos=client.positions(); algos=client.algo_orders()
    issues=[]; action_results=[]; evaluations=[]
    if pos.get("code") != "0": issues.append({"type":"positions_error","resp":pos})
    if algos.get("code") not in {"0","207"}: issues.append({"type":"algos_error","resp":algos})
    open_pos=[p for p in pos.get("data",[]) if abs(float(p.get("pos") or 0))>0] if pos.get("code") == "0" else []
    algo_rows = algos.get("data", []) if algos.get("code") in {"0", "207"} else []
    protective_rows = [a for a in algo_rows if _algo_stop_px(a) is not None]
    protected = {(a.get("instId"), a.get("posSide") or a.get("pos_side") or "") for a in protective_rows}
    protected_inst = {a.get("instId") for a in protective_rows if not (a.get("posSide") or a.get("pos_side"))}
    state = _load_state(); state_positions = state.setdefault("positions", {})
    live_keys=set()
    cache = InstrumentCache()
    for p in open_pos:
        inst = p.get("instId")
        side = _pos_side(p)
        key = _position_key(inst, side); live_keys.add(key)
        if (inst, side) not in protected and inst not in protected_inst:
            issues.append({"type": "unprotected_position", "instId": inst, "posSide": side, "pos": p.get("pos")})
            continue
        try:
            instrument = cache.get(inst, client)
            rec, ev = evaluate_guardian_actions(p, algo_rows, state_positions.get(key, {}), instrument)
            state_positions[key] = rec; evaluations.append(ev)
            for action in ev["actions"]:
                result = _apply_action(client, p, ev, action, dry_run=dry_run)
                action_results.append({"instId": inst, "posSide": side, "action": action, "result": result})
                if result.get("ok"):
                    if action["type"] == "move_stop":
                        rec["last_stop_px"] = action["stop_px"]
                        if action["label"] == "breakeven": rec["be_done"] = True
                        if action["label"] == "lock_0_5r": rec["lock_done"] = True
                    if action["type"] == "partial_close": rec["tp1_done"] = True
                    if action["type"] == "full_close": rec["full_close_done"] = True
                    rec["last_action_ts"] = time.time()
        except Exception as exc:
            issues.append({"type": "guardian_eval_error", "instId": inst, "posSide": side, "error": str(exc)})
    for key in list(state_positions.keys()):
        if key not in live_keys:
            state_positions.pop(key, None)
    _save_state(state)
    out={"ok": not issues, "dry_run": dry_run, "ts": time.time(), "open_positions": open_pos, "algo_count": len(algo_rows), "issues": issues, "evaluations": evaluations, "action_results": action_results}
    (CFG.data_dir/"state"/"guardian_latest.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out

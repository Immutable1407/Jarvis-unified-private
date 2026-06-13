from __future__ import annotations
from dataclasses import dataclass, asdict, replace
from typing import Any
from .config import CFG
from .market_data import stats_for

@dataclass
class Candidate:
    sleeve: str
    inst_id: str
    side: str  # long|short
    score: float
    reason: list[str]
    last: float
    stop_pct: float
    preliminary: bool = False


def maincoin_candidates(market: dict[str, Any], permission: str, delta: float = 0) -> list[Candidate]:
    if permission == "wait": return []
    out=[]
    for inst, s in market.get("maincoin", {}).items():
        ch4, ch24, last = float(s.get("change_4h",0)), float(s.get("change_24h",0)), float(s.get("last",0))
        ma20, ma99, atr = float(s.get("ma20_1h",0)), float(s.get("ma99_1h",0)), float(s.get("atr_pct_15m",0))
        if not last: continue
        score=50+delta; reason=[]; side=None
        if ch4 > 0.006 and last > ma20 and ch24 > -0.01:
            side="long"; score += min(18, ch4*900); reason += ["maincoin_positive_structure"]
        elif ch4 < -0.006 and last < ma20:
            side="short"; score += min(18, abs(ch4)*900); reason += ["maincoin_negative_structure"]
        if ma99 and abs(last-ma99)/last < 0.012:
            score -= 4; reason.append("ema99_fake_breakout_caution")
        if atr > 0.018:
            score -= 8; reason.append("high_atr_derisk")
        if side and score >= (58 if permission == "active" else 62):
            out.append(Candidate("maincoin", inst, side, round(score,2), reason, last, max(CFG.min_stop_pct, min(CFG.max_stop_pct, atr*1.8 or 0.012))))
    return sorted(out, key=lambda c:c.score, reverse=True)

def alt_candidates(market: dict[str, Any], long_perm: str, short_perm: str, long_delta: float = 0, short_delta: float = 0) -> list[Candidate]:
    out=[]
    uni=market.get("alt_universe", [])
    for row in uni[:60]:
        inst, chg, last = row["instId"], float(row["chg24h"]), float(row["last"])
        vol=float(row.get("vol",0))
        if vol < 500000 or not last: continue
        if long_perm != "wait" and chg > 0.035:
            score=52+min(22, chg*240)+long_delta
            if score >= (62 if long_perm=="active" else 68):
                out.append(Candidate("alt_long", inst, "long", round(score,2), ["seed_strength_needs_candle_confirm"], last, 0.018, preliminary=True))
        if short_perm != "wait" and chg < -0.035:
            score=52+min(22, abs(chg)*240)+short_delta
            if score >= (62 if short_perm=="active" else 68):
                out.append(Candidate("alt_short", inst, "short", round(score,2), ["seed_weakness_needs_candle_confirm"], last, 0.018, preliminary=True))
    return sorted(out, key=lambda c:c.score, reverse=True)

def promote_with_candles(client: Any, cand: Candidate) -> Candidate:
    """Promote seed-only alt candidate after live candle rescore. Fail closed by keeping preliminary=True."""
    if not cand.preliminary or cand.sleeve == "maincoin":
        return cand
    s=stats_for(client, cand.inst_id)
    score=cand.score; reasons=list(cand.reason)+["candle_rescore"]
    if cand.side == "short":
        if s.change_1h < -0.006: score += 4; reasons.append("short_1h_followthrough")
        if s.change_4h < -0.018: score += 5; reasons.append("short_4h_followthrough")
        if s.last < s.ma20_15m: score += 4; reasons.append("below_ma20_15m")
        if s.funding > 0: score += 2; reasons.append("positive_funding_weak_price")
        confirmed = score >= 72 and s.change_1h < -0.002 and s.last < s.ma20_15m
    else:
        if s.change_1h > 0.006: score += 4; reasons.append("long_1h_followthrough")
        if s.change_4h > 0.018: score += 5; reasons.append("long_4h_followthrough")
        if s.last > s.ma20_15m: score += 4; reasons.append("above_ma20_15m")
        if s.funding < 0.0005: score += 1; reasons.append("funding_not_overheated")
        confirmed = score >= 72 and s.change_1h > 0.002 and s.last > s.ma20_15m
    stop=max(CFG.min_stop_pct, min(CFG.max_stop_pct, s.atr_pct_15m*1.8 or cand.stop_pct))
    return Candidate(cand.sleeve, cand.inst_id, cand.side, round(score,2), reasons if confirmed else reasons+["candle_confirm_failed"], s.last or cand.last, stop, preliminary=not confirmed)

def all_candidates(market: dict[str, Any], decision: Any) -> list[Candidate]:
    mods=decision.context_modifiers or {}
    c=[]
    c += maincoin_candidates(market, decision.maincoin_permission, float(mods.get("maincoin_score_delta",0)))
    c += alt_candidates(market, decision.alt_long_permission, decision.alt_short_permission, float(mods.get("alt_long_score_delta",0)), float(mods.get("alt_short_score_delta",0)))
    return sorted(c, key=lambda x:x.score, reverse=True)

from __future__ import annotations
from dataclasses import dataclass, asdict, replace
from typing import Any
from .config import CFG
from .market_data import stats_for

PERM_RANK = {"wait": 0, "probe_only": 1, "active": 2}

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


def _score_threshold(permission: str, active_threshold: float, probe_threshold: float) -> float:
    return active_threshold if permission == "active" else probe_threshold


def maincoin_candidates(market: dict[str, Any], long_permission: str, short_permission: str, delta: float = 0) -> list[Candidate]:
    out=[]
    for inst, s in market.get("maincoin", {}).items():
        ch4, ch24, last = float(s.get("change_4h",0)), float(s.get("change_24h",0)), float(s.get("last",0))
        ma20, ma99, atr = float(s.get("ma20_1h",0)), float(s.get("ma99_1h",0)), float(s.get("atr_pct_15m",0))
        if not last:
            continue
        base=50+delta
        caution=[]
        if ma99 and abs(last-ma99)/last < 0.012:
            caution.append("ema99_fake_breakout_caution")
        if atr > 0.018:
            caution.append("high_atr_derisk")

        if long_permission != "wait" and ch4 > 0.006 and last > ma20 and ch24 > -0.01:
            score=base + min(20, ch4*950)
            reasons=["maincoin_long_positive_structure", *caution]
            if "ema99_fake_breakout_caution" in caution: score -= 4
            if "high_atr_derisk" in caution: score -= 8
            if score >= _score_threshold(long_permission, 58, 62):
                out.append(Candidate("maincoin_long", inst, "long", round(score,2), reasons, last, max(CFG.min_stop_pct, min(CFG.max_stop_pct, atr*1.8 or 0.012))))

        if short_permission != "wait" and CFG.allow_maincoin_short and ch4 < -0.006 and last < ma20:
            score=base + min(20, abs(ch4)*950)
            reasons=["maincoin_short_negative_structure", *caution]
            if "ema99_fake_breakout_caution" in caution: score -= 2
            if atr > 0.024: score -= 6; reasons.append("extreme_atr_short_caution")
            if score >= _score_threshold(short_permission, 59, 63):
                out.append(Candidate("maincoin_short", inst, "short", round(score,2), reasons, last, max(CFG.min_stop_pct, min(CFG.max_stop_pct, atr*1.9 or 0.012))))
    return sorted(out, key=lambda c:c.score, reverse=True)


def alt_candidates(market: dict[str, Any], long_perm: str, short_perm: str, long_delta: float = 0, short_delta: float = 0) -> list[Candidate]:
    out=[]
    uni=market.get("alt_universe", [])
    for row in uni[:int(getattr(CFG, "alt_universe_limit", 100))]:
        inst, chg, last = row["instId"], float(row["chg24h"]), float(row["last"])
        vol=float(row.get("vol",0))
        if vol < 500000 or not last: continue
        if long_perm != "wait" and chg > 0.030:
            score=52+min(24, chg*260)+long_delta
            if score >= (60 if long_perm=="active" else 66):
                out.append(Candidate("alt_long", inst, "long", round(score,2), ["seed_strength_needs_candle_confirm"], last, 0.018, preliminary=True))
        if short_perm != "wait" and CFG.allow_alt_short and chg < -0.030:
            score=52+min(24, abs(chg)*260)+short_delta
            if score >= (60 if short_perm=="active" else 66):
                out.append(Candidate("alt_short", inst, "short", round(score,2), ["seed_weakness_needs_candle_confirm"], last, 0.018, preliminary=True))
    return sorted(out, key=lambda c:c.score, reverse=True)


def promote_with_candles(client: Any, cand: Candidate) -> Candidate:
    """Promote seed-only alt candidate after live candle rescore. Fail closed by keeping preliminary=True."""
    if not cand.preliminary or cand.sleeve in {"maincoin_long", "maincoin_short", "maincoin"}:
        return cand
    s=stats_for(client, cand.inst_id)
    score=cand.score; reasons=list(cand.reason)+["candle_rescore"]
    if cand.side == "short":
        if s.change_1h < -0.005: score += 4; reasons.append("short_1h_followthrough")
        if s.change_4h < -0.015: score += 5; reasons.append("short_4h_followthrough")
        if s.last < s.ma20_15m: score += 4; reasons.append("below_ma20_15m")
        if s.funding > 0: score += 2; reasons.append("positive_funding_weak_price")
        confirmed = score >= CFG.min_live_candidate_score and s.change_1h < -0.002 and s.last < s.ma20_15m
    else:
        if s.change_1h > 0.005: score += 4; reasons.append("long_1h_followthrough")
        if s.change_4h > 0.015: score += 5; reasons.append("long_4h_followthrough")
        if s.last > s.ma20_15m: score += 4; reasons.append("above_ma20_15m")
        if s.funding < 0.0005: score += 1; reasons.append("funding_not_overheated")
        confirmed = score >= CFG.min_live_candidate_score and s.change_1h > 0.002 and s.last > s.ma20_15m
    stop=max(CFG.min_stop_pct, min(CFG.max_stop_pct, s.atr_pct_15m*1.8 or cand.stop_pct))
    return Candidate(cand.sleeve, cand.inst_id, cand.side, round(score,2), reasons if confirmed else reasons+["candle_confirm_failed"], s.last or cand.last, stop, preliminary=not confirmed)


def all_candidates(market: dict[str, Any], decision: Any) -> list[Candidate]:
    mods=decision.context_modifiers or {}
    main_long_perm=getattr(decision, "maincoin_long_permission", getattr(decision, "maincoin_permission", "wait"))
    main_short_perm=getattr(decision, "maincoin_short_permission", "wait")
    c=[]
    c += maincoin_candidates(market, main_long_perm, main_short_perm, float(mods.get("maincoin_score_delta",0)))
    c += alt_candidates(market, decision.alt_long_permission, decision.alt_short_permission, float(mods.get("alt_long_score_delta",0)), float(mods.get("alt_short_score_delta",0)))
    return sorted(c, key=lambda x:x.score, reverse=True)

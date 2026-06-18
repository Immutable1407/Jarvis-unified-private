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
    # v1.3.0: lane tells reports/guardian which logic generated the trade.
    strategy_lane: str = ""
    exit_style: str = "trend"


def _score_threshold(permission: str, active_threshold: float, probe_threshold: float) -> float:
    return active_threshold if permission == "active" else probe_threshold


def _stop_from_atr(atr: float, mult: float = 1.8, fallback: float = 0.012) -> float:
    return max(CFG.min_stop_pct, min(CFG.max_stop_pct, atr * mult or fallback))


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
                out.append(Candidate("maincoin_long", inst, "long", round(score,2), reasons, last, _stop_from_atr(atr), strategy_lane="maincoin_trend", exit_style="trend"))

        if short_permission != "wait" and CFG.allow_maincoin_short and ch4 < -0.006 and last < ma20:
            score=base + min(20, abs(ch4)*950)
            reasons=["maincoin_short_negative_structure", *caution]
            if "ema99_fake_breakout_caution" in caution: score -= 2
            if atr > 0.024: score -= 6; reasons.append("extreme_atr_short_caution")
            if score >= _score_threshold(short_permission, 59, 63):
                out.append(Candidate("maincoin_short", inst, "short", round(score,2), reasons, last, _stop_from_atr(atr, 1.9), strategy_lane="maincoin_trend", exit_style="trend"))
    return sorted(out, key=lambda c:c.score, reverse=True)


def maincoin_range_candidates(market: dict[str, Any], decision: Any, delta: float = 0) -> list[Candidate]:
    """Conservative BTC/ETH range lane for compression/dispersion phases.

    It does not grid or average down. It proposes only edge-of-range probes around
    MA20/MA99 distance, and execution still needs family slots and standard risk.
    """
    if not getattr(CFG, "maincoin_range_enabled", True):
        return []
    phase = getattr(decision, "market_phase", "")
    if phase not in {"btc_compression_ema99", "btc_range_alt_dispersion"}:
        return []
    long_perm = getattr(decision, "maincoin_long_permission", getattr(decision, "maincoin_permission", "wait"))
    short_perm = getattr(decision, "maincoin_short_permission", "wait")
    out=[]
    min_dist=float(getattr(CFG, "maincoin_range_min_distance", 0.004))
    max_atr=float(getattr(CFG, "maincoin_range_max_atr_pct", 0.016))
    threshold=float(getattr(CFG, "maincoin_range_score_threshold", 68.0))
    for inst in getattr(CFG, "range_maincoins", ("BTC-USDT-SWAP", "ETH-USDT-SWAP")):
        s=(market.get("maincoin", {}) or {}).get(inst, {})
        last=float(s.get("last",0)); ma20=float(s.get("ma20_1h",0)); ma99=float(s.get("ma99_1h",0)); atr=float(s.get("atr_pct_15m",0))
        ch4=float(s.get("change_4h",0)); funding=float(s.get("funding",0))
        if not last or not ma20 or atr <= 0 or atr > max_atr:
            continue
        anchor = ma99 or ma20
        dist20=(last-ma20)/last
        dist_anchor=(last-anchor)/last if anchor else 0.0
        base=64+delta
        if long_perm != "wait" and dist20 <= -min_dist and ch4 > -0.018:
            score=base + min(10, abs(dist20)*1000) + (1 if funding <= 0.0005 else 0)
            if score >= threshold:
                out.append(Candidate("maincoin_long", inst, "long", round(score,2), ["maincoin_range_lower_edge", f"dist20={dist20:.4f}", f"phase={phase}"], last, _stop_from_atr(atr, 1.5), strategy_lane="maincoin_range", exit_style="range"))
        if short_perm != "wait" and dist20 >= min_dist and ch4 < 0.018 and CFG.allow_maincoin_short:
            score=base + min(10, abs(dist20)*1000) + (1 if funding >= 0 else 0)
            if abs(dist_anchor) < 0.002:
                score += 1; reason_anchor="near_ma99_supply"
            else:
                reason_anchor="ma20_upper_edge"
            if score >= threshold:
                out.append(Candidate("maincoin_short", inst, "short", round(score,2), ["maincoin_range_upper_edge", reason_anchor, f"dist20={dist20:.4f}", f"phase={phase}"], last, _stop_from_atr(atr, 1.5), strategy_lane="maincoin_range", exit_style="range"))
    return sorted(out, key=lambda c:c.score, reverse=True)


def alt_candidates(market: dict[str, Any], long_perm: str, short_perm: str, long_delta: float = 0, short_delta: float = 0, phase: str = "") -> list[Candidate]:
    out=[]
    uni=market.get("alt_universe", [])
    for row in uni[:int(getattr(CFG, "alt_universe_limit", 100))]:
        inst, chg, last = row["instId"], float(row["chg24h"]), float(row["last"])
        vol=float(row.get("vol",0))
        if vol < 500000 or not last: continue
        # v1.3.0: alt_long is trend only in risk-on; in range/compression it is a fast probe; risk-off stays disabled by router.
        if long_perm != "wait" and chg > 0.030:
            lane = "alt_trend" if phase == "btc_impulse" and long_perm == "active" else "alt_fast_probe"
            exit_style = "trend" if lane == "alt_trend" else "fast_probe"
            score=52+min(24, chg*260)+long_delta
            if lane == "alt_fast_probe":
                score -= 3
            if score >= (60 if long_perm=="active" else 66):
                out.append(Candidate("alt_long", inst, "long", round(score,2), ["seed_strength_needs_candle_confirm", lane], last, 0.018, preliminary=True, strategy_lane=lane, exit_style=exit_style))
        if short_perm != "wait" and CFG.allow_alt_short and chg < -0.030:
            # short keeps trend-following in risk-off, but candle promotion must confirm follow-through/retest failure.
            lane = "alt_trend" if phase == "risk_off_alt_decay" and short_perm == "active" else "alt_fast_probe"
            exit_style = "trend" if lane == "alt_trend" else "fast_probe"
            score=52+min(24, abs(chg)*260)+short_delta
            if phase not in {"risk_off_alt_decay", "crash"}:
                score -= 2
            if score >= (60 if short_perm=="active" else 66):
                out.append(Candidate("alt_short", inst, "short", round(score,2), ["seed_weakness_needs_candle_confirm", lane], last, 0.018, preliminary=True, strategy_lane=lane, exit_style=exit_style))
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
        # v1.3.0 requires real follow-through plus a weak-price confirmation; this is the anti-crowded-short gate.
        confirmed = score >= CFG.min_live_candidate_score and s.change_1h < -0.002 and s.last < s.ma20_15m and s.change_4h < 0.004
    else:
        if s.change_1h > 0.005: score += 4; reasons.append("long_1h_followthrough")
        if s.change_4h > 0.015: score += 5; reasons.append("long_4h_followthrough")
        if s.last > s.ma20_15m: score += 4; reasons.append("above_ma20_15m")
        if s.funding < 0.0005: score += 1; reasons.append("funding_not_overheated")
        confirmed = score >= CFG.min_live_candidate_score and s.change_1h > 0.002 and s.last > s.ma20_15m
    stop=max(CFG.min_stop_pct, min(CFG.max_stop_pct, s.atr_pct_15m*1.8 or cand.stop_pct))
    return Candidate(cand.sleeve, cand.inst_id, cand.side, round(score,2), reasons if confirmed else reasons+["candle_confirm_failed"], s.last or cand.last, stop, preliminary=not confirmed, strategy_lane=cand.strategy_lane, exit_style=cand.exit_style)


def all_candidates(market: dict[str, Any], decision: Any) -> list[Candidate]:
    mods=decision.context_modifiers or {}
    main_long_perm=getattr(decision, "maincoin_long_permission", getattr(decision, "maincoin_permission", "wait"))
    main_short_perm=getattr(decision, "maincoin_short_permission", "wait")
    phase=getattr(decision, "market_phase", "")
    c=[]
    c += maincoin_candidates(market, main_long_perm, main_short_perm, float(mods.get("maincoin_score_delta",0)))
    c += maincoin_range_candidates(market, decision, float(mods.get("maincoin_score_delta",0)))
    c += alt_candidates(market, decision.alt_long_permission, decision.alt_short_permission, float(mods.get("alt_long_score_delta",0)), float(mods.get("alt_short_score_delta",0)), phase=phase)
    return sorted(c, key=lambda x:x.score, reverse=True)

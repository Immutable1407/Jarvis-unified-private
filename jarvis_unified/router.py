from __future__ import annotations
import json, time
from dataclasses import dataclass, asdict
from typing import Any
from .config import CFG, ensure_dirs
from .context import load_cold_context

@dataclass
class RouterDecision:
    ts: float
    market_phase: str
    maincoin_permission: str
    alt_long_permission: str
    alt_short_permission: str
    cash_preference: str
    total_risk_ceiling: float
    max_positions: int
    confidence: float
    reasons: list[str]
    context_modifiers: dict[str, Any]

def decide(market: dict[str, Any], cold_context: dict[str, Any] | None = None) -> RouterDecision:
    cold_context = cold_context or load_cold_context()
    mods = cold_context.get("modifiers") or {}
    btc = market["maincoin"].get("BTC-USDT-SWAP", {})
    eth = market["maincoin"].get("ETH-USDT-SWAP", {})
    sol = market["maincoin"].get("SOL-USDT-SWAP", {})
    breadth = market.get("breadth", {})
    reasons=[]
    b4, b24 = float(btc.get("change_4h",0)), float(btc.get("change_24h",0))
    atr = float(btc.get("atr_pct_15m",0))
    price, ma20, ma99 = float(btc.get("last",0)), float(btc.get("ma20_1h",0)), float(btc.get("ma99_1h",0))
    up_ratio, down_ratio = float(breadth.get("up_ratio",0)), float(breadth.get("down_ratio",0))
    funding = float(btc.get("funding",0))
    resonance = sum(1 for x in (eth, sol) if float(x.get("change_4h",0)) * (1 if b4 >= 0 else -1) > 0)
    near_ema99 = price and ma99 and abs(price-ma99)/price < 0.012

    phase="no_edge"; main="wait"; al="wait"; ash="wait"; cash="preferred"; risk=0.15; maxpos=0; conf=0.45
    if atr > 0.018 and b4 < -0.025:
        phase="crash"; reasons += ["btc_fast_drop_high_atr"]; cash="preferred"; risk=0.0
    elif b4 < -0.012 or b24 < -0.025 or down_ratio > 0.58:
        phase="risk_off_alt_decay"; main="probe_only" if b4 < -0.015 else "wait"; ash="active"; al="wait"; cash="preferred"; risk=0.25; maxpos=1; conf=0.62; reasons += ["btc_or_alt_breadth_weak"]
    elif near_ema99 and atr < 0.010:
        phase="btc_compression_ema99"; main="probe_only"; al="probe_only" if up_ratio>0.35 else "wait"; ash="probe_only" if down_ratio>0.35 else "wait"; cash="preferred"; risk=0.20; maxpos=1; conf=0.55; reasons += ["btc_near_ema99_compression"]
    elif b4 > 0.010 and b24 > 0.015 and price > ma20 and resonance >= 1:
        phase="btc_impulse"; main="active"; al="active" if up_ratio > 0.45 else "probe_only"; ash="wait"; cash="normal"; risk=0.35; maxpos=2; conf=0.66; reasons += ["btc_positive_impulse"]
    elif abs(b4) < 0.008 and up_ratio > 0.28 and down_ratio > 0.28:
        phase="btc_range_alt_dispersion"; main="wait"; al="probe_only"; ash="probe_only"; cash="normal"; risk=0.22; maxpos=1; conf=0.56; reasons += ["btc_range_alt_dispersion"]
    else:
        reasons += ["no_clear_edge"]

    # cold context modifiers alter permission/risk, never create trigger by itself.
    risk *= float(mods.get("total_risk_multiplier", 1.0))
    if mods.get("event_veto"):
        main=al=ash="wait"; cash="preferred"; risk=0.0; reasons.append("cold_context_event_veto")
    # Positive/negative deltas modify confidence.
    score_delta = max(float(mods.get("maincoin_score_delta",0)), float(mods.get("alt_long_score_delta",0)), float(mods.get("alt_short_score_delta",0)))
    conf = max(0.1, min(0.9, conf + score_delta/100.0))
    if cold_context.get("freshness") in {"missing","stale"}:
        conf -= 0.03; reasons.append(f"cold_context_{cold_context.get('freshness')}")

    return RouterDecision(time.time(), phase, main, al, ash, cash, round(risk,3), maxpos, round(conf,3), reasons, mods)

def save_router_snapshot(decision: RouterDecision, market: dict[str, Any]) -> dict[str, Any]:
    ensure_dirs()
    out={"decision": asdict(decision), "market_summary": {"breadth": market.get("breadth"), "btc": market.get("maincoin",{}).get("BTC-USDT-SWAP")}}
    latest=CFG.data_dir/"snapshots"/"router_latest.json"
    latest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    (CFG.data_dir/"snapshots"/f"router_{int(decision.ts)}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out

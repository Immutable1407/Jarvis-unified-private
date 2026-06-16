from __future__ import annotations
import json, time
from dataclasses import dataclass, asdict
from typing import Any
from .config import CFG, ensure_dirs
from .context import load_cold_context

PERM_RANK = {"wait": 0, "probe_only": 1, "active": 2}

def _aggregate_perm(*perms: str) -> str:
    return max(perms, key=lambda p: PERM_RANK.get(p, 0)) if perms else "wait"

@dataclass
class RouterDecision:
    ts: float
    market_phase: str
    # Legacy aggregate retained for reports/backward compatibility. Candidate generation uses the two directional fields below.
    maincoin_permission: str
    maincoin_long_permission: str
    maincoin_short_permission: str
    alt_long_permission: str
    alt_short_permission: str
    cash_preference: str
    total_risk_ceiling: float
    max_positions: int
    confidence: float
    reasons: list[str]
    context_modifiers: dict[str, Any]
    sleeve_permissions: dict[str, str]


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
    resonance = sum(1 for x in (eth, sol) if float(x.get("change_4h",0)) * (1 if b4 >= 0 else -1) > 0)
    near_ema99 = price and ma99 and abs(price-ma99)/price < 0.012

    phase="no_edge"
    main_l="wait"; main_s="wait"; al="wait"; ash="wait"
    cash="preferred"; risk=0.18; maxpos=0; conf=0.45

    # Matrix v1.0: four sleeves are first-class. Router grants permission to sleeves; execution still needs candidates + risk checks.
    if atr > 0.018 and b4 < -0.025:
        phase="crash"; reasons += ["btc_fast_drop_high_atr"]; cash="preferred"; risk=0.0; maxpos=0
    elif b4 < -0.012 or b24 < -0.025 or down_ratio > 0.58:
        phase="risk_off_alt_decay"
        main_s="probe_only" if b4 < -0.015 and CFG.allow_maincoin_short else "wait"
        ash="active" if CFG.allow_alt_short else "wait"
        main_l="wait"; al="wait"; cash="preferred"; risk=0.50; maxpos=5; conf=0.64
        reasons += ["btc_or_alt_breadth_weak", "matrix_short_sleeves_primary", "v1_2_controlled_growth_short_capacity"]
    elif near_ema99 and atr < 0.010:
        phase="btc_compression_ema99"
        main_l="probe_only"; main_s="probe_only" if CFG.allow_maincoin_short else "wait"
        al="probe_only" if up_ratio>0.35 else "wait"
        ash="probe_only" if down_ratio>0.35 and CFG.allow_alt_short else "wait"
        cash="preferred"; risk=0.32; maxpos=3; conf=0.57
        reasons += ["btc_near_ema99_compression", "matrix_probe_all_edges"]
    elif b4 > 0.010 and b24 > 0.015 and price > ma20 and resonance >= 1:
        phase="btc_impulse"
        main_l="active"; al="active" if up_ratio > 0.45 else "probe_only"
        main_s="wait"; ash="wait"; cash="normal"; risk=0.62; maxpos=6; conf=0.68
        reasons += ["btc_positive_impulse", "matrix_long_sleeves_primary", "v1_2_controlled_growth_long_capacity"]
    elif abs(b4) < 0.008 and up_ratio > 0.28 and down_ratio > 0.28:
        phase="btc_range_alt_dispersion"
        main_l="probe_only" if up_ratio > down_ratio else "wait"
        main_s="probe_only" if down_ratio > up_ratio and CFG.allow_maincoin_short else "wait"
        al="probe_only"; ash="probe_only" if CFG.allow_alt_short else "wait"
        cash="normal"; risk=0.45; maxpos=5; conf=0.58
        reasons += ["btc_range_alt_dispersion", "matrix_alt_both_sides_probe", "v1_2_controlled_growth_range_capacity"]
    else:
        reasons += ["no_clear_edge"]

    # cold context modifiers alter permission/risk/score, never create trigger by itself.
    risk *= float(mods.get("total_risk_multiplier", 1.0))
    if mods.get("event_veto"):
        main_l=main_s=al=ash="wait"; cash="preferred"; risk=0.0; maxpos=0; reasons.append("cold_context_event_veto")
    score_delta = max(float(mods.get("maincoin_score_delta",0)), float(mods.get("alt_long_score_delta",0)), float(mods.get("alt_short_score_delta",0)))
    conf = max(0.1, min(0.9, conf + score_delta/100.0))
    if cold_context.get("freshness") in {"missing","stale"}:
        conf -= 0.03; reasons.append(f"cold_context_{cold_context.get('freshness')}")

    sleeve_permissions={"maincoin_long": main_l, "maincoin_short": main_s, "alt_long": al, "alt_short": ash}
    main=_aggregate_perm(main_l, main_s)
    return RouterDecision(time.time(), phase, main, main_l, main_s, al, ash, cash, round(risk,3), maxpos, round(conf,3), reasons, mods, sleeve_permissions)


def save_router_snapshot(decision: RouterDecision, market: dict[str, Any]) -> dict[str, Any]:
    ensure_dirs()
    out={"decision": asdict(decision), "market_summary": {"breadth": market.get("breadth"), "btc": market.get("maincoin",{}).get("BTC-USDT-SWAP")}}
    latest=CFG.data_dir/"snapshots"/"router_latest.json"
    latest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    (CFG.data_dir/"snapshots"/f"router_{int(decision.ts)}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out

from __future__ import annotations
import json, subprocess, time, datetime as dt
from pathlib import Path
from typing import Any
from .config import CFG, ensure_dirs

CTX_PATH = CFG.data_dir / "snapshots" / "cold_context_latest.json"

def _run(cmd: list[str], timeout: int = 45) -> tuple[bool, Any]:
    try:
        p = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
        if p.returncode != 0:
            return False, {"error": p.stderr.strip() or p.stdout.strip(), "returncode": p.returncode}
        out = p.stdout.strip()
        return True, json.loads(out) if out else None
    except Exception as exc:
        return False, {"error": f"{type(exc).__name__}: {exc}"}

def collect_okx_sentiment() -> dict[str, Any]:
    base = ["/usr/local/bin/okx-profile", "--profile", CFG.okx_profile]
    result: dict[str, Any] = {"ok": True, "degradations": []}
    ok, data = _run(base + ["news", "coin-sentiment", "--coins", "BTC,ETH,SOL", "--period", "4h", "--json"])
    result["coin_sentiment"] = data if ok else None
    if not ok: result["ok"] = False; result["degradations"].append({"source":"coin_sentiment", **(data or {})})
    ok, data = _run(base + ["news", "sentiment-rank", "--period", "4h", "--sort-by", "hot", "--limit", "20", "--json"])
    result["hot_rank"] = data if ok else None
    if not ok: result["ok"] = False; result["degradations"].append({"source":"sentiment_rank", **(data or {})})
    ok, data = _run(base + ["news", "important", "--limit", "10", "--lang", "zh-CN", "--json"])
    result["important_news"] = data if ok else None
    if not ok: result["ok"] = False; result["degradations"].append({"source":"important_news", **(data or {})})
    return result

def collect_smartmoney() -> dict[str, Any]:
    base = ["/usr/local/bin/okx-profile", "--profile", CFG.okx_profile]
    result: dict[str, Any] = {"ok": True, "degradations": []}
    ok, data = _run(base + ["smartmoney", "signal-overview-by-filter", "--topInstruments", "20", "--period", "7", "--lmtNum", "100", "--json"])
    result["overview"] = data if ok else None
    if not ok: result["ok"] = False; result["degradations"].append({"source":"smartmoney_overview", **(data or {})})
    # Trends for core assets; failures degrade only.
    trends={}
    asof = dt.datetime.utcnow().strftime("%Y%m%d%H")
    for c in ("BTC","ETH","SOL"):
        ok, data = _run(base + ["smartmoney", "signal-trend-by-filter", "--instCcy", c, "--asOfTime", asof, "--granularity", "1h", "--limit", "12", "--period", "7", "--json"])
        trends[c] = data if ok else {"error": data}
        if not ok: result["ok"] = False; result["degradations"].append({"source":f"smartmoney_trend_{c}", **(data or {})})
    result["trends"] = trends
    return result

def collect_onchain() -> dict[str, Any]:
    # OKX OnchainOS may be unavailable/auth-gated in this environment. Include it as a first-class context slot,
    # but fail loud with degradation instead of substituting fake neutral values.
    ok, data = _run(["onchainos", "signal", "chains"], timeout=25)
    return {"ok": ok, "signal_chains": data if ok else None, "degradations": [] if ok else [{"source":"onchainos_signal_chains", **(data or {})}]}

def _modifiers(sent: dict[str, Any], sm: dict[str, Any], oc: dict[str, Any]) -> dict[str, Any]:
    main_delta = alt_long_delta = alt_short_delta = 0
    risk_mult = 1.0
    event_veto = False
    # Sentiment: parse defensively; OKX shapes can evolve.
    blob = json.dumps(sent, ensure_ascii=False).lower()
    if "bearish" in blob and "btc" in blob:
        main_delta -= 3; alt_long_delta -= 4; alt_short_delta += 2; risk_mult *= 0.9
    if "bullish" in blob and "btc" in blob:
        main_delta += 2
    # Smartmoney: broad overview positive/negative words affect permissions lightly.
    sblob = json.dumps(sm, ensure_ascii=False).lower()
    if "short" in sblob or "bearish" in sblob:
        alt_short_delta += 3; alt_long_delta -= 2
    if "long" in sblob or "bullish" in sblob:
        main_delta += 1; alt_long_delta += 1
    # Onchain unavailable reduces confidence, not direction.
    if not oc.get("ok"):
        risk_mult *= 0.95
    if "hack" in blob or "exploit" in blob or "sec" in blob and "lawsuit" in blob:
        event_veto = True; risk_mult *= 0.5
    return {"maincoin_score_delta": main_delta, "alt_long_score_delta": alt_long_delta, "alt_short_score_delta": alt_short_delta, "total_risk_multiplier": round(risk_mult, 3), "event_veto": event_veto}

def collect_cold_context() -> dict[str, Any]:
    ensure_dirs()
    sent = collect_okx_sentiment()
    sm = collect_smartmoney()
    oc = collect_onchain()
    ctx = {"ts": time.time(), "version": CFG.version, "sources": {"okx_sentiment": sent, "okx_smartmoney": sm, "okx_onchainos": oc}, "modifiers": _modifiers(sent, sm, oc)}
    ctx["freshness"] = "fresh"
    CTX_PATH.write_text(json.dumps(ctx, ensure_ascii=False, indent=2), encoding="utf-8")
    hist = CFG.data_dir / "snapshots" / f"cold_context_{int(ctx['ts'])}.json"
    hist.write_text(json.dumps(ctx, ensure_ascii=False, indent=2), encoding="utf-8")
    return ctx

def load_cold_context() -> dict[str, Any]:
    if not CTX_PATH.exists():
        return {"freshness": "missing", "modifiers": {"maincoin_score_delta":0,"alt_long_score_delta":0,"alt_short_score_delta":0,"total_risk_multiplier":0.9,"event_veto":False}}
    ctx = json.loads(CTX_PATH.read_text())
    age_h = (time.time() - float(ctx.get("ts",0))) / 3600
    ctx["age_hours"] = round(age_h,2)
    if age_h > CFG.context_max_age_hours:
        ctx["freshness"] = "stale"
        ctx["modifiers"] = {"maincoin_score_delta":0,"alt_long_score_delta":0,"alt_short_score_delta":0,"total_risk_multiplier":0.9,"event_veto":False}
    return ctx

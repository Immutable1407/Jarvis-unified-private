from __future__ import annotations
import json, time
from dataclasses import dataclass, asdict
from decimal import Decimal
from pathlib import Path
from typing import Any
from .config import CFG, ensure_dirs
from .okx_client import OKXClient, d

@dataclass
class CandleStats:
    inst_id: str
    last: float
    change_1h: float
    change_4h: float
    change_24h: float
    ma20_15m: float
    ma20_1h: float
    ma99_1h: float
    atr_pct_15m: float
    vol_quote_24h: float
    funding: float = 0.0
    oi_ccy: float = 0.0

class InstrumentCache:
    def __init__(self, path: Path | None = None):
        ensure_dirs(); self.path = path or (CFG.data_dir / "state" / "instruments.json")
        self.data: dict[str, Any] = {}
    def refresh(self, client: OKXClient) -> dict[str, Any]:
        r = client.instruments()
        if r.get("code") != "0": raise RuntimeError(f"instruments failed: {r}")
        self.data = {x["instId"]: x for x in r.get("data", []) if x.get("instId", "").endswith("USDT-SWAP")}
        self.path.write_text(json.dumps({"ts": time.time(), "data": self.data}, indent=2), encoding="utf-8")
        return self.data
    def load(self, client: OKXClient | None = None) -> dict[str, Any]:
        if self.data: return self.data
        if self.path.exists() and time.time() - json.loads(self.path.read_text()).get("ts", 0) < 86400:
            self.data = json.loads(self.path.read_text())["data"]; return self.data
        if client is None: client = OKXClient()
        return self.refresh(client)
    def get(self, inst_id: str, client: OKXClient | None = None) -> dict[str, Any]:
        data = self.load(client)
        if inst_id not in data: raise KeyError(f"instrument not found: {inst_id}")
        return data[inst_id]

def _parse_candles(resp: dict[str, Any]) -> list[list[Decimal]]:
    if resp.get("code") != "0": return []
    rows = list(reversed(resp.get("data") or []))
    out=[]
    for r in rows:
        # ts,o,h,l,c,vol,volCcy,volCcyQuote,confirm
        out.append([d(r[1]), d(r[2]), d(r[3]), d(r[4]), d(r[7] if len(r)>7 else 0)])
    return out

def _chg(rows: list[list[Decimal]], n: int) -> float:
    if len(rows) <= n: return 0.0
    old, now = rows[-n-1][3], rows[-1][3]
    return float((now - old) / old) if old else 0.0

def _ma(rows: list[list[Decimal]], n: int) -> float:
    if len(rows) < n: return 0.0
    return float(sum(r[3] for r in rows[-n:]) / Decimal(n))

def _atr_pct(rows: list[list[Decimal]], n: int = 14) -> float:
    if len(rows) < n + 1: return 0.0
    trs=[]
    for i in range(-n,0):
        high, low, close_prev = rows[i][1], rows[i][2], rows[i-1][3]
        trs.append(max(high-low, abs(high-close_prev), abs(low-close_prev)))
    last = rows[-1][3]
    return float((sum(trs)/Decimal(n))/last) if last else 0.0

def stats_for(client: OKXClient, inst_id: str) -> CandleStats:
    c15 = _parse_candles(client.candles(inst_id, "15m", 100))
    c1h = _parse_candles(client.candles(inst_id, "1H", 140))
    tick = client.ticker(inst_id)
    t = (tick.get("data") or [{}])[0] if tick.get("code") == "0" else {}
    fr = client.funding_rate(inst_id); oi = client.open_interest(inst_id)
    last = float(t.get("last") or (c15[-1][3] if c15 else 0))
    return CandleStats(
        inst_id=inst_id,
        last=last,
        change_1h=_chg(c15, 4), change_4h=_chg(c15, 16), change_24h=_chg(c1h, 24),
        ma20_15m=_ma(c15,20), ma20_1h=_ma(c1h,20), ma99_1h=_ma(c1h,99), atr_pct_15m=_atr_pct(c15,14),
        vol_quote_24h=float(t.get("volCcy24h") or t.get("vol24h") or 0),
        funding=float(((fr.get("data") or [{}])[0]).get("fundingRate") or 0) if fr.get("code") == "0" else 0.0,
        oi_ccy=float(((oi.get("data") or [{}])[0]).get("oiCcy") or 0) if oi.get("code") == "0" else 0.0,
    )

def broad_swap_universe(client: OKXClient, limit: int | None = None) -> list[dict[str, Any]]:
    if limit is None:
        limit = int(getattr(CFG, "alt_universe_limit", 100))
    r = client.tickers()
    if r.get("code") != "0": return []
    rows=[]
    for x in r.get("data", []):
        inst=x.get("instId","")
        if not inst.endswith("USDT-SWAP") or inst in CFG.allowed_maincoins: continue
        try:
            last=float(x.get("last") or 0); open24=float(x.get("open24h") or 0); vol=float(x.get("volCcy24h") or x.get("vol24h") or 0)
            chg=(last-open24)/open24 if open24 else 0.0
        except Exception: continue
        rows.append({"instId": inst, "last": last, "chg24h": chg, "vol": vol})
    rows.sort(key=lambda z: z["vol"], reverse=True)
    return rows[:limit]

def snapshot_market(client: OKXClient) -> dict[str, Any]:
    main = {i: asdict(stats_for(client, i)) for i in CFG.maincoin_scan}
    uni = broad_swap_universe(client, CFG.alt_universe_limit)
    up = sum(1 for x in uni if x["chg24h"] > 0.01); down = sum(1 for x in uni if x["chg24h"] < -0.01)
    return {"ts": time.time(), "maincoin": main, "alt_universe": uni, "breadth": {"count": len(uni), "up_1pct": up, "down_1pct": down, "up_ratio": up/max(1,len(uni)), "down_ratio": down/max(1,len(uni))}}

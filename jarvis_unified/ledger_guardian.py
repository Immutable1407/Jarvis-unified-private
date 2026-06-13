from __future__ import annotations
import json, time, datetime as dt
from .config import CFG, ensure_dirs
from .okx_client import OKXClient

def sync_fills(client: OKXClient | None = None) -> dict:
    ensure_dirs(); client = client or OKXClient()
    r=client.fills(100)
    if r.get("code") != "0": return {"ok": False, "error": r}
    path=CFG.data_dir/"ledgers"/"fills.jsonl"
    seen=set()
    if path.exists():
        for line in path.read_text().splitlines():
            try: seen.add(json.loads(line).get("tradeId"))
            except Exception: pass
    new=0
    with path.open("a", encoding="utf-8") as f:
        for x in r.get("data", []):
            tid=x.get("tradeId") or x.get("billId")
            if tid in seen: continue
            ts=int(x.get("ts") or time.time()*1000)
            date=dt.datetime.fromtimestamp(ts/1000, dt.UTC).strftime("%Y-%m-%d")
            fee=float(x.get("fee") or 0); pnl=float(x.get("fillPnl") or 0)
            rec={"date": date, "tradeId": tid, "ts": ts, "instId": x.get("instId"), "side": x.get("side"), "posSide": x.get("posSide"), "fillSz": x.get("fillSz"), "fillPx": x.get("fillPx"), "fee": fee, "fillPnl": pnl, "net_pnl": pnl+fee, "raw": x}
            f.write(json.dumps(rec, ensure_ascii=False)+"\n"); new+=1
    return {"ok": True, "new": new, "total_seen": len(seen)+new}

def guardian_check(client: OKXClient | None = None) -> dict:
    ensure_dirs(); client=client or OKXClient(); client.assert_account()
    pos=client.positions(); algos=client.algo_orders()
    issues=[]
    if pos.get("code") != "0": issues.append({"type":"positions_error","resp":pos})
    if algos.get("code") not in {"0","207"}: issues.append({"type":"algos_error","resp":algos})
    # v0.1 guardian is protection/audit first; it does not move stops yet.
    open_pos=[p for p in pos.get("data",[]) if abs(float(p.get("pos") or 0))>0] if pos.get("code") == "0" else []
    out={"ok": not issues, "ts": time.time(), "open_positions": open_pos, "algo_count": len(algos.get("data",[])), "issues": issues}
    (CFG.data_dir/"state"/"guardian_latest.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out

from __future__ import annotations
import json, subprocess, time, datetime as dt
from pathlib import Path
from .config import CFG, ensure_dirs


def _run(cmd: list[str], timeout: int=60):
    try:
        p=subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
        if p.returncode!=0: return None, p.stderr.strip() or p.stdout.strip()
        return json.loads(p.stdout) if p.stdout.strip() else None, None
    except Exception as e: return None, f"{type(e).__name__}: {e}"


def _acct(profile: str):
    cfg, err=_run(["/usr/local/bin/okx-profile","--profile",profile,"account","config","--json"])
    bal, berr=_run(["/usr/local/bin/okx-profile","--profile",profile,"account","balance-all","USDT","--json"])
    pos, perr=_run(["/usr/local/bin/okx-profile","--profile",profile,"account","positions","--instType","SWAP","--json"])
    c=(cfg or [{}])[0] if isinstance(cfg, list) and cfg else {}
    total=(bal or {}).get("trading",{}).get("totalEq") if isinstance(bal,dict) else None
    openp=[p for p in (pos or []) if abs(float(p.get("pos") or 0))>0] if isinstance(pos,list) else []
    upl=sum(float(p.get("upl") or 0) for p in openp)
    return {"profile": profile, "uid": c.get("uid"), "label": c.get("label"), "acctLv": c.get("acctLv"), "equity": total, "open_positions": len(openp), "upl": round(upl,4), "errors": [x for x in [err,berr,perr] if x]}


def _sleeve_for_fill(rec: dict) -> str:
    inst = rec.get("instId", "")
    pos_side = rec.get("posSide") or ("short" if rec.get("side") == "sell" else "long")
    if inst in CFG.allowed_maincoins:
        return "maincoin_long" if pos_side == "long" else "maincoin_short"
    return "alt_long" if pos_side == "long" else "alt_short"

def _matrix_pnl_summary(days: int = 7) -> dict:
    path = CFG.data_dir / "ledgers" / "fills.jsonl"
    out = {"net_pnl": 0.0, "fee": 0.0, "raw_fills": 0, "sleeves": {s:{"net_pnl":0.0,"fee":0.0,"raw_fills":0} for s in CFG.sleeve_names}}
    if not path.exists():
        return out
    cutoff = dt.datetime.now(dt.UTC).date() - dt.timedelta(days=max(0, days-1))
    for line in path.read_text().splitlines():
        try: rec=json.loads(line)
        except Exception: continue
        if str(rec.get("uid") or "") != str(CFG.expected_uid):
            continue
        try: day = dt.date.fromisoformat(str(rec.get("date")))
        except Exception: continue
        if day < cutoff:
            continue
        sleeve = _sleeve_for_fill(rec)
        net = float(rec.get("net_pnl") or 0); fee = float(rec.get("fee") or 0)
        out["net_pnl"] += net; out["fee"] += fee; out["raw_fills"] += 1
        row = out["sleeves"].setdefault(sleeve, {"net_pnl":0.0,"fee":0.0,"raw_fills":0})
        row["net_pnl"] += net; row["fee"] += fee; row["raw_fills"] += 1
    out["net_pnl"] = round(out["net_pnl"], 6); out["fee"] = round(out["fee"], 6)
    for row in out["sleeves"].values():
        row["net_pnl"] = round(row["net_pnl"], 6); row["fee"] = round(row["fee"], 6)
    return out

def refresh_daily_state() -> dict:
    result = {"live_cycle_dry_run": None, "healthcheck": None, "errors": []}
    try:
        from .live_cycle import run_live_cycle
        result["live_cycle_dry_run"] = run_live_cycle(dry_run=True, sync_fills_enabled=False, record_decisions=False)
    except Exception as exc:
        result["errors"].append(f"live_cycle_refresh:{type(exc).__name__}:{exc}")
    try:
        from .healthcheck import run_healthcheck
        result["healthcheck"] = run_healthcheck()
    except Exception as exc:
        result["errors"].append(f"healthcheck_refresh:{type(exc).__name__}:{exc}")
    return result

def combined_brief(refresh: bool = True) -> str:
    ensure_dirs()
    refresh_result = refresh_daily_state() if refresh else {"errors": []}
    profiles=[("矩阵账户 / Matrix Unified","jarvis-unified-100u")]
    rows=[(name,_acct(p)) for name,p in profiles]
    live_path=CFG.data_dir/"state"/"live_cycle_latest.json"
    health_path=CFG.data_dir/"state"/"healthcheck_latest.json"
    router={}
    health={}
    if live_path.exists():
        router=json.loads(live_path.read_text()).get("router",{})
    if health_path.exists():
        health=json.loads(health_path.read_text())
    pnl_summary=_matrix_pnl_summary(7)
    now=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M UTC+8")
    lines=[f"Jarvis 矩阵账户每日简报 — {now}", "", "一、账户概览"]
    for name,r in rows:
        lines.append(f"- {name}: equity={r.get('equity')}U, open_positions={r.get('open_positions')}, UPL={r.get('upl')}U, uid={r.get('uid')}, label={r.get('label')}")
        if r.get("errors"): lines.append(f"  - warning: {r['errors'][:1]}")
    lines += ["", f"二、矩阵账户 v{CFG.version} 2×2 Router"]
    if router:
        sleeves=router.get("sleeve_permissions") or {}
        lines += [
            f"- phase: {router.get('market_phase')}",
            f"- sleeves: main_long={sleeves.get('maincoin_long')}, main_short={sleeves.get('maincoin_short')}, alt_long={sleeves.get('alt_long')}, alt_short={sleeves.get('alt_short')}, cash={router.get('cash_preference')}",
            f"- confidence={router.get('confidence')}, risk_ceiling={router.get('total_risk_ceiling')}, max_positions={router.get('max_positions')}, reasons={', '.join(router.get('reasons',[])[:5])}",
        ]
    else:
        lines.append("- 尚无 live_cycle snapshot")
    if health:
        issue_types=[i.get("type") for i in health.get("issues",[])[:5]]
        lines += [f"- healthcheck: ok={health.get('ok')}, open_positions={health.get('open_positions')}, algo_count={health.get('algo_count')}, issues={issue_types}"]
    if refresh_result.get("errors"):
        lines.append(f"- refresh_warning: {refresh_result['errors'][:2]}")
    lines += ["", "三、近 7 日袖套归因", f"- total_net_pnl={pnl_summary['net_pnl']}U, fee={pnl_summary['fee']}U, raw_fills={pnl_summary['raw_fills']}"]
    for sleeve, row in pnl_summary["sleeves"].items():
        lines.append(f"- {sleeve}: net_pnl={row['net_pnl']}U, fee={row['fee']}U, raw_fills={row['raw_fills']}")
    lines += [
        "",
        "",
        "四、董事会结论",
        "- Mi 主流币账户与 v4 山寨账户已归档为历史实验；日常口径只看矩阵账户。",
        f"- v{CFG.version} 验证 2×2 全市场矩阵：主流多 / 主流空 / 山寨多 / 山寨空，Router 先分配袖套权限，候选、风控、guardian 再逐层确认。",
        "- 高频交易/健康/guardian 事件保持 local；每日和周结只输出管理摘要。",
    ]
    msg="\n".join(lines)
    path=CFG.report_dir/f"matrix_daily_{dt.datetime.utcnow().strftime('%Y%m%d')}.md"
    path.write_text(msg, encoding="utf-8")
    return msg

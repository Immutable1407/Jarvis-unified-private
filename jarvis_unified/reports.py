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

def combined_brief() -> str:
    ensure_dirs()
    profiles=[("Hermes Mi 主流币","hermes-mi-maincoin"),("Jarvis v4 山寨","jarvis-v4-alt"),("Unified Jarvis","jarvis-unified-100u")]
    rows=[(name,_acct(p)) for name,p in profiles]
    live_path=CFG.data_dir/"state"/"live_cycle_latest.json"
    health_path=CFG.data_dir/"state"/"healthcheck_latest.json"
    router={}
    health={}
    if live_path.exists():
        router=json.loads(live_path.read_text()).get("router",{})
    if health_path.exists():
        health=json.loads(health_path.read_text())
    now=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M UTC+8")
    lines=[f"Jarvis 三策略每日简报 — {now}", "", "一、账户概览"]
    for name,r in rows:
        lines.append(f"- {name}: equity={r.get('equity')}U, open_positions={r.get('open_positions')}, UPL={r.get('upl')}U, uid={r.get('uid')}, label={r.get('label')}")
        if r.get("errors"): lines.append(f"  - warning: {r['errors'][:1]}")
    lines += ["", f"二、Unified Jarvis v{CFG.version}"]
    if router:
        lines += [f"- phase: {router.get('market_phase')}", f"- permission: maincoin={router.get('maincoin_permission')}, alt_long={router.get('alt_long_permission')}, alt_short={router.get('alt_short_permission')}, cash={router.get('cash_preference')}", f"- confidence={router.get('confidence')}, risk_ceiling={router.get('total_risk_ceiling')}, reasons={', '.join(router.get('reasons',[])[:5])}"]
    else:
        lines.append("- 尚无 live_cycle snapshot")
    if health:
        issue_types=[i.get("type") for i in health.get("issues",[])[:5]]
        lines += [f"- healthcheck: ok={health.get('ok')}, open_positions={health.get('open_positions')}, algo_count={health.get('algo_count')}, issues={issue_types}"]
    lines += ["", "三、董事会结论", "- v0.3.0 进入完整 light-live 推进：放开到最多 3 仓/单袖套 2 仓/默认 4x，同时保留 UID、日亏损、重复币种、袖套仓位、guardian 保护闭环。", "- 高频交易/健康/guardian 事件保持 local，不推飞书。"]
    msg="\n".join(lines)
    path=CFG.report_dir/f"combined_daily_{dt.datetime.utcnow().strftime('%Y%m%d')}.md"
    path.write_text(msg, encoding="utf-8")
    return msg

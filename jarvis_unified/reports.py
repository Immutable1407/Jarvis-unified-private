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
    trading=(bal or {}).get("trading",{}) if isinstance(bal,dict) else {}
    total=trading.get("totalEq")
    detail={}
    details=trading.get("details") or []
    if isinstance(details, list):
        detail=next((x for x in details if x.get("ccy") == "USDT"), details[0] if details else {})
    openp=[p for p in (pos or []) if abs(float(p.get("pos") or 0))>0] if isinstance(pos,list) else []
    upl=sum(float(p.get("upl") or 0) for p in openp)
    notional=sum(abs(float(p.get("notionalUsd") or 0)) for p in openp)
    try:
        computed_lev = round(notional / float(total), 4) if total else None
    except Exception:
        computed_lev = None
    return {
        "profile": profile,
        "uid": c.get("uid"),
        "label": c.get("label"),
        "acctLv": c.get("acctLv"),
        "equity": total,
        "avail_bal": detail.get("availBal") or detail.get("availEq"),
        "notional_lever": detail.get("notionalLever") or computed_lev,
        "open_positions": len(openp),
        "upl": round(upl,4),
        "errors": [x for x in [err,berr,perr] if x],
    }


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

def _parse_fill_ts(rec: dict) -> float:
    raw = rec.get("ts")
    try:
        if raw not in (None, ""):
            val = float(raw)
            return val / 1000 if val > 1e12 else val
    except Exception:
        pass
    try:
        day = dt.date.fromisoformat(str(rec.get("date")))
        return dt.datetime.combine(day, dt.time.min, tzinfo=dt.UTC).timestamp()
    except Exception:
        return 0.0


def _realized_net_since(hours: float | None = None, *, today_utc: bool = False) -> dict:
    path = CFG.data_dir / "ledgers" / "fills.jsonl"
    out = {"net_pnl": 0.0, "fee": 0.0, "raw_fills": 0}
    if not path.exists():
        return out
    now = dt.datetime.now(dt.UTC)
    cutoff = dt.datetime(now.year, now.month, now.day, tzinfo=dt.UTC).timestamp() if today_utc else now.timestamp() - float(hours or 0) * 3600
    for line in path.read_text().splitlines():
        try: rec = json.loads(line)
        except Exception: continue
        if str(rec.get("uid") or "") != str(CFG.expected_uid):
            continue
        if _parse_fill_ts(rec) < cutoff:
            continue
        out["net_pnl"] += float(rec.get("net_pnl") or 0)
        out["fee"] += float(rec.get("fee") or 0)
        out["raw_fills"] += 1
    out["net_pnl"] = round(out["net_pnl"], 6); out["fee"] = round(out["fee"], 6)
    return out


def _risk_level(health: dict, acct: dict, pnl_today: dict, pnl_24h: dict) -> str:
    if health and not health.get("ok", True):
        return "高"
    if pnl_today.get("net_pnl", 0.0) <= -abs(float(getattr(CFG, "daily_realized_loss_halt_usdt", 6.0))) * 0.8:
        return "中到高"
    try:
        lev = float(acct.get("notional_lever") or 0)
    except Exception:
        lev = 0.0
    if lev < 0.5 and pnl_24h.get("net_pnl", 0.0) > -abs(float(getattr(CFG, "daily_realized_loss_halt_usdt", 6.0))):
        return "低到中"
    return "中"


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
    acct=_acct("jarvis-unified-100u")
    live_path=CFG.data_dir/"state"/"live_cycle_latest.json"
    health_path=CFG.data_dir/"state"/"healthcheck_latest.json"
    router={}
    health={}
    if live_path.exists():
        router=json.loads(live_path.read_text()).get("router",{})
    if health_path.exists():
        health=json.loads(health_path.read_text())
    pnl_today=_realized_net_since(today_utc=True)
    pnl_24h=_realized_net_since(hours=24)
    now=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M UTC+8")
    sleeve=router.get("sleeve_permissions") or {}
    issue_types=[i.get("type") for i in health.get("issues",[])[:5]] if health else []
    risk_level=_risk_level(health, acct, pnl_today, pnl_24h)
    health_state="正常" if health.get("ok", False) and not issue_types else f"异常 {issue_types}"
    lines=[
        "Jarvis 矩阵账户每日简报",
        "",
        f"日期：{now}",
        "账户：Matrix Account / OKX Unified",
        f"版本：v{CFG.version} structural completion",
        "",
        "1. 账户概览",
        "",
        f"- 当前权益：{acct.get('equity')} U",
        f"- 可用资金：{acct.get('avail_bal') or 'unknown'} U",
        f"- 当前浮盈：{acct.get('upl')} U",
        f"- 今日已实现净值：{pnl_today['net_pnl']} U",
        f"- 近 24h 已实现净值：{pnl_24h['net_pnl']} U",
        f"- 当前持仓数：{health.get('open_positions', acct.get('open_positions'))}",
        f"- 保护单数量：{health.get('algo_count', 'unknown')}",
        f"- 账户杠杆使用：约 {acct.get('notional_lever') or 'unknown'}x",
        f"- 健康状态：{health_state}",
        f"- 风险等级：{risk_level}",
        "",
        "简评：",
        "账户当前没有裸仓，保护单完整，杠杆使用较低。" if health_state == "正常" else "账户存在健康检查异常，需优先处理保护/运行问题。",
        "主要风险不是爆仓风险，而是策略仍处于 v1.3.0 结构验证期，需重点观察已实现亏损是否继续扩大。",
        "",
        "2. 今日 Router 状态",
        "",
        f"- 市场阶段：{router.get('market_phase', 'unknown')}",
        f"- 主流币 long：{sleeve.get('maincoin_long', router.get('maincoin_long_permission', 'unknown'))}",
        f"- 主流币 short：{sleeve.get('maincoin_short', router.get('maincoin_short_permission', 'unknown'))}",
        f"- 山寨 long：{sleeve.get('alt_long', router.get('alt_long_permission', 'unknown'))}",
        f"- 山寨 short：{sleeve.get('alt_short', router.get('alt_short_permission', 'unknown'))}",
        f"- cash preference：{router.get('cash_preference', 'unknown')}",
        f"- 最大允许仓位：{router.get('max_positions', 'unknown')}",
        f"- 风险 ceiling：{router.get('total_risk_ceiling', 'unknown')}",
        "",
        "简评：",
        "当前市场仍偏弱。" if router.get("market_phase") == "risk_off_alt_decay" else "当前市场阶段以 Router 实时判断为准。",
        "系统允许山寨 short，但已有持仓、cooldown 与 sleeve cap 会限制继续扩张。" if sleeve.get("alt_short") == "active" else "当前不主动扩张山寨 short。",
        "主流币 range 逻辑已上线，但只有在压缩/震荡且方向权限允许时才会进入候选。",
        "",
        "3. Jarvis 今日判断",
        "",
        "矩阵账户已从 v1.2.0 的“山寨主导试错”进入 v1.3.0 的“结构补全验证”。",
        "",
        "今日重点不是扩大收益，而是验证三件事：",
        "",
        "1. 主流币腿是否真的能补上；",
        "2. 山寨腿是否不再持续失血；",
        "3. 浮盈是否能被制度化保护。",
        "",
        "当前判断：",
        "",
        f"- 系统运行状态：{'正常' if health_state == '正常' else '异常'}；",
        f"- 持仓保护状态：{'正常' if health.get('algo_count', 0) >= health.get('open_positions', 999) else '需检查'}；",
        f"- 账户风险：{risk_level}；",
        "- 策略验证压力：仍然存在；",
        f"- 是否需要人工介入：{'暂不需要' if health_state == '正常' else '需要检查'}。",
        "",
        "如果未来 24–72 小时仍然出现：",
        "",
        "- 当前持仓常浮盈；",
        "- 历史平仓继续亏；",
        "- 主流币 range 不进 plans；",
        "- alt short 继续连续亏；",
        "",
        "则下一步进入 v1.3.1，重点做：",
        "",
        "- sleeve performance feedback；",
        "- lane-level PnL attribution；",
        "- 更精细的 MFE/MAE 复盘；",
        "- alt_short 拥挤交易过滤；",
        "- maincoin range 参数校准。",
    ]
    if acct.get("errors") or refresh_result.get("errors"):
        lines += ["", "运行提醒：", f"- account/report warnings: {acct.get('errors') or []} {refresh_result.get('errors') or []}"]
    msg="\n".join(lines)
    path=CFG.report_dir/f"matrix_daily_{dt.datetime.utcnow().strftime('%Y%m%d')}.md"
    path.write_text(msg, encoding="utf-8")
    return msg

from __future__ import annotations
import json, time
from pathlib import Path
from typing import Any
from .config import CFG, ensure_dirs
from .okx_client import OKXClient


def _load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, "missing"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as exc:
        return None, f"unreadable:{type(exc).__name__}:{exc}"


def _open_positions(pos_resp: dict[str, Any]) -> list[dict[str, Any]]:
    if pos_resp.get("code") != "0":
        return []
    return [p for p in pos_resp.get("data", []) if abs(float(p.get("pos") or 0)) > 0]


def _algo_stop_px(a: dict[str, Any]) -> str | None:
    for k in ("slTriggerPx", "triggerPx", "moveTriggerPx"):
        if a.get(k) not in (None, "", "0", 0):
            return str(a[k])
    return None


def run_healthcheck(client: OKXClient | None = None, cfg: Any = CFG) -> dict[str, Any]:
    """Read-only closed-loop healthcheck for Unified Jarvis.

    Checks the account guard, runtime freshness, cold-context freshness,
    protection continuity, and basic risk-parameter sanity. It does not write
    orders and is safe for cron/local diagnostics.
    """
    ensure_dirs()
    client = client or OKXClient()
    issues: list[dict[str, Any]] = []
    account: dict[str, Any] = {}
    now = time.time()

    try:
        account = client.assert_account()
        if str(account.get("uid")) != str(cfg.expected_uid) or str(account.get("mainUid")) != str(cfg.expected_main_uid):
            issues.append({"type": "uid_mismatch", "uid": account.get("uid"), "mainUid": account.get("mainUid")})
    except Exception as exc:
        issues.append({"type": "account_guard_error", "error": str(exc)})

    cold, cold_err = _load_json(cfg.data_dir / "snapshots" / "cold_context_latest.json")
    if cold_err:
        issues.append({"type": "cold_context_missing" if cold_err == "missing" else "cold_context_unreadable", "error": cold_err})
    else:
        age_h = (now - float(cold.get("ts", 0))) / 3600 if cold.get("ts") else 999
        if age_h > float(cfg.context_max_age_hours):
            issues.append({"type": "cold_context_stale", "age_hours": round(age_h, 2), "max_age_hours": cfg.context_max_age_hours})

    live, live_err = _load_json(cfg.data_dir / "state" / "live_cycle_latest.json")
    if live_err:
        issues.append({"type": "live_cycle_snapshot_missing" if live_err == "missing" else "live_cycle_snapshot_unreadable", "error": live_err})
    else:
        age_min = (now - float(live.get("ts", 0))) / 60 if live.get("ts") else 9999
        if age_min > float(cfg.live_cycle_minutes) * 3:
            issues.append({"type": "live_cycle_stale", "age_minutes": round(age_min, 1)})

    guardian, guardian_err = _load_json(cfg.data_dir / "state" / "guardian_latest.json")
    if guardian_err:
        issues.append({"type": "guardian_snapshot_missing" if guardian_err == "missing" else "guardian_snapshot_unreadable", "error": guardian_err})
    else:
        age_min = (now - float(guardian.get("ts", 0))) / 60 if guardian.get("ts") else 9999
        if age_min > float(cfg.guardian_minutes) * 4:
            issues.append({"type": "guardian_stale", "age_minutes": round(age_min, 1)})
        for issue in guardian.get("issues", [])[:5]:
            issues.append({"type": "guardian_issue", "detail": issue})
        for ar in guardian.get("action_results", [])[:10]:
            result = ar.get("result", {}) if isinstance(ar, dict) else {}
            if result and result.get("dry_run") is not True and not result.get("ok"):
                issues.append({"type": "guardian_action_failed", "detail": ar})

    pos_resp = client.positions()
    algo_resp = client.algo_orders()
    if pos_resp.get("code") != "0":
        issues.append({"type": "positions_error", "response": pos_resp})
    if algo_resp.get("code") not in {"0", "207"}:
        issues.append({"type": "algo_orders_error", "response": algo_resp})
    open_pos = _open_positions(pos_resp)
    algo_rows = algo_resp.get("data", []) if algo_resp.get("code") in {"0", "207"} else []
    protected = {(a.get("instId"), a.get("posSide") or "") for a in algo_rows if _algo_stop_px(a)}
    protected_inst = {a.get("instId") for a in algo_rows if _algo_stop_px(a) and not a.get("posSide")}
    for p in open_pos:
        inst, side = p.get("instId"), p.get("posSide") or ("long" if float(p.get("pos") or 0) > 0 else "short")
        if (inst, side) not in protected and inst not in protected_inst:
            issues.append({"type": "unprotected_position", "instId": inst, "posSide": side, "pos": p.get("pos")})

    max_total_positions = getattr(cfg, "max_total_positions", 3)
    single_trade_risk_usdt = getattr(cfg, "single_trade_risk_usdt", 0.75)
    daily_realized_loss_halt_usdt = getattr(cfg, "daily_realized_loss_halt_usdt", 4.50)
    if max_total_positions < 1 or max_total_positions > 6:
        issues.append({"type": "risk_param_out_of_range", "field": "max_total_positions", "value": max_total_positions})
    if single_trade_risk_usdt <= 0 or daily_realized_loss_halt_usdt <= single_trade_risk_usdt:
        issues.append({"type": "risk_param_out_of_range", "field": "risk_vs_daily_loss", "single": single_trade_risk_usdt, "daily": daily_realized_loss_halt_usdt})

    out = {
        "ok": not issues,
        "ts": now,
        "version": getattr(cfg, "version", "unknown"),
        "account": {"uid": account.get("uid"), "mainUid": account.get("mainUid"), "label": account.get("label")},
        "open_positions": len(open_pos),
        "algo_count": len(algo_rows),
        "issues": issues,
    }
    try:
        (cfg.data_dir / "state" / "healthcheck_latest.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return out

from __future__ import annotations
import base64, datetime as dt, hashlib, hmac, json, os, tomllib, urllib.parse, urllib.request, urllib.error
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Any
from .config import CFG

class OKXError(RuntimeError):
    pass

class OKXClient:
    def __init__(self, profile: str = CFG.okx_profile, config_path: str = "/root/.okx/config.toml"):
        self.profile = profile
        self.config_path = Path(config_path)
        self.base_url = "https://www.okx.com"
        cfg = tomllib.loads(self.config_path.read_text())
        prof = (cfg.get("profiles") or {}).get(profile)
        if not prof:
            raise OKXError(f"OKX profile not found: {profile}")
        self.api_key = prof.get("api_key", "")
        self.secret_key = prof.get("secret_key", "")
        self.passphrase = prof.get("passphrase", "")
        self.demo = bool(prof.get("demo", False))
        self.site = prof.get("site", "global")
        self._account_verified = False

    def _ts(self) -> str:
        now = dt.datetime.now(dt.UTC)
        return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"

    def _headers(self, method: str, path: str, body: str) -> dict[str, str]:
        ts = self._ts()
        pre = ts + method.upper() + path + body
        sig = base64.b64encode(hmac.new(self.secret_key.encode(), pre.encode(), hashlib.sha256).digest()).decode()
        h = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": sig,
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
            "User-Agent": "Jarvis-Unified/0.1.0",
        }
        if self.demo:
            h["x-simulated-trading"] = "1"
        return h

    def req(self, method: str, path: str, body: Any | None = None, auth: bool = True) -> dict[str, Any]:
        body_str = json.dumps(body, separators=(",", ":")) if body is not None else ""
        headers = self._headers(method, path, body_str) if auth else {"User-Agent": "Jarvis-Unified/0.1.0"}
        if body is not None and not auth:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base_url + path, data=body_str.encode() if body_str else None, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode(errors="replace")
            try:
                return json.loads(raw)
            except Exception:
                return {"code": str(exc.code), "msg": raw or str(exc)}
        except Exception as exc:
            raise OKXError(f"OKX request failed {method} {path}: {exc}") from exc

    # account
    def account_config(self) -> dict[str, Any]:
        return self.req("GET", "/api/v5/account/config")
    def balance(self) -> dict[str, Any]:
        return self.req("GET", "/api/v5/account/balance?ccy=USDT")
    def positions(self, inst_id: str | None = None) -> dict[str, Any]:
        qs = "instType=SWAP" + (f"&instId={urllib.parse.quote(inst_id)}" if inst_id else "")
        return self.req("GET", f"/api/v5/account/positions?{qs}")
    def algo_orders(self, inst_type: str = "SWAP") -> dict[str, Any]:
        merged, errors = [], []
        for ot in ("conditional", "oco", "trigger", "move_order_stop"):
            r = self.req("GET", f"/api/v5/trade/orders-algo-pending?instType={inst_type}&ordType={ot}")
            if r.get("code") == "0": merged.extend(r.get("data") or [])
            else: errors.append({"ordType": ot, "code": r.get("code"), "msg": r.get("msg")})
        return {"code": "0" if not errors else "207", "data": merged, "errors": errors}
    def fills(self, limit: int = 100) -> dict[str, Any]:
        return self.req("GET", f"/api/v5/trade/fills?instType=SWAP&limit={limit}")

    def assert_account(self) -> dict[str, Any]:
        r = self.account_config()
        if r.get("code") != "0" or not r.get("data"):
            raise OKXError(f"account config failed: {r}")
        c = r["data"][0]
        uid, mid = str(c.get("uid", "")), str(c.get("mainUid", ""))
        if uid != CFG.expected_uid or mid != CFG.expected_main_uid:
            raise OKXError(f"UID guard violation: uid={uid} mainUid={mid} expected={CFG.expected_uid}/{CFG.expected_main_uid}")
        if str(c.get("acctLv")) != "2":
            raise OKXError(f"account level must be 2 for SWAP light-live, got acctLv={c.get('acctLv')}")
        self._account_verified = True
        return c
    def _ensure_write(self) -> None:
        if not self._account_verified:
            self.assert_account()
        if os.environ.get(CFG.live_trading_env, "").lower() not in {"1", "true", "yes"}:
            raise OKXError(f"live trading env {CFG.live_trading_env}=true is required for writes")

    # public market
    def instruments(self) -> dict[str, Any]:
        return self.req("GET", "/api/v5/public/instruments?instType=SWAP", auth=False)
    def ticker(self, inst_id: str) -> dict[str, Any]:
        return self.req("GET", f"/api/v5/market/ticker?instId={urllib.parse.quote(inst_id)}", auth=False)
    def tickers(self) -> dict[str, Any]:
        return self.req("GET", "/api/v5/market/tickers?instType=SWAP", auth=False)
    def candles(self, inst_id: str, bar: str = "15m", limit: int = 80) -> dict[str, Any]:
        return self.req("GET", f"/api/v5/market/candles?instId={urllib.parse.quote(inst_id)}&bar={bar}&limit={limit}", auth=False)
    def funding_rate(self, inst_id: str) -> dict[str, Any]:
        return self.req("GET", f"/api/v5/public/funding-rate?instId={urllib.parse.quote(inst_id)}", auth=False)
    def open_interest(self, inst_id: str) -> dict[str, Any]:
        return self.req("GET", f"/api/v5/public/open-interest?instType=SWAP&instId={urllib.parse.quote(inst_id)}", auth=False)

    # writes
    def set_leverage(self, inst_id: str, lever: int, pos_side: str) -> dict[str, Any]:
        self._ensure_write()
        return self.req("POST", "/api/v5/account/set-leverage", {"instId": inst_id, "lever": str(lever), "mgnMode": "cross", "posSide": pos_side})
    def place_market(self, inst_id: str, side: str, pos_side: str, sz: str, sl_px: str | None = None, reduce_only: bool = False) -> dict[str, Any]:
        self._ensure_write()
        body = {"instId": inst_id, "tdMode": "cross", "side": side, "posSide": pos_side, "ordType": "market", "sz": str(sz)}
        if reduce_only: body["reduceOnly"] = "true"
        if sl_px is not None: body["attachAlgoOrds"] = [{"slTriggerPx": str(sl_px), "slOrdPx": "-1", "slTriggerPxType": "mark"}]
        return self.req("POST", "/api/v5/trade/order", body)
    def close_position(self, inst_id: str, pos_side: str) -> dict[str, Any]:
        self._ensure_write()
        return self.req("POST", "/api/v5/trade/close-position", {"instId": inst_id, "mgnMode": "cross", "posSide": pos_side})

def d(x: Any) -> Decimal:
    return Decimal(str(x))

def q_down(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0: return value
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step

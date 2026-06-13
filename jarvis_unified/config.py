from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "runtime"
REPORT_DIR = ROOT / "reports"

@dataclass(frozen=True)
class UnifiedConfig:
    version: str = "0.1.1"
    strategy_tag: str = "unified_v0_1_1_market_phase_router_guardrails"
    okx_profile: str = "jarvis-unified-100u"
    expected_uid: str = "851731612504386465"
    expected_main_uid: str = "621655308511150593"
    site: str = "global"
    live_trading_env: str = "JARVIS_UNIFIED_LIVE_TRADING"
    allowed_maincoins: tuple[str, ...] = ("BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "BNB-USDT-SWAP")
    max_total_positions: int = 2
    max_positions_per_sleeve: int = 1
    max_margin_usage_pct: float = 0.35
    single_trade_risk_usdt: float = 0.30
    daily_realized_loss_halt_usdt: float = 1.50
    leverage_default: int = 3
    leverage_hard_cap: int = 6
    live_cycle_minutes: int = 15
    guardian_minutes: int = 5
    cold_context_hours: int = 4
    context_max_age_hours: int = 6
    min_stop_pct: float = 0.006
    max_stop_pct: float = 0.025
    maincoin_scan: tuple[str, ...] = ("BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "BNB-USDT-SWAP")
    data_dir: Path = DATA_DIR
    report_dir: Path = REPORT_DIR

CFG = UnifiedConfig()

def ensure_dirs() -> None:
    for p in (DATA_DIR, REPORT_DIR, DATA_DIR / "snapshots", DATA_DIR / "ledgers", DATA_DIR / "state"):
        p.mkdir(parents=True, exist_ok=True)

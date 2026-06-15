from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "runtime"
REPORT_DIR = ROOT / "reports"

@dataclass(frozen=True)
class UnifiedConfig:
    version: str = "1.1.1"
    strategy_tag: str = "matrix_v1_1_1_tick_safe_stops"
    okx_profile: str = "jarvis-unified-100u"
    expected_uid: str = "851731612504386465"
    expected_main_uid: str = "621655308511150593"
    site: str = "global"
    live_trading_env: str = "JARVIS_UNIFIED_LIVE_TRADING"
    allowed_maincoins: tuple[str, ...] = ("BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "BNB-USDT-SWAP")
    max_total_positions: int = 5
    max_positions_per_sleeve: int = 2
    max_margin_usage_pct: float = 0.65
    single_trade_risk_usdt: float = 0.75
    daily_realized_loss_halt_usdt: float = 4.50
    leverage_default: int = 5
    leverage_hard_cap: int = 10
    max_same_symbol_positions: int = 1
    min_live_candidate_score: float = 70.0
    alt_universe_limit: int = 100
    stopout_cooldown_hours: int = 6
    # Matrix v1.1 treats the four sleeves independently: maincoin_long, maincoin_short, alt_long, alt_short.
    sleeve_names: tuple[str, ...] = ("maincoin_long", "maincoin_short", "alt_long", "alt_short")
    allow_maincoin_short: bool = True
    allow_alt_short: bool = True
    live_cycle_minutes: int = 15
    guardian_minutes: int = 5
    guardian_tp_state_file: str = "guardian_tp_state.json"
    guardian_be_r: float = 0.8
    guardian_tp1_r: float = 1.5
    guardian_tp1_fraction: float = 0.5
    guardian_lock_r: float = 2.0
    guardian_lock_profit_r: float = 0.5
    guardian_full_close_r: float = 3.0
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

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "runtime"
REPORT_DIR = ROOT / "reports"

@dataclass(frozen=True)
class UnifiedConfig:
    version: str = "1.3.1"
    strategy_tag: str = "matrix_v1_3_1_loss_logic_repair"
    okx_profile: str = "jarvis-unified-100u"
    expected_uid: str = "851731612504386465"
    expected_main_uid: str = "621655308511150593"
    site: str = "global"
    live_trading_env: str = "JARVIS_UNIFIED_LIVE_TRADING"
    allowed_maincoins: tuple[str, ...] = ("BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "BNB-USDT-SWAP")
    max_total_positions: int = 6
    max_positions_per_sleeve: int = 3
    # v1.3.0: family budgets keep Matrix from degenerating into an alt-only account.
    max_maincoin_positions_total: int = 3
    max_alt_positions_total: int = 3
    maincoin_reserved_slots: int = 1
    max_margin_usage_pct: float = 0.75
    single_trade_risk_usdt: float = 1.00
    daily_realized_loss_halt_usdt: float = 6.00
    rolling_24h_loss_halt_usdt: float = 6.00
    rolling_24h_loss_halt_enabled: bool = True
    leverage_default: int = 5
    leverage_hard_cap: int = 10
    max_same_symbol_positions: int = 1
    min_live_candidate_score: float = 70.0
    alt_universe_limit: int = 120
    stopout_cooldown_hours: int = 6
    growth_mode: str = "loss_logic_repair"
    max_orders_per_cycle: int = 1
    candle_rescore_top_n: int = 16
    opportunity_block_min_score: float = 85.0
    post_order_sl_confirm_attempts: int = 3
    post_order_sl_confirm_delay_sec: float = 1.0
    # Matrix v1.3 treats the four sleeves independently: maincoin_long, maincoin_short, alt_long, alt_short.
    sleeve_names: tuple[str, ...] = ("maincoin_long", "maincoin_short", "alt_long", "alt_short")
    allow_maincoin_short: bool = True
    allow_alt_short: bool = True
    live_cycle_minutes: int = 15
    guardian_minutes: int = 5
    guardian_tp_state_file: str = "guardian_tp_state.json"
    guardian_be_r: float = 1.0
    guardian_tp1_r: float = 1.5
    guardian_tp1_fraction: float = 0.5
    guardian_lock_r: float = 2.0
    guardian_lock_profit_r: float = 0.5
    guardian_full_close_r: float = 3.0
    # v1.3.0 protection logic: keep existing thresholds, add stateful giveback/time semantics.
    guardian_mfe_giveback_enabled: bool = True
    guardian_giveback_min_mfe_r: float = 1.2
    guardian_giveback_floor_r: float = 0.25
    guardian_giveback_ratio: float = 0.70
    guardian_time_stop_enabled: bool = True
    guardian_alt_time_stop_hours: float = 4.0
    guardian_alt_time_stop_min_r: float = 0.30
    guardian_maincoin_time_stop_hours: float = 8.0
    guardian_maincoin_time_stop_min_r: float = 0.20
    cold_context_hours: int = 4
    context_max_age_hours: int = 6
    min_stop_pct: float = 0.006
    max_stop_pct: float = 0.025
    tight_stop_notional_cap_usdt: float = 60.0
    tight_stop_threshold_pct: float = 0.012
    maincoin_scan: tuple[str, ...] = ("BTC-USDT-SWAP", "ETH-USDT-SWAP", "SOL-USDT-SWAP", "BNB-USDT-SWAP")
    # v1.3.0 maincoin range lane; conservative, BTC/ETH first.
    range_maincoins: tuple[str, ...] = ("BTC-USDT-SWAP", "ETH-USDT-SWAP")
    maincoin_range_enabled: bool = True
    maincoin_range_min_distance: float = 0.004
    maincoin_range_max_atr_pct: float = 0.016
    maincoin_range_score_threshold: float = 68.0
    # v1.3.0 selection: sleeve interleave prevents alt candidates from monopolizing plan evaluation.
    live_selection_mode: str = "sleeve_interleave"
    max_candidates_per_sleeve_per_cycle: int = 3
    data_dir: Path = DATA_DIR
    report_dir: Path = REPORT_DIR

CFG = UnifiedConfig()

def ensure_dirs() -> None:
    for p in (DATA_DIR, REPORT_DIR, DATA_DIR / "snapshots", DATA_DIR / "ledgers", DATA_DIR / "state"):
        p.mkdir(parents=True, exist_ok=True)

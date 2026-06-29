import os
import threading
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]

SETTINGS_FILE = BASE_DIR / "settings_store.json"
SHADOW_FILE = BASE_DIR / "shadow_store.json"

SHADOW_LOCK = threading.Lock()

DEFAULT_USER = "default"


def get_binance_mode() -> str:
    mode = str(os.getenv("BINANCE_MODE", "testnet") or "testnet").strip().lower()

    if mode not in {"testnet", "mainnet"}:
        return "testnet"

    return mode


def get_binance_spot_base_url() -> str:
    if get_binance_mode() == "mainnet":
        return "https://api.binance.com/api"

    return "https://testnet.binance.vision/api"


BINANCE_MODE = get_binance_mode()
BINANCE_SPOT_BASE_URL = get_binance_spot_base_url()


DEFAULT_COIN_FILTER = {
    "min_quote_volume": 1000000,
    "min_trade_count": 1000,
    "min_volatility": 0.4,
    "volatility_candle_count": 12,
    "volatility_interval": "15m",

    "rsi_min_15m": 50,
    "rsi_min_1h": 50,
    "rsi_min_4h": 50,

    "rsi_max_15m": 75,
    "rsi_max_1h": 75,
    "rsi_max_4h": 75,

    "volume_growth_multiplier": 1,
    "quality_score_min": 45,
    "lightweight_score_min": 55,

    "excluded_symbols": (
        "USDCUSDT,FDUSDUSDT,BUSDUSDT,TUSDUSDT,"
        "DAIUSDT,EURUSDT,USDPUSDT"
    )
}


DEFAULT_STRATEGIES = [
    {
        "name": "Momentum",
        "active": True,
        "type": "momentum",
        "description": "Trend, EMA, hacim ve momentum uyumu arar."
    },
    {
        "name": "Breakout",
        "active": True,
        "type": "breakout",
        "description": "Direnç kırılımı ve hacim artışı sonrası aday arar."
    },
    {
        "name": "Mean Reversion",
        "active": True,
        "type": "mean_reversion",
        "description": "Aşırı düşmüş ama toparlanma sinyali veren coinleri izler."
    },
    {
        "name": "Scalping",
        "active": False,
        "type": "scalping",
        "description": "Kısa zaman diliminde hızlı momentum fırsatlarını arar."
    },
    {
        "name": "RSI Divergence",
        "active": False,
        "type": "rsi_divergence",
        "description": "RSI uyumsuzluğu ile dönüş ihtimali arar."
    },
    {
        "name": "Total2 Uptrend",
        "active": False,
        "type": "total2_uptrend",
        "description": "TOTAL2 yükseliyorsa alt market için pozitif filtre uygular."
    },
    {
        "name": "Total2 Divergence",
        "active": False,
        "type": "total2_divergence",
        "description": "TOTAL yatayken TOTAL2 güçleniyorsa altcoin rotasyonu arar."
    },
    {
        "name": "Alt Risk Off",
        "active": False,
        "type": "alt_risk_off",
        "description": "TOTAL2 zayıfsa yeni altcoin girişlerini engeller."
    }
]


DEFAULT_SHADOW_STATE = {
    "settings": {},
    "settings_source": "settings_store_mirror",
    "settings_updated_at": None,
    "bot_running": False,
    "requested_running": False,
    "mode": "shadow",
    "engine_status": "stopped",
    "tick_in_progress": False,
    "active_scan_worker": False,
    "scan_worker_started_at": None,
    "scan_worker_deadline_at": None,
    "scan_cancel_requested": False,
    "scan_worker_generation": 0,
    "last_tick_started_at": None,
    "last_tick_finished_at": None,
    "next_tick_not_before": None,
    "bot_loop_backoff_seconds": 60,

    "bot_started_at": None,
    "bot_stopped_at": None,
    "last_tick": None,
    "last_updated_at": None,
    "last_calculation_at": None,
    "last_scan_time": None,

    "open_positions": [],
    "history": [],
    "logs": [],
    "performance_points": [],

    "last_scan": {
        "status": "idle",
        "time": None,
        "scanned": 0,
        "candidates_count": 0,
        "candidates": [],
        "scan_rows": [],
        "error": None
    }
}

from datetime import datetime
from uuid import uuid4
import copy
import threading
import time

from fastapi import APIRouter, Depends, HTTPException

from core.auth import require_owner, require_user
from core.config import DEFAULT_USER
from core.storage import (
    append_audit,
    append_log,
    archive_shadow_state,
    list_shadow_archives,
    load_shadow,
    load_settings,
    restore_shadow_archive,
    save_shadow,
    sync_last_scan_state,
    sync_settings_state,
)
from services.analysis_service import build_coinfilter_pipeline, build_filter_rejection_counts, build_scan_settings_snapshot, build_unique_filter_rejection_counts, scan_debug, scan_market
from services.bot_service import (
    emergency_stop_bot,
    reset_bot_state,
    run_bot_tick,
    start_bot,
    stop_bot,
)
from services.bot_runtime_truth_service import build_bot_runtime_truth
from services.coin_universe_final_service import append_scan_history, build_scan_history, build_scan_replay
from services.market_service import get_market_symbols
from services.performance_service import build_dashboard_summary
from services.real_trade_safety_service import build_real_trade_safety_status, build_runtime_health
from services.real_trade_state_service import ensure_real_trade_state, lock_real_trading
from infrastructure.runtime.bot_scan_worker import cancel_scan_worker, reconcile_stale_scan_worker
from infrastructure.runtime.bot_runtime_registry import mark_user_bot_requested


router = APIRouter(
    prefix="/api/bot",
    tags=["bot"]
)


COINFILTER_TEST_SCAN_MAX_LIMIT = 350
COINFILTER_TEST_SCAN_TIMEOUT_SECONDS = 8
COINFILTER_TEST_SCAN_COOLDOWN_SECONDS = 20
_COINFILTER_TEST_SCAN_LOCKS: dict[str, threading.Lock] = {}
_COINFILTER_TEST_SCAN_CACHE: dict[str, dict] = {}
_COINFILTER_TEST_SCAN_CACHE_AT: dict[str, float] = {}
_COINFILTER_TEST_SCAN_GLOBAL_LOCK = threading.Lock()


def _coinfilter_lock(user: str) -> threading.Lock:
    with _COINFILTER_TEST_SCAN_GLOBAL_LOCK:
        if user not in _COINFILTER_TEST_SCAN_LOCKS:
            _COINFILTER_TEST_SCAN_LOCKS[user] = threading.Lock()
        return _COINFILTER_TEST_SCAN_LOCKS[user]


def _clone_payload(value: dict | None) -> dict:
    try:
        return copy.deepcopy(value or {})
    except Exception:
        return dict(value or {})


def _cached_coinfilter_scan(user: str) -> dict:
    cached = _clone_payload(_COINFILTER_TEST_SCAN_CACHE.get(user))
    if cached:
        cached.setdefault("scan_diagnostics", {})
        cached["scan_diagnostics"]["safe_scan_cache_hit"] = True
        cached["cached"] = True
    return cached


def _remember_coinfilter_scan(user: str, scan: dict) -> None:
    _COINFILTER_TEST_SCAN_CACHE[user] = _clone_payload(scan)
    _COINFILTER_TEST_SCAN_CACHE_AT[user] = time.monotonic()


def _decorate_coinfilter_scan(scan: dict, *, user: str, requested_limit: int, applied_limit: int, cached: bool = False, busy: bool = False) -> dict:
    scan = _clone_payload(scan)
    scan["test_scan"] = True
    scan["mode"] = "coinfilter_test_scan"
    scan["filter_rejection_counts"] = scan.get("filter_rejection_counts") or build_unique_filter_rejection_counts(
        scan.get("scan_rows", []), scan.get("universe_rejection_breakdown_unique", {})
    )
    scan["filter_rejection_counts_cumulative"] = scan.get("filter_rejection_counts_cumulative") or build_filter_rejection_counts(
        scan.get("universe_rejection_breakdown", {}), scan.get("rejection_breakdown", {})
    )
    scan["pipeline"] = build_coinfilter_pipeline(scan, test_scan=True)
    scan.setdefault("scan_diagnostics", {})
    if isinstance(scan.get("settings_snapshot"), dict):
        scan.setdefault("coin_filter_settings_used", scan.get("settings_snapshot", {}).get("coin_filter_effective", {}))
    elif isinstance(scan.get("scan_diagnostics"), dict):
        scan.setdefault("coin_filter_settings_used", scan["scan_diagnostics"].get("coin_filter_settings_used", {}))
    scan["scan_diagnostics"].update({
        "test_scan": True,
        "safe_scan": True,
        "safe_scan_requested_limit": requested_limit,
        "safe_scan_applied_limit": applied_limit,
        "safe_scan_max_limit": COINFILTER_TEST_SCAN_MAX_LIMIT,
        "safe_scan_timeout_seconds": COINFILTER_TEST_SCAN_TIMEOUT_SECONDS,
        "safe_scan_cached": bool(cached),
        "safe_scan_busy": bool(busy),
        "execution_note": "CoinFilter test scan strateji, Karabasan, risk veya execution calistirmaz.",
    })
    return scan


def current_username(current_user: dict) -> str:
    username = str(current_user.get("username") or "").strip()
    return username or DEFAULT_USER


def _safe_int(value, fallback: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _reason_label(reason: str | None) -> str:
    labels = {
        "stable_pair": "Stable parite",
        "leveraged_token": "Kaldıraçlı token",
        "invalid_price": "Geçersiz fiyat",
        "low_quote_volume": "Düşük USDT hacim",
        "low_trade_count": "Düşük işlem adedi",
        "low_volatility": "Düşük volatilite",
        "weak_volume_growth": "Zayıf hacim artışı",
        "ema_not_aligned": "EMA uyumsuz",
        "rsi_out_of_range": "RSI aralık dışı",
        "macd_negative": "MACD negatif",
        "low_quality_score": "Düşük kalite skoru",
        "analysis_error": "Analiz hatası",
        "technical_analysis_error": "Teknik analiz hatası",
        "score_below_threshold": "Skor eşiği altı",
        "not_passed": "Geçemedi",
        "bot_not_running": "Bot çalışmıyor",
        "daily_loss_limit": "Günlük zarar limiti",
        "scan_not_ok": "Scan başarısız",
    }

    return labels.get(str(reason or ""), str(reason or "-"))


def _sort_breakdown(breakdown: dict | None) -> list[dict]:
    if not isinstance(breakdown, dict):
        return []

    rows = []

    for key, value in breakdown.items():
        rows.append({
            "reason": key,
            "label": _reason_label(key),
            "count": _safe_int(value),
        })

    rows.sort(key=lambda item: item["count"], reverse=True)
    return rows


def _scan_rows(scan: dict) -> list[dict]:
    rows = scan.get("scan_rows") if isinstance(scan.get("scan_rows"), list) else []
    if rows:
        return rows

    candidates = scan.get("candidates") if isinstance(scan.get("candidates"), list) else []
    return candidates


def _build_scan_funnel(scan: dict, data: dict, settings: dict) -> dict:
    rows = _scan_rows(scan)
    candidates = scan.get("candidates") if isinstance(scan.get("candidates"), list) else []

    total_seen = _safe_int(scan.get("universe_total_seen"), _safe_int(scan.get("scanned"), len(rows)))
    universe_rejected = _safe_int(scan.get("universe_rejected_count"), 0)
    eligible = _safe_int(scan.get("eligible_universe_count"), _safe_int(scan.get("scanned"), len(rows)))

    technical_passed = _safe_int(scan.get("candidates_count"), len(candidates))
    technical_rejected = _safe_int(scan.get("rejected_count"), max(eligible - technical_passed, 0))

    paper_lab = data.get("paper_lab") if isinstance(data.get("paper_lab"), dict) else {}
    models = paper_lab.get("models") if isinstance(paper_lab.get("models"), dict) else {}

    active_models = [
        model
        for model in models.values()
        if isinstance(model, dict) and model.get("status", "active") == "active"
    ]

    open_positions = data.get("open_positions") if isinstance(data.get("open_positions"), list) else []
    history = data.get("history") if isinstance(data.get("history"), list) else []

    latest_tick = None
    traces = data.get("bot_loop_traces") if isinstance(data.get("bot_loop_traces"), list) else []
    if traces:
        latest_tick = traces[-1]

    final_candidate_count = technical_passed
    opened_symbol = (latest_tick or {}).get("opened_symbol") if isinstance(latest_tick, dict) else None

    if not scan:
        main_block_reason = "scan_yok"
        main_block_label = "Henüz scan verisi yok"
    elif scan.get("status") != "ok":
        main_block_reason = scan.get("error") or scan.get("status") or "scan_not_ok"
        main_block_label = _reason_label(main_block_reason)
    elif technical_passed < 1:
        main_block_reason = scan.get("top_rejection_reason") or "no_candidate"
        main_block_label = _reason_label(main_block_reason)
    elif not active_models:
        main_block_reason = "paper_lab_model_yok"
        main_block_label = "Aktif Paper Lab modeli yok"
    elif not opened_symbol:
        main_block_reason = "strategy_or_risk_no_trade"
        main_block_label = "Strateji/risk koşulları işlem açtırmadı"
    else:
        main_block_reason = None
        main_block_label = "İşlem açıldı"

    karabasan = data.get("karabasan") if isinstance(data.get("karabasan"), dict) else {}
    risk_state = data.get("risk_state") if isinstance(data.get("risk_state"), dict) else {}
    strategy_signal_count = _safe_int(
        (latest_tick or {}).get("strategy_signal_count") if isinstance(latest_tick, dict) else None,
        _safe_int(scan.get("strategy_signal_count"), 0),
    )
    karabasan_passed = bool(
        karabasan.get("allow_trading", karabasan.get("passed", data.get("karabasan_passed", True)))
    )
    risk_passed = bool(
        risk_state.get("passed", data.get("risk_passed", data.get("risk_gate_open", True)))
    )
    trade_opened = bool(opened_symbol)
    top_blockers = (
        _sort_breakdown(scan.get("universe_rejection_breakdown"))[:5] +
        _sort_breakdown(scan.get("rejection_breakdown"))[:5]
    )

    return {
        "status": "ok",
        "scan_total": total_seen,
        "coinfilter_passed": technical_passed,
        "coinfilter_rejected": technical_rejected + universe_rejected,
        "strategy_signal_count": strategy_signal_count,
        "karabasan_passed": karabasan_passed,
        "risk_passed": risk_passed,
        "final_trade_candidate_count": final_candidate_count,
        "trade_opened": trade_opened,
        "primary_no_trade_reason": main_block_reason,
        "top_blockers": top_blockers,
        "total_seen": total_seen,
        "universe_rejected": universe_rejected,
        "eligible_universe": eligible,
        "technical_passed": technical_passed,
        "technical_rejected": technical_rejected,
        "active_models": len(active_models),
        "final_candidate_count": final_candidate_count,
        "open_positions_count": len(open_positions),
        "history_count": len(history),
        "opened_symbol": opened_symbol,
        "main_block_reason": main_block_reason,
        "main_block_label": main_block_label,
        "stages": [
            {
                "key": "total_seen",
                "label": "Toplam Görülen",
                "value": total_seen,
                "description": "Binance USDT evreninden görülen toplam parite.",
            },
            {
                "key": "eligible_universe",
                "label": "Evrene Kalan",
                "value": eligible,
                "description": "Stable, leveraged, fiyat/hacim temel guardlarından sonra kalan coin.",
            },
            {
                "key": "technical_passed",
                "label": "Teknik Filtreden Geçen",
                "value": technical_passed,
                "description": "Volatilite, volume growth, RSI, EMA, MACD ve kalite kontrollerinden geçen coin.",
            },
            {
                "key": "active_models",
                "label": "Aktif Model",
                "value": len(active_models),
                "description": "Aktif filtre + strateji kombinasyon modeli.",
            },
            {
                "key": "final_candidate_count",
                "label": "Final Aday",
                "value": final_candidate_count,
                "description": "İşlem hattına girebilecek aday coin sayısı.",
            },
            {
                "key": "opened_symbol",
                "label": "Açılan İşlem",
                "value": opened_symbol or "-",
                "description": "Son tick içinde açılan coin.",
            },
        ],
        "breakdowns": {
            "universe": _sort_breakdown(scan.get("universe_rejection_breakdown")),
            "technical": _sort_breakdown(scan.get("rejection_breakdown")),
        },
        "latest_tick": latest_tick or {},
        "settings_snapshot": {
            "scan_limit": ((settings.get("bot") or {}).get("scan_limit")),
            "scan_deep_analysis_limit": ((settings.get("bot") or {}).get("scan_deep_analysis_limit")),
            "min_quote_volume": ((settings.get("coin_filter") or {}).get("min_quote_volume")),
            "min_trade_count": ((settings.get("coin_filter") or {}).get("min_trade_count")),
            "min_volatility": ((settings.get("coin_filter") or {}).get("min_volatility")),
            "volume_growth_multiplier": ((settings.get("coin_filter") or {}).get("volume_growth_multiplier")),
            "volatility_interval": ((settings.get("coin_filter") or {}).get("volatility_interval")),
            "volatility_candle_count": ((settings.get("coin_filter") or {}).get("volatility_candle_count")),
            "rsi_min_15m": ((settings.get("coin_filter") or {}).get("rsi_min_15m")),
            "rsi_max_15m": ((settings.get("coin_filter") or {}).get("rsi_max_15m")),
            "rsi_min_1h": ((settings.get("coin_filter") or {}).get("rsi_min_1h")),
            "rsi_max_1h": ((settings.get("coin_filter") or {}).get("rsi_max_1h")),
            "rsi_min_4h": ((settings.get("coin_filter") or {}).get("rsi_min_4h")),
            "rsi_max_4h": ((settings.get("coin_filter") or {}).get("rsi_max_4h")),
        },
    }


def _last_scan_payload(user: str, data: dict, settings: dict) -> dict:
    last_scan = data.get("last_scan", {})
    last_scan = last_scan if isinstance(last_scan, dict) else {}

    scan_rows = last_scan.get("scan_rows", [])
    candidates = last_scan.get("candidates", [])

    if not isinstance(scan_rows, list):
        scan_rows = []
    if not isinstance(candidates, list):
        candidates = []

    current_settings_snapshot = build_scan_settings_snapshot(settings)
    scan_settings_snapshot = last_scan.get("settings_snapshot") if isinstance(last_scan.get("settings_snapshot"), dict) else {}
    coin_filter_settings_used = last_scan.get("coin_filter_settings_used")
    if not isinstance(coin_filter_settings_used, dict):
        diagnostics = last_scan.get("scan_diagnostics") if isinstance(last_scan.get("scan_diagnostics"), dict) else {}
        coin_filter_settings_used = diagnostics.get("coin_filter_settings_used") if isinstance(diagnostics.get("coin_filter_settings_used"), dict) else scan_settings_snapshot.get("coin_filter_effective", {})
    settings_changed_since_scan = bool(
        scan_settings_snapshot
        and current_settings_snapshot.get("coin_filter") != scan_settings_snapshot.get("coin_filter")
    )

    return {
        "status": "ok",
        "user": user,
        "mode": data.get("mode", "shadow"),
        "live": bool(last_scan.get("live")),
        "time": last_scan.get("time"),
        "scan_id": last_scan.get("scan_id"),
        "source": last_scan.get("source"),
        "scan_mode": last_scan.get("mode"),
        "test_scan": bool(last_scan.get("test_scan", False)),
        "pipeline": last_scan.get("pipeline", {}) if isinstance(last_scan.get("pipeline"), dict) else {},
        "scanned": last_scan.get("scanned", 0),
        "eligible_universe_count": last_scan.get("eligible_universe_count", 0),
        "universe_total_seen": last_scan.get("universe_total_seen", last_scan.get("scanned", 0)),
        "universe_rejected_count": last_scan.get("universe_rejected_count", 0),
        "candidates_count": last_scan.get("candidates_count", len(candidates)),
        "rejected_count": last_scan.get("rejected_count", 0),
        "top_rejection_reason": last_scan.get("top_rejection_reason"),
        "rejection_breakdown": last_scan.get("rejection_breakdown", {}),
        "universe_rejection_breakdown": last_scan.get("universe_rejection_breakdown", {}),
        "filter_rejection_counts": last_scan.get("filter_rejection_counts") or build_unique_filter_rejection_counts(scan_rows, last_scan.get("universe_rejection_breakdown_unique", {})),
        "filter_rejection_counts_cumulative": last_scan.get("filter_rejection_counts_cumulative") or build_filter_rejection_counts(last_scan.get("universe_rejection_breakdown", {}), last_scan.get("rejection_breakdown", {})),
        "settings_snapshot": scan_settings_snapshot,
        "current_settings_snapshot": current_settings_snapshot,
        "coin_filter_settings_used": coin_filter_settings_used,
        "settings_changed_since_scan": settings_changed_since_scan,
        "scan_diagnostics": {**(last_scan.get("scan_diagnostics", {}) if isinstance(last_scan.get("scan_diagnostics", {}), dict) else {}), "coin_filter_settings_used": coin_filter_settings_used},
        "scan_trace": last_scan.get("scan_trace", {}),
        "candidates": candidates,
        "scan_rows": scan_rows,
        "funnel_summary": _build_scan_funnel(last_scan, data, settings),
        "error": last_scan.get("error"),
    }


@router.get("/scan")
def bot_scan(
    limit: int = 1000,
    current_user: dict = Depends(require_user),
):
    user = current_username(current_user)
    settings = load_settings(user)
    data = load_shadow(user)

    if not data.get("bot_running", False):
        return {
            "status": "skipped",
            "user": user,
            "mode": data.get("mode", "shadow"),
            "live": False,
            "source": "binance",
            "scanned": 0,
            "candidates_count": 0,
            "candidates": [],
            "scan_rows": [],
            "error": "bot_not_running"
        }

    scan = scan_market(settings, limit=limit, deep_analysis=True)
    sync_last_scan_state(data, scan)
    append_scan_history(data, scan)
    save_shadow(data, user)

    return scan


@router.get("/market-scan")
def bot_public_market_scan(
    limit: int = 200,
    current_user: dict = Depends(require_user),
):
    user = current_username(current_user)
    settings = load_settings(user)
    data = load_shadow(user)

    limit = max(20, min(int(limit or 200), 1000))

    market = get_market_symbols(
        limit=limit,
        settings=settings,
        strict=False
    )

    now_text = datetime.now().isoformat(timespec="seconds")
    scan_id = str(uuid4())

    if market.get("status") != "ok":
        return {
            "status": "error",
            "mode": "paper_market_scan",
            "live": False,
            "source": "binance_public",
            "api_key_required": False,
            "time": now_text,
            "scan_id": scan_id,
            "scanned": 0,
            "candidates_count": 0,
            "rejected_count": 0,
            "candidates": [],
            "scan_rows": [],
            "error": market.get("error", "market_scan_failed"),
        }

    rows = []

    for item in market.get("symbols", []) or []:
        symbol = str(item.get("symbol") or "").upper()

        try:
            quote_volume = float(item.get("quote_volume") or item.get("quoteVolume") or 0)
        except (TypeError, ValueError):
            quote_volume = 0

        rows.append({
            "symbol": symbol,
            "price": item.get("price") or item.get("lastPrice"),
            "volume": item.get("volume"),
            "quote_volume": round(quote_volume, 2),
            "volume_today": round(quote_volume, 2),
            "trade_count": item.get("trade_count") or item.get("count"),
            "change_percent": item.get("change_percent") or item.get("priceChangePercent"),
            "rsi": "-",
            "status": "candidate",
            "passed": True,
            "score": 0,
            "reason": None,
            "rejection_reasons": [],
            "analysis_depth": "public_volume_scan",
        })

    rows.sort(key=lambda item: float(item.get("quote_volume") or 0), reverse=True)

    scan = {
        "status": "ok",
        "mode": "paper_market_scan",
        "live": True,
        "source": "binance_public",
        "api_key_required": False,
        "time": now_text,
        "scan_id": scan_id,
        "requested_limit": limit,
        "scanned": len(rows),
        "eligible_universe_count": len(rows),
        "universe_total_seen": market.get("total_seen", len(rows)),
        "universe_rejected_count": market.get("universe_rejected_count", 0),
        "universe_rejection_breakdown": market.get("universe_rejection_breakdown", {}),
        "universe_rejection_breakdown_unique": market.get("universe_rejection_breakdown_unique", {}),
        "candidates_count": len(rows),
        "rejected_count": int(market.get("universe_rejected_count") or 0),
        "top_rejection_reason": None,
        "rejection_breakdown": {},
        "filter_rejection_counts": build_unique_filter_rejection_counts(rows, market.get("universe_rejection_breakdown_unique", {})),
        "filter_rejection_counts_cumulative": build_filter_rejection_counts(market.get("universe_rejection_breakdown", {}), {}),
        "candidates": rows,
        "scan_rows": rows,
        "scan_diagnostics": {
            "mode": "public_binance_volume_scan",
            "note": "API key gerekmez. Stable coinler ve leveraged tokenlar elenir.",
        },
        "error": None,
    }

    sync_last_scan_state(data, scan)
    append_scan_history(data, scan)
    save_shadow(data, user)

    return scan


@router.get("/coinfilter-test-scan")
def bot_coinfilter_test_scan(
    limit: int = 1000,
    current_user: dict = Depends(require_user),
):
    user = current_username(current_user)
    settings = load_settings(user)
    data = load_shadow(user)
    settings_mirror_changed = sync_settings_state(data, settings)
    if settings_mirror_changed:
        save_shadow(data, user)

    requested_limit = max(20, _safe_int(limit, 1000))
    applied_limit = max(20, min(requested_limit, COINFILTER_TEST_SCAN_MAX_LIMIT))
    now_monotonic = time.monotonic()
    cached_age = now_monotonic - _COINFILTER_TEST_SCAN_CACHE_AT.get(user, 0)

    if cached_age < COINFILTER_TEST_SCAN_COOLDOWN_SECONDS:
        cached = _cached_coinfilter_scan(user)
        if cached:
            return _decorate_coinfilter_scan(cached, user=user, requested_limit=requested_limit, applied_limit=applied_limit, cached=True)

    lock = _coinfilter_lock(user)
    if not lock.acquire(blocking=False):
        cached = _cached_coinfilter_scan(user)
        if cached:
            return _decorate_coinfilter_scan(cached, user=user, requested_limit=requested_limit, applied_limit=applied_limit, cached=True, busy=True)
        return {
            "status": "busy",
            "user": user,
            "mode": "coinfilter_test_scan",
            "test_scan": True,
            "live": False,
            "source": "cache",
            "scanned": 0,
            "candidates_count": 0,
            "rejected_count": 0,
            "candidates": [],
            "scan_rows": [],
            "filter_rejection_counts": build_filter_rejection_counts({}, {}),
            "filter_rejection_counts_cumulative": build_filter_rejection_counts({}, {}),
            "scan_diagnostics": {
                "test_scan": True,
                "safe_scan": True,
                "safe_scan_busy": True,
                "safe_scan_requested_limit": requested_limit,
                "safe_scan_applied_limit": applied_limit,
                "safe_scan_max_limit": COINFILTER_TEST_SCAN_MAX_LIMIT,
                "execution_note": "CoinFilter test scan zaten çalışıyor; yeni CPU işi başlatılmadı.",
            },
            "error": "coinfilter_test_scan_already_running",
        }

    try:
        scan = scan_market(
            settings,
            limit=applied_limit,
            deep_analysis=False,
            timeout_seconds=COINFILTER_TEST_SCAN_TIMEOUT_SECONDS,
            deep_analysis_timeout_seconds=1,
        )
        scan = _decorate_coinfilter_scan(scan, user=user, requested_limit=requested_limit, applied_limit=applied_limit)
        _remember_coinfilter_scan(user, scan)
        sync_last_scan_state(data, scan)
        append_scan_history(data, scan)
        save_shadow(data, user)
        return scan
    except TimeoutError as error:
        cached = _cached_coinfilter_scan(user)
        if cached:
            cached["error"] = "coinfilter_test_scan_timeout_returned_cached"
            return _decorate_coinfilter_scan(cached, user=user, requested_limit=requested_limit, applied_limit=applied_limit, cached=True)
        return {
            "status": "timeout",
            "user": user,
            "mode": "coinfilter_test_scan",
            "test_scan": True,
            "live": False,
            "source": "binance",
            "scanned": 0,
            "candidates_count": 0,
            "rejected_count": 0,
            "candidates": [],
            "scan_rows": [],
            "filter_rejection_counts": build_filter_rejection_counts({}, {}),
            "filter_rejection_counts_cumulative": build_filter_rejection_counts({}, {}),
            "scan_diagnostics": {
                "test_scan": True,
                "safe_scan": True,
                "safe_scan_timeout_seconds": COINFILTER_TEST_SCAN_TIMEOUT_SECONDS,
                "safe_scan_requested_limit": requested_limit,
                "safe_scan_applied_limit": applied_limit,
            },
            "error": str(error) or "coinfilter_test_scan_timeout",
        }
    finally:
        lock.release()


@router.get("/last-scan")
def bot_last_scan(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    if sync_settings_state(data, settings):
        save_shadow(data, user)
    return _last_scan_payload(user, data, settings)


@router.get("/scan-explain")
def bot_scan_explain(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)

    payload = _last_scan_payload(user, data, settings)

    return {
        "status": "ok",
        "user": user,
        "scan": payload,
        "funnel_summary": payload.get("funnel_summary", {}),
        "settings_snapshot": (payload.get("funnel_summary") or {}).get("settings_snapshot", {}),
        "scan_rows": payload.get("scan_rows", []),
        "candidates": payload.get("candidates", []),
        "breakdowns": (payload.get("funnel_summary") or {}).get("breakdowns", {}),
    }


@router.get("/scan-history")
def bot_scan_history(limit: int = 50, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    payload = build_scan_history(data, limit=limit)
    payload["user"] = user
    return payload


@router.get("/scan-replay")
def bot_scan_replay(scan_id: str | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    payload = build_scan_replay(data, scan_id=scan_id)
    payload["user"] = user
    return payload


@router.get("/scan-debug")
def bot_scan_debug(
    limit: int = 10,
    current_user: dict = Depends(require_user),
):
    user = current_username(current_user)
    settings = load_settings(user)
    result = scan_debug(settings, limit=limit)
    result["user"] = user
    return result


@router.post("/tick")
def bot_tick(
    limit: int = 1000,
    current_user: dict = Depends(require_user),
):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)

    result = run_bot_tick(data, settings, limit=limit)
    save_shadow(data, user)
    result["user"] = user

    return result


@router.get("/status")
def bot_status(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = reconcile_stale_scan_worker(user)
    settings = load_settings(user)

    dashboard = build_dashboard_summary(data, settings)

    risk = settings.get("risk", {})
    bot = settings.get("bot", {})

    runtime_health = build_runtime_health(data, settings)
    runtime_truth = build_bot_runtime_truth(data, settings, username=user)
    last_scan = data.get("last_scan") if isinstance(data.get("last_scan"), dict) else {}
    last_scan_time = data.get("last_scan_time") or last_scan.get("time")
    return {
        "status": "ok",
        "user": user,
        "requested_running": runtime_truth["requested_running"],
        "thread_alive": runtime_truth["thread_alive"],
        "loop_alive": runtime_truth["loop_alive"],
        "bot_running": runtime_truth["bot_running"],
        "mode": data.get("mode", "shadow"),
        "engine_status": runtime_truth["engine_status"],
        "runtime_health_status": runtime_truth["runtime_health_status"],
        "last_tick_age_seconds": runtime_truth["last_tick_age_seconds"],
        "last_scan_age_seconds": runtime_truth["last_scan_age_seconds"],
        "restart_required": runtime_truth["restart_required"],
        "primary_runtime_problem": runtime_truth["primary_runtime_problem"],
        "bot_task_running": runtime_truth["bot_task_running"],
        "bot_task_started_at": runtime_truth["bot_task_started_at"],
        "bot_task_last_heartbeat_at": runtime_truth["bot_task_last_heartbeat_at"],
        "bot_task_exception": runtime_truth["bot_task_exception"],

        "bot_started_at": data.get("bot_started_at"),
        "bot_stopped_at": data.get("bot_stopped_at"),
        "last_tick": data.get("last_tick"),
        "last_updated_at": data.get("last_updated_at"),
        "last_calculation_at": data.get("last_calculation_at"),
        "stop_reason": data.get("stop_reason"),

        "runtime_seconds": dashboard.get("runtime_seconds"),
        "runtime_text": dashboard.get("runtime_text"),

        "open_positions_count": len(data.get("open_positions", [])),
        "max_open_positions": bot.get("max_open_positions", 5),
        "usdt_per_position": bot.get("usdt_per_position", 200),
        "daily_loss_limit": risk.get("daily_loss_limit", "30 USDT"),

        "last_scan_live": bool(last_scan.get("live")),
        "last_scan_time": last_scan_time,
        "last_scan_error": last_scan.get("error"),
        "active_scan_worker": bool(data.get("active_scan_worker")),
        "scan_worker_started_at": data.get("scan_worker_started_at"),
        "scan_worker_deadline_at": data.get("scan_worker_deadline_at"),
        "scan_cancel_requested": bool(data.get("scan_cancel_requested")),
        "scan_worker_generation": int(data.get("scan_worker_generation") or 0),
        "runtime_health": runtime_health,
        "real_trade_safety": build_real_trade_safety_status(data, settings),
    }


@router.post("/start")
def bot_start(mode: str = "paper", current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    cancel_scan_worker(user, reason="heartbeat_only_start_cleanup")
    data = load_shadow(user)

    if data.get("emergency_lock"):
        raise HTTPException(status_code=423, detail="Emergency lock aktif. Owner recovery unlock olmadan bot başlatılamaz.")

    already_running = bool(
        data.get("requested_running")
        and data.get("bot_running")
        and str(data.get("engine_status") or "") == "running"
    )

    try:
        start_bot(data, mode=mode)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    mark_user_bot_requested(user, True)
    save_shadow(data, user)
    runtime_truth = build_bot_runtime_truth(data, load_settings(user), username=user)

    return {
        "status": "already_running" if already_running else "running",
        "ok": True,
        "started": True,
        "user": user,
        "mode": "heartbeat_only",
        "runtime_mode": data.get("mode", "shadow"),
        "requested_running": True,
        "thread_alive": False,
        "loop_alive": False,
        "bot_running": True,
        "engine_status": "running",
        "primary_runtime_problem": None,
        "tick_in_progress": False,
        "active_scan_worker": False,
        "scan_cancel_requested": False,
        "bot_started_at": data.get("bot_started_at"),
        "runtime_truth": runtime_truth,
    }


@router.post("/stop")
def bot_stop(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)

    stop_bot(data, reason="user_requested_stop")
    mark_user_bot_requested(user, False)
    save_shadow(data, user)
    cancel_scan_worker(user, reason="user_requested_stop")
    data = load_shadow(user)
    runtime_truth = build_bot_runtime_truth(data, load_settings(user), username=user)

    return {
        "status": "stopped",
        "ok": True,
        "stopped": True,
        "user": user,
        "requested_running": False,
        "loop_alive": False,
        "bot_running": False,
        "engine_status": "stopped",
        "primary_runtime_problem": None,
        "tick_in_progress": False,
        "active_scan_worker": False,
        "scan_cancel_requested": True,
        "bot_stopped_at": data.get("bot_stopped_at"),
        "stop_reason": data.get("stop_reason"),
        "runtime_truth": runtime_truth,
    }


@router.post("/emergency-stop")
def bot_emergency_stop(
    action: str = "stop_new_buys",
    current_user: dict = Depends(require_user),
):
    user = current_username(current_user)
    data = load_shadow(user)

    backup_path = None

    if action == "close_all_shadow":
        backup_path = archive_shadow_state(data, user, reason="emergency-close")

    emergency_stop_bot(data, action=action)
    save_shadow(data, user)
    cancel_scan_worker(user, reason=f"emergency_stop:{action}")
    data = load_shadow(user)

    data["emergency_lock"] = True
    ensure_real_trade_state(data)["emergency_lock"] = True
    lock_real_trading(ensure_real_trade_state(data), reason="emergency_stop")
    data["emergency_lock_reason"] = action
    data["emergency_locked_at"] = __import__("core.storage", fromlist=["now_iso"]).now_iso()

    append_audit(
        data,
        "emergency_stop",
        "critical",
        f"Emergency stop: {action}",
        {
            "action": action,
            "backup_path": backup_path
        },
        user=user
    )

    save_shadow(data, user)

    return {
        "status": "emergency_stopped",
        "user": user,
        "action": action,
        "bot_running": False,
        "bot_stopped_at": data.get("bot_stopped_at"),
        "stop_reason": data.get("stop_reason"),
        "open_positions_count": len(data.get("open_positions", [])),
        "backup_path": backup_path
    }


@router.post("/reset")
def bot_reset(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    previous_data = load_shadow(user)
    backup_path = archive_shadow_state(previous_data, user, reason="reset")

    previous_real_state = ensure_real_trade_state(previous_data).copy()

    data = reset_bot_state()
    data["real_trade"] = previous_real_state

    lock_real_trading(ensure_real_trade_state(data), reason="paper_reset_safety_lock")

    append_audit(
        data,
        "bot_reset",
        "ok",
        "Paper/shadow reset tamamlandı; real trade state korundu ve kilitlendi.",
        {
            "backup_path": backup_path,
            "category": "system",
            "severity": "warning"
        },
        user=user
    )

    save_shadow(data, user)

    return {
        "status": "reset_done",
        "user": user,
        "bot_running": False,
        "open_positions_count": 0,
        "history_count": 0,
        "backup_path": backup_path
    }


@router.get("/backups")
def bot_backups(
    limit: int = 20,
    current_user: dict = Depends(require_owner),
):
    user = current_username(current_user)

    return {
        "status": "ok",
        "user": user,
        "count": len(list_shadow_archives(user, limit=limit)),
        "backups": list_shadow_archives(user, limit=limit)
    }


@router.post("/restore-backup")
def bot_restore_backup(
    backup_id: str,
    current_user: dict = Depends(require_owner),
):
    user = current_username(current_user)
    current_data = load_shadow(user)
    pre_restore_backup = archive_shadow_state(current_data, user, reason="pre-restore")

    try:
        restored = restore_shadow_archive(backup_id, user)
        restored["bot_running"] = False
        restored["engine_status"] = "stopped"
        restored["stop_reason"] = "restore_safety_lock"

        lock_real_trading(ensure_real_trade_state(restored), reason="backup_restore_safety_lock")

        append_audit(
            restored,
            "backup_restore",
            "critical",
            f"Backup restore: {backup_id}",
            {
                "backup_id": backup_id,
                "pre_restore_backup": pre_restore_backup,
                "category": "restore",
                "severity": "critical"
            },
            user=user
        )

        save_shadow(restored, user)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {
        "status": "restored",
        "user": user,
        "backup_id": backup_id,
        "pre_restore_backup": pre_restore_backup,
        "bot_running": restored.get("bot_running", False),
        "open_positions_count": len(restored.get("open_positions", [])),
        "history_count": len(restored.get("history", [])),
        "last_updated_at": restored.get("last_updated_at")
    }


@router.post("/recovery/unlock")
def bot_recovery_unlock(payload: dict | None = None, current_user: dict = Depends(require_owner)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)

    report = {
        "open_positions_count": len(data.get("open_positions", [])),
        "history_count": len(data.get("history", [])),
        "runtime_health": build_runtime_health(data, settings),
        "real_trade_safety": build_real_trade_safety_status(data, settings),
    }

    confirm = bool((payload or {}).get("confirm"))

    if not confirm:
        return {
            "status": "confirmation_required",
            "user": user,
            "locked": bool(data.get("emergency_lock")),
            "risk_report": report
        }

    data["emergency_lock"] = False
    ensure_real_trade_state(data)["emergency_lock"] = False
    data["emergency_unlocked_at"] = __import__("core.storage", fromlist=["now_iso"]).now_iso()
    data["bot_running"] = False
    data["engine_status"] = "stopped"
    data["stop_reason"] = "recovery_unlocked_manual_restart_required"

    append_audit(
        data,
        "emergency_recovery",
        "ok",
        "Emergency lock owner tarafından açıldı; bot manuel restart bekliyor.",
        report,
        user=user
    )

    save_shadow(data, user)

    return {
        "status": "unlocked",
        "user": user,
        "bot_running": False,
        "risk_report": report
    }


@router.get("/health-history")
def bot_health_history(limit: int = 100, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    history = list(data.get("health_history", []) or [])[-limit:]

    return {
        "status": "ok",
        "user": user,
        "count": len(history),
        "history": list(reversed(history))
    }
    

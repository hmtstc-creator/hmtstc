from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from services.autonomous_execution_governor_service import build_autonomous_execution_governor
from services.trade_quality_feedback_service import build_trade_quality_feedback


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        if value is None or value == "":
            return fallback
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def _safe_bool(value: Any, fallback: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
    if value is None:
        return fallback
    return bool(value)


def _policy(settings: dict | None) -> dict:
    settings = settings if isinstance(settings, dict) else {}
    tuning = settings.get("adaptive_tuner") if isinstance(settings.get("adaptive_tuner"), dict) else {}
    execution = settings.get("execution_governor") if isinstance(settings.get("execution_governor"), dict) else {}
    risk = settings.get("risk") if isinstance(settings.get("risk"), dict) else {}
    return {
        "enabled": _safe_bool(tuning.get("enabled"), True),
        "auto_apply": _safe_bool(tuning.get("auto_apply"), False),
        "min_quality_score": max(0.0, min(100.0, _safe_float(tuning.get("min_quality_score"), 62.0))),
        "target_quality_score": max(0.0, min(100.0, _safe_float(tuning.get("target_quality_score"), 72.0))),
        "min_sample_size": max(1, _safe_int(tuning.get("min_sample_size"), 5)),
        "max_order_step_pct": max(1.0, min(30.0, _safe_float(tuning.get("max_order_step_pct"), 10.0))),
        "max_confidence_step": max(1.0, min(25.0, _safe_float(tuning.get("max_confidence_step"), 5.0))),
        "max_single_order_usdt": max(0.0, _safe_float(execution.get("max_single_order_usdt"), 25.0)),
        "min_order_usdt": max(0.0, _safe_float(execution.get("min_order_usdt"), 5.0)),
        "daily_loss_stop_pct": max(0.1, _safe_float(risk.get("daily_loss_stop_pct"), 2.0)),
    }


def _closed_trades(data: dict) -> list[dict]:
    for key in ("closed_trades", "trade_history", "paper_closed_trades", "real_closed_trades"):
        value = data.get(key)
        if isinstance(value, list) and value:
            return [item for item in value if isinstance(item, dict)]
    return []


def _trade_stats(data: dict) -> dict:
    trades = _closed_trades(data)
    sample = len(trades)
    pnl_values = [_safe_float(t.get("pnl_usdt"), _safe_float(t.get("pnl"), 0.0)) for t in trades]
    wins = sum(1 for pnl in pnl_values if pnl > 0)
    losses = sum(1 for pnl in pnl_values if pnl < 0)
    total_pnl = round(sum(pnl_values), 4)
    win_rate = round((wins / sample) * 100, 2) if sample else 0.0
    loss_streak = 0
    for pnl in reversed(pnl_values):
        if pnl < 0:
            loss_streak += 1
        else:
            break
    return {"sample_size": sample, "wins": wins, "losses": losses, "win_rate": win_rate, "total_pnl_usdt": total_pnl, "loss_streak": loss_streak}


def _current_values(settings: dict, execution: dict) -> dict:
    daily = settings.get("daily_operation") if isinstance(settings.get("daily_operation"), dict) else {}
    risk = settings.get("risk") if isinstance(settings.get("risk"), dict) else {}
    exec_policy = settings.get("execution_governor") if isinstance(settings.get("execution_governor"), dict) else {}
    return {
        "min_confidence_for_active": _safe_float(daily.get("min_confidence_for_active"), 55.0),
        "max_single_order_usdt": _safe_float(exec_policy.get("max_single_order_usdt"), _safe_float(execution.get("suggested_order_usdt"), 25.0) or 25.0),
        "daily_loss_stop_pct": _safe_float(risk.get("daily_loss_stop_pct"), 2.0),
    }


def _proposal(key: str, current: float, proposed: float, reason: str, impact: str) -> dict:
    return {
        "key": key,
        "current": round(current, 4),
        "proposed": round(proposed, 4),
        "delta": round(proposed - current, 4),
        "reason": reason,
        "impact": impact,
    }


def build_adaptive_parameter_tuner(
    data: dict | None,
    settings: dict | None = None,
    auth_store: dict | None = None,
    username: str = "default",
) -> dict:
    """Create a safe, read-only tuning recommendation for autonomous operation.

    Rev69 deliberately does not mutate settings. It observes the Rev64 quality feedback,
    Rev68 execution gate, and recent trade statistics, then proposes bounded parameter
    adjustments that the owner can review or a later governance layer can apply.
    """
    data = deepcopy(data or {})
    settings = deepcopy(settings or {})
    policy = _policy(settings)
    quality = build_trade_quality_feedback(data, settings)
    execution = build_autonomous_execution_governor(data, settings, auth_store, username)
    stats = _trade_stats(data)
    current = _current_values(settings, execution)

    quality_score = _safe_float(quality.get("quality_score"), _safe_float(quality.get("overall_quality_score"), 0.0))
    execution_lane = str(execution.get("execution_lane") or "none")
    blockers = list(execution.get("blockers") or []) if isinstance(execution.get("blockers"), list) else []
    proposals: list[dict] = []
    warnings: list[str] = []

    if not policy["enabled"]:
        blockers.append("adaptive_tuner_disabled")

    insufficient_sample = stats["sample_size"] < policy["min_sample_size"]
    if insufficient_sample:
        warnings.append("sample_size_low")

    confidence_step = policy["max_confidence_step"]
    order_step = policy["max_order_step_pct"] / 100.0

    if quality_score and quality_score < policy["min_quality_score"]:
        proposals.append(_proposal(
            "daily_operation.min_confidence_for_active",
            current["min_confidence_for_active"],
            min(95.0, current["min_confidence_for_active"] + confidence_step),
            "Trade quality target altında; daha güçlü sinyal beklenmeli.",
            "İşlem sayısı düşer, düşük kaliteli giriş riski azalır.",
        ))
        proposals.append(_proposal(
            "execution_governor.max_single_order_usdt",
            current["max_single_order_usdt"],
            max(policy["min_order_usdt"], current["max_single_order_usdt"] * (1.0 - order_step)),
            "Kalite düşük; tek işlem notional değeri azaltılmalı.",
            "Zarar serilerinde sermaye korunur.",
        ))
    elif quality_score >= policy["target_quality_score"] and stats["win_rate"] >= 55.0 and stats["loss_streak"] <= 1 and not insufficient_sample:
        proposals.append(_proposal(
            "execution_governor.max_single_order_usdt",
            current["max_single_order_usdt"],
            min(policy["max_single_order_usdt"] * 1.5 if policy["max_single_order_usdt"] else current["max_single_order_usdt"] * 1.1, current["max_single_order_usdt"] * (1.0 + order_step)),
            "Kalite ve win-rate yeterli; kontrollü mikro büyüme denenebilir.",
            "Kazanan rejimde pozisyon etkisi sınırlı artar.",
        ))
        proposals.append(_proposal(
            "daily_operation.min_confidence_for_active",
            current["min_confidence_for_active"],
            max(35.0, current["min_confidence_for_active"] - min(confidence_step, 3.0)),
            "Kalite yüksek; fırsat kaçırmamak için eşik küçük adımla gevşetilebilir.",
            "İşlem fırsatı artar ama mikro adım sınırı korunur.",
        ))
    else:
        proposals.append(_proposal(
            "daily_operation.min_confidence_for_active",
            current["min_confidence_for_active"],
            current["min_confidence_for_active"],
            "Veri karışık; mevcut güven eşiği korunmalı.",
            "Sistem davranışı stabil kalır.",
        ))

    if stats["loss_streak"] >= 3:
        proposals.append(_proposal(
            "risk.daily_loss_stop_pct",
            current["daily_loss_stop_pct"],
            max(0.5, current["daily_loss_stop_pct"] * 0.75),
            "Ardışık zarar serisi var; günlük zarar limiti sıkılaştırılmalı.",
            "Bot daha erken koruma moduna geçer.",
        ))
        warnings.append("loss_streak_guard")

    executable = bool(execution.get("can_execute"))
    apply_mode = "manual_review"
    if blockers:
        apply_mode = "blocked"
    elif insufficient_sample:
        apply_mode = "observe_more"
    elif policy["auto_apply"]:
        apply_mode = "auto_apply_ready"

    status = "ok" if apply_mode in {"manual_review", "auto_apply_ready", "observe_more"} else "blocked"
    decision_text = "Parametreler korunuyor; veri izlenmeye devam." if not proposals else "Parametre önerileri hazır; otomatik uygulama kapalı." 
    if apply_mode == "auto_apply_ready":
        decision_text = "Parametre önerileri otomatik uygulama için hazır; yine de execution ayrı guard ister."
    elif apply_mode == "observe_more":
        decision_text = "Örneklem düşük; sistem daha fazla işlem kalitesi verisi beklemeli."
    elif apply_mode == "blocked":
        decision_text = "Tuning kararı bloklandı; execution/risk guard önce çözülmeli."

    return {
        "status": status,
        "revision": 69,
        "engine": "adaptive_parameter_tuner",
        "generated_at": now_iso(),
        "read_only": True,
        "auto_apply": False,
        "apply_mode": apply_mode,
        "execution_lane": execution_lane,
        "can_execute": executable,
        "quality_score": round(quality_score, 2),
        "trade_stats": stats,
        "proposal_count": len(proposals),
        "proposals": proposals[:6],
        "blockers": sorted(set(str(x) for x in blockers)),
        "warnings": sorted(set(str(x) for x in warnings)),
        "decision_text": decision_text,
        "source": {
            "trade_quality_revision": quality.get("revision"),
            "execution_governor_revision": execution.get("revision"),
        },
        "policy": policy,
    }


def build_summary_adaptive_parameter_tuner(data: dict | None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_adaptive_parameter_tuner(data, settings, auth_store, username)
    return {
        "status": payload.get("status"),
        "revision": 69,
        "read_only": True,
        "apply_mode": payload.get("apply_mode"),
        "proposal_count": payload.get("proposal_count"),
        "quality_score": payload.get("quality_score"),
        "decision_text": payload.get("decision_text"),
        "warnings": payload.get("warnings", []),
        "blockers": payload.get("blockers", []),
        "updated_at": payload.get("generated_at"),
    }


def build_adaptive_parameter_tuner_quality(data: dict | None = None, settings: dict | None = None, auth_store: dict | None = None, username: str = "default") -> dict:
    payload = build_adaptive_parameter_tuner(data, settings, auth_store, username)
    proposals = payload.get("proposals") if isinstance(payload.get("proposals"), list) else []
    checks = {
        "revision_69": payload.get("revision") == 69,
        "read_only": payload.get("read_only") is True,
        "no_direct_mutation": payload.get("auto_apply") is False,
        "source_chain_linked": (payload.get("source") or {}).get("trade_quality_revision") == 64 and (payload.get("source") or {}).get("execution_governor_revision") == 68,
        "proposal_contract": all({"key", "current", "proposed", "delta", "reason", "impact"}.issubset(item.keys()) for item in proposals if isinstance(item, dict)),
        "bounded_proposal_count": 0 <= len(proposals) <= 6,
        "no_secret_leak": "secret" not in str(payload).lower() and "api_key" not in str(payload).lower(),
    }
    return {
        "status": "ok" if all(checks.values()) else "review",
        "revision": 69,
        "engine": "adaptive_parameter_tuner_quality",
        "generated_at": now_iso(),
        "checks": checks,
        "apply_mode": payload.get("apply_mode"),
        "proposal_count": payload.get("proposal_count"),
    }

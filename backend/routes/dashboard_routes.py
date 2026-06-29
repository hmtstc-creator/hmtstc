import os
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends

from core.config import DEFAULT_USER
from core.auth import require_user
from core.storage import load_shadow, load_settings, save_shadow, sync_settings_state
from services.performance_service import build_dashboard_summary, filter_performance_points
from services.analysis_service import build_filter_rejection_counts, build_scan_settings_snapshot, build_unique_filter_rejection_counts
from services.bot_runtime_truth_service import build_bot_runtime_truth
from services.risk_service import build_risk_snapshot
from services.real_trade_safety_service import build_real_trade_safety_status, build_runtime_health
from services.rule_engine import build_persistent_paper_lab_status, list_rules


router = APIRouter(
    prefix="/api",
    tags=["dashboard"]
)



def build_cached_last_scan_payload(user: str, data: dict, settings: dict | None = None) -> dict:
    last_scan = data.get("last_scan") if isinstance(data.get("last_scan"), dict) else {}
    scan_rows = last_scan.get("scan_rows") if isinstance(last_scan.get("scan_rows"), list) else []
    candidates = last_scan.get("candidates") if isinstance(last_scan.get("candidates"), list) else []
    diagnostics = last_scan.get("scan_diagnostics") if isinstance(last_scan.get("scan_diagnostics"), dict) else {}
    filter_counts = last_scan.get("filter_rejection_counts")
    if not isinstance(filter_counts, dict):
        filter_counts = diagnostics.get("filter_rejection_counts") if isinstance(diagnostics.get("filter_rejection_counts"), dict) else {}
    if not filter_counts:
        filter_counts = build_unique_filter_rejection_counts(last_scan.get("scan_rows", []), last_scan.get("universe_rejection_breakdown_unique", {}))
    cumulative_filter_counts = last_scan.get("filter_rejection_counts_cumulative")
    if not isinstance(cumulative_filter_counts, dict):
        cumulative_filter_counts = diagnostics.get("filter_rejection_counts_cumulative") if isinstance(diagnostics.get("filter_rejection_counts_cumulative"), dict) else {}
    if not cumulative_filter_counts:
        cumulative_filter_counts = build_filter_rejection_counts(last_scan.get("universe_rejection_breakdown", {}), last_scan.get("rejection_breakdown", {}))
    volume_diag = last_scan.get("volume_rejection_diagnostics")
    if not isinstance(volume_diag, dict):
        volume_diag = diagnostics.get("volume_rejection_diagnostics") if isinstance(diagnostics.get("volume_rejection_diagnostics"), dict) else {}
    current_settings_snapshot = build_scan_settings_snapshot(settings or {}) if isinstance(settings, dict) else {}
    scan_settings_snapshot = last_scan.get("settings_snapshot") if isinstance(last_scan.get("settings_snapshot"), dict) else {}
    coin_filter_settings_used = last_scan.get("coin_filter_settings_used")
    if not isinstance(coin_filter_settings_used, dict):
        coin_filter_settings_used = diagnostics.get("coin_filter_settings_used") if isinstance(diagnostics.get("coin_filter_settings_used"), dict) else scan_settings_snapshot.get("coin_filter_effective", {})
    settings_changed_since_scan = bool(
        scan_settings_snapshot
        and current_settings_snapshot.get("coin_filter") != scan_settings_snapshot.get("coin_filter")
    )
    liquidity_diag = last_scan.get("liquidity_rejection_diagnostics")
    if not isinstance(liquidity_diag, dict):
        liquidity_diag = diagnostics.get("liquidity_rejection_diagnostics") if isinstance(diagnostics.get("liquidity_rejection_diagnostics"), dict) else {}
    return {
        "status": last_scan.get("status") or ("ok" if last_scan else "empty"),
        "user": user,
        "mode": last_scan.get("mode") or data.get("mode", "shadow"),
        "live": bool(last_scan.get("live")),
        "time": last_scan.get("time") or data.get("last_scan_time"),
        "scan_time": last_scan.get("time") or data.get("last_scan_time"),
        "last_scan_at": last_scan.get("time") or data.get("last_scan_time"),
        "scan_id": last_scan.get("scan_id"),
        "source": last_scan.get("source"),
        "test_scan": bool(last_scan.get("test_scan", False)),
        "scanned": last_scan.get("scanned", 0),
        "eligible_universe_count": last_scan.get("eligible_universe_count", 0),
        "universe_total_seen": last_scan.get("universe_total_seen", last_scan.get("scanned", 0)),
        "universe_rejected_count": last_scan.get("universe_rejected_count", 0),
        "universe_rejection_breakdown": last_scan.get("universe_rejection_breakdown", {}),
        "candidates_count": last_scan.get("candidates_count", len(candidates)),
        "rejected_count": last_scan.get("rejected_count", 0),
        "top_rejection_reason": last_scan.get("top_rejection_reason"),
        "rejection_breakdown": last_scan.get("rejection_breakdown", {}),
        "filter_rejection_counts": filter_counts,
        "filter_rejection_counts_cumulative": cumulative_filter_counts,
        "settings_snapshot": scan_settings_snapshot,
        "current_settings_snapshot": current_settings_snapshot,
        "coin_filter_settings_used": coin_filter_settings_used,
        "settings_used": last_scan.get("settings_used", coin_filter_settings_used),
        "settings_changed_since_scan": settings_changed_since_scan,
        "volume_rejection_diagnostics": volume_diag,
        "liquidity_rejection_diagnostics": liquidity_diag,
        "scan_diagnostics": {**diagnostics, "filter_rejection_counts": filter_counts, "filter_rejection_counts_cumulative": cumulative_filter_counts, "volume_rejection_diagnostics": volume_diag, "liquidity_rejection_diagnostics": liquidity_diag, "coin_filter_settings_used": coin_filter_settings_used},
        "pipeline": last_scan.get("pipeline", {}) if isinstance(last_scan.get("pipeline"), dict) else {},
        "funnel_summary": last_scan.get("funnel_summary", {}) if isinstance(last_scan.get("funnel_summary"), dict) else {},
        "candidates": candidates,
        "scan_rows": scan_rows,
        "candidate_handoff": last_scan.get("candidate_handoff", {}) if isinstance(last_scan.get("candidate_handoff"), dict) else {},
        "strategy_runtime": last_scan.get("strategy_runtime", {}) if isinstance(last_scan.get("strategy_runtime"), dict) else {},
        "karabasan_runtime": last_scan.get("karabasan_runtime", {}) if isinstance(last_scan.get("karabasan_runtime"), dict) else {},
        "error": last_scan.get("error"),
        "cached_read": True,
    }

def current_username(current_user: dict) -> str:
    username = str(current_user.get("username") or "").strip()
    return username or DEFAULT_USER


def _git_subject_from_object(repo: Path, sha: str) -> str:
    obj = repo / ".git" / "objects" / sha[:2] / sha[2:]
    if not obj.exists():
        return ""
    try:
        import zlib
        raw = zlib.decompress(obj.read_bytes())
        _, body = raw.split(b"\x00", 1)
        text = body.decode("utf-8", errors="replace")
        return text.split("\n\n", 1)[1].splitlines()[0].strip()
    except Exception:
        return ""


def build_info() -> dict:
    env_label = str(os.getenv("HMTSTC_BUILD_LABEL") or "").strip()
    env_commit = str(os.getenv("HMTSTC_BUILD_COMMIT") or "").strip()
    if env_label:
        return {"status": "ok", "commit": env_commit, "commit_short": env_commit[:12], "label": env_label}

    repo = Path(__file__).resolve().parents[2]
    sha = ""
    subject = ""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "log", "-1", "--pretty=%H%x00%s"],
            capture_output=True,
            text=True,
            timeout=1.5,
            check=False,
        )
        if result.returncode == 0 and result.stdout:
            sha, subject = (result.stdout.strip().split("\x00", 1) + [""])[:2]
    except Exception:
        sha = ""
        subject = ""

    if not sha:
        try:
            head = (repo / ".git" / "HEAD").read_text(encoding="utf-8").strip()
            if head.startswith("ref:"):
                ref = head.split(" ", 1)[1].strip()
                sha = (repo / ".git" / ref).read_text(encoding="utf-8").strip()
            else:
                sha = head
            subject = _git_subject_from_object(repo, sha)
        except Exception:
            sha = ""
            subject = ""

    label = subject or (sha[:12] if sha else "local")
    return {"status": "ok", "commit": sha, "commit_short": sha[:12], "label": label}


def build_bot_status_snapshot(user: str, data: dict, settings: dict, dashboard_summary: dict) -> dict:
    risk = settings.get("risk", {})
    bot = settings.get("bot", {})
    last_scan = data.get("last_scan") if isinstance(data.get("last_scan"), dict) else {}
    last_scan_time = data.get("last_scan_time") or last_scan.get("time")
    runtime_truth = build_bot_runtime_truth(data, settings, username=user)
    scan_error = last_scan.get("error")
    backend_api_status = "online" if runtime_truth.get("bot_running") and not scan_error else ("degraded" if scan_error else "online")
    return {
        "status": "ok",
        "user": user,
        "requested_running": runtime_truth.get("requested_running"),
        "thread_alive": runtime_truth.get("thread_alive"),
        "loop_alive": runtime_truth.get("loop_alive"),
        "bot_running": runtime_truth.get("bot_running"),
        "mode": data.get("mode", "shadow"),
        "engine_status": runtime_truth.get("engine_status"),
        "primary_runtime_problem": runtime_truth.get("primary_runtime_problem"),
        "backend_api_status": backend_api_status,
        "bot_started_at": data.get("bot_started_at"),
        "bot_stopped_at": data.get("bot_stopped_at"),
        "last_tick": data.get("last_tick"),
        "last_updated_at": data.get("last_updated_at"),
        "last_calculation_at": data.get("last_calculation_at"),
        "stop_reason": data.get("stop_reason"),
        "runtime_seconds": dashboard_summary.get("runtime_seconds"),
        "runtime_text": dashboard_summary.get("runtime_text"),
        "open_positions_count": len(data.get("open_positions", [])),
        "max_open_positions": bot.get("max_open_positions", 5),
        "usdt_per_position": bot.get("usdt_per_position", 200),
        "daily_loss_limit": risk.get("daily_loss_limit", "30 USDT"),
        "last_scan_live": bool(last_scan.get("live")),
        "last_scan_time": last_scan_time,
        "last_scan_error": scan_error,
        "runtime_health": build_runtime_health(data, settings),
        "real_trade_safety": build_real_trade_safety_status(data, settings),
    }


@router.get("/build")
def build_metadata():
    return build_info()


@router.get("/dashboard")
def dashboard(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    if sync_settings_state(data, settings):
        save_shadow(data, user)

    summary = build_dashboard_summary(data, settings)
    summary["risk"] = build_risk_snapshot(data, settings)
    summary["user"] = user

    return summary


@router.get("/dashboard/bundle")
def dashboard_bundle(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)
    settings = load_settings(user)
    if sync_settings_state(data, settings):
        save_shadow(data, user)

    summary = build_dashboard_summary(data, settings)
    summary["risk"] = build_risk_snapshot(data, settings)
    summary["user"] = user

    logs_data = data.get("logs", []) or []
    logs_payload = {
        "status": "ok",
        "user": user,
        "count": len(logs_data[-100:]),
        "bot_running": data.get("bot_running", False),
        "engine_status": data.get("engine_status", "unknown"),
        "last_tick": data.get("last_tick"),
        "logs": logs_data[-100:],
    }

    payload = {
        "status": "ok",
        "user": user,
        "build": build_info(),
        "dashboard": summary,
        "positions": data.get("open_positions", []),
        "history": data.get("history", []),
        "logs": logs_payload,
        "settings": {**settings, "user": user},
        "botStatus": build_bot_status_snapshot(user, data, settings, summary),
        "botScan": build_cached_last_scan_payload(user, data, settings),
        "rules": list_rules(user, include_store_status=False),
        "paper_lab_status": build_persistent_paper_lab_status(user),
    }

    if str(current_user.get("role") or "").lower() == "owner":
        from routes.users_routes import public_user
        from core.auth import read_auth_store
        store = read_auth_store()
        users = store.setdefault("users", {})
        payload["users"] = {"status": "ok", "users": [public_user(username, record) for username, record in users.items()]}

    return payload


@router.get("/positions")
def positions(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)

    return data.get("open_positions", [])


@router.get("/history")
def history(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    data = load_shadow(user)

    return data.get("history", [])


@router.get("/performance")
def performance(
    start: str | None = None,
    end: str | None = None,
    current_user: dict = Depends(require_user),
):
    user = current_username(current_user)
    data = load_shadow(user)

    return filter_performance_points(
        data,
        start=start,
        end=end
    )


@router.get("/logs")
def logs(
    level: str = "all",
    event: str = "all",
    query: str = "",
    limit: int = 100,
    current_user: dict = Depends(require_user),
):
    user = current_username(current_user)
    data = load_shadow(user)
    logs_data = data.get("logs", [])

    query_clean = str(query or "").lower()
    level_clean = str(level or "all").lower()
    event_clean = str(event or "all").lower()

    filtered = []

    for item in logs_data:
        message = str(item.get("message") or "").lower()
        item_level = str(item.get("level") or "").lower()
        item_event = str(item.get("event") or "").lower()

        if level_clean != "all" and item_level != level_clean:
            continue

        if event_clean != "all" and item_event != event_clean:
            continue

        if query_clean and query_clean not in message:
            continue

        filtered.append(item)

    filtered = filtered[-max(min(limit, 300), 10):]

    return {
        "status": "ok",
        "user": user,
        "count": len(filtered),
        "bot_running": data.get("bot_running", False),
        "engine_status": data.get("engine_status", "unknown"),
        "bot_started_at": data.get("bot_started_at"),
        "bot_stopped_at": data.get("bot_stopped_at"),
        "last_tick": data.get("last_tick"),
        "last_updated_at": data.get("last_updated_at"),
        "last_calculation_at": data.get("last_calculation_at"),
        "stop_reason": data.get("stop_reason"),
        "logs": filtered
    }

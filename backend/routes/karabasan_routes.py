from fastapi import APIRouter, Depends
from core.auth import require_user
from core.config import DEFAULT_USER
from core.storage import load_shadow, load_settings, save_settings
from services.karabasan_settings_service import build_karabasan_settings_contract
from services.karabasan_timeframe_service import build_karabasan_timeframe_analysis
from services.karabasan_target_profit_fit_service import build_karabasan_target_profit_fit
from services.karabasan_hard_block_service import build_karabasan_hard_block_report
from services.karabasan_final_decision_service import build_karabasan_final_decision, karabasan_decision_view
from services.karabasan_admin_page_service import build_karabasan_admin_page
from services.karabasan_subcriteria_service import build_karabasan_subcriteria
from services.karabasan_admin_settings_panel_service import build_karabasan_admin_settings_panel
from services.karabasan_live_gate_service import evaluate_karabasan_live_gate
from services.karabasan_paper_lab_service import build_karabasan_paper_lab_comparison
from services.karabasan_history_service import build_karabasan_decision_history
from services.karabasan_score_service import (
    build_karabasan_score,
    build_karabasan_summary,
    default_karabasan_settings,
)

router = APIRouter(prefix="/api/karabasan", tags=["karabasan"])


def current_username(current_user: dict) -> str:
    return str(current_user.get("username") or DEFAULT_USER).strip() or DEFAULT_USER


@router.get("/summary")
def karabasan_summary(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_karabasan_summary(load_shadow(user), load_settings(user))


@router.get("/score")
def karabasan_score(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_karabasan_score(load_shadow(user), load_settings(user))


@router.get("/score-breakdown")
def karabasan_score_breakdown(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    result = build_karabasan_score(load_shadow(user), load_settings(user))
    return {"score": result["karabasan_score"], "breakdown": result["breakdown_table"], "formula": result["admin_formula"]}


@router.get("/admin-analysis")
def karabasan_admin_analysis(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    result = build_karabasan_score(load_shadow(user), load_settings(user))
    result["admin_page"] = {
        "title": "Karabasan Analiz Merkezi",
        "purpose": "Hangi kriterin işlem iznini ne kadar etkilediğini admin görür.",
        "sections": ["Genel karar", "Skor kırılımı", "Alt kriterler", "Hard block", "Karar açıklaması"],
    }
    return result


@router.post("/evaluate-signal")
def karabasan_evaluate_signal(payload: dict, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_karabasan_score(load_shadow(user), load_settings(user), payload or {})


@router.get("/settings")
def karabasan_settings(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    settings = load_settings(user)
    return settings.get("karabasan") or default_karabasan_settings()


@router.post("/settings")
def karabasan_save_settings(payload: dict, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    settings = load_settings(user)
    base = default_karabasan_settings()
    incoming = payload or {}
    base.update(incoming)
    settings["karabasan"] = base
    save_settings(settings, user)
    return {"status": "ok", "karabasan": base}


@router.get("/history")
def karabasan_history(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    runtime = load_shadow(user)
    history = runtime.get("karabasan_history") or []
    return {"history": history[-100:], "count": len(history)}


@router.get("/settings-contract")
def karabasan_settings_contract(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_karabasan_settings_contract(load_settings(user))


@router.get("/timeframe-analysis")
def karabasan_timeframe_analysis(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_karabasan_timeframe_analysis(load_shadow(user), load_settings(user))


@router.get("/target-profit-fit")
def karabasan_target_profit_fit(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_karabasan_target_profit_fit(load_shadow(user), load_settings(user))


@router.get("/hard-blocks")
def karabasan_hard_blocks(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_karabasan_hard_block_report(load_shadow(user), load_settings(user))


@router.get("/final-decision")
def karabasan_final_decision(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    decision = build_karabasan_final_decision(load_shadow(user), load_settings(user))
    return karabasan_decision_view(decision, owner=str(current_user.get("role") or "").lower() in {"owner", "admin"})


@router.post("/final-decision")
def karabasan_final_decision_for_strategy(payload: dict, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    decision = build_karabasan_final_decision(load_shadow(user), load_settings(user), payload or {})
    return karabasan_decision_view(decision, owner=str(current_user.get("role") or "").lower() in {"owner", "admin"})


@router.get("/admin-page")
def karabasan_admin_page(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_karabasan_admin_page(load_shadow(user), load_settings(user))


@router.get("/subcriteria")
def karabasan_subcriteria(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_karabasan_subcriteria(load_shadow(user), load_settings(user))


@router.get("/admin-settings-panel")
def karabasan_admin_settings_panel(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_karabasan_admin_settings_panel(load_settings(user))


@router.post("/live-gate")
def karabasan_live_gate(payload: dict | None = None, current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return evaluate_karabasan_live_gate(load_shadow(user), load_settings(user), payload or {})


@router.get("/paper-lab-comparison")
def karabasan_paper_lab_comparison(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_karabasan_paper_lab_comparison(load_shadow(user), load_settings(user))


@router.get("/decision-history")
def karabasan_decision_history(current_user: dict = Depends(require_user)):
    user = current_username(current_user)
    return build_karabasan_decision_history(load_shadow(user), load_settings(user))

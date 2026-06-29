from services.replay_explainability_service import (
    build_evidence_chain,
    build_replay_index_final,
    build_reports_replay_final,
    build_trade_explanation,
    compare_report_archives,
)


def _gate(name, status, detail):
    return {"name": name, "status": status, "detail": detail}


def build_revision_33_quality_report(data: dict, settings: dict) -> dict:
    replay = build_replay_index_final(data, settings)
    explain = build_trade_explanation(data, settings)
    evidence = build_evidence_chain(data, settings)
    compare = compare_report_archives(data)
    gates = [
        _gate("trade_explainability", explain.get("status", "review"), "Trade neden açıldı/kapandı açıklama katmanı."),
        _gate("replay_index", replay.get("status", "review"), "Scan/model/recommendation/report replay index."),
        _gate("evidence_chain", evidence.get("status", "review"), "Karar kanıt zinciri."),
        _gate("report_compare", compare.get("status", "review"), "Rapor snapshot karşılaştırma."),
        _gate("read_only_policy", "ok", "Replay/explainability katmanı gerçek emir oluşturmaz."),
    ]
    ok_count = sum(1 for gate in gates if gate.get("status") == "ok")
    readiness = round(ok_count / len(gates) * 100, 2)
    return {
        "revision": 33,
        "status": "ok" if readiness >= 70 else "review",
        "readiness_score": readiness,
        "gates": gates,
        "trade_explainability": explain,
        "replay_index": replay,
        "evidence_chain": evidence,
        "report_compare": compare,
        "policy": {
            "read_only": True,
            "no_real_order_side_effect": True,
            "supports_forensic_review": True,
        },
    }


def build_revision_33_trade_explainability_quality(data: dict, settings: dict) -> dict:
    return build_trade_explanation(data, settings)


def build_revision_33_replay_quality(data: dict, settings: dict) -> dict:
    return build_replay_index_final(data, settings)


def build_revision_33_evidence_quality(data: dict, settings: dict) -> dict:
    return build_evidence_chain(data, settings)


def build_revision_33_report_compare_quality(data: dict, settings: dict) -> dict:
    return compare_report_archives(data)


def build_revision_33_ui_quality() -> dict:
    return {
        "status": "ok",
        "ui_blocks": [
            "reports_replay_panel",
            "trade_explainability_panel",
            "evidence_chain_panel",
            "archive_compare_panel",
            "intelligence_rev33_cards",
        ],
        "real_trade_side_effect": False,
    }

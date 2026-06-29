from copy import deepcopy

from services.karabasan_hard_block_service import build_karabasan_hard_blocks
from services.karabasan_score_service import build_karabasan_score


def _runtime_with_candidate_market(runtime: dict, strategy_output: dict) -> dict:
    prepared = deepcopy(runtime)
    candidate = strategy_output.get("candidate") if isinstance(strategy_output.get("candidate"), dict) else strategy_output
    signal = strategy_output.get("strategy_output") if isinstance(strategy_output.get("strategy_output"), dict) else strategy_output
    spread = candidate.get("spread_percent")
    quality = float(candidate.get("quality_score") or candidate.get("score") or signal.get("confidence") or 60)
    spread_score = max(0.0, min(100.0, 100.0 - float(spread or 0) * 220))
    prepared["karabasan_market"] = {
        **(prepared.get("karabasan_market") or {}),
        "liquidity": {
            "spread_score": spread_score,
            "order_book_depth": quality,
            "volume_score": quality,
            "slippage_risk": max(0.0, 100.0 - spread_score),
            "order_size_fit": 85,
        },
        "strategy_quality": {
            "general_win_rate": signal.get("confidence", quality),
            "coin_success": quality,
            "timeframe_success": quality,
            "filter_pass_quality": quality,
        },
        "coin": {
            "trend": quality,
            "momentum": quality,
            "volume": quality,
            "liquidity": spread_score,
        },
    }
    return prepared


def build_karabasan_final_decision(runtime, settings, signal=None):
    strategy_output = signal if isinstance(signal, dict) else {}
    prepared_runtime = _runtime_with_candidate_market(runtime, strategy_output)
    score_result = build_karabasan_score(prepared_runtime, settings, strategy_output)
    hard_block = build_karabasan_hard_blocks(runtime, settings, strategy_output)
    blocks = list(dict.fromkeys(hard_block["blocks"] + [str(item) for item in score_result.get("blocking_reasons", [])]))
    warnings = list(hard_block["warnings"])
    if score_result["karabasan_score"] < score_result["minimum_score"]:
        warnings.append("karabasan_score_below_minimum")
    approved = not blocks and score_result["decision"] == "allow"
    explanation = "İşlem izni verildi." if approved else (blocks[0] if blocks else "Karabasan skoru işlem izni vermedi.")
    return {
        "contract": "karabasan_final_gate_v1",
        "approved": approved,
        "score": score_result["karabasan_score"],
        "blocks": blocks,
        "warnings": list(dict.fromkeys(warnings)),
        "symbol": hard_block.get("symbol") or score_result.get("symbol"),
        "explanation": explanation,
        "user_summary": {
            "approved": approved,
            "score": score_result["karabasan_score"],
            "explanation": explanation,
        },
        "owner_details": {
            "minimum_score": score_result["minimum_score"],
            "decision": score_result["decision"],
            "confidence": score_result["confidence"],
            "score_breakdown": score_result["score_breakdown"],
            "main_reasons": score_result["main_reasons"],
            "risk_check": hard_block.get("risk_check"),
        },
    }


def karabasan_decision_view(decision: dict, owner: bool = False) -> dict:
    if owner:
        return decision
    return {
        "contract": decision.get("contract"),
        **(decision.get("user_summary") or {}),
        "blocks": decision.get("blocks", [])[:1],
        "warnings": decision.get("warnings", [])[:2],
    }

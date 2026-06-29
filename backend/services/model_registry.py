from copy import deepcopy


BASE_WALLET_USDT = 1000.0

FILTERS = [
    {
        "id": "FILTER_A_LIQUID_TREND",
        "name": "Liquid Trend",
        "description": "Likiditesi yüksek, spread/noise düşük ve trend kalitesi olan coinleri seçer.",
        "min_score": 65,
        "weights": {
            "liquidity": 0.30,
            "volatility": 0.15,
            "momentum": 0.15,
            "trend": 0.25,
            "spread": 0.10,
            "data_quality": 0.05,
        },
    },
    {
        "id": "FILTER_B_MOMENTUM_VOL",
        "name": "Momentum Volume",
        "description": "Hacim artışı, momentum ve hareket gücü yüksek coinleri seçer.",
        "min_score": 68,
        "weights": {
            "liquidity": 0.20,
            "volatility": 0.20,
            "momentum": 0.30,
            "trend": 0.10,
            "spread": 0.10,
            "data_quality": 0.10,
        },
    },
    {
        "id": "FILTER_C_STABLE_QUALITY",
        "name": "Stable Quality",
        "description": "Daha sakin, kaliteli ve yüksek likiditeli coinleri seçer.",
        "min_score": 62,
        "weights": {
            "liquidity": 0.35,
            "volatility": 0.10,
            "momentum": 0.10,
            "trend": 0.25,
            "spread": 0.15,
            "data_quality": 0.05,
        },
    },
]

STRATEGIES = [
    {
        "id": "STRATEGY_TREND_1",
        "name": "Trend Following",
        "description": "EMA uyumu ve kontrollü RSI ile trend devamı arar.",
    },
    {
        "id": "STRATEGY_PULLBACK_1",
        "name": "Pullback",
        "description": "Trend içinde kontrollü geri çekilmeden dönüş arar.",
    },
    {
        "id": "STRATEGY_BREAKOUT_1",
        "name": "Breakout",
        "description": "Hacim destekli kırılım ve momentum devamı arar.",
    },
    {
        "id": "STRATEGY_MOMENTUM_1",
        "name": "Momentum Continuation",
        "description": "Güçlü hareketin devamını yakalamaya çalışır.",
    },
]

# Risk profile varyantları Paper Lab kombinasyon mimarisinden kaldırıldı.
# Paper Lab artık tek model = filtre + strateji kombinasyonu olarak çalışır.
DEFAULT_MODEL_RUNTIME = {
    "wallet_start": BASE_WALLET_USDT,
    "slot_size": 200.0,
    "max_slots": 5,
    "max_open_positions": 5,
    "take_profit_percent": 1.5,
    "stop_loss_percent": 2.0,
}

COMPATIBILITY = {
    "FILTER_A_LIQUID_TREND": {
        "STRATEGY_TREND_1": "primary",
        "STRATEGY_PULLBACK_1": "primary",
        "STRATEGY_BREAKOUT_1": "secondary",
        "STRATEGY_MOMENTUM_1": "primary",
    },
    "FILTER_B_MOMENTUM_VOL": {
        "STRATEGY_TREND_1": "secondary",
        "STRATEGY_PULLBACK_1": "disabled",
        "STRATEGY_BREAKOUT_1": "primary",
        "STRATEGY_MOMENTUM_1": "primary",
    },
    "FILTER_C_STABLE_QUALITY": {
        "STRATEGY_TREND_1": "primary",
        "STRATEGY_PULLBACK_1": "primary",
        "STRATEGY_BREAKOUT_1": "disabled",
        "STRATEGY_MOMENTUM_1": "disabled",
    },
}


def _registry_by_id(items):
    return {item["id"]: deepcopy(item) for item in items}


def get_filter(filter_id: str) -> dict | None:
    return _registry_by_id(FILTERS).get(filter_id)


def get_strategy(strategy_id: str) -> dict | None:
    return _registry_by_id(STRATEGIES).get(strategy_id)


def make_model_id(filter_id: str, strategy_id: str, legacy_profile_id: str | None = None) -> str:
    # Eski üç parçalı çağrılar bozulmasın diye üçüncü parametre opsiyonel tutulur;
    # model kimliği artık sadece filter + strategy üzerinden üretilir.
    return f"{filter_id}__{strategy_id}"


def is_compatible(filter_id: str, strategy_id: str, include_secondary: bool = True) -> bool:
    level = COMPATIBILITY.get(filter_id, {}).get(strategy_id, "disabled")
    if level == "primary":
        return True
    return bool(include_secondary and level == "secondary")


def build_model_registry(include_secondary: bool = True) -> dict:
    models = []

    for filter_item in FILTERS:
        for strategy_item in STRATEGIES:
            level = COMPATIBILITY.get(filter_item["id"], {}).get(strategy_item["id"], "disabled")
            if level == "disabled":
                continue
            if level == "secondary" and not include_secondary:
                continue

            model_id = make_model_id(filter_item["id"], strategy_item["id"])
            models.append({
                "model_id": model_id,
                "filter_id": filter_item["id"],
                "filter_name": filter_item["name"],
                "strategy_id": strategy_item["id"],
                "strategy_name": strategy_item["name"],
                "compatibility": level,
                **DEFAULT_MODEL_RUNTIME,
                "status": "active",
            })

    return {
        "filters": deepcopy(FILTERS),
        "strategies": deepcopy(STRATEGIES),
        "compatibility": deepcopy(COMPATIBILITY),
        "models": models,
        "count": len(models),
    }


def get_default_real_model_id() -> str:
    return make_model_id(
        "FILTER_A_LIQUID_TREND",
        "STRATEGY_TREND_1",
    )

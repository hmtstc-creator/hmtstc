# Package 10.21.5 Revize 4 — Runtime Datetime + CoinFilter Dashboard Safety

This package fixes the live dashboard/status 500 caused by timezone-naive vs timezone-aware datetime subtraction, aligns CoinFilter low-liquidity rejection with the user-defined minimum USDT quote volume, adds per-filter rejection counters beside user-editable CoinFilter inputs, and restricts the center live network to passed CoinFilter candidates only.

## Files

- backend/services/performance_service.py
- backend/services/coin_quality_service.py
- backend/services/analysis_service.py
- frontend/js/pages/coinFilter.js
- frontend/js/pages/dashboard.js
- frontend/js/components/liveTradeNetwork.js
- scripts/level1_40_37_dashboard_live_trade_network_audit.py
- scripts/level1_40_38_runtime_datetime_coinfilter_dashboard_audit.py

## Quality gates

- Runtime datetime mixed timezone probe: OK
- Dashboard summary 500 guard: OK
- Min quote volume 1 does not trigger low_liquidity: OK
- CoinFilter row rejection counter: OK
- Dashboard network passed-only source: OK
- Backend import: OK
- JS syntax checks: OK


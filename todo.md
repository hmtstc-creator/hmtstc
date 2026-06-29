# HMTSTC TODO ve Kurulum Kılavuzu
## Spot Money Pilot İçin Adım Adım Uygulama Planı

**Amaç:** Bu dosya, HMTSTC web sitesinin ve backend sisteminin sıfırdan kurulması, geliştirilmesi, test edilmesi, yayına alınması ve canlı spot pilotun başlatılması için izlenecek adım adım talimatları verir.

**Kural:** Adımlar birbirine karıştırılmadan sırayla yapılmalıdır. Bir adımın kabul kriteri sağlanmadan sonraki adıma geçilmez.

---

# 0. Dosya ve Referans Yapısı

Projeye eklenecek ana dokümanlar:

```text
README.md   → Ürünün ne olduğunu ve mimariyi anlatır.
todo.md     → Kurulum, geliştirme, test ve deploy adımlarını anlatır.
```

Kod geliştirici veya yapay zekâ asistanı işe başlamadan önce bu iki dosyayı okumalıdır.

---

# Paket 2 Kararı

Paket 2 is repository hygiene and contract clarity.
It does not implement new trading features.
It fixes credential-shaped runtime store tracking, aligns example stores, and documents API/frontend contracts.

---

# Paket 3 Kararı

Paket 3 is API contract guard and static parser hardening.
It does not change backend routes, frontend runtime behavior, deploy behavior, Binance, Futures or real-trade logic.
It regenerates contract reports and requires missing endpoint count, method mismatch count and true blocker count to stay zero.

---

# Paket 4 Kararı

Paket 4 is dashboard decision funnel visibility.
It uses existing `/api/bot/last-scan` data in the frontend to show why the bot did not open a trade.
It does not add a backend endpoint and does not change Binance, Futures, real-trade, strategy, filter, risk or order behavior.

---

# Paket 5 Kararı

Paket 5 is mutating endpoint safety audit.
It adds a read-only quality gate for frontend mutating API calls:

```powershell
py scripts/level1_40_06_api_route_inventory.py
py scripts/level1_40_07_frontend_api_inventory.py
py scripts/level1_40_08_api_contract_diff.py --strict
py scripts/level1_40_09_missing_endpoint_report.py
py scripts/level1_40_10_mutating_endpoint_safety_audit.py
```

It does not change backend real-trade routes, Binance services, order execution, Futures, bot control runtime behavior, strategy, filter or risk logic.

---

# Paket 6 Kararı

Paket 6 is real-trade manual review matrix.
It converts Paket 5 `CRITICAL_REAL_TRADE` findings into a read-only owner approval and risk type matrix.

Quality gate order:

```powershell
py scripts/level1_40_06_api_route_inventory.py
py scripts/level1_40_07_frontend_api_inventory.py
py scripts/level1_40_08_api_contract_diff.py --strict
py scripts/level1_40_09_missing_endpoint_report.py
py scripts/level1_40_10_mutating_endpoint_safety_audit.py
py scripts/level1_40_11_real_trade_manual_review_matrix.py
```

It does not change real-trade routes, order execution, Binance, Futures, bot start/stop runtime behavior, Karabasan, strategy, filter or risk logic.

---

# Paket 7 Kararı

Paket 7 is owner approval contract audit.
It converts Paket 6 manual review expectations into a read-only contract audit for owner approval, readiness, dry-run evidence, audit reason and emergency lock expectations.

Quality gate order:

```powershell
py scripts/level1_40_06_api_route_inventory.py
py scripts/level1_40_07_frontend_api_inventory.py
py scripts/level1_40_08_api_contract_diff.py --strict
py scripts/level1_40_09_missing_endpoint_report.py
py scripts/level1_40_10_mutating_endpoint_safety_audit.py
py scripts/level1_40_11_real_trade_manual_review_matrix.py
py scripts/level1_40_12_owner_approval_contract_audit.py
```

It does not change live order submission, Binance, order executor, Futures, Karabasan, strategy, filter or bot signal behavior.

---

# Paket 8 Kararı

Paket 8 is Dashboard rule selection persistence and Paper Lab activation stability.
It keeps user filter/strategy selection drafts during save, verifies backend selected ids before clearing the draft, and prevents blind all-active checkbox fallback when backend sent an explicit empty selection.

Quality gate order:

```powershell
py scripts/level1_40_06_api_route_inventory.py
py scripts/level1_40_07_frontend_api_inventory.py
py scripts/level1_40_08_api_contract_diff.py --strict
py scripts/level1_40_09_missing_endpoint_report.py
py scripts/level1_40_10_mutating_endpoint_safety_audit.py
py scripts/level1_40_11_real_trade_manual_review_matrix.py
py scripts/level1_40_12_owner_approval_contract_audit.py
py scripts/level1_40_13_rule_selection_persistence_audit.py
```

It does not change backend model combination math, strategy/filter decision logic, Binance, Futures, real-trade, order executor or bot start/stop behavior.

---

# Paket 9 Kararı

Paket 9 is Paper Lab backend stability and rule save contract.
It adds backend payload validation, clearer HTTP errors, response shape guarantees and audit/log isolation for `/api/rules/activate-paper-lab`, rule save, rule get and rule delete.

Quality gate order:

```powershell
py scripts/level1_40_06_api_route_inventory.py
py scripts/level1_40_07_frontend_api_inventory.py
py scripts/level1_40_08_api_contract_diff.py --strict
py scripts/level1_40_09_missing_endpoint_report.py
py scripts/level1_40_10_mutating_endpoint_safety_audit.py
py scripts/level1_40_11_real_trade_manual_review_matrix.py
py scripts/level1_40_12_owner_approval_contract_audit.py
py scripts/level1_40_13_rule_selection_persistence_audit.py
py scripts/level1_40_14_rule_backend_stability_audit.py
```

It does not change Paper Lab model combination math, strategy/filter decision logic, Binance, Futures, real-trade, order executor or bot start/stop behavior.

---

# Paket 10 Kararı

Paket 10 is live system status visibility, backend access diagnosis and runtime rule_store protection.
It adds a Dashboard system status strip, shared frontend API error classification, bot start status verification and rule_store backup visibility.

Quality gate order:

```powershell
py scripts/level1_40_06_api_route_inventory.py
py scripts/level1_40_07_frontend_api_inventory.py
py scripts/level1_40_08_api_contract_diff.py --strict
py scripts/level1_40_09_missing_endpoint_report.py
py scripts/level1_40_10_mutating_endpoint_safety_audit.py
py scripts/level1_40_11_real_trade_manual_review_matrix.py
py scripts/level1_40_12_owner_approval_contract_audit.py
py scripts/level1_40_13_rule_selection_persistence_audit.py
py scripts/level1_40_14_rule_backend_stability_audit.py
py scripts/level1_40_15_system_status_runtime_store_audit.py
```

It does not change live order submission, Binance services, order executor, Futures, Karabasan math, strategy/filter decision logic or Paper Lab model combination math.

---

# Paket 10.8 Kararı

Paket 10.8 is Dashboard active rules selection persistence and Paper Lab independence.
It moves Dashboard active selection save to `/api/rules/selection`, prevents Paper Lab from reading or overwriting Dashboard selected ids, keeps Paper Lab state in separate runtime fields, and adds the 40.23 independence audit gate.

Quality gate order:

```powershell
py scripts\level1_40_20_live_startup_rules_hydration_audit.py
py scripts\level1_40_21_auth_restore_truth_audit.py
py scripts\level1_40_22_coinfilter_rules_paperlab_audit.py
py scripts\level1_40_23_rules_paperlab_independence_audit.py
py scripts\level1_40_07_frontend_api_inventory.py
py scripts\level1_40_08_api_contract_diff.py --strict
py scripts\level1_40_09_missing_endpoint_report.py
```

It does not change live order submission, Binance services, order executor, Futures, Karabasan math or strategy/filter decision logic.

---

# Paket 10.9 Kararı

Paket 10.9 is Paper Lab autonomous research engine hardening.
It prevents Paper Lab from using Dashboard selected ids, keeps results in isolated Paper Lab runtime state, makes repeated manual runs possible through a running/finally reset lifecycle, and adds the 40.24 audit gate.

Quality gate order:

```powershell
py scripts\level1_40_20_live_startup_rules_hydration_audit.py
py scripts\level1_40_21_auth_restore_truth_audit.py
py scripts\level1_40_22_coinfilter_rules_paperlab_audit.py
py scripts\level1_40_23_rules_paperlab_independence_audit.py
py scripts\level1_40_24_paperlab_autonomous_engine_audit.py
py scripts\level1_40_07_frontend_api_inventory.py
py scripts\level1_40_08_api_contract_diff.py --strict
py scripts\level1_40_09_missing_endpoint_report.py
```

It does not change live order submission, Binance services, order executor, Futures, Karabasan math or strategy/filter decision logic.

---

# Paket 10.10 Kararı

Paket 10.10 is Paper Lab persistent runtime store and hydration guarantee.
It records successful and failed Paper Lab research runs into ignored `backend/paper_lab_store.json` with atomic unique-tmp writes, exposes `/api/rules/paper-lab/status`, hydrates frontend Paper Lab state from backend persistent status, and adds the 40.25 audit gate.

Quality gate order:

```powershell
py scripts\level1_40_20_live_startup_rules_hydration_audit.py
py scripts\level1_40_21_auth_restore_truth_audit.py
py scripts\level1_40_22_coinfilter_rules_paperlab_audit.py
py scripts\level1_40_23_rules_paperlab_independence_audit.py
py scripts\level1_40_24_paperlab_autonomous_engine_audit.py
py scripts\level1_40_25_paperlab_persistence_audit.py
py scripts\level1_40_07_frontend_api_inventory.py
py scripts\level1_40_08_api_contract_diff.py --strict
py scripts\level1_40_09_missing_endpoint_report.py
py scripts\level1_40_10_mutating_endpoint_safety_audit.py
```

It does not change live order submission, Binance services, order executor, Futures, Karabasan math, strategy/filter decision logic or Paper Lab model combination math.

---

# Paket 10.11 Kararı

Paket 10.11 is Paper Lab hydration throttle and rules render stability.
It prevents `/api/rules/paper-lab/status` request storms with 60 second throttle and in-progress guard, prefers bundled `paper_lab_status`, keeps rules hydration/render independent from Paper Lab status loading, and adds the 40.26 audit gate.

Quality gate order:

```powershell
py scripts\level1_40_20_live_startup_rules_hydration_audit.py
py scripts\level1_40_21_auth_restore_truth_audit.py
py scripts\level1_40_22_coinfilter_rules_paperlab_audit.py
py scripts\level1_40_23_rules_paperlab_independence_audit.py
py scripts\level1_40_24_paperlab_autonomous_engine_audit.py
py scripts\level1_40_25_paperlab_persistence_audit.py
py scripts\level1_40_26_paperlab_hydration_stability_audit.py
py scripts\level1_40_08_api_contract_diff.py --strict
py scripts\level1_40_09_missing_endpoint_report.py
```

It does not change live order submission, Binance services, order executor, Futures, Karabasan math, strategy/filter decision logic, Paper Lab persistence store or Paper Lab model combination math.

---

# Paket 10.12 Kararı

Paket 10.12 is runtime health Paper Lab store link fix.
It links `build_runtime_health` / `/health/ops` last_paper_lab status to `backend/paper_lab_store.json` through `get_last_paper_lab_run`, preserves legacy runtime field fallback, keeps health endpoint exception-safe, and adds the 40.27 audit gate.

Quality gate order:

```powershell
py scripts\level1_40_27_runtime_health_paperlab_store_audit.py
py scripts\level1_40_26_paperlab_hydration_stability_audit.py
py scripts\level1_40_25_paperlab_persistence_audit.py
py scripts\level1_40_09_missing_endpoint_report.py
py scripts\level1_40_08_api_contract_diff.py --strict
```

It does not change live order submission, Binance services, order executor, Futures, Karabasan math, strategy/filter decision logic, Paper Lab persistence store or Paper Lab model combination math.

---

# Paket 10.13 Kararı

Paket 10.13 is runtime health Paper Lab user resolution fix.
It adds `get_latest_paper_lab_run_any_user()` to scan all `paper_lab_store.json` users, makes `build_runtime_health` try exact username first and any-user latest run second, includes `username` in `last_paper_lab`, and adds the 40.28 audit gate.

Quality gate order:

```powershell
py scripts\level1_40_28_runtime_health_paperlab_user_resolution_audit.py
py scripts\level1_40_27_runtime_health_paperlab_store_audit.py
py scripts\level1_40_26_paperlab_hydration_stability_audit.py
py scripts\level1_40_09_missing_endpoint_report.py
py scripts\level1_40_08_api_contract_diff.py --strict
```

It does not change live order submission, Binance services, order executor, Futures, Karabasan math, strategy/filter decision logic, Paper Lab persistence store writing or Paper Lab model combination math.

---

# Paket 10.14 Kararı

Paket 10.14 is CoinFilter persistence proof and 8-hour report infrastructure.
It proves CoinFilter save payload, backend response, settings store echo and GET refresh echo match, protects the last persisted CoinFilter value from stale bundle/partial settings payloads, adds report-ready bot no-trade reason funnel fields, and exposes scheduler-independent 8-hour report endpoints with the 40.29 audit gate.

Quality gate order:

```powershell
py scripts\level1_40_29_coinfilter_persistence_and_8h_report_audit.py
py scripts\level1_40_28_runtime_health_paperlab_user_resolution_audit.py
py scripts\level1_40_27_runtime_health_paperlab_store_audit.py
py scripts\level1_40_26_paperlab_hydration_stability_audit.py
py scripts\level1_40_25_paperlab_persistence_audit.py
py scripts\level1_40_09_missing_endpoint_report.py
py scripts\level1_40_08_api_contract_diff.py --strict
```

It does not add a live Paper Lab monitor, WebSocket, SSE, scheduler dependency, live order submission, Binance behavior, order executor behavior, Futures behavior, Karabasan math, strategy/filter decision logic or Paper Lab model combination math.

---

# Paket 10.15 Kararı

Paket 10.15 is bot runtime heartbeat truth and scan loop recovery.
It separates persistent `requested_running` from live `loop_alive`, derives effective `bot_running` from fresh tick/scan heartbeat, restores requested paper/shadow bot loops after backend restart when emergency lock is not active, and adds the 40.30 audit gate.

Quality gate order:

```powershell
py scripts\level1_40_30_bot_runtime_heartbeat_truth_audit.py
py scripts\level1_40_29_coinfilter_persistence_and_8h_report_audit.py
py scripts\level1_40_28_runtime_health_paperlab_user_resolution_audit.py
py scripts\level1_40_09_missing_endpoint_report.py
py scripts\level1_40_08_api_contract_diff.py --strict
```

It does not loosen CoinFilter rules, add live Paper Lab monitor/progress/WebSocket/SSE, unlock real trading, change Binance behavior, order executor behavior, Futures behavior, Karabasan math, strategy/filter decision logic or Paper Lab model combination math.

---

# Paket 10.16 Kararı

Paket 10.16 is bot restore real scan loop recovery.
It prevents restore from faking heartbeat, makes startup restore and manual bot start share `ensure_bot_loop_running`, validates alive state through a real scheduler thread reference plus fresh heartbeat, and adds the 40.31 audit gate.

Quality gate order:

```powershell
py scripts\level1_40_31_bot_restore_real_loop_audit.py
py scripts\level1_40_30_bot_runtime_heartbeat_truth_audit.py
py scripts\level1_40_29_coinfilter_persistence_and_8h_report_audit.py
py scripts\level1_40_09_missing_endpoint_report.py
py scripts\level1_40_08_api_contract_diff.py --strict
```

It does not loosen CoinFilter rules, add Paper Lab live monitor/progress/WebSocket/SSE, unlock real trading, change Binance behavior, order executor behavior, Futures behavior, Karabasan math, strategy/filter decision logic or Paper Lab model combination math.

---

# Paket 10.17 Kararı

Paket 10.17 is bot restore first tick proof.
It prevents thread alive from being accepted as restore success, requires first real bot tick/scan evidence before `loop_alive=true`, adds a non-blocking restore watchdog, separates `waiting_first_tick` from `restore_no_first_tick`, and adds the 40.32 audit gate.

Quality gate order:

```powershell
py scripts\level1_40_32_bot_restore_first_tick_audit.py
py scripts\level1_40_31_bot_restore_real_loop_audit.py
py scripts\level1_40_30_bot_runtime_heartbeat_truth_audit.py
py scripts\level1_40_29_coinfilter_persistence_and_8h_report_audit.py
py scripts\level1_40_09_missing_endpoint_report.py
py scripts\level1_40_08_api_contract_diff.py --strict
```

It does not loosen CoinFilter rules, add Paper Lab live monitor/progress/WebSocket/SSE, unlock real trading, change Binance behavior, order executor behavior, Futures behavior, Karabasan math, strategy/filter decision logic or Paper Lab model combination math.

---

# Paket 10.18 Kararı

Paket 10.18 is CoinFilter final simplification and bot pipeline contract start.
It makes CoinFilter a focused Binance USDT candidate-pool page, removes rule/strategy inventory from that page, adds `/api/bot/coinfilter-test-scan`, adds `test_scan=true` and a pipeline contract, and adds the 40.33 audit gate.

# Paket 10.19 Kararı

Paket 10.19 CoinFilter test scan timeout duzeltmesidir.

- Test scan `scan_market(..., deep_analysis=False)` kullanir.
- Normal bot tick deep teknik analizi kullanmaya devam eder.
- Lightweight test scan `analyze_symbol` ve `fetch_klines` calistirmaz.
- Diagnostics `deep_analysis_enabled=false`, `deep_analysis_limit=0`, `deep_analyzed_count=0` doner.
- Paket 11 oncesi 40.34 audit `ok` ve canli limit=20/1000 istekleri HTTP 200 olmalidir.

# Paket 10.20 Kararı

Paket 10.20 last scan contract preservation duzeltmesidir.

- Storage normalizasyonu test scan, mode, pipeline ve universe alanlarini korur.
- Eksik legacy `last_scan.pipeline`, ayni veya daha yeni history kaydindan guvenli sekilde repair edilir.
- Mevcut pipeline history tarafindan overwrite edilmez.
- `/api/bot/last-scan` test_scan, pipeline ve scan_mode alanlarini acik doner.
- Paket 11 oncesi 40.35 audit `ok` ve canli test scan/last-scan degerleri ayni olmalidir.

# Paket 10.21 Kararı

Paket 10.21 CoinFilter save ve bot start stability kapisidir.

- Settings save timeout abort ham AbortError olarak gosterilmez.
- Save sonrasi backend reload ve payload/response/store/refresh karsilastirmasi zorunludur.
- Scan diagnostics kullanilan CoinFilter ayarlarini raporlar.
- Bot start `requested_running=true` degerini first tick failure durumunda da korur.
- `bot_running=true` yalnizca gercek loop ve first tick kaniti ile gorunur.
- Paket 10.22, 10.21 canli kabul gecmeden baslatilmaz.

# Paket 10.21.1 Hotfix Kararı

- None/NaN/Infinity market ve indicator degerleri karsilastirmaya girmeden normalize edilir.
- Normalize edilemeyen coin loop crash yerine reject edilir.
- User-level hata scheduler task'ini global olarak oldurmez.
- Traceback ve gercek exception sebebi runtime state/log icinde saklanir.
- Teknik hata `requested_running=true` kullanici istegini kapatmaz.
- Normal bot tick deep analiz adayi en fazla 12'dir.

# Paket 10.21.2 Hotfix Kararı

- Her scan tamamlandiginda `last_scan_time`, `last_scan.time` ile birebir senkronlanir.
- Bot status ve Dashboard bundle eksik top-level alan icin nested scan time fallback kullanir.
- Bot running ve scan error bosken Dashboard Backend API durumu online kalir.
- `requested_running`, `bot_running` ve `engine_status` runtime truth alanlari korunur.
- Paket 10.22 oncesi 40.36.2 audit `ok` olmalidir.

# Paket 10.21.3 CPU Throttle Kararı

- Startup'ta `requested_running=false` kullanici icin scheduler veya restore loop baslatilmaz.
- Stopped kullanici scan, tick, deep analysis, heartbeat veya runtime store write uretmez.
- Tick araligi en az 30 saniye, hata backoff'u en az 60 saniyedir.
- Ayni kullanici icin bir tick bitmeden ikinci tick baslamaz.
- Normal bot deep analysis limiti en fazla 8 semboldur.
- Paket 10.22 ve Dashboard 10.23 bu pakette baslatilmaz.
- Paket 10.22 oncesi 40.36.3 audit ve canli CPU kabulü tamamlanmalidir.

# Paket 10.21.4 First Tick Timeout Kararı

- Bot start endpointi first tick veya deep analysis bitisini beklemez.
- First tick en fazla 25 saniye watchdog ile korunur.
- Normal scan 20 saniye, deep analysis 15 saniye deadline kullanir.
- Tick success, exception veya timeout fark etmeksizin finally ile unlock edilir.
- Failed bot state `requested_running=false`, `bot_running=false`, `tick_in_progress=false` olur.
- Frontend start 200 cevabini generic API hatasi saymaz; first tick timeout mesajini ayri gosterir.
- Paket 10.22 ve Dashboard 10.23 bu pakette baslatilmaz.
- Paket 10.22 oncesi 40.36.4 audit ve canli CPU/RAM kabulü tamamlanmalidir.

# Paket 10.21.5 Hard Cancel Scan Worker Kararı

- [x] First tick `deep_analysis=False` lightweight snapshot olarak ayrildi.
- [x] Deep scan ayri daemon worker'a tasindi.
- [x] Worker generation ve cooperative cancel guard eklendi.
- [x] Stop/emergency/timeout stale worker write'ini atomik olarak engelliyor.
- [x] CoinFilter cached last scan'i koruyor; bos durumda `Henüz canlı tarama yok` gosteriyor.
- [x] 40.36.5 audit kalite kapisi eklendi.
- [ ] Deploy sonrasi CPU/RAM ve 45 saniyelik bot start canli kabulü yapilacak.
- Paket 10.22 ve Paket 10.23, canli kabul tamamlanmadan baslatilmayacak.

# Paket 10.21.5 Revize 2 First Tick Heartbeat Kararı

- [x] First tick saf heartbeat oldu; market ve analiz cagrilari kaldirildi.
- [x] Restore first tick kaniti yeni `last_tick` alanina baglandi.
- [x] Startup scan grace ile cached scan startup'i bloke etmiyor.
- [x] Frontend status polling gecici hatada sinirli tekrar deniyor.
- [x] `10k` hacim varyantlari `10000` parse ediliyor.
- [x] CoinFilter `quoteVolume_USDT_24h` diagnostic gosteriyor.
- [x] 40.36.5 Rev2 audit kalite kapisi eklendi.
- [ ] Deploy sonrasi 45 saniyelik bot start ve CoinFilter hacim diagnostic canli kabulü yapilacak.
- Paket 10.22 ve Paket 10.23 baslatilmadi.

Quality gate order:

```powershell
py scripts\level1_40_33_coinfilter_final_pipeline_audit.py
py scripts\level1_40_32_bot_restore_first_tick_audit.py
py scripts\level1_40_31_bot_restore_real_loop_audit.py
py scripts\level1_40_30_bot_runtime_heartbeat_truth_audit.py
py scripts\level1_40_29_coinfilter_persistence_and_8h_report_audit.py
py scripts\level1_40_09_missing_endpoint_report.py
py scripts\level1_40_08_api_contract_diff.py --strict
```

It does not open real orders, unlock Binance live order behavior, change Paper Lab engine, change Strategy Editor, start Paket 11 or commit runtime store files.

---

# Paket 10.1 Kararı

Paket 10.1 is auth 401, logout and frontend state guard.
It separates auth/session expiry from backend offline, makes logout tolerant of 401 and preserves the last successful rule list after unauthorized responses.

Quality gate order:

```powershell
py scripts/level1_40_13_rule_selection_persistence_audit.py
py scripts/level1_40_14_rule_backend_stability_audit.py
py scripts/level1_40_15_system_status_runtime_store_audit.py
py scripts/level1_40_16_auth_401_state_guard_audit.py
```

It does not change live order submission, Binance services, order executor, Futures, Karabasan math, strategy/filter decision logic or Paper Lab model combination math.

---

# Paket 10.2 Kararı

Paket 10.2 is Paper Lab live refresh and backend state truth.
It removes the Auto Paper Lab `apiReady/apiSyncReady` hard-block, reads `/api/rules` before local cache decisions, preserves successful Paper Lab state after refresh failures and protects existing rules when dashboard bundle returns missing/unsafe rules payloads.

Quality gate order:

```powershell
py scripts/level1_40_13_rule_selection_persistence_audit.py
py scripts/level1_40_14_rule_backend_stability_audit.py
py scripts/level1_40_15_system_status_runtime_store_audit.py
py scripts/level1_40_16_auth_401_state_guard_audit.py
py scripts/level1_40_17_paper_lab_state_truth_audit.py
```

It does not change live order submission, Binance services, order executor, Futures, Karabasan math, strategy/filter decision logic or Paper Lab model combination math.

---

# Paket 10.3 Kararı

Paket 10.3 is auth store atomic write lock and login double-submit guard.
It replaces shared `auth_store.json.tmp` writes with unique tmp files under RLock, handles auth store write failures as controlled login responses and prevents repeated frontend login submits.

Quality gate order:

```powershell
py scripts/level1_40_16_auth_401_state_guard_audit.py
py scripts/level1_40_17_paper_lab_state_truth_audit.py
py scripts/level1_40_18_auth_store_atomic_write_audit.py
```

It does not change live order submission, Binance services, order executor, Futures, Karabasan math, strategy/filter decision logic or Paper Lab model combination math.

---

# Paket 10.4 Kararı

Paket 10.4 is sync storm and mutation abort isolation.
It separates core reads, heavy reads, protected mutations and audit best-effort requests so CoinFilter, Rules and Paper Lab save flows are not marked as backend offline because of unrelated aborts or heavy endpoint timeouts.

Quality gate order:

```powershell
py scripts\level1_40_16_auth_401_state_guard_audit.py
py scripts\level1_40_17_paper_lab_state_truth_audit.py
py scripts\level1_40_18_auth_store_atomic_write_audit.py
py scripts\level1_40_19_mutation_abort_isolation_audit.py
py scripts\level1_40_07_frontend_api_inventory.py
py scripts\level1_40_08_api_contract_diff.py --strict
py scripts\level1_40_09_missing_endpoint_report.py
```

It does not change live order submission, Binance services, order executor, Futures, Karabasan math, strategy/filter decision logic or Paper Lab model combination math.

---

# Paket 10.5 Kararı

Paket 10.5 is live startup, rules hydration and backend timeout recovery.
It slows frontend polling, defers heavy sync after startup/login, keeps `/api/rules` and `/api/settings` hydrated even when dashboard bundle is degraded, and protects login/logout from sync storms.

Quality gate order:

```powershell
py scripts\level1_40_19_mutation_abort_isolation_audit.py
py scripts\level1_40_20_live_startup_rules_hydration_audit.py
```

It does not change live order submission, Binance services, order executor, Futures, Karabasan math, strategy/filter decision logic or Paper Lab model combination math.

---

# Paket 10.6 Kararı

Paket 10.6 is auth restore truth, token validation and startup sync gate.
It treats localStorage token as a restore candidate only, verifies it with `/api/auth/me`, blocks dashboard/rules/settings sync until restore completes, and keeps Paket 10.5 startup/heavy-sync guards intact.

Quality gate order:

```powershell
py scripts\level1_40_20_live_startup_rules_hydration_audit.py
py scripts\level1_40_21_auth_restore_truth_audit.py
py scripts\level1_40_07_frontend_api_inventory.py
py scripts\level1_40_08_api_contract_diff.py --strict
py scripts\level1_40_09_missing_endpoint_report.py
```

It does not change live order submission, Binance services, order executor, Futures, Karabasan math, strategy/filter decision logic or Paper Lab model combination math.

---

# Paket 10.7 Kararı

Paket 10.7 is CoinFilter persistence, rules selection integrity and Paper Lab visibility.
It keeps CoinFilter edits in local draft until save succeeds, prevents empty/missing selected ids from becoming all-selected, surfaces the latest Paper Lab run on the strategies page even when heavy reports are delayed, and adds an end-to-end rules selection proof from save payload through backend response, dashboard render and post-Paper-Lab render.

Quality gate order:

```powershell
py scripts\level1_40_20_live_startup_rules_hydration_audit.py
py scripts\level1_40_21_auth_restore_truth_audit.py
py scripts\level1_40_22_coinfilter_rules_paperlab_audit.py
py scripts\level1_40_07_frontend_api_inventory.py
py scripts\level1_40_08_api_contract_diff.py --strict
py scripts\level1_40_09_missing_endpoint_report.py
```

It does not change live order submission, Binance services, order executor, Futures, Karabasan math, strategy/filter decision logic or Paper Lab model combination math.

---

# 1. Ön Hazırlık

## 1.1 Gereken araçlar

Kurulu olması gerekenler:

- Git.
- Python 3.11+.
- Node.js 18+.
- PostgreSQL 15+.
- Nginx.
- Docker ve Docker Compose.
- VS Code.
- GitHub hesabı.
- VPS erişimi.
- Binance test hesabı ve canlı API key.

## 1.2 Repo hazırlığı

Yapılacaklar:

1. GitHub reposunu bilgisayara çek.
2. Eski gereksiz zip/doküman kalıntılarını ayır.
3. Ana doküman olarak README.md ve todo.md dosyalarını köke koy.
4. Eski rev dokümanları gerekiyorsa `/docs/archive/` klasörüne taşı.
5. `frontend/js/pages.js` eski monolitik yapıysa legacy kabul et.
6. Aktif sayfa yapısını `frontend/js/pages/` klasörü altında modüler hale getir.

Kabul kriteri:

- Kök dizinde README.md ve todo.md var.
- Aktif kod dosyaları ile arşiv dosyaları karışmıyor.
- Geliştirici hangi dosyanın aktif olduğunu biliyor.

---

# 2. Backend Temel Kurulum

## 2.1 Python sanal ortamı

Adımlar:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell için:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Kabul kriteri:

- `python --version` çalışıyor.
- `pip list` proje paketlerini gösteriyor.
- Backend import hatası vermiyor.

## 2.2 Environment değişkenleri

`.env` dosyası oluştur:

```env
APP_ENV=development
DATABASE_URL=postgresql://user:password@localhost:5432/hmtstc
JWT_SECRET=change_me
ENCRYPTION_KEY=change_me_32_bytes
BINANCE_BASE_URL=https://api.binance.com
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

Kurallar:

- `.env` asla GitHub’a commit edilmez.
- `ENCRYPTION_KEY` database içinde saklanmaz.
- Production secret değerleri VPS üzerinde güvenli saklanır.

Kabul kriteri:

- Backend `.env` dosyasını okuyabiliyor.
- Secret değerleri loglara yazılmıyor.

---

# 3. Veritabanı Kurulumu

## 3.1 PostgreSQL oluşturma

Adımlar:

1. PostgreSQL kur.
2. `hmtstc` adında database oluştur.
3. `hmtstc_user` adında kullanıcı oluştur.
4. Sadece gerekli yetkileri ver.

Örnek:

```sql
CREATE DATABASE hmtstc;
CREATE USER hmtstc_user WITH PASSWORD 'strong_password';
GRANT ALL PRIVILEGES ON DATABASE hmtstc TO hmtstc_user;
```

## 3.2 Migration sistemi

Alembic veya eşdeğer migration aracı kur.

İlk migration’da oluşturulacak tablolar:

```text
users
roles
sessions
user_exchange_accounts
user_bot_settings
user_strategy_settings
user_filter_settings
risk_agreements
user_risk_acceptance
signals
orders
order_states
positions
trade_journal
risk_events
karabasan_scores
audit_logs
system_health
```

Kabul kriteri:

- Migration sıfırdan çalışıyor.
- Tablolar oluşuyor.
- Rollback çalışıyor.
- Test database production’dan ayrı.

---

# 4. Auth ve Kullanıcı İzolasyonu

## 4.1 Kullanıcı modeli

`users` tablosu alanları:

```text
id
email
password_hash
role
status
created_at
updated_at
last_login_at
```

Roller:

```text
USER
ADMIN_AHMET
```

## 4.2 Login API

Uç noktalar:

```text
POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/me
```

Kabul kriteri:

- Kullanıcı giriş yapıyor.
- Token üretiliyor.
- Token olmadan protected API çalışmıyor.
- Admin olmayan admin endpointlerine giremiyor.

## 4.3 Tenant isolation

Kural:

```text
Backend user_id değerini sadece token’dan alır.
Frontend’den gelen user_id dikkate alınmaz.
```

Test senaryosu:

1. Kullanıcı A login olur.
2. Kullanıcı B’nin ayarını okumaya çalışır.
3. Backend 403 döndürür.

Kabul kriteri:

- Kullanıcı A, Kullanıcı B verisine erişemez.
- Admin rolü olmayan admin işlem yapamaz.

---

# 5. API Secret Güvenliği

## 5.1 Binance API kayıt ekranı

Ayarlar sayfasında alanlar:

- API Key.
- API Secret.
- API Test butonu.
- API Status.
- Maskelenmiş API Key.

## 5.2 Backend saklama kuralı

- API secret encrypted saklanır.
- API secret frontend’e geri dönmez.
- Admin secret göremez.
- Secret loglanmaz.

Kabul kriteri:

- Database içinde secret düz metin görünmez.
- API response içinde secret yok.
- Loglarda secret yok.

## 5.3 API permission kontrolü

API key kaydedilirken:

1. Key geçerli mi?
2. Trade yetkisi var mı?
3. Read yetkisi var mı?
4. Withdrawal yetkisi var mı?

Withdrawal yetkisi varsa key reddedilir.

Kabul kriteri:

- Withdrawal izinli key kaydedilemez.
- API test hatası kullanıcıya anlaşılır döner.

---

# 6. Kullanıcı Ayarları

## 6.1 Ayar modeli

`user_bot_settings` alanları:

```text
user_id
allocated_budget_usdt
position_size_usdt
max_open_positions
daily_loss_limit_usdt
bot_mode
risk_level
created_at
updated_at
```

Bot modları:

```text
OFF
ON
AUTO
```

## 6.2 Ayarlar API

```text
GET /api/settings
PUT /api/settings/bot
PUT /api/settings/binance
POST /api/settings/binance/test
DELETE /api/settings/binance
```

Kabul kriteri:

- Kullanıcı kendi bütçesini kaydedebiliyor.
- Bütçe Binance bakiyesinden büyük olamaz.
- Ayarlar başka kullanıcıyı etkilemez.

---

# 7. Dashboard Geliştirme

## 7.1 Dashboard alanları

Dashboard’da gösterilecekler:

- API bağlı mı?
- Bot açık mı?
- Bot modu nedir?
- Bot bütçesi ne?
- Günlük PnL.
- Açık pozisyon sayısı.
- Açık emirler.
- Son sinyal.
- Karabasan durumu.
- Bot neden işlem açmadı?
- Emergency Stop.

## 7.2 Dashboard API

```text
GET /api/dashboard
GET /api/dashboard/summary
GET /api/dashboard/explanation
PUT /api/dashboard/bot-mode
```

Kabul kriteri:

- Dashboard 2 saniye içinde yüklenir.
- Botun işlem açmama nedeni gösterilir.
- Emergency Stop butonu çalışır.

---

# 8. Binance Spot Connector

## 8.1 Gerekli fonksiyonlar

```text
test_api_connection()
get_account_balance()
get_symbol_rules()
get_open_orders()
place_limit_order()
cancel_order()
get_order_status()
get_trade_history()
```

## 8.2 Symbol rule kontrolü

Her emirden önce:

- Min notional.
- Lot size.
- Tick size.
- Precision.
- Step size.

Kabul kriteri:

- Precision hatası alınmıyor.
- Min notional altı emir gönderilmiyor.
- Binance reddi düzgün yönetiliyor.

---

# 9. Strategy ve Filter Engine

## 9.1 Coin evreni

İlk sürüm:

- Top 20–30 yüksek hacimli USDT paritesi.
- Yeni listelenen coin yok.
- Düşük hacimli coin yok.
- Yüksek spread coin yok.

## 9.2 Filtreler

İlk sürüm filtreleri:

```text
BTC trend filtresi
Hacim filtresi
Spread filtresi
Likidite filtresi
Volatilite filtresi
Karabasan filtresi
```

## 9.3 Strateji

İlk canlıda tek strateji:

```text
Spot Momentum Trend Strategy V0
```

Giriş şartları:

- 1H trend pozitif.
- 15M momentum pozitif.
- Hacim ortalamanın üzerinde.
- Spread düşük.
- Order book derinliği yeterli.
- Karabasan ALLOW.

Kabul kriteri:

- Sinyal reason_code ile üretilir.
- Hangi filtre geçti/kaldı loglanır.

---

# 10. Risk Engine

## 10.1 Risk kontrolleri

Her emirden önce çalışır:

- Bot ON/AUTO mu?
- API bağlı mı?
- Risk sözleşmesi kabul edildi mi?
- Bot bütçesi yeterli mi?
- Günlük zarar limiti doldu mu?
- Max açık pozisyon doldu mu?
- Aynı sembolde açık emir var mı?
- Aynı sembolde açık pozisyon var mı?
- Stop Loss hesaplanıyor mu?
- Take Profit hesaplanıyor mu?
- Spread uygun mu?
- Likidite uygun mu?
- Karabasan ALLOW mu?

## 10.2 Risk kararları

```text
APPROVED
WAIT
BLOCKED
REDUCED_SIZE
EMERGENCY_STOP
MANUAL_REVIEW_REQUIRED
```

Kabul kriteri:

- Risk Engine onayı olmadan emir gitmez.
- Her red nedeni reason_code ile yazılır.

---

# 11. Order Lifecycle

## 11.1 State machine

```text
SIGNAL_CREATED
SIGNAL_VALIDATED
RISK_CHECK_STARTED
RISK_APPROVED
ORDER_PREPARED
ORDER_SENT
ORDER_ACCEPTED
PARTIALLY_FILLED
FILLED
STOP_LOSS_ATTACHED
TAKE_PROFIT_ATTACHED
POSITION_MONITORING
EXIT_SIGNAL_RECEIVED
CLOSING_ORDER_SENT
CLOSED
PNL_CALCULATED
TRADE_JOURNAL_WRITTEN
RECONCILED
```

## 11.2 Duplicate koruma

- signal_id.
- idempotency_key.
- user-symbol lock.
- timeout sonrası önce Binance status sorgula.

Kabul kriteri:

- Aynı sinyal iki emir açmaz.
- Timeout sonrası kör retry yapılmaz.
- Partial fill yönetilir.

---

# 12. Trade Journal ve Raporlama

Her işlem kaydedilir:

- user_id.
- symbol.
- entry price.
- exit price.
- quantity.
- fee.
- slippage.
- gross PnL.
- net PnL.
- strategy_id.
- filter_result.
- karabasan_score.
- open_reason.
- close_reason.

CSV export zorunlu.

Kabul kriteri:

- Kullanıcı kendi trade history verisini indirebilir.
- Başka kullanıcının verisini indiremez.

---

# 13. Karabasan V0

## 13.1 Girdiler

- BTC trend.
- BTC ani düşüş.
- BTC volatilite.
- Binance API health.
- System health.

## 13.2 Çıktılar

```text
ALLOW
WAIT
BLOCK
```

Kabul kriteri:

- Karabasan BLOCK ise yeni emir yok.
- Karabasan WAIT ise yeni emir yok, açık pozisyon izlenir.
- Karabasan kararı Dashboard’da görünür.

---

# 14. Paper Lab Basic

## 14.1 İlk kapsam

- Admin only.
- Sanal bütçe.
- 3 filtre x 3 strateji kombinasyonu.
- Her model 1000 USDT.
- 100 USDT x 10 işlem.

## 14.2 Metrikler

- Net PnL.
- Max drawdown.
- Win rate.
- Profit factor.
- Komisyon etkisi.
- Slippage etkisi.
- Karabasan uyumu.

Kabul kriteri:

- Paper sonuçları canlıyı otomatik değiştirmez.
- Admin onayı olmadan model promotion olmaz.

---

# 15. Monitoring ve Alerting

## 15.1 İzlenecek metrikler

- API latency.
- Binance latency.
- Failed orders.
- Rejected orders.
- Active bots.
- PnL.
- Drawdown.
- Win rate.
- Profit factor.
- CPU/RAM.
- DB health.

## 15.2 Alert durumları

- Binance API down.
- DB down.
- Stop loss failed.
- Daily loss limit reached.
- Reconciliation mismatch.
- Suspicious login.

Kabul kriteri:

- Kritik alert admin’e görünür.
- Emergency Stop tetiklenebilir.

---

# 16. Test Planı

## 16.1 Unit test

Test edilecekler:

- Auth.
- Tenant isolation.
- Secret encryption.
- Risk Engine.
- Strategy Engine.
- Order Lifecycle.
- Karabasan.

## 16.2 Integration test

Test edilecekler:

- API key test.
- Bakiye okuma.
- Sembol kuralları.
- Emir prepare.
- Emir status.
- Trade journal.

## 16.3 E2E test

Senaryo:

1. Kullanıcı login olur.
2. API key girer.
3. API test başarılı olur.
4. Bot bütçesi girer.
5. Risk sözleşmesi kabul eder.
6. Bot ON olur.
7. Sinyal oluşur.
8. Risk Engine onaylar.
9. Emir hazırlanır.
10. Mock Binance emri kabul eder.
11. Pozisyon Dashboard’da görünür.
12. İşlem kapanır.
13. Trade Journal oluşur.

Kabul kriteri:

- E2E senaryo hatasız çalışır.

---

# 17. Deploy Planı

## 17.1 VPS hazırlığı

- Ubuntu server.
- Python.
- Node.js.
- PostgreSQL.
- Nginx.
- SSL.
- Systemd servisleri.

## 17.2 Servisler

```text
hmtstc-backend.service
hmtstc-webhook.service
hmtstc-deploy.service
```

## 17.3 Nginx

- Frontend statik dosyaları servis eder.
- `/api` isteklerini backend’e proxy eder.
- HTTPS zorunlu.

## 17.4 GitHub deploy

- GitHub push.
- Webhook.
- Deploy script.
- Backup.
- Pull latest.
- Migration.
- Restart backend.
- Health check.

Kabul kriteri:

- Deploy sonrası health check başarılı.
- Rollback planı var.

---

# 18. Controlled Live Pilot

## 18.1 Pilot sınırları

- İlk kullanıcı: Admin/Ahmet veya test hesabı.
- Bot bütçesi düşük.
- Max açık pozisyon: 1–3.
- Sadece yüksek hacimli USDT pariteleri.
- Stop Loss zorunlu.
- Take Profit zorunlu.
- Emergency Stop aktif.

## 18.2 Pilot başarı kriterleri

- Emirler kaybolmuyor.
- Duplicate emir yok.
- Risk Engine doğru çalışıyor.
- Dashboard doğru gösteriyor.
- Trade Journal doğru kayıt tutuyor.
- PnL doğru hesaplanıyor.
- Emergency Stop çalışıyor.

## 18.3 Pilot sonrası

- Hatalar düzeltilir.
- Paper Lab verileri incelenir.
- Karabasan geliştirilir.
- Çok kullanıcı fazına geçilir.

---

# 19. Futures Fazı

Futures ilk canlı kapsamda yoktur.

Futures için şartlar:

- Spot MVP stabil.
- Paper Lab stabil.
- Karabasan V1 çalışıyor.
- Futures testnet başarılı.
- Liquidation distance hesaplanıyor.
- Funding fee izleniyor.
- Reduce-only close çalışıyor.
- Admin onayı var.
- Kullanıcı risk sözleşmesi ayrı.

İlk Futures canlı sadece admin pilot olabilir.

---

# 20. Final Kontrol Listesi

```text
[ ] README.md kökte
[ ] todo.md kökte
[ ] PostgreSQL hazır
[ ] Migration çalışıyor
[ ] Auth çalışıyor
[ ] RBAC çalışıyor
[ ] Tenant isolation test edildi
[ ] API secret encrypted
[ ] Binance API test çalışıyor
[ ] Dashboard MVP hazır
[ ] Ayarlar sayfası hazır
[ ] Risk sözleşmesi hazır
[ ] Spot connector hazır
[ ] Strategy Engine hazır
[ ] Filter Engine hazır
[ ] Risk Engine hazır
[ ] Order Lifecycle hazır
[ ] Trade Journal hazır
[ ] Karabasan V0 hazır
[ ] Audit Log hazır
[ ] Emergency Stop hazır
[ ] Monitoring hazır
[ ] Paper Lab basic hazır
[ ] E2E test başarılı
[ ] Deploy başarılı
[ ] Controlled Live Pilot başlatıldı
```

Bu liste tamamlanmadan genel kullanıcıya canlı işlem açılmamalıdır.

## Paket 10.23 Dashboard Live Trade Network

- [x] Bot kontrolleri dashboard icine alindi.
- [x] Header bot kontrol dependency'si kaldirildi.
- [x] Canvas tabanli Live Trade Network eklendi.
- [x] CoinFilter ve volume diagnostic ozeti eklendi.
- [x] Portfoy, PnL ve son olay panelleri eklendi.
- [x] 900px ve 640px responsive kurallari eklendi.
- [x] 40.37 audit kalite kapisi eklendi.
- [ ] Deploy sonrasi masaustu/mobil canli kabul tamamlanacak.

## Paket 10.21.5 Revize 3 Runtime Contract

- [x] Merkezi auto-scan ve background-worker flagleri default false.
- [x] Bot start heartbeat-only ve idempotent.
- [x] Bot stop worker state cancel-and-clear sozlesmesinde.
- [x] Status read-only ve yalnizca stale worker cleanup yapabilir.
- [x] Dashboard bundle worker veya scan baslatmiyor.
- [x] Frontend start/stop pending guard 5 saniye ile sinirli.
- [x] 40.36.5 Revize3 audit eklendi ve lokal kalite kapisi temiz.
- [ ] VPS start/stop sonrasi CPU ve process canli kabul testi tamamlanacak.

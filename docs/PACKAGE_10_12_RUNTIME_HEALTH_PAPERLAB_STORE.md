# Paket 10.12 Runtime Health Paper Lab Store

## 1. Paket amaci

Paket 10.12, `/health/ops` runtime health ciktisinda `last_paper_lab: missing` gorunmesine neden olan kaynak baglantisi eksigini giderir.

Sorun Paper Lab persistence degildi. Son Paper Lab run kaydi `backend/paper_lab_store.json` icinde tutuluyor, ancak `build_runtime_health` yeni persistent store'u okumuyordu.

## 2. Kapsam

Degisen davranis:

- `backend/services/real_trade_safety_service.py` icindeki `build_runtime_health` artik once `get_last_paper_lab_run(username)` ile persistent Paper Lab store'u okur.
- Store'da run varsa `last_paper_lab.source = paper_lab_store` doner.
- Store bos ise eski runtime alanlarina fallbaack korunur.
- Store okuma hatasi health endpoint'i dusurmez.

Degistirilmeyen davranislar:

- Paper Lab persistence store yazimi
- Paper Lab autonomous engine
- Dashboard active selection
- Trading logic
- Binance / order executor / Futures alanlari

## 3. Username tespiti

Runtime health kullaniciyi su sirayla tespit eder:

1. `settings.username`
2. `settings.user`
3. `data.username`
4. `data.user`
5. `admin` fallback

## 4. last_paper_lab ciktisi

Store'da run varsa:

```json
{
  "state": "ok",
  "seconds": 0,
  "fresh": true,
  "started_at": "...",
  "completed_at": "...",
  "run_id": "...",
  "status": "completed",
  "source": "paper_lab_store"
}
```

Store okuma exception verirse endpoint dusmez:

```json
{
  "state": "missing",
  "seconds": null,
  "fresh": false,
  "source": "paper_lab_store",
  "error": "..."
}
```

Store bos ise legacy fallback:

- `data.last_paper_lab_tick`
- `data.last_model_evaluation_at`
- `paper_lab.last_run_at`

## 5. Yeni audit

Yeni kalite kapisi:

- `scripts/level1_40_27_runtime_health_paperlab_store_audit.py`
- `docs/LEVEL1_40_27_RUNTIME_HEALTH_PAPERLAB_STORE_AUDIT.json`
- `docs/LEVEL1_40_27_RUNTIME_HEALTH_PAPERLAB_STORE_AUDIT.md`

40.27 blocker kontrolleri:

- `real_trade_safety_service_imports_get_last_paper_lab_run`
- `build_runtime_health_uses_paper_lab_store`
- `paper_lab_store_read_is_try_except_protected`
- `health_failure_does_not_break_endpoint`
- `last_paper_lab_includes_source_paper_lab_store`
- `fallback_to_old_fields_preserved`
- `runtime_health_username_priority_present`
- 40.20-40.26 status `ok`

## 6. Degisen dosyalar

- `backend/services/real_trade_safety_service.py`
- `scripts/level1_40_27_runtime_health_paperlab_store_audit.py`
- `docs/LEVEL1_40_27_RUNTIME_HEALTH_PAPERLAB_STORE_AUDIT.json`
- `docs/LEVEL1_40_27_RUNTIME_HEALTH_PAPERLAB_STORE_AUDIT.md`
- `docs/PACKAGE_10_12_RUNTIME_HEALTH_PAPERLAB_STORE.md`
- `README.md`
- `todo.md`

## 7. Test sonuclari

- `py -X pycache_prefix=.pycache_paket10_12 -m py_compile backend\services\real_trade_safety_service.py scripts\level1_40_27_runtime_health_paperlab_store_audit.py`: pass
- `py scripts\level1_40_27_runtime_health_paperlab_store_audit.py`: pass, `status=ok`, `build_runtime_health_uses_paper_lab_store=true`, `paper_lab_store_read_is_try_except_protected=true`, `last_paper_lab_includes_source_paper_lab_store=true`, `fallback_to_old_fields_preserved=true`
- `py scripts\level1_40_26_paperlab_hydration_stability_audit.py`: pass, `status=ok`
- `py scripts\level1_40_25_paperlab_persistence_audit.py`: pass, `status=ok`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, `missing_path_count=0`, `method_mismatch_count=0`, `true_blocker_count=0`
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `matched_call_count=94`, `missing_path_count=0`, `method_mismatch_count=0`
- `py -c "... monkeypatch get_last_paper_lab_run ..."`: pass, `last_paper_lab.source=paper_lab_store`, `state=ok`

Yerel workspace'te runtime `backend/paper_lab_store.json` yoktu; canli kabul testi VPS runtime store ile yapilmalidir.

## 8. Canli kabul testi

Deploy sonrasi:

```bash
curl -sS http://127.0.0.1:8000/health/ops
```

Beklenen:

- `last_paper_lab.state != missing`
- `last_paper_lab.source = paper_lab_store`
- `run_id`, `started_at`, `completed_at`, `status` alanlari gorunur

## 9. Paket 11'e gecis karari

Paket 11'e sadece 40.20-40.27 zinciri `ok` olduktan ve canli `/health/ops` ciktisinda mevcut Paper Lab run `source=paper_lab_store` ile gorundukten sonra gecilebilir.

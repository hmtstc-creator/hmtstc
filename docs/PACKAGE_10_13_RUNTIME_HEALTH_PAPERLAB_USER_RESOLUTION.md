# Paket 10.13 Runtime Health Paper Lab User Resolution

## 1. Paket amaci

Paket 10.13, `/health/ops` auth context tasimadiginda Paper Lab persistent store kullanicisini yanlis cozme sorununu giderir.

Canli store yapisi:

- `backend/paper_lab_store.json`
- `users.ahmet`

Paket 10.12 exact username ile store okuyordu. `/health/ops` username bulamayinca `admin` fallback'e dusebiliyor ve `users.ahmet` altindaki run'i kacirabiliyordu.

## 2. Store any-user reader

Yeni helper:

- `get_latest_paper_lab_run_any_user()`

Davranis:

- `paper_lab_store.json` icindeki `users` dict taranir.
- Tum kullanicilarin `runs` kayitlari incelenir.
- En guncel `completed_at` veya `started_at` timestamp'ine sahip run secilir.
- Donen payload icine `username` eklenir.

## 3. Runtime health cozumleme sirasi

`build_runtime_health` Paper Lab health bilgisini su sirayla cozer:

1. Username tespit edilebiliyorsa `get_last_paper_lab_run(username)`
2. Sonuc yoksa `get_latest_paper_lab_run_any_user()`
3. O da yoksa legacy fallback:
   - `last_paper_lab_tick`
   - `last_model_evaluation_at`
   - `paper_lab.last_run_at`

## 4. last_paper_lab ciktisi

Store'dan herhangi bir kullanicida run bulunursa:

```json
{
  "state": "ok",
  "seconds": 0,
  "fresh": true,
  "username": "ahmet",
  "started_at": "2026-06-11T22:12:22",
  "completed_at": "2026-06-11T22:12:24",
  "run_id": "...",
  "status": "completed",
  "source": "paper_lab_store"
}
```

Store bozuk veya okunamazsa health endpoint dusmez; Paket 10.12 exception-safe davranisi korunur.

## 5. Yeni audit

Yeni kalite kapisi:

- `scripts/level1_40_28_runtime_health_paperlab_user_resolution_audit.py`
- `docs/LEVEL1_40_28_RUNTIME_HEALTH_PAPERLAB_USER_RESOLUTION_AUDIT.json`
- `docs/LEVEL1_40_28_RUNTIME_HEALTH_PAPERLAB_USER_RESOLUTION_AUDIT.md`

40.28 blocker kontrolleri:

- `paper_lab_store_has_get_latest_any_user`
- `latest_any_user_scans_users_dict`
- `latest_any_user_returns_username`
- `build_runtime_health_uses_exact_username_first`
- `build_runtime_health_falls_back_to_any_user`
- `last_paper_lab_includes_username`
- `source_paper_lab_store_preserved`
- `legacy_fallback_preserved`
- `health_exception_safe`
- 40.20-40.27 status `ok`

## 6. Degisen dosyalar

- `backend/services/paper_lab_store.py`
- `backend/services/real_trade_safety_service.py`
- `scripts/level1_40_27_runtime_health_paperlab_store_audit.py`
- `scripts/level1_40_28_runtime_health_paperlab_user_resolution_audit.py`
- `docs/LEVEL1_40_27_RUNTIME_HEALTH_PAPERLAB_STORE_AUDIT.json`
- `docs/LEVEL1_40_27_RUNTIME_HEALTH_PAPERLAB_STORE_AUDIT.md`
- `docs/LEVEL1_40_28_RUNTIME_HEALTH_PAPERLAB_USER_RESOLUTION_AUDIT.json`
- `docs/LEVEL1_40_28_RUNTIME_HEALTH_PAPERLAB_USER_RESOLUTION_AUDIT.md`
- `docs/PACKAGE_10_13_RUNTIME_HEALTH_PAPERLAB_USER_RESOLUTION.md`
- `README.md`
- `todo.md`

## 7. Test sonuclari

- `py -X pycache_prefix=.pycache_paket10_13 -m py_compile backend\services\paper_lab_store.py backend\services\real_trade_safety_service.py scripts\level1_40_27_runtime_health_paperlab_store_audit.py scripts\level1_40_28_runtime_health_paperlab_user_resolution_audit.py`: pass
- `py scripts\level1_40_28_runtime_health_paperlab_user_resolution_audit.py`: pass, `status=ok`, `paper_lab_store_has_get_latest_any_user=true`, `build_runtime_health_falls_back_to_any_user=true`, `last_paper_lab_includes_username=true`, `legacy_fallback_preserved=true`
- `py scripts\level1_40_27_runtime_health_paperlab_store_audit.py`: pass, `status=ok`
- `py scripts\level1_40_26_paperlab_hydration_stability_audit.py`: pass, `status=ok`
- `py scripts\level1_40_09_missing_endpoint_report.py`: pass, `missing_path_count=0`, `method_mismatch_count=0`, `true_blocker_count=0`
- `py scripts\level1_40_08_api_contract_diff.py --strict`: pass, `matched_call_count=94`, `missing_path_count=0`, `method_mismatch_count=0`
- Any-user monkeypatch davranis testi: pass, `last_paper_lab.source=paper_lab_store`, `username=ahmet`, `state=ok`

## 8. Canli kabul testi

Deploy sonrasi:

```bash
curl --max-time 15 -sS http://127.0.0.1:8000/health/ops | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin).get('runtime_health',{}).get('last_paper_lab'), ensure_ascii=False, indent=2))"
```

Beklenen:

```json
{
  "state": "ok",
  "source": "paper_lab_store",
  "username": "ahmet",
  "started_at": "2026-06-11T22:12:22",
  "completed_at": "2026-06-11T22:12:24"
}
```

## 9. Paket 11'e gecis karari

Paket 11'e sadece 40.20-40.28 zinciri `ok` olduktan ve canli `/health/ops` ciktisinda Paper Lab run `source=paper_lab_store`, `username=ahmet` ile gorundukten sonra gecilebilir.

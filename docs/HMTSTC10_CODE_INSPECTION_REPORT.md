# HMTSTC10 Kod İnceleme Raporu

**Kaynak ZIP:** hmtstc10.zip  
**İnceleme zamanı:** 2026-06-15  
**Baseline:** `d4f06c7 dashboard6` -> `3bd86ec dashboard7`  
**Amaç:** Paket 20 için güvenilir kaynak baseline'ını dondurmak ve Blackbox kaynaklı eksik teslimleri üretim kodundan ayırmak.

## Kısa durum

1. Repo HEAD'i `3bd86ec dashboard7`; karşılaştırma baseline'ı `d4f06c7 dashboard6` olarak doğrulandı.
2. İki commit arasındaki fark tam olarak 8 dosya: iki Blackbox metni, beş audit/rapor değişikliği ve `frontend/js/pages/dashboard.js`.
3. Mevcut statik testlerde kritik Python/JS syntax hatası görülmedi.
4. Mevcut 39.x auditleri `level1_40_39_1`, `level1_40_39_2`, `level1_40_39_3` ve `level1_40_39_safe` Paket 20 kapısından çalıştırılır.
5. `level1_40_39_4_coinfilter_final_pipeline_contract_audit.py` ve vaat edilen iki rapor repo içinde yok. Blackbox 5.4 tamamlanmış veya güvenilir kabul edilmez.
6. Runtime/store/env dosyaları tracked veya staged listede bulunmadı; `.gitignore` genel runtime store ve env varyantlarını da kapsayacak şekilde sıkılaştırıldı.
5. CoinFilter sayfasında hâlâ `Sistem Sabit Korumaları` bölümü ve `RSI Periyodu` satırı görünüyor. Bunlar hedef sadeleştirme formatına aykırı.
6. Lightweight scan tarafında RSI değerleri hâlâ proxy/default 50 olarak üretilebiliyor; hacim artış çarpanı da gerçek previous volume kıyasından değil proxy davranıştan etkileniyor.
7. `filter_rejection_counts` hâlâ kümülatif reason mapping yaklaşımından etkileniyor. Hedefte bu alan unique sequential pipeline sonucu olmalı.
8. Dashboard network tarafında `passed === true` yönünde iyileştirme izleri var; buna rağmen aday handoff contract paket 26'da kesinleştirilmeli.

## İncelenen kritik dosyalar

- `frontend/js/pages/coinFilter.js`
- `frontend/js/pages/dashboard.js`
- `frontend/js/app/api.js`
- `backend/services/analysis_service.py`
- `backend/services/coin_universe_service.py`
- `backend/routes/bot_routes.py`
- `backend/routes/dashboard_routes.py`
- `backend/core/config.py`
- `backend/core/storage.py`

## Statik test durumu

Çalıştırılan kontroller:

```text
python3 -m py_compile backend/core/config.py backend/core/storage.py backend/routes/bot_routes.py backend/routes/dashboard_routes.py backend/services/analysis_service.py backend/services/coin_universe_service.py
node --check frontend/js/pages/coinFilter.js
node --check frontend/js/pages/dashboard.js
node --check frontend/js/app/api.js
python3 scripts/level1_40_39_3_coinfilter_settings_contract_audit.py
python3 scripts/level1_40_39_2_coinfilter_single_source_hydration_audit.py
python3 scripts/level1_40_39_safe_coinfilter_scan_and_counters_audit.py
```

Sonuç:

```text
Syntax check: OK
level1_40_39_1: OK
level1_40_39_2: OK
level1_40_39_3: OK
level1_40_39_safe: OK
level1_40_39_4: MISSING
```

## `d4f06c7..3bd86ec` değişiklik sınıflandırması

| Dosya grubu | Karar |
|---|---|
| `blackbox2.md`, `blackbox2_full.txt` | Yalnızca talep/metin kaydı; uygulama kanıtı değildir. |
| `frontend/js/pages/dashboard.js` | `passed === true` filtresi yönünde dar frontend değişikliği; sonraki paketlerde ayrıca doğrulanmalı. |
| 40.33 ve 40.39 audit çıktıları | Üretilmiş rapor değişiklikleri; kaynak implementasyon yerine geçmez. |
| Eksik 40.39.4 script ve raporları | Güvenilmez/teslim edilmemiş kabul edilir. Paket 20 bunları üretmez veya varsaymaz. |

## Baseline güvenlik kararı

- Paket 20 üretim backend, frontend karar mantığı veya canlı emir yolunu değiştirmez.
- Mevcut runtime state ve secret dosyaları kaynak ağacına alınmaz.
- Çalışma ağacındaki Paket 21-40 plan dosyaları ve önceden değişmiş 39.x raporları kullanıcı çalışması olarak korunur; Paket 20 bunları geri almaz.
- Tek komut kalite kapısı: `py scripts/level1_40_40_package_20_40_roadmap_audit.py`.
- Audit `OK` vermeden Paket 21 uygulamasına geçilmez.

## Paket 20-40 ilerleme kuralı

- Her paket kendi audit scriptini üretmeden tamamlanmış sayılmayacak.
- Her paket sonrası `git status -sb`, py_compile, ilgili JS syntax check ve paket audit çıktısı alınacak.
- Runtime/store/env dosyaları commitlenmeyecek.
- Canlı VPS'e geçmeden önce lokal audit ve dosya listesi kontrol edilecek.
- Paket 20-40 planı `docs/PACKAGE_20_40_MASTER_ROADMAP.md` içinde ana kaynak olarak tutulacak.

## En kritik mevcut riskler

1. **Blackbox sonrası commit riski:** `3bd86ec` ve ZIP working tree tam güvenilir kabul edilmemeli; Paket 20'de doğrulanmalı.
2. **CoinFilter karar riski:** UI'da görünen parametrelerin tamamı gerçek backend filtresine birebir bağlı değil.
3. **RSI riski:** Lightweight scan default/proxy RSI kullanıyor; gerçek işlem kararı için yeterli değil.
4. **Hacim artış riski:** `volume_growth_multiplier` gerçek previous volume kıyasıyla çalışmadan yanıltıcı sonuç verebilir.
5. **Pipeline sayım riski:** Kümülatif red sayıları unique coin sayısı gibi algılanırsa kullanıcı yanlış karar verir.
6. **Bot loop riski:** Botun açık görünmesi gerçek trade loop'un sağlıklı çalıştığı anlamına gelmiyor; Paket 29'da net runtime truth şart.

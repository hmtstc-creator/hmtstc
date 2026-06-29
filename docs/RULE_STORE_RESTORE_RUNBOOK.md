# Rule Store Restore Runbook

## Amaç

`backend/rule_store.json` canlı runtime veri dosyasıdır. Bu dosya bos gorunurse ve `backend/runtime_backups` icinde daha yuksek rule sayili bir yedek varsa sistem otomatik restore yapmaz. Restore sadece manuel owner/admin onayi ile yapilir.

## Ne Zaman Kullanilir?

Bu runbook su durumda kullanilir:

- Dashboard `Rule Store` satiri `0 filtre / 0 strateji` gosterir.
- `LEVEL1_40_15_SYSTEM_STATUS_RUNTIME_STORE_AUDIT` `empty_active_backup_blocker=true` doner.
- Audit raporu `backup_candidate` alaninda kullanilabilecek yedegi gosterir.

## Manuel Kontrol

1. Aktif dosyanin durumunu kontrol et:

```powershell
py scripts\level1_40_15_system_status_runtime_store_audit.py
```

2. Rapor dosyasinda su alanlari oku:

```text
docs/LEVEL1_40_15_SYSTEM_STATUS_RUNTIME_STORE_AUDIT.json
active_rule_store_total_rules
backup_max_rule_count
backup_candidate
empty_active_backup_blocker
```

3. `backup_candidate` dosyasini manuel incele. Rule sayisi, filtre/strateji dagilimi ve beklenen kullanici kaydi dogru degilse restore yapma.

4. Restore oncesi aktif dosyanin elle yedegini al. Aktif dosya yoksa bu adim sadece olay notu olarak kaydedilir.

5. Owner/admin onayi olmadan `backup_candidate` dosyasini `backend/rule_store.json` uzerine kopyalama.

## Restore Sonrasi Kontrol

Restore yapildiysa tekrar calistir:

```powershell
py scripts\level1_40_15_system_status_runtime_store_audit.py
py scripts\level1_40_13_rule_selection_persistence_audit.py
py scripts\level1_40_14_rule_backend_stability_audit.py
```

Beklenen:

- `active_rule_store_total_rules > 0`
- `empty_active_backup_blocker=false`
- 40.13 status `ok`
- 40.14 status `ok`

## Kurallar

- Otomatik restore yok.
- Runtime store dosyalari Git tarafindan takip edilmez.
- Restore islemi deploy scripti icine gomulmez.
- Binance, order executor, Futures veya real-trade dosyalari bu prosedurle degistirilmez.

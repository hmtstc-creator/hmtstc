# Paket 10.21.5 Revize 5.3 — CoinFilter Settings Contract

Amaç: CoinFilter scan sırasında kullanılan ayarların runtime içinde net görünmesini sağlamak ve son scan ile mevcut settings ayrımını deterministik yapmak.

## Kapsam

- `settings_store` hâlâ tek kaynak olarak kalır.
- `shadow_store.users.<user>.settings` sadece runtime mirror olarak güncellenir.
- `/api/dashboard/bundle` ve `/api/bot/last-scan` artık hem son scan ayar snapshotını hem mevcut settings snapshotını döndürür.
- Son scan farklı ayarlarla yapıldıysa `settings_changed_since_scan=true` olur.
- `scan_rows` artık `passed` boolean alanını taşır.
- `trade_count=0` veya minimum altı değerler artık düşük işlem adedi filtresinden kaçmaz.

## Kabul

- `backend/shadow_store.json -> users.<user>.settings.coin_filter` null kalmamalı.
- `last_scan.settings_snapshot.coin_filter` scan sırasında kullanılan değerleri göstermeli.
- `last_scan.current_settings_snapshot.coin_filter` mevcut kaydedilmiş değerleri göstermeli.
- `scan_rows[*].passed` true/false olmalı.
- CPU ve otomatik scan davranışına dokunulmadı.

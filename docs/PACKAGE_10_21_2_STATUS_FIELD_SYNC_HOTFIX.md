# Paket 10.21.2 Status Field Sync Hotfix

## Amac

Bot scan sonucu mevcutken `last_scan_time` alaninin bos kalmasini engeller. Bot status ve Dashboard bundle ayni scan zamanini kullanir.

## Davranis

- Her scan yaziminda `last_scan` ve `last_scan_time` birlikte guncellenir.
- `last_scan_time`, yeni scan icindeki `time` degerine birebir esitlenir.
- Legacy runtime state normalizasyonu eksik top-level alani `last_scan.time` ile onarir.
- `/api/bot/status` ve `/api/dashboard/bundle` nested scan time fallback kullanir.
- Bot gercekten calisiyor ve `last_scan.error` bos ise backend API durumu `online` kalir.
- Basarili bundle hidrasyonu eski frontend Backend API hata durumunu temizler.
- `requested_running`, `bot_running` ve `engine_status` runtime truth kaynagindan korunur.

## Test sonuclari

- `py -m py_compile ...`: pass
- `py scripts\level1_40_36_2_status_field_sync_hotfix_audit.py`: pass, `status=ok`

## Canli kabul

- `requested_running=true`, `bot_running=true`, `engine_status=running`
- `last_scan.time` ve `last_scan_time` dolu ve ayni
- Dashboard Backend API hata gostermiyor
- Coin tarama sonuclari gecikmeden geliyor

Canli scheduler ve Dashboard gorunumu deploy sonrasi kabul edilmelidir.

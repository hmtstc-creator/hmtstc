# Store Policy

## 1. Runtime Store Tanimi

Runtime store dosyalari VPS veya local calisma ortaminda olusan state, auth, audit, trade, settings ve credential verilerini tutar. Bu dosyalar kaynak kod degildir ve Git tarafindan takip edilmemelidir.

## 2. Example Store Tanimi

Example store dosyalari yalnizca sanitize edilmis placeholder degerler icerir. Deploy veya local kurulum icin dosya sekli gosterir, gercek kullanici, token, API key veya secret icermez.

## 3. Git'e Girmemesi Gereken Dosyalar

```text
backend/binance_credentials_store.json
backend/settings_store.json
backend/shadow_store.json
backend/auth_store.json
backend/rule_store.json
backend/audit_store.json
backend/real_trade_store.json
backend/*_store.runtime.json
backend/runtime_backups/
backend/*_backup_*.json
```

## 4. Git'te Kalabilecek Example Dosyalari

```text
backend/binance_credentials_store.example.json
backend/settings_store.example.json
backend/shadow_store.example.json
backend/.env.example
```

Bu dosyalar yalnizca placeholder degerler icermelidir.

## 5. Binance Credential Store Politikasi

backend/binance_credentials_store.json runtime-only dosyadir ve Git tarafindan takip edilmemelidir. Git icinde yalnizca backend/binance_credentials_store.example.json sanitize ornek dosyasi bulunabilir.

Runtime dosyasinda gercek credential varsa:

- Degerler dokumana veya loga acik yazilmaz.
- API key ve secret frontend'e plaintext donmez.
- Runtime dosyasi local/VPS izinleriyle korunur.
- Commit veya PR icine alinmaz.

## 6. Deploy Store Example Politikasi

`deploy/deploy.sh`, runtime settings ve shadow store dosyalari yoksa example dosyalardan baslatmayi dener. Bu nedenle asagidaki sanitize dosyalar repoda tutulur:

```text
backend/settings_store.example.json
backend/shadow_store.example.json
```

Varsayilan policy:

- `live_trading_default`: false
- `bot_enabled_default`: false
- `emergency_stop`: true

## 7. Secret Masking Kurali

Rapor, log ve dokumanlarda gercek secret yazilmaz. Gerekirse yalnizca maskeli gosterim kullanilir:

```text
api_key: abc***xyz
api_secret: ***MASKED***
token: ***MASKED***
```

## 8. Paket 2 Karari

Paket 2 ile credential-shaped tracked runtime store politikasi duzeltilmistir. `backend/binance_credentials_store.json` runtime-only kabul edilir, `.gitignore` tarafindan kapsanir ve repoda sanitize `backend/binance_credentials_store.example.json` kullanilir.

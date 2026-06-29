#!/bin/bash

set -Eeuo pipefail

PROJECT_DIR="/var/www/hmtstc"
BACKEND_DIR="$PROJECT_DIR/backend"
BACKUP_DIR="$BACKEND_DIR/runtime_backups"

echo "HMTSTC deploy başladı"

cd "$PROJECT_DIR"

echo "Dosya izinleri ön hazırlık"
sudo mkdir -p "$BACKUP_DIR"
sudo chown -R hmtstc:www-data "$BACKEND_DIR"
sudo chmod 750 "$BACKEND_DIR"
sudo chmod -R 770 "$BACKUP_DIR"

echo "Rev34 runtime backup hazırlanıyor"
python3 "$PROJECT_DIR/scripts/pre_deploy_backup.py" --label deploy || {
  echo "Rev34 pre-deploy backup başarısız"
  exit 1
}

echo "Backend venv kontrol ediliyor"

if [ ! -d "$BACKEND_DIR/venv" ]; then
  python3 -m venv "$BACKEND_DIR/venv"
fi

cd "$BACKEND_DIR"

source venv/bin/activate

echo "Python paketleri kontrol ediliyor"
pip install -r requirements.txt

echo "Runtime dosyaları kontrol ediliyor"

if [ ! -f "$BACKEND_DIR/settings_store.json" ] && [ -f "$BACKEND_DIR/settings_store.example.json" ]; then
  cp "$BACKEND_DIR/settings_store.example.json" "$BACKEND_DIR/settings_store.json"
fi

if [ ! -f "$BACKEND_DIR/shadow_store.json" ] && [ -f "$BACKEND_DIR/shadow_store.example.json" ]; then
  cp "$BACKEND_DIR/shadow_store.example.json" "$BACKEND_DIR/shadow_store.json"
fi

sudo touch "$BACKEND_DIR/.env"

echo "Runtime izinleri düzenleniyor"

sudo chown -R hmtstc:www-data "$BACKEND_DIR"
sudo chmod 750 "$BACKEND_DIR"
sudo chmod 640 "$BACKEND_DIR/.env"

sudo chmod 660 "$BACKEND_DIR/settings_store.json" 2>/dev/null || true
sudo chmod 660 "$BACKEND_DIR/shadow_store.json" 2>/dev/null || true
sudo chmod 660 "$BACKEND_DIR/auth_store.json" 2>/dev/null || true

sudo mkdir -p "$BACKUP_DIR"
sudo chown -R hmtstc:www-data "$BACKUP_DIR"
sudo chmod -R 770 "$BACKUP_DIR"

echo "Backend service dosyası güncelleniyor"
sudo cp "$PROJECT_DIR/deploy/hmtstc-backend.service" /etc/systemd/system/hmtstc-backend.service

echo "Systemd reload"
sudo systemctl daemon-reload

echo "Backend restart"
sudo systemctl restart hmtstc-backend.service

echo "Nginx config güncelleniyor"
sudo cp "$PROJECT_DIR/deploy/nginx.conf" /etc/nginx/sites-available/hmtstc-api

if [ ! -L /etc/nginx/sites-enabled/hmtstc-api ]; then
  sudo ln -s /etc/nginx/sites-available/hmtstc-api /etc/nginx/sites-enabled/hmtstc-api
fi

echo "Nginx test"
sudo nginx -t

echo "Nginx reload"
sudo systemctl reload nginx

echo "Webhook restart"
sudo systemctl restart hmtstc-webhook.service || true

echo "Rev34 post-deploy smoke kontrolü başlıyor"

if python3 "$PROJECT_DIR/scripts/post_deploy_check.py" --base-url http://127.0.0.1:8000 --offline; then
  echo "Rev34 offline deploy safety kontrolü başarılı"
else
  echo "Rev34 offline deploy safety kontrolü başarısız"
  exit 1
fi

for i in {1..15}; do
  if curl -m 5 -fsS http://127.0.0.1:8000/health && curl -m 5 -fsS http://127.0.0.1:8000/health/ops; then
    echo ""
    echo "HMTSTC Rev34 deploy tamam - real trading locked policy aktif"
    exit 0
  fi

  echo "Backend henüz hazır değil, tekrar deneniyor... $i"
  sleep 2
done

echo "Backend health/ops kontrolü başarısız"
exit 1


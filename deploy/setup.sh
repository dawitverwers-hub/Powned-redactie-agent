#!/bin/bash
# =============================================================================
# PowNed Redactie Platform — Server Setup Script
# Draai dit eenmalig op een verse Ubuntu 22.04 VPS als root
# Gebruik: bash setup.sh redactie.example.com admin@example.com
# =============================================================================

set -e

DOMAIN=${1:-"redactie.example.com"}
ADMIN_EMAIL=${2:-"admin@example.com"}
APP_DIR="/opt/powned"
APP_USER="powned"

echo ""
echo "============================================"
echo "  PowNed Redactie Platform — Setup"
echo "  Domein: $DOMAIN"
echo "============================================"
echo ""

# ── 1. Systeem updaten ────────────────────────────────────────────────────────
echo "▶ Systeem updaten..."
apt-get update -qq && apt-get upgrade -y -qq

# ── 2. Benodigde pakketten ───────────────────────────────────────────────────
echo "▶ Pakketten installeren..."
apt-get install -y -qq \
    python3 python3-pip python3-venv \
    nginx certbot python3-certbot-nginx \
    git curl wget unzip sqlite3 \
    chromium-browser chromium-chromedriver \
    ufw fail2ban

# ── 3. App-gebruiker aanmaken ────────────────────────────────────────────────
echo "▶ App-gebruiker aanmaken..."
useradd -r -s /bin/bash -m -d "$APP_DIR" "$APP_USER" 2>/dev/null || true

# ── 4. Code kopiëren ─────────────────────────────────────────────────────────
echo "▶ Code installeren..."
# Kopieer de geüploade bestanden (zie deploy instructies)
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# ── 5. Python venv & dependencies ───────────────────────────────────────────
echo "▶ Python-omgeving installeren..."
sudo -u "$APP_USER" bash -c "
  cd $APP_DIR
  python3 -m venv powned_venv
  source powned_venv/bin/activate
  pip install --quiet --upgrade pip
  pip install --quiet -r requirements.txt
  playwright install chromium
"

# ── 6. Nginx configureren ────────────────────────────────────────────────────
echo "▶ Nginx configureren..."
cp /tmp/powned-nginx.conf /etc/nginx/sites-available/powned
ln -sf /etc/nginx/sites-available/powned /etc/nginx/sites-enabled/powned
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# ── 7. SSL certificaat ───────────────────────────────────────────────────────
echo "▶ SSL-certificaat aanvragen ($DOMAIN)..."
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$ADMIN_EMAIL" --redirect

# ── 8. Systemd service ───────────────────────────────────────────────────────
echo "▶ Systemd service installeren..."
cp /tmp/powned.service /etc/systemd/system/powned.service
systemctl daemon-reload
systemctl enable powned
systemctl start powned

# ── 9. Cron voor pipeline + backup ───────────────────────────────────────────
echo "▶ Cron instellen (pipeline elk uur, backup elke nacht)..."
chmod +x "$APP_DIR/powned_refresh.sh" "$APP_DIR/backup.sh"
mkdir -p "$APP_DIR/data/backups"
(
  crontab -u "$APP_USER" -l 2>/dev/null
  echo "0 * * * * $APP_DIR/powned_refresh.sh >> $APP_DIR/data/cron.log 2>&1"
  echo "0 3 * * * $APP_DIR/backup.sh >> $APP_DIR/data/backup.log 2>&1"
) | crontab -u "$APP_USER" -

# ── 10. Firewall ─────────────────────────────────────────────────────────────
echo "▶ Firewall instellen..."
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# ── 11. Fail2ban ─────────────────────────────────────────────────────────────
systemctl enable fail2ban && systemctl start fail2ban

echo ""
echo "============================================"
echo "  ✓ Setup klaar!"
echo "  Platform: https://$DOMAIN"
echo "  Status:   systemctl status powned"
echo "  Logs:     journalctl -u powned -f"
echo "  Pipeline: $APP_DIR/data/cron.log"
echo "============================================"
echo ""

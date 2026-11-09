# PowNed Redactie Platform — Deployment Guide

## Wat je nodig hebt

- Een Hetzner-account: hetzner.com (€4/maand)
- Een subdomain: `redactie.example.com` → wijst naar het VPS-IP
- Je OpenAI API key (voor Pow Patrol)
- Je terminal + SSH

---

## Stap 1 — VPS aanmaken op Hetzner

1. Log in op hetzner.com → Cloud → New Project → "powned-redactie"
2. Create Server:
   - **Location**: Falkenstein (EU/GDPR)
   - **OS**: Ubuntu 22.04
   - **Type**: CX22 (2 vCPU, 4GB RAM) — €4.35/maand
   - **SSH key**: voeg je eigen public key toe
3. Noteer het IP-adres (bijv. `<server-ip>`)

---

## Stap 2 — DNS instellen

Ga naar je DNS-beheer (bijv. Cloudflare, TransIP, je domeinregistrar):

```
Type  Naam          Waarde
A     redactie      <server-ip>   (jouw VPS-IP)
```

Wacht 5-15 minuten tot het DNS propagated is.

---

## Stap 3 — Code uploaden naar de server

Vanuit je Mac, upload de hele projectmap:

```bash
# Vanuit de projectmap
rsync -avz --exclude 'powned_venv' --exclude 'node_modules' \
  --exclude '*.pyc' --exclude '__pycache__' \
  --exclude 'remotion-walkthrough' \
  ./ root@<server-ip>:/opt/powned/
```

---

## Stap 4 — .env aanmaken op de server

```bash
ssh root@<server-ip>

cat > /opt/powned/.env << 'EOF'
OPENAI_API_KEY=sk-...jouw-sleutel-hier...
PORT=5001
EOF
```

---

## Stap 5 — Setup script draaien

```bash
ssh root@<server-ip>

# Nginx config klaarzetten
cp /opt/powned/deploy/nginx.conf /tmp/powned-nginx.conf
# Pas het domein aan in de config:
sed -i 's/redactie.example.com/jouw-domein.nl/g' /tmp/powned-nginx.conf

# Systemd service klaarzetten
cp /opt/powned/deploy/powned.service /tmp/powned.service

# Setup draaien
bash /opt/powned/deploy/setup.sh redactie.example.com admin@example.com
```

Duurt ~5 minuten. Aan het einde staat de URL.

---

## Stap 6 — Gebruikers toevoegen

Voeg elk redactielid toe via het manage_users.py script:

```bash
ssh root@<server-ip>
cd /opt/powned

# Gebruiker toevoegen (genereert wachtwoord automatisch)
python3 manage_users.py add "Naam Achternaam" naam@example.com

# Overzicht
python3 manage_users.py list

# Wachtwoord resetten
python3 manage_users.py reset-password naam@example.com nieuwwachtwoord
```

---

## Dagelijks beheer

```bash
# Status controleren
systemctl status powned

# Logs bekijken
journalctl -u powned -f

# Pipeline handmatig triggeren
sudo -u powned /opt/powned/powned_refresh.sh

# Pipeline-log bekijken
tail -f /opt/powned/data/cron.log

# Server herstarten
systemctl restart powned
```

---

## Updates uitrollen

Wanneer je code-wijzigingen wilt deployen:

```bash
# Vanuit Mac — upload gewijzigde bestanden
rsync -avz --exclude 'powned_venv' --exclude 'node_modules' \
  --exclude '*.pyc' --exclude '__pycache__' \
  ./ root@<server-ip>:/opt/powned/

# Server herstarten
ssh root@<server-ip> systemctl restart powned
```

---

## Wat de server automatisch doet

- **Elk uur** (via cron): nieuws ophalen, scoren, ethiekcheck, feed herbouwen
- **Bij crash**: server herstart automatisch (systemd Restart=always)
- **SSL**: certbot vernieuwt het certificaat automatisch (90-daags)

---

## Monitoring instellen

### UptimeRobot — gratis, checkt elke 5 minuten

1. Maak een gratis account op **uptimerobot.com**
2. Add Monitor → HTTP(s)
3. URL: `https://redactie.example.com/health`
4. Alert when: status not 200
5. Vul je e-mailadres in → je krijgt een mail als de site plat gaat

De `/health` endpoint geeft HTTP 503 terug als de pipeline meer dan 3 uur oud is — UptimeRobot stuurt dan automatisch een alert.

---

### Push notificaties bij pipeline-fouten (ntfy.sh)

ntfy.sh is gratis, geen account nodig, werkt op telefoon.

**Eenmalig instellen:**

1. Bedenk een unieke naam, bijv. `powned-redactie-x7k2` (houd dit geheim)
2. Voeg toe aan `.env` op de server:
   ```
   NTFY_TOPIC=powned-redactie-x7k2
   ```
3. Installeer de **ntfy-app** op je telefoon (iOS/Android)
4. Abonneer op het topic: `powned-redactie-x7k2`

Als de pipeline faalt krijg je direct een pushmelding op je telefoon.

---

### Database backups

Worden automatisch elke nacht om 03:00 gemaakt.
Laatste 7 backups worden bewaard in `/opt/powned/data/backups/`.

Handmatige backup:
```bash
ssh root@VPS-IP "sudo -u powned /opt/powned/backup.sh"
```

Backup terugzetten:
```bash
ssh root@VPS-IP
systemctl stop powned
cp /opt/powned/data/backups/powned_YYYYMMDD_HHMM.db /opt/powned/data/powned.db
systemctl start powned
```

---

## Kosten overzicht

| Item | Kosten |
|---|---|
| Hetzner CX22 VPS | €4.35/maand |
| OpenAI API (Pow Patrol) | ~€5-15/maand afhankelijk van gebruik |
| Domein (indien nodig) | €10-15/jaar |
| **Totaal** | **~€10-20/maand** |

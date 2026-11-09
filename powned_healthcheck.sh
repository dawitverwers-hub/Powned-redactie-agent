#!/bin/bash
# powned_healthcheck.sh — Fallback watcher
#
# Logica:
#   1. Is de Flask server bereikbaar? Zo niet → herstart hem.
#   2. Is de database de afgelopen 2 uur bijgewerkt?
#      Zo niet → trigger de pipeline via /refresh (primair).
#   3. Is n8n actief? Zo niet → start n8n zodat de
#      ingebouwde cron-workflow als fallback kan overnemen.
#
# Draai via cron (elke 15 min):
#   */15 * * * * /bin/bash /path/to/powned_healthcheck.sh >> /tmp/powned_health.log 2>&1

SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
FLASK_URL="http://localhost:5001"
N8N_URL="http://localhost:5678"
DB="$SCRIPTS/data/powned.db"
LOG_PREFIX="[healthcheck $(date '+%H:%M:%S')]"

# ── 1. Flask server check ─────────────────────────────────────────
if ! curl -sf "$FLASK_URL" > /dev/null 2>&1; then
    echo "$LOG_PREFIX Flask niet bereikbaar — herstart..."
    PYTHONPATH="$SCRIPTS/src" "$SCRIPTS/powned_venv/bin/python3" \
        "$SCRIPTS/powned_server.py" &
    sleep 5
    curl -sf "$FLASK_URL" > /dev/null 2>&1 \
        && echo "$LOG_PREFIX Flask herstart OK" \
        || echo "$LOG_PREFIX Flask herstart MISLUKT"
else
    echo "$LOG_PREFIX Flask OK"
fi

# ── 2. Pipeline freshness check ───────────────────────────────────
# Kijk wanneer het laatste artikel is opgeslagen
LAATSTE=$(sqlite3 "$DB" \
    "SELECT strftime('%s','now') - strftime('%s', MAX(fetched_at)) FROM items;" \
    2>/dev/null)

# Als de DB ouder is dan 7200 seconden (2 uur) → trigger refresh
if [ -z "$LAATSTE" ] || [ "$LAATSTE" -gt 7200 ]; then
    echo "$LOG_PREFIX Database te oud ($LAATSTE sec) — trigger primaire refresh..."
    RESPONSE=$(curl -sf -X POST "$FLASK_URL/refresh" 2>&1)
    echo "$LOG_PREFIX Refresh response: $RESPONSE"
else
    echo "$LOG_PREFIX Pipeline vers ($LAATSTE sec geleden)"
fi

# ── 3. n8n fallback check ────────────────────────────────────────
if ! curl -sf "$N8N_URL" > /dev/null 2>&1; then
    echo "$LOG_PREFIX n8n niet actief — start als fallback..."
    PATH="$HOME/.npm-global/bin:/usr/local/bin:/usr/bin:/bin" \
    N8N_SECURE_COOKIE=false \
    N8N_PORT=5678 \
    N8N_LOG_LEVEL=warn \
        "$HOME/.npm-global/bin/n8n" start >> /tmp/n8n.log 2>&1 &
    echo "$LOG_PREFIX n8n fallback gestart (PID $!)"
else
    echo "$LOG_PREFIX n8n OK (fallback stand-by)"
fi

#!/bin/bash
# PowNed Redactie — Dagelijkse database backup
# Draait via cron: 0 3 * * * /opt/powned/backup.sh

SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
DB="$SCRIPTS/data/powned.db"
BACKUP_DIR="$SCRIPTS/data/backups"
DATE=$(date +%Y%m%d_%H%M)
BACKUP="$BACKUP_DIR/powned_$DATE.db"
LOG="$SCRIPTS/data/backup.log"
NTFY_TOPIC="${NTFY_TOPIC:-}"  # optioneel: push notificatie bij fout

mkdir -p "$BACKUP_DIR"

echo "[$(date '+%d-%m-%Y %H:%M')] Backup starten..." >> "$LOG"

if [ ! -f "$DB" ]; then
    echo "[$(date '+%d-%m-%Y %H:%M')] FOUT: database niet gevonden: $DB" >> "$LOG"
    [ -n "$NTFY_TOPIC" ] && curl -s -d "❌ PowNed backup GEFAALD: database niet gevonden" \
        "https://ntfy.sh/$NTFY_TOPIC" > /dev/null
    exit 1
fi

# SQLite hot backup (veilig terwijl server draait)
sqlite3 "$DB" ".backup '$BACKUP'"

if [ $? -eq 0 ]; then
    SIZE=$(du -h "$BACKUP" | cut -f1)
    echo "[$(date '+%d-%m-%Y %H:%M')] ✓ Backup geslaagd: $(basename $BACKUP) ($SIZE)" >> "$LOG"
else
    echo "[$(date '+%d-%m-%Y %H:%M')] FOUT: backup mislukt" >> "$LOG"
    [ -n "$NTFY_TOPIC" ] && curl -s -d "❌ PowNed backup GEFAALD op $(hostname)" \
        "https://ntfy.sh/$NTFY_TOPIC" > /dev/null
    exit 1
fi

# Bewaar alleen de laatste 7 backups
BACKUP_COUNT=$(ls "$BACKUP_DIR"/powned_*.db 2>/dev/null | wc -l)
if [ "$BACKUP_COUNT" -gt 7 ]; then
    ls -t "$BACKUP_DIR"/powned_*.db | tail -n +8 | xargs rm -f
    echo "[$(date '+%d-%m-%Y %H:%M')] Oude backups opgeruimd (bewaar 7 meest recente)" >> "$LOG"
fi

echo "[$(date '+%d-%m-%Y %H:%M')] Klaar. Backups aanwezig: $(ls $BACKUP_DIR/powned_*.db 2>/dev/null | wc -l)" >> "$LOG"

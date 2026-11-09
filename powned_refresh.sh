#!/bin/bash
# PowNed pipeline — haalt nieuwe artikelen op en herbouwt de feed

SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
# Gebruik werkende venv (Desktop-project heeft alle packages)
_DESKTOP_VENV="/path/to/Powned-redactie-agent/powned_venv/bin/python3"
_LOCAL_VENV="$SCRIPTS/powned_venv/bin/python3"
if [ -n "$PYTHON_BIN" ]; then
    PYTHON="$PYTHON_BIN"
elif "$_LOCAL_VENV" -c "import yaml" 2>/dev/null; then
    PYTHON="$_LOCAL_VENV"
elif [ -f "$_DESKTOP_VENV" ]; then
    PYTHON="$_DESKTOP_VENV"
else
    PYTHON="$_LOCAL_VENV"
fi
DATA_DIR="${FEED_DIR:-$SCRIPTS/data}"
LOG="${LOG_PATH:-$DATA_DIR/refresh.log}"
DB="sqlite:////$DATA_DIR/powned.db"
NTFY_TOPIC="${NTFY_TOPIC:-}"   # zet in .env voor push notificaties: NTFY_TOPIC=powned-redactie-abc

mkdir -p "$DATA_DIR"

# ── Hulpfuncties ──────────────────────────────────────────────────────────────
alert() {
    local msg="$1"
    echo "[$(date '+%d-%m-%Y %H:%M')] ⚠ ALERT: $msg" | tee -a "$LOG"
    if [ -n "$NTFY_TOPIC" ]; then
        curl -s \
            -H "Title: PowNed Pipeline Fout" \
            -H "Priority: high" \
            -H "Tags: warning,powned" \
            -d "$msg" \
            "https://ntfy.sh/$NTFY_TOPIC" > /dev/null 2>&1
    fi
}

run_step() {
    local num="$1"
    local total="$2"
    local label="$3"
    local cmd="$4"

    echo "▶ Stap $num/$total — $label..." | tee -a "$LOG"
    if ! eval "$cmd" >> "$LOG" 2>&1; then
        alert "Stap $num/$total gefaald: $label. Bekijk: $LOG"
        return 1
    fi
    return 0
}

# ── Start ────────────────────────────────────────────────────────────────────
echo "" >> "$LOG"
echo "=== Run: $(date '+%d-%m-%Y %H:%M:%S') ===" >> "$LOG"

cd "$SCRIPTS"

ERRORS=0

run_step 1 5 "Nieuws ophalen" \
    "DATABASE_URL=\"$DB\" PYTHONPATH=\"$SCRIPTS/src\" \"$PYTHON\" \"$SCRIPTS/src/main.py\"" \
    || ERRORS=$((ERRORS+1))

run_step 2 5 "Volledige tekst ophalen" \
    "DATABASE_URL=\"$DB\" PYTHONPATH=\"$SCRIPTS/src\" \"$PYTHON\" \"$SCRIPTS/enrich_content.py\"" \
    || ERRORS=$((ERRORS+1))

run_step 3 5 "Relevantie scoren" \
    "DATABASE_URL=\"$DB\" PYTHONPATH=\"$SCRIPTS/src\" \"$PYTHON\" \"$SCRIPTS/score_relevance.py\"" \
    || ERRORS=$((ERRORS+1))

run_step 4 5 "Ethische check (Agent 04)" \
    "DATABASE_URL=\"$DB\" PYTHONPATH=\"$SCRIPTS/src\" \"$PYTHON\" \"$SCRIPTS/agent04_ethics.py\"" \
    || ERRORS=$((ERRORS+1))

run_step 5 5 "Feed herbouwen" \
    "DATABASE_URL=\"$DB\" DB_PATH=\"$DATA_DIR/powned.db\" FEED_DIR=\"$DATA_DIR\" \"$PYTHON\" \"$SCRIPTS/powned_build.py\"" \
    || ERRORS=$((ERRORS+1))

# ── Resultaat ────────────────────────────────────────────────────────────────
if [ "$ERRORS" -eq 0 ]; then
    echo "✅ Pipeline klaar op $(date '+%H:%M:%S') — geen fouten" | tee -a "$LOG"
else
    alert "$ERRORS stap(pen) gefaald. Pipeline deels voltooid. Controleer $LOG"
    echo "⚠ Pipeline klaar met $ERRORS fout(en) op $(date '+%H:%M:%S')" | tee -a "$LOG"
    exit 1
fi

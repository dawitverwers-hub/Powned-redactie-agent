# PowNed Redactie Agent 🎬

Volledig geautomatiseerde nieuwspipeline voor de PowNed-redactie. Haalt nieuws op uit 32+ bronnen, beoordeelt relevantie met AI (Agent 02), voert ethische checks uit (Agent 04) en bouwt een visueel dashboard.

---

## 🏗️ Architectuur

```
RSS/Sitemap bronnen (32+)
        ↓
Agent 01 — Feed ophalen & opslaan (SQLite)
        ↓
Agent 02 — Relevantie scoren (GPT-4o-mini)
        ↓
Agent 04 — Ethische check (GPT-4o-mini)
        ↓
Agent 03 — Dashboard bouwen (HTML)
        ↓
powned_server.py — Flask API + live dashboard
```

---

## 🚀 Installatie

### 1. Python omgeving

```bash
python3 -m venv powned_venv
source powned_venv/bin/activate
pip install flask openai feedparser requests pyyaml python-dotenv loguru playwright
playwright install chromium
```

### 2. Environment variabelen

Maak een `.env` bestand aan in de root:

```env
OPENAI_API_KEY=sk-proj-...
DATABASE_URL=sqlite:///data/powned.db
```

### 2b. Dashboard users and password salt

Add `POWNED_SALT=<any long random string>` to your `.env` (see `.env.example`). It is used to hash dashboard passwords and is never stored in the code.
Users live in `config/users.json`, which is **not** part of this repository. Copy `config/users.example.json` to `config/users.json` and add people with:

```bash
python3 manage_users.py add "Name Surname" name@example.com
```

### 3. Database initialiseren

```bash
PYTHONPATH=src python src/main.py --init
```

### 4. Server starten

```bash
python powned_server.py
```

Dashboard draait op → **http://localhost:5001**

---

## 🔄 Pipeline handmatig draaien

```bash
# Alles in één keer (aanbevolen)
bash powned_refresh.sh

# Of stap voor stap:
PYTHONPATH=src python src/main.py          # Agent 01: feed ophalen
python score_relevance.py                  # Agent 02: scoren
python agent04_ethics.py                   # Agent 04: ethiekcheck
python powned_build.py                     # Agent 03: dashboard bouwen
```

### Volledige ethiekcheck (alle artikelen)
```bash
ETHICS_MAX=9999 PYTHONPATH=src python agent04_ethics.py
```

---

## 🤖 n8n Workflow automatisering

De complete pipeline draait automatisch elk uur via n8n. Het bestand `powned_n8n_workflow.json` bevat de volledige workflow — klaar om te importeren.

### n8n installeren

```bash
# Zet npm prefix naar user-writable locatie (eenmalig)
mkdir -p ~/.npm-global
npm config set prefix '~/.npm-global'
export PATH=~/.npm-global/bin:$PATH

# Installeer n8n
npm install -g n8n --cache /tmp/npm-cache
```

### n8n starten

```bash
N8N_SECURE_COOKIE=false N8N_PORT=5678 n8n start
```

Open n8n → **http://localhost:5678**

### Account aanmaken (eerste keer)

Vul in:
- Email: kies zelf (bijv. `redactie@example.com`)
- Wachtwoord: kies zelf

### Workflow importeren

```bash
n8n import:workflow --input=powned_n8n_workflow.json
```

### OpenAI key instellen in de workflow

Na het importeren moet je je eigen OpenAI key invullen:

1. Open n8n → ga naar de workflow
2. Klik op de node **🤖 Agent 02 — Scoren**
3. Zoek in de `body` het stuk `Bearer JOUW_OPENAI_KEY_HIER`
4. Vervang `JOUW_OPENAI_KEY_HIER` door jouw eigen `sk-proj-...` key
5. Doe hetzelfde bij **🔍 Agent 04 — Ethiek**
6. Sla op (Cmd+S)

### Workflow activeren

- Rechtsboven in de workflow: toggle **Inactive → Active**
- De pipeline draait dan automatisch elk uur
- Of klik **Execute Workflow** (▶) voor een handmatige run

> ⚠️ Zorg dat `powned_server.py` draait op `localhost:5001` voordat je de workflow start — n8n communiceert via die API.

---

## 📁 Bestandsstructuur

```
powned_scripts/
├── powned_server.py        # Flask server + API endpoints
├── powned_build.py         # Dashboard HTML genereren (Agent 03)
├── powned_refresh.sh       # Volledige pipeline shell script
├── agent04_ethics.py       # Ethische check Agent 04
├── score_relevance.py      # Relevantie scoring Agent 02
├── enrich_content.py       # Content verrijking
├── powned_web.py           # Web scraper helpers
├── powned_n8n_workflow.json # n8n workflow (importeerbaar)
├── config/
│   └── sources.yml         # RSS/Sitemap bronnen (32+)
└── src/
    ├── main.py             # Agent 01: feed ophalen
    ├── sources/            # RSS, sitemap, playwright scrapers
    ├── storage/            # SQLite database layer
    └── paywall/            # Paywall bypass helpers
```

---

## 🗄️ Database schema

SQLite database in `data/powned.db`:

| Kolom | Type | Beschrijving |
|-------|------|-------------|
| url | TEXT PK | Artikel URL |
| title | TEXT | Koptekst |
| source | TEXT | Bron naam |
| content | TEXT | Samenvatting |
| full_content | TEXT | Volledige tekst |
| relevance_score | INTEGER | 0-100 PowNed-fit score |
| prioriteit | TEXT | must-have/sterk/interessant/zwak/afwijzen |
| ethics_verdict | TEXT | GROEN/ORANJE/ROOD |
| ethics_score | INTEGER | 0-100 ethiek score |
| ethics_report | TEXT | JSON rapport met 7 indicatoren |
| published_at | TEXT | Publicatiedatum |
| fetched_at | TEXT | Ophaaldatum |

---

## 🌐 API Endpoints

De server biedt een REST API voor n8n en andere integraties:

| Methode | Endpoint | Beschrijving |
|---------|----------|-------------|
| GET | `/` | Dashboard |
| GET | `/api/sources` | Alle bronnen uit sources.yml |
| GET | `/api/items/pending-score` | Items zonder score |
| GET | `/api/items/pending-ethics` | Items zonder ethiekcheck |
| POST | `/api/items/check` | Duplicaat check op URL/hash |
| POST | `/api/items/save` | Nieuw item opslaan |
| POST | `/api/items/update-score` | Batch scores opslaan |
| POST | `/api/items/update-ethics` | Batch ethiek opslaan |
| POST | `/api/rebuild` | Dashboard herbouwen |
| POST | `/ethics-check` | On-demand ethiekcheck per artikel |
| POST | `/chat` | Chat met redactie-AI |

---

## 👥 Voor collega's

1. Clone de repo
2. Maak `.env` aan met je eigen `OPENAI_API_KEY`
3. Volg de installatiesstappen hierboven
4. Start de server: `python powned_server.py`
5. Open het dashboard: http://localhost:5001

Voor n8n: installeer n8n, importeer `powned_n8n_workflow.json` en voeg je OpenAI key toe als credential.

---

## 🔧 Auto-start (macOS LaunchAgent)

De server en n8n starten automatisch bij inloggen via LaunchAgents:
- `~/Library/LaunchAgents/local.powned.plist` — PowNed server
- `~/Library/LaunchAgents/local.n8n.plist` — n8n

Herstarten na config wijziging:
```bash
launchctl stop local.powned && launchctl stop local.n8n
# Wacht 3 seconden — ze starten automatisch opnieuw
```

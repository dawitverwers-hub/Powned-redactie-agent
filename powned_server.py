"""PowNed feed server — serveert de feed en kan de pipeline triggeren via /refresh."""

import hashlib
import json
import os
import sqlite3
import subprocess
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from pathlib import Path

ROOT      = Path(__file__).resolve().parent
PORT      = int(os.environ.get("PORT", 5001))
FEED_DIR  = Path(os.environ.get("FEED_DIR", str(ROOT / "data" / "dashboard")))
FEED_DIR.mkdir(parents=True, exist_ok=True)
SCRIPT    = ROOT / "powned_refresh.sh"
DB_PATH   = Path(os.environ.get("DB_PATH", str(ROOT / "data" / "powned.db")))

# Laad .env bestand als de key nog niet in de omgeving staat
def _load_env():
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            if key.strip() not in os.environ:
                os.environ[key.strip()] = val.strip()

_load_env()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

_status = {"running": False, "last": None, "log": []}
_lock   = threading.Lock()

CHAT_SYSTEM = """# Pow Patrol — PowNed Redactie-assistent

## Identiteit
Je naam is **Pow Patrol**. Je bent de interne AI-assistent van de PowNed-redactie. Je naam is een woordspeling op PowNed ("Pow") en het idee dat je de nieuwsfeed bewaakt en patrouilleert ("Patrol"). Je bent geen generieke chatbot — je bent specifiek getraind op de PowNed-werkwijze, de feed-architectuur en het redactionele DNA van de zender.

Je spreekt altijd Nederlands. Je toon is direct, nuchter en collegiaal — alsof je een ervaren redacteur bent die naast iemand zit, niet een robot die instructies uitvoert.

---

## Realtime context
- **Datum & tijd:** {now}
- **Feed:** {feed_stats}

---

## PowNed — Redactioneel DNA
PowNed is een Nederlandse nieuwszender voor het jonge, kritische publiek (18–35 jaar). De zender kiest bewust voor nieuws dat confronteert, verbaast of prikkelt — niet voor het grijze midden.

**Wat scoort hoog bij PowNed:**
- Viraal nieuws en social media-verhalen met maatschappelijke lading
- Misdaad, geweld, rechtszaken — als er een duidelijk verhaal aan zit
- Politiek schandaal, hypocrisie, macht versus volk
- Opmerkelijke menselijke verhalen (absurd, indrukwekkend, herkenbaar)
- Protest, staking, actie — zeker als er beeld bij is
- Regionaal nieuws met landelijke potentie

**Wat PowNed niet doet:**
- Saaie beleidsnieuws zonder haak
- Puur institutioneel nieuws (vergaderingen, rapporten)
- Buitenlands nieuws zonder Nederlandse relevantie
- Nieuws dat moreel oordeelt zonder entertainment-waarde

---

## De Relevantiescore (0–100)
Elk artikel krijgt een AI-score op basis van vijf criteria:

| Criterium | Max | Wat het meet |
|---|---|---|
| Viraal potentieel | 25 | Kans op doorvertellen, shares, discussie |
| Visuele vertaalbaarheid | 25 | Heeft het beeld, video, of sterke visual? |
| Nieuwswaarde | 20 | Is het feitelijk nieuws, niet oud of irrelevant? |
| Landelijk bereik | 20 | Relevant buiten de directe regio? |
| Doelgroepfit (18–35) | 10 | Past het bij het PowNed-publiek? |

**Prioriteitsdrempels:**
- **Must-have** (70–100): Vandaag behandelen. Geen excuus om dit te missen.
- **Should-have** (45–69): Sterk artikel, maar niet urgent.
- **Nice-to-have** (<45): Kan interessant zijn, maar verdrinkt snel.

---

## Het PowNed Redactie Platform — Architectuur
Je weet alles van dit systeem en kunt technische vragen volledig beantwoorden.

**Stack:**
- Backend: Python 3 — `powned_server.py` (HTTP-server op poort 5001)
- Database: SQLite — `data/powned.db` (één bestand, alle tabellen)
- Build: `powned_build.py` — genereert de volledige feed-HTML uit de database
- Frontend: Statische HTML/CSS/JS, gegenereerd door de build

**Database-tabellen:**
- `items` — alle artikelen (url, title, source, region, city, published_at, relevance_score, score_breakdown, prioriteit, ethics_verdict, human_label)
- `editorial_labels` — redactionele keuzes per gebruiker (favoriet/interessant/overslaan)
- `agenda_events` — protesten en stakingen (handmatig + automatisch herkend)
- `editorial_rules` — geleerde regels vanuit de chat (actief/inactief)
- `chat_messages` — volledige chatgeschiedenis

**Feed-logica:**
- Alleen artikelen jonger dan 3 dagen verschijnen in de actieve feed
- Oudere artikelen blijven in de database, niet in de feed
- De build filtert, sorteert en scoort — output is een statische HTML
- De server serveert de HTML en handelt API-calls af

**Functionaliteiten:**
- 🔥 Feed — gesorteerd op prioriteit, filterbaar op bron, stad, ethiek, relevantiescore
- 🗺️ Kaart — artikelen gepind per stad op een interactieve Nederlandse kaart (Leaflet.js + CartoDB Dark)
- 📅 Agenda — automatische detectie van protest-keywords + handmatige events
- 📚 Archief — persoonlijk archief van gelabelde artikelen per redacteur
- ❓ Uitleg — uitlegpagina over het systeem in gewone taal
- 🤖 Pow Patrol — jij, deze chatbot, als floating panel in de feed

**API-endpoints (allemaal op poort 5001):**
- `GET /` — de feed (statische HTML)
- `GET /api/feed` — JSON feed met filters
- `GET /api/status` — pipeline-status + artikel-telling
- `GET /api/archief?user=email` — gelabelde artikelen per gebruiker
- `GET /api/agenda` — agenda-events (auto + handmatig)
- `POST /label` — artikel labelen (favoriet/interessant/overslaan)
- `POST /chat` — jij, Pow Patrol
- `POST /search` — artikelen zoeken in de database
- `GET /refresh` — pipeline triggeren (nieuwe artikelen ophalen + scoren)

---

## Redactionele regels (geleerd van deze redactie)
{rules}

---

## Commando's — gebruik ze proactief
Je hebt directe toegang tot acties in het platform. Gebruik ze zonder dat de gebruiker erom hoeft te vragen als de situatie erom vraagt.

```
WEB_ZOEK: [zoekterm]
```
→ Zoekt actuele informatie op het web. Gebruik dit automatisch als je iets niet weet, als een artikel context mist, of als iemand vraagt wat er nu speelt rond een onderwerp.

```
FAVORIET: [volledige URL]
```
→ Slaat een artikel op als favoriet in het archief van de gebruiker. Gebruik alleen als de gebruiker dit expliciet vraagt.

```
ZOEK: [zoekterm]
```
→ Doorzoekt de actieve feed. Gebruik dit als iemand vraagt of er iets over een onderwerp in de feed zit.

```
VOORSTEL_REGEL: [concrete regel]
```
→ Stelt een nieuwe redactionele regel voor die opgeslagen kan worden. Gebruik dit als je een patroon herkent in wat de redactie relevant vindt.

**Technische vereiste:** Zet commando's altijd op een EIGEN REGEL aan het EINDE van je antwoord — nooit midden in de tekst.

---

## Gedragsregels

**Toon:**
- Informeel, direct, geen onnodig jargon
- Geen "Zeker!" of "Natuurlijk!" als openingszin — ga direct to the point
- Gebruik "je" en "jij", niet "u"

**Lengte:**
- Redactionele vraag over één artikel → 2–3 zinnen, altijd met een concreet oordeel (wel/niet PowNed-waardig, waarom)
- Strategische redactionele vraag → zo lang als nodig, maar geen padding
- Technische vraag over het platform → volledig antwoord, gebruik opsommingen en code-blokken waar het helpt
- Algemene nieuwsvraag → bondig, gebruik WEB_ZOEK als je actuele info nodig hebt

**Als je het niet weet:**
- Gebruik WEB_ZOEK — gok niet
- Zeg het als je iets niet zeker weet, maar geef daarna alsnog een richting aan"""


# ── Auth helpers ────────────────────────────────────────────────────────────
USERS_FILE = ROOT / "config" / "users.json"

def _load_users():
    try:
        return json.loads(USERS_FILE.read_text())
    except Exception:
        return {"allowed_domains": ["powned.nl","powned.tv"], "users": []}

def _hash_pw(pw: str) -> str:
    salt = os.environ.get("POWNED_SALT")
    if not salt:
        raise RuntimeError("Set POWNED_SALT in your .env (any long random string)")
    return hashlib.sha256(f"{salt}{pw}".encode()).hexdigest()

def _verify_login(email: str, password: str):
    cfg = _load_users()
    domain = email.split("@")[-1].lower() if "@" in email else ""
    if domain not in cfg.get("allowed_domains", []):
        return None, "Alleen PowNed e-mailadressen zijn toegestaan."
    pw_hash = _hash_pw(password)
    for u in cfg.get("users", []):
        if u["email"].lower() == email.lower() and u["password_hash"] == pw_hash:
            return u, None
    return None, "Onjuist e-mailadres of wachtwoord."

# ── Protest keywords voor agenda ─────────────────────────────────────────────
PROTEST_KW = [
    "protest", "demonstratie", "staking", "betoging", "protestmars",
    "blokkade", "manifestatie", "sit-in", "bezetting", "boycot", "staker",
    "actievoerder", "actiedag", "vakbond", "vakbonden", "fnv", "cnv",
    "klimaatmars", "klimaatprotest", "boerenprotest",
]

def _protest_where():
    conds = " OR ".join(f"LOWER(title) LIKE '%{k}%'" for k in PROTEST_KW)
    return f"({conds})"

def _db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    # Zorg dat tabellen bestaan
    conn.execute("""CREATE TABLE IF NOT EXISTS editorial_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        active INTEGER DEFAULT 1
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS editorial_labels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        url TEXT NOT NULL,
        title TEXT,
        source TEXT,
        image_url TEXT,
        relevance_score INTEGER,
        ethics_verdict TEXT,
        label TEXT NOT NULL,
        note TEXT DEFAULT '',
        user_email TEXT,
        user_name TEXT,
        labeled_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(url, user_email)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS agenda_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        event_date TEXT NOT NULL,
        location TEXT DEFAULT '',
        event_type TEXT DEFAULT 'overig',
        source_url TEXT DEFAULT '',
        auto_detected INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS chat_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    return conn


def run_pipeline():
    with _lock:
        _status["running"] = True
        _status["log"] = []
    try:
        proc = subprocess.Popen(
            ["bash", str(SCRIPT)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        for line in proc.stdout:
            line = line.rstrip()
            with _lock:
                _status["log"].append(line)
        proc.wait()
        with _lock:
            _status["last"] = "success" if proc.returncode == 0 else "error"
    except Exception as e:
        with _lock:
            _status["last"] = f"error: {e}"
    finally:
        with _lock:
            _status["running"] = False


def web_search(query: str) -> str:
    """Zoek extra context via DuckDuckGo Instant Answers."""
    try:
        import urllib.parse
        url = ("https://api.duckduckgo.com/?q=" + urllib.parse.quote(query)
               + "&format=json&no_html=1&skip_disambig=1&no_redirect=1")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read())
        parts = []
        if data.get("AbstractText"):
            parts.append(data["AbstractText"][:400])
        for item in data.get("RelatedTopics", [])[:4]:
            if isinstance(item, dict) and item.get("Text"):
                parts.append(item["Text"][:200])
        return "\n".join(parts)
    except Exception:
        return ""


def call_openai(system: str, messages: list, max_tokens: int = 1000) -> str:
    """Roep OpenAI API aan en geef de reply terug."""
    try:
        import urllib.request
        payload = json.dumps({
            "model": "gpt-4o",
            "messages": [{"role": "system", "content": system}] + messages,
            "max_tokens": max_tokens,
            "temperature": 0.65,
        }).encode()
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPENAI_API_KEY}",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[Fout bij AI-verbinding: {e}]"


def _feed_stats() -> str:
    """Haal actuele feed-statistieken op voor Pow Patrol context."""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        total     = conn.execute("SELECT COUNT(*) FROM items WHERE published_at >= datetime('now','-3 days')").fetchone()[0]
        must_have = conn.execute("SELECT COUNT(*) FROM items WHERE prioriteit='must-have' AND published_at >= datetime('now','-3 days')").fetchone()[0]
        labeled   = conn.execute("SELECT COUNT(*) FROM editorial_labels").fetchone()[0]
        last_row  = conn.execute("SELECT MAX(fetched_at) FROM items").fetchone()
        top_must  = conn.execute(
            "SELECT title, source FROM items WHERE prioriteit='must-have' "
            "AND published_at >= datetime('now','-1 day') ORDER BY relevance_score DESC LIMIT 3"
        ).fetchall()
        conn.close()
        age_min = 999
        if last_row and last_row[0]:
            from datetime import datetime
            try:
                last    = datetime.fromisoformat(last_row[0].replace("Z",""))
                age_min = int((datetime.utcnow() - last).total_seconds() / 60)
            except Exception:
                pass
        top_str = " | ".join(f"\"{r['title'][:50]}\" ({r['source']})" for r in top_must) if top_must else "geen"
        return (f"{total} artikelen in feed (laatste 3 dagen), {must_have} must-have, "
                f"{labeled} gelabeld door redactie. Pipeline: {age_min} min geleden. "
                f"Top must-haves vandaag: {top_str}")
    except Exception:
        return "Feed-stats tijdelijk niet beschikbaar."


# Chat gebruikt GPT-4o (OpenAI) — bewuste keuze: sneller en goedkoper dan Claude Opus
# voor korte redactionele Q&A. De rest van de pipeline (scoring, ethiek) draait los.
# Omschakelbaar via OPENAI_API_KEY in .env.

def web_search_improved(query: str) -> str:
    """DDG Instant Answers API — officieel en stabiel, geen HTML-scraping."""
    import urllib.parse
    try:
        url = ("https://api.duckduckgo.com/?q=" + urllib.parse.quote(query)
               + "&format=json&no_html=1&skip_disambig=1&no_redirect=1")
        req = urllib.request.Request(url, headers={"User-Agent": "PowNed-Redactie/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        results = []
        if data.get("Answer"):
            results.append(f"Direct: {data['Answer']}")
        if data.get("AbstractText"):
            src = data.get("AbstractSource", "Wikipedia")
            results.append(f"[{src}] {data['AbstractText'][:500]}")
        for item in data.get("RelatedTopics", [])[:4]:
            if isinstance(item, dict) and item.get("Text"):
                results.append(f"• {item['Text'][:200]}")
        return "\n".join(results) if results else ""
    except Exception:
        return ""


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTP server zodat chat-calls de server niet blokkeren."""
    daemon_threads = True


class Handler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"   # Safari fetch vereist HTTP/1.1

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FEED_DIR), **kwargs)

    def end_headers(self):
        self.send_header("ngrok-skip-browser-warning", "true")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length))

    def do_POST(self):
        # ── /api/auth/login ─────────────────────────────────
        if self.path == "/api/auth/login":
            try:
                data  = self._body()
                email = data.get("email", "").strip().lower()
                pw    = data.get("password", "")
                user, err = _verify_login(email, pw)
                if user:
                    self._json({"status": "ok", "user": {"email": user["email"], "name": user["name"], "role": user.get("role","redacteur")}})
                else:
                    self._json({"status": "error", "message": err})
            except Exception as e:
                self._json({"status": "error", "message": str(e)})

        # ── /api/agenda/add ─────────────────────────────────
        elif self.path == "/api/agenda/add":
            try:
                data  = self._body()
                conn  = _db()
                conn.execute(
                    "INSERT INTO agenda_events (title, event_date, location, event_type, source_url, auto_detected) VALUES (?,?,?,?,?,0)",
                    (data.get("title",""), data.get("event_date",""), data.get("location",""), data.get("event_type","overig"), data.get("source_url",""))
                )
                conn.commit()
                conn.close()
                self._json({"status": "ok"})
            except Exception as e:
                self._json({"status": "error", "message": str(e)})

        # ── /api/agenda/delete ──────────────────────────────
        elif self.path == "/api/agenda/delete":
            try:
                data = self._body()
                conn = _db()
                conn.execute("DELETE FROM agenda_events WHERE id=? AND auto_detected=0", (data.get("id"),))
                conn.commit(); conn.close()
                self._json({"status": "ok"})
            except Exception as e:
                self._json({"status": "error", "message": str(e)})

        # ── /label ─────────────────────────────────────────
        elif self.path == "/label":
            try:
                data       = self._body()
                url        = data.get("url", "").strip()
                label      = data.get("label", "").strip()
                user_email = data.get("user_email", "").strip()
                user_name  = data.get("user_name", "").strip()
                note       = data.get("note", "").strip()
                if url and label in ("interessant", "overslaan", "favoriet"):
                    conn = _db()
                    conn.execute("UPDATE items SET human_label = ? WHERE url = ?", (label, url))
                    item = conn.execute(
                        "SELECT title, source, image_url, relevance_score, ethics_verdict FROM items WHERE url=?",
                        (url,)
                    ).fetchone()
                    conn.execute("""
                        INSERT INTO editorial_labels
                            (url, title, source, image_url, relevance_score, ethics_verdict, label, note, user_email, user_name)
                        VALUES (?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(url, user_email) DO UPDATE
                            SET label=excluded.label, note=excluded.note, labeled_at=CURRENT_TIMESTAMP
                    """, (
                        url,
                        item["title"]          if item else "",
                        item["source"]         if item else "",
                        item["image_url"]      if item else "",
                        item["relevance_score"] if item else 0,
                        item["ethics_verdict"] if item else "",
                        label, note, user_email, user_name
                    ))
                    conn.commit()
                    conn.close()
                    self._json({"status": "ok", "label": label})
                else:
                    self._json({"status": "error", "msg": "ongeldige url of label"})
            except Exception as e:
                self._json({"status": "error", "msg": str(e)})

        # ── /chat ───────────────────────────────────────────
        elif self.path == "/chat":
            try:
                from datetime import datetime as _dt
                data    = self._body()
                message = data.get("message", "").strip()
                article = data.get("article", {})
                history = data.get("history", [])

                if not message:
                    self._json({"error": "leeg bericht"}); return

                conn  = _db()
                rules = conn.execute(
                    "SELECT rule FROM editorial_rules WHERE active=1 ORDER BY created_at DESC LIMIT 30"
                ).fetchall()
                conn.execute("INSERT INTO chat_messages (role, content) VALUES ('user', ?)", (message,))
                conn.commit()
                conn.close()

                rules_text = "\n".join(f"- {r['rule']}" for r in rules) if rules else "Nog geen redactionele regels opgeslagen."
                now_str    = _dt.now().strftime("%A %d %B %Y, %H:%M")
                stats_str  = _feed_stats()

                system = CHAT_SYSTEM.format(
                    rules=rules_text,
                    now=now_str,
                    feed_stats=stats_str,
                )

                msgs = []
                for h in history[-14:]:
                    if h.get("role") in ("user", "assistant") and h.get("content"):
                        msgs.append({"role": h["role"], "content": h["content"]})

                if article:
                    ctx = (f"\n\n[Huidig artikel in context: \"{article.get('title','')}\" "
                           f"| Bron: {article.get('source','')} "
                           f"| Score: {article.get('score','')} "
                           f"| Prioriteit: {article.get('prioriteit','')} "
                           f"| Samenvatting: {article.get('summary','')[:400]}]")
                    message = message + ctx

                msgs.append({"role": "user", "content": message})

                reply = call_openai(system, msgs)

                # ── WEB_ZOEK: officiële DDG API, eerlijke fallback als leeg
                if "WEB_ZOEK:" in reply:
                    parts      = reply.split("WEB_ZOEK:", 1)
                    pre_reply  = parts[0].strip()
                    web_query  = parts[1].strip().split("\n")[0].strip()
                    web_result = web_search_improved(web_query)
                    msgs.append({"role": "assistant",
                                 "content": pre_reply + f"\n[zoekopdracht: '{web_query}']"})
                    if web_result:
                        msgs.append({"role": "user",
                                     "content": f"Webresultaten:\n{web_result}\n\nGeef nu een antwoord."})
                    else:
                        msgs.append({"role": "user",
                                     "content": ("De websearch gaf geen resultaten. "
                                                 "Geef antwoord op basis van je eigen kennis "
                                                 "en vermeld expliciet dat je geen actuele webinfo had.")})
                    reply = call_openai(system, msgs)

                # ── FAVORIET detecteren
                favorite_url = None
                if "FAVORIET:" in reply:
                    parts        = reply.split("FAVORIET:", 1)
                    reply        = parts[0].strip()
                    favorite_url = parts[1].strip().split("\n")[0].strip()
                    if not favorite_url.startswith("http"):
                        favorite_url = None

                # ── ZOEK: artikel-zoekopdracht
                search_query = None
                if "ZOEK:" in reply:
                    parts        = reply.split("ZOEK:", 1)
                    reply        = parts[0].strip()
                    search_query = parts[1].strip().split("\n")[0].strip()

                # ── VOORSTEL_REGEL
                proposed_rule = None
                if "VOORSTEL_REGEL:" in reply:
                    parts         = reply.split("VOORSTEL_REGEL:", 1)
                    reply         = parts[0].strip()
                    proposed_rule = parts[1].strip()

                # Sla antwoord op in geschiedenis
                conn = _db()
                conn.execute("INSERT INTO chat_messages (role, content) VALUES ('assistant', ?)", (reply,))
                conn.commit()
                conn.close()

                self._json({"reply": reply, "proposed_rule": proposed_rule,
                            "search_query": search_query, "favorite_url": favorite_url})

            except Exception as e:
                self._json({"error": str(e)})

        # ── /rules POST (sla regel op) ──────────────────────
        elif self.path == "/rules":
            try:
                data = self._body()
                rule = data.get("rule", "").strip()
                if len(rule) < 10:
                    self._json({"ok": False, "msg": "Regel te kort (minimaal 10 tekens)"}); return
                if len(rule) > 300:
                    self._json({"ok": False, "msg": "Regel te lang (maximaal 300 tekens)"}); return
                conn  = _db()
                # Voorkom exacte duplicaten
                exists = conn.execute(
                    "SELECT id FROM editorial_rules WHERE rule=? AND active=1", (rule,)
                ).fetchone()
                if exists:
                    conn.close()
                    self._json({"ok": False, "msg": "Deze regel bestaat al"}); return
                conn.execute("INSERT INTO editorial_rules (rule) VALUES (?)", (rule,))
                conn.commit()
                count = conn.execute("SELECT COUNT(*) FROM editorial_rules WHERE active=1").fetchone()[0]
                conn.close()
                self._json({"ok": True, "total": count})
            except Exception as e:
                self._json({"ok": False, "msg": str(e)})

        # ── /search POST ────────────────────────────────────
        elif self.path == "/search":
            try:
                data  = self._body()
                query = data.get("query", "").strip()
                if not query:
                    self._json({"results": []}); return
                conn  = _db()
                like  = f"%{query}%"
                rows  = conn.execute(
                    "SELECT title, url, source, published_at, image_url, "
                    "relevance_score, prioriteit FROM items "
                    "WHERE (title LIKE ? OR content LIKE ? OR full_content LIKE ?) "
                    "ORDER BY published_at DESC LIMIT 12",
                    (like, like, like)
                ).fetchall()
                conn.close()
                self._json({"results": [dict(r) for r in rows]})
            except Exception as e:
                self._json({"results": [], "error": str(e)})

        # ── /ethics-check POST ─────────────────────────────
        elif self.path == "/ethics-check":
            try:
                data = self._body()
                url  = data.get("url", "").strip()
                if not url:
                    self._json({"error": "geen url"}); return

                conn = _db()
                row  = conn.execute(
                    "SELECT url, title, source, content, full_content, relevance_score, "
                    "prioriteit, ethics_verdict, ethics_score, ethics_report FROM items WHERE url=?",
                    (url,)
                ).fetchone()
                conn.close()

                if not row:
                    self._json({"error": "item niet gevonden"}); return

                item = dict(row)

                # Terugkeer cached verdict als al gecheckt
                if item.get("ethics_verdict"):
                    self._json({
                        "verdict":  item["ethics_verdict"],
                        "score":    item["ethics_score"],
                        "report":   json.loads(item["ethics_report"] or "{}"),
                        "cached":   True,
                    }); return

                # Live check via OpenAI
                PAYWALL_SRCS = {"FD","NRC","De Telegraaf","Volkskrant","Trouw","AD","Bloomberg"}
                paywall = item.get("source","") in PAYWALL_SRCS
                input_data = {
                    "agent_bron":    "agent_03",
                    "item_id":       url,
                    "titel":         item.get("title",""),
                    "tekst":         (item.get("full_content") or item.get("content") or "")[:1500],
                    "originele_bron": item.get("source",""),
                    "url":           url,
                    "ranking_score": item.get("relevance_score",0),
                    "paywall_omzeild": paywall,
                }
                ETHICS_SYSTEM = """Je bent Agent 04 — de Ethische Agent van PowNed.
Beoordeel het item op 7 indicatoren (elk 0-100). Geef ALLEEN geldig JSON terug.
Indicatoren: bronherkomst_legitimiteit, paywall_copyright, privacy_persoonsgegevens,
verificatie_framing, eenzijdigheid_hoor_wederhoor, clickbait_sensatiezucht, ethische_verkrijging.
Verdictregels: gemiddelde ≥70=GROEN, 45-69=ORANJE, <45=ROOD. Zwakste <40 = max ORANJE.
JSON-formaat: {"scores":{...7 indicatoren...},"overall_score":0-100,"verdict":"GROEN|ORANJE|ROOD",
"zwakste_indicator":"naam","zwakste_score":0-100,"paywall_alert":true/false,
"gemarkeerde_passages":[],"aanbeveling":"max 2 zinnen","mogelijke_pipeline_fout":"agent_01/02/03/geen"}"""

                reply = call_openai(ETHICS_SYSTEM, [{"role":"user","content":json.dumps(input_data, ensure_ascii=False)}])
                try:
                    result  = json.loads(reply)
                    scores  = result.get("scores",{})
                    overall = result.get("overall_score") or (round(sum(scores.values())/len(scores)) if scores else 50)
                    verdict = result.get("verdict","ORANJE")
                    result["overall_score"] = overall
                    result["verdict"]       = verdict
                    report  = json.dumps(result, ensure_ascii=False)
                    conn2 = _db()
                    conn2.execute(
                        "UPDATE items SET ethics_verdict=?, ethics_score=?, ethics_report=? WHERE url=?",
                        (verdict, overall, report, url)
                    )
                    conn2.commit()
                    conn2.close()
                    self._json({"verdict": verdict, "score": overall, "report": result, "cached": False})
                except Exception as parse_err:
                    self._json({"error": f"parse fout: {parse_err}", "raw": reply})
            except Exception as e:
                self._json({"error": str(e)})

        # ── /rules/delete POST ──────────────────────────────
        elif self.path == "/rules/delete":
            try:
                data = self._body()
                rid  = data.get("id")
                if rid:
                    conn = _db()
                    conn.execute("UPDATE editorial_rules SET active=0 WHERE id=?", (rid,))
                    conn.commit()
                    conn.close()
                    self._json({"ok": True})
                else:
                    self._json({"ok": False})
            except Exception as e:
                self._json({"ok": False, "msg": str(e)})

        # ── /api/items/check ── duplicaatcheck voor n8n ────────
        elif self.path == "/api/items/check":
            try:
                data = self._body()
                url  = data.get("url","").strip()
                if not url:
                    self._json({"exists": False}); return
                import hashlib
                content_hash = hashlib.sha256(((data.get("content",""))+(data.get("title",""))).encode("utf-8","ignore")).hexdigest()
                conn = _db()
                row  = conn.execute("SELECT 1 FROM items WHERE url=? OR content_hash=?", (url, content_hash)).fetchone()
                conn.close()
                self._json({"exists": bool(row), "url": url})
            except Exception as e:
                self._json({"exists": False, "error": str(e)})

        # ── /api/items/save ── nieuw item opslaan voor n8n ─────
        elif self.path == "/api/items/save":
            try:
                import hashlib
                data  = self._body()
                url   = data.get("url","").strip()
                if not url:
                    self._json({"ok": False, "msg": "geen url"}); return
                content_hash = hashlib.sha256(((data.get("content",""))+(data.get("title",""))).encode("utf-8","ignore")).hexdigest()
                conn = _db()
                conn.execute("""INSERT OR IGNORE INTO items
                    (url,content_hash,title,source,published_at,content,image_url,region,raw_html)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (url, content_hash, data.get("title"), data.get("source"),
                     data.get("published_at"), data.get("content"), data.get("image_url"),
                     data.get("region"), data.get("raw_html")))
                conn.commit()
                conn.close()
                self._json({"ok": True, "url": url})
            except Exception as e:
                self._json({"ok": False, "msg": str(e)})

        # ── /api/items/update-score ── scores opslaan van n8n ──
        elif self.path == "/api/items/update-score":
            try:
                data = self._body()
                items = data if isinstance(data, list) else [data]
                conn  = _db()
                for item in items:
                    conn.execute(
                        "UPDATE items SET relevance_score=?,relevance_reason=?,score_breakdown=?,prioriteit=? WHERE url=?",
                        (item.get("relevance_score"), item.get("relevance_reason"),
                         item.get("score_breakdown"), item.get("prioriteit"), item.get("url"))
                    )
                conn.commit()
                conn.close()
                self._json({"ok": True, "updated": len(items)})
            except Exception as e:
                self._json({"ok": False, "msg": str(e)})

        # ── /api/items/update-ethics ── ethiek opslaan van n8n ─
        elif self.path == "/api/items/update-ethics":
            try:
                data = self._body()
                items = data if isinstance(data, list) else [data]
                conn  = _db()
                for item in items:
                    conn.execute(
                        "UPDATE items SET ethics_verdict=?,ethics_score=?,ethics_report=? WHERE url=?",
                        (item.get("ethics_verdict"), item.get("ethics_score"),
                         json.dumps(item.get("ethics_report",{}), ensure_ascii=False), item.get("url"))
                    )
                conn.commit()
                conn.close()
                self._json({"ok": True, "updated": len(items)})
            except Exception as e:
                self._json({"ok": False, "msg": str(e)})

        # ── /api/rebuild ── feed herbouwen vanuit n8n ───────────
        elif self.path == "/api/rebuild":
            try:
                import subprocess as sp
                result = sp.run(
                    [os.environ.get("PYTHON_BIN", str(ROOT / "powned_venv" / "bin" / "python3")),
                     str(ROOT / "powned_build.py")],
                    capture_output=True, text=True,
                    env={**__import__("os").environ,
                         "DATABASE_URL": f"sqlite:///{DB_PATH}"}
                )
                self._json({"ok": result.returncode == 0,
                            "output": result.stdout.strip() or result.stderr.strip()})
            except Exception as e:
                self._json({"ok": False, "msg": str(e)})

        # ── /api/pipeline/collect POST ── voor n8n v2 ──────────────
        # Draait stap 1 (main.py, alle bronnen incl. Playwright) en
        # stap 2 (enrich_content.py) synchroon en geeft JSON terug.
        # n8n wacht op het antwoord (timeout 10 min) voor AI-scoring.
        elif self.path == "/api/pipeline/collect":
            with _lock:
                already = _status["running"]
            if already:
                self._json({"ok": False, "msg": "Pipeline al actief — wacht tot klaar"})
                return
            with _lock:
                _status["running"] = True
                _status["log"] = []
            logs = []
            errors = []
            try:
                # Gebruik PYTHON_BIN env var, of zoek een werkende venv-python
                python = os.environ.get("PYTHON_BIN", "")
                if not python:
                    candidates = [
                        str(ROOT / "powned_venv" / "bin" / "python3"),
                        "/path/to/Powned-redactie-agent/powned_venv/bin/python3",
                    ]
                    for c in candidates:
                        if os.path.isfile(c):
                            # Check of yaml beschikbaar is (venv is compleet)
                            test = subprocess.run([c, "-c", "import yaml"], capture_output=True)
                            if test.returncode == 0:
                                python = c
                                break
                    if not python:
                        python = candidates[0]  # laatste poging
                env = {
                    **os.environ,
                    "DATABASE_URL": f"sqlite:////{DB_PATH}",
                    "DB_PATH": str(DB_PATH),
                    "FEED_DIR": str(ROOT / "data"),
                    "PYTHONPATH": str(ROOT / "src"),
                }
                steps = [
                    ("stap1", "Nieuws ophalen (RSS + Scraper + Playwright)", str(ROOT / "src" / "main.py")),
                    ("stap2", "Volledige tekst ophalen (Playwright + Trafilatura)", str(ROOT / "enrich_content.py")),
                ]
                results = {}
                for key, label, script in steps:
                    logs.append(f"▶ {label}...")
                    with _lock:
                        _status["log"].append(f"▶ {label}...")
                    proc = subprocess.Popen(
                        [python, script],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, env=env, cwd=str(ROOT)
                    )
                    out_lines = []
                    for line in proc.stdout:
                        out_lines.append(line.rstrip())
                        with _lock:
                            _status["log"].append(line.rstrip())
                    proc.wait()
                    ok = proc.returncode == 0
                    status_str = "OK" if ok else f"FOUT (code {proc.returncode})"
                    logs.append(f"✓ {label}: {status_str}")
                    results[key] = {"ok": ok, "exitCode": proc.returncode, "output": "\n".join(out_lines[-40:])}
                    if not ok:
                        errors.append(f"{label}: exitcode {proc.returncode}")
                with _lock:
                    _status["last"] = "collect_done"
                self._json({
                    "ok": len(errors) == 0,
                    "msg": "Stap 1+2 klaar" if not errors else f"Fouten: {'; '.join(errors)}",
                    "stap1": results.get("stap1", {}),
                    "stap2": results.get("stap2", {}),
                    "log": logs,
                })
            except Exception as e:
                with _lock:
                    _status["last"] = f"error: {e}"
                self._json({"ok": False, "msg": str(e), "log": logs})
            finally:
                with _lock:
                    _status["running"] = False

        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path in ("/", "/index.html", "/feed"):
            self._file(FEED_DIR / "index.html")

        elif self.path == "/refresh":
            with _lock:
                already = _status["running"]
            if already:
                self._json({"status": "running"})
            else:
                threading.Thread(target=run_pipeline, daemon=True).start()
                self._json({"status": "started"})

        elif self.path == "/status":
            with _lock:
                data = dict(_status)
            self._json(data)

        # ── /api/sources GET ── bronnenlijst voor n8n ──────────
        elif self.path == "/api/sources":
            try:
                import yaml
                src_file = ROOT / "config" / "sources.yml"
                sources  = yaml.safe_load(src_file.read_text()).get("sources", [])
                rss_only = [s for s in sources if s.get("type") in ("rss", "sitemap")]
                self._json({"sources": rss_only, "count": len(rss_only)})
            except Exception as e:
                self._json({"sources": [], "error": str(e)})

        # ── /api/items/pending-score GET ── te scoren items ────
        elif self.path.startswith("/api/items/pending-score"):
            try:
                from urllib.parse import urlparse, parse_qs
                limit = int(parse_qs(urlparse(self.path).query).get("limit",["80"])[0])
                conn  = _db()
                rows  = conn.execute(
                    """SELECT url,title,source,content,full_content,published_at
                       FROM items WHERE prioriteit IS NULL AND title IS NOT NULL AND title!=''
                       ORDER BY fetched_at DESC LIMIT ?""", (limit,)
                ).fetchall()
                conn.close()
                self._json({"items": [dict(r) for r in rows], "count": len(rows)})
            except Exception as e:
                self._json({"items": [], "error": str(e)})

        # ── /api/items/pending-ethics GET ── te checken items ──
        elif self.path.startswith("/api/items/pending-ethics"):
            try:
                from urllib.parse import urlparse, parse_qs
                limit = int(parse_qs(urlparse(self.path).query).get("limit",["40"])[0])
                conn  = _db()
                rows  = conn.execute(
                    """SELECT url,title,source,content,full_content,relevance_score,prioriteit
                       FROM items WHERE ethics_verdict IS NULL
                         AND prioriteit IN ('must-have','sterk','interessant')
                       ORDER BY relevance_score DESC LIMIT ?""", (limit,)
                ).fetchall()
                conn.close()
                self._json({"items": [dict(r) for r in rows], "count": len(rows)})
            except Exception as e:
                self._json({"items": [], "error": str(e)})

        # ── /rules GET (haal regels op) ─────────────────────
        elif self.path == "/rules":
            try:
                conn  = _db()
                rules = conn.execute(
                    "SELECT id, rule, created_at FROM editorial_rules WHERE active=1 ORDER BY created_at DESC"
                ).fetchall()
                conn.close()
                self._json({"rules": [dict(r) for r in rules]})
            except Exception as e:
                self._json({"rules": [], "error": str(e)})

        # ── /api/feed GET ── volledige feed voor React frontend ──
        elif self.path.startswith("/api/feed"):
            try:
                from urllib.parse import urlparse, parse_qs
                from datetime import datetime
                qs     = parse_qs(urlparse(self.path).query)
                limit  = int(qs.get("limit", ["200"])[0])
                offset = int(qs.get("offset", ["0"])[0])
                prio   = qs.get("prio", [None])[0]
                ethics = qs.get("ethics", [None])[0]
                region = qs.get("region", [None])[0]
                q      = qs.get("q", [None])[0]

                conn = _db()
                where, params = ["title IS NOT NULL", "title != ''"], []
                if prio:   where.append("prioriteit = ?");       params.append(prio)
                if ethics: where.append("ethics_verdict = ?");   params.append(ethics)
                if region: where.append("region = ?");           params.append(region)
                if q:      where.append("title LIKE ?");         params.append(f"%{q}%")

                base  = f"WHERE {' AND '.join(where)}"
                total = conn.execute(f"SELECT COUNT(*) FROM items {base}", params).fetchone()[0]
                rows  = conn.execute(
                    f"""SELECT url,title,source,region,published_at,fetched_at,
                               content,image_url,relevance_score,relevance_reason,
                               score_breakdown,prioriteit,ethics_verdict,ethics_score,
                               ethics_report,full_content
                        FROM items {base}
                        ORDER BY CASE prioriteit
                          WHEN 'must-have' THEN 1 WHEN 'sterk' THEN 2
                          WHEN 'interessant' THEN 3 WHEN 'zwak' THEN 4 ELSE 5 END,
                          relevance_score DESC
                        LIMIT ? OFFSET ?""",
                    params + [limit, offset]
                ).fetchall()

                # Pipeline status
                last_row = conn.execute("SELECT MAX(fetched_at) FROM items").fetchone()
                new_count = conn.execute(
                    "SELECT COUNT(*) FROM items WHERE fetched_at > datetime('now','-1 hour')"
                ).fetchone()[0]
                stats = conn.execute(
                    """SELECT
                         COUNT(CASE WHEN prioriteit='must-have' THEN 1 END) as must_have,
                         COUNT(CASE WHEN prioriteit='sterk' THEN 1 END) as sterk,
                         COUNT(CASE WHEN prioriteit='interessant' THEN 1 END) as interessant,
                         COUNT(CASE WHEN ethics_verdict='GROEN' THEN 1 END) as ethics_groen,
                         COUNT(CASE WHEN ethics_verdict='ORANJE' THEN 1 END) as ethics_oranje,
                         COUNT(CASE WHEN ethics_verdict='ROOD' THEN 1 END) as ethics_rood
                       FROM items"""
                ).fetchone()
                conn.close()

                age_min = 9999
                if last_row and last_row[0]:
                    try:
                        last = datetime.fromisoformat(last_row[0].replace("Z",""))
                        age_min = int((datetime.utcnow() - last).total_seconds() / 60)
                    except: pass

                with _lock:
                    running = _status["running"]

                self._json({
                    "items":   [dict(r) for r in rows],
                    "total":   total,
                    "pipeline": {
                        "age_minutes": age_min,
                        "new_count":   new_count,
                        "running":     running,
                        "fresh":       age_min < 90,
                    },
                    "stats": dict(stats) if stats else {},
                })
            except Exception as e:
                self._json({"items": [], "total": 0, "error": str(e)})

        # ── Pagina-routes ───────────────────────────────────────────────────────
        elif self.path in ("/login", "/login.html"):
            self._file(FEED_DIR / "login.html")
        elif self.path in ("/dashboard", "/dashboard.html", "/dashboard/"):
            self._file(FEED_DIR / "dashboard.html")
        elif self.path in ("/agenda", "/agenda.html"):
            self._file(FEED_DIR / "agenda.html")
        elif self.path in ("/archief", "/archief.html"):
            self._file(FEED_DIR / "archief.html")
        elif self.path in ("/uitleg", "/uitleg.html"):
            self._file(FEED_DIR / "uitleg.html")
        elif self.path in ("/walkthrough", "/walkthrough.html"):
            self._file(FEED_DIR / "walkthrough.html")

        # ── /api/dashboard/stats ────────────────────────────────────────────
        elif self.path == "/api/dashboard/stats":
            try:
                from datetime import datetime
                conn      = _db()
                new_count = conn.execute(
                    "SELECT COUNT(*) FROM items WHERE fetched_at > datetime('now','-1 hour')"
                ).fetchone()[0]
                must_have = conn.execute(
                    "SELECT COUNT(*) FROM items WHERE prioriteit='must-have'"
                ).fetchone()[0]
                total     = conn.execute(
                    "SELECT COUNT(*) FROM items WHERE published_at >= datetime('now','-3 days')"
                ).fetchone()[0]
                total_all = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
                last_row  = conn.execute("SELECT MAX(fetched_at) FROM items").fetchone()
                labeled_count = conn.execute("SELECT COUNT(*) FROM editorial_labels").fetchone()[0]
                next_event    = conn.execute(
                    "SELECT title, event_date FROM agenda_events WHERE event_date >= date('now') ORDER BY event_date LIMIT 1"
                ).fetchone()
                conn.close()
                age_min = 9999
                if last_row and last_row[0]:
                    try:
                        last    = datetime.fromisoformat(last_row[0].replace("Z",""))
                        age_min = int((datetime.utcnow() - last).total_seconds() / 60)
                    except Exception:
                        pass
                self._json({
                    "new_count":      new_count,
                    "must_have":      must_have,
                    "total":          total,
                    "total_all":      total_all,
                    "labeled":        labeled_count,
                    "next_event":     dict(next_event) if next_event else None,
                    "pipeline_fresh": age_min < 90,
                    "pipeline_age":   age_min,
                })
            except Exception as e:
                self._json({"error": str(e)})

        # ── /api/chat/history ─────────────────────────────────────────────────
        elif self.path == "/api/chat/history":
            try:
                conn = _db()
                rows = conn.execute(
                    "SELECT role, content FROM chat_messages ORDER BY id DESC LIMIT 20"
                ).fetchall()
                conn.close()
                msgs = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
                self._json({"messages": msgs})
            except Exception as e:
                self._json({"messages": [], "error": str(e)})

        # ── /api/status ── lichtgewicht poll voor auto-refresh ───────────────
        # ── /health ── UptimeRobot health check ──────────────────────────────
        elif self.path == "/health":
            try:
                from datetime import datetime
                conn     = _db()
                total    = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
                last_row = conn.execute("SELECT MAX(fetched_at) FROM items").fetchone()
                labeled  = conn.execute("SELECT COUNT(*) FROM editorial_labels").fetchone()[0]
                conn.close()
                age_min = 9999
                if last_row and last_row[0]:
                    try:
                        last    = datetime.fromisoformat(last_row[0].replace("Z",""))
                        age_min = int((datetime.utcnow() - last).total_seconds() / 60)
                    except Exception:
                        pass
                healthy = age_min < 180  # unhealthy als pipeline >3 uur oud
                status  = {
                    "status":         "ok" if healthy else "degraded",
                    "pipeline_age_minutes": age_min,
                    "pipeline_fresh": age_min < 90,
                    "articles_total": total,
                    "labels_total":   labeled,
                    "version":        "1.0",
                }
                if healthy:
                    self._json(status)
                else:
                    # HTTP 503 zodat UptimeRobot een alert stuurt
                    body = json.dumps(status, ensure_ascii=False).encode()
                    self.send_response(503)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", len(body))
                    self.end_headers()
                    self.wfile.write(body)
            except Exception as e:
                body = json.dumps({"status": "error", "error": str(e)}).encode()
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", len(body))
                self.end_headers()
                self.wfile.write(body)

        elif self.path == "/api/status":
            try:
                from datetime import datetime
                conn      = _db()
                total     = conn.execute(
                    "SELECT COUNT(*) FROM items WHERE published_at >= datetime('now','-3 days')"
                ).fetchone()[0]
                last_row  = conn.execute("SELECT MAX(fetched_at) FROM items").fetchone()
                conn.close()
                age_min = 9999
                if last_row and last_row[0]:
                    try:
                        last    = datetime.fromisoformat(last_row[0].replace("Z",""))
                        age_min = int((datetime.utcnow() - last).total_seconds() / 60)
                    except Exception:
                        pass
                self._json({"total": total, "age_minutes": age_min, "fresh": age_min < 90})
            except Exception as e:
                self._json({"total": 0, "error": str(e)})

        # ── /api/agenda ────────────────────────────────────────────────────
        elif self.path.startswith("/api/agenda"):
            try:
                conn  = _db()
                where = _protest_where()
                protest_items = conn.execute(
                    f"""SELECT title, url, source, image_url,
                               DATE(published_at) as event_date, published_at
                        FROM items WHERE {where}
                          AND published_at IS NOT NULL AND published_at != ''
                        ORDER BY published_at DESC LIMIT 200"""
                ).fetchall()
                manual = conn.execute(
                    "SELECT * FROM agenda_events ORDER BY event_date DESC"
                ).fetchall()
                conn.close()
                auto_list   = [dict(r) | {"auto_detected": 1, "event_type": "protest"} for r in protest_items]
                manual_list = [dict(r) for r in manual]
                self._json({"auto": auto_list, "manual": manual_list})
            except Exception as e:
                self._json({"auto": [], "manual": [], "error": str(e)})

        # ── /api/archief ───────────────────────────────────────────────────
        elif self.path.startswith("/api/archief"):
            try:
                from urllib.parse import urlparse, parse_qs
                qs = parse_qs(urlparse(self.path).query)
                label = qs.get("label", [None])[0]
                user  = qs.get("user", [None])[0]
                conn  = _db()
                where, params = ["1=1"], []
                if label: where.append("label=?"); params.append(label)
                if user:  where.append("user_email=?"); params.append(user)
                rows = conn.execute(
                    f"SELECT * FROM editorial_labels WHERE {' AND '.join(where)} ORDER BY labeled_at DESC LIMIT 200",
                    params
                ).fetchall()
                conn.close()
                self._json({"items": [dict(r) for r in rows]})
            except Exception as e:
                self._json({"items": [], "error": str(e)})

        else:
            super().do_GET()

    def _file(self, path: Path):
        if not path.exists():
            self.send_error(404, "Pagina niet gevonden")
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # stille logging


HOST = os.environ.get("HOST", "127.0.0.1")  # prod: 127.0.0.1 (achter nginx), dev: 127.0.0.1
print(f"PowNed Feed → http://{HOST}:{PORT}")
print("Klik op 'Nieuwe artikelen' in de feed om de pipeline te starten.")
ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()

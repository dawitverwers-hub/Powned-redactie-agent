"""Genereert een statische HTML-feed uit powned.db."""

import os
import re
import sqlite3
from collections import Counter
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

# Gebruik DB_PATH / FEED_DIR env vars als die gezet zijn (voor launchd/deploy), anders relatieve fallback
_BASE = Path(__file__).resolve().parent
DB = Path(os.environ.get("DB_PATH", str(_BASE / "data" / "powned.db")))
OUT_DIR = Path(os.environ.get("FEED_DIR", str(_BASE / "data" / "dashboard")))
OUT_DIR.mkdir(parents=True, exist_ok=True)

PAGE_SIZE = 48

# ── Stad-extractie ────────────────────────────────────────────────────────────
# Gesorteerd op lengte (langste eerst) om partiële matches te voorkomen
DUTCH_CITIES = sorted([
    "Amsterdam","Rotterdam","Den Haag","'s-Gravenhage","Utrecht","Eindhoven",
    "Tilburg","Groningen","Almere","Breda","Nijmegen","Enschede","Haarlem",
    "Apeldoorn","Arnhem","Zaanstad","Amersfoort","'s-Hertogenbosch","Den Bosch",
    "Haarlemmermeer","Zoetermeer","Zwolle","Leiden","Maastricht","Dordrecht",
    "Emmen","Delft","Deventer","Helmond","Alkmaar","Venlo","Leeuwarden",
    "Westland","Sittard","Heerlen","Oss","Roosendaal","Gouda","Zaandam",
    "Hoorn","Ede","Purmerend","Nieuwegein","Spijkenisse","Vlaardingen",
    "Schiedam","Capelle aan den IJssel","Lelystad","Alphen aan den Rijn",
    "Hilversum","Hengelo","Dordrecht","Hardenberg","Ridderkerk","Barendrecht",
    "Diemen","Wormerland","Weesp","Badhoevedorp","Katwijk","Harderwijk",
    "Wageningen","Veenendaal","Zeist","Bilthoven","Driebergen","Woerden",
    "Bodegraven","Waddinxveen","Zoetermeer","Middelburg","Vlissingen","Goes",
    "Terneuzen","Bergen op Zoom","Tilburg","Waalwijk","Oosterhout",
    "Etten-Leur","Deurne","Helmond","Weert","Roermond","Venray","Boxtel",
    "Vught","Culemborg","Tiel","Doetinchem","Winterswijk","Zutphen","Lochem",
    "Heerde","Harderwijk","Nunspeet","Ermelo","Zevenaar","Aalten","Beuningen",
    "Wijchen","Grave","Gennep","Mook","Cuijk","Boxmeer","Mill",
    "Hoogeveen","Meppel","Assen","Emmen","Coevorden","Stadskanaal","Veendam",
    "Winschoten","Delfzijl","Appingedam","Leek","Zuidhorn","Beilen","Borger",
    "Franeker","Harlingen","Sneek","Joure","Heerenveen","Drachten","Dokkum",
    "Bolsward","Makkum","Workum","Lemmer","Wolvega","Steenwijk","Kampen",
    "Hardenberg","Ommen","Almelo","Oldenzaal","Losser","Haaksbergen",
    "Goor","Rijssen","Wierden","Vriezenveen","Coevorden","Hardenberg",
], key=len, reverse=True)

_CITY_PATTERN = re.compile(
    r'\b(' + '|'.join(re.escape(c) for c in DUTCH_CITIES) + r')\b',
    re.IGNORECASE
)

def extract_cities(title: str, content: str = "") -> str:
    """Extraheer Nederlandse steden uit titel + eerste 300 tekens van content."""
    text = f"{title} {content[:300]}"
    found = []
    seen = set()
    for m in _CITY_PATTERN.finditer(text):
        city = m.group(0)
        key = city.lower()
        if key not in seen:
            seen.add(key)
            # Normaliseer varianten
            if key in ("'s-gravenhage",): city = "Den Haag"
            if key in ("den bosch",): city = "'s-Hertogenbosch"
            found.append(city)
    return ",".join(found)

PAYWALL_SOURCES_BUILD = {"AD", "Volkskrant", "Trouw", "De Telegraaf"}

SOURCE_COLORS = {
    # PowNed eigen
    "PowNed":                "#e2148b",
    # Nationaal
    "NOS":                   "#c0392b",
    "De Telegraaf":          "#003da5",
    "AD":                    "#b20000",
    "RTL Nieuws":            "#ff6600",
    "Hart van Nederland":    "#e8003c",
    "Volkskrant":            "#d4001a",
    "Trouw":                 "#006b3c",
    "Politie":               "#154273",
    "Rechtspraak":           "#4a4a8a",
    "Crimesite":             "#8b0000",
    # Regionaal
    "NH Nieuws":             "#e4001b",
    "AT5":                   "#e4001b",
    "Gooi- en Eemlander":    "#0057a8",
    "Rijnmond":              "#e30613",
    "Regio 15":              "#008000",
    "Omroep West":           "#005cb9",
    "RTV Utrecht":           "#e4001b",
    "Omroep Brabant":        "#ff6900",
    "BN De Stem":            "#e2001a",
    "De Stentor":            "#0066cc",
    "PZC":                   "#005b8e",
    "RTV Noord":             "#00843d",
    "L1 Limburg":            "#ae1c28",
    # Zoektermen
    "Zoekterm Zwarte Piet":  "#333333",
    "Zoekterm Demonstratie": "#555555",
    "Zoekterm Inbraak":      "#333333",
}
PLACEHOLDER_GRADIENTS = [
    "linear-gradient(135deg,#1a0a0a,#3d0000)",
    "linear-gradient(135deg,#0a0a1a,#00003d)",
    "linear-gradient(135deg,#0a1a0a,#003d00)",
    "linear-gradient(135deg,#1a0a1a,#3d003d)",
    "linear-gradient(135deg,#1a1a0a,#3d3d00)",
    "linear-gradient(135deg,#0a1a1a,#003d3d)",
    "linear-gradient(135deg,#1a1a1a,#2a2a2a)",
]

def strip_tags(text):
    return re.sub(r"<[^>]+>", "", text or "").strip()

# ── Pipeline status ───────────────────────────────────────────────────────────
def _pipeline_status():
    try:
        conn_s = sqlite3.connect(str(DB))
        row = conn_s.execute("SELECT MAX(fetched_at) FROM items").fetchone()
        new_count = conn_s.execute(
            "SELECT COUNT(*) FROM items WHERE fetched_at > datetime('now','-1 hour')"
        ).fetchone()[0]
        conn_s.close()
        if not row or not row[0]:
            return "onbekend", False, 0
        last = datetime.fromisoformat(row[0].replace("Z",""))
        mins = max(0, int((datetime.utcnow() - last).total_seconds() / 60))
        if   mins < 2:   age = "zojuist"
        elif mins < 60:  age = f"{mins} min geleden"
        elif mins < 120: age = "1 uur geleden"
        else:            age = f"{mins // 60} uur geleden"
        return age, mins < 90, new_count
    except Exception:
        return "onbekend", False, 0

_pipeline_age, _pipeline_ok, _pipeline_new = _pipeline_status()

def clean_title(title, source):
    t = strip_tags(title or "")
    for suffix in [f" - {source}", f" | {source}"]:
        if t.endswith(suffix):
            t = t[:-len(suffix)].strip()
    return t or "(geen titel)"

def parse_date(s):
    if not s:
        return datetime.min
    try:
        return parsedate_to_datetime(s).replace(tzinfo=None)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return datetime.min

def fmt_date(s):
    dt = parse_date(s)
    if dt == datetime.min:
        return ""
    days = ["ma","di","wo","do","vr","za","zo"]
    months = ["jan","feb","mrt","apr","mei","jun","jul","aug","sep","okt","nov","dec"]
    return f"{days[dt.weekday()]} {dt.day} {months[dt.month-1]}, {dt.hour:02d}:{dt.minute:02d}"

def is_new(s):
    dt = parse_date(s)
    if dt == datetime.min:
        return False
    return (datetime.now() - dt).total_seconds() < 4 * 3600

# ── Data laden ────────────────────────────────────────────────────────────────
conn = sqlite3.connect(DB)
# Migratie: voeg ethics-kolommen toe als ze nog niet bestaan
for _sql in [
    "ALTER TABLE items ADD COLUMN ethics_verdict TEXT",
    "ALTER TABLE items ADD COLUMN ethics_score   INTEGER",
    "ALTER TABLE items ADD COLUMN ethics_report  TEXT",
]:
    try:
        conn.execute(_sql); conn.commit()
    except Exception:
        pass
conn.row_factory = sqlite3.Row
# Migreer city-kolom als die nog niet bestaat
try:
    conn.execute("ALTER TABLE items ADD COLUMN city TEXT")
    conn.commit()
except Exception:
    pass

rows = conn.execute(
    "SELECT title, url, source, region, published_at, content, image_url, fetched_at, full_content, "
    "relevance_score, relevance_reason, score_breakdown, prioriteit, human_label, "
    "ethics_verdict, ethics_score, ethics_report, city FROM items"
).fetchall()

# Sla steden op in DB voor items die nog geen city hebben
updates = []
for r in rows:
    if not r["city"]:
        c = extract_cities(r["title"] or "", r["content"] or "")
        if c:
            updates.append((c, r["url"]))
if updates:
    conn.executemany("UPDATE items SET city=? WHERE url=?", updates)
    conn.commit()
conn.close()

items = [dict(r) for r in rows]
# Vul city in voor items die net zijn bijgewerkt
url_to_city = {url: city for city, url in updates}
for item in items:
    if not item.get("city") and item["url"] in url_to_city:
        item["city"] = url_to_city[item["url"]]

items.sort(key=lambda x: parse_date(x["published_at"]), reverse=True)

# ── filter: artikelen opgehaald in de laatste 3 dagen ────────────────────
# Gebruik fetched_at (wanneer WIJ het ophaalden) ipv published_at
# zodat vandaag opgehaalde artikelen altijd zichtbaar zijn,
# ook als de RSS-bron een oude published_at-datum teruggeeft.
from datetime import timedelta
_cutoff = datetime.now() - timedelta(days=3)
items = [i for i in items
         if parse_date(i.get("fetched_at","")) >= _cutoff
         or parse_date(i["published_at"]) >= _cutoff
         or parse_date(i["published_at"]) == datetime.min]

def _is_hot(item):
    prio = item.get("prioriteit")
    if prio:
        return prio in ("must-have", "sterk", "interessant")
    # Fallback voor items die nog gescoord worden met oud 1-10 systeem
    return (item.get("relevance_score") or 0) >= 6

def _sort_score(item):
    prio = item.get("prioriteit")
    score = item.get("relevance_score") or 0
    # Normaliseer oud systeem (1-10) naar 0-100 zodat sortering klopt
    if prio and score > 10:
        return score
    return score * 10

hot_items = sorted(
    [i for i in items if _is_hot(i) and i.get("source") != "PowNed"],
    key=lambda x: (_sort_score(x), parse_date(x["published_at"])),
    reverse=True
)[:300]

powned_items = sorted(
    [i for i in items if i.get("source") == "PowNed"],
    key=lambda x: parse_date(x["published_at"]),
    reverse=True
)[:12]

source_counts = Counter(i["source"] for i in items if i["source"])
region_counts = Counter(i["region"] for i in items if i["region"])
sources = sorted(source_counts)
regions = sorted(region_counts)
total = len(items)

# Stad-counts: extraheer uit alle items
_city_counter: Counter = Counter()
for _i in items:
    for _c in extract_cities(_i.get("title",""), _i.get("full_content") or _i.get("content","")).split(","):
        if _c:
            _city_counter[_c] += 1
# Top 30 steden met minstens 2 artikelen, alfabetisch
top_cities = sorted(
    [c for c, n in _city_counter.items() if n >= 2],
    key=lambda c: (-_city_counter[c], c)
)[:30]

# Ethiek-counts
ethics_counts = Counter(
    i.get("ethics_verdict") for i in items if i.get("ethics_verdict")
)

# Welcome screen aantallen
_must_have_count   = sum(1 for i in items if i.get("prioriteit") == "must-have")
_regionaal_count   = sum(v for k, v in region_counts.items() if k and k != "NL")
_ethics_rood_count = ethics_counts.get("ROOD", 0)

# Sidebar groepen
NIEUWS_SOURCES = [
    "PowNed", "NOS", "De Telegraaf", "RTL Nieuws", "AD", "Hart van Nederland",
    "Volkskrant", "Trouw", "Politie", "Rechtspraak", "Crimesite",
]
POLITICI_SOURCES = [
    "MinPres Jetten", "Geert Wilders", "Thierry Baudet",
    "Pepijn van Houwelingen", "Extinction Rebellion",
]
ZOEKTERMEN_SOURCES = [
    "Zoekterm Zwarte Piet", "Zoekterm Demonstratie", "Zoekterm Inbraak",
]
REGIONAAL_SOURCES = [
    "NH Nieuws", "AT5", "Gooi- en Eemlander", "Rijnmond", "Regio 15",
    "Omroep West", "RTV Utrecht", "Omroep Brabant", "BN De Stem",
    "De Stentor", "PZC", "RTV Noord", "L1 Limburg",
]

# ── HTML helpers ──────────────────────────────────────────────────────────────
def esc(s):
    # Newlines/tabs breken HTML-attributen — verwijder ze ook
    s = (s or "").replace("\n", " ").replace("\r", " ").replace("\t", " ")
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")

def card_html(item, idx, hero=False):
    title      = clean_title(item["title"], item.get("source",""))
    url        = item["url"] or "#"
    source     = item["source"] or ""
    region     = item["region"] or ""
    pub        = fmt_date(item["published_at"])
    pub_iso    = item["published_at"] or ""
    snippet    = strip_tags(item["content"] or "")[:200]
    img_url    = (item["image_url"] or "").strip()
    full       = strip_tags(item.get("full_content") or "")
    color      = SOURCE_COLORS.get(source, "#555")
    grad       = PLACEHOLDER_GRADIENTS[idx % len(PLACEHOLDER_GRADIENTS)]
    new_badge  = '<span class="new-badge">NIEUW</span>' if is_new(pub_iso) else ""
    has_full   = len(full) > 200
    is_paywall = source in PAYWALL_SOURCES_BUILD
    score      = item.get("relevance_score") or 0
    prioriteit = item.get("prioriteit") or ""
    breakdown       = item.get("score_breakdown") or ""
    ethics_verdict  = item.get("ethics_verdict") or ""
    ethics_score    = item.get("ethics_score") or 0
    ethics_report   = item.get("ethics_report") or ""
    if prioriteit:
        score_badge = f'<span class="score-badge prio-{prioriteit.replace("-","_")}">{score}<span class="score-denom">/100</span></span>'
    elif score >= 6:
        score_badge = f'<span class="score-badge score-{score}">{score}<span class="score-denom">/10</span></span>'
    else:
        score_badge = ""
    _ethics_cls = {"GROEN":"ethics-groen","ORANJE":"ethics-oranje","ROOD":"ethics-rood"}
    _ethics_icon = {"GROEN":"✅","ORANJE":"⚠️","ROOD":"🚫"}
    ethics_badge = (f'<span class="ethics-badge {_ethics_cls.get(ethics_verdict,"")}" '
                    f'title="Ethiekcheck: {ethics_verdict} ({ethics_score}/100)">'
                    f'{_ethics_icon.get(ethics_verdict,"")} {ethics_verdict}</span>'
                    ) if ethics_verdict else ""

    if img_url:
        img_block = (f'<div class="card-img">'
                     f'<img src="{img_url}" alt="" loading="lazy" '
                     f'onerror="this.parentElement.classList.add(\'placeholder\');'
                     f'this.parentElement.style.background=\'{grad}\';this.remove()">'
                     f'</div>')
    else:
        letter = source[0].upper() if source else "?"
        img_block = f'<div class="card-img placeholder" style="background:{grad}"><span>{letter}</span></div>'

    region_sub    = (f'<span class="card-region">{region}</span>'
                     if region and region != "NL" else "")
    snippet_block = (f'<p>{snippet}{"…" if len(strip_tags(item["content"] or "")) > 200 else ""}</p>'
                     if snippet else "")
    full_attr     = f' data-full="{esc(full[:8000])}"' if has_full else ""
    # Altijd RSS-samenvatting meegeven als fallback voor modal
    summary_attr  = f' data-summary="{esc((item.get("content") or "")[:1000])}"'
    human_label     = item.get("human_label") or ""
    reason_attr     = f' data-reason="{esc(item.get("relevance_reason") or "")}"'
    breakdown_attr  = f' data-breakdown="{esc(breakdown)}"' if breakdown else ""
    prioriteit_attr = f' data-prioriteit="{esc(prioriteit)}"' if prioriteit else ""
    label_attr      = f' data-human-label="{esc(human_label)}"' if human_label else ""
    ethics_attr     = f' data-ethics="{esc(ethics_verdict)}"' if ethics_verdict else ""
    ethics_rep_attr = f' data-ethics-report="{esc(ethics_report[:3000])}"' if ethics_report else ""
    # Gebruik opgeslagen city uit DB als die er is, anders live extraheren
    cities = item.get("city") or extract_cities(title, item.get("full_content") or item.get("content",""))
    city_attr = f' data-city="{esc(cities)}"' if cities else ""
    hero_cls      = " hero" if hero else ""

    return (f'<article class="card{hero_cls}" data-source="{source}" data-region="{region}" '
            f'data-pub="{pub_iso}" data-url="{esc(url)}" data-title="{esc(title)}" '
            f'data-source-label="{esc(source)}" data-img="{esc(img_url)}" '
            f'data-color="{color}"{full_attr}{summary_attr}{reason_attr}{breakdown_attr}{prioriteit_attr}{label_attr}{ethics_attr}{ethics_rep_attr}{city_attr}>'
            f'{img_block}'
            f'<div class="card-body">'
            f'<div class="card-meta">'
            f'<span class="badge" style="background:{color}">{source}</span>'
            f'{score_badge}{ethics_badge}'
            f'<time class="card-date" title="{pub}">{pub}</time>'
            f'</div>'
            f'<h2>{title}</h2>'
            f'{region_sub}'
            f'{snippet_block}'
            f'<div class="card-actions">'
            f'<div class="card-actions-row">'
            f'<a class="read-btn" href="{url}" target="_blank" rel="noopener" onclick="event.stopPropagation()">Lees origineel ↗</a>'
            + (f'<a class="bypass-btn" href="https://archive.ph/newest/{url}" target="_blank" rel="noopener" onclick="event.stopPropagation()">🔓 Betaalmuur</a>' if is_paywall or not has_full else '')
            + f'</div>'
            f'<div class="card-actions-row">'
            + f'<button class="fav-btn" onclick="event.stopPropagation();toggleFav(this)" title="Opslaan als favoriet">♥</button>'
            + f'<button class="label-btn label-interessant" onclick="event.stopPropagation();setLabel(this,\'interessant\')" title="Markeer als interessant">✓ Interessant</button>'
            + f'<button class="label-btn label-overslaan" onclick="event.stopPropagation();setLabel(this,\'overslaan\')" title="Overslaan">✗ Overslaan</button>'
            + f'</div>'
            + f'</div></div></article>')

hero_html = card_html(items[0], 0, hero=True) if items else ""

def hot_card_html(item, idx):
    title      = clean_title(item["title"], item.get("source",""))
    url        = item["url"] or "#"
    source     = item["source"] or ""
    score      = item.get("relevance_score") or 0
    reason     = item.get("relevance_reason") or ""
    prioriteit = item.get("prioriteit") or ""
    breakdown  = item.get("score_breakdown") or ""
    img_url    = (item["image_url"] or "").strip()
    pub_iso    = item["published_at"] or ""
    pub        = fmt_date(pub_iso)
    color      = SOURCE_COLORS.get(source, "#555")
    grad       = PLACEHOLDER_GRADIENTS[idx % len(PLACEHOLDER_GRADIENTS)]
    full       = strip_tags(item.get("full_content") or "")
    has_full   = len(full) > 200
    is_paywall = source in PAYWALL_SOURCES_BUILD
    full_attr       = f' data-full="{esc(full[:8000])}"' if has_full else ""
    reason_attr     = f' data-reason="{esc(reason)}"'
    breakdown_attr  = f' data-breakdown="{esc(breakdown)}"' if breakdown else ""
    prioriteit_attr = f' data-prioriteit="{esc(prioriteit)}"' if prioriteit else ""

    if img_url:
        img_block = (f'<div class="card-img">'
                     f'<img src="{img_url}" alt="" loading="lazy" '
                     f'onerror="this.parentElement.style.background=\'{grad}\';this.remove()">'
                     f'</div>')
    else:
        letter = source[0].upper() if source else "?"
        img_block = f'<div class="card-img placeholder" style="background:{grad}"><span>{letter}</span></div>'

    bypass_btn = (f'<a class="bypass-btn" href="https://archive.ph/newest/{url}" target="_blank" rel="noopener" onclick="event.stopPropagation()">🔓 Betaalmuur</a>'
                  if is_paywall or not has_full else '')

    human_label_h   = item.get("human_label") or ""
    label_attr_h    = f' data-human-label="{esc(human_label_h)}"' if human_label_h else ""
    ethics_v_h      = item.get("ethics_verdict") or ""
    ethics_s_h      = item.get("ethics_score") or 0
    ethics_r_h      = item.get("ethics_report") or ""
    _ec  = {"GROEN":"ethics-groen","ORANJE":"ethics-oranje","ROOD":"ethics-rood"}
    _ei  = {"GROEN":"✅","ORANJE":"⚠️","ROOD":"🚫"}
    ethics_badge_h  = (f'<span class="ethics-badge {_ec.get(ethics_v_h,"")}" '
                       f'title="Ethiekcheck: {ethics_v_h} ({ethics_s_h}/100)">'
                       f'{_ei.get(ethics_v_h,"")} {ethics_v_h}</span>'
                       ) if ethics_v_h else ""
    ethics_attr_h   = f' data-ethics="{esc(ethics_v_h)}"' if ethics_v_h else ""
    ethics_rep_h    = f' data-ethics-report="{esc(ethics_r_h[:3000])}"' if ethics_r_h else ""
    cities_h        = extract_cities(title, item.get("full_content") or item.get("content",""))
    city_attr_h     = f' data-city="{esc(cities_h)}"' if cities_h else ""

    if prioriteit:
        hot_score_badge = (f'<span class="score-badge prio-{prioriteit.replace("-","_")}">'
                           f'{score}<span class="score-denom">/100</span></span>')
        prio_label = f'<span class="prio-label prio-label-{prioriteit.replace("-","_")}">{prioriteit}</span>'
    else:
        hot_score_badge = f'<span class="score-badge score-{score}">{score}<span class="score-denom">/10</span></span>'
        prio_label = ""

    return (f'<article class="hot-card" data-source="{source}" data-url="{esc(url)}" '
            f'data-pub="{pub_iso}" data-title="{esc(title)}" data-source-label="{esc(source)}" '
            f'data-img="{esc(img_url)}" data-color="{color}"{full_attr}{reason_attr}'
            f'{breakdown_attr}{prioriteit_attr}{label_attr_h}{ethics_attr_h}{ethics_rep_h}{city_attr_h}>'
            f'{img_block}'
            f'<div class="card-body">'
            f'<div class="card-meta">'
            f'<span class="badge" style="background:{color}">{source}</span>'
            f'{hot_score_badge}{ethics_badge_h}'
            f'<time class="card-date" title="{pub}">{pub}</time>'
            f'</div>'
            f'<h3>{title}</h3>'
            f'<p class="hot-reason">{esc(reason)}</p>'
            f'<div class="card-actions">'
            f'<div class="card-actions-row">'
            f'<a class="read-btn" href="{url}" target="_blank" rel="noopener" onclick="event.stopPropagation()">Lees origineel ↗</a>'
            f'{bypass_btn}'
            f'</div>'
            f'<div class="card-actions-row">'
            f'<button class="fav-btn" onclick="event.stopPropagation();toggleFav(this)" title="Opslaan als favoriet">♥</button>'
            f'<button class="label-btn label-interessant" onclick="event.stopPropagation();setLabel(this,\'interessant\')" title="Interessant">✓ Interessant</button>'
            f'<button class="label-btn label-overslaan" onclick="event.stopPropagation();setLabel(this,\'overslaan\')" title="Overslaan">✗ Overslaan</button>'
            f'</div>'
            f'</div>'
            f'</div></article>')

hot_html = "".join(hot_card_html(item, i) for i, item in enumerate(hot_items))
powned_html = "".join(hot_card_html(item, i) for i, item in enumerate(powned_items))

grid_items = []
for i, item in enumerate(items[1:], 1):
    hidden = ' style="display:none"' if i >= PAGE_SIZE else ""
    c = card_html(item, i)
    c = c.replace('<article class="card"', f'<article class="card"{hidden}', 1)
    grid_items.append(c)
grid_html = "\n".join(grid_items)

SOURCE_DOMAINS = {
    "NOS":                   "nos.nl",
    "De Telegraaf":          "telegraaf.nl",
    "AD":                    "ad.nl",
    "RTL Nieuws":            "rtlnieuws.nl",
    "Hart van Nederland":    "hartvannederland.nl",
    "Volkskrant":            "volkskrant.nl",
    "Trouw":                 "trouw.nl",
    "Politie":               "politie.nl",
    "Rechtspraak":           "rechtspraak.nl",
    "Crimesite":             "crimesite.nl",
    "NH Nieuws":             "nhnieuws.nl",
    "AT5":                   "at5.nl",
    "Gooi- en Eemlander":    "gooieneemlander.nl",
    "Rijnmond":              "rijnmond.nl",
    "Regio 15":              "regio15.nl",
    "Omroep West":           "omroepwest.nl",
    "RTV Utrecht":           "rtvutrecht.nl",
    "Omroep Brabant":        "omroepbrabant.nl",
    "BN De Stem":            "bndestem.nl",
    "De Stentor":            "destentor.nl",
    "PZC":                   "pzc.nl",
    "RTV Noord":             "rtvnoord.nl",
    "L1 Limburg":            "l1nieuws.nl",
    "PowNed":                "powned.tv",
}

def source_icon(s):
    domain = SOURCE_DOMAINS.get(s)
    if domain:
        favicon = f"https://www.google.com/s2/favicons?domain={domain}&sz=32"
        color   = SOURCE_COLORS.get(s, "#888")
        return (f'<img class="chip-logo" src="{favicon}" alt="" loading="lazy" '
                f'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'block\'">'
                f'<span class="chip-dot" style="display:none"></span>')
    return f'<span class="chip-dot"></span>'

def make_chips(src_list):
    return "".join(
        f'<button class="chip" data-type="source" data-val="{s}" style="--c:{SOURCE_COLORS.get(s,"#888")}">'
        f'{source_icon(s)}'
        f'<span class="chip-name">{s}</span>'
        f'<span class="chip-count">{source_counts.get(s, 0)}</span></button>'
        for s in src_list
    )

nieuws_chips    = make_chips(NIEUWS_SOURCES)
politici_chips  = make_chips(POLITICI_SOURCES)
zoekterm_chips  = make_chips(ZOEKTERMEN_SOURCES)
regionaal_chips = make_chips(REGIONAAL_SOURCES)
REGION_FLAGS = {
    "NL":            "https://flagcdn.com/24x18/nl.png",
    "Amsterdam":     "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6d/Flag_of_Amsterdam.svg/40px-Flag_of_Amsterdam.svg.png",
    "Noord-Holland": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/51/Flag_of_North_Holland.svg/40px-Flag_of_North_Holland.svg.png",
    "Zuid-Holland":  "https://upload.wikimedia.org/wikipedia/commons/thumb/3/38/Flag_of_Zuid-Holland.svg/40px-Flag_of_Zuid-Holland.svg.png",
    "Utrecht":       "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4b/Utrecht_%28province%29-Flag.svg/40px-Utrecht_%28province%29-Flag.svg.png",
    "Noord-Brabant": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a2/North_Brabant-Flag.svg/40px-North_Brabant-Flag.svg.png",
    "Overijssel":    "https://upload.wikimedia.org/wikipedia/commons/thumb/f/f8/Flag_of_Overijssel.svg/40px-Flag_of_Overijssel.svg.png",
    "Zeeland":       "https://upload.wikimedia.org/wikipedia/commons/thumb/5/54/Flag_of_Zeeland.svg/40px-Flag_of_Zeeland.svg.png",
    "Groningen":     "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e6/Flag_of_Groningen.svg/40px-Flag_of_Groningen.svg.png",
    "Limburg":       "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d1/Flag_of_Limburg_%28Netherlands%29.svg/40px-Flag_of_Limburg_%28Netherlands%29.svg.png",
}

def region_icon(r):
    flag = REGION_FLAGS.get(r)
    if flag:
        return (f'<img class="chip-logo chip-flag" src="{flag}" alt="" loading="lazy" '
                f'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'block\'">'
                f'<span class="chip-dot" style="display:none"></span>')
    return '<span class="chip-dot"></span>'

region_chips = "".join(
    f'<button class="chip" data-type="region" data-val="{r}" style="--c:#9c2d8f">'
    f'{region_icon(r)}'
    f'<span class="chip-name">{r}</span>'
    f'<span class="chip-count">{region_counts[r]}</span></button>'
    for r in regions
)

# Editorial grid (vervangt slider)
editorial_items = [i for i in hot_items if (i.get("image_url") or "").strip()][:8]
if len(editorial_items) < 3:
    editorial_items = hot_items[:min(8, len(hot_items))]

def _ed_attrs(item):
    title      = clean_title(item["title"], item.get("source",""))
    url        = item["url"] or "#"
    source     = item["source"] or ""
    score      = item.get("relevance_score") or 0
    reason     = item.get("relevance_reason") or ""
    prioriteit = item.get("prioriteit") or ""
    breakdown  = item.get("score_breakdown") or ""
    img_url    = (item.get("image_url") or "").strip()
    color      = SOURCE_COLORS.get(source, "#888")
    full       = strip_tags(item.get("full_content") or "")
    ethics_v   = item.get("ethics_verdict") or ""
    ethics_s   = item.get("ethics_score") or 0
    pub_iso    = ""
    try:
        pub_iso = parse_date(item.get("published_at","")).isoformat()
    except Exception:
        pass
    cities     = extract_cities(title, item.get("full_content") or item.get("content",""))
    full_attr  = f' data-full="{esc(full[:8000])}"' if len(full) > 200 else ""
    return dict(title=title, url=url, source=source, score=score, reason=reason,
                prioriteit=prioriteit, breakdown=breakdown, img_url=img_url,
                color=color, full=full, ethics_v=ethics_v, ethics_s=ethics_s,
                pub_iso=pub_iso, cities=cities, full_attr=full_attr)

def editorial_hero(item):
    d = _ed_attrs(item)
    prio_cls  = f' prio-{d["prioriteit"].replace("-","_")}' if d["prioriteit"] else ""
    score_el  = f'<span class="ed-score{prio_cls}">{d["score"]}/100</span>' if d["score"] else ""
    snippet   = strip_tags(item.get("content") or "")[:180]
    ethics_icon = {"GROEN":"✅","ORANJE":"⚠️","ROOD":"🚫"}.get(d["ethics_v"],"")
    ethics_el = (f'<span class="ed-ethics ed-ethics-{d["ethics_v"].lower()}">'
                 f'{ethics_icon} {d["ethics_v"]}</span>') if d["ethics_v"] else ""
    bg = f"url('{d['img_url']}')" if d["img_url"] else ""
    return (f'<article class="ed-hero" data-source="{d["source"]}" data-url="{esc(d["url"])}" '
            f'data-pub="{d["pub_iso"]}" data-city="{esc(d["cities"])}" '
            f'data-ethics="{d["ethics_v"]}" data-title="{esc(d["title"])}" '
            f'data-img="{esc(d["img_url"])}" data-color="{d["color"]}" '
            f'data-reason="{esc(d["reason"])}" data-breakdown="{esc(d["breakdown"])}" '
            f'data-prioriteit="{d["prioriteit"]}"{d["full_attr"]}>'
            f'<div class="ed-hero-bg" style="background-image:{bg}"></div>'
            f'<div class="ed-hero-overlay"></div>'
            f'<div class="ed-hero-body">'
            f'<div class="ed-meta">'
            f'<span class="ed-source" style="background:{d["color"]}">{d["source"]}</span>'
            f'{score_el}{ethics_el}'
            f'</div>'
            f'<h2 class="ed-title">{d["title"]}</h2>'
            f'<p class="ed-snippet">{esc(snippet)}{"…" if len(snippet)==180 else ""}</p>'
            f'<p class="ed-reason">{esc(d["reason"][:90])}{"…" if len(d["reason"])>90 else ""}</p>'
            f'<div class="ed-actions">'
            f'<a class="ed-btn-primary" href="{d["url"]}" target="_blank" rel="noopener" onclick="event.stopPropagation()">Lees artikel ↗</a>'
            f'<button class="ed-btn-modal" onclick="event.stopPropagation();openModal(this.closest(\'.ed-hero\'))">Snelle preview</button>'
            f'</div>'
            f'</div>'
            f'</article>')

def editorial_side(item):
    d = _ed_attrs(item)
    prio_cls  = f' prio-{d["prioriteit"].replace("-","_")}' if d["prioriteit"] else ""
    score_el  = f'<span class="ed-score ed-score-sm{prio_cls}">{d["score"]}/100</span>' if d["score"] else ""
    ethics_icon = {"GROEN":"✅","ORANJE":"⚠️","ROOD":"🚫"}.get(d["ethics_v"],"")
    return (f'<article class="ed-side" data-source="{d["source"]}" data-url="{esc(d["url"])}" '
            f'data-pub="{d["pub_iso"]}" data-city="{esc(d["cities"])}" '
            f'data-ethics="{d["ethics_v"]}" data-title="{esc(d["title"])}" '
            f'data-img="{esc(d["img_url"])}" data-color="{d["color"]}" '
            f'data-reason="{esc(d["reason"])}" data-breakdown="{esc(d["breakdown"])}" '
            f'data-prioriteit="{d["prioriteit"]}"{d["full_attr"]}>'
            f'<div class="ed-side-img" style="background-image:url(\'{d["img_url"]}\')"></div>'
            f'<div class="ed-side-body">'
            f'<div class="ed-meta">'
            f'<span class="ed-source" style="background:{d["color"]}">{d["source"]}</span>'
            f'{score_el}'
            f'</div>'
            f'<h3 class="ed-side-title">{d["title"]}</h3>'
            f'<a class="ed-side-link" href="{d["url"]}" target="_blank" rel="noopener" onclick="event.stopPropagation()">Lees ↗</a>'
            f'</div>'
            f'</article>')

if editorial_items:
    slides_html = "".join(
        editorial_hero(item).replace('class="ed-hero"', f'class="ed-hero{"" if i else " active"}"', 1)
        for i, item in enumerate(editorial_items)
    )
    dots_html = "".join(
        f'<button class="ed-dot{"" if i else " active"}" data-idx="{i}"></button>'
        for i in range(len(editorial_items))
    )
    sides_html = "".join(editorial_side(editorial_items[i]) for i in range(1, min(3, len(editorial_items))))
    editorial_html = (
        f'<div class="ed-slider-wrap">'
        f'<div class="ed-slides">{slides_html}</div>'
        f'<div class="ed-controls">'
        f'<button class="ed-arr ed-arr-l">&#x2039;</button>'
        f'<button class="ed-arr ed-arr-r">&#x203a;</button>'
        f'<div class="ed-dots">{dots_html}</div>'
        f'</div>'
        f'<div class="ed-progress"><div class="ed-progress-bar"></div></div>'
        f'</div>'
        f'{sides_html}'
    )
else:
    editorial_html = ""

# Banner slides (legacy — niet meer gebruikt in HTML maar functies intact houden)
banner_items = editorial_items
def banner_slide(item, idx):
    title      = clean_title(item["title"], item.get("source",""))
    url        = item["url"] or "#"
    source     = item["source"] or ""
    score      = item.get("relevance_score") or 0
    reason     = item.get("relevance_reason") or ""
    prioriteit = item.get("prioriteit") or ""
    breakdown  = item.get("score_breakdown") or ""
    img_url    = (item["image_url"] or "").strip()
    color      = SOURCE_COLORS.get(source, "#888")
    full       = strip_tags(item.get("full_content") or "")
    has_full   = len(full) > 200
    full_attr       = f' data-full="{esc(full[:8000])}"' if has_full else ""
    reason_attr     = f' data-reason="{esc(reason)}"'
    breakdown_attr  = f' data-breakdown="{esc(breakdown)}"' if breakdown else ""
    prioriteit_attr = f' data-prioriteit="{esc(prioriteit)}"' if prioriteit else ""
    active   = " active" if idx == 0 else ""
    bg = f'style="background-image:url(\'{img_url}\')"' if img_url else 'style="background:#1a0000"'
    if prioriteit:
        score_el = f'<span class="slide-score prio-{prioriteit.replace("-","_")}">{score}/100</span>'
    elif score >= 6:
        score_el = f'<span class="slide-score">{score}/10</span>'
    else:
        score_el = ""
    snippet  = strip_tags(item.get("content") or "")[:160]
    return (f'<div class="slide{active}" data-source="{source}" data-url="{esc(url)}" '
            f'data-title="{esc(title)}" data-source-label="{esc(source)}" '
            f'data-img="{esc(img_url)}" data-color="{color}"{full_attr}{reason_attr}'
            f'{breakdown_attr}{prioriteit_attr}>'
            f'<div class="slide-bg" {bg}></div>'
            f'<div class="slide-overlay"></div>'
            f'<div class="slide-content">'
            f'<div class="slide-meta">'
            f'<span class="slide-source" style="background:{color}">{source}</span>'
            f'{score_el}'
            f'</div>'
            f'<h2 class="slide-title">{title}</h2>'
            f'<p class="slide-snippet">{esc(snippet)}{"…" if len(snippet) == 160 else ""}</p>'
            f'<p class="slide-reason">{esc(reason[:100])}{"…" if len(reason) > 100 else ""}</p>'
            f'<div class="slide-actions">'
            f'<a class="slide-btn-primary" href="{url}" target="_blank" rel="noopener" onclick="event.stopPropagation()">Lees artikel ↗</a>'
            f'<button class="slide-btn-modal" onclick="event.stopPropagation();openModal(this.closest(\'.slide\'))">Snelle preview</button>'
            f'</div>'
            f'</div>'
            f'</div>')

banner_html = "".join(banner_slide(item, i) for i, item in enumerate(banner_items))
banner_dots = "".join(
    f'<button class="dot {"active" if i == 0 else ""}" data-slide="{i}"></button>'
    for i in range(len(banner_items))
)

# ── HTML template ─────────────────────────────────────────────────────────────
html = f"""<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PowNed Redactie</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" crossorigin="">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" crossorigin=""></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js" defer></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/ScrollTrigger.min.js" defer></script>
<script>
// Als de pagina direct als bestand wordt geopend → doorsturen naar de server
if (location.protocol === 'file:') {{
  location.replace('http://127.0.0.1:5001');
}}
</script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
:root{{
  --pink:#e2148b;--purple:#9c2d8f;
  --gradient:linear-gradient(90deg,#e2148b,#9c2d8f);
  --bg:#000000;--surface:#111111;--surface2:#1a1a1a;--surface3:#252525;
  --border:rgba(255,255,255,.07);--border2:rgba(255,255,255,.12);
  --text:#f0f0f0;--text2:#888888;--muted:#444444;--muted2:#606060;
  --radius:12px;
  --shadow:0 1px 3px rgba(0,0,0,.5),0 4px 16px rgba(0,0,0,.4);
  --shadow-lg:0 4px 8px rgba(0,0,0,.5),0 16px 48px rgba(0,0,0,.6);
}}
*{{box-sizing:border-box;margin:0;padding:0}}
html{{scroll-behavior:smooth;-webkit-text-size-adjust:100%}}
body{{
  font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;
  background:var(--bg);color:var(--text);min-height:100vh;
  -webkit-font-smoothing:antialiased;
  scroll-behavior:smooth
}}
a{{text-decoration:none;color:inherit}}

/* ══ HEADER ══════════════════════════════════════════════════════════════════ */
header{{
  background:rgba(0,0,0,.95);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
  border-bottom:1px solid var(--border);
  padding:0 24px;position:sticky;top:0;z-index:400;
  display:flex;align-items:center;gap:16px;height:60px;
  box-shadow:0 1px 0 0 transparent
}}
header::after{{
  content:'';position:absolute;bottom:0;left:0;right:0;height:2px;
  background:var(--gradient)
}}
.logo{{display:flex;align-items:center;gap:10px;flex-shrink:0;cursor:pointer;user-select:none}}
.logo-img{{height:34px;width:auto;flex-shrink:0;display:block;object-fit:contain}}
.logo-tag{{
  font-size:.55rem;font-weight:600;color:var(--muted);letter-spacing:1.5px;
  text-transform:uppercase;padding:3px 8px;border-radius:20px;
  background:var(--surface2);margin-left:2px
}}
.search-wrap{{flex:1;position:relative;max-width:400px;margin:0 16px}}
.search-wrap svg{{position:absolute;left:12px;top:50%;transform:translateY(-50%);color:var(--muted);pointer-events:none}}
#search{{
  width:100%;background:var(--surface2);border:1px solid var(--border);
  border-radius:10px;color:var(--text);font-size:.84rem;font-family:inherit;
  padding:9px 14px 9px 36px;outline:none;transition:border-color .2s,box-shadow .2s
}}
#search:focus{{border-color:rgba(226,20,139,.5);box-shadow:0 0 0 3px rgba(226,20,139,.1)}}
#search::placeholder{{color:var(--muted)}}
/* ══ WELCOME SCREEN ══════════════════════════════════════════════════════════ */
.welcome-screen{{
  position:fixed;inset:0;z-index:9999;
  background:#000;
  display:flex;align-items:center;justify-content:center;
  animation:wsFadeIn .35s ease;
  overflow-y:auto;padding:24px;
}}
.welcome-screen.hiding{{
  animation:wsFadeOut .4s ease forwards;
  pointer-events:none;
}}
@keyframes wsFadeIn{{from{{opacity:0}}to{{opacity:1}}}}
@keyframes wsFadeOut{{from{{opacity:1;transform:scale(1)}}to{{opacity:0;transform:scale(.97)}}}}

.welcome-inner{{
  width:100%;max-width:680px;
  display:flex;flex-direction:column;gap:40px;
  padding:20px 0 40px;
}}

.welcome-greeting{{
  display:flex;flex-direction:column;gap:4px;
}}
.welcome-time{{
  font-size:clamp(2.4rem,6vw,4.2rem);
  font-weight:900;
  line-height:1;
  letter-spacing:-0.03em;
  color:var(--text);
}}
.welcome-name{{
  font-size:clamp(2.4rem,6vw,4.2rem);
  font-weight:900;
  line-height:1;
  letter-spacing:-0.03em;
  background:var(--gradient);
  -webkit-background-clip:text;
  -webkit-text-fill-color:transparent;
  background-clip:text;
}}
.welcome-meta{{
  display:flex;align-items:center;gap:12px;margin-top:8px;flex-wrap:wrap;
}}
.welcome-date{{
  font-size:.85rem;color:var(--muted);
}}
.welcome-pipe{{
  display:flex;align-items:center;gap:6px;
  font-size:.78rem;color:var(--text2);
  background:var(--surface2);border:1px solid var(--border);
  padding:4px 10px;border-radius:6px;
}}
.wp-dot{{width:6px;height:6px;border-radius:50%;}}
.wp-dot.ok{{background:#00c853;box-shadow:0 0 5px rgba(0,200,83,.6)}}
.wp-dot.warn{{background:#ffb300;}}

.welcome-sub{{
  font-size:.95rem;color:var(--muted);margin-top:-20px;
}}

.feed-options{{
  display:grid;
  grid-template-columns:1fr 1fr;
  gap:12px;
}}
@media(max-width:560px){{.feed-options{{grid-template-columns:1fr}}}}

.feed-option{{
  background:var(--surface);
  border:1px solid var(--border);
  border-radius:14px;
  padding:22px 24px;
  cursor:pointer;
  text-align:left;
  transition:border-color .18s,background .18s,transform .15s;
  font-family:inherit;
  display:flex;flex-direction:column;gap:6px;
  position:relative;overflow:hidden;
}}
.feed-option::before{{
  content:'';position:absolute;inset:0;
  background:var(--gradient);opacity:0;
  transition:opacity .18s;
}}
.feed-option:hover{{
  border-color:rgba(226,20,139,.35);
  background:rgba(226,20,139,.04);
  transform:translateY(-2px);
}}
.feed-option:hover::before{{opacity:.04}}
.feed-option:active{{transform:translateY(0)}}

.fo-icon{{font-size:1.4rem;line-height:1;margin-bottom:2px}}
.fo-title{{
  font-size:1rem;font-weight:800;color:var(--text);
  letter-spacing:-.02em;line-height:1;
}}
.fo-sub{{
  font-size:.78rem;color:var(--muted);line-height:1.45;
}}
.fo-count{{
  font-size:.7rem;font-weight:700;color:var(--pink);
  margin-top:4px;
}}
.fo-arrow{{
  position:absolute;right:18px;top:50%;transform:translateY(-50%);
  font-size:1.1rem;color:var(--muted);transition:color .15s,right .15s;
}}
.feed-option:hover .fo-arrow{{color:var(--text);right:14px}}

.welcome-footer{{
  display:flex;align-items:center;gap:16px;flex-wrap:wrap;
}}
.welcome-skip{{
  font-size:.78rem;color:var(--muted);background:none;border:none;
  cursor:pointer;font-family:inherit;padding:0;transition:color .15s;
}}
.welcome-skip:hover{{color:var(--text2)}}
.welcome-name-edit{{
  font-size:.75rem;color:var(--muted);background:var(--surface2);
  border:1px solid var(--border);border-radius:6px;
  padding:5px 10px;cursor:pointer;font-family:inherit;
  transition:border-color .15s,color .15s;
}}
.welcome-name-edit:hover{{border-color:var(--border2);color:var(--text2)}}

/* ══ PIPELINE STATUS ═════════════════════════════════════════════════════════ */
.pipeline-status{{
  display:flex;align-items:center;gap:6px;font-size:.7rem;
  padding:5px 10px;border-radius:7px;background:var(--surface2);
  border:1px solid var(--border);white-space:nowrap;flex-shrink:0
}}
.ps-dot{{width:6px;height:6px;border-radius:50%;flex-shrink:0}}
.ps-dot.ok{{background:#00c853;box-shadow:0 0 6px rgba(0,200,83,.5)}}
.ps-dot.warn{{background:#ffb300;box-shadow:0 0 6px rgba(255,179,0,.5)}}
.ps-age{{color:var(--text2)}}
.ps-new{{
  font-weight:700;color:var(--pink);margin-left:2px;
  background:rgba(226,20,139,.1);padding:1px 5px;border-radius:4px
}}
@media(max-width:780px){{.pipeline-status{{display:none}}}}

.hdr-right{{margin-left:auto;display:flex;align-items:center;gap:10px;flex-shrink:0}}
.counter{{font-size:.72rem;color:var(--text2);white-space:nowrap}}
.counter strong{{color:var(--text);font-weight:700}}
.hdr-btn{{
  background:var(--surface2);border:1px solid var(--border2);border-radius:9px;
  color:var(--text2);font-size:.73rem;font-weight:600;padding:7px 14px;
  cursor:pointer;transition:all .18s;white-space:nowrap;font-family:inherit
}}
.hdr-btn:hover{{background:var(--gradient);border-color:transparent;color:#fff}}
.hdr-divider{{width:1px;height:22px;background:var(--border2);flex-shrink:0}}
.syncstudio-badge{{
  display:flex;flex-direction:column;align-items:flex-end;gap:1px;
  text-decoration:none;flex-shrink:0;opacity:.85;transition:opacity .18s
}}
.syncstudio-badge:hover{{opacity:1}}
.ss-made{{font-size:.52rem;color:var(--muted);letter-spacing:1px;text-transform:uppercase;line-height:1}}
.ss-logo{{font-size:.8rem;letter-spacing:.5px;line-height:1}}
.ss-logo b{{color:#fff;font-weight:800}}
.ss-teal{{color:#00e5c0;font-weight:400}}
@media(max-width:580px){{.logo-tag,.counter,.hdr-divider,.syncstudio-badge{{display:none}}}}

/* ══ TABS ════════════════════════════════════════════════════════════════════ */
.tabs{{
  background:rgba(8,8,15,.92);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
  border-bottom:1px solid var(--border);
  padding:0 24px;position:sticky;top:60px;z-index:300;
  display:flex;align-items:stretch;overflow-x:auto;scrollbar-width:none
}}
.tabs::-webkit-scrollbar{{display:none}}
.tab{{
  padding:0 18px;height:46px;font-size:.78rem;font-weight:600;
  color:var(--muted);cursor:pointer;border:none;border-bottom:2px solid transparent;
  background:none;transition:color .15s;white-space:nowrap;font-family:inherit;
  display:flex;align-items:center;gap:7px;letter-spacing:-.1px
}}
.tab:hover{{color:var(--text2)}}
.tab.active{{color:var(--text);border-bottom-color:transparent;background:linear-gradient(var(--bg),var(--bg)) padding-box,var(--gradient) border-box;border-bottom:2px solid transparent;background-clip:padding-box;position:relative}}
.tab.active::after{{content:'';position:absolute;bottom:-1px;left:0;right:0;height:2px;background:var(--gradient)}}
.tab-badge{{
  font-size:.58rem;font-weight:700;padding:2px 7px;border-radius:20px;
  background:var(--surface2);color:var(--muted)
}}
.tab.active .tab-badge{{background:var(--gradient);color:#fff}}

/* ══ SIDEBAR ═════════════════════════════════════════════════════════════════ */
.layout{{display:flex;min-height:calc(100vh - 106px);position:relative}}

.sidebar{{
  width:224px;overflow:hidden;flex-shrink:0;
  transition:width .28s cubic-bezier(.4,0,.2,1);
  background:var(--surface);border-right:1px solid var(--border);
  position:sticky;top:106px;height:calc(100vh - 106px);
  display:flex;flex-direction:column
}}
.sidebar.closed{{width:0}}

.sidebar-inner{{
  width:224px;padding:20px 14px 14px;overflow-y:auto;flex:1;
  scrollbar-width:thin;scrollbar-color:var(--surface3) transparent
}}
.sidebar-inner::-webkit-scrollbar{{width:3px}}
.sidebar-inner::-webkit-scrollbar-thumb{{background:var(--surface3);border-radius:2px}}

.sb-section{{margin-bottom:22px}}
.sb-label{{
  font-size:.58rem;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;
  color:var(--muted);margin-bottom:4px;padding:0 10px;display:block
}}
.chip{{
  display:flex;align-items:center;gap:9px;width:100%;
  padding:7px 10px;border-radius:8px;font-size:.78rem;font-weight:500;cursor:pointer;
  background:transparent;border:none;color:var(--text2);
  transition:background .1s,color .1s;font-family:inherit;text-align:left
}}
.chip:hover{{background:var(--surface2);color:var(--text)}}
.chip.active{{background:var(--surface2);color:var(--text)}}
.chip-dot{{width:6px;height:6px;border-radius:50%;flex-shrink:0;background:var(--c,var(--muted))}}
.chip.active .chip-dot{{background:var(--c,var(--pink))}}
.chip-logo{{width:16px;height:16px;border-radius:3px;flex-shrink:0;object-fit:contain}}
.chip-flag{{width:22px;height:14px;border-radius:2px;object-fit:cover}}
.chip.active .chip-logo{{opacity:1}}
.chip:not(.active) .chip-logo{{opacity:.7}}
.chip-name{{flex:1;overflow:hidden;text-overflow:ellipsis}}
.chip-count{{font-size:.62rem;color:var(--muted);flex-shrink:0}}
.chip.active .chip-count{{color:var(--text2)}}

.sb-divider{{height:1px;background:var(--border);margin:6px 10px 18px}}

.sb-clear{{
  margin:8px 14px 16px;padding:8px;border-radius:8px;
  font-size:.72rem;font-weight:600;cursor:pointer;
  background:transparent;border:1px solid var(--border2);
  color:var(--text2);transition:all .15s;font-family:inherit;width:calc(100% - 28px)
}}
.sb-clear:hover{{border-color:rgba(226,20,139,.4);color:var(--pink)}}

.ethics-filter-row{{display:flex;flex-direction:column;gap:4px;padding:0 4px}}
.ethics-chip{{
  display:flex;align-items:center;gap:8px;width:100%;
  padding:6px 8px;border-radius:7px;font-size:.76rem;font-weight:600;cursor:pointer;
  background:transparent;border:1px solid var(--border);color:var(--text2);
  transition:all .15s;font-family:inherit;text-align:left
}}
.ethics-chip:hover,.ethics-chip.active{{color:var(--text)}}
.ethics-chip-groen:hover,.ethics-chip-groen.active{{background:rgba(0,200,83,.1);border-color:rgba(0,200,83,.3);color:#00c853}}
.ethics-chip-oranje:hover,.ethics-chip-oranje.active{{background:rgba(255,179,0,.1);border-color:rgba(255,179,0,.3);color:#ffb300}}
.ethics-chip-rood:hover,.ethics-chip-rood.active{{background:rgba(255,23,68,.1);border-color:rgba(255,23,68,.3);color:#ff1744}}
.edot{{width:7px;height:7px;border-radius:50%;flex-shrink:0}}
.edot-groen{{background:#00c853}}
.edot-oranje{{background:#ffb300}}
.edot-rood{{background:#ff1744}}

.sidebar-toggle{{
  background:transparent;border:1px solid var(--border);border-radius:9px;
  color:var(--text2);width:36px;height:36px;cursor:pointer;
  display:flex;align-items:center;justify-content:center;
  transition:all .15s;flex-shrink:0
}}
.sidebar-toggle:hover{{border-color:var(--border2);color:var(--text)}}
.sidebar-toggle.active{{border-color:rgba(226,20,139,.4);color:var(--pink)}}
.sidebar-toggle svg{{pointer-events:none}}

@media(max-width:720px){{
  .sidebar{{position:fixed;top:106px;left:0;z-index:350;
    height:calc(100vh - 106px);box-shadow:16px 0 48px rgba(0,0,0,.8)}}
  .sb-backdrop{{display:none;position:fixed;inset:0;top:106px;background:rgba(0,0,0,.7);z-index:340}}
  .sb-backdrop.show{{display:block}}
}}

.main-content{{flex:1;min-width:0;padding:28px 28px}}

/* ══ VIEWS ═══════════════════════════════════════════════════════════════════ */
.view{{display:none}}.view.active{{display:block}}

/* ══ NIEUW SECTIE ════════════════════════════════════════════════════════════ */
.nieuw-bar{{
  display:none;align-items:center;gap:12px;
  background:rgba(226,20,139,.07);border:1px solid rgba(226,20,139,.2);
  border-radius:10px;padding:10px 16px;margin-bottom:20px;
  animation:slideDown .3s ease
}}
.nieuw-bar.show{{display:flex}}
@keyframes slideDown{{from{{opacity:0;transform:translateY(-8px)}}to{{opacity:1;transform:translateY(0)}}}}
.nieuw-dot{{width:8px;height:8px;border-radius:50%;background:var(--pink);
  animation:pulse 1.4s ease infinite;flex-shrink:0}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.4}}}}
.nieuw-label{{font-size:.8rem;font-weight:700;color:var(--pink)}}
.nieuw-sub{{font-size:.75rem;color:var(--text2);margin-left:4px}}
.nieuw-dismiss{{margin-left:auto;font-size:.7rem;color:var(--muted);
  cursor:pointer;padding:2px 6px;border-radius:4px;border:none;
  background:transparent;font-family:inherit;transition:color .15s}}
.nieuw-dismiss:hover{{color:var(--text2)}}

/* ══ EDITORIAL GRID ══════════════════════════════════════════════════════════ */
.editorial-grid{{
  display:grid;
  grid-template-columns:1fr 340px;
  grid-template-rows:1fr 1fr;
  gap:10px;
  height:480px;
  margin-bottom:32px;
  border-radius:14px;
  overflow:hidden;
}}
@media(max-width:960px){{
  .editorial-grid{{grid-template-columns:1fr;grid-template-rows:360px auto auto;height:auto}}
  .ed-hero{{grid-row:1}}
  .ed-side{{height:110px}}
}}

.ed-slider-wrap{{
  grid-column:1;grid-row:1/3;
  position:relative;overflow:hidden;border-radius:12px;
  background:var(--surface2);
}}
.ed-slides{{position:relative;height:100%}}
.ed-hero{{
  display:none;
  position:absolute;inset:0;
  overflow:hidden;cursor:pointer;
}}
.ed-hero.active{{
  display:block;z-index:2;
  animation:edFadeIn .65s ease forwards;
}}
.ed-hero.leaving{{display:block;z-index:1}}
@keyframes edFadeIn{{from{{opacity:0}}to{{opacity:1}}}}
.ed-hero.active:hover .ed-hero-bg{{transform:scale(1.03)}}
.ed-controls{{
  position:absolute;top:0;left:0;right:0;bottom:0;
  z-index:5;pointer-events:none;
}}
.ed-dots{{
  position:absolute;bottom:18px;right:18px;
  display:flex;gap:7px;align-items:center;
  pointer-events:auto;
}}
.ed-dot{{
  width:7px;height:7px;border-radius:50%;
  background:rgba(255,255,255,.3);border:none;cursor:pointer;
  transition:background .2s,transform .2s;padding:0;
}}
.ed-dot.active{{background:#e2148b;transform:scale(1.4)}}
.ed-arr{{
  position:absolute;top:50%;transform:translateY(-50%);
  background:rgba(0,0,0,.55);border:1px solid rgba(255,255,255,.18);
  color:#fff;font-size:1.6rem;width:40px;height:40px;
  border-radius:50%;cursor:pointer;
  display:flex;align-items:center;justify-content:center;
  opacity:.75;transition:opacity .2s,background .15s,transform .15s;line-height:1;
  pointer-events:auto;
}}
.ed-arr:hover{{background:rgba(226,20,139,.8);border-color:transparent;opacity:1;transform:translateY(-50%) scale(1.1)}}
.ed-arr-l{{left:12px}}
.ed-arr-r{{right:56px}}
.ed-progress{{
  position:absolute;bottom:0;left:0;right:0;height:3px;
  background:rgba(255,255,255,.12);z-index:6;overflow:hidden;
  border-radius:0 0 12px 12px;
}}
.ed-progress-bar{{
  height:100%;width:0%;
  background:linear-gradient(90deg,#e2148b,#9c2d8f);
  transition:none;
}}
.ed-hero-bg{{
  position:absolute;inset:0;
  background-size:cover;background-position:center;
  transition:transform 6s ease;
}}
.ed-hero-overlay{{
  position:absolute;inset:0;
  background:linear-gradient(110deg,rgba(0,0,0,.92) 0%,rgba(0,0,0,.55) 50%,rgba(0,0,0,.1) 100%),
             linear-gradient(to top,rgba(0,0,0,.7) 0%,transparent 60%);
}}
.ed-hero-body{{
  position:absolute;bottom:0;left:0;padding:36px 40px;max-width:580px;
  display:flex;flex-direction:column;gap:10px;
}}
@media(max-width:720px){{.ed-hero-body{{padding:22px 20px}}}}

.ed-side{{
  grid-column:2;
  display:flex;gap:0;overflow:hidden;cursor:pointer;
  border-radius:10px;background:var(--surface2);
  transition:background .15s;
}}
.ed-side:hover{{background:var(--surface3,#252525)}}
.ed-side-img{{
  width:110px;flex-shrink:0;
  background-size:cover;background-position:center;
}}
.ed-side-body{{
  flex:1;padding:14px 15px;display:flex;flex-direction:column;gap:6px;min-width:0;
}}
.ed-side-title{{
  font-size:.83rem;font-weight:700;line-height:1.35;color:var(--text);
  display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;
}}
.ed-side-link{{
  font-size:.72rem;color:var(--pink);font-weight:600;margin-top:auto;
  transition:opacity .15s;
}}
.ed-side-link:hover{{opacity:.75}}

.ed-meta{{display:flex;align-items:center;gap:6px;flex-wrap:wrap}}
.ed-source{{
  font-size:.55rem;font-weight:700;padding:3px 8px;border-radius:4px;
  color:#fff;text-transform:uppercase;letter-spacing:.5px;
}}
.ed-score{{
  font-size:.55rem;font-weight:700;padding:3px 8px;border-radius:4px;
  background:var(--gradient);color:#fff;
}}
.ed-score-sm{{font-size:.55rem;padding:2px 6px}}
.ed-ethics{{font-size:.58rem;font-weight:600;padding:2px 6px;border-radius:4px}}
.ed-ethics-groen{{background:rgba(0,200,83,.15);color:#00c853}}
.ed-ethics-oranje{{background:rgba(255,179,0,.15);color:#ffb300}}
.ed-ethics-rood{{background:rgba(255,23,68,.15);color:#ff1744}}
.ed-title{{
  font-size:clamp(1.1rem,2.8vw,1.65rem);font-weight:900;
  line-height:1.18;color:#fff;letter-spacing:-.25px;
}}
.ed-snippet{{
  font-size:.84rem;color:rgba(255,255,255,.55);line-height:1.65;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;
}}
.ed-reason{{font-size:.74rem;color:rgba(226,20,139,.9);font-weight:500}}
.ed-actions{{display:flex;gap:8px;flex-wrap:wrap;margin-top:4px}}
.ed-btn-primary{{
  padding:9px 20px;border-radius:8px;background:var(--gradient);
  color:#fff;font-size:.8rem;font-weight:700;border:none;cursor:pointer;
  transition:opacity .15s;font-family:inherit;
}}
.ed-btn-primary:hover{{opacity:.85}}
.ed-btn-modal{{
  padding:9px 16px;border-radius:8px;background:rgba(255,255,255,.08);
  color:rgba(255,255,255,.75);font-size:.8rem;font-weight:600;
  border:1px solid rgba(255,255,255,.12);cursor:pointer;
  transition:background .15s;font-family:inherit;
}}
.ed-btn-modal:hover{{background:rgba(255,255,255,.14)}}

/* ══ BANNER / SLIDER (legacy, niet meer getoond) ════════════════════════════ */
.banner{{
  position:relative;width:100%;height:500px;overflow:hidden;
  border-radius:16px;margin-bottom:32px;cursor:pointer;background:var(--surface);
  box-shadow:var(--shadow-lg);display:none;
}}
@media(max-width:900px){{.banner{{height:420px}}}}
@media(max-width:720px){{.banner{{height:340px;border-radius:12px}}}}

.slide{{position:absolute;inset:0;opacity:0;transition:opacity .7s ease;pointer-events:none}}
.slide.active{{opacity:1;pointer-events:all}}

.slide-bg{{
  position:absolute;inset:0;background-size:cover;background-position:center;
  transition:transform 8s ease;transform:scale(1.04)
}}
.slide.active .slide-bg{{transform:scale(1)}}

.slide-overlay{{
  position:absolute;inset:0;
  background:linear-gradient(105deg,rgba(8,8,15,.96) 0%,rgba(8,8,15,.65) 45%,rgba(8,8,15,.15) 100%),
             linear-gradient(to top,rgba(8,8,15,.7) 0%,transparent 55%)
}}

.slide-content{{
  position:absolute;bottom:0;left:0;padding:44px 48px;max-width:620px;
  display:flex;flex-direction:column;gap:12px
}}
@media(max-width:720px){{.slide-content{{padding:24px;max-width:100%}}}}

.slide-meta{{display:flex;align-items:center;gap:8px}}
.slide-source{{
  font-size:.58rem;font-weight:700;padding:4px 9px;border-radius:5px;
  color:#fff;text-transform:uppercase;letter-spacing:.6px
}}
.slide-score{{
  font-size:.58rem;font-weight:700;padding:4px 9px;border-radius:5px;
  background:var(--gradient);color:#fff;letter-spacing:.4px
}}
.slide-title{{
  font-size:clamp(1.2rem,3.5vw,1.85rem);font-weight:900;line-height:1.18;color:#fff;
  letter-spacing:-.3px
}}
.slide-snippet{{
  font-size:.85rem;color:rgba(255,255,255,.6);line-height:1.65;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden
}}
.slide-reason{{
  font-size:.76rem;color:rgba(226,20,139,.9);font-weight:500;
  display:-webkit-box;-webkit-line-clamp:1;-webkit-box-orient:vertical;overflow:hidden
}}
.slide-actions{{display:flex;gap:10px;flex-wrap:wrap;margin-top:8px}}
.slide-btn-primary{{
  padding:10px 22px;border-radius:9px;
  background:var(--gradient);color:#fff;font-size:.82rem;font-weight:700;
  border:none;cursor:pointer;transition:opacity .15s;font-family:inherit;letter-spacing:-.1px
}}
.slide-btn-primary:hover{{opacity:.88}}
.slide-btn-modal{{
  padding:10px 18px;border-radius:9px;
  background:rgba(255,255,255,.08);color:rgba(255,255,255,.8);font-size:.82rem;font-weight:600;
  border:1px solid rgba(255,255,255,.14);cursor:pointer;
  transition:background .15s;font-family:inherit
}}
.slide-btn-modal:hover{{background:rgba(255,255,255,.14)}}

.banner-arrow{{
  position:absolute;top:50%;transform:translateY(-50%);
  background:rgba(8,8,15,.6);border:1px solid rgba(255,255,255,.08);
  color:rgba(255,255,255,.7);width:40px;height:40px;border-radius:50%;
  display:flex;align-items:center;justify-content:center;
  cursor:pointer;z-index:10;transition:all .15s ease;font-size:1.1rem
}}
.banner-arrow:hover{{background:var(--gradient);border-color:transparent;color:#fff}}
.banner-prev{{left:16px}}
.banner-next{{right:16px}}

.banner-dots{{position:absolute;bottom:16px;right:20px;display:flex;gap:5px;z-index:10}}
.dot{{
  width:5px;height:5px;border-radius:50%;
  background:rgba(255,255,255,.25);border:none;cursor:pointer;
  transition:all .2s;padding:0
}}
.dot.active{{background:rgba(255,255,255,.9);width:20px;border-radius:3px}}

.banner-progress{{
  position:absolute;bottom:0;left:0;height:3px;
  background:var(--gradient);transition:width .1s linear;z-index:10
}}

/* ══ SECTIE HEADING ══════════════════════════════════════════════════════════ */
.sec{{display:flex;align-items:center;gap:14px;margin-bottom:16px;margin-top:8px}}
.sec-title{{font-size:.62rem;font-weight:700;text-transform:uppercase;
  letter-spacing:1px;color:var(--muted);white-space:nowrap}}
.sec-title b{{color:var(--text2)}}
.sec-line{{flex:1;height:1px;background:var(--border)}}

/* ══ POWNED ROW ══════════════════════════════════════════════════════════════ */
.powned-row{{
  display:flex;gap:12px;overflow-x:auto;padding-bottom:12px;margin-bottom:32px;
  scrollbar-width:thin;scrollbar-color:var(--surface3) transparent
}}
.powned-row::-webkit-scrollbar{{height:3px}}
.powned-row::-webkit-scrollbar-thumb{{background:var(--surface3);border-radius:2px}}
.powned-row .hot-card{{flex-shrink:0;width:260px}}
.powned-row .fav-btn{{display:none!important}}
@media(max-width:600px){{.powned-row .hot-card{{width:210px}}}}
.sec-link{{
  font-size:.68rem;font-weight:600;color:var(--pink);white-space:nowrap;flex-shrink:0;
  padding:4px 10px;border-radius:6px;border:1px solid rgba(226,20,139,.3);
  transition:all .15s
}}
.sec-link:hover{{background:var(--gradient);color:#fff;border-color:transparent}}

/* ══ HOT GRID ════════════════════════════════════════════════════════════════ */
.hot-row{{
  display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));
  gap:14px;margin-bottom:32px
}}
.hot-card{{
  background:var(--surface);border-radius:var(--radius);
  overflow:hidden;cursor:pointer;
  transition:transform .15s,box-shadow .15s;
  display:flex;flex-direction:column;
  box-shadow:var(--shadow)
}}
.hot-card:hover{{transform:translateY(-3px);box-shadow:var(--shadow-lg)}}
.hot-card .card-img{{aspect-ratio:16/9;flex-shrink:0;height:auto}}
.hot-card .card-body{{padding:16px;display:flex;flex-direction:column;gap:9px;flex:1}}
.hot-card h3{{
  font-size:.9rem;font-weight:700;line-height:1.38;color:var(--text);
  display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;
  letter-spacing:-.1px
}}
.hot-reason{{
  font-size:.72rem;color:var(--text2);line-height:1.55;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden
}}

/* ══ HERO CARD ═══════════════════════════════════════════════════════════════ */
.hero{{
  display:grid;grid-template-columns:1.4fr 1fr;
  border-radius:var(--radius);overflow:hidden;
  background:var(--surface);
  margin-bottom:16px;cursor:pointer;
  transition:transform .2s,box-shadow .2s;
  box-shadow:var(--shadow)
}}
.hero:hover{{transform:translateY(-2px);box-shadow:var(--shadow-lg)}}
.hero .card-img{{height:100%;min-height:300px;border-radius:0}}
.hero .card-body{{padding:32px;display:flex;flex-direction:column;gap:16px}}
.hero h2{{font-size:1.4rem;line-height:1.22;font-weight:800;color:var(--text);letter-spacing:-.3px}}
.hero p{{font-size:.86rem;color:var(--text2);line-height:1.7;
  display:-webkit-box;-webkit-line-clamp:5;-webkit-box-orient:vertical;overflow:hidden}}
.hero .card-actions{{margin-top:auto}}
@media(max-width:700px){{
  .hero{{grid-template-columns:1fr}}
  .hero .card-img{{height:210px;min-height:unset}}
}}

/* ══ GRID ════════════════════════════════════════════════════════════════════ */
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:14px}}

/* ══ CARD ════════════════════════════════════════════════════════════════════ */
.card{{
  background:var(--surface);border-radius:var(--radius);
  overflow:hidden;display:flex;flex-direction:column;
  transition:transform .15s,box-shadow .15s;cursor:pointer;
  box-shadow:var(--shadow)
}}
.card:hover{{transform:translateY(-2px);box-shadow:var(--shadow-lg)}}
.card-img{{
  width:100%;aspect-ratio:16/9;min-height:164px;overflow:hidden;flex-shrink:0;
  display:flex;align-items:center;justify-content:center;background:var(--surface2)
}}
.card-img img{{width:100%;height:100%;object-fit:cover;transition:transform .4s ease}}
.card:hover .card-img img,.hot-card:hover .card-img img{{transform:scale(1.05)}}
.card-img.placeholder{{font-size:2.5rem;font-weight:900;color:rgba(255,255,255,.03)}}
.card-body{{padding:16px 18px;display:flex;flex-direction:column;gap:10px;flex:1}}
.card-meta{{display:flex;align-items:center;gap:5px;flex-wrap:wrap}}

/* badges */
.badge{{
  font-size:.57rem;font-weight:700;padding:3px 7px;border-radius:5px;
  color:#fff;text-transform:uppercase;letter-spacing:.4px;white-space:nowrap
}}
.badge-region{{
  background:var(--surface3)!important;
  color:var(--text2)!important
}}
.new-badge{{
  font-size:.55rem;font-weight:800;padding:3px 7px;border-radius:5px;
  background:var(--gradient);color:#fff;text-transform:uppercase;letter-spacing:.5px;
  animation:pulse 2s infinite
}}
.score-badge{{
  font-size:.55rem;font-weight:700;padding:3px 7px;border-radius:5px;
  color:#fff;white-space:nowrap
}}
.score-denom{{font-weight:400;opacity:.7}}
/* Oud systeem 1-10 */
.score-6{{background:#6a1f6a}}
.score-7{{background:#8b1a7a}}
.score-8{{background:#b01080}}
.score-9,.score-10{{background:var(--gradient)}}
/* Nieuw systeem 0-100 — prioriteit */
.prio-must_have{{background:var(--gradient);box-shadow:0 0 8px rgba(226,20,139,.4)}}
.prio-sterk{{background:#15803d}}
.prio-interessant{{background:#1d4ed8}}
.prio-zwak{{background:#92400e}}
.prio-afwijzen{{background:#374151}}

/* ── Must-have: eigen visuele taal op kaartlevel ── */
.card[data-prioriteit="must-have"]{{
  border-left:3px solid var(--pink);
  background:linear-gradient(90deg,rgba(226,20,139,.06) 0%,var(--surface) 60%);
}}
.card[data-prioriteit="must-have"] h2{{
  font-size:1rem;
}}
.hot-card[data-prioriteit="must-have"]{{
  border-left:3px solid var(--pink);
  background:linear-gradient(90deg,rgba(226,20,139,.07) 0%,var(--surface) 70%);
}}
.hot-card[data-prioriteit="must-have"] .card-body h2,
.hot-card[data-prioriteit="must-have"] h2,
.hot-card[data-prioriteit="must-have"] h3{{
  color:#fff;
}}

/* ── Regio subtekst onder titel ── */
.card-region{{
  font-size:.68rem;color:var(--muted);
  display:block;margin-top:-6px;margin-bottom:4px;
  letter-spacing:.02em;
}}

/* ── Keyboard focus ring voor navigatie ── */
.card.kb-focus,.hot-card.kb-focus{{
  outline:2px solid rgba(226,20,139,.6);
  outline-offset:2px;
}}

/* ── Keyboard shortcut hint (rechtsonder) ── */
.kb-hint{{
  position:fixed;bottom:16px;right:20px;z-index:200;
  background:var(--surface2);border:1px solid var(--border);
  border-radius:8px;padding:8px 12px;
  font-size:.68rem;color:var(--muted);
  display:flex;gap:10px;align-items:center;
  opacity:0;transition:opacity .3s;pointer-events:none;
}}
.kb-hint.show{{opacity:1;pointer-events:all}}
.kb-hint kbd{{
  background:var(--surface3,#252525);border:1px solid rgba(255,255,255,.12);
  border-radius:3px;padding:1px 5px;font-size:.65rem;
  color:var(--text2);font-family:inherit;
}}
/* Prioriteit label naast score */
.prio-label{{
  font-size:.5rem;font-weight:700;padding:2px 6px;border-radius:4px;
  text-transform:uppercase;letter-spacing:.5px;color:#fff;white-space:nowrap
}}
.prio-label-must_have{{background:rgba(226,20,139,.25);color:#f472b6;border:1px solid rgba(226,20,139,.3)}}
.prio-label-sterk{{background:rgba(21,128,61,.25);color:#4ade80;border:1px solid rgba(21,128,61,.3)}}
.prio-label-interessant{{background:rgba(29,78,216,.25);color:#60a5fa;border:1px solid rgba(29,78,216,.3)}}
.prio-label-zwak{{background:rgba(146,64,14,.25);color:#fbbf24;border:1px solid rgba(146,64,14,.3)}}
/* Ethics badges op kaarten */
.ethics-badge{{
  font-size:.52rem;font-weight:700;padding:2px 6px;border-radius:4px;
  text-transform:uppercase;letter-spacing:.4px;white-space:nowrap;
  display:inline-flex;align-items:center;gap:2px
}}
.ethics-groen{{background:rgba(6,78,59,.6);color:#6ee7b7;border:1px solid rgba(52,211,153,.2)}}
.ethics-oranje{{background:rgba(120,53,15,.6);color:#fcd34d;border:1px solid rgba(251,191,36,.2)}}
.ethics-rood{{background:rgba(127,29,29,.6);color:#fca5a5;border:1px solid rgba(252,165,165,.2)}}
/* Ethics rapport in modal */
.ethics-section{{
  margin:12px 0 0;padding:12px 16px;background:var(--surface3);
  border-radius:8px;border:1px solid var(--border)
}}
.ethics-header{{
  display:flex;align-items:center;justify-content:space-between;
  margin-bottom:10px;cursor:pointer;gap:8px
}}
.ethics-header-title{{
  font-size:.6rem;font-weight:700;text-transform:uppercase;
  letter-spacing:.8px;color:var(--muted)
}}
.ethics-verdict-pill{{
  font-size:.6rem;font-weight:800;padding:3px 9px;border-radius:12px;
  text-transform:uppercase;letter-spacing:.5px
}}
.ethics-verdict-GROEN{{background:#064e3b;color:#6ee7b7}}
.ethics-verdict-ORANJE{{background:#78350f;color:#fcd34d}}
.ethics-verdict-ROOD{{background:#7f1d1d;color:#fca5a5}}
.ethics-bars{{}}
.ethics-row{{display:flex;align-items:center;gap:8px;margin-bottom:5px}}
.ethics-label{{font-size:.58rem;color:var(--text2);width:160px;flex-shrink:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.ethics-bar-track{{flex:1;height:4px;background:var(--surface2);border-radius:2px;overflow:hidden}}
.ethics-bar-fill{{height:100%;border-radius:2px;transition:width .4s ease}}
.ethics-val{{font-size:.55rem;color:var(--muted);width:26px;text-align:right;flex-shrink:0}}
.ethics-aanbeveling{{
  font-size:.68rem;color:var(--text2);margin-top:10px;padding-top:8px;
  border-top:1px solid var(--border);line-height:1.5
}}
/* Breakdown bars in modal */
.breakdown-section{{
  margin:12px 0 0;padding:12px 16px;background:var(--surface3);
  border-radius:8px;border:1px solid var(--border)
}}
.breakdown-title{{
  font-size:.6rem;font-weight:700;text-transform:uppercase;letter-spacing:.8px;
  color:var(--muted);margin-bottom:10px
}}
.breakdown-row{{display:flex;align-items:center;gap:8px;margin-bottom:6px}}
.breakdown-row:last-child{{margin-bottom:0}}
.breakdown-label{{font-size:.62rem;color:var(--text2);width:130px;flex-shrink:0}}
.breakdown-bar-track{{flex:1;height:5px;background:var(--surface2);border-radius:3px;overflow:hidden}}
.breakdown-bar-fill{{height:100%;border-radius:3px;background:var(--gradient);transition:width .4s}}
.breakdown-val{{font-size:.6rem;font-weight:700;color:var(--text2);width:28px;text-align:right;flex-shrink:0}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.5}}}}
.card-date{{font-size:.62rem;color:var(--text2);margin-left:auto;white-space:nowrap;flex-shrink:0}}

.card h2{{font-size:.92rem;font-weight:700;line-height:1.42;color:var(--text);letter-spacing:-.1px}}
.card p{{
  font-size:.78rem;color:var(--text2);line-height:1.62;
  display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden
}}
.full-indicator{{font-size:.65rem;color:var(--muted);font-weight:600}}
.summary-indicator{{font-size:.65rem;color:#888;font-weight:600}}

/* ══ CARD ACTIONS ════════════════════════════════════════════════════════════ */
.card-actions{{
  display:flex;flex-direction:column;gap:6px;margin-top:auto
}}
.card-actions-row{{
  display:flex;gap:5px;align-items:center;flex-wrap:wrap
}}
/* Lees origineel — primaire actie, altijd zichtbaar */
.read-btn{{
  display:inline-flex;align-items:center;gap:5px;
  padding:6px 13px;border-radius:7px;
  font-size:.72rem;font-weight:700;
  background:rgba(226,20,139,.15);
  border:1px solid rgba(226,20,139,.35);
  color:#f472b6;
  transition:all .15s;white-space:nowrap;font-family:inherit;cursor:pointer;
  text-decoration:none
}}
.read-btn:hover{{background:rgba(226,20,139,.28);border-color:rgba(226,20,139,.6);color:#fff}}
/* Bypass betaalmuur — secundaire actie */
.bypass-btn{{
  display:inline-flex;align-items:center;gap:5px;
  padding:6px 11px;border-radius:7px;
  font-size:.72rem;font-weight:600;
  background:rgba(156,45,143,.12);
  border:1px solid rgba(156,45,143,.3);
  color:#c084fc;
  transition:all .15s;white-space:nowrap;font-family:inherit;cursor:pointer;
  text-decoration:none
}}
.bypass-btn:hover{{background:rgba(156,45,143,.25);border-color:rgba(156,45,143,.55);color:#fff}}
/* Favoriet knop */
.fav-btn{{
  display:inline-flex;align-items:center;justify-content:center;
  width:30px;height:30px;border-radius:7px;
  background:rgba(255,255,255,.05);border:1px solid var(--border2);
  color:var(--text2);font-size:.95rem;cursor:pointer;
  transition:all .15s;flex-shrink:0;font-family:inherit;padding:0;line-height:1
}}
.fav-btn:hover{{background:rgba(226,20,139,.15);border-color:rgba(226,20,139,.4);color:#f472b6;transform:scale(1.1)}}
.fav-btn.active{{background:rgba(226,20,139,.18);border-color:rgba(226,20,139,.5);color:#e2148b}}
/* Label knoppen — Interessant / Overslaan */
.label-btn{{
  display:inline-flex;align-items:center;gap:4px;
  padding:5px 10px;border-radius:7px;
  font-size:.68rem;font-weight:700;
  cursor:pointer;transition:all .15s;flex-shrink:0;
  font-family:inherit;white-space:nowrap;
  background:rgba(255,255,255,.05);border:1px solid var(--border2);
  color:var(--text2)
}}
.label-interessant:hover{{background:rgba(21,128,61,.18);border-color:rgba(74,222,128,.4);color:#4ade80}}
.label-interessant.active,
.card[data-human-label="interessant"] .label-interessant,
.hot-card[data-human-label="interessant"] .label-interessant{{
  background:rgba(21,128,61,.22);border-color:#4ade80;color:#4ade80
}}
.label-overslaan:hover{{background:rgba(239,68,68,.13);border-color:rgba(248,113,113,.4);color:#f87171}}
.label-overslaan.active,
.card[data-human-label="overslaan"] .label-overslaan,
.hot-card[data-human-label="overslaan"] .label-overslaan{{
  background:rgba(239,68,68,.18);border-color:#f87171;color:#f87171
}}

/* modal samenvatting */
.summary-content{{padding:4px 0}}
.summary-label{{font-size:.72rem;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.8px;margin-bottom:12px!important}}
.summary-note{{font-size:.75rem;color:var(--muted);font-style:italic;margin-top:16px!important}}

/* favoriet in powned-row verbergen */

/* ══ LIJSTWEERGAVE ═══════════════════════════════════════════════════════════ */
.list-item{{
  display:grid;grid-template-columns:88px 1fr auto;gap:14px;align-items:center;
  padding:14px 16px;background:var(--surface);
  border-radius:var(--radius);cursor:pointer;
  transition:transform .15s ease,box-shadow .15s ease;margin-bottom:10px;
  box-shadow:var(--shadow)
}}
.list-item:hover{{transform:translateX(3px);box-shadow:var(--shadow-lg)}}
.list-thumb{{
  width:88px;height:60px;border-radius:8px;overflow:hidden;
  background:var(--surface2);flex-shrink:0
}}
.list-thumb img{{width:100%;height:100%;object-fit:cover}}
.list-thumb.no-img{{
  display:flex;align-items:center;justify-content:center;
  font-size:1.4rem;font-weight:900;color:rgba(255,255,255,.04)
}}
.list-title{{
  font-size:.86rem;font-weight:600;color:var(--text);line-height:1.4;
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;
  letter-spacing:-.1px
}}
.list-sub{{font-size:.66rem;color:var(--muted);margin-top:5px;display:flex;gap:7px;align-items:center}}
.list-score-badge{{
  flex-shrink:0;font-size:.6rem;font-weight:700;padding:3px 9px;
  border-radius:5px;color:var(--pink);border:1px solid rgba(226,20,139,.25);white-space:nowrap
}}

/* ══ MODAL ═══════════════════════════════════════════════════════════════════ */
.modal-overlay{{
  position:fixed;inset:0;background:rgba(0,0,0,.8);z-index:600;
  display:flex;align-items:center;justify-content:center;padding:20px;
  backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px)
}}
.modal-overlay.hidden{{display:none}}
.modal{{
  background:var(--surface);border:1px solid var(--border2);border-radius:18px;
  max-width:720px;width:100%;max-height:90vh;
  display:flex;flex-direction:column;overflow:hidden;
  box-shadow:0 32px 100px rgba(0,0,0,.8),0 0 0 1px rgba(255,255,255,.04)
}}
.modal-header{{padding:clamp(16px,3vw,22px) clamp(18px,4vw,26px) clamp(14px,2.5vw,18px);border-bottom:1px solid var(--border);flex-shrink:0}}
.modal-topbar{{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}}
.modal-meta{{display:flex;align-items:center;gap:8px;flex-wrap:wrap}}
.modal-close{{
  background:var(--surface2);border:1px solid var(--border);
  border-radius:8px;color:var(--text2);padding:6px 13px;
  cursor:pointer;font-size:.73rem;font-weight:600;
  transition:all .15s;flex-shrink:0;font-family:inherit
}}
.modal-close:hover{{color:var(--text);border-color:var(--border2)}}
.modal-title{{font-size:1.15rem;font-weight:800;line-height:1.28;color:var(--text);letter-spacing:-.2px}}
.modal-ai{{
  margin-top:10px;font-size:.76rem;color:var(--text);line-height:1.6;
  background:rgba(226,20,139,.07);border-left:2px solid var(--pink);
  padding:10px 14px;border-radius:0 8px 8px 0;font-style:italic
}}
.modal-img{{width:100%;max-height:280px;object-fit:cover;display:block;border-radius:8px 8px 0 0}}
.modal-body{{
  padding:clamp(16px,3vw,22px) clamp(18px,4vw,26px);
  overflow-y:auto;flex:1;scroll-behavior:smooth;
  line-height:1.9;font-size:.87rem;color:var(--text2)
}}
.modal-body p{{margin-bottom:14px}}
.btn-label{{
  padding:9px 16px;border-radius:8px;font-size:.76rem;font-weight:700;
  border:1px solid var(--border2);background:rgba(255,255,255,.04);
  cursor:pointer;transition:all .15s;font-family:inherit;color:var(--text2);
  display:inline-flex;align-items:center;gap:5px
}}
.btn-interessant:hover,.btn-interessant.active{{
  background:rgba(21,128,61,.22);border-color:#4ade80;color:#4ade80
}}
.btn-overslaan:hover,.btn-overslaan.active{{
  background:rgba(239,68,68,.18);border-color:#f87171;color:#f87171
}}
.modal-footer{{
  padding:16px 26px;border-top:1px solid var(--border);
  display:flex;gap:8px;flex-wrap:wrap;background:var(--surface);flex-shrink:0
}}
.btn-red{{
  padding:10px 20px;border-radius:9px;
  background:var(--pink);color:#fff;font-size:.8rem;font-weight:700;
  border:none;cursor:pointer;transition:opacity .15s;font-family:inherit;letter-spacing:-.1px
}}
.btn-red:hover{{opacity:.88}}
.btn-dark{{
  padding:10px 16px;border-radius:9px;
  background:transparent;color:var(--text2);
  font-size:.8rem;font-weight:600;border:1px solid var(--border2);
  cursor:pointer;transition:all .15s;font-family:inherit
}}
.btn-dark:hover{{border-color:rgba(156,45,143,.4);color:var(--purple)}}
.no-content{{text-align:center;padding:48px 20px;color:var(--muted)}}
.no-content p{{margin-bottom:12px;line-height:1.65;font-size:.86rem}}

/* ══ DATUMFILTER ═════════════════════════════════════════════════════════════ */
.date-filter{{
  display:flex;align-items:center;gap:6px;flex-wrap:wrap;
  position:sticky;top:106px;z-index:200;
  background:rgba(8,8,15,.88);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
  padding:10px 28px;margin:0 -28px 20px;
  border-bottom:1px solid var(--border)
}}
.date-chip{{
  padding:5px 13px;border-radius:20px;font-size:.72rem;font-weight:600;
  background:var(--surface2);border:1px solid var(--border);
  color:var(--text2);cursor:pointer;transition:all .15s;
  font-family:inherit;white-space:nowrap
}}
.date-chip:hover{{border-color:var(--border2);color:var(--text)}}
.date-chip.active{{
  background:rgba(226,20,139,.12);border-color:rgba(226,20,139,.45);
  color:var(--pink)
}}

/* ══ LOAD MORE ═══════════════════════════════════════════════════════════════ */
#loadMore{{
  display:block;margin:32px auto 0;padding:11px 32px;
  background:transparent;border:1px solid var(--border2);
  border-radius:10px;color:var(--text2);font-size:.8rem;font-weight:600;
  cursor:pointer;transition:all .2s;font-family:inherit;letter-spacing:-.1px
}}
#loadMore:hover{{border-color:rgba(226,20,139,.4);color:var(--pink)}}

.empty{{text-align:center;padding:100px 20px;color:var(--muted)}}
.empty p{{font-size:.87rem;line-height:1.6}}

/* ══ MOBIEL ══════════════════════════════════════════════════════════════════ */
@media(max-width:600px){{

  /* header */
  header{{padding:0 14px;height:54px;gap:10px}}
  .logo-img{{height:24px}}
  .search-wrap{{max-width:none;margin:0 4px}}
  #search{{padding:8px 10px 8px 32px;font-size:.82rem}}
  .hdr-btn{{font-size:.68rem;padding:6px 10px}}

  /* tabs */
  .tabs{{padding:0 14px;top:54px}}
  .tab{{padding:0 12px;height:42px;font-size:.74rem}}

  /* layout */
  .layout{{min-height:calc(100vh - 96px)}}
  .sidebar{{top:96px;height:calc(100vh - 96px)}}
  .sb-backdrop{{top:96px}}
  .main-content{{padding:16px 14px}}
  .date-filter{{top:96px;padding:8px 14px;margin:0 -14px 16px}}

  /* banner */
  .banner{{height:280px;border-radius:10px;margin-bottom:20px}}
  .slide-content{{padding:18px}}
  .slide-title{{font-size:1.1rem;letter-spacing:-.2px}}
  .slide-snippet{{display:none}}
  .slide-btn-primary,.slide-btn-modal{{padding:8px 14px;font-size:.75rem}}
  .banner-arrow{{display:none}}

  /* grid — 1 kolom op mobiel */
  .hot-row{{grid-template-columns:1fr;gap:12px}}
  .grid{{grid-template-columns:1fr;gap:12px}}

  /* hero — stapelen */
  .hero{{grid-template-columns:1fr}}
  .hero .card-img{{height:190px;min-height:unset}}
  .hero .card-body{{padding:18px}}
  .hero h2{{font-size:1.1rem}}

  /* kaarten */
  .card-body{{padding:14px}}
  .card h2{{font-size:.9rem}}
  .hot-card h3{{font-size:.88rem}}

  /* lijst */
  .list-item{{grid-template-columns:72px 1fr auto;padding:10px 12px;gap:10px}}
  .list-thumb{{width:72px;height:50px}}
  .list-title{{font-size:.82rem}}

  /* modal — volledig scherm op mobiel */
  .modal-overlay{{padding:0;align-items:flex-end}}
  .modal{{border-radius:18px 18px 0 0;max-height:92dvh;border-left:none;border-right:none;border-bottom:none;display:flex;flex-direction:column}}
  .modal-header{{padding:16px 18px 14px;flex-shrink:0}}
  .modal-body{{flex:1;min-height:0;padding:16px 18px}}
  .modal-title{{font-size:1rem}}
  .modal-footer{{padding:12px 18px;gap:8px;flex-shrink:0}}
  .btn-red,.btn-dark{{flex:1;justify-content:center;padding:12px}}

  /* load more */
  #loadMore{{width:100%;margin-top:20px}}

  /* sidebar */
  .sidebar.open{{width:80vw;max-width:280px}}
}}

/* kleine telefoons */
@media(max-width:380px){{
  .tab{{padding:0 10px;font-size:.7rem}}
  .banner{{height:240px}}
  .slide-title{{font-size:1rem}}
}}

/* ══ CHAT ════════════════════════════════════════════════════════════════════ */
.chat-fab{{
  position:fixed;bottom:28px;right:28px;z-index:901;
  width:58px;height:58px;border-radius:50%;border:none;cursor:pointer;
  background:var(--gradient);color:#fff;
  display:flex;align-items:center;justify-content:center;
  box-shadow:0 4px 20px rgba(226,20,139,.5);
  transition:transform .18s,box-shadow .18s;
  padding:0
}}
.chat-fab:hover{{transform:scale(1.1) rotate(-8deg);box-shadow:0 6px 28px rgba(226,20,139,.7)}}
.chat-fab svg{{width:30px;height:30px;fill:#fff}}
.chat-fab-badge{{
  position:absolute;top:-4px;right:-4px;
  background:#e2148b;color:#fff;font-size:.6rem;font-weight:800;
  min-width:18px;height:18px;border-radius:9px;padding:0 4px;
  display:none;align-items:center;justify-content:center;
  border:2px solid var(--bg)
}}
.chat-fab-badge.visible{{display:flex}}

.chat-panel{{
  position:fixed;bottom:96px;right:28px;z-index:900;
  width:370px;max-width:calc(100vw - 32px);
  background:var(--surface);border:1px solid var(--border2);
  border-radius:20px;display:flex;flex-direction:column;
  box-shadow:0 8px 40px rgba(0,0,0,.6);
  transform:translateY(16px) scale(.97);opacity:0;pointer-events:none;
  transition:transform .18s cubic-bezier(.34,1.56,.64,1),opacity .15s
}}
.chat-panel.open{{transform:translateY(0) scale(1);opacity:1;pointer-events:all}}

.chat-header{{
  padding:12px 16px;border-bottom:1px solid var(--border);
  display:flex;align-items:center;gap:10px;flex-shrink:0
}}
.chat-avatar{{
  width:40px;height:40px;border-radius:50%;flex-shrink:0;
  background:var(--gradient);
  display:flex;align-items:center;justify-content:center;
  box-shadow:0 2px 10px rgba(226,20,139,.35)
}}
.chat-avatar svg{{width:24px;height:24px}}
.chat-header-title{{font-weight:700;font-size:.9rem;flex:1}}
.chat-header-sub{{font-size:.68rem;color:var(--muted)}}
.chat-rules-btn{{
  background:var(--surface2);border:1px solid var(--border);border-radius:8px;
  color:var(--text2);font-size:.68rem;padding:4px 9px;cursor:pointer;
  transition:all .15s;font-family:inherit
}}
.chat-rules-btn:hover{{border-color:var(--pink);color:var(--pink)}}
.chat-close{{
  width:28px;height:28px;border-radius:50%;border:none;background:var(--surface2);
  color:var(--muted);cursor:pointer;font-size:1rem;display:flex;align-items:center;justify-content:center
}}
.chat-close:hover{{background:var(--surface3);color:var(--text)}}

.chat-article-ctx{{
  margin:8px 12px 0;padding:8px 12px;
  background:rgba(226,20,139,.08);border:1px solid rgba(226,20,139,.2);
  border-radius:10px;font-size:.72rem;color:var(--text2);
  display:flex;align-items:center;gap:8px
}}
.chat-article-ctx span{{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.chat-ctx-clear{{background:none;border:none;color:var(--muted);cursor:pointer;font-size:.9rem;padding:0;line-height:1}}

.chat-messages{{
  flex:1;overflow-y:auto;padding:14px 12px;scroll-behavior:smooth;
  display:flex;flex-direction:column;gap:10px;
  min-height:200px;max-height:340px;
  scrollbar-width:thin;scrollbar-color:var(--surface3) transparent
}}
.chat-msg{{max-width:88%;padding:9px 13px;border-radius:14px;font-size:.82rem;line-height:1.5;word-break:break-word}}
.chat-msg.user{{
  align-self:flex-end;
  background:var(--gradient);color:#fff;
  border-bottom-right-radius:4px
}}
.chat-msg.assistant{{
  align-self:flex-start;
  background:var(--surface2);color:var(--text);
  border-bottom-left-radius:4px;border:1px solid var(--border)
}}
.chat-msg.thinking{{color:var(--muted);font-style:italic;font-size:.78rem}}

.chat-rule-card{{
  align-self:stretch;
  background:rgba(0,229,192,.06);border:1px solid rgba(0,229,192,.25);
  border-radius:12px;padding:10px 12px;font-size:.78rem
}}
.chat-rule-card .rule-label{{color:#00e5c0;font-weight:700;font-size:.68rem;letter-spacing:.5px;margin-bottom:4px}}
.chat-rule-card .rule-text{{color:var(--text);margin-bottom:8px;line-height:1.4}}
.chat-rule-actions{{display:flex;gap:6px}}
.chat-rule-actions button{{
  flex:1;padding:5px 8px;border-radius:7px;font-size:.72rem;font-weight:700;
  cursor:pointer;border:1px solid;font-family:inherit;transition:all .15s
}}
.btn-save-rule{{background:rgba(0,229,192,.12);border-color:rgba(0,229,192,.35);color:#00e5c0}}
.btn-save-rule:hover{{background:rgba(0,229,192,.25)}}
.btn-skip-rule{{background:var(--surface2);border-color:var(--border);color:var(--muted)}}
.btn-skip-rule:hover{{color:var(--text)}}

.chat-input-row{{
  padding:10px 12px;border-top:1px solid var(--border);
  display:flex;gap:8px;flex-shrink:0
}}
#chatInput{{
  flex:1;background:var(--surface2);border:1px solid var(--border);
  border-radius:10px;color:var(--text);font-size:.82rem;font-family:inherit;
  padding:9px 13px;outline:none;resize:none;transition:border-color .2s;
  max-height:80px;min-height:38px
}}
#chatInput:focus{{border-color:rgba(226,20,139,.5)}}
#chatInput::placeholder{{color:var(--muted)}}
.chat-send-btn{{
  width:38px;height:38px;border-radius:10px;border:none;flex-shrink:0;
  background:var(--gradient);color:#fff;cursor:pointer;font-size:1rem;
  display:flex;align-items:center;justify-content:center;
  transition:opacity .15s;align-self:flex-end
}}
.chat-send-btn:disabled{{opacity:.4;cursor:default}}

/* zoekresultaten in chat */
.chat-results{{
  align-self:stretch;display:flex;flex-direction:column;gap:6px
}}
.chat-results-label{{
  font-size:.68rem;color:var(--muted);font-weight:600;letter-spacing:.5px;
  text-transform:uppercase;margin-bottom:2px
}}
.chat-result-card{{
  display:flex;align-items:center;gap:10px;padding:8px 10px;
  background:var(--surface2);border:1px solid var(--border);
  border-radius:10px;cursor:pointer;transition:border-color .15s;
  text-decoration:none
}}
.chat-result-card:hover{{border-color:rgba(226,20,139,.4)}}
.chat-result-thumb{{
  width:42px;height:42px;border-radius:6px;flex-shrink:0;
  object-fit:cover;background:var(--surface3)
}}
.chat-result-thumb.no-img{{
  display:flex;align-items:center;justify-content:center;
  font-size:.8rem;font-weight:700;color:var(--muted)
}}
.chat-result-info{{flex:1;min-width:0}}
.chat-result-title{{
  font-size:.75rem;font-weight:600;color:var(--text);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;line-height:1.3
}}
.chat-result-meta{{font-size:.65rem;color:var(--muted);margin-top:2px}}
.chat-result-open{{
  font-size:.68rem;color:var(--pink);flex-shrink:0;font-weight:600
}}
.chat-no-results{{font-size:.78rem;color:var(--muted);font-style:italic}}

/* regels paneel */
.rules-panel{{
  position:fixed;bottom:96px;right:28px;z-index:901;
  width:370px;max-width:calc(100vw - 32px);
  background:var(--surface);border:1px solid var(--border2);
  border-radius:20px;display:flex;flex-direction:column;
  box-shadow:0 8px 40px rgba(0,0,0,.6);
  transform:translateY(20px) scale(.97);opacity:0;pointer-events:none;
  transition:transform .22s cubic-bezier(.34,1.56,.64,1),opacity .18s;
  max-height:480px
}}
.rules-panel.open{{transform:translateY(0) scale(1);opacity:1;pointer-events:all}}
.rules-header{{padding:14px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px}}
.rules-header h3{{flex:1;font-size:.9rem;margin:0}}
.rules-list{{flex:1;overflow-y:auto;padding:10px 12px;display:flex;flex-direction:column;gap:6px}}
.rule-item{{
  display:flex;align-items:center;gap:8px;padding:8px 10px;
  background:var(--surface2);border:1px solid var(--border);border-radius:10px;
  font-size:.78rem;color:var(--text2)
}}
.rule-item span{{flex:1}}
.rule-del{{background:none;border:none;color:var(--muted);cursor:pointer;font-size:.9rem;padding:2px 6px;border-radius:6px}}
.rule-del:hover{{background:rgba(255,60,60,.15);color:#ff6060}}
.rules-empty{{color:var(--muted);font-size:.8rem;padding:20px;text-align:center}}

/* ══════════════════════════════════════════════════════════
   PREMIUM LAYER — UI/UX overhaul
   ══════════════════════════════════════════════════════════ */

/* ── Typografie verfijning ── */
h2,h3{{letter-spacing:-.025em}}
.card-body h2{{
  font-size:.92rem;font-weight:800;line-height:1.35;
  letter-spacing:-.02em;color:var(--text);
}}
.card-body p{{font-size:.78rem;color:var(--text2);line-height:1.65}}

/* ── Card: scherper, premium ── */
.card{{
  border-radius:12px;
  border:1px solid var(--border);
  box-shadow:none;
  transition:transform .18s cubic-bezier(.4,0,.2,1),
             border-color .18s,
             box-shadow .18s;
}}
.card:hover{{
  transform:translateY(-3px);
  border-color:var(--border2);
  box-shadow:0 12px 40px rgba(0,0,0,.5),0 1px 0 rgba(255,255,255,.04) inset;
}}
.card-img{{min-height:148px;border-radius:0}}
.card-body{{padding:14px 16px;gap:8px}}

/* ── Must-have card: glow + behandeling ── */
.card[data-prioriteit="must-have"]{{
  border-left:3px solid var(--pink)!important;
  border-color:rgba(226,20,139,.25)!important;
  background:linear-gradient(90deg,rgba(226,20,139,.05) 0%,var(--surface) 55%)!important;
}}
.card[data-prioriteit="must-have"]:hover{{
  border-color:rgba(226,20,139,.4)!important;
  box-shadow:0 8px 32px rgba(226,20,139,.15),0 0 0 1px rgba(226,20,139,.1)!important;
}}
.card[data-prioriteit="must-have"] h2{{
  font-size:.96rem;color:#fff!important;
}}

/* ── Hot cards: horizontale lijstweergave (editorial) ── */
.hot-row{{
  display:flex;flex-direction:column;gap:2px;margin-bottom:32px
}}
.hot-card{{
  display:flex;flex-direction:row;align-items:stretch;
  background:transparent;border-radius:10px;
  border:1px solid transparent;
  box-shadow:none;overflow:hidden;
  transition:background .15s,border-color .15s,transform .15s cubic-bezier(.4,0,.2,1);
  min-height:90px;
}}
.hot-card:hover{{
  background:var(--surface)!important;
  border-color:var(--border)!important;
  transform:none!important;
  box-shadow:none!important;
}}
.hot-card .card-img{{
  width:110px;height:auto;flex-shrink:0;
  aspect-ratio:unset;min-height:unset;
  border-radius:8px;
  margin:10px 0 10px 10px;
  overflow:hidden;
}}
.hot-card .card-img img{{
  width:100%;height:100%;object-fit:cover;border-radius:8px;
  transition:transform .4s ease;
}}
.hot-card:hover .card-img img{{transform:scale(1.04)}}
.hot-card .card-body{{
  flex:1;padding:12px 16px;display:flex;flex-direction:column;gap:6px;min-width:0
}}
.hot-card h3{{
  font-size:.88rem;font-weight:800;line-height:1.35;
  letter-spacing:-.02em;color:var(--text);
  -webkit-line-clamp:2;
}}
.hot-reason{{
  font-size:.72rem;color:var(--pink);font-weight:500;opacity:.85;
  -webkit-line-clamp:1;
}}
.hot-card .card-actions{{margin-top:auto;padding-top:0}}

/* Must-have hot card */
.hot-card[data-prioriteit="must-have"]{{
  border-left:3px solid var(--pink)!important;
  background:linear-gradient(90deg,rgba(226,20,139,.06) 0%,transparent 50%)!important;
  border-color:rgba(226,20,139,.18)!important;
}}
.hot-card[data-prioriteit="must-have"]:hover{{
  background:linear-gradient(90deg,rgba(226,20,139,.1) 0%,var(--surface) 50%)!important;
  border-color:rgba(226,20,139,.35)!important;
}}

/* ── Score badge verfijning ── */
.score-badge{{
  font-size:.56rem;font-weight:800;padding:2px 6px;border-radius:4px;
  letter-spacing:.02em;
}}
.prio-must_have{{
  background:linear-gradient(135deg,#e2148b,#9c2d8f)!important;
  box-shadow:0 0 10px rgba(226,20,139,.35)!important;
}}

/* ── Ethics badge verfijning ── */
.ethics-badge{{
  font-size:.54rem;padding:2px 5px;border-radius:4px;
  letter-spacing:.04em;
}}

/* ── Card meta spacing ── */
.card-meta{{gap:4px;margin-bottom:2px}}
.card-date{{margin-left:auto;font-size:.65rem;color:var(--muted);white-space:nowrap}}

/* ── Sectie heading ── */
.sec-title{{font-size:.6rem;letter-spacing:.18em}}
.sec-title b{{color:var(--text2)}}

/* ── Load more verfijning ── */
#loadMore{{
  display:block;margin:28px auto 0;
  padding:10px 28px;border-radius:8px;
  background:var(--surface2);border:1px solid var(--border2);
  color:var(--text2);font-size:.8rem;font-weight:600;
  cursor:pointer;transition:all .18s;font-family:inherit;
}}
#loadMore:hover{{
  background:var(--surface3);color:var(--text);border-color:rgba(255,255,255,.2);
}}

/* ── Sidebar chip verfijning ── */
.chip{{border-radius:7px;padding:6px 9px;font-size:.76rem}}
.chip.active{{
  background:var(--surface2)!important;
  box-shadow:inset 0 0 0 1px rgba(226,20,139,.2);
}}

/* ── Scrollbar ── */
::-webkit-scrollbar{{width:3px;height:3px}}
::-webkit-scrollbar-thumb{{background:var(--surface3);border-radius:2px}}
::-webkit-scrollbar-thumb:hover{{background:#3a3a3a}}

/* ── GSAP animatie classes ── */
.card-anim{{opacity:0;transform:translateY(12px)}}
.hot-anim{{opacity:0;transform:translateX(-8px)}}

/* ── Powned row kaarten ── */
.powned-row{{gap:12px}}
.powned-row .hot-card{{
  border:1px solid var(--border);background:var(--surface)!important;
  border-radius:10px;
}}

/* ── Date filter verfijning ── */
.date-chip{{
  border-radius:7px;font-size:.73rem;font-weight:600;
  padding:5px 12px;border:1px solid transparent;
  transition:all .15s;
}}
.date-chip.active{{
  background:var(--surface2);border-color:var(--border2);color:var(--text);
}}

/* ── Keyboard hint verfijning ── */
.kb-hint{{
  border-radius:10px;padding:10px 14px;
  background:var(--surface2);border:1px solid var(--border2);
  box-shadow:0 4px 20px rgba(0,0,0,.4);
}}
/* ── Dashboard back button ── */
.back-dashboard{{display:flex;align-items:center;gap:5px;padding:5px 12px;border-radius:8px;font-size:.75rem;font-weight:600;color:#a0a0a8;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);cursor:pointer;transition:all .15s;text-decoration:none;flex-shrink:0}}
.back-dashboard:hover{{color:#f0f0f0;background:rgba(226,20,139,.12);border-color:rgba(226,20,139,.3)}}
/* ── Refresh banner ── */
.refresh-banner{{display:none;position:fixed;bottom:24px;left:50%;transform:translateX(-50%);z-index:200;align-items:center;gap:10px;padding:10px 18px;background:#0c0c0f;border:1px solid rgba(226,20,139,.35);border-radius:12px;box-shadow:0 8px 32px rgba(0,0,0,.6);font-size:.8rem;color:#f0f0f0;white-space:nowrap}}
.refresh-banner.show{{display:flex;animation:bannerIn .3s ease}}
@keyframes bannerIn{{from{{opacity:0;transform:translateX(-50%) translateY(10px)}}to{{opacity:1;transform:translateX(-50%) translateY(0)}}}}
.refresh-banner-dot{{width:8px;height:8px;border-radius:50%;background:#e2148b;box-shadow:0 0 6px #e2148b;animation:mapPulse 1.5s ease-out infinite;flex-shrink:0}}
.refresh-banner-btn{{padding:5px 12px;border-radius:7px;background:linear-gradient(135deg,#e2148b,#9c2d8f);color:#fff;font-size:.75rem;font-weight:700;cursor:pointer;border:none;font-family:inherit}}
.refresh-banner-close{{padding:4px 8px;color:#606068;cursor:pointer;border:none;background:none;font-size:1rem;font-family:inherit}}
/* ── Score slider ── */
.sb-score-header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}}
.sb-score-val{{font-size:.75rem;font-weight:800;color:#e2148b;background:rgba(226,20,139,.12);padding:2px 8px;border-radius:5px;min-width:36px;text-align:center}}
.score-slider{{width:100%;-webkit-appearance:none;appearance:none;height:4px;border-radius:2px;outline:none;cursor:pointer;background:var(--surface3);margin:6px 0}}
.score-slider::-webkit-slider-thumb{{-webkit-appearance:none;appearance:none;width:16px;height:16px;border-radius:50%;background:linear-gradient(135deg,#e2148b,#9c2d8f);cursor:pointer;box-shadow:0 0 6px rgba(226,20,139,.4)}}
.score-slider::-moz-range-thumb{{width:14px;height:14px;border-radius:50%;background:linear-gradient(135deg,#e2148b,#9c2d8f);cursor:pointer;border:none}}
.score-slider-labels{{display:flex;justify-content:space-between;font-size:.62rem;color:var(--muted);margin-top:2px}}
/* ── Kaart view ── */
#view-kaart{{display:none;flex-direction:column;height:calc(100vh - 115px);position:relative}}
#view-kaart.active{{display:flex}}
#mapContainer{{flex:1;min-height:0;width:100%;border-radius:14px;overflow:hidden;border:1px solid rgba(255,255,255,.07)}}
#nlMap{{position:absolute;inset:0;background:#0a0a0f}}
.leaflet-container{{background:#0a0a0f!important;font-family:'Inter',system-ui,sans-serif}}
.leaflet-control-attribution{{background:rgba(0,0,0,.7)!important;color:#606068!important;font-size:.6rem!important}}
.leaflet-control-attribution a{{color:#e2148b!important}}
.leaflet-control-zoom a{{background:#141417!important;color:#a0a0a8!important;border-color:rgba(255,255,255,.1)!important}}
.leaflet-control-zoom a:hover{{background:#1e1e22!important;color:#f0f0f0!important}}
.map-pin{{position:relative;display:flex;align-items:center;justify-content:center;border-radius:50%;cursor:pointer;transition:transform .15s}}
.map-pin:hover{{transform:scale(1.3)!important}}
.map-pin-inner{{border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:.55rem;font-weight:800;color:#fff;letter-spacing:-.02em}}
.map-pin-pulse{{position:absolute;inset:-4px;border-radius:50%;animation:mapPulse 2s ease-out infinite;pointer-events:none}}
@keyframes mapPulse{{0%{{opacity:.6;transform:scale(1)}}100%{{opacity:0;transform:scale(2.2)}}}}
.map-popup{{background:#0c0c0f;border:1px solid rgba(255,255,255,.1);border-radius:12px;padding:12px 14px;min-width:220px;max-width:280px;box-shadow:0 8px 32px rgba(0,0,0,.7)}}
.map-popup-source{{display:inline-flex;align-items:center;gap:5px;padding:2px 7px;border-radius:4px;font-size:.62rem;font-weight:700;text-transform:uppercase;margin-bottom:7px;color:#fff}}
.map-popup-title{{font-size:.82rem;font-weight:700;color:#f0f0f0;line-height:1.35;margin-bottom:8px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}}
.map-popup-meta{{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:8px}}
.map-popup-score{{font-size:.65rem;font-weight:800;padding:2px 6px;border-radius:4px}}
.map-popup-prio{{font-size:.62rem;font-weight:700;padding:2px 6px;border-radius:4px;text-transform:uppercase;letter-spacing:.05em}}
.map-popup-link{{display:block;text-align:center;padding:7px;background:linear-gradient(135deg,#e2148b,#9c2d8f);border-radius:7px;font-size:.75rem;font-weight:700;color:#fff;text-decoration:none}}
.leaflet-popup-content-wrapper{{background:transparent!important;border:none!important;box-shadow:none!important;padding:0!important}}
.leaflet-popup-content{{margin:0!important}}
.leaflet-popup-tip-container{{display:none}}
.map-controls{{display:flex;align-items:center;gap:8px;padding:10px 0;flex-wrap:wrap}}
.map-ctrl-btn{{display:flex;align-items:center;gap:6px;padding:7px 14px;border-radius:8px;font-size:.75rem;font-weight:600;color:#a0a0a8;background:#141417;border:1px solid rgba(255,255,255,.08);cursor:pointer;transition:all .15s}}
.map-ctrl-btn:hover,.map-ctrl-btn.active{{color:#f0f0f0;border-color:rgba(226,20,139,.4);background:rgba(226,20,139,.1)}}
.map-stat{{padding:7px 12px;border-radius:8px;font-size:.72rem;color:#606068;background:#0c0c0f;border:1px solid rgba(255,255,255,.06)}}
.map-legend{{display:flex;align-items:center;gap:12px;margin-left:auto;flex-wrap:wrap}}
.legend-item{{display:flex;align-items:center;gap:5px;font-size:.68rem;color:#606068}}
.legend-dot{{width:10px;height:10px;border-radius:50%;flex-shrink:0}}
.user-location-marker{{width:14px;height:14px;border-radius:50%;background:#60a5fa;box-shadow:0 0 0 3px rgba(96,165,250,.3),0 0 12px rgba(96,165,250,.5);animation:userPulse 2s ease-in-out infinite}}
@keyframes userPulse{{0%,100%{{box-shadow:0 0 0 3px rgba(96,165,250,.3),0 0 12px rgba(96,165,250,.5)}}50%{{box-shadow:0 0 0 6px rgba(96,165,250,.15),0 0 20px rgba(96,165,250,.6)}}}}
</style>
</head>
<body>

<!-- ══ WELCOME SCREEN ══ -->
<!-- Auto-refresh banner -->
<div class="refresh-banner" id="refreshBanner">
  <div class="refresh-banner-dot"></div>
  <span id="refreshBannerText">Nieuwe artikelen beschikbaar</span>
  <button class="refresh-banner-btn" onclick="location.reload()">Vernieuwen</button>
  <button class="refresh-banner-close" onclick="document.getElementById('refreshBanner').classList.remove('show')" title="Sluiten">✕</button>
</div>

<!-- ══ HEADER ══ -->
<header>
  <button class="sidebar-toggle" id="sidebarToggle" onclick="toggleSidebar()" title="Filters">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3">
      <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="16" y2="12"/><line x1="3" y1="18" x2="12" y2="18"/>
    </svg>
  </button>
  <div class="logo" onclick="location.href='/dashboard'" title="Terug naar dashboard" style="cursor:pointer">
    <img class="logo-img" src="https://www.google.com/s2/favicons?sz=64&domain=powned.tv" alt="PowNed" style="border-radius:6px">
    <span class="logo-tag">Redactie</span>
  </div>
  <a href="/dashboard" class="back-dashboard">
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
    Dashboard
  </a>
  <div class="search-wrap">
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
      <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
    </svg>
    <input id="search" type="search" placeholder="Zoek in artikelen…" autocomplete="off">
  </div>
  <div class="pipeline-status" id="pipelineStatus" title="Pipeline laatste run">
    <span class="ps-dot {"ok" if _pipeline_ok else "warn"}"></span>
    <span class="ps-age" id="psAge">⚡ {_pipeline_age}</span>
    {"<span class='ps-new'>+" + str(_pipeline_new) + " nieuw</span>" if _pipeline_new > 0 else ""}
  </div>
  <div class="hdr-right">
    <span class="counter"><strong id="count">{total}</strong> artikelen</span>
    <button class="hdr-btn" onclick="showRefreshInfo()">↻ Nieuwe artikelen</button>
    <a href="https://www.powned.tv" target="_blank" class="hdr-btn">PowNed.tv ↗</a>
    <div class="hdr-divider"></div>
    <a href="https://syncstudio.nl" target="_blank" class="syncstudio-badge" title="Gemaakt door SyncStudio">
      <span class="ss-made">made by</span>
      <span class="ss-logo"><b>SYNC</b><span class="ss-teal">STUDIO.</span></span>
    </a>
  </div>
</header>

<!-- ══ TABS ══ -->
<nav class="tabs">
  <button class="tab active" data-tab="relevant">PowNed Relevant <span class="tab-badge" id="tb-relevant">{len(hot_items)}</span></button>
  <button class="tab" data-tab="feed">📰 Alle artikelen <span class="tab-badge" id="tb-feed">{total}</span></button>
  <button class="tab" data-tab="list">☰ Lijst</button>
  <button class="tab" data-tab="favorieten">♥ Favorieten <span class="tab-badge" id="tb-favorieten">0</span></button>
  <button class="tab" data-tab="kaart">🗺️ Kaart <span class="tab-badge" id="tb-kaart" style="background:rgba(226,20,139,.2);color:#e2148b">NL</span></button>
</nav>

<!-- ══ LAYOUT ══ -->
<div class="sb-backdrop" id="sbBackdrop" onclick="toggleSidebar()"></div>
<div class="layout">

  <!-- SIDEBAR -->
  <aside class="sidebar" id="sidebar">
    <div class="sidebar-inner">
      <div class="sb-section">
        <div class="sb-score-header">
          <span class="sb-label">📊 Relevantie</span>
          <span class="sb-score-val" id="scoreVal">Alles</span>
        </div>
        <input type="range" id="scoreSlider" min="0" max="100" value="0" step="5" class="score-slider">
        <div class="score-slider-labels"><span>0</span><span>50</span><span>100</span></div>
      </div>
      <div class="sb-divider"></div>
      <div class="sb-section">
        <span class="sb-label">⚖️ Ethiek</span>
        <div class="ethics-filter-row">
          <button class="ethics-chip ethics-chip-groen" data-type="ethics" data-val="GROEN" onclick="void(0)">
            <span class="edot edot-groen"></span>GROEN
            <span class="chip-count">{ethics_counts.get("GROEN",0)}</span>
          </button>
          <button class="ethics-chip ethics-chip-oranje" data-type="ethics" data-val="ORANJE" onclick="void(0)">
            <span class="edot edot-oranje"></span>ORANJE
            <span class="chip-count">{ethics_counts.get("ORANJE",0)}</span>
          </button>
          <button class="ethics-chip ethics-chip-rood" data-type="ethics" data-val="ROOD" onclick="void(0)">
            <span class="edot edot-rood"></span>ROOD
            <span class="chip-count">{ethics_counts.get("ROOD",0)}</span>
          </button>
        </div>
      </div>
      <div class="sb-divider"></div>
      <div class="sb-section">
        <span class="sb-label">📍 Plaatsen</span>
        {"".join(
          f'<button class="chip" data-type="city" data-val="{c}" style="--c:#00a896">'
          f'<span class="chip-dot"></span>'
          f'<span class="chip-name">{c}</span>'
          f'<span class="chip-count">{_city_counter[c]}</span></button>'
          for c in top_cities
        )}
      </div>
      <div class="sb-divider"></div>
      <div class="sb-section">
        <span class="sb-label">📰 Nieuws</span>
        {nieuws_chips}
      </div>
      <div class="sb-divider"></div>
      <div class="sb-section">
        <span class="sb-label">🏛️ Politici &amp; Sociaal</span>
        {politici_chips}
      </div>
      <div class="sb-divider"></div>
      <div class="sb-section">
        <span class="sb-label">🗺️ Regio's</span>
        {regionaal_chips}
      </div>
    </div>
    <button class="sb-clear" id="clearBtn" onclick="clearFilters()" style="display:none">✕ Wis alle filters</button>
  </aside>

  <!-- MAIN -->
  <main class="main-content">

    <!-- DATUMFILTER — gedeeld voor relevant + feed -->
    <div class="date-filter" id="dateFilter">
      <button class="date-chip active" data-days="0" onclick="setDateFilter(this)">Alles</button>
      <button class="date-chip" data-days="1" onclick="setDateFilter(this)">Vandaag</button>
      <button class="date-chip" data-days="2" onclick="setDateFilter(this)">48 uur</button>
      <button class="date-chip" data-days="3" onclick="setDateFilter(this)">3 dagen</button>
      <button class="date-chip" data-days="7" onclick="setDateFilter(this)">Deze week</button>
    </div>

    <!-- NIEUW SECTIE — gedeeld voor alle tabs -->
    <div class="nieuw-bar" id="nieuwBar">
      <span class="nieuw-dot"></span>
      <span class="nieuw-label" id="nieuwLabel">Nieuw</span>
      <span class="nieuw-sub" id="nieuwSub"></span>
      <button class="nieuw-dismiss" onclick="dismissNieuw()">Alles gezien ✓</button>
    </div>

    <!-- TAB: RELEVANT -->
    <div class="view active" id="view-relevant">

      <!-- EDITORIAL GRID (vervangt slider) -->
      <div class="editorial-grid" id="editorialGrid">
        {editorial_html}
      </div>
      {"" if not powned_html else f'''<div class="sec">
        <span class="sec-title"><b>Al op PowNed.tv</b> — recent gepubliceerd</span>
        <div class="sec-line"></div>
        <a href="https://www.powned.tv" target="_blank" class="sec-link">PowNed.tv ↗</a>
      </div>
      <div class="powned-row" id="pownedRow">{powned_html}</div>'''}
      <div class="sec">
        <span class="sec-title"><b>Top gescoord</b> door AI — overige items</span>
        <div class="sec-line"></div>
      </div>
      <div class="hot-row" id="hotRow">{hot_html}</div>
      <div class="empty" id="hotEmpty" style="display:none"><p>Geen relevante artikelen gevonden voor deze filter.</p></div>
    </div>

    <!-- TAB: FEED -->
    <div class="view" id="view-feed">
      <!-- EDITORIAL GRID ook in alle-artikelen tab -->
      <div class="editorial-grid" id="editorialGridFeed">
        {editorial_html}
      </div>
      <div class="grid" id="grid">{grid_html}</div>
      <div class="empty" id="empty" style="display:none"><p>Geen artikelen gevonden.</p></div>
      <button id="loadMore" onclick="loadMore()">Laad meer artikelen ↓</button>
    </div>

    <!-- TAB: LIJST -->
    <div class="view" id="view-list">
      <div id="listView"></div>
    </div>

    <!-- TAB: FAVORIETEN -->
    <div class="view" id="view-favorieten">
      <div id="favGrid" class="grid"></div>
      <div class="empty" id="favEmpty" style="display:none">
        <p>Nog geen favorieten opgeslagen.<br>Klik op het ♥ hartje op een artikel om het toe te voegen.</p>
      </div>
    </div>

    <div class="view" id="view-kaart">
      <div class="map-controls">
        <button class="map-ctrl-btn" id="btnMyLocation" onclick="mapGoToMyLocation()">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/></svg>
          Mijn locatie
        </button>
        <button class="map-ctrl-btn active" id="btnMapAll" onclick="mapFilterPrio('')">Alle prioriteiten</button>
        <button class="map-ctrl-btn" id="btnMapMust" onclick="mapFilterPrio('must-have')">🔥 Must-have</button>
        <button class="map-ctrl-btn" id="btnMapShould" onclick="mapFilterPrio('should-have')">⚡ Should-have</button>
        <div class="map-stat">Gepind: <strong id="mapPinCount">0</strong> artikelen</div>
        <div class="map-legend">
          <div class="legend-item"><div class="legend-dot" style="background:#e2148b;box-shadow:0 0 6px #e2148b"></div>Must-have</div>
          <div class="legend-item"><div class="legend-dot" style="background:#f59e0b"></div>Should-have</div>
          <div class="legend-item"><div class="legend-dot" style="background:#60a5fa"></div>Nice-to-have</div>
          <div class="legend-item"><div class="legend-dot" style="background:#60a5fa;box-shadow:0 0 0 2px rgba(96,165,250,.3)"></div>Jouw locatie</div>
        </div>
      </div>
      <div id="mapContainer">
        <div id="nlMap"></div>
      </div>
    </div>

  </main>
</div>

<!-- ══ MODAL ══ -->
<div class="modal-overlay hidden" id="modalOverlay" onclick="closeModal(event)">
  <div class="modal">
    <div class="modal-header">
      <div class="modal-topbar">
        <div class="modal-meta" id="modalMeta"></div>
        <button class="modal-close" onclick="closeModalDirect()">✕ Sluiten</button>
      </div>
      <h2 class="modal-title" id="modalTitle"></h2>
      <div class="modal-ai" id="modalAI" style="display:none"></div>
      <div id="modalBreakdown" style="display:none"></div>
      <div id="modalEthics" style="display:none"></div>
    </div>
    <div class="modal-body" id="modalBody"></div>
    <div class="modal-footer" id="modalFooter"></div>
  </div>
</div>

<script>
// ── TABS ──────────────────────────────────────────────────────────────────────
function switchTab(name) {{
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
  document.querySelectorAll('.view').forEach(v => v.classList.toggle('active', v.id === 'view-' + name));
  const showDateFilter = name === 'relevant' || name === 'feed';
  document.getElementById('dateFilter').style.display = showDateFilter ? '' : 'none';
  if (name === 'list') buildList();
  if (name === 'favorieten') buildFavGrid();
  if (name === 'kaart') setTimeout(() => {{ initMap(); if (nlMap) nlMap.invalidateSize(); }}, 80);
}}
document.querySelectorAll('.tab').forEach(t =>
  t.addEventListener('click', () => {{
    if (t.dataset.tab === 'feed' || t.dataset.tab === 'relevant') clearFilters();
    switchTab(t.dataset.tab);
  }})
);

// ── FAVORIETEN ────────────────────────────────────────────────────────────────
function getFavs() {{
  try {{ return JSON.parse(localStorage.getItem('powned_favs2') || '{{}}'); }}
  catch {{ return {{}}; }}
}}
function saveFavs(obj) {{
  localStorage.setItem('powned_favs2', JSON.stringify(obj));
}}
function cardToData(card) {{
  return {{
    url:       card.dataset.url,
    title:     card.dataset.title,
    source:    card.dataset.source || '',
    color:     card.dataset.color || '#555',
    img:       card.dataset.img || '',
    pub:       card.dataset.pub || '',
    full:      card.dataset.full || '',
    reason:    card.dataset.reason || '',
    breakdown: card.dataset.breakdown || '',
    prioriteit: card.dataset.prioriteit || '',
  }};
}}
function buildFavCard(d) {{
  const img = d.img
    ? `<div class="card-img"><img src="${{d.img}}" alt="" loading="lazy" onerror="this.parentElement.remove()"></div>`
    : `<div class="card-img placeholder" style="background:linear-gradient(135deg,#1a0a0a,#3d0000)"><span>${{(d.source||'?')[0].toUpperCase()}}</span></div>`;
  return `<article class="card"
    data-url="${{d.url}}" data-title="${{d.title}}" data-source="${{d.source}}"
    data-color="${{d.color}}" data-img="${{d.img}}" data-pub="${{d.pub}}"
    data-full="${{d.full}}" data-reason="${{d.reason}}"
    data-breakdown="${{d.breakdown||''}}" data-prioriteit="${{d.prioriteit||''}}">
    ${{img}}
    <div class="card-body">
      <div class="card-meta">
        <span class="badge" style="background:${{d.color}}">${{d.source}}</span>
      </div>
      <h2>${{d.title}}</h2>
      <div class="card-actions">
        <a class="read-btn" href="${{d.url}}" target="_blank" rel="noopener" onclick="event.stopPropagation()">Lees origineel ↗</a>
        <button class="fav-btn active" onclick="event.stopPropagation();toggleFav(this)" title="Verwijder uit favorieten">♥</button>
      </div>
    </div>
  </article>`;
}}
function _sessionInfo() {{
  try {{ const s = JSON.parse(localStorage.getItem('powned_session')||'null'); return {{email:s?.email||'',name:s?.name||''}}; }}
  catch {{ return {{email:'',name:''}}; }}
}}
function toggleFav(btn) {{
  const card = btn.closest('article');
  const url  = card.dataset.url;
  const favs = getFavs();
  const {{email, name}} = _sessionInfo();
  if (favs[url]) {{
    delete favs[url];
    document.querySelectorAll('article[data-url]').forEach(c => {{
      if (c.dataset.url === url) c.querySelector('.fav-btn')?.classList.remove('active');
    }});
    fetch('/label', {{method:'POST', headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{url, label:'overslaan', user_email:email, user_name:name}})
    }}).catch(()=>{{}});
  }} else {{
    favs[url] = cardToData(card);
    document.querySelectorAll('article[data-url]').forEach(c => {{
      if (c.dataset.url === url) c.querySelector('.fav-btn')?.classList.add('active');
    }});
    btn.animate([{{transform:'scale(1.5)'}},{{transform:'scale(1)'}}], {{duration:250}});
    fetch('/label', {{method:'POST', headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{url, label:'favoriet', user_email:email, user_name:name}})
    }}).catch(()=>{{}});
  }}
  saveFavs(favs);
  updateFavCount();
  if (document.getElementById('view-favorieten').classList.contains('active')) buildFavGrid();
}}
function updateFavCount() {{
  document.getElementById('tb-favorieten').textContent = Object.keys(getFavs()).length;
}}
function addFavByUrl(url) {{
  if (!url) return;
  const favs = getFavs();
  if (favs[url]) return; // al opgeslagen
  // Zoek kaart in DOM
  const card = document.querySelector(`article[data-url="${{url}}"]`);
  if (card) {{
    favs[url] = cardToData(card);
    card.querySelector('.fav-btn')?.classList.add('active');
  }} else if (articleCtx && articleCtx.url === url) {{
    // Gebruik chat-context als fallback
    favs[url] = {{
      url,
      title:     articleCtx.title || url,
      source:    articleCtx.source || '',
      color:     '#555',
      img:       '',
      pub:       '',
      full:      articleCtx.summary || '',
      reason:    '',
      breakdown: '',
      prioriteit: articleCtx.score || '',
    }};
  }} else {{
    favs[url] = {{ url, title: url, source: '', color: '#555', img: '', pub: '', full: '', reason: '', breakdown: '', prioriteit: '' }};
  }}
  saveFavs(favs);
  updateFavCount();
  if (document.getElementById('view-favorieten').classList.contains('active')) buildFavGrid();
}}
function buildFavGrid() {{
  const favs  = getFavs();
  const grid  = document.getElementById('favGrid');
  const empty = document.getElementById('favEmpty');
  const list  = Object.values(favs);
  if (!list.length) {{ grid.innerHTML = ''; empty.style.display = ''; return; }}
  empty.style.display = 'none';
  grid.innerHTML = list.map(buildFavCard).join('');
  grid.querySelectorAll('article').forEach(c => c.addEventListener('click', () => openModal(c)));
}}
// ── Gebruikersnaam in header ───────────────────────────────────────────────────
(function() {{
  try {{
    const s = JSON.parse(localStorage.getItem('powned_session') || 'null');
    if (!s || !s.email) return;
    document.addEventListener('DOMContentLoaded', function() {{
      const hdr = document.querySelector('.hdr-right');
      if (!hdr) return;
      const user = document.createElement('span');
      user.style.cssText = 'font-size:.75rem;color:var(--text2);font-weight:600';
      user.textContent = '👤 ' + (s.name || s.email.split('@')[0]);
      hdr.prepend(user);
    }});
  }} catch(e) {{}}
}})();
// Init: herstel hartjes bij pagina-load

document.addEventListener('DOMContentLoaded', () => {{
  const favs = getFavs();
  document.querySelectorAll('article[data-url]').forEach(card => {{
    if (favs[card.dataset.url]) card.querySelector('.fav-btn')?.classList.add('active');
  }});
  updateFavCount();
}});

// ── BANNER / SLIDER ───────────────────────────────────────────────────────────
const slides = [...document.querySelectorAll('.slide')];
const dots   = [...document.querySelectorAll('.dot')];
const BANNER_INTERVAL = 5000;
let bannerIdx = 0, bannerTimer = null, bannerStart = 0, bannerPaused = false;

function bannerGo(idx) {{
  slides[bannerIdx].classList.remove('active');
  dots[bannerIdx]?.classList.remove('active');
  bannerIdx = (idx + slides.length) % slides.length;
  slides[bannerIdx].classList.add('active');
  dots[bannerIdx]?.classList.add('active');
  bannerStart = Date.now();
  document.getElementById('bannerProgress').style.width = '0%';
}}
function bannerStep(d) {{ clearInterval(bannerTimer); bannerGo(bannerIdx + d); startBannerTimer(); }}
function startBannerTimer() {{
  clearInterval(bannerTimer);
  bannerStart = Date.now();
  bannerTimer = setInterval(() => {{
    if (!bannerPaused) bannerGo(bannerIdx + 1);
  }}, BANNER_INTERVAL);
}}
// voortgangsbalk
setInterval(() => {{
  if (bannerPaused || !slides.length) return;
  const pct = Math.min(100, (Date.now() - bannerStart) / BANNER_INTERVAL * 100);
  document.getElementById('bannerProgress').style.width = pct + '%';
}}, 80);

dots.forEach(d => d.addEventListener('click', e => {{
  e.stopPropagation();
  clearInterval(bannerTimer);
  bannerGo(+d.dataset.slide);
  startBannerTimer();
}}));

const banner = document.getElementById('banner');
if (banner) {{
  banner.addEventListener('mouseenter', () => bannerPaused = true);
  banner.addEventListener('mouseleave', () => {{ bannerPaused = false; bannerStart = Date.now(); }});
  banner.addEventListener('click', e => {{
    if (e.target.closest('.banner-arrow,.dot,.slide-actions')) return;
    const slide = slides[bannerIdx];
    if (slide) openModal(slide);
  }});
}}
if (slides.length) startBannerTimer();

// ── LIJST ──────────────────────────────────────────────────────────────────
function buildList() {{
  const q = document.getElementById('search').value.toLowerCase().trim();
  const all = [document.querySelector('.hero'), ...document.querySelectorAll('#grid .card')].filter(Boolean);
  const filtered = all.filter(c => {{
    const matchSrc = !activeSource || c.dataset.source === activeSource;
    const matchReg = !activeRegion || c.dataset.region === activeRegion;
    const matchQ   = !q || (c.querySelector('h2')?.textContent||'').toLowerCase().includes(q)
                        || (c.dataset.source||'').toLowerCase().includes(q);
    return matchSrc && matchReg && matchQ;
  }});
  document.getElementById('listView').innerHTML = filtered.map(c => {{
    const title = c.querySelector('h2')?.textContent || '';
    const src   = c.dataset.source || '';
    const img   = c.dataset.img || '';
    const color = c.dataset.color || '#555';
    const pub   = c.querySelector('time')?.textContent || '';
    const score = c.querySelector('.score-badge')?.textContent || '';
    const thumb = img
      ? `<div class="list-thumb"><img src="${{img}}" loading="lazy" onerror="this.parentElement.className='list-thumb no-img';this.remove()"></div>`
      : `<div class="list-thumb no-img" style="background:var(--surface3)">${{src[0]||'?'}}</div>`;
    const prio = c.dataset.prioriteit || '';
    const prioClass = prio ? `prio-label prio-label-${{prio.replace('-','_')}}` : '';
    return `<div class="list-item"
        data-source="${{src}}" data-url="${{c.dataset.url||''}}"
        data-title="${{c.dataset.title||''}}" data-source-label="${{src}}"
        data-img="${{img}}" data-color="${{color}}"
        data-full="${{c.dataset.full||''}}" data-reason="${{c.dataset.reason||''}}"
        data-breakdown="${{c.dataset.breakdown||''}}" data-prioriteit="${{prio}}"
        onclick="openModal(this)">
      ${{thumb}}
      <div>
        <div class="list-title">${{title}}</div>
        <div class="list-sub">
          <span class="badge" style="background:${{color}}">${{src}}</span>
          ${{pub ? `<span>${{pub}}</span>` : ''}}
        </div>
      </div>
      ${{prio ? `<span class="${{prioClass}}">${{prio}}</span>` : (score ? `<span class="list-score-badge">${{score}}</span>` : '')}}
    </div>`;
  }}).join('');
}}

// ── RELATIVE TIME ─────────────────────────────────────────────────────────────
function relTime(iso) {{
  if (!iso) return '';
  const d = new Date(iso), diff = (Date.now() - d) / 1000;
  if (isNaN(d) || diff < 0) return '';
  if (diff < 60) return 'zojuist';
  if (diff < 120) return '1 min geleden';
  if (diff < 3600) return Math.floor(diff/60) + ' min geleden';
  if (diff < 7200) return '1 uur geleden';
  if (diff < 86400) return Math.floor(diff/3600) + ' uur geleden';
  if (diff < 172800) return 'gisteren';
  const days=['zo','ma','di','wo','do','vr','za'];
  const months=['jan','feb','mrt','apr','mei','jun','jul','aug','sep','okt','nov','dec'];
  return days[d.getDay()] + ' ' + d.getDate() + ' ' + months[d.getMonth()];
}}
document.querySelectorAll('time.card-date').forEach(el => {{
  const rel = relTime(el.closest('[data-pub]')?.dataset.pub);
  if (rel) el.textContent = rel;
}});

// ── HUMAN LABELS ─────────────────────────────────────────────────────────────
function setLabel(btn, label) {{
  const card = btn.closest('article');
  const url  = card.dataset.url;
  if (!url) return;
  const cur  = card.dataset.humanLabel;
  const newLabel = cur === label ? '' : label;
  card.dataset.humanLabel = newLabel;
  const {{email, name}} = _sessionInfo();
  fetch('/label', {{
    method: 'POST',
    headers: {{'Content-Type':'application/json'}},
    body: JSON.stringify({{url, label: newLabel || 'overslaan', user_email: email, user_name: name}}),
  }}).catch(()=>{{}});
  document.querySelectorAll(`article[data-url="${{url}}"]`).forEach(c => {{ c.dataset.humanLabel = newLabel; }});
}}
function setLabelModal(btn, label, url) {{
  const {{email, name}} = _sessionInfo();
  fetch('/label', {{
    method: 'POST',
    headers: {{'Content-Type':'application/json'}},
    body: JSON.stringify({{url, label, user_email: email, user_name: name}}),
  }}).catch(()=>{{}});
  document.querySelectorAll(`article[data-url="${{url}}"]`).forEach(c => {{
    c.dataset.humanLabel = label;
  }});
  // Update modal knoppen
  btn.closest('.modal-footer').querySelectorAll('.btn-label').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}}

// ── MODAL ─────────────────────────────────────────────────────────────────────
function openModal(card) {{
  const full      = card.dataset.full || '';
  const url       = card.dataset.url  || '#';
  const title     = card.dataset.title || '';
  const src       = card.dataset.sourceLabel || card.dataset.source || '';
  const color     = card.dataset.color || '#555';
  const img       = card.dataset.img  || '';
  const reason    = card.dataset.reason || '';
  const breakdown = card.dataset.breakdown || '';
  const prioriteit = card.dataset.prioriteit || '';
  const pub       = card.querySelector('time')?.textContent || '';

  document.getElementById('modalTitle').textContent = title;

  const pubIso = card.dataset.pub || '';
  const relPub = relTime(pubIso);
  const prioLabels = {{'must-have':'must-have','sterk':'sterk','interessant':'interessant','zwak':'zwak','afwijzen':'afwijzen'}};
  const prioColors = {{'must-have':'#e2148b','sterk':'#15803d','interessant':'#1d4ed8','zwak':'#92400e','afwijzen':'#374151'}};
  const prioHtml = prioriteit
    ? `<span style="font-size:.55rem;font-weight:700;padding:2px 8px;border-radius:4px;
        background:${{prioColors[prioriteit]||'#555'}};color:#fff;text-transform:uppercase;
        letter-spacing:.5px">${{prioriteit}}</span>`
    : '';
  document.getElementById('modalMeta').innerHTML =
    `<span class="badge" style="background:${{color}}">${{src}}</span>`
    + prioHtml
    + (relPub ? `<span style="font-size:.7rem;color:var(--muted)">${{relPub}}</span>` : '');

  // Redactie feedback
  const aiEl = document.getElementById('modalAI');
  if (reason) {{ aiEl.innerHTML = '✏️ ' + reason; aiEl.style.display = ''; }}
  else aiEl.style.display = 'none';

  // Breakdown bars
  const breakdownEl = document.getElementById('modalBreakdown');
  if (breakdown && breakdown !== 'v2') {{
    try {{
      const bd = JSON.parse(breakdown);
      const rows = [
        ['Viraal & emotie',    bd.viraal,             25],
        ['Visueel potentieel', bd.visueel,             20],
        ['Nieuwswaarde',       bd.nieuwswaarde,        20],
        ['Landelijk potentieel',bd.landelijkPotentieel,20],
        ['Doelgroepfit',       bd.doelgroepfit,        15],
      ];
      const total = rows.reduce((s,[,v])=>s+(v||0),0);
      breakdownEl.innerHTML =
        `<div class="breakdown-section">
          <div class="breakdown-title">Redactiescore: ${{total}}/100</div>`
        + rows.map(([lbl,val,max])=>{{
            const pct = Math.round(((val||0)/max)*100);
            return `<div class="breakdown-row">
              <span class="breakdown-label">${{lbl}}</span>
              <div class="breakdown-bar-track"><div class="breakdown-bar-fill" style="width:${{pct}}%"></div></div>
              <span class="breakdown-val">${{val||0}}/${{max}}</span>
            </div>`;
          }}).join('')
        + `</div>`;
      breakdownEl.style.display = '';
    }} catch(e) {{ breakdownEl.style.display = 'none'; }}
  }} else {{ breakdownEl.style.display = 'none'; }}

  // Ethics (Agent 04) — verdict beschikbaar voor footer, toelichting altijd verborgen
  const ethicsVerdict = card.dataset.ethics || '';
  const ethicsEl      = document.getElementById('modalEthics');
  ethicsEl.innerHTML  = '';
  ethicsEl.style.display = 'none';

  const body = document.getElementById('modalBody');
  const imgHtml = img ? `<img class="modal-img" src="${{img}}" alt="" style="margin:-20px -24px 20px;width:calc(100% + 48px);max-width:none">` : '';
  const summary = card.dataset.summary || '';
  if (full) {{
    const paras = full.split('\\n\\n').filter(p => p.trim().length > 20);
    body.innerHTML = imgHtml + (paras.map(p => `<p>${{p.trim()}}</p>`).join('') || `<p>${{full}}</p>`);
  }} else if (summary) {{
    body.innerHTML = imgHtml + `<div class="summary-content">
      <p class="summary-label">📋 RSS-samenvatting</p>
      <p>${{summary}}</p>
      <p class="summary-note">Volledige tekst staat op de bronsite — klik "Lees origineel" hieronder.</p>
    </div>`;
  }} else {{
    body.innerHTML = imgHtml + `<div class="no-content"><p>Geen tekstinhoud beschikbaar.</p></div>`;
  }}

  const paywallSources = ['AD','Volkskrant','Trouw','De Telegraaf'];
  const showBypass = !full || paywallSources.includes(src);
  const curLabel = card.dataset.humanLabel || '';
  // Sla artikel-context op als globale variabele zodat de Chat-knop het kan lezen
  const scoreVal = prioriteit || (card.querySelector('.score-badge')?.textContent || '');
  window._chatCtx = {{title: title, source: src, score: scoreVal,
    summary: (card.dataset.summary || card.dataset.full || '').slice(0,300), url: url}};
  document.getElementById('modalFooter').innerHTML =
    `<a class="btn-red" href="${{url}}" target="_blank" rel="noopener">Lees origineel ↗</a>`
    + (showBypass ? `<a class="btn-dark" href="https://archive.ph/newest/${{encodeURIComponent(url)}}" target="_blank" rel="noopener">🔓 Bypass betaalmuur</a>` : '')
    + `<button class="btn-label btn-interessant${{curLabel==='interessant'?' active':''}}" onclick="setLabelModal(this,'interessant','${{url.replace(/'/g,\"\\\\'\")}}')" >✓ Interessant</button>`
    + `<button class="btn-label btn-overslaan${{curLabel==='overslaan'?' active':''}}" onclick="setLabelModal(this,'overslaan','${{url.replace(/'/g,\"\\\\'\")}}')" >✗ Overslaan</button>`
    + `<button class="btn-dark" onclick="closeModalDirect();chatFromModal()">💬 Chat</button>`
    + `<button class="btn-dark" id="ethicsBtn" onclick="handleEthicsBtn('${{url.replace(/'/g,"\\\\'")}}',this)">🔍 Ethiekcheck</button>`;

  document.getElementById('modalOverlay').classList.remove('hidden');
  document.body.style.overflow = 'hidden';
}}
function closeModalDirect() {{
  document.getElementById('modalOverlay').classList.add('hidden');
  document.body.style.overflow = '';
}}
function closeModal(e) {{
  if (e.target === document.getElementById('modalOverlay')) closeModalDirect();
}}
document.addEventListener('keydown', e => {{
  if (e.key === 'Escape') {{ closeModalDirect(); document.getElementById('search').blur(); }}
  if (e.key === '/' && document.activeElement !== document.getElementById('search')) {{
    e.preventDefault(); document.getElementById('search').focus();
  }}
}});

document.querySelectorAll('.card, .hot-card').forEach(card =>
  card.addEventListener('click', e => {{
    if (e.target.closest('.read-btn,.bypass-btn')) return;
    openModal(card);
  }})
);

// ── FILTER + ZOEK ─────────────────────────────────────────────────────────────
const allCards  = [...document.querySelectorAll('#grid .card')];
const hotCards  = [...document.querySelectorAll('#hotRow .hot-card')];
const hero      = document.querySelector('.hero');
let activeSource = '', activeRegion = '', activeCity = '', activeEthics = '', activeDays = 0, activeMinScore = 0, page = 1;
const PAGE = {PAGE_SIZE};

function matchCard(c) {{
  const q  = document.getElementById('search').value.toLowerCase().trim();
  const ms = !activeSource || c.dataset.source === activeSource;
  const mr = !activeRegion || c.dataset.region === activeRegion;
  const mc = !activeCity   || (c.dataset.city || '').split(',').map(s=>s.trim()).includes(activeCity);
  const me = !activeEthics || c.dataset.ethics === activeEthics;
  const mq = !q || (c.querySelector('h2,h3')?.textContent||'').toLowerCase().includes(q)
                 || (c.dataset.source||'').toLowerCase().includes(q)
                 || (c.dataset.city||'').toLowerCase().includes(q);
  let md = true;
  if (activeDays > 0) {{
    const pub = c.dataset.pub;
    if (pub) {{
      const diff = (Date.now() - new Date(pub).getTime()) / 864e5;
      md = diff <= activeDays;
    }} else {{
      md = false;
    }}
  }}
  let mscore = true;
  if (activeMinScore > 0) {{
    const bd = c.dataset.breakdown ? JSON.parse(c.dataset.breakdown) : {{}};
    const total = Object.values(bd).reduce((a,b)=>a+b,0);
    mscore = total >= activeMinScore;
  }}
  return ms && mr && mc && me && mq && md && mscore;
}}
function heroOk() {{
  return hero ? matchCard(hero) : false;
}}
function applyFilters() {{
  page = 1;
  const vis = allCards.filter(matchCard);
  allCards.forEach(c => c.style.display = 'none');
  vis.slice(0, page * PAGE).forEach(c => c.style.display = '');
  if (hero) hero.style.display = heroOk() ? '' : 'none';
  const tot = vis.length + (heroOk() ? 1 : 0);
  document.getElementById('count').textContent = tot;
  document.getElementById('empty').style.display = tot === 0 ? '' : 'none';
  document.getElementById('loadMore').style.display = vis.length > PAGE ? '' : 'none';
  const filterActive = !!(activeSource || activeRegion || activeCity || activeEthics || activeDays > 0 || activeMinScore > 0 || document.getElementById('search').value);
  document.getElementById('clearBtn').style.display = filterActive ? '' : 'none';

  // Verberg editorial grids + PowNed.tv sectie bij actieve filter
  const hideTopSections = filterActive ? 'none' : '';
  ['editorialGrid','editorialGridFeed'].forEach(id => {{
    const el = document.getElementById(id);
    if (el) el.style.display = hideTopSections;
  }});
  const pownedRow = document.getElementById('pownedRow');
  if (pownedRow) {{
    pownedRow.style.display = hideTopSections;
    const sec = pownedRow.previousElementSibling;
    if (sec && sec.classList.contains('sec')) sec.style.display = hideTopSections;
  }}

  // Filter ook hot-cards in PowNed Relevant tab
  const visHot = hotCards.filter(matchCard);
  hotCards.forEach(c => c.style.display = 'none');
  visHot.forEach(c => c.style.display = '');
  const hotEmpty = document.getElementById('hotEmpty');
  if (hotEmpty) hotEmpty.style.display = visHot.length === 0 ? '' : 'none';

  if (document.getElementById('view-list').classList.contains('active')) buildList();
  updateEditorialFromFilters();
}}
function loadMore() {{
  page++;
  const vis = allCards.filter(matchCard);
  vis.slice(0, page * PAGE).forEach(c => c.style.display = '');
  if (vis.length <= page * PAGE) document.getElementById('loadMore').style.display = 'none';
}}
document.querySelectorAll('.chip, .ethics-chip').forEach(chip =>
  chip.addEventListener('click', () => {{
    const {{type, val}} = chip.dataset;
    if (type === 'source') {{
      activeSource = activeSource === val ? '' : val;
      activeRegion = ''; activeCity = '';
      document.querySelectorAll('.chip[data-type="source"]').forEach(c =>
        c.classList.toggle('active', c.dataset.val === activeSource));
      document.querySelectorAll('.chip[data-type="region"],.chip[data-type="city"]').forEach(c =>
        c.classList.remove('active'));
    }} else if (type === 'city') {{
      activeCity = activeCity === val ? '' : val;
      activeRegion = ''; activeSource = '';
      document.querySelectorAll('.chip[data-type="city"]').forEach(c =>
        c.classList.toggle('active', c.dataset.val === activeCity));
      document.querySelectorAll('.chip[data-type="source"],.chip[data-type="region"]').forEach(c =>
        c.classList.remove('active'));
    }} else if (type === 'ethics') {{
      activeEthics = activeEthics === val ? '' : val;
      document.querySelectorAll('.ethics-chip').forEach(c =>
        c.classList.toggle('active', c.dataset.val === activeEthics));
    }} else {{
      activeRegion = activeRegion === val ? '' : val;
      activeSource = ''; activeCity = '';
      document.querySelectorAll('.chip[data-type="region"]').forEach(c =>
        c.classList.toggle('active', c.dataset.val === activeRegion));
      document.querySelectorAll('.chip[data-type="source"],.chip[data-type="city"]').forEach(c =>
        c.classList.remove('active'));
    }}
    applyFilters();
  }})
);
document.getElementById('search').addEventListener('input', applyFilters);
function setDateFilter(btn) {{
  activeDays = parseInt(btn.dataset.days);
  document.querySelectorAll('.date-chip').forEach(c => c.classList.remove('active'));
  btn.classList.add('active');
  applyFilters();
}}
function clearFilters() {{
  activeSource = ''; activeRegion = ''; activeCity = ''; activeEthics = ''; activeDays = 0; activeMinScore = 0;
  document.querySelectorAll('.chip,.ethics-chip').forEach(c => c.classList.remove('active'));
  document.querySelectorAll('.date-chip').forEach(c => c.classList.toggle('active', c.dataset.days === '0'));
  document.getElementById('search').value = '';
  const slider = document.getElementById('scoreSlider');
  if (slider) {{ slider.value = 0; slider.style.background = ''; }}
  const scoreVal = document.getElementById('scoreVal');
  if (scoreVal) scoreVal.textContent = 'Alles';
  applyFilters();
}}

applyFilters();

// ── EDITORIAL SLIDER ──────────────────────────────────────────────────────────
document.querySelectorAll('.editorial-grid').forEach(function(grid) {{
  var wrap   = grid.querySelector('.ed-slider-wrap');
  if (!wrap) return;
  var slides = Array.from(wrap.querySelectorAll('.ed-hero'));
  var dots   = Array.from(wrap.querySelectorAll('.ed-dot'));
  if (slides.length < 2) return;
  var cur = 0;
  var paused = false;
  var INTERVAL = 5000;

  // Progress bar
  var bar = wrap.querySelector('.ed-progress-bar');
  var progStart = null;
  var progRaf = null;

  function startProgress() {{
    if (!bar) return;
    if (progRaf) cancelAnimationFrame(progRaf);
    bar.style.transition = 'none';
    bar.style.width = '0%';
    progStart = null;
    function tick(ts) {{
      if (paused) {{ progStart = null; bar.style.width = bar.style.width; progRaf = requestAnimationFrame(tick); return; }}
      if (!progStart) progStart = ts;
      var pct = Math.min((ts - progStart) / INTERVAL * 100, 100);
      bar.style.width = pct + '%';
      if (pct < 100) {{ progRaf = requestAnimationFrame(tick); }}
    }}
    progRaf = requestAnimationFrame(tick);
  }}

  function goTo(n) {{
    var prev = slides[cur];
    if (dots[cur]) dots[cur].classList.remove('active');
    prev.classList.remove('active');
    prev.classList.add('leaving');
    setTimeout(function() {{ prev.classList.remove('leaving'); }}, 700);
    cur = (n % slides.length + slides.length) % slides.length;
    slides[cur].classList.add('active');
    if (dots[cur]) dots[cur].classList.add('active');
    startProgress();
  }}

  // Timer loopt altijd — maar slaat over als gepauzeerd
  setInterval(function() {{
    if (!paused) goTo(cur + 1);
  }}, INTERVAL);

  startProgress();

  // Hover: pauzeer automatisch scrollen
  wrap.addEventListener('mouseenter', function() {{ paused = true; }});
  wrap.addEventListener('mouseleave', function() {{ paused = false; }});

  // Dots
  dots.forEach(function(d, i) {{
    d.addEventListener('click', function(e) {{
      e.stopPropagation();
      goTo(i);
    }});
  }});

  // Pijltjes
  var arrL = wrap.querySelector('.ed-arr-l');
  var arrR = wrap.querySelector('.ed-arr-r');
  if (arrL) arrL.addEventListener('click', function(e) {{
    e.stopPropagation();
    goTo(cur - 1);
  }});
  if (arrR) arrR.addEventListener('click', function(e) {{
    e.stopPropagation();
    goTo(cur + 1);
  }});

  // Artikel klikken → modal openen
  slides.forEach(function(slide) {{
    slide.querySelector('.ed-hero-body')?.addEventListener('click', function() {{
      openModal(slide);
    }});
  }});
}});

function updateEditorialFromFilters() {{}}  // editorial grid wordt al verborgen bij filter


// ── FAVORITES SYNC — DB is source of truth, localStorage is UI-cache ─────────
async function syncFavoritesFromDB() {{
  const session = JSON.parse(localStorage.getItem('powned_session') || 'null');
  if (!session?.email) return;
  try {{
    const res  = await fetch(`/api/archief?user=${{encodeURIComponent(session.email)}}&label=favoriet`);
    const data = await res.json();
    const favs = {{}};
    (data.items || []).forEach(item => {{
      favs[item.url] = {{
        url:       item.url,
        title:     item.title || item.url,
        source:    item.source || '',
        color:     '#e2148b',
        img:       item.image_url || '',
        pub:       item.labeled_at || '',
        full:      '', reason: '', breakdown: '', prioriteit: '',
      }};
    }});
    saveFavs(favs);
    updateFavCount();
    // Markeer kaarten in de DOM die al favoriet zijn
    Object.keys(favs).forEach(url => {{
      document.querySelectorAll(`article[data-url="${{url}}"] .fav-btn`).forEach(b => b.classList.add('active'));
    }});
  }} catch(e) {{}}
}}
syncFavoritesFromDB();

// ── EDITORIAL GRID: klik opent modal (beide grids) ───────────────────────────
document.querySelectorAll('.ed-hero, .ed-side').forEach(el =>
  el.addEventListener('click', e => {{
    if (e.target.closest('a, button')) return;
    openModal(el);
  }})
);

// ── NIEUW SECTIE (localStorage) ───────────────────────────────────────────────
(function() {{
  const KEY      = 'powned_last_visit';
  const lastVisit = localStorage.getItem(KEY);

  if (lastVisit) {{
    const since   = new Date(lastVisit);
    const sources = [
      ...document.querySelectorAll('#hotRow .hot-card'),
      ...document.querySelectorAll('#grid .card'),
      ...document.querySelectorAll('.ed-hero, .ed-side'),
    ];
    const newItems = sources.filter(c => {{
      const pub = c.dataset.pub;
      return pub && new Date(pub) > since;
    }});

    if (newItems.length > 0) {{
      const bar   = document.getElementById('nieuwBar');
      const label = document.getElementById('nieuwLabel');
      const sub   = document.getElementById('nieuwSub');
      const sinceStr = since.toLocaleTimeString('nl-NL', {{hour:'2-digit',minute:'2-digit'}});
      label.textContent = `${{newItems.length}} nieuw`;
      sub.textContent   = `sinds ${{sinceStr}}`;
      bar.classList.add('show');

      // Highlight nieuwe items subtiel
      newItems.forEach(c => c.style.outline = '1px solid rgba(226,20,139,.25)');
    }}
  }}

  // Sla huidige sessietijd op bij weggaan
  window.addEventListener('beforeunload', () => {{
    localStorage.setItem(KEY, new Date().toISOString());
  }});
  // En direct bij laden (zodat eerste bezoek ook geteld wordt)
  if (!lastVisit) localStorage.setItem(KEY, new Date().toISOString());
}})();

function dismissNieuw() {{
  document.getElementById('nieuwBar').classList.remove('show');
  document.querySelectorAll('#hotRow .hot-card, #grid .card, .ed-hero, .ed-side').forEach(c => {{
    c.style.outline = '';
  }});
  localStorage.setItem('powned_last_visit', new Date().toISOString());
}}

// ── PIPELINE STATUS (elke 2 min live bijwerken) ───────────────────────────────
(function() {{
  function updatePipelineStatus() {{
    fetch('/refresh', {{method:'GET'}}).then(r => r.json()).then(d => {{
      const dot = document.querySelector('.ps-dot');
      const age = document.getElementById('psAge');
      if (!dot || !age) return;
      // Toon running state
      if (d.running) {{
        dot.className = 'ps-dot ok';
        age.textContent = '⚡ Bezig…';
      }}
    }}).catch(() => {{}});
  }}
  setInterval(updatePipelineStatus, 120000); // elke 2 min
}})();

// ── SIDEBAR TOGGLE ────────────────────────────────────────────────────────────
function toggleSidebar() {{
  const sb   = document.getElementById('sidebar');
  const btn  = document.getElementById('sidebarToggle');
  const bd   = document.getElementById('sbBackdrop');
  const closed = sb.classList.toggle('closed');
  btn.classList.toggle('active', !closed);
  if (bd) bd.classList.toggle('show', !closed);
}}
// Sidebar standaard open op desktop, gesloten op mobiel
(function() {{
  const sb  = document.getElementById('sidebar');
  const btn = document.getElementById('sidebarToggle');
  if (window.innerWidth <= 720) {{
    sb.classList.add('closed');
  }} else {{
    btn.classList.add('active');
  }}
}})();

// ── REFRESH VIA SERVER ────────────────────────────────────────────────────────
function showRefreshInfo() {{
  const overlay = document.createElement('div');
  overlay.id = 'refreshOverlay';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.88);z-index:700;display:flex;align-items:center;justify-content:center;padding:20px;backdrop-filter:blur(6px)';
  overlay.innerHTML = `
    <div style="background:#111;border:1px solid #333;border-radius:10px;max-width:460px;width:100%;padding:28px">
      <h3 id="rfTitle" style="font-size:1rem;font-weight:800;margin-bottom:8px;color:#fff">↻ Nieuwe artikelen ophalen</h3>
      <p id="rfSub" style="font-size:.8rem;color:#888;margin-bottom:18px">Haalt nieuws op, scoort relevantie en herbouwt de feed. Duurt ~1 minuut.</p>
      <div id="rfLog" style="display:none;background:#000;border:1px solid #2a2a2a;border-radius:6px;padding:12px;font-family:monospace;font-size:.72rem;color:#aaa;max-height:160px;overflow-y:auto;margin-bottom:16px;line-height:1.7"></div>
      <div id="rfBar" style="display:none;background:#1a1a1a;border-radius:4px;height:4px;margin-bottom:16px;overflow:hidden">
        <div id="rfBarFill" style="height:100%;background:linear-gradient(90deg,#e2148b,#9c2d8f);width:0%;transition:width .4s;border-radius:4px"></div>
      </div>
      <div style="display:flex;gap:10px">
        <button id="rfBtn" onclick="startRefresh()"
          style="flex:1;padding:10px;background:linear-gradient(90deg,#e2148b,#9c2d8f);color:#fff;border:none;border-radius:6px;font-size:.82rem;font-weight:700;cursor:pointer;font-family:inherit">
          ↻ Start ophalen
        </button>
        <button id="rfClose" onclick="document.getElementById('refreshOverlay').remove()"
          style="padding:10px 16px;background:#1c1c1c;color:#aaa;border:1px solid #333;border-radius:6px;font-size:.82rem;font-weight:700;cursor:pointer;font-family:inherit">
          Sluiten
        </button>
      </div>
    </div>`;
  overlay.addEventListener('click', e => {{ if (e.target === overlay) overlay.remove(); }});
  document.body.appendChild(overlay);
}}

function startRefresh() {{
  const btn  = document.getElementById('rfBtn');
  const log  = document.getElementById('rfLog');
  const bar  = document.getElementById('rfBar');
  const fill = document.getElementById('rfBarFill');
  const sub  = document.getElementById('rfSub');

  btn.disabled = true;
  btn.textContent = '⏳ Bezig…';
  log.style.display = 'block';
  bar.style.display = 'block';
  log.innerHTML = '<span style="color:#e2148b">Pipeline gestart…</span><br>';

  fetch('http://localhost:5001/refresh')
    .then(r => r.json())
    .then(d => {{
      if (d.status === 'running') {{
        log.innerHTML += 'Pipeline is al bezig…<br>';
      }}
      pollStatus(log, fill, sub, btn);
    }})
    .catch(() => {{
      log.innerHTML += '<span style="color:#f00">Server niet bereikbaar. Start de server eerst:<br><code>python3 ~/powned_server.py</code></span>';
      btn.disabled = false;
      btn.textContent = '↻ Probeer opnieuw';
    }});
}}

function pollStatus(log, fill, sub, btn) {{
  let dots = 0, progress = 5;
  const interval = setInterval(() => {{
    fetch('http://localhost:5001/status').then(r => r.json()).then(s => {{
      const lines = s.log || [];
      if (lines.length) {{
        log.innerHTML = lines.map(l =>
          l.startsWith('✓') ? `<span style="color:#e2148b">${{l}}</span>` :
          l.startsWith('❌') ? `<span style="color:#f55">${{l}}</span>` : l
        ).join('<br>') + '<br>';
        log.scrollTop = log.scrollHeight;
        progress = Math.min(90, 5 + lines.length * 8);
        fill.style.width = progress + '%';
      }}
      dots++;
      if (!s.running) {{
        clearInterval(interval);
        fill.style.width = '100%';
        if (s.last === 'success') {{
          log.innerHTML += '<br><span style="color:#e2148b;font-weight:bold">✓ Klaar! Feed wordt herladen…</span>';
          sub.textContent = 'Feed succesvol bijgewerkt.';
          btn.textContent = '✓ Klaar';
          setTimeout(() => location.reload(), 1200);
        }} else {{
          log.innerHTML += `<br><span style="color:#f55">Er ging iets mis: ${{s.last}}</span>`;
          btn.disabled = false;
          btn.textContent = '↻ Probeer opnieuw';
        }}
      }}
    }}).catch(() => clearInterval(interval));
  }}, 1000);
}}
</script>

<!-- ══ CHAT FAB ══ -->
<button class="chat-fab" id="chatFab" onclick="toggleChat()" title="Pow Patrol — PowNed redactie-assistent">
  <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" fill="none">
    <circle cx="42" cy="40" r="24" stroke="white" stroke-width="9"/>
    <line x1="60" y1="58" x2="84" y2="84" stroke="white" stroke-width="10" stroke-linecap="round"/>
  </svg>
  <span class="chat-fab-badge" id="chatBadge">0</span>
</button>

<!-- ══ CHAT PANEL ══ -->
<div class="chat-panel" id="chatPanel">
  <div class="chat-header">
    <div class="chat-avatar">
      <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" fill="none">
        <circle cx="42" cy="40" r="24" stroke="white" stroke-width="9"/>
        <line x1="60" y1="58" x2="84" y2="84" stroke="white" stroke-width="10" stroke-linecap="round"/>
      </svg>
    </div>
    <div>
      <div class="chat-header-title">Pow Patrol</div>
      <div class="chat-header-sub">PowNed redactie-assistent</div>
    </div>
    <button class="chat-close" onclick="toggleChat()">✕</button>
  </div>
  <div id="chatArticleCtx" class="chat-article-ctx" style="display:none">
    <span id="chatCtxTitle"></span>
    <button class="chat-ctx-clear" onclick="clearArticleCtx()" title="Verwijder context">✕</button>
  </div>
  <div class="chat-messages" id="chatMessages">
    <div class="chat-msg assistant">
      Hey! Ik ben <b>Pow Patrol</b> — de redactie-assistent van PowNed. Typ een zoekwoord om artikelen te vinden, of open een artikel en klik "💬 Chat" om erover te praten. 🔍
    </div>
  </div>
  <div class="chat-input-row">
    <textarea id="chatInput" placeholder="Stel een vraag of geef feedback…" rows="1"
      onkeydown="if(event.key==='Enter'&&!event.shiftKey){{event.preventDefault();sendChat()}}"></textarea>
    <button class="chat-send-btn" id="chatSendBtn" onclick="sendChat()">➤</button>
  </div>
</div>

<!-- ══ RULES PANEL ══ -->
<div class="rules-panel" id="rulesPanel">
  <div class="rules-header">
    <h3>⚙ Redactionele regels</h3>
    <button class="chat-close" onclick="toggleRules()">✕</button>
  </div>
  <div class="rules-list" id="rulesList">
    <div class="rules-empty">Nog geen regels. Chat met de assistent om regels te leren!</div>
  </div>
</div>

<script>
// ── Chat state ────────────────────────────────────────
let chatHistory  = [];
let articleCtx   = null;
let rulesCount   = 0;
let chatLoaded   = false;

// Laad de laatste chatberichten uit de database bij eerste opening
async function loadChatHistory() {{
  if (chatLoaded) return;
  chatLoaded = true;
  try {{
    const res  = await fetch('/api/chat/history');
    const data = await res.json();
    if (data.messages && data.messages.length > 0) {{
      const msgs = document.getElementById('chatMessages');
      data.messages.forEach(m => {{
        if (m.role === 'user' || m.role === 'assistant') {{
          appendMsg(m.role, m.content);
          chatHistory.push({{role: m.role, content: m.content}});
        }}
      }});
      msgs.scrollTop = msgs.scrollHeight;
    }}
  }} catch(e) {{}}
}}

function toggleChat() {{
  const p = document.getElementById('chatPanel');
  const r = document.getElementById('rulesPanel');
  r.classList.remove('open');
  p.classList.toggle('open');
  if (p.classList.contains('open')) {{
    document.getElementById('chatInput').focus();
    document.getElementById('chatBadge').classList.remove('visible');
    loadChatHistory();
  }}
}}

function toggleRules() {{
  const r = document.getElementById('rulesPanel');
  const p = document.getElementById('chatPanel');
  p.classList.remove('open');
  r.classList.toggle('open');
  if (r.classList.contains('open')) loadRules();
}}

// Klik buiten chat/sidebar → sluiten
document.addEventListener('click', e => {{
  const chatPanel  = document.getElementById('chatPanel');
  const rulesPanel = document.getElementById('rulesPanel');
  const chatFab    = document.getElementById('chatFab');
  const sidebar    = document.getElementById('sidebar');
  const sbToggle   = document.getElementById('sidebarToggle');

  // Chat sluiten bij klik buiten
  if (chatPanel.classList.contains('open') &&
      !chatPanel.contains(e.target) && !chatFab.contains(e.target)) {{
    chatPanel.classList.remove('open');
  }}
  // Regels sluiten bij klik buiten
  if (rulesPanel.classList.contains('open') &&
      !rulesPanel.contains(e.target) && !chatFab.contains(e.target)) {{
    rulesPanel.classList.remove('open');
  }}
  // Sidebar sluiten bij klik buiten
  if (sidebar.classList.contains('open') &&
      !sidebar.contains(e.target) && e.target !== sbToggle && !sbToggle.contains(e.target)) {{
    sidebar.classList.remove('open');
    const backdrop = document.getElementById('sbBackdrop');
    if (backdrop) backdrop.style.display = 'none';
    sbToggle.classList.remove('active');
  }}
}});

function setArticleCtx(title, source, score, summary, url, prioriteit) {{
  articleCtx = {{title, source, score, summary, url, prioriteit: prioriteit||''}};
  document.getElementById('chatCtxTitle').textContent = '📰 ' + title;
  document.getElementById('chatArticleCtx').style.display = 'flex';
  document.getElementById('chatPanel').classList.add('open');
  document.getElementById('chatInput').focus();
  loadChatHistory();
}}

function clearArticleCtx() {{
  articleCtx = null;
  document.getElementById('chatArticleCtx').style.display = 'none';
}}

function appendMsg(role, content) {{
  const box = document.getElementById('chatMessages');
  const div = document.createElement('div');
  div.className = 'chat-msg ' + role;
  div.textContent = content;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
  return div;
}}

function appendRuleCard(rule) {{
  const box = document.getElementById('chatMessages');
  const card = document.createElement('div');
  card.className = 'chat-rule-card';
  card.innerHTML = `
    <div class="rule-label">💡 VOORSTEL</div>
    <div class="rule-text">${{rule}}</div>
    <div class="chat-rule-actions">
      <button class="btn-save-rule" onclick="saveRule(this, '${{rule.replace(/'/g,"\\'")}}')">✓ Regel opslaan</button>
      <button class="btn-skip-rule" onclick="this.closest('.chat-rule-card').remove()">✗ Negeer</button>
    </div>`;
  box.appendChild(card);
  box.scrollTop = box.scrollHeight;
}}

function appendResults(results, query) {{
  const box = document.getElementById('chatMessages');
  const wrap = document.createElement('div');
  wrap.className = 'chat-results';
  if (!results.length) {{
    wrap.innerHTML = `<div class="chat-results-label">🔍 Zoekresultaten voor "${{query}}"</div>
      <div class="chat-no-results">Geen artikelen gevonden voor "<b>${{query}}</b>".</div>`;
  }} else {{
    const cards = results.map(r => {{
      const thumb = r.image_url
        ? `<img class="chat-result-thumb" src="${{r.image_url}}" loading="lazy" onerror="this.className='chat-result-thumb no-img';this.textContent='${{(r.source||'?')[0]}}';">`
        : `<div class="chat-result-thumb no-img">${{(r.source||'?')[0]}}</div>`;
      const badge = r.prioriteit
        ? `<span style="color:var(--pink);font-weight:700">${{r.prioriteit}}</span> · `
        : '';
      return `<div class="chat-result-card" onclick="searchCardClick(this)"
          data-url="${{r.url||''}}" data-title="${{(r.title||'').replace(/"/g,'&quot;')}}"
          data-source="${{r.source||''}}" data-img="${{r.image_url||''}}"
          data-color="#e2148b" data-source-label="${{r.source||''}}">
        ${{thumb}}
        <div class="chat-result-info">
          <div class="chat-result-title">${{r.title||'(geen titel)'}}</div>
          <div class="chat-result-meta">${{badge}}${{r.source||''}} · ${{r.published_at ? r.published_at.slice(0,10) : ''}}</div>
        </div>
        <span class="chat-result-open">↗</span>
      </div>`;
    }}).join('');
    wrap.innerHTML = `<div class="chat-results-label">🔍 ${{results.length}} resultaten voor "${{query}}"</div>${{cards}}`;
  }}
  box.appendChild(wrap);
  box.scrollTop = box.scrollHeight;
}}

function searchCardClick(el) {{
  // Artikel modal openen vanuit zoekresultaat
  const url = el.dataset.url;
  if (!url) return;
  // Zoek kaart in de feed, anders open direct
  const card = document.querySelector(`article[data-url="${{CSS.escape(url)}}"], .hot-card[data-url="${{CSS.escape(url)}}"]`);
  if (card) {{ openModal(card); return; }}
  window.open(url, '_blank');
}}

async function sendChat() {{
  const input = document.getElementById('chatInput');
  const msg   = input.value.trim();
  if (!msg) return;

  input.value = '';
  input.style.height = 'auto';

  appendMsg('user', msg);
  chatHistory.push({{role:'user', content:msg}});

  const thinking = appendMsg('assistant thinking', '…');
  document.getElementById('chatSendBtn').disabled = true;

  try {{
    // Stuur altijd naar AI — die geeft ZOEK: terug als zoekintentie herkend wordt
    const body = {{
      message: msg,
      history: chatHistory.slice(-12),
      article: articleCtx || null,
    }};
    const res  = await fetch('/chat', {{
      method: 'POST',
      headers: {{'Content-Type':'application/json'}},
      body: JSON.stringify(body),
    }});
    const data = await res.json();

    thinking.remove();

    if (data.error) {{
      appendMsg('assistant', '⚠ ' + data.error);
    }} else {{
      // Zoekcommando afhandelen
      if (data.search_query) {{
        if (data.reply) appendMsg('assistant', data.reply);
        chatHistory.push({{role:'assistant', content: data.reply || ''}});
        const sRes = await fetch('/search', {{
          method: 'POST',
          headers: {{'Content-Type':'application/json'}},
          body: JSON.stringify({{query: data.search_query}}),
        }});
        const sData = await sRes.json();
        appendResults(sData.results || [], data.search_query);
      }} else {{
        appendMsg('assistant', data.reply);
        chatHistory.push({{role:'assistant', content:data.reply}});
        if (data.proposed_rule) appendRuleCard(data.proposed_rule);
        if (data.favorite_url) {{
          addFavByUrl(data.favorite_url);
          appendMsg('assistant', `✓ Artikel toegevoegd aan favorieten.`);
        }}
      }}
    }}
  }} catch(e) {{
    thinking.remove();
    appendMsg('assistant', '⚠ Verbinding mislukt. Zorg dat je de site opent via http://127.0.0.1:5001');
  }}

  document.getElementById('chatSendBtn').disabled = false;
  document.getElementById('chatInput').focus();
}}

async function saveRule(btn, rule) {{
  // Validatie — voorkom onzinnige of schadelijke regels
  const trimmed = rule.trim();
  if (trimmed.length < 10) {{
    btn.textContent = '⚠ Te kort (min 10 tekens)';
    setTimeout(() => {{ btn.textContent = 'Opslaan als regel'; btn.disabled = false; }}, 2500);
    return;
  }}
  if (trimmed.length > 300) {{
    btn.textContent = '⚠ Te lang (max 300 tekens)';
    setTimeout(() => {{ btn.textContent = 'Opslaan als regel'; btn.disabled = false; }}, 2500);
    return;
  }}
  btn.disabled = true;
  btn.textContent = '…';
  try {{
    const res  = await fetch('/rules', {{
      method: 'POST',
      headers: {{'Content-Type':'application/json'}},
      body: JSON.stringify({{rule: trimmed}}),
    }});
    const data = await res.json();
    if (data.ok) {{
      btn.closest('.chat-rule-card').innerHTML =
        '<div style="color:#22c55e;font-size:.78rem;padding:6px 0">✓ Regel opgeslagen — Pow Patrol leert hiervan. Bekijk alle regels via het ⚙-icoontje.</div>';
      rulesCount = data.total || rulesCount + 1;
    }} else {{
      btn.textContent = '⚠ Niet opgeslagen'; btn.disabled = false;
    }}
  }} catch(e) {{
    btn.textContent = '⚠ Fout'; btn.disabled = false;
  }}
}}

function _buildEthicsDetail(ethicsJson, verdict) {{
  try {{
    const er = JSON.parse(ethicsJson);
    const sc = er.scores || {{}};
    const indicatorLabels = {{
      bronherkomst_legitimiteit:    'Bronherkomst',
      paywall_copyright:            'Paywall/copyright',
      privacy_persoonsgegevens:     'Privacy',
      verificatie_framing:          'Verificatie & framing',
      eenzijdigheid_hoor_wederhoor: 'Hoor & wederhoor',
      clickbait_sensatiezucht:      'Clickbait',
      ethische_verkrijging:         'Ethische verkrijging',
    }};
    const barColor = v => v >= 70 ? '#34d399' : v >= 45 ? '#fbbf24' : '#f87171';
    const barsHtml = Object.entries(indicatorLabels).map(([key,lbl]) => {{
      const v = sc[key] ?? 0;
      return `<div class="ethics-row">
        <span class="ethics-label">${{lbl}}</span>
        <div class="ethics-bar-track"><div class="ethics-bar-fill" style="width:${{v}}%;background:${{barColor(v)}}"></div></div>
        <span class="ethics-val">${{v}}</span>
      </div>`;
    }}).join('');
    const aanbeveling = er.aanbeveling ? `<div class="ethics-aanbeveling">💡 ${{er.aanbeveling}}</div>` : '';
    const payAlert    = er.paywall_alert ? `<span style="font-size:.58rem;color:#fcd34d;margin-left:6px">⚠️ Paywall</span>` : '';
    return `<div class="ethics-section">
      <div class="ethics-header">
        <span class="ethics-header-title">🔍 Ethiekcheck Agent</span>
        <span class="ethics-verdict-pill ethics-verdict-${{verdict}}">${{verdict}} ${{er.overall_score||''}}/100${{payAlert}}</span>
      </div>
      <div class="ethics-bars">${{barsHtml}}</div>
      ${{aanbeveling}}
    </div>`;
  }} catch(e) {{ return ''; }}
}}

function handleEthicsBtn(url, btn) {{
  const card = document.querySelector(`article[data-url="${{CSS.escape(url)}}"], .hot-card[data-url="${{CSS.escape(url)}}"]`);
  const ethicsEl = document.getElementById('modalEthics');

  // Toelichting al beschikbaar — tonen/verbergen
  if (card && card.dataset.ethics && card.dataset.ethicsReport) {{
    if (ethicsEl.style.display !== 'none' && ethicsEl.innerHTML) {{
      ethicsEl.style.display = 'none';
      btn.textContent = '🔍 Ethiekcheck';
    }} else {{
      ethicsEl.innerHTML = _buildEthicsDetail(card.dataset.ethicsReport, card.dataset.ethics);
      ethicsEl.style.display = '';
      btn.textContent = '🔍 Ethiekcheck';
    }}
    return;
  }}
  // Nog geen check — uitvoeren
  runEthicsCheck(url, btn);
}}

async function runEthicsCheck(url, btn) {{
  btn.disabled = true;
  btn.textContent = '🔍 Bezig…';
  try {{
    const res  = await fetch('/ethics-check', {{
      method: 'POST',
      headers: {{'Content-Type':'application/json'}},
      body: JSON.stringify({{url}}),
    }});
    const data = await res.json();
    if (data.error) {{ btn.disabled = false; btn.textContent = '⚠ ' + data.error; return; }}

    // Update card data-attributen
    const card = document.querySelector(`article[data-url="${{CSS.escape(url)}}"], .hot-card[data-url="${{CSS.escape(url)}}"]`);
    if (card && data.verdict) {{
      card.dataset.ethics       = data.verdict;
      card.dataset.ethicsReport = JSON.stringify(data.report || {{}});
      // Badge op kaart toevoegen
      const meta = card.querySelector('.card-meta');
      if (meta && !meta.querySelector('.ethics-badge')) {{
        const cls  = {{'GROEN':'ethics-groen','ORANJE':'ethics-oranje','ROOD':'ethics-rood'}}[data.verdict] || '';
        const icon = {{'GROEN':'✅','ORANJE':'⚠️','ROOD':'🚫'}}[data.verdict] || '';
        const badge = document.createElement('span');
        badge.className   = `ethics-badge ${{cls}}`;
        badge.title       = `Ethiekcheck: ${{data.verdict}} (${{data.score}}/100)`;
        badge.textContent = `${{icon}} ${{data.verdict}}`;
        meta.appendChild(badge);
      }}
      // Toelichting tonen in modal
      const ethicsEl = document.getElementById('modalEthics');
      ethicsEl.innerHTML    = _buildEthicsDetail(JSON.stringify(data.report||{{}}), data.verdict);
      ethicsEl.style.display = '';
      btn.disabled    = false;
      btn.textContent = '🔍 Ethiekcheck';
    }}
  }} catch(e) {{
    btn.disabled = false;
    btn.textContent = '⚠ Fout';
  }}
}}

async function loadRules() {{
  const list = document.getElementById('rulesList');
  try {{
    const res   = await fetch('/rules');
    const data  = await res.json();
    const rules = data.rules || [];
    rulesCount  = rules.length;
    if (!rules.length) {{
      list.innerHTML = '<div class="rules-empty">Nog geen regels opgeslagen.<br><span style="font-size:.7rem;opacity:.6">Stel een regel voor via de chat — Pow Patrol leert ervan.</span></div>';
      return;
    }}
    const header = `<div style="font-size:.68rem;color:#606068;padding:4px 2px 8px;border-bottom:1px solid rgba(255,255,255,.06);margin-bottom:6px">
      ${{rules.length}} actieve regel${{rules.length!==1?'s':''}} · Verwijder regels die niet meer kloppen
    </div>`;
    list.innerHTML = header + rules.map(r => {{
      const date = r.created_at
        ? new Date(r.created_at).toLocaleDateString('nl-NL', {{day:'numeric',month:'short'}})
        : '';
      return `<div class="rule-item" id="rule-${{r.id}}">
        <div style="flex:1;min-width:0">
          <div style="font-size:.8rem;color:#f0f0f0;line-height:1.4">${{r.rule}}</div>
          ${{date ? `<div style="font-size:.65rem;color:#606068;margin-top:2px">${{date}}</div>` : ''}}
        </div>
        <button class="rule-del" onclick="deleteRule(${{r.id}})" title="Verwijder regel">✕</button>
      </div>`;
    }}).join('');
  }} catch(e) {{
    list.innerHTML = '<div class="rules-empty">Kon regels niet laden.</div>';
  }}
}}

async function deleteRule(id) {{
  try {{
    await fetch('/rules/delete', {{
      method: 'POST',
      headers: {{'Content-Type':'application/json'}},
      body: JSON.stringify({{id}}),
    }});
    document.getElementById('rule-'+id)?.remove();
    rulesCount = Math.max(0, rulesCount - 1);
    if (!document.querySelector('.rule-item')) {{
      document.getElementById('rulesList').innerHTML =
        '<div class="rules-empty">Geen actieve regels meer.</div>';
    }}
  }} catch(e) {{}}
}}

function chatFromModal() {{
  const ctx = window._chatCtx;
  if (ctx) setTimeout(() => setArticleCtx(ctx.title, ctx.source, ctx.score, ctx.summary, ctx.url), 50);
}}

// Auto-resize textarea
document.getElementById('chatInput').addEventListener('input', function() {{
  this.style.height = 'auto';
  this.style.height = Math.min(this.scrollHeight, 80) + 'px';
}});

// ── GSAP ANIMATIES ────────────────────────────────────────────────────────────
window.addEventListener('load', function() {{
  if (typeof gsap === 'undefined') return;

  gsap.registerPlugin(ScrollTrigger);

  // Hot cards: stagger in van links
  const hotCards = document.querySelectorAll('#hotRow .hot-card');
  if (hotCards.length) {{
    gsap.fromTo(hotCards,
      {{ opacity: 0, x: -12 }},
      {{
        opacity: 1, x: 0,
        duration: 0.35,
        stagger: 0.04,
        ease: 'power2.out',
        delay: 0.15,
      }}
    );
  }}

  // Grid cards: stagger in van onder
  const gridCards = document.querySelectorAll('#grid .card:not([style*="display:none"])');
  if (gridCards.length) {{
    gsap.fromTo(gridCards,
      {{ opacity: 0, y: 14 }},
      {{
        opacity: 1, y: 0,
        duration: 0.3,
        stagger: 0.025,
        ease: 'power2.out',
        delay: 0.1,
      }}
    );
  }}

  // Editorial cards: scale in
  const edCards = document.querySelectorAll('.ed-hero, .ed-side');
  if (edCards.length) {{
    gsap.fromTo(edCards,
      {{ opacity: 0, scale: 0.97 }},
      {{
        opacity: 1, scale: 1,
        duration: 0.4,
        stagger: 0.08,
        ease: 'power3.out',
      }}
    );
  }}

  // ScrollTrigger voor lazy-animatie van kaarten die in beeld komen
  ScrollTrigger.batch('#grid .card', {{
    onEnter: batch => gsap.to(batch, {{
      opacity: 1, y: 0,
      duration: 0.3, stagger: 0.04,
      ease: 'power2.out',
      overwrite: true,
    }}),
    start: 'top 95%',
  }});
}});

// ── KEYBOARD SHORTCUTS ────────────────────────────────────────────────────────
(function() {{
  let kbIdx = -1;

  function visibleCards() {{
    const activeView = document.querySelector('.view.active');
    if (!activeView) return [];
    const cards = [
      ...activeView.querySelectorAll('.hot-card:not([style*="display:none"])'),
      ...activeView.querySelectorAll('.card:not([style*="display:none"]):not(.hero)'),
    ];
    return cards;
  }}

  function setFocus(idx) {{
    const cards = visibleCards();
    if (!cards.length) return;
    document.querySelectorAll('.kb-focus').forEach(c => c.classList.remove('kb-focus'));
    kbIdx = Math.max(0, Math.min(idx, cards.length - 1));
    const card = cards[kbIdx];
    card.classList.add('kb-focus');
    card.scrollIntoView({{ behavior:'smooth', block:'nearest' }});
  }}

  function currentCard() {{
    return visibleCards()[kbIdx] || null;
  }}

  // Toon shortcut hint kort bij eerste gebruik
  let hintShown = false;
  function showHint() {{
    if (hintShown) return;
    hintShown = true;
    const h = document.getElementById('kbHint');
    if (h) {{ h.classList.add('show'); setTimeout(() => h.classList.remove('show'), 3500); }}
  }}

  document.addEventListener('keydown', e => {{
    // Negeer als gebruiker typt in input/textarea
    const tag = document.activeElement?.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || document.activeElement?.isContentEditable) return;

    // Negeer als modal open is (Escape sluit hem)
    const modalOpen = !document.getElementById('modalOverlay')?.classList.contains('hidden');

    switch(e.key) {{
      case 'j':
      case 'J':
      case 'ArrowDown':
        if (modalOpen) return;
        e.preventDefault();
        showHint();
        setFocus(kbIdx < 0 ? 0 : kbIdx + 1);
        break;

      case 'k':
      case 'K':
      case 'ArrowUp':
        if (modalOpen) return;
        e.preventDefault();
        showHint();
        setFocus(kbIdx <= 0 ? 0 : kbIdx - 1);
        break;

      case 'Enter':
        if (modalOpen) return;
        if (kbIdx >= 0 && currentCard()) {{
          e.preventDefault();
          openModal(currentCard());
        }}
        break;

      case 'o':
      case 'O':
        e.preventDefault();
        const urlCard = currentCard() || document.querySelector('.modal-overlay:not(.hidden) .modal');
        const url = urlCard?.dataset?.url
          || document.getElementById('modalOverlay')?.querySelector('[data-url]')?.dataset?.url;
        if (url) window.open(url, '_blank', 'noopener');
        break;

      case 'f':
      case 'F':
        if (modalOpen) return;
        if (currentCard()) {{
          e.preventDefault();
          const favBtn = currentCard().querySelector('.fav-btn');
          if (favBtn) {{ favBtn.click(); }}
        }}
        break;

      case 'Escape':
        if (modalOpen) {{ closeModalDirect(); kbIdx = -1; }}
        break;

      case '?':
        const h = document.getElementById('kbHint');
        if (h) h.classList.toggle('show');
        break;
    }}
  }});
}})();
</script>

<!-- Keyboard hint -->
<div class="kb-hint" id="kbHint">
  <kbd>J</kbd><kbd>K</kbd> navigeren &nbsp;
  <kbd>Enter</kbd> preview &nbsp;
  <kbd>O</kbd> openen &nbsp;
  <kbd>F</kbd> favoriet &nbsp;
  <kbd>Esc</kbd> sluiten &nbsp;
  <kbd>?</kbd> toon hint
</div>

<script>
// ── RELEVANTIE SLIDER ─────────────────────────────────────────────────────────
(function() {{
  const slider   = document.getElementById('scoreSlider');
  const scoreVal = document.getElementById('scoreVal');
  if (!slider) return;
  slider.addEventListener('input', function() {{
    activeMinScore = parseInt(this.value);
    const pct = activeMinScore;
    this.style.background = pct > 0
      ? `linear-gradient(to right, #e2148b ${{pct}}%, var(--surface3) ${{pct}}%)`
      : '';
    scoreVal.textContent = pct > 0 ? pct + '+' : 'Alles';
    applyFilters();
  }});
}})();

// ── KAART VAN NEDERLAND ───────────────────────────────────────────────────────
const CITY_COORDS = {{
  'Amsterdam':[52.3676,4.9041],'Rotterdam':[51.9225,4.4792],'Den Haag':[52.0705,4.3007],
  'Utrecht':[52.0907,5.1214],'Eindhoven':[51.4416,5.4697],'Groningen':[53.2194,6.5665],
  'Tilburg':[51.5555,5.0913],'Almere':[52.3508,5.2647],'Breda':[51.5719,4.7683],
  'Nijmegen':[51.8426,5.8546],'Enschede':[52.2215,6.8937],'Apeldoorn':[52.2112,5.9699],
  'Haarlem':[52.3874,4.6462],'Arnhem':[51.9851,5.8987],'Amersfoort':[52.1561,5.3878],
  'Zoetermeer':[52.0579,4.4928],'Zwolle':[52.5168,6.0830],'Leiden':[52.1601,4.4970],
  'leiden':[52.1601,4.4970],'Maastricht':[50.8514,5.6910],'Dordrecht':[51.8133,4.6901],
  'Delft':[52.0116,4.3571],'Alkmaar':[52.6324,4.7534],'Deventer':[52.2552,6.1638],
  'Venlo':[51.3704,6.1724],'Leeuwarden':[53.2012,5.7999],'Hilversum':[52.2292,5.1698],
  'Roermond':[51.1934,5.9878],'Gouda':[52.0116,4.7086],'Zeist':[52.0893,5.2327],
  'Zutphen':[52.1388,6.2013],'Hengelo':[52.2655,6.7933],"\\'s-Hertogenbosch":[51.6978,5.3037],
  'Den Bosch':[51.6978,5.3037],'Spijkenisse':[51.8455,4.3294],'Schiedam':[51.9147,4.3986],
  'Nieuwegein':[52.0276,5.0940],'Oss':[51.7656,5.5192],'Heerlen':[50.8879,5.9794],
  'Amstelveen':[52.3005,4.8604],'Middelburg':[51.4988,3.6109],'Almelo':[52.3568,6.6629],
  'Weert':[51.2511,5.7044],'Leek':[53.1624,6.3887],'leek':[53.1624,6.3887],
  'Harderwijk':[52.3432,5.6235],'Woerden':[52.0875,4.8872],'Tiel':[51.8885,5.4294],
  'Helmond':[51.4831,5.6614],'Katwijk':[52.2007,4.4024],'Purmerend':[52.5031,4.9605],
  'Vlaardingen':[51.9124,4.3408],'Bergen op Zoom':[51.4917,4.2847],
  'Ede':[52.0440,5.6564],'Zaanstad':[52.4567,4.8121],'Emmen':[52.7851,6.9070],
  'Hoogeveen':[52.7265,6.4769],'Doetinchem':[51.9627,6.2951],'Lelystad':[52.5185,5.4714],
  'Sittard':[51.0085,5.8721],'Kampen':[52.5568,5.9104],'Rijswijk':[52.0453,4.3222],
  'Alphen aan den Rijn':[52.1279,4.6583],'Barendrecht':[51.8530,4.5392],
  'Roosendaal':[51.5325,4.4624],'Capelle aan den IJssel':[51.9278,4.5714],
  'Hardenberg':[52.5774,6.6165],'Veenendaal':[52.0261,5.5544]
}};
const SOURCE_COLORS_MAP = {{
  'PowNed':'#e2148b','NOS':'#c0392b','De Telegraaf':'#003da5','AD':'#b20000',
  'RTL Nieuws':'#ff6600','Hart van Nederland':'#e8003c','Volkskrant':'#d4001a',
  'Trouw':'#004f99','Rijnmond':'#e30613','NH Nieuws':'#e4001b','AT5':'#e4001b',
  'Omroep Brabant':'#ff6900','RTV Noord':'#00843d','L1 Limburg':'#ae1c28',
  'Omroep West':'#005cb9','RTV Utrecht':'#e4001b','Regio 15':'#008000'
}};
const PRIO_COLORS = {{'must-have':'#e2148b','should-have':'#f59e0b','nice-to-have':'#60a5fa'}};
let nlMap = null, mapMarkers = [], mapPrioFilter = '', userMarker = null;

function initMap() {{
  if (nlMap) return;
  nlMap = L.map('nlMap', {{ center:[52.35,5.29], zoom:8, minZoom:7, maxZoom:14 }});
  L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
    attribution:'&copy; <a href="https://carto.com/">CARTO</a>', subdomains:'abcd', maxZoom:19
  }}).addTo(nlMap);
  plotMapMarkers();
}}
function getCardScore(card) {{
  try {{ const bd = card.dataset.breakdown ? JSON.parse(card.dataset.breakdown) : {{}};
    return Object.values(bd).reduce((a,b)=>a+b,0); }} catch {{ return 0; }}
}}
function plotMapMarkers() {{
  mapMarkers.forEach(m => nlMap.removeLayer(m));
  mapMarkers = [];
  const allC = [...document.querySelectorAll('.card, .hot-card')];
  const byCity = {{}};
  allC.forEach(card => {{
    const cities = (card.dataset.city||'').split(',').map(s=>s.trim()).filter(Boolean);
    const prio = card.dataset.prioriteit || 'nice-to-have';
    if (mapPrioFilter && prio !== mapPrioFilter) return;
    cities.forEach(city => {{
      const coords = CITY_COORDS[city];
      if (!coords) return;
      if (!byCity[city]) byCity[city] = {{ coords, articles:[] }};
      byCity[city].articles.push(card);
    }});
  }});
  let total = 0;
  Object.entries(byCity).forEach(([city, data]) => {{
    const articles = data.articles;
    total += articles.length;
    const hasMust   = articles.some(c => c.dataset.prioriteit === 'must-have');
    const hasShould = articles.some(c => c.dataset.prioriteit === 'should-have');
    const prio  = hasMust ? 'must-have' : hasShould ? 'should-have' : 'nice-to-have';
    const color = PRIO_COLORS[prio];
    const size  = articles.length > 5 ? 38 : articles.length > 2 ? 30 : 24;
    const pulse = prio === 'must-have';
    const icon  = L.divIcon({{
      className:'',
      html:`<div class="map-pin" style="width:${{size}}px;height:${{size}}px">
        ${{pulse ? `<div class="map-pin-pulse" style="background:${{color}}30;border:1.5px solid ${{color}}60"></div>` : ''}}
        <div class="map-pin-inner" style="width:${{size}}px;height:${{size}}px;background:${{color}};box-shadow:0 0 ${{pulse?14:8}}px ${{color}}60">
          ${{articles.length}}
        </div></div>`,
      iconSize:[size,size], iconAnchor:[size/2,size/2], popupAnchor:[0,-size/2-4]
    }});
    const top    = articles.slice(0,3);
    const popHtml = `<div class="map-popup">
      <div style="font-size:.65rem;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:#606068;margin-bottom:8px">${{city}} — ${{articles.length}} artikel${{articles.length!==1?'en':''}}</div>
      ${{top.map(card => {{
        const src      = card.dataset.source||'';
        const srcColor = SOURCE_COLORS_MAP[src]||'#888';
        const title    = card.dataset.title||card.querySelector('h2,h3')?.textContent||'';
        const url      = card.dataset.url||'#';
        const score    = getCardScore(card);
        const p  = card.dataset.prioriteit||'nice-to-have';
        const pc = PRIO_COLORS[p];
        return `<div style="border-bottom:1px solid rgba(255,255,255,.06);padding-bottom:8px;margin-bottom:8px">
          <div class="map-popup-source" style="background:${{srcColor}}20;color:${{srcColor}};border:1px solid ${{srcColor}}40">${{src}}</div>
          <div class="map-popup-title">${{title.slice(0,90)}}${{title.length>90?'…':''}}</div>
          <div class="map-popup-meta">
            <span class="map-popup-score" style="background:${{pc}}20;color:${{pc}}">${{score}}/100</span>
            <span class="map-popup-prio" style="background:${{pc}}15;color:${{pc}}">${{p}}</span>
          </div>
          <a class="map-popup-link" href="${{url}}" target="_blank" rel="noopener">Lees artikel ↗</a>
        </div>`;
      }}).join('')}}
      ${{articles.length > 3 ? `<div style="font-size:.7rem;color:#606068;text-align:center">+${{articles.length-3}} meer in ${{city}}</div>` : ''}}
    </div>`;
    const jLat = (Math.random()-.5)*.015, jLng = (Math.random()-.5)*.015;
    const marker = L.marker([data.coords[0]+jLat, data.coords[1]+jLng], {{icon}})
      .bindPopup(popHtml, {{maxWidth:290, minWidth:240}}).addTo(nlMap);
    mapMarkers.push(marker);
  }});
  document.getElementById('mapPinCount').textContent = total;
  document.getElementById('tb-kaart').textContent = total;
}}
function mapFilterPrio(prio) {{
  mapPrioFilter = prio;
  document.querySelectorAll('#btnMapAll,#btnMapMust,#btnMapShould').forEach(b => b.classList.remove('active'));
  document.getElementById(prio==='must-have'?'btnMapMust':prio==='should-have'?'btnMapShould':'btnMapAll').classList.add('active');
  plotMapMarkers();
}}
function mapGoToMyLocation() {{
  if (!navigator.geolocation) {{ alert('Locatie niet beschikbaar.'); return; }}
  const btn = document.getElementById('btnMyLocation');
  btn.textContent = '⏳ Zoeken…';
  navigator.geolocation.getCurrentPosition(pos => {{
    const lat = pos.coords.latitude, lng = pos.coords.longitude;
    if (userMarker) nlMap.removeLayer(userMarker);
    userMarker = L.marker([lat, lng], {{icon: L.divIcon({{
      className:'', html:'<div class="user-location-marker"></div>', iconSize:[14,14], iconAnchor:[7,7]
    }})}}).addTo(nlMap).bindPopup('<div class="map-popup" style="text-align:center"><div style="color:#60a5fa;font-weight:700">📍 Jouw locatie</div></div>');
    nlMap.flyTo([lat, lng], 10, {{duration:1.4}});
    btn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/></svg> Mijn locatie';
    btn.classList.add('active');
  }}, () => {{
    btn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/></svg> Mijn locatie';
    alert('Kon locatie niet ophalen. Geef toestemming in de browser.');
  }});
}}

// ── AUTO-REFRESH BANNER ───────────────────────────────────────────────────────
(function() {{
  const startTotal = {total};
  const banner     = document.getElementById('refreshBanner');
  const bannerText = document.getElementById('refreshBannerText');
  function checkForUpdates() {{
    fetch('/api/status').then(r => r.json()).then(d => {{
      if (d.total > startTotal) {{
        const diff = d.total - startTotal;
        bannerText.textContent = `${{diff}} nieuwe artikel${{diff===1?'':'en'}} beschikbaar`;
        banner.classList.add('show');
      }}
    }}).catch(()=>{{}});
  }}
  setTimeout(checkForUpdates, 180000); // eerste check na 3 min
  setInterval(checkForUpdates, 300000); // daarna elke 5 min
}})();
</script>

</body>
</html>"""

out = OUT_DIR / "index.html"
out.write_text(html, encoding="utf-8")
print(f"✓ {total} items → {out}")

# ── Login pagina genereren ──────────────────────────────────────────────────
login_html = """<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PowNed Redactie — Inloggen</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#000;display:flex;align-items:center;justify-content:center;min-height:100vh;font-family:'Inter',sans-serif}
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
.card{background:#111;border:1px solid rgba(255,255,255,.08);border-radius:16px;padding:40px;width:100%;max-width:400px}
.logo{text-align:center;margin-bottom:32px}
.logo span{font-size:24px;font-weight:800;background:linear-gradient(90deg,#e2148b,#9c2d8f);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.logo small{display:block;color:#666;font-size:13px;margin-top:4px}
label{display:block;color:#888;font-size:13px;margin-bottom:6px;margin-top:20px}
input{width:100%;background:#1a1a1a;border:1px solid rgba(255,255,255,.1);border-radius:8px;padding:12px 14px;color:#fff;font-size:15px;outline:none}
input:focus{border-color:#e2148b}
button{margin-top:28px;width:100%;background:linear-gradient(90deg,#e2148b,#9c2d8f);border:none;border-radius:8px;padding:14px;color:#fff;font-weight:700;font-size:15px;cursor:pointer}
button:hover{opacity:.9}
.error{color:#ff4444;font-size:13px;margin-top:12px;text-align:center;min-height:20px}
</style>
</head>
<body>
<div class="card">
  <div class="logo">
    <span>PowNed Redactie</span>
    <small>Nieuwsdashboard</small>
  </div>
  <form id="form">
    <label>E-mailadres</label>
    <input type="email" id="email" placeholder="naam@example.com" required autofocus>
    <label>Wachtwoord</label>
    <input type="password" id="pw" placeholder="••••••••" required>
    <button type="submit">Inloggen</button>
    <div class="error" id="err"></div>
  </form>
</div>
<script>
document.getElementById('form').addEventListener('submit', async e => {
  e.preventDefault();
  const btn = e.target.querySelector('button');
  btn.textContent = 'Bezig…';
  btn.disabled = true;
  const resp = await fetch('/api/auth/login', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({email: document.getElementById('email').value, password: document.getElementById('pw').value})
  });
  const data = await resp.json();
  if (data.status === 'ok' || data.ok) {
    const u = data.user || data;
    localStorage.setItem('powned_session', JSON.stringify({email: u.email, name: u.name, role: u.role}));
    window.location.href = '/dashboard';
  } else {
    document.getElementById('err').textContent = data.error || data.message || 'Inloggen mislukt';
    btn.textContent = 'Inloggen';
    btn.disabled = false;
  }
});
</script>
</body>
</html>"""

login_out = OUT_DIR / "login.html"
login_out.write_text(login_html, encoding="utf-8")
print(f"✓ Login pagina → {login_out}")

# ── AGENDA PAGINA ────────────────────────────────────────────────────────────
agenda_html = """<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agenda — PowNed Redactie</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#000;color:#f0f0f0;font-family:'Inter',sans-serif;min-height:100vh;display:flex;flex-direction:column}
.hdr{display:flex;align-items:center;gap:12px;padding:16px 24px;border-bottom:1px solid rgba(255,255,255,.07);background:rgba(0,0,0,.95);position:sticky;top:0;z-index:10}
.back{display:flex;align-items:center;gap:6px;color:#888;font-size:13px;font-weight:600;text-decoration:none;padding:6px 12px;border-radius:8px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);transition:all .15s}
.back:hover{color:#f0f0f0;background:rgba(226,20,139,.12);border-color:rgba(226,20,139,.3)}
.hdr-title{font-size:15px;font-weight:700}
.hdr-add{margin-left:auto;background:linear-gradient(90deg,#e2148b,#9c2d8f);border:none;border-radius:8px;padding:8px 16px;color:#fff;font-weight:700;font-size:13px;cursor:pointer}
.hdr-add:hover{opacity:.9}
.main{display:flex;flex:1;gap:0;overflow:hidden}

/* ── KALENDER ── */
.cal-panel{flex:1;padding:28px 24px;overflow-y:auto;border-right:1px solid rgba(255,255,255,.06)}
.cal-nav{display:flex;align-items:center;gap:12px;margin-bottom:20px}
.cal-nav button{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.08);border-radius:8px;color:#f0f0f0;width:32px;height:32px;cursor:pointer;font-size:16px;display:flex;align-items:center;justify-content:center;transition:background .15s}
.cal-nav button:hover{background:rgba(226,20,139,.2);border-color:rgba(226,20,139,.4)}
.cal-nav h2{font-size:18px;font-weight:800;flex:1}
.cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:2px}
.cal-dow{text-align:center;font-size:11px;font-weight:700;color:#555;text-transform:uppercase;letter-spacing:.05em;padding:6px 0;margin-bottom:4px}
.cal-day{min-height:80px;padding:6px;border-radius:8px;background:#0d0d0d;border:1px solid transparent;cursor:pointer;transition:border-color .15s,background .15s;position:relative;vertical-align:top}
.cal-day:hover{background:#141414;border-color:rgba(255,255,255,.1)}
.cal-day.today{border-color:rgba(226,20,139,.4);background:rgba(226,20,139,.05)}
.cal-day.other-month .day-num{color:#333}
.cal-day.selected{border-color:#e2148b;background:rgba(226,20,139,.08)}
.day-num{font-size:13px;font-weight:700;color:#aaa;margin-bottom:4px}
.cal-day.today .day-num{color:#e2148b}
.cal-event-dot{font-size:10px;font-weight:600;padding:2px 5px;border-radius:4px;margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:pointer}
.dot-protest{background:rgba(226,20,139,.2);color:#e2148b}
.dot-staking{background:rgba(255,107,53,.2);color:#ff6b35}
.dot-persconferentie{background:rgba(99,102,241,.2);color:#818cf8}
.dot-overig{background:rgba(255,255,255,.07);color:#888}
.more-dots{font-size:10px;color:#555;margin-top:1px}

/* ── ZIJBALK: DETAILS + TOEVOEGEN ── */
.side-panel{width:320px;flex-shrink:0;display:flex;flex-direction:column;overflow-y:auto}
.side-section{padding:20px;border-bottom:1px solid rgba(255,255,255,.06)}
.side-section h3{font-size:12px;font-weight:700;color:#e2148b;text-transform:uppercase;letter-spacing:.06em;margin-bottom:14px}
.selected-date-title{font-size:15px;font-weight:800;margin-bottom:12px;color:#f0f0f0}
.ev-list{display:flex;flex-direction:column;gap:8px}
.ev-item{background:#111;border:1px solid rgba(255,255,255,.07);border-radius:10px;padding:12px 14px;display:flex;gap:10px;align-items:flex-start}
.ev-item-color{width:3px;border-radius:2px;flex-shrink:0;align-self:stretch}
.ev-item-body{flex:1;min-width:0}
.ev-item-title{font-size:13px;font-weight:700;margin-bottom:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ev-item-meta{font-size:11px;color:#555;display:flex;gap:6px;flex-wrap:wrap}
.del-btn{background:none;border:none;color:#333;cursor:pointer;font-size:13px;padding:2px 4px;border-radius:4px;transition:color .15s;flex-shrink:0}
.del-btn:hover{color:#ff4444}
.no-events{font-size:13px;color:#444;padding:8px 0}

/* ── FORMULIER ── */
.add-form{display:flex;flex-direction:column;gap:10px}
.form-row{display:grid;grid-template-columns:1fr 1fr;gap:10px}
label{display:block;color:#888;font-size:11px;margin-bottom:4px}
input,select{width:100%;background:#1a1a1a;border:1px solid rgba(255,255,255,.1);border-radius:8px;padding:9px 11px;color:#fff;font-size:13px;outline:none}
input:focus,select:focus{border-color:#e2148b}
.add-btn{background:linear-gradient(90deg,#e2148b,#9c2d8f);border:none;border-radius:8px;padding:10px;color:#fff;font-weight:700;font-size:13px;cursor:pointer;width:100%}
.add-btn:hover{opacity:.9}

/* ── AANKOMENDE EVENTS ── */
.upcoming-list{display:flex;flex-direction:column;gap:8px}
.up-item{display:flex;gap:12px;align-items:flex-start;padding:10px 12px;background:#0d0d0d;border-radius:10px;border:1px solid rgba(255,255,255,.05)}
.up-date{min-width:40px;text-align:center}
.up-day{font-size:18px;font-weight:800;color:#e2148b;line-height:1}
.up-month{font-size:10px;color:#555;text-transform:uppercase;letter-spacing:.04em}
.up-body{flex:1;min-width:0}
.up-title{font-size:13px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:2px}
.up-meta{font-size:11px;color:#555}
.badge{display:inline-block;padding:1px 6px;border-radius:10px;font-size:10px;font-weight:600}
.badge.protest{background:rgba(226,20,139,.15);color:#e2148b}
.badge.staking{background:rgba(255,107,53,.15);color:#ff6b35}
.badge.persconferentie{background:rgba(99,102,241,.15);color:#818cf8}
.badge.overig{background:rgba(255,255,255,.07);color:#666}
.empty-side{font-size:12px;color:#444;padding:8px 0}
@media(max-width:700px){.main{flex-direction:column}.side-panel{width:100%;border-top:1px solid rgba(255,255,255,.06)}.cal-day{min-height:50px}}
</style>
</head>
<body>
<div class="hdr">
  <a href="/dashboard" class="back">← Dashboard</a>
  <span class="hdr-title">📅 Agenda</span>
  <button class="hdr-add" onclick="document.getElementById('ev-title').focus()">+ Toevoegen</button>
</div>
<div class="main">
  <!-- KALENDER -->
  <div class="cal-panel">
    <div class="cal-nav">
      <button onclick="prevMonth()">‹</button>
      <h2 id="cal-title"></h2>
      <button onclick="nextMonth()">›</button>
      <button onclick="goToday()" style="width:auto;padding:0 10px;font-size:12px;font-weight:700">Vandaag</button>
    </div>
    <div class="cal-grid" id="cal-dow"></div>
    <div class="cal-grid" id="cal-body"></div>
  </div>

  <!-- ZIJBALK -->
  <div class="side-panel">
    <div class="side-section">
      <h3 id="selected-label">Selecteer een dag</h3>
      <div id="day-events"><div class="no-events">Klik op een dag om events te zien</div></div>
    </div>
    <div class="side-section">
      <h3>+ Nieuw evenement</h3>
      <div class="add-form">
        <div><label>Titel</label><input id="ev-title" placeholder="Bijv. NS-staking" /></div>
        <div class="form-row">
          <div><label>Datum</label><input id="ev-date" type="date" /></div>
          <div><label>Type</label>
            <select id="ev-type">
              <option value="protest">Protest</option>
              <option value="staking">Staking</option>
              <option value="persconferentie">Persconferentie</option>
              <option value="overig">Overig</option>
            </select>
          </div>
        </div>
        <div><label>Locatie</label><input id="ev-loc" placeholder="Amsterdam, heel NL…" /></div>
        <div><label>Bronlink (optioneel)</label><input id="ev-url" placeholder="https://…" /></div>
        <button class="add-btn" onclick="addEvent()">Toevoegen</button>
      </div>
    </div>
    <div class="side-section" style="flex:1">
      <h3>Aankomend</h3>
      <div class="upcoming-list" id="upcoming"><div class="empty-side">Laden…</div></div>
    </div>
  </div>
</div>
<script>
(function(){{
  const s = JSON.parse(localStorage.getItem('powned_session')||'null');
  if(!s||!s.email) {{ window.location.href='/login'; return; }}
}})();

const MONTHS_LONG = ['januari','februari','maart','april','mei','juni','juli','augustus','september','oktober','november','december'];
const MONTHS_SHORT = ['jan','feb','mrt','apr','mei','jun','jul','aug','sep','okt','nov','dec'];
const DAYS = ['zo','ma','di','wo','do','vr','za'];
const TYPE_COLOR = {{protest:'protest',staking:'staking',persconferentie:'persconferentie',overig:'overig'}};

let allEvents = [];
let viewYear, viewMonth, selectedDate;

function toKey(d) {{ return d.toISOString().slice(0,10); }}

function today() {{ const d = new Date(); d.setHours(0,0,0,0); return d; }}

async function loadEvents() {{
  const res = await fetch('/api/agenda');
  const data = await res.json();
  allEvents = (data.events || []).map(e => ({{...e, _date: new Date(e.event_date + 'T00:00:00')}}));
  renderCalendar();
  renderUpcoming();
  if (selectedDate) renderDayEvents(selectedDate);
}}

function renderCalendar() {{
  const title = document.getElementById('cal-title');
  title.textContent = MONTHS_LONG[viewMonth] + ' ' + viewYear;

  // Day-of-week headers (ma first)
  const dowEl = document.getElementById('cal-dow');
  const orderedDays = ['ma','di','wo','do','vr','za','zo'];
  dowEl.innerHTML = orderedDays.map(d => `<div class="cal-dow">${{d}}</div>`).join('');

  const body = document.getElementById('cal-body');
  const firstDay = new Date(viewYear, viewMonth, 1);
  // Monday = 0
  let startDow = (firstDay.getDay() + 6) % 7;
  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
  const daysInPrev  = new Date(viewYear, viewMonth, 0).getDate();
  const todayKey = toKey(today());

  // Build event map by date key
  const eventMap = {{}};
  allEvents.forEach(e => {{
    const k = toKey(e._date);
    if (!eventMap[k]) eventMap[k] = [];
    eventMap[k].push(e);
  }});

  let cells = '';
  // Prev month overflow
  for (let i = startDow - 1; i >= 0; i--) {{
    const d = new Date(viewYear, viewMonth - 1, daysInPrev - i);
    cells += dayCell(d, eventMap, todayKey, true);
  }}
  // Current month
  for (let d = 1; d <= daysInMonth; d++) {{
    const date = new Date(viewYear, viewMonth, d);
    cells += dayCell(date, eventMap, todayKey, false);
  }}
  // Next month fill
  const total = startDow + daysInMonth;
  const remainder = total % 7 === 0 ? 0 : 7 - (total % 7);
  for (let d = 1; d <= remainder; d++) {{
    const date = new Date(viewYear, viewMonth + 1, d);
    cells += dayCell(date, eventMap, todayKey, true);
  }}
  body.innerHTML = cells;
}}

function dayCell(date, eventMap, todayKey, otherMonth) {{
  const key = toKey(date);
  const evs = eventMap[key] || [];
  const isToday = key === todayKey;
  const isSel   = selectedDate && key === toKey(selectedDate);
  let cls = 'cal-day';
  if (otherMonth) cls += ' other-month';
  if (isToday)    cls += ' today';
  if (isSel)      cls += ' selected';

  const dots = evs.slice(0,2).map(e =>
    `<div class="cal-event-dot dot-${{e.event_type||'overig'}}" title="${{e.title}}">${{e.title}}</div>`
  ).join('');
  const more = evs.length > 2 ? `<div class="more-dots">+${{evs.length-2}} meer</div>` : '';

  return `<div class="${{cls}}" data-key="${{key}}" onclick="selectDay('${{key}}')">
    <div class="day-num">${{date.getDate()}}</div>
    ${{dots}}${{more}}
  </div>`;
}}

function selectDay(key) {{
  selectedDate = new Date(key + 'T00:00:00');
  renderCalendar();
  renderDayEvents(selectedDate);
  // Preset the date field
  document.getElementById('ev-date').value = key;
}}

function renderDayEvents(date) {{
  const key = toKey(date);
  const MONTHS_FULL = ['1 jan','2 feb','3 mrt'];
  const label = date.getDate() + ' ' + MONTHS_LONG[date.getMonth()] + ' ' + date.getFullYear();
  document.getElementById('selected-label').textContent = label;
  const evs = allEvents.filter(e => toKey(e._date) === key);
  const el = document.getElementById('day-events');
  if (!evs.length) {{ el.innerHTML = '<div class="no-events">Geen evenementen op deze dag</div>'; return; }}
  el.innerHTML = '<div class="ev-list">' + evs.map(e => {{
    const col = {{protest:'#e2148b',staking:'#ff6b35',persconferentie:'#818cf8',overig:'#555'}}[e.event_type||'overig'];
    return `<div class="ev-item">
      <div class="ev-item-color" style="background:${{col}}"></div>
      <div class="ev-item-body">
        <div class="ev-item-title">${{e.title}}</div>
        <div class="ev-item-meta">
          <span class="badge ${{e.event_type||'overig'}}">${{e.event_type||'overig'}}</span>
          ${{e.location ? `<span>📍 ${{e.location}}</span>` : ''}}
          ${{e.source_url ? `<a href="${{e.source_url}}" target="_blank" style="color:#555;font-size:11px">Bron ↗</a>` : ''}}
          ${{e.auto_detected ? '<span style="color:#444">auto</span>' : ''}}
        </div>
      </div>
      ${{!e.auto_detected ? `<button class="del-btn" onclick="del(${{e.id}})">✕</button>` : ''}}
    </div>`;
  }}).join('') + '</div>';
}}

function renderUpcoming() {{
  const now = today();
  const upcoming = allEvents
    .filter(e => e._date >= now)
    .sort((a,b) => a._date - b._date)
    .slice(0, 8);
  const el = document.getElementById('upcoming');
  if (!upcoming.length) {{ el.innerHTML = '<div class="empty-side">Geen aankomende evenementen</div>'; return; }}
  el.innerHTML = upcoming.map(e => `
    <div class="up-item" onclick="selectDay('${{toKey(e._date)}}')" style="cursor:pointer">
      <div class="up-date"><div class="up-day">${{e._date.getDate()}}</div><div class="up-month">${{MONTHS_SHORT[e._date.getMonth()]}}</div></div>
      <div class="up-body">
        <div class="up-title">${{e.title}}</div>
        <div class="up-meta">
          <span class="badge ${{e.event_type||'overig'}}">${{e.event_type||'overig'}}</span>
          ${{e.location ? ` · ${{e.location}}` : ''}}
        </div>
      </div>
    </div>`).join('');
}}

function prevMonth() {{ viewMonth--; if(viewMonth<0){{viewMonth=11;viewYear--;}} renderCalendar(); }}
function nextMonth() {{ viewMonth++; if(viewMonth>11){{viewMonth=0;viewYear++;}} renderCalendar(); }}
function goToday()  {{ const t=today(); viewYear=t.getFullYear(); viewMonth=t.getMonth(); renderCalendar(); }}

async function addEvent() {{
  const title = document.getElementById('ev-title').value.trim();
  const date  = document.getElementById('ev-date').value;
  const loc   = document.getElementById('ev-loc').value.trim();
  const type  = document.getElementById('ev-type').value;
  const url   = document.getElementById('ev-url').value.trim();
  if (!title || !date) {{ alert('Vul minimaal een titel en datum in'); return; }}
  await fetch('/api/agenda/add', {{ method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{ title, event_date: date, location: loc, event_type: type, source_url: url }}) }});
  document.getElementById('ev-title').value = '';
  document.getElementById('ev-loc').value = '';
  document.getElementById('ev-url').value = '';
  await loadEvents();
  selectDay(date);
}}

async function del(id) {{
  if (!confirm('Evenement verwijderen?')) return;
  await fetch('/api/agenda/delete', {{ method:'POST', headers:{{'Content-Type':'application/json'}}, body: JSON.stringify({{id}}) }});
  await loadEvents();
}}

// Init
const t = today();
viewYear = t.getFullYear();
viewMonth = t.getMonth();
selectedDate = t;
loadEvents();
</script>
</body>
</html>"""

agenda_out = OUT_DIR / "agenda.html"
agenda_out.write_text(agenda_html.replace('{{', '{').replace('}}', '}'), encoding="utf-8")
print(f"✓ Agenda pagina → {agenda_out}")

# ── ARCHIEF PAGINA ───────────────────────────────────────────────────────────
archief_html = """<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mijn Archief — PowNed Redactie</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#000;color:#f0f0f0;font-family:'Inter',sans-serif;min-height:100vh}
.hdr{display:flex;align-items:center;gap:12px;padding:18px 28px;border-bottom:1px solid rgba(255,255,255,.07);background:rgba(0,0,0,.9)}
.back{display:flex;align-items:center;gap:6px;color:#888;font-size:13px;font-weight:600;text-decoration:none;padding:6px 12px;border-radius:8px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);transition:all .15s}
.back:hover{color:#f0f0f0;background:rgba(226,20,139,.12);border-color:rgba(226,20,139,.3)}
.hdr-title{font-size:15px;font-weight:700}
.content{max-width:760px;margin:0 auto;padding:40px 24px}
h1{font-size:28px;font-weight:800;margin-bottom:6px}
.subtitle{color:#666;font-size:14px;margin-bottom:32px}
.tabs{display:flex;gap:8px;margin-bottom:24px}
.tab{padding:7px 16px;border-radius:20px;border:1px solid rgba(255,255,255,.1);background:none;color:#888;font-size:13px;font-weight:600;cursor:pointer;transition:all .15s}
.tab.active{background:linear-gradient(90deg,#e2148b,#9c2d8f);border-color:transparent;color:#fff}
.articles{display:flex;flex-direction:column;gap:10px}
.article{background:#111;border:1px solid rgba(255,255,255,.07);border-radius:12px;padding:16px 18px;display:flex;gap:14px;align-items:flex-start}
.art-img{width:72px;height:72px;border-radius:8px;object-fit:cover;flex-shrink:0;background:#1a1a1a}
.art-body{flex:1;min-width:0}
.art-source{font-size:11px;color:#e2148b;font-weight:700;text-transform:uppercase;letter-spacing:.04em;margin-bottom:4px}
.art-title{font-size:14px;font-weight:700;margin-bottom:6px;line-height:1.4}
.art-meta{font-size:12px;color:#555;display:flex;gap:10px}
.art-actions{display:flex;gap:8px;margin-top:10px}
.btn-sm{padding:5px 12px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.05);color:#aaa;transition:all .15s;text-decoration:none}
.btn-sm:hover{background:rgba(226,20,139,.12);border-color:rgba(226,20,139,.3);color:#f0f0f0}
.btn-del{color:#555}
.btn-del:hover{background:rgba(255,68,68,.1);border-color:rgba(255,68,68,.3);color:#ff6666}
.badge{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:600}
.badge.favoriet{background:rgba(226,20,139,.15);color:#e2148b}
.badge.bekijken{background:rgba(255,107,53,.15);color:#ff6b35}
.badge.verwerkt{background:rgba(34,197,94,.12);color:#4ade80}
.empty{text-align:center;padding:60px 0;color:#444}
.empty span{font-size:40px;display:block;margin-bottom:12px}
</style>
</head>
<body>
<div class="hdr">
  <a href="/dashboard" class="back">← Dashboard</a>
  <span class="hdr-title">📁 Mijn Archief</span>
</div>
<div class="content">
  <h1>Mijn Archief</h1>
  <p class="subtitle" id="user-subtitle">Jouw opgeslagen artikelen</p>
  <div class="tabs">
    <button class="tab active" onclick="setLabel('favoriet')">⭐ Favorieten</button>
    <button class="tab" onclick="setLabel('bekijken')">👀 Later bekijken</button>
    <button class="tab" onclick="setLabel('verwerkt')">✅ Verwerkt</button>
  </div>
  <div class="articles" id="articles"><div class="empty"><span>📭</span>Laden…</div></div>
</div>
<script>
let session = null;
let activeLabel = 'favoriet';

(function(){
  session = JSON.parse(localStorage.getItem('powned_session')||'null');
  if(!session||!session.email) { window.location.href='/login'; return; }
  document.getElementById('user-subtitle').textContent = `Opgeslagen artikelen van ${session.name || session.email}`;
})();

function setLabel(label) {
  activeLabel = label;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  event.target.classList.add('active');
  load();
}

async function load() {
  if (!session) return;
  const el = document.getElementById('articles');
  el.innerHTML = '<div class="empty"><span>⏳</span>Laden…</div>';
  const res = await fetch(`/api/archief?user=${encodeURIComponent(session.email)}&label=${activeLabel}`);
  const data = await res.json();
  const items = data.items || [];
  if (!items.length) {
    el.innerHTML = '<div class="empty"><span>📭</span>Geen artikelen in dit archief</div>';
    return;
  }
  el.innerHTML = items.map(a => `
    <div class="article" id="art-${encodeURIComponent(a.url)}">
      ${a.image_url ? `<img class="art-img" src="${a.image_url}" onerror="this.style.display='none'">` : ''}
      <div class="art-body">
        <div class="art-source">${a.source || ''}</div>
        <div class="art-title">${a.title}</div>
        <div class="art-meta">
          <span class="badge ${activeLabel}">${activeLabel}</span>
          ${a.published_at ? `<span>${new Date(a.published_at).toLocaleDateString('nl-NL')}</span>` : ''}
          ${a.region ? `<span>📍 ${a.region}</span>` : ''}
        </div>
        <div class="art-actions">
          <a class="btn-sm" href="${a.url}" target="_blank">Lees artikel ↗</a>
          <button class="btn-sm btn-del" onclick="remove('${encodeURIComponent(a.url)}','${a.url}')">✕ Verwijder</button>
        </div>
      </div>
    </div>`).join('');
}

async function remove(encodedUrl, url) {
  if (!session) return;
  await fetch('/api/archief/label', { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ user: session.email, url, label: null }) });
  document.getElementById('art-' + encodedUrl)?.remove();
}

load();
</script>
</body>
</html>"""

archief_out = OUT_DIR / "archief.html"
archief_out.write_text(archief_html, encoding="utf-8")
print(f"✓ Archief pagina → {archief_out}")

# ── UITLEG PAGINA ────────────────────────────────────────────────────────────
uitleg_html = """<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Hoe werkt dit? — PowNed Redactie</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#000;color:#f0f0f0;font-family:'Inter',sans-serif;min-height:100vh}
.hdr{display:flex;align-items:center;gap:12px;padding:18px 28px;border-bottom:1px solid rgba(255,255,255,.07);background:rgba(0,0,0,.9)}
.back{display:flex;align-items:center;gap:6px;color:#888;font-size:13px;font-weight:600;text-decoration:none;padding:6px 12px;border-radius:8px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.08);transition:all .15s}
.back:hover{color:#f0f0f0;background:rgba(226,20,139,.12);border-color:rgba(226,20,139,.3)}
.hdr-title{font-size:15px;font-weight:700}
.content{max-width:680px;margin:0 auto;padding:40px 24px}
h1{font-size:28px;font-weight:800;margin-bottom:6px}
.subtitle{color:#666;font-size:14px;margin-bottom:40px}
.section{margin-bottom:36px}
.section h2{font-size:16px;font-weight:800;color:#e2148b;text-transform:uppercase;letter-spacing:.06em;margin-bottom:14px;display:flex;align-items:center;gap:8px}
.section p,.section li{font-size:14px;color:#aaa;line-height:1.7}
.section ul{padding-left:0;list-style:none;display:flex;flex-direction:column;gap:8px}
.section li::before{content:'→ ';color:#e2148b;font-weight:700}
.card-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.info-card{background:#111;border:1px solid rgba(255,255,255,.07);border-radius:12px;padding:16px}
.info-card .icon{font-size:24px;margin-bottom:8px}
.info-card h3{font-size:13px;font-weight:700;margin-bottom:5px}
.info-card p{font-size:12px;color:#666;line-height:1.6}
.divider{height:1px;background:rgba(255,255,255,.06);margin:32px 0}
.color-row{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.dot{width:12px;height:12px;border-radius:50%;flex-shrink:0}
.color-row span{font-size:13px;color:#aaa}
</style>
</head>
<body>
<div class="hdr">
  <a href="/dashboard" class="back">← Dashboard</a>
  <span class="hdr-title">💡 Hoe werkt dit?</span>
</div>
<div class="content">
  <h1>Hoe werkt dit systeem?</h1>
  <p class="subtitle">Een korte uitleg over de PowNed Redactie Agent</p>

  <div class="section">
    <h2>🤖 Wat doet dit systeem?</h2>
    <p>De PowNed Redactie Agent verzamelt automatisch nieuws uit tientallen bronnen, analyseert elk artikel met AI en geeft aan wat relevant is voor PowNed. Zo hoef jij niet alles zelf te lezen en zie je in één oogopslag wat er speelt.</p>
  </div>

  <div class="divider"></div>

  <div class="section">
    <h2>📰 De feed</h2>
    <div class="card-grid">
      <div class="info-card"><div class="icon">🔥</div><h3>PowNed Relevant</h3><p>Alleen artikelen die hoog scoren op relevantie voor PowNed — must-haves en sterke verhalen.</p></div>
      <div class="info-card"><div class="icon">📋</div><h3>Alle artikelen</h3><p>De volledige feed van alle binnengekomen artikelen, van alle bronnen.</p></div>
      <div class="info-card"><div class="icon">🔍</div><h3>Filters</h3><p>Filter op regio, nieuwsbron, stad of ethiekoordeel. De slider bepaalt de minimale relevantiescore.</p></div>
      <div class="info-card"><div class="icon">⭐</div><h3>Opslaan</h3><p>Klik op het ster-icoon om een artikel op te slaan in jouw archief voor later.</p></div>
    </div>
  </div>

  <div class="divider"></div>

  <div class="section">
    <h2>🎨 Ethiek kleuren</h2>
    <div class="color-row"><div class="dot" style="background:#4ade80"></div><span><strong>Groen</strong> — Geen ethische bezwaren, direct te gebruiken</span></div>
    <div class="color-row"><div class="dot" style="background:#fb923c"></div><span><strong>Oranje</strong> — Let op bij gebruik, check de context</span></div>
    <div class="color-row"><div class="dot" style="background:#f87171"></div><span><strong>Rood</strong> — Ethisch gevoelig, voorzichtigheid geboden</span></div>
  </div>

  <div class="divider"></div>

  <div class="section">
    <h2>📅 Agenda</h2>
    <p>De agenda toont aankomende protesten, stakingen en persconferenties. Sommige worden automatisch herkend uit het nieuws, andere kun je zelf toevoegen.</p>
  </div>

  <div class="divider"></div>

  <div class="section">
    <h2>💬 AI Chat</h2>
    <p>Via de chat-knop rechtsonder kun je vragen stellen over het nieuws of aan de AI vragen om een artikel samen te vatten. De AI heeft toegang tot alle artikelen in de feed.</p>
  </div>

  <div class="divider"></div>

  <div class="section">
    <h2>❓ Vragen of problemen?</h2>
    <ul>
      <li>Klik op "Nieuwe artikelen" om de pipeline handmatig te starten</li>
      <li>Gebruik de zoekbalk om snel een artikel te vinden</li>
      <li>Klik op een artikel voor een snelle preview zonder de pagina te verlaten</li>
      <li>De feed ververst automatisch elke 2 minuten</li>
    </ul>
  </div>
</div>
</body>
</html>"""

uitleg_out = OUT_DIR / "uitleg.html"
uitleg_out.write_text(uitleg_html, encoding="utf-8")
print(f"✓ Uitleg pagina → {uitleg_out}")

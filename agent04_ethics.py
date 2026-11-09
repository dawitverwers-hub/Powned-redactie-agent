"""Agent 04 — Ethische Agent: Bronintegriteitscheck v1.2

Verwerkt items in batches van 5 per API-call (snel & goedkoop).
Slaat verdict + rapport op in de database.

Run: PYTHONPATH=src python agent04_ethics.py
Run alles: ETHICS_MAX=9999 python agent04_ethics.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from pathlib import Path

from openai import AsyncOpenAI
from dotenv import load_dotenv
from loguru import logger

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

DB = Path(
    os.environ.get("DATABASE_URL", "").replace("sqlite:///", "", 1)
    or os.environ.get("DB_PATH", "")
    or str(ROOT / "data" / "powned.db")
)

MAX_ITEMS   = int(os.environ.get("ETHICS_MAX", 9999))
BATCH_SIZE  = 3
CONCURRENCY = 3          # gelijktijdige API-calls (lager = minder rate-limits)
MODEL       = "gpt-4o-mini"
client      = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

PAYWALL_SOURCES = {"FD","NRC","De Telegraaf","Volkskrant","Trouw","AD","Bloomberg","The Times"}

# ── System prompt (batch-variant) ─────────────────────────────────────────────
SYSTEM_PROMPT = """Je bent Agent 04 — Ethische Agent van PowNed. Je controleert nieuwsitems.

Beoordeel elk item in de array op 7 indicatoren (0–100 per indicator).
Geef UITSLUITEND een JSON-array terug met één object per item, in dezelfde volgorde.

Indicatoren:
1. bronherkomst_legitimiteit  — Transparante, traceerbare bron?
2. paywall_copyright          — Betaalmuur-content verantwoord verwerkt?
3. privacy_persoonsgegevens   — Geen privégegevens van niet-publieke personen?
4. verificatie_framing        — Feitelijk correct, geen misleidende framing?
5. eenzijdigheid_hoor_wederhoor — Meerdere perspectieven of genre duidelijk gelabeld?
6. clickbait_sensatiezucht    — Kop dekt inhoud, geen overdreven sensatietaal?
7. ethische_verkrijging       — Informatie via rechtmatige weg verkregen?

Verdictregels per item:
- Gemiddelde ≥ 70  → "GROEN"
- Gemiddelde 45–69 → "ORANJE"
- Gemiddelde < 45  → "ROOD"
- Zwakste indicator < 40 → maximaal "ORANJE"

Geef ALLEEN een JSON-array terug (geen markdown):
[
  {
    "item_id": "zelfde als in input",
    "scores": {
      "bronherkomst_legitimiteit": 0-100,
      "paywall_copyright": 0-100,
      "privacy_persoonsgegevens": 0-100,
      "verificatie_framing": 0-100,
      "eenzijdigheid_hoor_wederhoor": 0-100,
      "clickbait_sensatiezucht": 0-100,
      "ethische_verkrijging": 0-100
    },
    "overall_score": 0-100,
    "verdict": "GROEN" of "ORANJE" of "ROOD",
    "zwakste_indicator": "naam",
    "zwakste_score": 0-100,
    "paywall_alert": true of false,
    "gemarkeerde_passages": [],
    "aanbeveling": "max 2 zinnen",
    "mogelijke_pipeline_fout": "geen" of "agent_01" of "agent_02" of "agent_03"
  }
]"""


def _connect() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    return conn


def _migrate() -> None:
    conn = _connect()
    for sql in [
        "ALTER TABLE items ADD COLUMN ethics_verdict TEXT",
        "ALTER TABLE items ADD COLUMN ethics_score   INTEGER",
        "ALTER TABLE items ADD COLUMN ethics_report  TEXT",
        "CREATE INDEX IF NOT EXISTS idx_items_ethics ON items(ethics_verdict)",
    ]:
        try:
            conn.execute(sql)
        except Exception:
            pass
    conn.commit()
    conn.close()


def _calc_verdict(scores: dict) -> str:
    if not scores:
        return "ORANJE"
    vals = list(scores.values())
    avg  = sum(vals) / len(vals)
    minimum = min(vals)
    if minimum < 40:
        return "ORANJE" if avg >= 45 else "ROOD"
    if avg >= 70:   return "GROEN"
    if avg >= 45:   return "ORANJE"
    return "ROOD"


async def check_batch(batch: list[dict], sem: asyncio.Semaphore) -> list[dict]:
    """Stuur een batch van max BATCH_SIZE items naar Agent 04. Returnt lijst met resultaten."""
    input_data = [
        {
            "item_id":        item["url"],
            "titel":          item.get("title", ""),
            "tekst":          (item.get("full_content") or item.get("content") or "")[:800],
            "originele_bron": item.get("source", ""),
            "ranking_score":  item.get("relevance_score", 0),
            "paywall_omzeild": item.get("source", "") in PAYWALL_SOURCES,
        }
        for item in batch
    ]

    async with sem:
        try:
            resp = await asyncio.wait_for(
                client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user",   "content": json.dumps(input_data, ensure_ascii=False)},
                    ],
                    max_tokens=1800,
                    temperature=0.1,
                    response_format={"type": "json_object"},
                ),
                timeout=60.0,
            )
            raw = resp.choices[0].message.content
            # Model geeft soms {"results": [...]} of {"items": [...]} terug ipv directe array
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
            # Zoek de array in het object
            for v in parsed.values():
                if isinstance(v, list):
                    return v
            return []
        except Exception as e:
            logger.warning(f"  Batch-fout: {e}")
            return []


def _save_results(results: list[dict], items_by_url: dict) -> int:
    """Sla resultaten op in de DB. Returnt aantal opgeslagen items."""
    saved = 0
    conn  = _connect()
    for r in results:
        url = r.get("item_id", "")
        if not url or url not in items_by_url:
            continue
        scores  = r.get("scores", {})
        overall = r.get("overall_score")
        if overall is None and scores:
            vals    = list(scores.values())
            overall = round(sum(vals) / len(vals))
        overall  = round(float(overall or 50))
        verdict  = _calc_verdict(scores)     # eigen berekening als verificatie
        r["verdict"]       = verdict
        r["overall_score"] = overall
        report = json.dumps(r, ensure_ascii=False)

        conn.execute(
            "UPDATE items SET ethics_verdict=?, ethics_score=?, ethics_report=? WHERE url=?",
            (verdict, overall, report, url),
        )
        saved += 1

        icon = {"GROEN": "✅", "ORANJE": "⚠️", "ROOD": "🚫"}.get(verdict, "?")
        logger.info(f"  {icon} [{verdict:6} {overall:3}/100] {items_by_url[url].get('title','')[:55]}")

    conn.commit()
    conn.close()
    return saved


async def run() -> None:
    _migrate()

    conn  = _connect()
    rows  = conn.execute(
        """SELECT url, title, source, content, full_content, relevance_score, prioriteit
           FROM items
           WHERE ethics_verdict IS NULL
           ORDER BY relevance_score DESC
           LIMIT ?""",
        (MAX_ITEMS,),
    ).fetchall()
    items = [dict(r) for r in rows]
    conn.close()

    if not items:
        logger.info("Agent 04 — geen nieuwe items om te checken.")
        return

    n_batches = (len(items) + BATCH_SIZE - 1) // BATCH_SIZE
    logger.info(f"Agent 04 — {len(items)} items → {n_batches} batches (gelijktijdig: {CONCURRENCY})…")

    items_by_url = {item["url"]: item for item in items}
    batches      = [items[i:i+BATCH_SIZE] for i in range(0, len(items), BATCH_SIZE)]
    sem          = asyncio.Semaphore(CONCURRENCY)

    tasks   = [check_batch(b, sem) for b in batches]
    results_nested = await asyncio.gather(*tasks)

    all_results = [r for batch_res in results_nested for r in batch_res]
    total_saved = _save_results(all_results, items_by_url)

    logger.info(f"Agent 04 — ✓ {total_saved}/{len(items)} items gecheckt")


if __name__ == "__main__":
    asyncio.run(run())

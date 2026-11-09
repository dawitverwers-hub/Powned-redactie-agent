"""Automatisering 2 — PowNed relevantie-scoring met OpenAI.

Scoort artikelen in batches van 10 (1 API-call per 10 items).
Vijf criteria, totaal 0-100. Slaat op in:
  relevance_score  → totaal 0-100
  relevance_reason → redactiefeedback (1 zin + concrete actie)
  score_breakdown  → JSON met 5 deelscores
  prioriteit       → must-have | sterk | interessant | zwak | afwijzen

Run: PYTHONPATH=src python score_relevance.py
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

DB = Path(os.environ.get("DATABASE_URL", "").replace("sqlite:///", "", 1) or
          os.environ.get("DB_PATH", "") or
          str(ROOT / "data" / "powned.db"))

BATCH_SIZE  = 20   # artikelen per API-call
CONCURRENCY = 1    # parallelle batches
RETRY_DELAY = 30   # seconden wachten bij rate limit

SYSTEM_PROMPT = """Je bent een PowNed-redacteur. Beoordeel nieuwsitems op PowNed-fit.

PowNed maakt nieuws voor jongeren (18–35): emotioneel, deelbaar, visueel sterk, kritisch op autoriteit. Lokale verhalen met landelijke haak scoren hoog.

Beoordeel elk item op VIJF criteria:

1. viraal (max 25): trending/woede/burger-vs-systeem? 20-25=viraal, 10-19=potentieel, 0-9=vlak
2. visueel (max 20): beeldmateriaal beschikbaar? 17-20=gegarandeerd, 10-16=mogelijk, 0-9=geen
3. nieuwswaarde (max 20): urgentie en exclusiviteit? 17-20=<6u oud+exclusief, 10-16=vandaag+breed, 0-9=oud/achtergrond
4. landelijk (max 20): lokale trigger met landelijke haak? 17-20=raakt debat direct, 10-16=verbinding mogelijk, 0-9=puur lokaal
5. doelgroepfit (max 15): past bij 18-35 jaar? 12-15=leeft op socials+onrechtvaardigheid, 7-11=breed, 0-6=te oud/abstract

Geef ook 1 feedbackzin voor de redacteur (max 15 woorden, concrete actie: interview/beelden ophalen/TikTok/bellen).

Antwoord ALLEEN met JSON-array, zelfde volgorde als input:
[{"id":<id>,"viraal":<0-25>,"visueel":<0-20>,"nieuwswaarde":<0-20>,"landelijk":<0-20>,"doelgroepfit":<0-15>,"feedback":"<zin>"}]"""


def _prioriteit(score: int) -> str:
    if score >= 85: return "must-have"
    if score >= 70: return "sterk"
    if score >= 55: return "interessant"
    if score >= 40: return "zwak"
    return "afwijzen"


def _build_batch_prompt(batch: list[dict]) -> str:
    items = []
    for item in batch:
        content = (item.get("full_content") or item.get("content") or "")[:400]
        items.append({
            "id":    item["_idx"],
            "titel": item["title"],
            "bron":  f"{item['source']} ({item.get('region') or 'NL'})",
            "tekst": content,
        })
    return json.dumps(items, ensure_ascii=False)


async def score_batch(
    client: AsyncOpenAI,
    sem: asyncio.Semaphore,
    batch: list[dict],
) -> list[tuple] | None:
    async with sem:
        for attempt in range(4):
            try:
                resp = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    max_tokens=BATCH_SIZE * 80,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user",   "content": _build_batch_prompt(batch)},
                    ],
                )
                raw = resp.choices[0].message.content.strip()
                parsed = json.loads(raw)

                # Model geeft soms {"items": [...]} of {"results": [...]} terug
                if isinstance(parsed, dict):
                    results_list = next(
                        (v for v in parsed.values() if isinstance(v, list)), []
                    )
                else:
                    results_list = parsed

                out = []
                for r in results_list:
                    idx       = int(r.get("id", -1))
                    viraal    = max(0, min(25, int(r.get("viraal", 0))))
                    visueel   = max(0, min(20, int(r.get("visueel", 0))))
                    nieuws    = max(0, min(20, int(r.get("nieuwswaarde", 0))))
                    landelijk = max(0, min(20, int(r.get("landelijk", 0))))
                    doelgroep = max(0, min(15, int(r.get("doelgroepfit", 0))))
                    score     = viraal + visueel + nieuws + landelijk + doelgroep
                    feedback  = str(r.get("feedback", ""))[:300]
                    prio      = _prioriteit(score)
                    breakdown = json.dumps({
                        "viraal": viraal, "visueel": visueel,
                        "nieuwswaarde": nieuws, "landelijkPotentieel": landelijk,
                        "doelgroepfit": doelgroep,
                    })
                    item = next((i for i in batch if i["_idx"] == idx), None)
                    if item:
                        out.append((item["url"], score, feedback, breakdown, prio))
                return out

            except Exception as exc:
                err = str(exc)
                if "429" in err or "rate_limit" in err.lower():
                    wait = RETRY_DELAY * (2 ** attempt)
                    logger.warning(f"Rate limit — wacht {wait}s (poging {attempt+1}/4)")
                    await asyncio.sleep(wait)
                else:
                    logger.warning(f"Batch mislukt: {exc}")
                    return None

        logger.warning("Batch opgegeven na 4 pogingen")
        return None


async def run() -> None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("Geen OPENAI_API_KEY gevonden")
        return

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT url, title, source, region, content, full_content "
        "FROM items WHERE prioriteit IS NULL AND title IS NOT NULL AND title != ''"
    ).fetchall()
    items = [dict(r) for r in rows]

    if not items:
        logger.info("Alles al gescoord.")
        conn.close()
        return

    for i, item in enumerate(items):
        item["_idx"] = i

    n_batches = (len(items) + BATCH_SIZE - 1) // BATCH_SIZE
    logger.info(f"{len(items)} items → {n_batches} API-calls (batches van {BATCH_SIZE})…")

    batches      = [items[i:i+BATCH_SIZE] for i in range(0, len(items), BATCH_SIZE)]
    client       = AsyncOpenAI(api_key=api_key)
    sem          = asyncio.Semaphore(CONCURRENCY)
    batch_results = await asyncio.gather(*(score_batch(client, sem, b) for b in batches))

    valid = [r for batch in batch_results if batch for r in batch]

    if valid:
        conn.executemany(
            "UPDATE items SET relevance_score=?, relevance_reason=?, "
            "score_breakdown=?, prioriteit=? WHERE url=?",
            [(score, fb, bd, prio, url) for url, score, fb, bd, prio in valid],
        )
        conn.commit()

        avg    = sum(r[1] for r in valid) / len(valid)
        counts = {}
        for _, _, _, _, prio in valid:
            counts[prio] = counts.get(prio, 0) + 1

        logger.info(f"✓ {len(valid)}/{len(items)} gescoord | gemiddelde: {avg:.0f}/100")
        logger.info("Verdeling: " + " | ".join(
            f"{p}: {counts.get(p,0)}" for p in
            ["must-have", "sterk", "interessant", "zwak", "afwijzen"]
        ))
        top = sorted(valid, key=lambda x: x[1], reverse=True)[:5]
        logger.info("Top 5:")
        for url, score, fb, _, prio in top:
            title = next((i["title"] for i in items if i["url"] == url), url)
            logger.info(f"  [{score}/100 · {prio}] {title[:65]}")
            logger.info(f"    → {fb}")

    conn.close()


if __name__ == "__main__":
    asyncio.run(run())

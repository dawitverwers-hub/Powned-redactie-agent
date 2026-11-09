"""Entry point voor Automatisering 1 — PowNed Redactie Agent.

Runt de hele dataverzameling-pipeline:
  1. Laadt bronnenlijst uit config/sources.yml
  2. Dispatcht per source-type naar de juiste module
  3. Past paywall-bypass toe waar nodig
  4. Slaat ruwe items op in de database (met dedupe)

Run: python src/main.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import yaml
from dotenv import load_dotenv
from loguru import logger

from sources import rss, scraper, playwright_src, sitemap_src
from storage import db

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "sources.yml"


def load_sources() -> list[dict]:
    """Lees bronnenlijst uit YAML."""
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config.get("sources", [])


async def fetch_source(source: dict) -> list[dict]:
    """Dispatch per source-type naar de juiste module."""
    source_type = source.get("type")
    name = source.get("name", "?")
    logger.info(f"Ophalen: {name} ({source_type})")

    try:
        if source_type == "rss":
            return await rss.fetch(source)
        if source_type == "sitemap":
            return await sitemap_src.fetch(source)
        if source_type == "scraper":
            return await scraper.fetch(source)
        if source_type == "playwright":
            return await playwright_src.fetch(source)
        # TODO: social, mail
        logger.warning(f"Onbekend source-type: {source_type} ({name})")
        return []
    except Exception as exc:
        logger.error(f"Fout bij {name}: {exc}")
        return []


RETENTION_DAYS = 7  # artikelen ouder dan dit worden verwijderd


async def run_pipeline() -> None:
    """Hoofd-pipeline."""
    db.init()
    sources = load_sources()
    logger.info(f"{len(sources)} bronnen geladen")

    # Parallel ophalen
    results = await asyncio.gather(*(fetch_source(s) for s in sources))

    # Plat slaan + dedupe in db
    new_items = 0
    for items in results:
        for item in items:
            if db.insert_if_new(item):
                new_items += 1

    logger.info(f"Pipeline klaar — {new_items} nieuwe items opgeslagen")

    # Opruimen: verwijder artikelen ouder dan RETENTION_DAYS
    deleted = db.delete_older_than(RETENTION_DAYS)
    if deleted:
        logger.info(f"🗑️  {deleted} artikelen ouder dan {RETENTION_DAYS} dagen verwijderd")


def main() -> None:
    load_dotenv(ROOT / ".env")
    asyncio.run(run_pipeline())


if __name__ == "__main__":
    main()

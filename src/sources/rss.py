"""RSS-bronnen ophalen."""

from __future__ import annotations

import asyncio
from email.utils import parsedate_to_datetime

import feedparser
import httpx
from loguru import logger

# Standaard browser User-Agent
_UA_BROWSER = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Google Feedfetcher UA — sommige sites serveren RSS alleen aan Google
_UA_FEEDFETCHER = "Feedfetcher-Google; (+http://www.google.com/feedfetcher.html)"


def _to_iso(date_str: str) -> str:
    """Zet RFC 2822 datumstring om naar ISO 8601. Geeft origineel terug bij fout."""
    if not date_str:
        return ""
    try:
        return parsedate_to_datetime(date_str).isoformat()
    except Exception:
        return date_str


def _fetch_sync(url: str, user_agent: str) -> str | None:
    """Synchrone RSS-fetch via httpx met opgegeven User-Agent."""
    try:
        with httpx.Client(
            headers={"User-Agent": user_agent, "Accept": "application/rss+xml, application/xml, */*"},
            follow_redirects=True,
            timeout=15,
        ) as client:
            r = client.get(url)
            if r.status_code == 200:
                txt = r.text.strip()
                if txt.startswith("<?xml") or txt.startswith("<rss") or "<channel>" in txt[:500]:
                    return txt
    except Exception as exc:
        logger.debug(f"httpx fetch fout voor {url}: {exc}")
    return None


async def fetch(source: dict) -> list[dict]:
    """Lees een RSS-feed en geef items terug in de standaard shape.

    Gebruikt httpx met browser- of Feedfetcher-UA, valt terug op feedparser
    als httpx niets bruikbaars teruggeeft.
    """
    url = source["url"]
    ua_hint = source.get("user_agent", "browser")

    loop = asyncio.get_running_loop()

    # Bepaal User-Agent volgorde
    if ua_hint == "feedfetcher":
        agents = [_UA_FEEDFETCHER, _UA_BROWSER]
    else:
        agents = [_UA_BROWSER, _UA_FEEDFETCHER]

    xml_content: str | None = None
    for agent in agents:
        xml_content = await loop.run_in_executor(None, _fetch_sync, url, agent)
        if xml_content:
            break

    if xml_content:
        parsed = feedparser.parse(xml_content)
    else:
        # Laatste redmiddel: feedparser native fetch
        parsed = await loop.run_in_executor(None, feedparser.parse, url)

    if parsed.bozo and not parsed.entries:
        logger.warning(f"RSS niet leesbaar: {source['name']} ({parsed.bozo_exception})")
        return []

    items: list[dict] = []
    for entry in parsed.entries:
        raw_date = entry.get("published", entry.get("updated", ""))
        items.append(
            {
                "url": entry.get("link"),
                "title": entry.get("title", "").strip(),
                "source": source["name"],
                "published_at": _to_iso(raw_date),
                "content": entry.get("summary", ""),
                "image_url": _extract_image(entry),
                "region": source.get("region"),
                "raw_html": None,
            }
        )

    logger.debug(f"RSS {source['name']}: {len(items)} items")
    return items


def _extract_image(entry: dict) -> str | None:
    """Probeer een afbeelding-URL uit het feed-entry te halen."""
    # media:content (meest betrouwbaar)
    if "media_content" in entry and entry["media_content"]:
        url = entry["media_content"][0].get("url", "")
        if url and url.startswith("http"):
            return url
    # media:thumbnail
    if "media_thumbnail" in entry and entry["media_thumbnail"]:
        url = entry["media_thumbnail"][0].get("url", "")
        if url and url.startswith("http"):
            return url
    # enclosure
    if "enclosures" in entry:
        for enc in entry["enclosures"]:
            if enc.get("type", "").startswith("image/") and enc.get("href", "").startswith("http"):
                return enc["href"]
    # link met image type
    if "links" in entry:
        for link in entry["links"]:
            if link.get("type", "").startswith("image/") and link.get("href", "").startswith("http"):
                return link.get("href")
    return None

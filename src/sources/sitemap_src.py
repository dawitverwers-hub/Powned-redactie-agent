"""Google News Sitemap bron — leest sitemap-news.xml voor directe artikel-URLs.

Veel nieuwssites publiceren een Google News Sitemap (`sitemap-news.xml`) met
recente artikelen inclusief directe URLs. Dit is beter dan Google News RSS
omdat de URLs al gedecodeerd zijn zodat enrich_content.py er og:image van kan
ophalen.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from loguru import logger

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _parse_sitemap(xml: str, source_name: str, region: str | None) -> list[dict]:
    """Verwerk sitemap-news.xml XML naar standaard Item-list."""
    soup = BeautifulSoup(xml, "xml")
    items: list[dict] = []

    for url_tag in soup.find_all("url"):
        loc = url_tag.find("loc")
        if not loc:
            continue
        article_url = loc.get_text(strip=True)

        # Publicatiedatum
        published_at = ""
        # news:publication_date heeft prioriteit
        pub_date_tag = url_tag.find("news:publication_date") or url_tag.find("publication_date")
        if pub_date_tag:
            published_at = pub_date_tag.get_text(strip=True)
        else:
            lastmod = url_tag.find("lastmod")
            if lastmod:
                published_at = lastmod.get_text(strip=True)

        # Titel
        title = ""
        title_tag = url_tag.find("news:title") or url_tag.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

        items.append({
            "url": article_url,
            "title": title,
            "source": source_name,
            "published_at": published_at,
            "content": "",
            "image_url": None,
            "region": region,
            "raw_html": None,
        })

    return items


def _fetch_sync(url: str) -> str | None:
    """Synchrone sitemap-fetch via httpx."""
    try:
        with httpx.Client(
            headers={"User-Agent": _UA, "Accept": "application/xml, text/xml, */*"},
            follow_redirects=True,
            timeout=15,
        ) as client:
            r = client.get(url)
            if r.status_code == 200:
                return r.text
    except Exception as exc:
        logger.debug(f"Sitemap fetch fout voor {url}: {exc}")
    return None


async def fetch(source: dict) -> list[dict]:
    """Haal sitemap-news.xml op en geef items terug in standaard shape."""
    url = source["url"]
    name = source["name"]
    region = source.get("region")

    loop = asyncio.get_running_loop()
    xml = await loop.run_in_executor(None, _fetch_sync, url)

    if not xml:
        logger.warning(f"Sitemap niet beschikbaar: {name} ({url})")
        return []

    items = _parse_sitemap(xml, name, region)
    logger.debug(f"Sitemap {name}: {len(items)} items")
    return items

"""HTML scraping voor bronnen zonder bruikbare RSS."""

from __future__ import annotations

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from paywall import bypass

USER_AGENT = (
    "Mozilla/5.0 (compatible; PowNedRedactieAgent/0.1; "
    "+https://example.nl/bot)"  # TODO: vervang door definitieve URL
)


async def fetch(source: dict) -> list[dict]:
    """Scrape een overzichtspagina en haal artikel-links op.

    NB: deze implementatie is een skeleton. Per site moet je een eigen
    selector-strategie kiezen (CSS-selectors of XPath). Overweeg per bron
    een aparte adapter onder src/sources/sites/<naam>.py.
    """
    url = source["url"]
    name = source["name"]

    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True
    ) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning(f"HTTP-fout {name}: {exc}")
            return []

    soup = BeautifulSoup(response.text, "lxml")

    # TODO: site-specifieke link-extractie. Voor nu een naïeve aanpak:
    # alle <a href> die er als artikel uitzien (bevat /20XX/ of /artikel/).
    article_links: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/202" in href or "/artikel" in href or "/nieuws" in href:
            full = httpx.URL(url).join(href)
            article_links.add(str(full))

    logger.debug(f"Scraper {name}: {len(article_links)} kandidaat-links")

    items: list[dict] = []
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True
    ) as client:
        for link in list(article_links)[:20]:  # rate-limit per run
            item = await _fetch_article(client, link, source)
            if item:
                items.append(item)

    return items


async def _fetch_article(
    client: httpx.AsyncClient, url: str, source: dict
) -> dict | None:
    """Haal één artikel op. Past paywall-bypass toe als nodig."""
    try:
        response = await client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.debug(f"Artikel niet bereikbaar {url}: {exc}")
        return None

    html = response.text

    if source.get("paywall"):
        full = await bypass.unlock(url, html)
        if full:
            html = full

    soup = BeautifulSoup(html, "lxml")
    title = soup.find("h1")
    title_text = title.get_text(strip=True) if title else ""

    return {
        "url": url,
        "title": title_text,
        "source": source["name"],
        "published_at": "",  # TODO: extract uit meta-tags
        "content": _extract_main_text(soup),
        "image_url": None,
        "region": source.get("region"),
        "raw_html": html,
    }


def _extract_main_text(soup: BeautifulSoup) -> str:
    """Heel naïeve hoofdtekst-extractie. Vervang door bv. trafilatura."""
    article = soup.find("article") or soup.find("main") or soup.body
    if not article:
        return ""
    paragraphs = [p.get_text(strip=True) for p in article.find_all("p")]
    return "\n\n".join(p for p in paragraphs if p)

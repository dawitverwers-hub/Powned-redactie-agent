"""Playwright-gebaseerde scraper voor sites die httpx blokkeren (bv. Telegraaf)."""

from __future__ import annotations

import httpx
from bs4 import BeautifulSoup
from loguru import logger

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


async def fetch(source: dict) -> list[dict]:
    if not PLAYWRIGHT_AVAILABLE:
        logger.error("Playwright niet geïnstalleerd — sla bron over: " + source["name"])
        return []

    url = source["url"]
    name = source["name"]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=_USER_AGENT)

        # Overzichtspagina — wacht op networkidle zodat JS artikel-links heeft gerenderd
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
            html = await page.content()
        except Exception as exc:
            logger.warning(f"Playwright-fout {name}: {exc}")
            await browser.close()
            return []

        soup = BeautifulSoup(html, "lxml")
        article_links: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/202" in href or "/artikel" in href or "/nieuws" in href:
                full = str(httpx.URL(url).join(href))
                article_links.add(full)

        logger.debug(f"Playwright {name}: {len(article_links)} kandidaat-links")

        # Artikelen ophalen — browser hergebruiken, niet per artikel opnieuw starten
        items: list[dict] = []
        for link in list(article_links)[:15]:
            title, content = await _fetch_article_text(context, link)
            if title:
                items.append(
                    {
                        "url": link,
                        "title": title,
                        "source": name,
                        "published_at": "",
                        "content": content,
                        "image_url": None,
                        "region": source.get("region"),
                        "raw_html": None,
                    }
                )

        await browser.close()

    return items


async def _fetch_article_text(context, url: str) -> tuple[str, str]:
    """Haal titel en hoofdtekst op. Hergebruikt de meegegeven browser-context."""
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="networkidle", timeout=20000)
        html = await page.content()
    except Exception as exc:
        logger.debug(f"Artikel niet bereikbaar {url}: {exc}")
        await page.close()
        return "", ""
    finally:
        await page.close()

    soup = BeautifulSoup(html, "lxml")
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else ""
    article = soup.find("article") or soup.find("main") or soup.body
    paragraphs = [p.get_text(strip=True) for p in (article or soup).find_all("p")]
    content = "\n\n".join(p for p in paragraphs if p)
    return title, content

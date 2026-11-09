"""Haalt volledige artikeltekst op voor items met alleen een RSS-samenvatting.

Strategie:
  - Vrije bronnen  → trafilatura (snel, geen browser)
  - Paywall bronnen → Playwright headless Chromium (render JS, bypass soft paywall)
  - Fallback        → RSS samenvatting als alles mislukt

Run: PYTHONPATH=src python3 enrich_content.py
"""

from __future__ import annotations

import asyncio
import os as _os
import re
import sqlite3
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from loguru import logger

try:
    import trafilatura as _trafilatura
    _HAS_TRAFILATURA = True
except ImportError:
    _HAS_TRAFILATURA = False

try:
    from playwright.async_api import async_playwright
    _HAS_PLAYWRIGHT = True
except ImportError:
    _HAS_PLAYWRIGHT = False

try:
    from googlenewsdecoder import new_decoderv1 as _gnd_decode
    _HAS_GND = True
except ImportError:
    _HAS_GND = False

DB = Path(_os.environ.get("DATABASE_URL", "").replace("sqlite:///", "", 1) or
          _os.environ.get("DB_PATH", "") or
          str(Path(__file__).parent / "data" / "powned.db"))

CONCURRENCY_FREE     = 10   # parallelle fetches voor vrije bronnen
CONCURRENCY_PAYWALL  = 2    # Playwright: minder parallel (zwaarder)
TIMEOUT = 20

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "nl-NL,nl;q=0.9",
}

# Bronnen zonder paywall
FREE_SOURCES = {
    "PowNed",
    "NOS", "De Telegraaf", "RTL Nieuws", "Hart van Nederland",
    "Politie", "Rechtspraak", "Crimesite",
    "NH Nieuws", "AT5", "Gooi- en Eemlander",
    "Rijnmond", "Regio 15", "Omroep West", "RTV Utrecht",
    "Omroep Brabant", "BN De Stem", "De Stentor", "PZC",
    "RTV Noord", "L1 Limburg",
    "Zoekterm Zwarte Piet", "Zoekterm Demonstratie", "Zoekterm Inbraak",
    "MinPres Jetten", "Geert Wilders", "Thierry Baudet",
    "Pepijn van Houwelingen", "Extinction Rebellion",
}

# Bronnen met paywall — Playwright headless bypass
PAYWALL_SOURCES = {"AD", "Volkskrant", "Trouw"}

ELIGIBLE_SOURCES = FREE_SOURCES | PAYWALL_SOURCES

PAYWALL_MARKERS = [
    "inloggen om verder te lezen",
    "dit artikel is alleen voor abonnees",
    "lees verder met een abonnement",
    "word abonnee om verder te lezen",
    "unlock this article",
    "subscribe to read",
    "log in to continue",
    "subscribers only",
    "je hebt een abonnement nodig",
    "alleen voor abonnees",
    "lees dit artikel gratis",
    "maak een gratis account",
]


def _is_paywalled(html: str) -> bool:
    """Strikte paywall-check: lange, specifieke zinnen die ALLEEN in paywall-blokken voorkomen."""
    low = html.lower()
    return any(m in low for m in PAYWALL_MARKERS)


def _has_enough_content(html: str, min_chars: int = 500) -> bool:
    """Check of er genoeg leesbare tekst in de pagina zit."""
    soup = BeautifulSoup(html, "lxml")
    text = " ".join(p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 40)
    return len(text) >= min_chars


def _extract_text_bs4(html: str) -> str:
    """BeautifulSoup fallback tekst-extractor."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "aside", "header"]):
        tag.decompose()
    article = (soup.find("article")
               or soup.find(class_=re.compile(r"article|content|body", re.I))
               or soup.find("main"))
    if not article:
        article = soup.body
    if not article:
        return ""
    paragraphs = [p.get_text(" ", strip=True) for p in article.find_all("p")
                  if len(p.get_text(strip=True)) > 40]
    return "\n\n".join(paragraphs)


def _extract_text_trafilatura(html: str, url: str = "") -> str:
    """trafilatura tekst-extractor — nauwkeuriger dan BeautifulSoup."""
    if not _HAS_TRAFILATURA:
        return _extract_text_bs4(html)
    try:
        text = _trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
            favor_recall=True,
        )
        return text or ""
    except Exception:
        return _extract_text_bs4(html)


def _extract_image(html: str) -> str | None:
    soup = BeautifulSoup(html, "lxml")
    for prop in ("og:image", "og:image:secure_url", "twitter:image", "twitter:image:src"):
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        if tag:
            img = tag.get("content", "").strip()
            if img.startswith("http"):
                return img
    for container in (soup.find("article"), soup.find("main")):
        if not container:
            continue
        for img_tag in container.find_all("img", src=True):
            src = img_tag["src"].strip()
            if src.startswith("http") and not any(x in src for x in ("icon", "logo", "avatar", "pixel")):
                return src
    return None


def _decode_sync(url: str) -> str:
    if not _HAS_GND:
        return url
    try:
        result = _gnd_decode(url)
        if result.get("status") and result.get("decoded_url"):
            decoded = result["decoded_url"]
            if "news.google.com" not in decoded:
                decoded = re.sub(r"^https?://(?!www\.)(powned\.tv)", r"https://www.\1", decoded)
                return decoded
    except Exception as exc:
        logger.debug(f"Google News decode fout: {exc}")
    return url


async def resolve_google_news_url(url: str) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _decode_sync, url)


# ──────────────────────────────────────────────
#  Snelle og:image-only fetch (alleen <head>)
# ──────────────────────────────────────────────

async def fetch_og_image(client: httpx.AsyncClient, url: str) -> str | None:
    """Haal alleen de og:image op door de eerste 8KB van de pagina te lezen."""
    try:
        async with client.stream("GET", url, timeout=10, follow_redirects=True) as r:
            if r.status_code != 200:
                return None
            chunk = b""
            async for data in r.aiter_bytes(chunk_size=4096):
                chunk += data
                if len(chunk) >= 12288 or b"</head>" in chunk.lower():
                    break
        html = chunk.decode("utf-8", errors="ignore")
        return _extract_image(html)
    except Exception:
        return None


# ──────────────────────────────────────────────
#  Vrije bronnen: trafilatura via httpx
# ──────────────────────────────────────────────

async def fetch_free(client: httpx.AsyncClient, url: str) -> tuple[str | None, str | None]:
    """Haal vrij artikel op via httpx + trafilatura."""
    try:
        r = await client.get(url, timeout=TIMEOUT, follow_redirects=True)
        if r.status_code != 200:
            return None, None
        html = r.text
        if _is_paywalled(html):
            logger.debug(f"Onverwachte paywall bij vrije bron: {url}")
            return None, None
        text = _extract_text_trafilatura(html, url)
        img = _extract_image(html)
        return (text if len(text) > 200 else None), img
    except Exception as exc:
        logger.debug(f"Fout bij {url}: {exc}")
        return None, None


# ──────────────────────────────────────────────
#  Paywall-bronnen: Playwright headless Chromium
# ──────────────────────────────────────────────

async def fetch_via_playwright(url: str) -> tuple[str | None, str | None]:
    """Haal paywall-artikel op via Playwright. Geeft (tekst, img_url)."""
    if not _HAS_PLAYWRIGHT:
        logger.warning("Playwright niet beschikbaar — paywall-bypass overgeslagen")
        return None, None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                locale="nl-NL",
            )
            page = await context.new_page()

            await page.goto(url, timeout=20000, wait_until="load")
            await page.wait_for_timeout(2000)   # wacht op late JS-rendering

            html = await page.content()
            await browser.close()

        # Alleen echte paywall als er ook GEEN content is (headers/footers bevatten ook paywall-woorden)
        if _is_paywalled(html) and not _has_enough_content(html):
            logger.debug(f"Paywall na JS-render (geen content): {url}")
            return None, None

        text = _extract_text_trafilatura(html, url)
        if not text or len(text) < 200:
            text = _extract_text_bs4(html)
        img = _extract_image(html)
        return (text if len(text) > 200 else None), img

    except Exception as exc:
        logger.debug(f"Playwright fout voor {url}: {exc}")
        return None, None


# ──────────────────────────────────────────────
#  Gecombineerde fetch
# ──────────────────────────────────────────────

async def fetch_full(
    client: httpx.AsyncClient,
    url: str,
    source: str,
    paywall_sem: asyncio.Semaphore,
) -> tuple[str | None, str | None, str]:
    """Haal volledige tekst + afbeelding op. Geeft (tekst, img_url, echte_url)."""
    real_url = url
    if "news.google.com" in url:
        real_url = await resolve_google_news_url(url)
        if real_url != url:
            logger.debug(f"Google News decoded → {real_url[:80]}")

    if source in PAYWALL_SOURCES:
        async with paywall_sem:
            text, img = await fetch_via_playwright(real_url)
        # Fallback: gewone fetch (soms geen paywall op eerste hit)
        if not text:
            text, img = await fetch_free(client, real_url)
    else:
        text, img = await fetch_free(client, real_url)

    return text, img, real_url


# ──────────────────────────────────────────────
#  Hoofd-loop
# ──────────────────────────────────────────────

async def enrich() -> None:
    conn = sqlite3.connect(DB)

    # ── Stap A: artikelen zonder volledige tekst ─────────────────────────
    rows_text = conn.execute(
        "SELECT url, source, image_url, content FROM items "
        "WHERE (full_content IS NULL OR full_content = '') "
        "AND source IN ({})".format(",".join("?" * len(ELIGIBLE_SOURCES))),
        list(ELIGIBLE_SOURCES),
    ).fetchall()

    # ── Stap B: artikelen met tekst maar zonder afbeelding ───────────────
    rows_img = conn.execute(
        "SELECT url, source, image_url, content FROM items "
        "WHERE (image_url IS NULL OR image_url = '') "
        "AND (full_content IS NOT NULL AND full_content != '') "
        "AND source IN ({})".format(",".join("?" * len(ELIGIBLE_SOURCES))),
        list(ELIGIBLE_SOURCES),
    ).fetchall()

    logger.info(f"{len(rows_text)} items te verrijken met tekst, {len(rows_img)} extra voor afbeelding…")

    free_sem    = asyncio.Semaphore(CONCURRENCY_FREE)
    paywall_sem = asyncio.Semaphore(CONCURRENCY_PAYWALL)

    # url → (full_content | None, img_url | None, real_url)
    results: dict[str, tuple[str | None, str | None, str]] = {}

    async def worker(url: str, source: str, existing_img: str | None,
                     rss_content: str | None, img_only: bool = False) -> None:
        if img_only:
            # Alleen og:image ophalen — snel, geen volledige pagina nodig
            async with free_sem:
                real_url = url
                if "news.google.com" in url:
                    real_url = await resolve_google_news_url(url)
                img = await fetch_og_image(client, real_url)
                if img:
                    results[url] = (None, img, real_url)
        else:
            async with free_sem if source not in PAYWALL_SOURCES else asyncio.Semaphore(999):
                text, img, real_url = await fetch_full(client, url, source, paywall_sem)
                if text and len(text) > 300:
                    results[url] = (text, img, real_url)
                elif img:
                    results[url] = (None, img, real_url)

    async with httpx.AsyncClient(headers=HEADERS) as client:
        tasks = [worker(url, src, img, rss, False) for url, src, img, rss in rows_text]
        tasks += [worker(url, src, img, rss, img_only=True) for url, src, img, rss in rows_img]
        await asyncio.gather(*tasks)

    updated = 0
    for orig_url, (text, img, real_url) in results.items():
        try:
            conn.execute(
                "UPDATE items SET "
                "full_content = CASE WHEN ? IS NOT NULL THEN ? ELSE full_content END, "
                "url = CASE WHEN ? != url THEN ? ELSE url END, "
                "image_url = CASE WHEN (image_url IS NULL OR image_url = '') AND ? IS NOT NULL THEN ? ELSE image_url END "
                "WHERE url = ?",
                (text, text, real_url, real_url, img, img, orig_url),
            )
            updated += 1
        except Exception as exc:
            # URL-conflict: sla URL-update over, bewaar alleen tekst/afbeelding
            try:
                conn.execute(
                    "UPDATE items SET "
                    "full_content = CASE WHEN ? IS NOT NULL THEN ? ELSE full_content END, "
                    "image_url = CASE WHEN (image_url IS NULL OR image_url = '') AND ? IS NOT NULL THEN ? ELSE image_url END "
                    "WHERE url = ?",
                    (text, text, img, img, orig_url),
                )
                updated += 1
            except Exception:
                logger.debug(f"Update overgeslagen voor {orig_url}: {exc}")
    if updated:
        conn.commit()
        logger.info(f"✓ {updated} artikelen bijgewerkt (tekst + afbeeldingen)")
    else:
        logger.info("Geen updates")

    conn.close()


if __name__ == "__main__":
    asyncio.run(enrich())

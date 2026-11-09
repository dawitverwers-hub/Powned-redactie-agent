"""Paywall-omzeiling.

LET OP — legal: PowNed gebruikt nu handmatig tools als removepaywall.com voor
research. Voordat dit in productie gaat moet er duidelijkheid zijn over wat
juridisch acceptabel is (auteursrecht, NVJ-code). Zie het canvas, blok 9
"Consideration & Implications".

Strategieën in volgorde van voorkeur:
  1. Google-referrer truc — sommige sites laten Googlebot/-referrer door
  2. Print-versie of AMP-versie van het artikel
  3. Headless browser (Playwright) met cookies/JS-uitschakeling
  4. Externe service (removepaywall.com / 12ft.io) — alleen voor research
"""

from __future__ import annotations

import httpx
from loguru import logger

USER_AGENT_GOOGLEBOT = (
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)


async def unlock(url: str, current_html: str) -> str | None:
    """Probeer de volledige tekst achter de paywall te krijgen.

    Returnt nieuwe HTML, of None als het niet lukt.
    """
    # Strategie 1: Googlebot-headers
    html = await _try_googlebot(url)
    if html and _looks_complete(html):
        logger.debug(f"Paywall omzeild via Googlebot: {url}")
        return html

    # TODO Strategie 2: AMP-versie
    # TODO Strategie 3: Playwright met JS-uitschakeling
    # TODO Strategie 4: externe service (alleen na legal-go)

    logger.info(f"Paywall niet omzeild: {url}")
    return None


async def _try_googlebot(url: str) -> str | None:
    headers = {
        "User-Agent": USER_AGENT_GOOGLEBOT,
        "Referer": "https://www.google.com/",
    }
    try:
        async with httpx.AsyncClient(
            headers=headers, timeout=30, follow_redirects=True
        ) as client:
            response = await client.get(url)
            if response.status_code == 200:
                return response.text
    except httpx.HTTPError:
        return None
    return None


def _looks_complete(html: str) -> bool:
    """Heuristiek: als de HTML duidelijk een paywall-marker bevat, is het niet compleet."""
    markers = ["paywall", "abonnee", "log in om verder te lezen", "premium-artikel"]
    lower = html.lower()
    return not any(m in lower for m in markers)

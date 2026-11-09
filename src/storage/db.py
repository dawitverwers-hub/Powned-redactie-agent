"""SQLite-opslag voor ruwe items.

Klein en synchroon — bewust simpel gehouden voor de eerste versie. Voor
productie kan dit naar Postgres met SQLAlchemy + async (asyncpg) worden
omgezet zonder de rest van de pipeline te raken.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path

from loguru import logger

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DB = ROOT / "data" / "powned.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    url              TEXT PRIMARY KEY,
    content_hash     TEXT NOT NULL,
    title            TEXT,
    source           TEXT,
    published_at     TEXT,
    content          TEXT,
    image_url        TEXT,
    region           TEXT,
    raw_html         TEXT,
    fetched_at       TEXT DEFAULT CURRENT_TIMESTAMP,
    relevance_score  INTEGER,
    relevance_reason TEXT,
    full_content     TEXT,
    score_breakdown  TEXT,
    prioriteit       TEXT
);
CREATE INDEX IF NOT EXISTS idx_items_source     ON items(source);
CREATE INDEX IF NOT EXISTS idx_items_region     ON items(region);
CREATE INDEX IF NOT EXISTS idx_items_fetched_at ON items(fetched_at);
"""

# Migratie voor bestaande databases die de nieuwe kolommen nog niet hebben.
# De relevance_score index staat hier zodat hij ná de kolom-migratie wordt aangemaakt.
MIGRATE_SQL = [
    "ALTER TABLE items ADD COLUMN relevance_score  INTEGER",
    "ALTER TABLE items ADD COLUMN relevance_reason TEXT",
    "ALTER TABLE items ADD COLUMN full_content     TEXT",
    "ALTER TABLE items ADD COLUMN score_breakdown  TEXT",
    "ALTER TABLE items ADD COLUMN prioriteit       TEXT",
    "ALTER TABLE items ADD COLUMN human_label      TEXT",
    "CREATE INDEX IF NOT EXISTS idx_items_relevance_score ON items(relevance_score)",
    "CREATE INDEX IF NOT EXISTS idx_items_prioriteit      ON items(prioriteit)",
    """CREATE TABLE IF NOT EXISTS editorial_rules (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        rule       TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        active     INTEGER DEFAULT 1
    )""",
    """CREATE TABLE IF NOT EXISTS chat_messages (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        role       TEXT NOT NULL,
        content    TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""",
    # Agent 04 — Ethische check
    "ALTER TABLE items ADD COLUMN ethics_verdict TEXT",
    "ALTER TABLE items ADD COLUMN ethics_score   INTEGER",
    "ALTER TABLE items ADD COLUMN ethics_report  TEXT",
    "CREATE INDEX IF NOT EXISTS idx_items_ethics ON items(ethics_verdict)",
]


def _db_path() -> Path:
    """Resolve database-pad uit DATABASE_URL of fallback."""
    url = os.getenv("DATABASE_URL", "")
    if url.startswith("sqlite:///"):
        return ROOT / url.replace("sqlite:///", "", 1)
    return DEFAULT_DB


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(path)


def init() -> None:
    """Maak schema aan als het nog niet bestaat, en migreer bestaande tabellen."""
    with _connect() as conn:
        conn.executescript(SCHEMA)
        for sql in MIGRATE_SQL:
            try:
                conn.execute(sql)
            except Exception:
                pass  # kolom bestaat al
    logger.info(f"Database klaar: {_db_path()}")


def insert_if_new(item: dict) -> bool:
    """Sla item op als URL nog niet bestaat. Returnt True als nieuw, False als duplicaat.

    Dedupe-strategie: primair op URL, secundair op content-hash (vangt
    dezelfde tekst op verschillende URLs).
    """
    url = item.get("url")
    if not url:
        return False

    content_hash = _hash(item.get("content", "") + item.get("title", ""))

    with _connect() as conn:
        cur = conn.execute(
            "SELECT 1 FROM items WHERE url = ? OR content_hash = ?",
            (url, content_hash),
        )
        if cur.fetchone():
            return False

        conn.execute(
            """
            INSERT INTO items
              (url, content_hash, title, source, published_at,
               content, image_url, region, raw_html)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                url,
                content_hash,
                item.get("title"),
                item.get("source"),
                item.get("published_at"),
                item.get("content"),
                item.get("image_url"),
                item.get("region"),
                item.get("raw_html"),
            ),
        )
    return True


def delete_older_than(days: int) -> int:
    """Verwijder artikelen ouder dan `days` dagen. Returnt het aantal verwijderde rijen."""
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM items WHERE fetched_at < datetime('now', ?)",
            (f"-{days} days",),
        )
        return cur.rowcount


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()

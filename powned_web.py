"""Eenvoudige webinterface voor de PowNed Redactie Feed.

Run: PYTHONPATH=src .venv/bin/python web.py
Open: http://localhost:5000
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import os

from flask import Flask, render_template_string, request

DB_PATH = Path("/path/to/powned.db")

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html lang="nl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PowNed Redactie Feed</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #0f0f0f;
      color: #f0f0f0;
      min-height: 100vh;
    }

    header {
      background: #e30613;
      padding: 18px 32px;
      display: flex;
      align-items: center;
      gap: 16px;
      position: sticky;
      top: 0;
      z-index: 100;
      box-shadow: 0 2px 12px rgba(0,0,0,0.5);
    }

    header h1 {
      font-size: 1.4rem;
      font-weight: 800;
      letter-spacing: -0.5px;
      color: #fff;
    }

    header span {
      background: rgba(255,255,255,0.2);
      color: #fff;
      font-size: 0.75rem;
      font-weight: 700;
      padding: 3px 10px;
      border-radius: 20px;
    }

    .toolbar {
      background: #1a1a1a;
      padding: 14px 32px;
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
      border-bottom: 1px solid #2a2a2a;
    }

    .toolbar label {
      font-size: 0.8rem;
      color: #888;
      margin-right: 4px;
    }

    select {
      background: #2a2a2a;
      color: #f0f0f0;
      border: 1px solid #3a3a3a;
      border-radius: 6px;
      padding: 6px 12px;
      font-size: 0.85rem;
      cursor: pointer;
    }

    select:focus { outline: 2px solid #e30613; }

    .stats {
      margin-left: auto;
      font-size: 0.8rem;
      color: #666;
    }

    .stats strong { color: #e30613; }

    main {
      max-width: 1100px;
      margin: 0 auto;
      padding: 28px 24px;
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 16px;
    }

    .card {
      background: #1a1a1a;
      border: 1px solid #2a2a2a;
      border-radius: 10px;
      padding: 18px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      transition: border-color 0.15s, transform 0.15s;
    }

    .card:hover {
      border-color: #e30613;
      transform: translateY(-2px);
    }

    .card-meta {
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
    }

    .badge {
      font-size: 0.7rem;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 4px;
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }

    .badge-source { background: #e30613; color: #fff; }
    .badge-region { background: #2a2a2a; color: #aaa; border: 1px solid #3a3a3a; }

    .card-date {
      font-size: 0.72rem;
      color: #555;
      margin-left: auto;
    }

    .card h2 {
      font-size: 0.97rem;
      font-weight: 700;
      line-height: 1.4;
      color: #f0f0f0;
    }

    .card p {
      font-size: 0.82rem;
      color: #888;
      line-height: 1.5;
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }

    .card a {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      margin-top: auto;
      padding: 7px 14px;
      background: transparent;
      border: 1px solid #333;
      border-radius: 6px;
      color: #ccc;
      text-decoration: none;
      font-size: 0.8rem;
      font-weight: 600;
      transition: background 0.15s, border-color 0.15s, color 0.15s;
      align-self: flex-start;
    }

    .card a:hover {
      background: #e30613;
      border-color: #e30613;
      color: #fff;
    }

    .empty {
      grid-column: 1/-1;
      text-align: center;
      padding: 60px;
      color: #444;
    }
  </style>
</head>
<body>

<header>
  <h1>PowNed Redactie Feed</h1>
  <span>Automatisering 1</span>
</header>

<form method="get">
<div class="toolbar">
  <label>Bron</label>
  <select name="source" onchange="this.form.submit()">
    <option value="">Alle bronnen</option>
    {% for s in sources %}
    <option value="{{ s }}" {% if selected_source == s %}selected{% endif %}>{{ s }}</option>
    {% endfor %}
  </select>

  <label>Regio</label>
  <select name="region" onchange="this.form.submit()">
    <option value="">Alle regio's</option>
    {% for r in regions %}
    <option value="{{ r }}" {% if selected_region == r %}selected{% endif %}>{{ r }}</option>
    {% endfor %}
  </select>

  <div class="stats"><strong>{{ total }}</strong> items gevonden</div>
</div>
</form>

<main>
  {% for item in items %}
  <div class="card">
    <div class="card-meta">
      <span class="badge badge-source">{{ item.source }}</span>
      {% if item.region %}<span class="badge badge-region">{{ item.region }}</span>{% endif %}
      <span class="card-date">{{ item.published_at[:16] if item.published_at else '–' }}</span>
    </div>
    <h2>{{ item.title or '(geen titel)' }}</h2>
    {% if item.content %}
    <p>{{ item.content[:200] }}</p>
    {% endif %}
    <a href="{{ item.url }}" target="_blank" rel="noopener">
      ↗ Lees origineel
    </a>
  </div>
  {% else %}
  <div class="empty">Geen items gevonden.</div>
  {% endfor %}
</main>

</body>
</html>
"""


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def index():
    source = request.args.get("source", "")
    region = request.args.get("region", "")

    conn = get_db()

    sources = [r[0] for r in conn.execute("SELECT DISTINCT source FROM items ORDER BY source")]
    regions = [r[0] for r in conn.execute("SELECT DISTINCT region FROM items WHERE region IS NOT NULL ORDER BY region")]

    query = "SELECT * FROM items WHERE 1=1"
    params = []
    if source:
        query += " AND source = ?"
        params.append(source)
    if region:
        query += " AND region = ?"
        params.append(region)
    query += " ORDER BY fetched_at DESC, published_at DESC LIMIT 200"

    items = conn.execute(query, params).fetchall()
    total = len(items)
    conn.close()

    return render_template_string(
        HTML,
        items=items,
        sources=sources,
        regions=regions,
        selected_source=source,
        selected_region=region,
        total=total,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print(f"→ Open http://localhost:{port} in je browser")
    app.run(debug=True, port=port)

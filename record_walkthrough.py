"""
PowNed Redactie — End-to-End Product Walkthrough Recorder
Opname van de volledige productflow via Playwright.
Output: walkthrough_raw.webm → walkthrough.mp4 (via ffmpeg)
"""
import subprocess, sys, time, os
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_URL  = "http://localhost:5001"
EMAIL     = os.environ["POWNED_EMAIL"]
PASSWORD  = os.environ["POWNED_PASSWORD"]
OUT_DIR   = Path(__file__).parent / "walkthrough_output"
OUT_DIR.mkdir(exist_ok=True)
VIDEO_DIR = OUT_DIR / "video"
VIDEO_DIR.mkdir(exist_ok=True)

def slow_type(el, text, delay=60):
    """Typt tekst karakter voor karakter voor een realistisch effect."""
    el.click()
    for ch in text:
        el.type(ch)
        time.sleep(delay / 1000)

def smooth_scroll(page, px, steps=8):
    """Scrollt vloeiend naar beneden."""
    step = px // steps
    for _ in range(steps):
        page.mouse.wheel(0, step)
        time.sleep(0.12)

def pause(ms=1200):
    time.sleep(ms / 1000)

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--window-size=1440,900", "--disable-blink-features=AutomationControlled"]
        )
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 900},
            record_video_dir=str(VIDEO_DIR),
            record_video_size={"width": 1440, "height": 900},
            locale="nl-NL",
            color_scheme="dark",
        )
        page = ctx.new_page()

        # ── 1. Login scherm ──────────────────────────────────────────────────
        print("▶ Login...")
        page.goto(BASE_URL + "/login")
        pause(2000)

        email_field = page.locator("input[type='email'], input[name='email'], input[placeholder*='mail'], input[placeholder*='Mail']").first
        pw_field    = page.locator("input[type='password']").first

        slow_type(email_field, EMAIL, delay=55)
        pause(500)
        slow_type(pw_field, PASSWORD, delay=55)
        pause(800)

        page.locator("button[type='submit'], button:has-text('Inloggen')").first.click()
        page.wait_for_url("**/dashboard", timeout=8000)
        pause(2500)

        # ── 2. Dashboard ─────────────────────────────────────────────────────
        print("▶ Dashboard...")
        pause(3000)

        # Hover over elke tegel
        for selector in [".tile-feed", ".tile-agenda", ".tile-archief", ".tile-uitleg"]:
            try:
                el = page.locator(selector).first
                el.hover()
                pause(700)
            except Exception:
                pass
        pause(1500)

        # ── 3. Feed ──────────────────────────────────────────────────────────
        print("▶ Feed...")
        page.locator("a.tile-feed, a[href='/']").first.click()
        page.wait_for_url("**/", timeout=6000)
        pause(3000)

        # Scroll langzaam door de feed
        smooth_scroll(page, 600, steps=10)
        pause(1500)

        # Hover over een must-have kaart
        try:
            card = page.locator(".card.hero, .hot-card, .card").first
            card.hover()
            pause(1200)
        except Exception:
            pass

        # Klik op een kaart om de modal te openen
        try:
            page.locator(".card, .hot-card").first.click()
            pause(2500)

            # Hover over label-knoppen in de modal
            for sel in [".btn-label", ".fav-btn"]:
                try:
                    page.locator(sel).first.hover()
                    pause(600)
                except Exception:
                    pass

            # Sluit modal
            page.keyboard.press("Escape")
            pause(1000)
        except Exception:
            pass

        # Scroll terug omhoog
        page.evaluate("window.scrollTo({top: 0, behavior: 'smooth'})")
        pause(1500)

        # ── 4. Relevantie-slider in de sidebar ───────────────────────────────
        print("▶ Filters & relevantie-slider...")
        try:
            page.locator("#sidebarToggle").click()
            pause(1000)

            slider = page.locator("#scoreSlider")
            slider.hover()
            pause(600)

            # Sleep de slider naar rechts
            box = slider.bounding_box()
            if box:
                start_x = box["x"] + box["width"] * 0.05
                end_x   = box["x"] + box["width"] * 0.75
                y       = box["y"] + box["height"] / 2
                page.mouse.move(start_x, y)
                page.mouse.down()
                for step in range(10):
                    x = start_x + (end_x - start_x) * (step + 1) / 10
                    page.mouse.move(x, y)
                    time.sleep(0.08)
                page.mouse.up()
                pause(1500)

                # Slider terug naar 0
                page.mouse.move(start_x, y)
                page.mouse.down()
                for step in range(10):
                    x = end_x - (end_x - start_x) * (step + 1) / 10
                    page.mouse.move(x, y)
                    time.sleep(0.08)
                page.mouse.up()
                pause(800)

            # Sidebar sluiten
            page.locator("#sidebarToggle").click()
            pause(800)
        except Exception as e:
            print(f"  Slider overgeslagen: {e}")

        # ── 5. Kaart-tab ─────────────────────────────────────────────────────
        print("▶ Kaart...")
        try:
            page.locator(".tab[data-tab='kaart']").click()
            pause(4000)  # kaart laden

            # Hover over filter knoppen
            for btn_id in ["#btnMapMust", "#btnMapShould", "#btnMapAll"]:
                try:
                    page.locator(btn_id).hover()
                    pause(600)
                    page.locator(btn_id).click()
                    pause(1200)
                except Exception:
                    pass

            # Zoom in op de kaart
            try:
                map_el = page.locator("#nlMap")
                map_box = map_el.bounding_box()
                if map_box:
                    cx = map_box["x"] + map_box["width"] / 2
                    cy = map_box["y"] + map_box["height"] / 2
                    page.mouse.wheel(cx, cy, delta_x=0, delta_y=-300)
                    pause(1500)
                    page.mouse.wheel(cx, cy, delta_x=0, delta_y=300)
                    pause(800)
            except Exception:
                pass

            # Terug naar relevant tab
            page.locator(".tab[data-tab='relevant']").click()
            pause(1500)
        except Exception as e:
            print(f"  Kaart overgeslagen: {e}")

        # ── 6. Pow Patrol chat ───────────────────────────────────────────────
        print("▶ Pow Patrol chat...")
        try:
            page.locator("#chatFab").click()
            pause(1500)

            chat_input = page.locator("#chatInput")
            chat_input.click()
            pause(500)

            slow_type(chat_input, "Is dit de moeite waard voor PowNed?", delay=45)
            pause(800)
            page.keyboard.press("Enter")
            pause(5000)  # wacht op AI-antwoord

            # Scroll chat omlaag
            page.evaluate("document.getElementById('chatMessages').scrollTop = 9999")
            pause(2000)

            # Sluit chat
            page.locator(".chat-close").first.click()
            pause(1000)
        except Exception as e:
            print(f"  Chat overgeslagen: {e}")

        # ── 7. Agenda ────────────────────────────────────────────────────────
        print("▶ Agenda...")
        page.goto(BASE_URL + "/agenda")
        pause(3500)
        smooth_scroll(page, 400, steps=6)
        pause(2000)

        # ── 8. Archief ───────────────────────────────────────────────────────
        print("▶ Archief...")
        page.goto(BASE_URL + "/archief")
        pause(3000)

        # Klik door de filter-tabs
        for tab_text in ["♥ Favoriet", "✓ Interessant", "Alle"]:
            try:
                page.locator(f"button.tab:has-text('{tab_text}')").first.click()
                pause(1000)
            except Exception:
                pass
        pause(1500)

        # ── 9. Uitleg ────────────────────────────────────────────────────────
        print("▶ Uitleg...")
        page.goto(BASE_URL + "/uitleg")
        pause(2500)

        # Klik uitlegblokken open
        for i in range(1, 5):
            try:
                page.locator(f"#s{i} .section-header").click()
                pause(800)
                smooth_scroll(page, 120, steps=4)
            except Exception:
                pass
        pause(1500)

        # ── 10. Terug naar dashboard ─────────────────────────────────────────
        print("▶ Terug naar dashboard...")
        page.goto(BASE_URL + "/dashboard")
        pause(3000)

        # Eindigend shot: hover over feed-tegel
        try:
            page.locator(".tile-feed").first.hover()
            pause(1500)
        except Exception:
            pass

        pause(2000)
        print("✓ Opname klaar — browser sluit...")
        ctx.close()
        browser.close()

    # ── Video omzetten naar mp4 ──────────────────────────────────────────────
    webm_files = list(VIDEO_DIR.glob("*.webm"))
    if not webm_files:
        print("⚠ Geen video gevonden in", VIDEO_DIR)
        return

    src = webm_files[0]
    dst = OUT_DIR / "powned_walkthrough.mp4"
    print(f"\n▶ Converteren: {src.name} → powned_walkthrough.mp4")

    # Zoek ffmpeg in alle standaard paden
    ffmpeg_bin = None
    for candidate in ["ffmpeg",
                       "/opt/homebrew/bin/ffmpeg",
                       "/usr/local/bin/ffmpeg",
                       "/usr/bin/ffmpeg",
                       str(Path.home() / ".local/bin/ffmpeg")]:
        result = subprocess.run(["which", candidate] if candidate == "ffmpeg"
                                else ["test", "-f", candidate],
                                capture_output=True)
        if result.returncode == 0:
            ffmpeg_bin = candidate
            break
        # Voor absolute paden: check of het bestand bestaat
        if candidate != "ffmpeg" and Path(candidate).exists():
            ffmpeg_bin = candidate
            break

    if ffmpeg_bin:
        ffmpeg = subprocess.run(
            [ffmpeg_bin, "-y", "-i", str(src),
             "-vf", "scale=1440:900",
             "-c:v", "libx264", "-preset", "medium", "-crf", "18",
             "-pix_fmt", "yuv420p",
             str(dst)],
            capture_output=True, text=True
        )
        if ffmpeg.returncode == 0:
            size_mb = dst.stat().st_size / 1024 / 1024
            print(f"\n✓ MP4 klaar: {dst}")
            print(f"  Grootte: {size_mb:.1f} MB")
            subprocess.run(["open", "-R", str(dst)])
        else:
            print(f"⚠ ffmpeg-conversie mislukt. Reden:\n{ffmpeg.stderr[-300:]}")
            _open_webm(src, OUT_DIR)
    else:
        _open_webm(src, OUT_DIR)

def _open_webm(src, out_dir):
    print(f"\n✓ Opname klaar als WebM (direct afspeelbaar in Chrome/VLC):")
    print(f"  {src}")
    print(f"\n  Converteren naar MP4 zonder ffmpeg:")
    print(f"  1. Open https://cloudconvert.com/webm-to-mp4")
    print(f"  2. Upload het .webm bestand uit de Finder")
    print(f"\n  Of installeer ffmpeg via: ! brew install ffmpeg")
    subprocess.run(["open", str(out_dir)])

if __name__ == "__main__":
    # Check of server draait
    try:
        import urllib.request
        urllib.request.urlopen(BASE_URL + "/login", timeout=3)
    except Exception:
        print(f"⚠ Server niet bereikbaar op {BASE_URL}")
        print("  Start eerst: npm start")
        sys.exit(1)

    print("🎬 PowNed Redactie — Product Walkthrough Recorder")
    print(f"   Server: {BASE_URL}")
    print(f"   Output: {OUT_DIR}")
    print("   Druk op Ctrl+C om te stoppen\n")
    run()

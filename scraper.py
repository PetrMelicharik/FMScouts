"""
FMScouts Scraper — produkční verze
Spouštěno automaticky přes GitHub Actions 2x týdně.
Data se ukládají do data/players.json.
"""

import requests
import openpyxl
import json
import time
import random
import os
from datetime import datetime
from pathlib import Path

# ── Konfigurace ────────────────────────────────────────────────────────────────

EXCEL_FILE   = "players.xlsx"
OUTPUT_FILE  = "data/players.json"
DELAY_MIN    = 4      # minimum sekund mezi requesty
DELAY_MAX    = 9      # maximum sekund mezi requesty
BURST_EVERY  = 12     # po kolika requestech udělat delší pauzu
BURST_PAUSE  = (25, 45)  # délka delší pauzy (sekundy)
MAX_RETRIES  = 3
TIMEOUT      = 12

# Realistické User-Agents — aktuální verze Chrome/Firefox
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# Accept-Language varianty (simuluje různé lokace)
ACCEPT_LANGS = [
    "cs-CZ,cs;q=0.9,en;q=0.8",
    "en-US,en;q=0.9",
    "sk-SK,sk;q=0.9,cs;q=0.8,en;q=0.7",
    "pl-PL,pl;q=0.9,en;q=0.8",
]

# ── Session & Headers ──────────────────────────────────────────────────────────

_request_count = 0

def make_session():
    s = requests.Session()
    s.headers.update({
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Connection": "keep-alive",
    })
    return s

def rotate_headers(session):
    """Rotuje User-Agent a Accept-Language při každém requestu."""
    session.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": random.choice(ACCEPT_LANGS),
        "Referer": random.choice([
            "https://www.sofascore.com/",
            "https://www.sofascore.com/cs/",
            "https://www.sofascore.com/cs/hrace",
        ]),
    })

def smart_delay():
    """Náhodná pauza + delší pauza každých BURST_EVERY requestů."""
    global _request_count
    _request_count += 1
    delay = random.uniform(DELAY_MIN, DELAY_MAX)
    # Přidej trochu náhodnosti — někdy kratší, někdy delší
    if random.random() < 0.15:
        delay *= random.uniform(1.5, 2.5)
    time.sleep(delay)
    if _request_count % BURST_EVERY == 0:
        pause = random.uniform(*BURST_PAUSE)
        print(f"  ☕ Pauza {pause:.0f}s (simulace přirozené aktivity)...")
        time.sleep(pause)

def fetch(url, session, retries=0):
    rotate_headers(session)
    smart_delay()
    try:
        r = session.get(url, timeout=TIMEOUT)
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", 90))
            print(f"  ⚠️  Rate limit! Čekám {wait}s...")
            time.sleep(wait + random.uniform(5, 15))
            return fetch(url, session, retries)
        if r.status_code in (403, 401, 451):
            print(f"  🚫 Blokováno ({r.status_code}): {url}")
            return None
        r.raise_for_status()
        return r.json()
    except requests.exceptions.Timeout:
        if retries < MAX_RETRIES:
            time.sleep((retries + 1) * 8)
            return fetch(url, session, retries + 1)
        return None
    except requests.exceptions.RequestException as e:
        if retries < MAX_RETRIES:
            time.sleep((retries + 1) * 6)
            return fetch(url, session, retries + 1)
        print(f"  ✗ {e}")
        return None

# ── Excel → hráči ─────────────────────────────────────────────────────────────

def load_players(path):
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]
    col = {name: i for i, name in enumerate(header)}
    players = []
    for row in rows[1:]:
        if not row[col["id"]]:
            continue
        players.append({
            "id": row[col["id"]],
            "firstName": row[col["Jméno"]] or "",
            "lastName": row[col["Příjmení"]] or "",
            "name": f"{row[col['Jméno']] or ''} {row[col['Příjmení']] or ''}".strip(),
            "pos": row[col["Pozice"]] or "",
            "pos2": row[col["2. pozice"]] or "",
            "transfermarkt": row[col["Transfermarkt"]] or "",
            "sofascore": row[col["Sofascore"]] or "",
            "profileUrl": row[col["Profile_link"]] or "",
            "ratingsUrl": row[col["Ratings_link"]] or "",
            "statsUrl": row[col["Stats_link"]] or "",
        })
    wb.close()
    print(f"✓ Načteno {len(players)} hráčů z Excelu")
    return players

# ── Scraping jednoho hráče ─────────────────────────────────────────────────────

def scrape_player(p, session):
    result = {
        **p,
        "data": {},
        "stats": {},
        "ratings": [],
        "avgRating": None,
        "maxRating": None,
        "minRating": None,
        "lastUpdated": datetime.utcnow().isoformat(),
    }

    # Profil
    if p["profileUrl"]:
        d = fetch(p["profileUrl"], session)
        if d and "player" in d:
            pl = d["player"]
            result["data"] = {
                "team": pl.get("team", {}).get("name", "") if pl.get("team") else "",
                "teamId": pl.get("team", {}).get("id") if pl.get("team") else None,
                "age": pl.get("age"),
                "dateOfBirthTimestamp": pl.get("dateOfBirthTimestamp"),
                "country": pl.get("country", {}).get("name", "") if pl.get("country") else "",
                "countryCode": pl.get("country", {}).get("alpha2", "") if pl.get("country") else "",
                "height": pl.get("height"),
                "preferredFoot": pl.get("preferredFoot", ""),
                "marketValue": pl.get("proposedMarketValueRaw", {}).get("value") if pl.get("proposedMarketValueRaw") else None,
                "shirtNumber": pl.get("shirtNumber"),
            }

    # Statistiky
    if p["statsUrl"]:
        d = fetch(p["statsUrl"], session)
        if d and "statistics" in d:
            s = d["statistics"]
            result["stats"] = {
                "goals": s.get("goals", 0),
                "goalAssist": s.get("goalAssist", 0),
                "minutesPlayed": s.get("minutesPlayed", 0),
                "appearances": s.get("appearances", 0),
                "rating": s.get("rating"),
                "totalShots": s.get("totalShots", 0),
                "shotsOnTarget": s.get("onTargetScoringAttempt", 0),
                "accuratePasses": s.get("accuratePasses", 0),
                "accuratePassesPercentage": s.get("accuratePassesPercentage"),
                "tackles": s.get("tackles", 0),
                "interceptions": s.get("interceptions", 0),
                "successfulDribbles": s.get("successfulDribbles", 0),
                "yellowCards": s.get("yellowCards", 0),
                "redCards": s.get("redCards", 0),
                "cleanSheets": s.get("cleanSheet", 0),
                "saves": s.get("saves", 0),
            }

    # Ratingy
    if p["ratingsUrl"]:
        d = fetch(p["ratingsUrl"], session)
        if d and "ratings" in d:
            result["ratings"] = [
                {
                    "rating": r.get("rating"),
                    "startTimestamp": r.get("startTimestamp"),
                    "opponent": r.get("opponent", {}).get("name", "") if r.get("opponent") else "",
                }
                for r in d["ratings"] if r.get("rating")
            ]
            if result["ratings"]:
                vals = [r["rating"] for r in result["ratings"]]
                result["avgRating"] = round(sum(vals) / len(vals), 3)
                result["maxRating"] = round(max(vals), 3)
                result["minRating"] = round(min(vals), 3)

    return result

# ── Uložení ────────────────────────────────────────────────────────────────────

def save(players, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "players": players,
            "meta": {
                "lastUpdated": datetime.utcnow().isoformat(),
                "count": len(players),
                "withRatings": sum(1 for p in players if p.get("avgRating")),
            }
        }, f, ensure_ascii=False, indent=2)

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print(f"=== FMScouts Scraper {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} ===\n")

    if not Path(EXCEL_FILE).exists():
        print(f"❌ {EXCEL_FILE} nenalezen!")
        return

    players = load_players(EXCEL_FILE)

    # Načti existující data pro resume
    existing = {}
    if Path(OUTPUT_FILE).exists():
        try:
            with open(OUTPUT_FILE, encoding="utf-8") as f:
                saved = json.load(f)
            existing = {p["id"]: p for p in saved.get("players", [])}
            print(f"↺  Resume: {len(existing)} existujících záznamů\n")
        except Exception:
            pass

    session = make_session()
    results = []
    total = len(players)
    ok = 0
    skipped = 0

    for i, player in enumerate(players):
        pid = player["id"]
        name = player["name"]

        # Přeskoč pokud má dnešní data
        if pid in existing:
            ex = existing[pid]
            ts = ex.get("lastUpdated", "")
            if ts and ts[:10] == datetime.utcnow().strftime("%Y-%m-%d"):
                results.append(ex)
                skipped += 1
                continue

        print(f"[{i+1}/{total}] {name}...", end=" ", flush=True)
        scraped = scrape_player(player, session)
        results.append(scraped)

        parts = []
        if scraped.get("avgRating"):
            parts.append(f"★ {scraped['avgRating']:.2f}")
        if scraped.get("data", {}).get("team"):
            parts.append(scraped["data"]["team"])
        print("✓" + (f"  {', '.join(parts)}" if parts else ""))
        ok += 1

        # Průběžné ukládání každých 15 hráčů
        if ok % 15 == 0:
            save(results, OUTPUT_FILE)
            print(f"  💾 Průběžně uloženo ({len(results)} celkem)\n")

    save(results, OUTPUT_FILE)
    print(f"\n{'='*40}")
    print(f"✅ Hotovo! Zpracováno: {ok}, přeskočeno: {skipped}, celkem: {len(results)}")
    with_ratings = sum(1 for p in results if p.get("avgRating"))
    print(f"   S ratingy: {with_ratings}/{len(results)}")

if __name__ == "__main__":
    main()

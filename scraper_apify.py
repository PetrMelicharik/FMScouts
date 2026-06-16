"""
FMScouts Scraper — Apify Proxy verze
Používá Apify residential proxy přímo v requestech.
"""

import requests
import openpyxl
import json
import time
import random
import os
from datetime import datetime
from pathlib import Path

APIFY_TOKEN = os.environ.get("APIFY_TOKEN")
EXCEL_FILE = "players.xlsx"
OUTPUT_FILE = "data/players.json"
DELAY_MIN = 3
DELAY_MAX = 8
BURST_EVERY = 15
BURST_PAUSE = (20, 40)
MAX_RETRIES = 3
TIMEOUT = 15

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

_req_count = 0

def make_session():
    s = requests.Session()
    # Apify residential proxy
    if APIFY_TOKEN:
        password = APIFY_TOKEN
        proxy_url = f"http://groups-RESIDENTIAL:{password}@proxy.apify.com:8000"
        s.proxies = {"http": proxy_url, "https": proxy_url}
        print("✓ Apify residential proxy aktivní")
    else:
        print("⚠ Bez proxy (lokální spuštění)")
    return s

def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Referer": "https://www.sofascore.com/",
        "Origin": "https://www.sofascore.com",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": random.choice(["cs-CZ,cs;q=0.9,en;q=0.8", "en-US,en;q=0.9", "sk-SK,sk;q=0.9"]),
        "Accept-Encoding": "gzip, deflate, br",
        "Cache-Control": "no-cache",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }

def smart_delay():
    global _req_count
    _req_count += 1
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
    if _req_count % BURST_EVERY == 0:
        pause = random.uniform(*BURST_PAUSE)
        print(f"  ☕ Pauza {pause:.0f}s...")
        time.sleep(pause)

def fetch(url, session, retries=0):
    smart_delay()
    try:
        r = session.get(url, headers=get_headers(), timeout=TIMEOUT)
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", 60))
            print(f"  ⚠ Rate limit, čekám {wait}s...")
            time.sleep(wait)
            return fetch(url, session, retries)
        if r.status_code in (403, 401):
            print(f"  🚫 Blokováno ({r.status_code})")
            return None
        r.raise_for_status()
        return r.json()
    except Exception as e:
        if retries < MAX_RETRIES:
            time.sleep((retries + 1) * 5)
            return fetch(url, session, retries + 1)
        print(f"  ✗ {e}")
        return None

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

def scrape_player(p, session):
    result = {
        **p,
        "data": {}, "stats": {}, "ratings": [],
        "avgRating": None, "maxRating": None, "minRating": None,
        "lastUpdated": datetime.utcnow().isoformat(),
    }

    if p["profileUrl"]:
        d = fetch(p["profileUrl"], session)
        if d and "player" in d:
            pl = d["player"]
            result["data"] = {
                "team": pl.get("team", {}).get("name", "") if pl.get("team") else "",
                "age": pl.get("age"),
                "country": pl.get("country", {}).get("name", "") if pl.get("country") else "",
                "height": pl.get("height"),
                "preferredFoot": pl.get("preferredFoot", ""),
                "marketValue": pl.get("proposedMarketValueRaw", {}).get("value") if pl.get("proposedMarketValueRaw") else None,
            }

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
                "accuratePasses": s.get("accuratePasses", 0),
                "tackles": s.get("tackles", 0),
                "successfulDribbles": s.get("successfulDribbles", 0),
                "yellowCards": s.get("yellowCards", 0),
                "redCards": s.get("redCards", 0),
                "saves": s.get("saves", 0),
                "cleanSheets": s.get("cleanSheet", 0),
            }

    if p["ratingsUrl"]:
        d = fetch(p["ratingsUrl"], session)
        if d and "ratings" in d:
            rats = [r for r in d["ratings"] if r.get("rating")]
            result["ratings"] = [
                {"rating": r["rating"], "startTimestamp": r.get("startTimestamp"),
                 "opponent": r.get("opponent", {}).get("name", "") if r.get("opponent") else ""}
                for r in rats
            ]
            if result["ratings"]:
                vals = [r["rating"] for r in result["ratings"]]
                result["avgRating"] = round(sum(vals) / len(vals), 3)
                result["maxRating"] = round(max(vals), 3)
                result["minRating"] = round(min(vals), 3)

    return result

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

def main():
    print(f"=== FMScouts Scraper {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} ===\n")

    players = load_players(EXCEL_FILE)
    session = make_session()

    # Test první hráč
    print("\n--- Test první hráč ---")
    test = scrape_player(players[0], session)
    if test.get("data") or test.get("stats") or test.get("ratings"):
        print(f"✓ Test OK! Rating: {test.get('avgRating')}, Tým: {test.get('data', {}).get('team')}")
    else:
        print("✗ Test selhal — proxy pravděpodobně nefunguje pro Sofascore")
        print("Ukládám prázdná data...")
        save(players, OUTPUT_FILE)
        return

    # Načti existující data
    existing = {}
    if Path(OUTPUT_FILE).exists():
        try:
            with open(OUTPUT_FILE, encoding="utf-8") as f:
                saved = json.load(f)
            existing = {p["id"]: p for p in saved.get("players", [])}
        except Exception:
            pass

    results = [test]
    total = len(players)

    for i, player in enumerate(players[1:], 2):
        pid = player["id"]
        ts = existing.get(pid, {}).get("lastUpdated", "")
        if ts and ts[:10] == datetime.utcnow().strftime("%Y-%m-%d"):
            results.append(existing[pid])
            continue

        print(f"[{i}/{total}] {player['name']}...", end=" ", flush=True)
        scraped = scrape_player(player, session)
        results.append(scraped)
        parts = []
        if scraped.get("avgRating"): parts.append(f"★ {scraped['avgRating']:.2f}")
        if scraped.get("data", {}).get("team"): parts.append(scraped["data"]["team"])
        print("✓" + (f"  {', '.join(parts)}" if parts else ""))

        if i % 15 == 0:
            save(results, OUTPUT_FILE)
            print(f"  💾 Uloženo {len(results)}/{total}\n")

    save(results, OUTPUT_FILE)
    with_ratings = sum(1 for p in results if p.get("avgRating"))
    print(f"\n✅ Hotovo! {len(results)} hráčů, {with_ratings} s ratingem.")

if __name__ == "__main__":
    main()

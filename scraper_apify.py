"""
FMScouts Scraper — Webshare Proxy verze
"""

import requests
import openpyxl
import json
import time
import random
import os
from datetime import datetime
from pathlib import Path

WEBSHARE_USER = os.environ.get("WEBSHARE_USER")
WEBSHARE_PASS = os.environ.get("WEBSHARE_PASS")
EXCEL_FILE = "players.xlsx"
OUTPUT_FILE = "data/players.json"
DELAY_MIN = 4
DELAY_MAX = 9
BURST_EVERY = 15
BURST_PAUSE = (25, 45)
MAX_RETRIES = 3
TIMEOUT = 15

# 10 Webshare proxy IP:PORT
PROXIES = [
    ("38.154.203.95", 5863),
    ("198.105.121.200", 6462),
    ("64.137.96.74", 6641),
    ("209.127.138.10", 5784),
    ("38.154.185.97", 6370),
    ("84.247.60.125", 6095),
    ("142.111.67.146", 5611),
    ("191.96.254.138", 6185),
    ("23.229.19.94", 8689),
    ("2.57.20.2", 6983),
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

_req_count = 0

def get_proxy():
    ip, port = random.choice(PROXIES)
    proxy_url = f"http://{WEBSHARE_USER}:{WEBSHARE_PASS}@{ip}:{port}"
    return {"http": proxy_url, "https": proxy_url}

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

def fetch(url, retries=0):
    smart_delay()
    try:
        r = requests.get(url, headers=get_headers(), proxies=get_proxy(), timeout=TIMEOUT)
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", 60))
            print(f"  ⚠ Rate limit, čekám {wait}s...")
            time.sleep(wait)
            return fetch(url, retries)
        if r.status_code in (403, 401):
            print(f"  🚫 Blokováno ({r.status_code})")
            return None
        r.raise_for_status()
        return r.json()
    except Exception as e:
        if retries < MAX_RETRIES:
            time.sleep((retries + 1) * 5)
            return fetch(url, retries + 1)
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

def scrape_player(p):
    result = {
        **p,
        "data": {}, "stats": {}, "ratings": [],
        "avgRating": None, "maxRating": None, "minRating": None,
        "lastUpdated": datetime.utcnow().isoformat(),
    }

    if p["profileUrl"]:
        d = fetch(p["profileUrl"])
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
        d = fetch(p["statsUrl"])
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
        d = fetch(p["ratingsUrl"])
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

    if not WEBSHARE_USER or not WEBSHARE_PASS:
        print("❌ WEBSHARE_USER nebo WEBSHARE_PASS není nastaven!")
        return

    players = load_players(EXCEL_FILE)
    print(f"✓ Webshare proxy aktivní ({len(PROXIES)} IP adres, rotace)\n")

    # Test prvního hráče
    print("--- Test ---")
    test = scrape_player(players[0])
    if test.get("data") or test.get("stats") or test.get("ratings"):
        print(f"✓ Proxy funguje! Rating: {test.get('avgRating')}, Tým: {test.get('data', {}).get('team')}\n")
    else:
        print("✗ Test selhal — Sofascore blokuje i Webshare proxy")
        save(players, OUTPUT_FILE)
        return

    # Načti existující data pro resume
    existing = {}
    if Path(OUTPUT_FILE).exists():
        try:
            with open(OUTPUT_FILE, encoding="utf-8") as f:
                saved = json.load(f)
            existing = {p["id"]: p for p in saved.get("players", [])}
            print(f"↺ Resume: {len(existing)} existujících záznamů\n")
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
        scraped = scrape_player(player)
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

"""
FMScouts Scraper — Apify verze
Spouštěno přes GitHub Actions, scraping běží na Apify serverech.
"""

import requests
import openpyxl
import json
import time
import os
from datetime import datetime
from pathlib import Path

APIFY_TOKEN = os.environ.get("APIFY_TOKEN")
ACTOR_ID = "VzKtdb1t0Qnc07X8V"  # sofascore-scraper-pro
EXCEL_FILE = "players.xlsx"
OUTPUT_FILE = "data/players.json"

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

def apify_scrape(urls):
    headers = {
        "Authorization": f"Bearer {APIFY_TOKEN}",
        "Content-Type": "application/json",
    }
    print(f"  → Spouštím Apify actor pro {len(urls)} URL...")
    run_resp = requests.post(
        f"https://api.apify.com/v2/acts/{ACTOR_ID}/runs",
        headers=headers,
        json={"startUrls": [{"url": u} for u in urls]},
        timeout=30,
    )
    run_resp.raise_for_status()
    run_id = run_resp.json()["data"]["id"]
    dataset_id = run_resp.json()["data"]["defaultDatasetId"]
    print(f"  → Run ID: {run_id}")

    for attempt in range(60):
        time.sleep(15)
        status_resp = requests.get(
            f"https://api.apify.com/v2/actor-runs/{run_id}",
            headers=headers, timeout=15,
        )
        status = status_resp.json()["data"]["status"]
        print(f"  → Status: {status} (pokus {attempt+1}/60)")
        if status == "SUCCEEDED":
            break
        if status in ("FAILED", "ABORTED", "TIMED-OUT"):
            print(f"  ✗ Actor selhal: {status}")
            return []

    results_resp = requests.get(
        f"https://api.apify.com/v2/datasets/{dataset_id}/items?limit=10000",
        headers=headers, timeout=30,
    )
    items = results_resp.json()
    print(f"  ✓ Získáno {len(items)} výsledků")
    return items

def parse_results(items, players):
    url_map = {}
    for item in items:
        url = item.get("url") or item.get("inputUrl") or ""
        url_map[url] = item

    results = []
    for p in players:
        result = {
            **p,
            "data": {}, "stats": {}, "ratings": [],
            "avgRating": None, "maxRating": None, "minRating": None,
            "lastUpdated": datetime.utcnow().isoformat(),
        }

        profile_data = url_map.get(p["profileUrl"], {})
        if profile_data.get("player"):
            pl = profile_data["player"]
            result["data"] = {
                "team": pl.get("team", {}).get("name", "") if pl.get("team") else "",
                "age": pl.get("age"),
                "country": pl.get("country", {}).get("name", "") if pl.get("country") else "",
                "height": pl.get("height"),
                "preferredFoot": pl.get("preferredFoot", ""),
                "marketValue": pl.get("proposedMarketValueRaw", {}).get("value") if pl.get("proposedMarketValueRaw") else None,
            }

        stats_data = url_map.get(p["statsUrl"], {})
        if stats_data.get("statistics"):
            s = stats_data["statistics"]
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

        ratings_data = url_map.get(p["ratingsUrl"], {})
        if ratings_data.get("ratings"):
            rats = [r for r in ratings_data["ratings"] if r.get("rating")]
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

        results.append(result)
    return results

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
    print(f"=== FMScouts Apify Scraper {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} ===\n")
    if not APIFY_TOKEN:
        print("❌ APIFY_TOKEN není nastaven!")
        return

    players = load_players(EXCEL_FILE)

    all_urls = set()
    for p in players:
        if p["profileUrl"]: all_urls.add(p["profileUrl"])
        if p["statsUrl"]: all_urls.add(p["statsUrl"])
        if p["ratingsUrl"]: all_urls.add(p["ratingsUrl"])

    print(f"Celkem {len(all_urls)} URL pro {len(players)} hráčů\n")
    all_urls = list(all_urls)
    all_items = []

    for i in range(0, len(all_urls), 300):
        batch = all_urls[i:i+300]
        print(f"Batch {i//300 + 1} ({len(batch)} URL)...")
        items = apify_scrape(batch)
        all_items.extend(items)
        if i + 300 < len(all_urls):
            print("Čekám 30s...")
            time.sleep(30)

    print(f"\nZpracovávám {len(all_items)} výsledků...")
    results = parse_results(all_items, players)
    save(results, OUTPUT_FILE)
    with_ratings = sum(1 for p in results if p.get("avgRating"))
    print(f"\n✅ Hotovo! {len(results)} hráčů, {with_ratings} s ratingem.")

if __name__ == "__main__":
    main()

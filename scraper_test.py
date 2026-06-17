"""
FMScouts Scraper — TESTOVACÍ verze
Stáhne jen Česko 1. liga + Norsko 1. liga pro otestování.
~60-80 requestů celkem, vejde se do free tier.
"""

import requests
import json
import time
import os
from datetime import datetime
from pathlib import Path

API_KEY  = os.environ.get("APIFOOTBALL_KEY")
BASE_URL = "https://v3.football.api-sports.io"
OUTPUT   = "data/players.json"
SEASON   = 2025

# Jen 2 ligy pro test
LEAGUES = [
    {"id": 345, "name": "Česko (1. liga)",   "country": "Czech",  "tier": 1},
    {"id": 103, "name": "Norsko (1. liga)",  "country": "Norway", "tier": 1},
]

def get(endpoint, params={}):
    headers = {"x-apisports-key": API_KEY}
    url = f"{BASE_URL}/{endpoint}"
    time.sleep(0.4)
    r = requests.get(url, headers=headers, params=params, timeout=15)
    remaining = r.headers.get("x-ratelimit-requests-remaining", "?")
    print(f"    [API] Zbývá requestů dnes: {remaining}")
    if r.status_code == 429:
        print("  ⚠ Rate limit, čekám 60s...")
        time.sleep(60)
        return get(endpoint, params)
    r.raise_for_status()
    return r.json().get("response", [])

def scrape_league(league):
    lid = league["id"]
    print(f"\n{'='*50}")
    print(f"  {league['name']} (ID: {lid})")
    print(f"{'='*50}")

    teams = get("teams", {"league": lid, "season": SEASON})
    if not teams:
        print(f"  ✗ Žádné týmy")
        return []
    print(f"  Týmy: {len(teams)}")

    all_players = []
    for ti, team_data in enumerate(teams):
        team = team_data.get("team", {})
        team_id   = team.get("id")
        team_name = team.get("name", "")
        print(f"  [{ti+1}/{len(teams)}] {team_name}...", end=" ", flush=True)

        page = 1
        team_players = []
        while True:
            players = get("players", {"team": team_id, "league": lid, "season": SEASON, "page": page})
            if not players:
                break
            for p_data in players:
                p     = p_data.get("player", {})
                stats = p_data.get("statistics", [{}])[0]
                games  = stats.get("games", {})
                goals  = stats.get("goals", {})
                passes = stats.get("passes", {})
                shots  = stats.get("shots", {})
                duels  = stats.get("duels", {})
                drib   = stats.get("dribbles", {})
                fouls  = stats.get("fouls", {})
                cards  = stats.get("cards", {})
                tackles= stats.get("tackles", {})

                team_players.append({
                    "id":           p.get("id"),
                    "name":         p.get("name", ""),
                    "firstname":    p.get("firstname", ""),
                    "lastname":     p.get("lastname", ""),
                    "age":          p.get("age"),
                    "nationality":  p.get("nationality", ""),
                    "height":       p.get("height", ""),
                    "weight":       p.get("weight", ""),
                    "photo":        p.get("photo", ""),
                    "leagueId":     lid,
                    "leagueName":   league["name"],
                    "leagueTier":   league["tier"],
                    "country":      league["country"],
                    "teamId":       team_id,
                    "teamName":     team_name,
                    "season":       SEASON,
                    "position":     games.get("position", ""),
                    "appearances":  games.get("appearences"),
                    "lineups":      games.get("lineups"),
                    "minutesPlayed":games.get("minutes"),
                    "rating":       games.get("rating"),
                    "goals":        goals.get("total"),
                    "assists":      goals.get("assists"),
                    "shots":        shots.get("total"),
                    "shotsOnTarget":shots.get("on"),
                    "passes":       passes.get("total"),
                    "keyPasses":    passes.get("key"),
                    "passAccuracy": passes.get("accuracy"),
                    "dribbles":     drib.get("attempts"),
                    "dribblesWon":  drib.get("success"),
                    "duels":        duels.get("total"),
                    "duelsWon":     duels.get("won"),
                    "tackles":      tackles.get("total"),
                    "blocks":       tackles.get("blocks"),
                    "interceptions":tackles.get("interceptions"),
                    "yellowCards":  cards.get("yellow"),
                    "redCards":     cards.get("red"),
                    "foulsCommitted":fouls.get("committed"),
                    "foulsSuffered": fouls.get("drawn"),
                    "lastUpdated":  datetime.utcnow().isoformat(),
                })
            if len(players) < 20:
                break
            page += 1

        print(f"✓ {len(team_players)} hráčů")
        all_players.extend(team_players)

    print(f"\n  Liga hotova: {len(all_players)} hráčů")
    return all_players

def save(players, leagues_done):
    Path(OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump({
            "players": players,
            "meta": {
                "lastUpdated":  datetime.utcnow().isoformat(),
                "season":       SEASON,
                "totalPlayers": len(players),
                "leagues":      leagues_done,
                "testMode":     True,
            }
        }, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Uloženo {len(players)} hráčů → {OUTPUT}")

def main():
    print(f"\n{'#'*50}")
    print(f"  FMScouts TEST Scraper")
    print(f"  {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Ligy: {len(LEAGUES)} | Sezóna: {SEASON}")
    print(f"{'#'*50}\n")

    if not API_KEY:
        print("❌ APIFOOTBALL_KEY není nastaven!")
        return

    all_players = []
    leagues_done = []

    for league in LEAGUES:
        players = scrape_league(league)
        all_players.extend(players)
        leagues_done.append({
            "id": league["id"], "name": league["name"],
            "country": league["country"], "tier": league["tier"],
            "players": len(players),
        })
        save(all_players, leagues_done)

    print(f"\n{'#'*50}")
    print(f"✅ HOTOVO! {len(all_players)} hráčů z {len(LEAGUES)} testovacích lig")
    print(f"{'#'*50}")

if __name__ == "__main__":
    main()

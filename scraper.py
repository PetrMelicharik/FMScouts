"""
FMScouts Scraper — API-Football verze
Stahuje všechny hráče a statistiky z vybraných lig.
Spouštěno automaticky přes GitHub Actions.
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

LEAGUES = [
    {"id": 316, "name": "Bosna (Premier League)",  "country": "Bosnia",      "tier": 1},
    {"id": 175, "name": "Bulharsko (1. liga)",      "country": "Bulgaria",    "tier": 1},
    {"id": 176, "name": "Bulharsko (2. liga)",      "country": "Bulgaria",    "tier": 2},
    {"id": 345, "name": "Česko (1. liga)",          "country": "Czech",       "tier": 1},
    {"id": 346, "name": "Česko (2. liga)",          "country": "Czech",       "tier": 2},
    {"id": 119, "name": "Dánsko (1. liga)",         "country": "Denmark",     "tier": 1},
    {"id": 120, "name": "Dánsko (2. liga)",         "country": "Denmark",     "tier": 2},
    {"id": 329, "name": "Estonsko (1. liga)",       "country": "Estonia",     "tier": 1},
    {"id": 244, "name": "Finsko (1. liga)",         "country": "Finland",     "tier": 1},
    {"id": 210, "name": "Chorvatsko (1. liga)",     "country": "Croatia",     "tier": 1},
    {"id": 211, "name": "Chorvatsko (2. liga)",     "country": "Croatia",     "tier": 2},
    {"id": 365, "name": "Kosovo (1. liga)",         "country": "Kosovo",      "tier": 1},
    {"id": 271, "name": "Lotyšsko (1. liga)",       "country": "Latvia",      "tier": 1},
    {"id": 103, "name": "Maďarsko (1. liga)",       "country": "Hungary",     "tier": 1},
    {"id": 103, "name": "Norsko (1. liga)",         "country": "Norway",      "tier": 1},
    {"id": 104, "name": "Norsko (2. liga)",         "country": "Norway",      "tier": 2},
    {"id": 106, "name": "Polsko (1. liga)",         "country": "Poland",      "tier": 1},
    {"id": 107, "name": "Polsko (2. liga)",         "country": "Poland",      "tier": 2},
    {"id": 218, "name": "Rakousko (1. liga)",       "country": "Austria",     "tier": 1},
    {"id": 219, "name": "Rakousko (2. liga)",       "country": "Austria",     "tier": 2},
    {"id": 283, "name": "Rumunsko (1. liga)",       "country": "Romania",     "tier": 1},
    {"id": 284, "name": "Rumunsko (2. liga)",       "country": "Romania",     "tier": 2},
    {"id": 332, "name": "Slovensko (1. liga)",      "country": "Slovakia",    "tier": 1},
    {"id": 373, "name": "Slovinsko (1. liga)",      "country": "Slovenia",    "tier": 1},
    {"id": 286, "name": "Srbsko (1. liga)",         "country": "Serbia",      "tier": 1},
    {"id": 287, "name": "Srbsko (2. liga)",         "country": "Serbia",      "tier": 2},
    {"id": 113, "name": "Švédsko (1. liga)",        "country": "Sweden",      "tier": 1},
    {"id": 114, "name": "Švédsko (2. liga)",        "country": "Sweden",      "tier": 2},
    {"id": 207, "name": "Švýcarsko (1. liga)",      "country": "Switzerland", "tier": 1},
    {"id": 208, "name": "Švýcarsko (2. liga)",      "country": "Switzerland", "tier": 2},
    {"id": 333, "name": "Ukrajina (1. liga)",       "country": "Ukraine",     "tier": 1},
    {"id": 334, "name": "Ukrajina (2. liga)",       "country": "Ukraine",     "tier": 2},
]

# Opravím Maďarsko a Norsko — sdílely ID 103
LEAGUES[13]["id"] = 271  # Maďarsko = 271
LEAGUES[14]["id"] = 103  # Norsko = 103

def get(endpoint, params={}):
    """Volání API-Football s rate limit ochranou."""
    headers = {"x-apisports-key": API_KEY}
    url = f"{BASE_URL}/{endpoint}"
    time.sleep(0.35)  # max ~3 req/s, API limit je 10/s
    r = requests.get(url, headers=headers, params=params, timeout=15)
    if r.status_code == 429:
        print("  ⚠ Rate limit, čekám 60s...")
        time.sleep(60)
        return get(endpoint, params)
    r.raise_for_status()
    data = r.json()
    remaining = r.headers.get("x-ratelimit-requests-remaining", "?")
    if str(remaining) != "?" and int(remaining) < 100:
        print(f"  ⚠ Zbývá pouze {remaining} requestů dnes!")
    return data.get("response", [])

def get_teams(league_id):
    """Vrátí seznam týmů v lize."""
    return get("teams", {"league": league_id, "season": SEASON})

def get_players(team_id, league_id, page=1):
    """Vrátí hráče týmu s statistikami."""
    return get("players", {
        "team": team_id,
        "league": league_id,
        "season": SEASON,
        "page": page
    })

def scrape_league(league):
    """Stáhne všechny hráče z jedné ligy."""
    lid = league["id"]
    lname = league["name"]
    print(f"\n{'='*50}")
    print(f"  {lname} (ID: {lid})")
    print(f"{'='*50}")

    teams = get_teams(lid)
    if not teams:
        print(f"  ✗ Žádné týmy nenalezeny")
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
            players = get_players(team_id, lid, page)
            if not players:
                break
            for p_data in players:
                p    = p_data.get("player", {})
                stats = p_data.get("statistics", [{}])[0]
                games = stats.get("games", {})
                goals = stats.get("goals", {})
                passes= stats.get("passes", {})
                shots = stats.get("shots", {})
                duels = stats.get("duels", {})
                drib  = stats.get("dribbles", {})
                fouls = stats.get("fouls", {})
                cards = stats.get("cards", {})
                penalty=stats.get("penalty", {})
                tackles=stats.get("tackles", {})

                player = {
                    # Identifikace
                    "id":          p.get("id"),
                    "name":        p.get("name", ""),
                    "firstname":   p.get("firstname", ""),
                    "lastname":    p.get("lastname", ""),
                    "age":         p.get("age"),
                    "nationality": p.get("nationality", ""),
                    "height":      p.get("height", ""),
                    "weight":      p.get("weight", ""),
                    "photo":       p.get("photo", ""),

                    # Liga & tým
                    "leagueId":    lid,
                    "leagueName":  lname,
                    "leagueTier":  league["tier"],
                    "country":     league["country"],
                    "teamId":      team_id,
                    "teamName":    team_name,
                    "season":      SEASON,

                    # Pozice
                    "position":    games.get("position", ""),

                    # Zápasy
                    "appearances":    games.get("appearences"),
                    "lineups":        games.get("lineups"),
                    "minutesPlayed":  games.get("minutes"),
                    "rating":         games.get("rating"),

                    # Útočné
                    "goals":          goals.get("total"),
                    "assists":        goals.get("assists"),
                    "shots":          shots.get("total"),
                    "shotsOnTarget":  shots.get("on"),

                    # Přihrávky
                    "passes":         passes.get("total"),
                    "keyPasses":      passes.get("key"),
                    "passAccuracy":   passes.get("accuracy"),

                    # Driblinky & souboje
                    "dribbles":       drib.get("attempts"),
                    "dribblesWon":    drib.get("success"),
                    "duels":          duels.get("total"),
                    "duelsWon":       duels.get("won"),

                    # Obranné
                    "tackles":        tackles.get("total"),
                    "blocks":         tackles.get("blocks"),
                    "interceptions":  tackles.get("interceptions"),

                    # Disciplína
                    "yellowCards":    cards.get("yellow"),
                    "redCards":       cards.get("red"),
                    "foulsCommitted": fouls.get("committed"),
                    "foulsSuffered":  fouls.get("drawn"),

                    # Penalty
                    "penaltyScored":  penalty.get("scored"),
                    "penaltyMissed":  penalty.get("missed"),

                    # Meta
                    "lastUpdated": datetime.utcnow().isoformat(),
                }
                team_players.append(player)

            # Další stránka?
            if len(players) < 20:
                break
            page += 1

        print(f"✓ {len(team_players)} hráčů")
        all_players.extend(team_players)

    print(f"\n  Liga hotova: {len(all_players)} hráčů celkem")
    return all_players

def save(players, meta):
    Path(OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump({"players": players, "meta": meta}, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Uloženo {len(players)} hráčů → {OUTPUT}")

def main():
    print(f"\n{'#'*50}")
    print(f"  FMScouts Scraper — {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Lig: {len(LEAGUES)} | Sezóna: {SEASON}")
    print(f"{'#'*50}\n")

    if not API_KEY:
        print("❌ APIFOOTBALL_KEY není nastaven!")
        return

    all_players = []
    league_stats = []

    for league in LEAGUES:
        players = scrape_league(league)
        all_players.extend(players)
        league_stats.append({
            "id":      league["id"],
            "name":    league["name"],
            "country": league["country"],
            "tier":    league["tier"],
            "players": len(players),
        })
        # Průběžné ukládání po každé lize
        save(all_players, {
            "lastUpdated":  datetime.utcnow().isoformat(),
            "season":       SEASON,
            "totalPlayers": len(all_players),
            "leagues":      league_stats,
        })

    print(f"\n{'#'*50}")
    print(f"✅ HOTOVO! Celkem {len(all_players)} hráčů z {len(LEAGUES)} lig")
    print(f"{'#'*50}")

if __name__ == "__main__":
    main()

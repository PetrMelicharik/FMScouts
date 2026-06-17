"""
FMScouts Scraper — API-Football
Stahuje hráče a statistiky ze všech lig.
Každá liga má správně nastavenou aktuální sezónu.
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

# Systémy sezón:
# "spring_fall" = jaro-podzim (2026): Norsko, Švédsko, Finsko, Estonsko, Lotyšsko
# "fall_spring" = podzim-jaro (2025): zbytek (Česko, Slovensko, Polsko, Bosna atd.)

LEAGUES = [
    # Česko
    {"id": 345, "name": "Česko (1. liga)",        "country": "Czech",       "tier": 1, "season_type": "fall_spring"},
    # Dánsko — podzim-jaro (od 2024/25)
    {"id": 119, "name": "Dánsko (1. liga)",       "country": "Denmark",     "tier": 1, "season_type": "fall_spring"},
    {"id": 120, "name": "Dánsko (2. liga)",       "country": "Denmark",     "tier": 2, "season_type": "fall_spring"},
    # Estonsko — jaro-podzim
    # Finsko — jaro-podzim
    {"id": 244, "name": "Finsko (1. liga)",       "country": "Finland",     "tier": 1, "season_type": "spring_fall"},
    # Chorvatsko
    {"id": 210, "name": "Chorvatsko (1. liga)",   "country": "Croatia",     "tier": 1, "season_type": "fall_spring"},
    # Maďarsko
    {"id": 271, "name": "Maďarsko (1. liga)",     "country": "Hungary",     "tier": 1, "season_type": "fall_spring"},
    # Norsko — jaro-podzim
    {"id": 103, "name": "Norsko (1. liga)",       "country": "Norway",      "tier": 1, "season_type": "spring_fall"},
    # Polsko
    {"id": 106, "name": "Polsko (1. liga)",       "country": "Poland",      "tier": 1, "season_type": "fall_spring"},
    # Rakousko
    {"id": 218, "name": "Rakousko (1. liga)",     "country": "Austria",     "tier": 1, "season_type": "fall_spring"},
    # Rumunsko
    {"id": 283, "name": "Rumunsko (1. liga)",     "country": "Romania",     "tier": 1, "season_type": "fall_spring"},
    # Slovensko
    {"id": 332, "name": "Slovensko (1. liga)",    "country": "Slovakia",    "tier": 1, "season_type": "fall_spring"},
    # Slovinsko
    # Srbsko
    {"id": 286, "name": "Srbsko (1. liga)",       "country": "Serbia",      "tier": 1, "season_type": "fall_spring"},
    # Švédsko — jaro-podzim
    {"id": 113, "name": "Švédsko (1. liga)",      "country": "Sweden",      "tier": 1, "season_type": "spring_fall"},
    {"id": 114, "name": "Švédsko (2. liga)",      "country": "Sweden",      "tier": 2, "season_type": "spring_fall"},
    # Švýcarsko
    {"id": 207, "name": "Švýcarsko (1. liga)",    "country": "Switzerland", "tier": 1, "season_type": "fall_spring"},
    # Ukrajina
    {"id": 333, "name": "Ukrajina (1. liga)",     "country": "Ukraine",     "tier": 1, "season_type": "fall_spring"},
]

def current_season(season_type):
    """Vrátí aktuální sezónu podle typu ligy."""
    now = datetime.utcnow()
    year = now.year
    if season_type == "spring_fall":
        # Jaro-podzim: sezóna = aktuální rok (2026)
        return year
    else:
        # Podzim-jaro: sezóna začala loni (2025/26 → season = 2025)
        # Pokud jsme po červenci, sezóna začala letos, jinak loni
        if now.month >= 7:
            return year
        else:
            return year - 1

def get(endpoint, params={}):
    headers = {"x-apisports-key": API_KEY}
    url = f"{BASE_URL}/{endpoint}"
    time.sleep(0.35)
    r = requests.get(url, headers=headers, params=params, timeout=15)
    remaining = r.headers.get("x-ratelimit-requests-remaining", "?")
    if str(remaining) != "?" and int(remaining) < 200:
        print(f"    ⚠ Zbývá pouze {remaining} requestů dnes!")
    if r.status_code == 429:
        print("  ⚠ Rate limit, čekám 60s...")
        time.sleep(60)
        return get(endpoint, params)
    r.raise_for_status()
    return r.json().get("response", [])

def scrape_league(league):
    lid    = league["id"]
    season = current_season(league["season_type"])
    print(f"\n{'='*50}")
    print(f"  {league['name']} (ID:{lid} Sezóna:{season})")
    print(f"{'='*50}")

    teams = get("teams", {"league": lid, "season": season})
    if not teams:
        # Zkus předchozí sezónu jako fallback
        fallback = season - 1
        print(f"  ↺ Žádné týmy pro {season}, zkouším {fallback}...")
        teams = get("teams", {"league": lid, "season": fallback})
        if teams:
            season = fallback
        else:
            print(f"  ✗ Žádné týmy nenalezeny")
            return []

    print(f"  Týmy: {len(teams)}, Sezóna: {season}")
    all_players = []

    for ti, team_data in enumerate(teams):
        team      = team_data.get("team", {})
        team_id   = team.get("id")
        team_name = team.get("name", "")
        print(f"  [{ti+1}/{len(teams)}] {team_name}...", end=" ", flush=True)

        page = 1
        team_players = []
        while True:
            players = get("players", {
                "team": team_id, "league": lid,
                "season": season, "page": page
            })
            if not players:
                break
            for p_data in players:
                p      = p_data.get("player", {})
                stats  = p_data.get("statistics", [{}])[0]
                games  = stats.get("games", {})
                goals  = stats.get("goals", {})
                passes = stats.get("passes", {})
                shots  = stats.get("shots", {})
                duels  = stats.get("duels", {})
                drib   = stats.get("dribbles", {})
                fouls  = stats.get("fouls", {})
                cards  = stats.get("cards", {})
                tackles= stats.get("tackles", {})
                penalty= stats.get("penalty", {})

                team_players.append({
                    "id":             p.get("id"),
                    "name":           p.get("name", ""),
                    "firstname":      p.get("firstname", ""),
                    "lastname":       p.get("lastname", ""),
                    "age":            p.get("age"),
                    "nationality":    p.get("nationality", ""),
                    "height":         p.get("height", ""),
                    "weight":         p.get("weight", ""),
                    "photo":          p.get("photo", ""),
                    "leagueId":       lid,
                    "leagueName":     league["name"],
                    "leagueTier":     league["tier"],
                    "country":        league["country"],
                    "teamId":         team_id,
                    "teamName":       team_name,
                    "season":         season,
                    "position":       games.get("position", ""),
                    "appearances":    games.get("appearences"),
                    "lineups":        games.get("lineups"),
                    "minutesPlayed":  games.get("minutes"),
                    "rating":         games.get("rating"),
                    "goals":          goals.get("total"),
                    "assists":        goals.get("assists"),
                    "shots":          shots.get("total"),
                    "shotsOnTarget":  shots.get("on"),
                    "passes":         passes.get("total"),
                    "keyPasses":      passes.get("key"),
                    "passAccuracy":   passes.get("accuracy"),
                    "dribbles":       drib.get("attempts"),
                    "dribblesWon":    drib.get("success"),
                    "duels":          duels.get("total"),
                    "duelsWon":       duels.get("won"),
                    "tackles":        tackles.get("total"),
                    "blocks":         tackles.get("blocks"),
                    "interceptions":  tackles.get("interceptions"),
                    "yellowCards":    cards.get("yellow"),
                    "redCards":       cards.get("red"),
                    "foulsCommitted": fouls.get("committed"),
                    "foulsSuffered":  fouls.get("drawn"),
                    "penaltyScored":  penalty.get("scored"),
                    "penaltyMissed":  penalty.get("missed"),
                    "lastUpdated":    datetime.utcnow().isoformat(),
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
                "totalPlayers": len(players),
                "leagues":      leagues_done,
            }
        }, f, ensure_ascii=False, indent=2)

def main():
    now = datetime.utcnow()
    print(f"\n{'#'*50}")
    print(f"  FMScouts Scraper — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Lig: {len(LEAGUES)}")
    print(f"  Aktuální sezóny:")
    print(f"    Jaro-podzim (NO, SE, FI, DK...): {current_season('spring_fall')}")
    print(f"    Podzim-jaro (CZ, SK, PL...):     {current_season('fall_spring')}")
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
            "id":      league["id"],
            "name":    league["name"],
            "country": league["country"],
            "tier":    league["tier"],
            "season":  current_season(league["season_type"]),
            "players": len(players),
        })
        save(all_players, leagues_done)

    print(f"\n{'#'*50}")
    print(f"✅ HOTOVO! {len(all_players)} hráčů z {len(LEAGUES)} lig")
    print(f"{'#'*50}")

if __name__ == "__main__":
    main()

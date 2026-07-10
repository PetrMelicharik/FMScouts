"""
FMScouts Scraper — API-Football
Stahuje hráče a statistiky ze všech lig.
Aktuální sezóna se zjišťuje přímo z API-Football (spolehlivější než odhad podle data),
s fallbackem na starý odhad podle měsíce, pokud by API selhalo.
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

def estimate_season_by_date(season_type):
    """Starý odhad podle měsíce — používá se jen jako fallback, pokud selže dotaz na API."""
    now = datetime.utcnow()
    year = now.year
    if season_type == "spring_fall":
        return year
    else:
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

def get_current_season(league_id, season_type):
    """
    Zjistí aktuální sezónu přímo z API-Football (endpoint /leagues vrací u každé
    sezóny příznak "current": true) — spolehlivější než odhad podle data, který
    selhává na přelomu sezón (nová sezóna existuje jako záznam, ale ještě nemá
    žádné odehrané zápasy/statistiky).
    Pokud dotaz selže nebo API neoznačí žádnou sezónu jako aktuální, spadne
    zpět na starý odhad podle měsíce.
    """
    try:
        resp = get("leagues", {"id": league_id})
        if resp:
            seasons = resp[0].get("seasons", [])
            for s in seasons:
                if s.get("current"):
                    return s.get("year")
    except Exception as e:
        print(f"  ⚠ Nepodařilo se zjistit aktuální sezónu z API ({e}), používám odhad podle data.")
    return estimate_season_by_date(season_type)

def scrape_teams_players(lid, season, league):
    """Stáhne týmy a hráče pro danou ligu a konkrétní sezónu.
    Vrátí None, pokud liga v dané sezóně vůbec nemá žádné týmy."""
    teams = get("teams", {"league": lid, "season": season})
    if not teams:
        return None

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
                    "birthDate":      p.get("birth", {}).get("date", ""),
                    "nationality":    p.get("nationality", ""),
                    "height":         p.get("height", ""),
                    "weight":         p.get("weight", ""),
                    "photo":          p.get("photo", ""),
                    "injured":        p.get("injured", False),
                    "leagueId":       lid,
                    "leagueName":     league["name"],
                    "leagueTier":     league["tier"],
                    "country":        league["country"],
                    "teamId":         team_id,
                    "teamName":       team_name,
                    "season":         season,
                    "position":       games.get("position", ""),
                    "shirtNumber":    games.get("number"),
                    "captain":        games.get("captain", False),
                    "appearances":    games.get("appearences"),
                    "lineups":        games.get("lineups"),
                    "minutesPlayed":  games.get("minutes"),
                    "rating":         games.get("rating"),
                    "goals":          goals.get("total"),
                    "assists":        goals.get("assists"),
                    "goalsConceded":  goals.get("conceded"),
                    "saves":          goals.get("saves"),
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
                    "penaltySaved":   penalty.get("saved"),
                    "lastUpdated":    datetime.utcnow().isoformat(),
                })
            if len(players) < 20:
                break
            page += 1

        print(f"✓ {len(team_players)} hráčů")
        all_players.extend(team_players)

    return all_players

def scrape_league(league):
    lid = league["id"]
    season = get_current_season(lid, league["season_type"])
    print(f"\n{'='*50}")
    print(f"  {league['name']} (ID:{lid} Sezóna:{season})")
    print(f"{'='*50}")

    all_players = scrape_teams_players(lid, season, league)

    if all_players is None:
        # Žádné týmy vůbec pro tuto sezónu — zkus předchozí
        fallback = season - 1
        print(f"  ↺ Žádné týmy pro {season}, zkouším {fallback}...")
        all_players = scrape_teams_players(lid, fallback, league)
        if all_players is None:
            print(f"  ✗ Žádné týmy nenalezeny")
            return []
        season = fallback

    elif len(all_players) == 0:
        # Týmy existují, ale bez jediné statistiky — nová sezóna typicky ještě nezačala
        fallback = season - 1
        print(f"  ↺ 0 hráčů se statistikami pro sezónu {season} (pravděpodobně ještě nezačala), zkouším {fallback}...")
        fallback_players = scrape_teams_players(lid, fallback, league)
        if fallback_players:
            all_players = fallback_players
            season = fallback

    print(f"\n  Liga hotova: {len(all_players)} hráčů (sezóna {season})")
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
    print(f"  Sezóna se zjišťuje přímo z API-Football (s fallbackem na odhad podle data)")
    print(f"{'#'*50}\n")

    if not API_KEY:
        print("❌ APIFOOTBALL_KEY není nastaven!")
        return

    all_players = []
    leagues_done = []

    for league in LEAGUES:
        players = scrape_league(league)
        used_season = players[0]["season"] if players else get_current_season(league["id"], league["season_type"])
        all_players.extend(players)
        leagues_done.append({
            "id":      league["id"],
            "name":    league["name"],
            "country": league["country"],
            "tier":    league["tier"],
            "season":  used_season,
            "players": len(players),
        })
        save(all_players, leagues_done)

    print(f"\n{'#'*50}")
    print(f"✅ HOTOVO! {len(all_players)} hráčů z {len(LEAGUES)} lig")
    print(f"{'#'*50}")

if __name__ == "__main__":
    main()

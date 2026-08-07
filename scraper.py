"""
FMScouts Scraper — API-Football
Stahuje hráče a statistiky ze všech lig.
Každá liga má správně nastavenou aktuální sezónu.

Změny oproti předchozí verzi:
- před stahováním hráčů se ověří API-Football coverage.players pro danou
  ligu/sezónu (endpoint /leagues?id=X) — pokud je false, rovnou se jde na
  předchozí sezónu, ať se zbytečně netahají prázdné odpovědi
- log hlášky přesně říkají PROČ se použila jiná sezóna (coverage vypnuté /
  žádné týmy / 0 hráčů se statistikami) místo dohadu "asi ještě nezačala"
- do players.json meta se u každé ligy ukládá seasonUsed, seasonRequested,
  playerStatsUnavailable a fallbackReason, takže je to vidět i mimo log
- jedna liga, která spadne s chybou, už nezastaví zbytek běhu (try/except)
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


def get_player_coverage(league_id, season):
    """
    Zjistí u API-Football, jestli má daná liga+sezóna zapnuté coverage.players
    (endpoint /leagues?id=X vrací seznam sezón s coverage flagy).
    Vrací True / False / None (nepodařilo se zjistit — sezóna nenalezena
    v seznamu, nebo dotaz selhal).
    """
    try:
        resp = get("leagues", {"id": league_id})
    except Exception as e:
        print(f"    ⚠ Nepodařilo se ověřit coverage: {e}")
        return None
    if not resp:
        return None
    for s in resp[0].get("seasons", []):
        if s.get("year") == season:
            return s.get("coverage", {}).get("players")
    return None


def fetch_players_for_season(league, season):
    """
    Stáhne hráče pro všechny týmy dané ligy a sezóny.
    Vrací (players, teams_count):
      - players je None, pokud pro danou sezónu nejsou vůbec žádné týmy
      - players je [] (prázdný seznam), pokud týmy jsou, ale žádný hráč
        nemá k dispozici statistiky
    """
    lid = league["id"]
    teams = get("teams", {"league": lid, "season": season})
    if not teams:
        return None, 0

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

    return all_players, len(teams)


def scrape_league(league):
    """
    Stáhne hráče pro jednu ligu. Vrací (players, meta), kde meta obsahuje:
      seasonRequested        - sezóna, která by měla logicky platit teď
      seasonUsed              - sezóna, ze které reálně pocházejí data (None při úplném selhání)
      playerStatsUnavailable  - True, pokud API-Football nemá pro seasonRequested statistiky hráčů
      fallbackReason           - lidsky čitelný důvod přepnutí sezóny (nebo None)
    """
    lid             = league["id"]
    intended_season = current_season(league["season_type"])
    lname           = league["name"]
    print(f"\n{'='*50}")
    print(f"  {lname} (ID:{lid} Sezóna:{intended_season})")
    print(f"{'='*50}")

    meta = {
        "seasonRequested":       intended_season,
        "seasonUsed":            intended_season,
        "playerStatsUnavailable": False,
        "fallbackReason":        None,
    }

    season = intended_season

    # 1) Ověř předem, jestli API-Football vůbec má statistiky hráčů pro tuhle sezónu.
    coverage = get_player_coverage(lid, season)
    if coverage is False:
        print(f"  ⚠ API-Football: coverage.players=false pro sezónu {season} "
              f"(liga se může už hrát, ale poskytovatel zatím nezveřejňuje statistiky hráčů).")
        meta["playerStatsUnavailable"] = True
        meta["fallbackReason"] = f"coverage.players=false pro sezónu {intended_season}"
        season = season - 1
        print(f"  ↺ Zkouším rovnou sezónu {season} místo {intended_season}.")
    elif coverage is None:
        print(f"  ℹ Coverage se nepodařilo ověřit, zkouším sezónu {season} přímo.")

    # 2) Stáhni hráče pro (případně už přepnutou) sezónu.
    players, teams_count = fetch_players_for_season(league, season)

    # 3a) Vůbec žádné týmy pro tuhle sezónu.
    if players is None:
        fallback_season = intended_season - 1
        if fallback_season != season:
            print(f"  ↺ Žádné týmy pro sezónu {season}, zkouším {fallback_season}...")
            players, teams_count = fetch_players_for_season(league, fallback_season)
            season = fallback_season
            meta["fallbackReason"] = meta["fallbackReason"] or f"žádné týmy nenalezeny pro sezónu {intended_season}"
        if players is None:
            print(f"  ✗ Žádné týmy nenalezeny ani pro sezónu {season}")
            meta["seasonUsed"] = None
            return [], meta

    # 3b) Týmy jsou, ale nikdo nemá statistiky (0 hráčů) — a ještě jsme nepřešli na fallback.
    elif len(players) == 0 and teams_count > 0 and season == intended_season:
        fallback_season = intended_season - 1
        print(f"  ↺ 0 hráčů se statistikami pro sezónu {season} "
              f"(API-Football zatím nemá player-data pro tuto sezónu), zkouším {fallback_season}...")
        fb_players, fb_teams_count = fetch_players_for_season(league, fallback_season)
        if fb_players:
            players = fb_players
            season = fallback_season
            meta["playerStatsUnavailable"] = True
            meta["fallbackReason"] = f"0 hráčů se statistikami vráceno pro sezónu {intended_season}"
        else:
            print(f"  ✗ Ani sezóna {fallback_season} nemá hráče se statistikami")

    meta["seasonUsed"] = season
    print(f"\n  Liga hotova: {len(players)} hráčů (sezóna {season})")
    return players, meta


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
        try:
            players, meta = scrape_league(league)
        except Exception as e:
            print(f"  ✗ Chyba při scrapování ligy {league['name']}: {e}")
            leagues_done.append({
                "id":                     league["id"],
                "name":                   league["name"],
                "country":                league["country"],
                "tier":                   league["tier"],
                "season":                 None,
                "seasonRequested":        current_season(league["season_type"]),
                "players":                0,
                "playerStatsUnavailable": None,
                "fallbackReason":         None,
                "error":                  str(e),
            })
            save(all_players, leagues_done)
            continue

        all_players.extend(players)
        leagues_done.append({
            "id":                     league["id"],
            "name":                   league["name"],
            "country":                league["country"],
            "tier":                   league["tier"],
            "season":                 meta["seasonUsed"],
            "seasonRequested":        meta["seasonRequested"],
            "players":                len(players),
            "playerStatsUnavailable": meta["playerStatsUnavailable"],
            "fallbackReason":         meta["fallbackReason"],
        })
        save(all_players, leagues_done)

    print(f"\n{'#'*50}")
    print(f"✅ HOTOVO! {len(all_players)} hráčů z {len(LEAGUES)} lig")
    print(f"{'#'*50}")


if __name__ == "__main__":
    main()

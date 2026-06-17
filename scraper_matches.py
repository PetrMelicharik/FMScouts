"""
FMScouts — Scraper zápasů a per-zápasových statistik
Ukládá data do Supabase databáze.
Spouštět každé pondělí (po víkendu) nebo manuálně.
"""

import requests
import json
import time
import os
from datetime import datetime, timedelta
from pathlib import Path

API_KEY         = os.environ.get("APIFOOTBALL_KEY")
SUPABASE_URL    = os.environ.get("SUPABASE_URL")
SUPABASE_KEY    = os.environ.get("SUPABASE_SERVICE_KEY")
BASE_URL        = "https://v3.football.api-sports.io"
# Kolik dní zpět stahovat (0 = celá sezóna, 14 = posledních 14 dní)
DAYS_BACK       = int(os.environ.get("DAYS_BACK", "14"))

# Všechny ligy
ALL_LEAGUES = [
    {"id": 345, "name": "Česko (1. liga)",      "season_type": "fall_spring"},
    {"id": 119, "name": "Dánsko (1. liga)",      "season_type": "fall_spring"},
    {"id": 120, "name": "Dánsko (2. liga)",      "season_type": "fall_spring"},
    {"id": 244, "name": "Finsko (1. liga)",      "season_type": "spring_fall"},
    {"id": 210, "name": "Chorvatsko (1. liga)",  "season_type": "fall_spring"},
    {"id": 271, "name": "Maďarsko (1. liga)",    "season_type": "fall_spring"},
    {"id": 103, "name": "Norsko (1. liga)",      "season_type": "spring_fall"},
    {"id": 106, "name": "Polsko (1. liga)",      "season_type": "fall_spring"},
    {"id": 218, "name": "Rakousko (1. liga)",    "season_type": "fall_spring"},
    {"id": 283, "name": "Rumunsko (1. liga)",    "season_type": "fall_spring"},
    {"id": 332, "name": "Slovensko (1. liga)",   "season_type": "fall_spring"},
    {"id": 286, "name": "Srbsko (1. liga)",      "season_type": "fall_spring"},
    {"id": 113, "name": "Švédsko (1. liga)",     "season_type": "spring_fall"},
    {"id": 114, "name": "Švédsko (2. liga)",     "season_type": "spring_fall"},
    {"id": 207, "name": "Švýcarsko (1. liga)",   "season_type": "fall_spring"},
    {"id": 333, "name": "Ukrajina (1. liga)",    "season_type": "fall_spring"},
]

# Jen ligy jaro-podzim (aktivní sezóna 2026)
SPRING_FALL_LEAGUES = [l for l in ALL_LEAGUES if l["season_type"] == "spring_fall"]

# Vyber podle env proměnné LEAGUES_MODE
LEAGUES_MODE = os.environ.get("LEAGUES_MODE", "all")
LEAGUES = SPRING_FALL_LEAGUES if LEAGUES_MODE == "spring_fall" else ALL_LEAGUES

def current_season(season_type):
    now = datetime.utcnow()
    year = now.year
    if season_type == "spring_fall":
        return year
    return year if now.month >= 7 else year - 1

# ── API-Football ───────────────────────────────────────────────────────────────

def api_get(endpoint, params={}):
    headers = {"x-apisports-key": API_KEY}
    time.sleep(0.35)
    r = requests.get(f"{BASE_URL}/{endpoint}", headers=headers, params=params, timeout=15)
    if r.status_code == 429:
        print("  ⚠ Rate limit, čekám 60s...")
        time.sleep(60)
        return api_get(endpoint, params)
    r.raise_for_status()
    return r.json().get("response", [])

# ── Supabase ───────────────────────────────────────────────────────────────────

def sb_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates"
    }

def sb_upsert(table, rows):
    if not rows:
        return
    r = requests.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers={**sb_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
        json=rows,
        timeout=30
    )
    if r.status_code not in (200, 201):
        print(f"  ✗ Supabase error {r.status_code}: {r.text[:200]}")
    return r

def sb_get_match_ids():
    """Vrátí set ID zápasů které už máme v DB."""
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/matches?select=id&limit=10000",
        headers=sb_headers(),
        timeout=15
    )
    if r.status_code == 200:
        return {row["id"] for row in r.json()}
    return set()

# ── Stažení zápasů ─────────────────────────────────────────────────────────────

def fetch_fixtures(league_id, season, full_season=False):
    """Stáhne odehrané zápasy. full_season=True stáhne celou sezónu."""
    if full_season:
        # Celá sezóna — bez omezení datumu
        fixtures = api_get("fixtures", {
            "league": league_id,
            "season": season,
            "status": "FT"
        })
    else:
        # Posledních N dní
        date_from = (datetime.utcnow() - timedelta(days=DAYS_BACK)).strftime("%Y-%m-%d")
        date_to   = datetime.utcnow().strftime("%Y-%m-%d")
        fixtures = api_get("fixtures", {
            "league": league_id,
            "season": season,
            "from":   date_from,
            "to":     date_to,
            "status": "FT"
        })
    return fixtures

def fetch_fixture_players(fixture_id):
    """Stáhne statistiky hráčů pro konkrétní zápas."""
    return api_get("fixtures/players", {"fixture": fixture_id})

# ── Zpracování ─────────────────────────────────────────────────────────────────

def process_league(league, existing_ids, full_season=False):
    lid    = league["id"]
    season = current_season(league["season_type"])
    lname  = league["name"]
    print(f"\n  {lname} (sezóna {season})")

    fixtures = fetch_fixtures(lid, season, full_season=full_season)
    if not fixtures:
        print(f"    Žádné nové zápasy")
        return 0, 0

    new_fixtures = [f for f in fixtures if f["fixture"]["id"] not in existing_ids]
    print(f"    Zápasů celkem: {len(fixtures)}, nových: {len(new_fixtures)}")

    matches_saved  = 0
    stats_saved    = 0

    for f in new_fixtures:
        fix     = f["fixture"]
        fix_id  = fix["id"]
        teams   = f["teams"]
        goals   = f["goals"]
        league_info = f["league"]

        # Ulož zápas
        match_row = {
            "id":         fix_id,
            "league_id":  lid,
            "season":     season,
            "round":      league_info.get("round", ""),
            "home_team":  teams["home"]["name"],
            "away_team":  teams["away"]["name"],
            "home_goals": goals.get("home"),
            "away_goals": goals.get("away"),
            "match_date": fix.get("date"),
        }
        sb_upsert("matches", [match_row])
        matches_saved += 1

        # Stáhni statistiky hráčů
        player_data = fetch_fixture_players(fix_id)
        stat_rows   = []

        for team_data in player_data:
            team_id   = team_data.get("team", {}).get("id")
            team_name = team_data.get("team", {}).get("name", "")
            for p_data in team_data.get("players", []):
                p     = p_data.get("player", {})
                stats = p_data.get("statistics", [{}])[0]
                games = stats.get("games", {})
                r     = games.get("rating")
                if not r:
                    continue  # přeskoč hráče bez ratingu

                stat_rows.append({
                    "player_id":    p.get("id"),
                    "match_id":     fix_id,
                    "league_id":    lid,
                    "season":       season,
                    "team_id":      team_id,
                    "team_name":    team_name,
                    "rating":       float(r),
                    "goals":        stats.get("goals", {}).get("total") or 0,
                    "assists":      stats.get("goals", {}).get("assists") or 0,
                    "minutes":      games.get("minutes") or 0,
                    "shots":        stats.get("shots", {}).get("total") or 0,
                    "passes":       stats.get("passes", {}).get("total") or 0,
                    "tackles":      stats.get("tackles", {}).get("total") or 0,
                    "yellow_cards": stats.get("cards", {}).get("yellow") or 0,
                    "red_cards":    stats.get("cards", {}).get("red") or 0,
                })

        if stat_rows:
            sb_upsert("player_match_stats", stat_rows)
            stats_saved += len(stat_rows)
            print(f"    ✓ {match_row['home_team']} vs {match_row['away_team']}: {len(stat_rows)} hráčů")

    return matches_saved, stats_saved

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'#'*50}")
    print(f"  FMScouts Match Scraper")
    print(f"  {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'#'*50}\n")

    if not API_KEY:
        print("❌ APIFOOTBALL_KEY není nastaven!")
        return
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("❌ SUPABASE_URL nebo SUPABASE_SERVICE_KEY není nastaven!")
        return

    print("Načítám existující zápasy z DB...")
    existing_ids = sb_get_match_ids()
    print(f"  V DB je {len(existing_ids)} zápasů\n")

    total_matches = 0
    total_stats   = 0

    # Pokud DAYS_BACK=0 nebo prázdná DB, stáhni celou sezónu
    full_season = DAYS_BACK == 0 or len(existing_ids) == 0
    if full_season:
        print("⚡ Stahuju celou sezónu!\n")
    else:
        print(f"📅 Stahuju posledních {DAYS_BACK} dní\n")

    for league in LEAGUES:
        m, s = process_league(league, existing_ids, full_season=full_season)
        total_matches += m
        total_stats   += s

    print(f"\n{'#'*50}")
    print(f"✅ Hotovo! Uloženo {total_matches} zápasů, {total_stats} hráčských výkonů")
    print(f"{'#'*50}")

if __name__ == "__main__":
    main()

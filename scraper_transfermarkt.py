"""
FMScouts — Transfermarkt scraper
Stahuje: přesnou pozici, tržní hodnotu, délku smlouvy
Spouštět jednou měsíčně lokálně.
Výsledky ukládá do data/tm_data.json
"""

import requests
import json
import time
import random
import re
from urllib.parse import quote_plus
from datetime import datetime
from pathlib import Path

OUTPUT = "data/tm_data.json"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
]

def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://www.transfermarkt.com/",
        "DNT": "1",
        "Connection": "keep-alive",
    }

def fetch(url, session):
    time.sleep(random.uniform(4, 8))
    try:
        r = session.get(url, headers=get_headers(), timeout=15)
        r.encoding = 'utf-8'
        if r.status_code == 200:
            return r.text
        print(f"  HTTP {r.status_code}")
        return None
    except Exception as e:
        print(f"  {e}")
        return None

def search_tm(query, session):
    """Jeden vyhledávací pokus na TM."""
    url = f"https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche?query={quote_plus(query)}"
    html = fetch(url, session)
    if not html:
        return None
    m = re.search(r'href="(/[^"]+/profil/spieler/\d+)"', html)
    if m:
        return "https://www.transfermarkt.com" + m.group(1)
    return None

def search_player(name, team, session):
    """Hledá hráče — zkouší více variant jména."""
    parts = name.strip().split()

    # Varianta 1: celé jméno
    url = search_tm(name, session)
    if url:
        return url

    # Varianta 2: první + poslední jméno (přeskočí prostřední)
    if len(parts) >= 3:
        short = parts[0] + ' ' + parts[-1]
        url = search_tm(short, session)
        if url:
            return url

    # Varianta 3: jen příjmení + tým
    if len(parts) >= 2:
        url = search_tm(parts[-1] + ' ' + team[:10], session)
        if url:
            return url

    # Varianta 4: jen příjmení
    if len(parts) >= 2:
        url = search_tm(parts[-1], session)
        if url:
            return url

    return None

def parse_player_page(html):
    """Parsuje profil hráče na Transfermarktu."""
    result = {}

    # Tržní hodnota — "Market value: €11.00m" nebo "Market value: €500k"
    mv = re.search(r'Market value:\s*(€[\d,.]+\s*(?:m|k|bn)?)', html, re.IGNORECASE)
    if mv:
        result['marketValue'] = mv.group(1).strip()

    # Pozice — "Central Midfield" nebo "Centre-Back" atd.
    pos = re.search(r'➤\s*([A-Za-z\s\-]+?)\s*➤\s*Market value', html)
    if pos:
        result['position'] = pos.group(1).strip()

    # Smlouva — "Contract expires: <span...>31/12/2027" nebo "Jun 30, 2027"
    contract = re.search(
        r'Contract expires[^<]*<[^>]+>\s*([^<]{4,20})',
        html, re.IGNORECASE
    )
    if contract:
        val = contract.group(1).strip()
        # Ověř že obsahuje rok
        if re.search(r'20[23]\d', val):
            result['contractUntil'] = val

    return result

def load_players():
    path = Path("data/players.json")
    if not path.exists():
        print("data/players.json nenalezen!")
        return []
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return d.get("players", [])

def load_existing():
    if Path(OUTPUT).exists():
        try:
            with open(OUTPUT, encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def save(data):
    Path(OUTPUT).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def main():
    print(f"\n{'#'*50}")
    print(f"  FMScouts Transfermarkt Scraper")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'#'*50}\n")

    players = load_players()
    if not players:
        return

    existing = load_existing()
    session = requests.Session()

    this_month = datetime.now().strftime("%Y-%m")
    to_process = []
    for p in players:
        pid = str(p.get("id"))
        ex = existing.get(pid, {})
        last = ex.get("lastUpdated", "")
        # Přeskoč jen hráče s úspěšnými daty z tohoto měsíce
        # Hráče s chybou zkus znovu
        if last[:7] == this_month and not ex.get("error"):
            continue
        to_process.append(p)

    print(f"Hráčů k zpracování: {len(to_process)}\n")

    ok = 0
    fail = 0

    for i, p in enumerate(to_process):
        pid = str(p.get("id"))
        firstname = p.get("firstname", "")
        lastname = p.get("lastname", "")
        name = p.get("name", "")
        full_name = (firstname + " " + lastname).strip() if firstname and lastname else name
        team = p.get("teamName", "")
        print(f"[{i+1}] {full_name} ({team})...", end=" ", flush=True)

        url = search_player(full_name, team, session)
        if not url:
            print("✗ nenalezen")
            fail += 1
            existing[pid] = {"lastUpdated": datetime.now().isoformat(), "error": "not found"}
            continue

        html = fetch(url, session)
        if not html:
            print("✗ chyba stránky")
            fail += 1
            continue

        data = parse_player_page(html)
        data["lastUpdated"] = datetime.now().isoformat()
        data["tmUrl"] = url
        existing[pid] = data

        parts = []
        if data.get("marketValue"): parts.append(data["marketValue"])
        if data.get("position"): parts.append(data["position"])
        if data.get("contractUntil"): parts.append("smlouva do " + data["contractUntil"])
        print("✓ " + (", ".join(parts) if parts else "nalezen, bez dat"))
        ok += 1

        if ok % 20 == 0:
            save(existing)
            print(f"  💾 Průběžně uloženo\n")

        if (i+1) % 50 == 0:
            pause = random.uniform(30, 60)
            print(f"  ☕ Pauza {pause:.0f}s...")
            time.sleep(pause)

    save(existing)
    print(f"\n{'#'*50}")
    print(f"✅ Hotovo! OK: {ok}, Chyby: {fail}")
    print(f"{'#'*50}")

if __name__ == "__main__":
    main()

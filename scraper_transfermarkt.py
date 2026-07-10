"""
FMScouts — Transfermarkt scraper
Stahuje: přesnou pozici, tržní hodnotu, délku smlouvy
Spouštět jednou měsíčně.
Výsledky ukládá do data/tm_data.json

Kromě čitelného textu data smlouvy (contractUntil) se snaží dopočítat i
strojově čitelné datum (contractUntilDate, formát YYYY-MM-DD), aby podle
smlouvy šlo v appce spolehlivě řadit. Pokud se text nepodaří rozpoznat
(neznámý formát/jazyk), contractUntilDate zůstane prázdné — appka pak
takového hráče při řazení podle smlouvy zařadí na konec, místo aby řazení
spadlo na chybu.
"""

import requests
import json
import time
import random
import os
import re
from datetime import datetime
from pathlib import Path

OUTPUT = "data/tm_data.json"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
]

# Názvy měsíců, se kterými se lze na Transfermarktu (podle jazyka stránky) setkat.
MONTH_NAMES = {
    # čeština
    "leden": 1, "únor": 2, "brezen": 3, "březen": 3, "duben": 4, "kveten": 5, "květen": 5,
    "cerven": 6, "červen": 6, "cervenec": 7, "červenec": 7, "srpen": 8,
    "zari": 9, "září": 9, "rijen": 10, "říjen": 10, "listopad": 11, "prosinec": 12,
    # angličtina
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
    # němčina (Transfermarkt je německý web, tohle se objevuje nejčastěji)
    "januar": 1, "februar": 2, "märz": 3, "marz": 3, "mai": 5, "juni": 6, "juli": 7,
    "oktober": 10, "dezember": 12,
}

def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Referer": "https://www.transfermarkt.com/",
        "DNT": "1",
    }

def fetch(url, session):
    time.sleep(random.uniform(4, 8))
    try:
        r = session.get(url, headers=get_headers(), timeout=15)
        if r.status_code == 200:
            return r.text
        print(f"  ✗ HTTP {r.status_code}: {url}")
        return None
    except Exception as e:
        print(f"  ✗ {e}")
        return None

def search_player(name, team, session):
    """Hledá hráče na Transfermarktu podle jména."""
    query = name.replace(' ', '+')
    url = f"https://www.transfermarkt.com/schnellsuche/ergebnis/schnellsuche?query={query}"
    html = fetch(url, session)
    if not html:
        return None

    # Hledej odkaz na hráče + kontroluj shodu klubu
    pattern = r'href="(/[^"]+/profil/spieler/\d+)"[^>]*>([^<]+)</a>.*?<td[^>]*>([^<]*(?:' + re.escape(team[:6]) + r')[^<]*)</td>'
    matches = re.findall(pattern, html, re.IGNORECASE | re.DOTALL)
    
    if matches:
        return "https://www.transfermarkt.com" + matches[0][0]
    
    # Fallback — první výsledek hráče
    simple = re.search(r'href="(/[^"]+/profil/spieler/(\d+))"', html)
    if simple:
        return "https://www.transfermarkt.com" + simple.group(1)
    
    return None

def parse_contract_date(raw):
    """
    Zkusí převést volný text data smlouvy (různé jazyky/formáty z Transfermarktu)
    na strojově čitelné ISO datum YYYY-MM-DD. Vrátí None, pokud formát nerozpozná.
    """
    if not raw:
        return None
    raw = raw.strip()

    # Formát DD.MM.YYYY nebo DD/MM/YYYY
    m = re.match(r'^(\d{1,2})[.\/](\d{1,2})[.\/](\d{4})$', raw)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return datetime(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            return None

    # Formát "30. červen 2027" / "30 June 2027" / "30. Juni 2027" (den před měsícem)
    m = re.search(r'(\d{1,2})\.?\s+([A-Za-zÁ-Žá-ž]+)\.?,?\s+(\d{4})', raw)
    if m:
        day = int(m.group(1))
        month = MONTH_NAMES.get(m.group(2).lower())
        year = int(m.group(3))
        if month:
            try:
                return datetime(year, month, day).strftime("%Y-%m-%d")
            except ValueError:
                return None

    # Formát "June 30, 2027" (měsíc před dnem)
    m = re.search(r'([A-Za-zÁ-Žá-ž]+)\.?\s+(\d{1,2}),?\s+(\d{4})', raw)
    if m:
        month = MONTH_NAMES.get(m.group(1).lower())
        day = int(m.group(2))
        year = int(m.group(3))
        if month:
            try:
                return datetime(year, month, day).strftime("%Y-%m-%d")
            except ValueError:
                return None

    return None

def parse_player_page(html):
    """Parsuje profil hráče na Transfermarktu."""
    result = {}

    # Tržní hodnota
    mv = re.search(r'<a[^>]+class="[^"]*market-value[^"]*"[^>]*>([^<]+)</a>', html)
    if not mv:
        mv = re.search(r'class="[^"]*marketValue[^"]*"[^>]*>\s*<[^>]+>\s*([\d,.]+\s*(?:mil\.|tis\.)?[\s€£$]?)', html)
    if mv:
        result['marketValue'] = mv.group(1).strip()

    # Přesná pozice
    pos = re.search(r'Pozice\s*</span>\s*<[^>]+>\s*<[^>]+>([^<]+)</a>', html)
    if not pos:
        pos = re.search(r'Position.*?<td[^>]*>\s*([^<\n]{3,30})\s*</td>', html, re.DOTALL)
    if pos:
        result['position'] = pos.group(1).strip()

    # Délka smlouvy
    contract = re.search(r'(?:Smlouva do|Contract expires|Vertrag bis)[^<]*</[^>]+>\s*<[^>]+>\s*([^<]+)</td>', html, re.IGNORECASE)
    if not contract:
        contract = re.search(r'(\d{1,2}\.\s*(?:leden|únor|březen|duben|květen|červen|červenec|srpen|září|říjen|listopadu|prosinec|\w+)\s*\d{4})', html)
    if contract:
        result['contractUntil'] = contract.group(1).strip()
        parsed = parse_contract_date(result['contractUntil'])
        if parsed:
            result['contractUntilDate'] = parsed

    return result

def load_players():
    """Načte hráče z players.json."""
    path = Path("data/players.json")
    if not path.exists():
        print("❌ data/players.json nenalezen!")
        return []
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return d.get("players", [])

def load_existing():
    """Načte existující TM data."""
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
    print(f"  {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'#'*50}\n")

    players = load_players()
    if not players:
        return

    existing = load_existing()
    session = requests.Session()

    # Přeskoč hráče aktualizované tento měsíc
    this_month = datetime.utcnow().strftime("%Y-%m")
    to_process = []
    for p in players:
        pid = str(p.get("id"))
        last = existing.get(pid, {}).get("lastUpdated", "")
        if last[:7] != this_month:
            to_process.append(p)

    print(f"Hráčů k zpracování: {len(to_process)} (přeskočeno {len(players)-len(to_process)})\n")

    ok = 0
    fail = 0

    for i, p in enumerate(to_process):
        pid = str(p.get("id"))
        name = p.get("name", "")
        team = p.get("teamName", "")
        print(f"[{i+1}/{len(to_process)}] {name} ({team})...", end=" ", flush=True)

        url = search_player(name, team, session)
        if not url:
            print("✗ nenalezen")
            fail += 1
            existing[pid] = {"lastUpdated": datetime.utcnow().isoformat(), "error": "not found"}
            continue

        html = fetch(url, session)
        if not html:
            print("✗ chyba stránky")
            fail += 1
            continue

        data = parse_player_page(html)
        data["lastUpdated"] = datetime.utcnow().isoformat()
        data["tmUrl"] = url
        existing[pid] = data

        parts = []
        if data.get("marketValue"): parts.append(data["marketValue"])
        if data.get("position"): parts.append(data["position"])
        if data.get("contractUntil"): parts.append("smlouva do " + data["contractUntil"])
        print("✓ " + (", ".join(parts) if parts else "bez dat"))
        ok += 1

        # Ukládej každých 20 hráčů
        if ok % 20 == 0:
            save(existing)
            print(f"  💾 Průběžně uloženo\n")

        # Delší pauza každých 50 requestů
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

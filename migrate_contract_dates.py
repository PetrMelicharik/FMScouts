"""
FMScouts — jednorázová migrace dat Transfermarktu

Doplní strojově čitelné datum konce smlouvy (contractUntilDate) do už
nascrapovaných záznamů v data/tm_data.json, aniž by bylo nutné znovu
spouštět celý (pomalý) scraper_transfermarkt.py. Pracuje jen s daty, která
už máte na disku — žádné požadavky na Transfermarkt, běží okamžitě.

Použití (spustit v kořeni projektu, kde je složka data/):
    python migrate_contract_dates.py

Bezpečné spustit opakovaně — záznamy, které už contractUntilDate mají,
se přeskočí a nepřepíšou.
"""

import json
import re
from datetime import datetime
from pathlib import Path

TM_DATA_PATH = "data/tm_data.json"

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

def main():
    path = Path(TM_DATA_PATH)
    if not path.exists():
        print(f"❌ {TM_DATA_PATH} nenalezen — spusť tento skript v kořeni projektu (tam, kde je složka data/).")
        return

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    updated = 0
    already_had = 0
    unparseable = 0
    no_contract = 0
    unparseable_samples = []

    for pid, entry in data.items():
        if not isinstance(entry, dict):
            continue
        if entry.get("contractUntilDate"):
            already_had += 1
            continue
        raw = entry.get("contractUntil")
        if not raw:
            no_contract += 1
            continue
        parsed = parse_contract_date(raw)
        if parsed:
            entry["contractUntilDate"] = parsed
            updated += 1
        else:
            unparseable += 1
            if len(unparseable_samples) < 10:
                unparseable_samples.append(raw)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n{'#'*50}")
    print(f"✅ Hotovo!")
    print(f"   Doplněno nových dat:        {updated}")
    print(f"   Už datum mělo (přeskočeno): {already_had}")
    print(f"   Bez údaje o smlouvě:        {no_contract}")
    print(f"   Nešlo rozpoznat formát:     {unparseable}")
    if unparseable_samples:
        print(f"\n   Ukázka nerozpoznaných textů (zkontroluj, jestli nejde formát doplnit):")
        for s in unparseable_samples:
            print(f"     - {s!r}")
    print(f"{'#'*50}\n")

if __name__ == "__main__":
    main()
